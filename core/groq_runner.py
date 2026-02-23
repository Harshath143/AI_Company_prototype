"""
Direct Groq API runner with API key rotation pool.
When one key hits a rate limit, instantly switches to the next key.
Only sleeps if ALL keys are exhausted in a rotation cycle.
"""
import os
import json
import time
import random
from openai import OpenAI
from core.file_system import FileSystem
from core.logger import logger

# Tool definitions in OpenAI JSON schema format
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path to write to."},
                    "content": {"type": "string", "description": "Content to write into the file."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path to read from."}
                },
                "required": ["path"]
            }
        }
    }
]


def _execute_tool(name: str, args: dict, project_root: str) -> str:
    """Dispatch a tool call, passing project_root for safe file scoping (C-2 R2)."""
    if name == "write_file":
        return FileSystem.write_file(args["path"], args["content"], project_root=project_root)
    elif name == "read_file":
        return FileSystem.read_file(args["path"], project_root=project_root)
    return f"Unknown tool: {name}"


def _make_client(api_key: str) -> OpenAI:
    """Create a single OpenAI-compatible client for the given key."""
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_API_BASE", "https://api.groq.com/openai/v1")
    )


def build_client_pool() -> list[OpenAI]:
    """
    Build a pool of OpenAI clients, one per available GROQ API key.
    Reads GROQ_API_KEY (primary) and GROQ_API_KEY_2 through GROQ_API_KEY_5.
    A-1 (R2): Logs a masked identifier for each active key for debuggability.
    """
    keys = []
    primary = os.getenv("GROQ_API_KEY", "").strip()
    if primary and not primary.startswith("your_"):
        keys.append(primary)

    for i in range(2, 6):
        key = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
        if key and not key.startswith("your_"):
            keys.append(key)

    if not keys:
        raise ValueError("No valid GROQ API keys found. Set GROQ_API_KEY in .env")

    logger.info(f"API key pool initialized with {len(keys)} key(s):")
    for i, key in enumerate(keys):
        # A-1 (R2): Show masked key so the user can verify which keys are active
        masked = key[:8] + "..." + key[-4:]
        logger.info(f"  Key {i + 1}: {masked}")

    return [_make_client(k) for k in keys]


def run_agent(
    system_prompt: str,
    user_message: str,
    model: str,
    clients: list[OpenAI],
    project_root: str,
    viz_state=None,
    agent_name: str = "Agent",
) -> str:
    """
    Run a single agent turn using direct Groq API calls with JSON tool use.

    C-1 (R2): Rate-limit events do NOT consume tool-call iterations.
              Separate counters for work done vs rate-limit retries.
    C-2 (R2): project_root scopes all file I/O — no os.chdir() needed.
    A-4 (R2): max_tool_calls raised to 25 to handle complex multi-file projects.
    N-1 (R2): clients typed as list[OpenAI].
    """
    model_id = model.replace("groq/", "")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    logger.info(f"[{agent_name}] Starting | model={model_id} | keys={len(clients)} | root={project_root}")
    if viz_state:
        viz_state.update(agent_name, "Thinking...")

    # C-1 (R2): Two independent counters — work iterations vs rate-limit retries
    max_tool_calls = 25        # A-4: raised from 15
    max_rate_retries = 30      # total rate-limit hits before giving up
    max_tool_fail_retries = 2

    tool_calls_made = 0        # counts real productive API calls
    rate_limit_hits = 0        # counts rate-limit events (separate from work)
    tool_fail_retries = 0

    # Key rotation state
    client_idx = 0
    cycle_count = 0
    base_wait = 20

    while tool_calls_made < max_tool_calls and rate_limit_hits < max_rate_retries:
        current_client = clients[client_idx]

        try:
            response = current_client.chat.completions.create(
                model=model_id,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
            )
            # Successful API call — reset cycle state
            cycle_count = 0
            tool_calls_made += 1

        except Exception as e:
            error_str = str(e)

            # --- Rate limit: rotate to next key without consuming a tool_call slot ---
            if "rate_limit_exceeded" in error_str:
                rate_limit_hits += 1
                next_idx = (client_idx + 1) % len(clients)
                all_exhausted = (next_idx == 0)

                if all_exhausted:
                    cycle_count += 1
                    wait = base_wait * (2 ** (cycle_count - 1)) + random.uniform(0, 5)
                    logger.warning(
                        f"[{agent_name}] All {len(clients)} key(s) exhausted "
                        f"(cycle {cycle_count}). Waiting {wait:.1f}s..."
                    )
                    if viz_state:
                        viz_state.update(agent_name, f"All keys exhausted. Waiting {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    logger.warning(
                        f"[{agent_name}] Key [{client_idx+1}/{len(clients)}] rate-limited. "
                        f"Rotating → key [{next_idx+1}/{len(clients)}] "
                        f"(rate hits: {rate_limit_hits}/{max_rate_retries})"
                    )
                    if viz_state:
                        viz_state.update(agent_name, f"Rotating → key [{next_idx+1}/{len(clients)}]...")

                client_idx = next_idx
                # NOTE: no increment to tool_calls_made — rate limits don't count as work
                continue

            # --- Malformed tool call (small models using XML syntax) ---
            if "tool_use_failed" in error_str and tool_fail_retries < max_tool_fail_retries:
                tool_fail_retries += 1
                logger.warning(
                    f"[{agent_name}] Malformed tool call "
                    f"(attempt {tool_fail_retries}/{max_tool_fail_retries}). Injecting correction..."
                )
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous tool call was malformed. "
                        "You MUST call tools using the provided JSON function schema — "
                        "do NOT use XML-style <function=...> syntax. Please retry."
                    )
                })
                continue

            raise

        msg = response.choices[0].message

        # No tool calls — agent is done
        if not msg.tool_calls:
            result = msg.content or ""
            logger.info(
                f"[{agent_name}] Completed. "
                f"Output: {len(result)} chars | tool calls: {tool_calls_made} | rate hits: {rate_limit_hits}"
            )
            return result

        # Process tool calls
        messages.append(msg)
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name

            # Guard against malformed JSON from model
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                logger.error(f"[{agent_name}] Malformed tool args for {fn_name}: {e}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": "Error: Could not parse tool arguments. Please retry with valid JSON."
                })
                continue

            logger.info(f"[{agent_name}] Tool: {fn_name}({list(fn_args.keys())})")
            if viz_state:
                viz_state.update(agent_name, f"Using tool: {fn_name}")

            tool_result = _execute_tool(fn_name, fn_args, project_root=project_root)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result
            })

    if rate_limit_hits >= max_rate_retries:
        logger.error(f"[{agent_name}] Aborted: too many rate-limit hits ({rate_limit_hits}).")
        return f"Agent aborted: rate limit hit {rate_limit_hits} times."

    logger.warning(f"[{agent_name}] Reached max tool calls ({max_tool_calls}) without finishing.")
    return "Agent reached max tool calls."
