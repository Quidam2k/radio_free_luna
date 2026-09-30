"""
Text backend for DJ commentary (#6019).

DJ_LLM=openai      (default) the OpenAI-compatible client the generator already holds.
DJ_LLM=claude_cli  `claude -p` on Todd's Claude subscription, model DJ_LLM_MODEL
                   (default claude-sonnet-5-5). Windowless, no tools, no MCP, no session
                   transcript. Raises on any failure so callers fall back as before.
"""

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CLI_CWD = PROJECT_ROOT / "data" / "runtime" / "dj_llm"
_CLI_TIMEOUT_S = 90


def backend() -> str:
    return os.getenv("DJ_LLM", "openai").strip().lower() or "openai"


def cli_model() -> str:
    return os.getenv("DJ_LLM_MODEL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"


def claude_cli_complete(system: str, prompt: str, timeout: float = _CLI_TIMEOUT_S) -> str:
    """One completion via `claude -p`. Prompt goes over stdin; returns stripped text."""
    _CLI_CWD.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["claude", "-p", "--model", cli_model(),
         "--system-prompt", system,
         "--tools", "",
         "--strict-mcp-config",
         "--no-session-persistence"],
        input=prompt, capture_output=True, text=True, encoding="utf-8",
        timeout=timeout, cwd=str(_CLI_CWD),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p exit {result.returncode}: {(result.stderr or '')[:200]}")
    text = (result.stdout or "").strip()
    if not text:
        raise ValueError("Empty completion from claude -p")
    return text
