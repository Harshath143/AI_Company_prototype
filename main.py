import sys
import os
import re
import traceback
from datetime import datetime

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.orchestrator import Orchestrator
from core.logger import logger
from dotenv import load_dotenv

load_dotenv()

# Maximum allowed length for a user requirement string
_MAX_REQUIREMENT_LEN = 2000

def slugify(text: str) -> str:
    """
    Convert a human requirement into a safe directory name.
    'Build a snake game' -> 'build_a_snake_game'
    """
    text = text.strip().lower()
    text = re.sub(r'[^\w\s-]', '', text)       # strip special chars
    text = re.sub(r'[\s\-]+', '_', text)        # spaces/hyphens -> underscores
    text = re.sub(r'_+', '_', text).strip('_')  # collapse duplicates
    return text[:80]                             # cap at 80 chars

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <project_requirement>")
        print("Example: python main.py 'Create a Snake game in Python'")
        return

    # Validate input
    user_requirement = sys.argv[1].strip()
    if not user_requirement:
        print("Error: Requirement cannot be empty.")
        sys.exit(1)
    if len(user_requirement) > _MAX_REQUIREMENT_LEN:
        print(f"Error: Requirement too long (max {_MAX_REQUIREMENT_LEN} chars, got {len(user_requirement)}).")
        sys.exit(1)

    # Derive an isolated project folder from the requirement string
    project_name = slugify(user_requirement)
    projects_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")
    project_dir = os.path.join(projects_base, project_name)

    # A-2 (R2): Append a timestamp suffix if the folder already exists
    # Prevents silently overwriting a previous build of the same project
    if os.path.exists(project_dir):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = f"{project_dir}_{stamp}"
        logger.info(f"Project folder already exists. Using timestamped path: {project_dir}")

    os.makedirs(project_dir, exist_ok=True)

    print(f"\n📁 Project folder: {project_dir}\n")
    logger.info(f"Project directory: {project_dir}")

    orchestrator = Orchestrator()
    try:
        result = orchestrator.run(user_requirement, project_dir)
        print("\n\n*** NEOFORGE AI EXECUTION COMPLETE ***")
        print(f"Project output: {project_dir}")
        print("Final Result:")
        print(result)
        print("\n\n*** FINAL_RELEASE_STAMP: NEOFORGE_AI_READY ***")
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
