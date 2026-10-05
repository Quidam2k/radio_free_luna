"""
Text backend for DJ commentary (#6019).

DJ_LLM=openai      (default) the OpenAI-compatible client the generator already holds.
DJ_LLM=claude_cli  `claude -p` on Todd's Claude subscription, model DJ_LLM_MODEL
                   (default claude-sonnet-5-5; claude-haiku-4-5-20251001 for the cheap host).
                   Windowless, no tools, no MCP, no session transcript.
DJ_LLM=local       an OpenAI-compatible local server (#6914), LM Studio by default:
                   DJ_LOCAL_BASE_URL (http://127.0.0.1:1234/v1), DJ_LOCAL_MODEL.
                   Output is schema-constrained to {"bridge": "..."}. GPU etiquette (#2057):
                   DJ_LOCAL_UNLOAD=ttl:<seconds> (default ttl:300, LM Studio unloads the
                   model after that much idle), after_call (`lms unload` right away), or never.
Every backend raises on any failure so callers fall back as before.
"""

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CLI_CWD = PROJECT_ROOT / "data" / "runtime" / "dj_llm"
_CLI_TIMEOUT_S = 90


def backend() -> str:
    return os.getenv("DJ_LLM", "openai").strip().lower() or "openai"


def cli_model() -> str:
    return os.getenv("DJ_LLM_MODEL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"


def claude_cli_complete(system: str, prompt: str, timeout: float = _CLI_TIMEOUT_S,
                        model: str = None) -> str:
    """One completion via `claude -p`. Prompt goes over stdin; returns stripped text."""
    _CLI_CWD.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["claude", "-p", "--model", model or cli_model(),
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


def local_base_url() -> str:
    return os.getenv("DJ_LOCAL_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")


def local_model() -> str:
    return os.getenv("DJ_LOCAL_MODEL", "google/gemma-4-12b").strip()


def local_unload_mode() -> str:
    return os.getenv("DJ_LOCAL_UNLOAD", "ttl:300").strip().lower()


_BRIDGE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "dj_line",
        "strict": True,
        "schema": {"type": "object", "properties": {"bridge": {"type": "string"}},
                   "required": ["bridge"], "additionalProperties": False},
    },
}


def local_complete(system: str, prompt: str, model: str = None,
                   timeout: float = _CLI_TIMEOUT_S) -> str:
    """One completion from the local OpenAI-compatible server; returns the spoken text.

    LM Studio loads the model on demand (JIT). The ttl field makes it unload after
    DJ_LOCAL_UNLOAD idle seconds; after_call unloads it with `lms` as soon as we're done.
    """
    model = model or local_model()
    if "qwen3" in model.lower():
        system += "\n/no_think"
    body = {"model": model, "temperature": 0.8, "max_tokens": 400,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "response_format": _BRIDGE_SCHEMA}
    mode = local_unload_mode()
    if mode.startswith("ttl:"):
        body["ttl"] = int(mode[4:] or 300)
    req = urllib.request.Request(f"{local_base_url()}/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    finally:
        if mode == "after_call":
            unload_local(model)
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    try:
        text = json.loads(text).get("bridge", text)
    except (ValueError, AttributeError):
        pass
    text = str(text).strip()
    if not text:
        raise ValueError("Empty completion from local model")
    return text


def unload_local(model: str = None) -> bool:
    """Unload the local model now (`lms unload`). Never raises; True on success."""
    lms = shutil.which("lms") or str(Path.home() / ".cache" / "lm-studio" / "bin" / "lms.exe")
    try:
        result = subprocess.run([lms, "unload", model or local_model()], capture_output=True,
                                text=True, timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.returncode == 0
    except Exception:
        return False


def complete(system: str, prompt: str, backend_name: str = None, model: str = None) -> str:
    """Blocking completion on a non-OpenAI backend (claude_cli or local). Raises on failure."""
    name = backend_name or backend()
    if name == "local":
        return local_complete(system, prompt, model=model)
    if name == "claude_cli":
        return claude_cli_complete(system, prompt, **({"model": model} if model else {}))
    raise ValueError(f"unknown DJ_LLM backend {name!r}")
