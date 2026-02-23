import os
import time
import threading
import urllib.request
from datetime import datetime
from core.logger import logger
from core.file_system import FileSystem, PROJECT_SUBDIRS
from core.groq_runner import run_agent, build_client_pool
from viz.server import run_in_thread, VizState

# ---------------------------------------------------------------------------
# Agent system prompts — ONE output per prompt (critical for 8B model reliability)
# ---------------------------------------------------------------------------

PM_PRD_PROMPT = """You are a Project Manager. Write a detailed Product Requirements Document for the given project.
Call write_file ONCE with path='PRD.md' containing a thorough PRD. Then stop."""

PM_ARCH_PROMPT = """You are a Project Manager and System Architect.
First, call read_file with path='PRD.md' to read the requirements.
Then call write_file ONCE with path='ARCHITECTURE.md'.

The ARCHITECTURE.md must describe:
1. Technology stack choices
2. Folder layout:
   - src/      : main source code files (list each file with its purpose)
   - tests/    : unit test files
   - frontend/ : HTML/CSS/JS files (if applicable)
   - logs/     : runtime log files
3. List all source files explicitly, e.g:
   src/snake.py - Snake class, movement logic
   src/food.py  - Food class, random placement
   src/game.py  - Game loop, scoring, input handling
   frontend/index.html - Game canvas and UI (if using browser)"""

TL_PROMPT = """You are a Team Lead. Break the project into development tasks.
First, call read_file with path='PRD.md'.
Then, call read_file with path='ARCHITECTURE.md'.
Then, call write_file ONCE with path='TASK_LIST.json'.

The JSON must be an array of task objects, each with: id, name, description, files.
The 'files' key must list REAL source file paths that match ARCHITECTURE.md, e.g:
  ["src/snake.py", "src/food.py", "src/game.py"]

Critical rules:
- Do NOT use names like 'file1.txt'.
- Use paths from the architecture (src/, frontend/, tests/).
- Stop after writing TASK_LIST.json."""

DEV_IMPL_PROMPT = """You are a senior Developer. Implement ALL project source files listed in TASK_LIST.json.

Steps:
1. Call read_file with path='ARCHITECTURE.md'
2. Call read_file with path='TASK_LIST.json'
3. For EVERY file in the 'files' array of every task, call write_file with COMPLETE working code.
   - Use the exact path from the task list (e.g. 'src/snake.py').
   - Write REAL runnable code — no placeholders, no pseudocode, no TODO comments.
   - Include all imports, classes, functions, and a working main() or entry point.

For a Python Snake game, implement real logic:
  - Grid-based movement with boundary/self-collision detection
  - Keyboard input handling
  - Food spawning at random empty cells
  - Score display and game-over screen

Write every file. Stop only after ALL files are written."""

VALIDATOR_PROMPT = """You are a Code Reviewer. Validate the generated source files.
1. Call read_file with path='TASK_LIST.json' to get the file list.
2. Call read_file for each source file.
3. Call write_file ONCE with path='VALIDATION_REPORT.md' — a real report with CRITICAL/ADVISORY/NITPICK findings.
Stop after writing the report."""

TESTER_PROMPT = """You are a QA Engineer. Write unit tests for the project.
1. Call read_file with path='TASK_LIST.json' to get the file list.
2. Call read_file for each source file (once each).
3. Call write_file ONCE with path='tests/test_main.py' using pytest.
   - Include happy path, edge case, and error condition tests.
Stop immediately after writing. Do NOT re-read or rewrite the test file."""


def _wait_for_viz_server(
    thread: threading.Thread,
    host: str = "127.0.0.1",
    port: int = 8000,
    timeout: float = 10.0
):
    """Poll until viz server is ready and verify the thread is alive."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not thread.is_alive():
            logger.warning(
                "Visualizer server thread has died — "
                "port 8000 may already be in use. Continuing without viz."
            )
            return
        try:
            urllib.request.urlopen(f"http://{host}:{port}", timeout=0.5)
            logger.info("Visualizer server is ready.")
            return
        except Exception:
            time.sleep(0.25)
    logger.warning("Visualizer server did not become ready in time. Continuing anyway.")


class Orchestrator:
    def __init__(self):
        logger.info("Initializing NeoForge AI Orchestrator...")
        viz_thread = run_in_thread()
        VizState.update("System", "Initializing...")
        self.clients = build_client_pool()
        self.model = os.getenv("OPENAI_MODEL_NAME", "groq/llama-3.3-70b-versatile")
        _wait_for_viz_server(viz_thread)

    def run(self, user_requirement: str, project_dir: str) -> str:
        """
        Run the full pipeline. Each step calls run_agent for ONE specific output file.
        This is the critical design choice for 8B model reliability:
          - one agent call = one output file = reliable completion
        """
        logger.info(f"Starting orchestration for: {user_requirement}")
        logger.info(f"Output directory: {project_dir}")

        # Create standard subdirectories upfront
        for subdir in PROJECT_SUBDIRS:
            os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

        # Shared call helper — scopes all file I/O to project_dir
        def call(agent_name: str, prompt: str, message: str):
            VizState.update(agent_name, message[:60])
            return run_agent(
                system_prompt=prompt,
                user_message=message,
                model=self.model,
                clients=self.clients,
                project_root=project_dir,
                viz_state=VizState,
                agent_name=agent_name,
            )

        # ── Phase 1a: PM writes PRD.md ─────────────────────────────────────
        call("Project Manager",
             PM_PRD_PROMPT,
             f"Write a PRD for this project: {user_requirement}")

        # Verify PRD was created before continuing
        prd_path = os.path.join(project_dir, "PRD.md")
        if not os.path.exists(prd_path):
            logger.error("PM failed to create PRD.md. Aborting.")
            raise RuntimeError("PRD.md not created by Project Manager agent.")

        # ── Phase 1b: PM writes ARCHITECTURE.md ───────────────────────────
        call("Architect",
             PM_ARCH_PROMPT,
             "Read PRD.md, then write ARCHITECTURE.md with the folder layout and file list.")

        # Verify ARCHITECTURE created before TL runs
        arch_path = os.path.join(project_dir, "ARCHITECTURE.md")
        if not os.path.exists(arch_path):
            logger.error("Architect failed to create ARCHITECTURE.md. Aborting.")
            raise RuntimeError("ARCHITECTURE.md not created by Architect agent.")

        # ── Phase 2: TL writes TASK_LIST.json ─────────────────────────────
        call("Team Lead",
             TL_PROMPT,
             "Read PRD.md and ARCHITECTURE.md, then write TASK_LIST.json.")

        task_path = os.path.join(project_dir, "TASK_LIST.json")
        if not os.path.exists(task_path):
            logger.error("Team Lead failed to create TASK_LIST.json. Aborting.")
            raise RuntimeError("TASK_LIST.json not created by Team Lead agent.")

        # ── Phase 3: Developer writes all src/ files ───────────────────────
        call("Developer",
             DEV_IMPL_PROMPT,
             "Read ARCHITECTURE.md and TASK_LIST.json. Implement every source file listed.")

        # ── Phase 4: Validator writes VALIDATION_REPORT.md ────────────────
        call("Backend Logic Validator",
             VALIDATOR_PROMPT,
             "Read TASK_LIST.json, read each source file, write VALIDATION_REPORT.md.")

        # ── Phase 5: Tester writes tests/test_main.py ─────────────────────
        call("QA Tester",
             TESTER_PROMPT,
             "Read TASK_LIST.json, read each source file once, write tests/test_main.py.")

        VizState.update("System", "Orchestration Complete")
        logger.info("Orchestration complete.")
        return f"NeoForge AI pipeline completed. Output in: {project_dir}"
