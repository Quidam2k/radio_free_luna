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
DJ_LLM=anthropic   the Anthropic Messages API on its own key (#4154): ANTHROPIC_API_KEY from the
                   environment, else read from DJ_ANTHROPIC_ENV_FILE (Q:/Pantheon/.env). Patter on
                   DJ_PATTER_MODEL (claude-haiku-5-5), planning/picking on DJ_PLANNER_MODEL
                   (claude-sonnet-5-5). Raw HTTPS, not the SDK: anthropic 1.x needs anyio>=4 and
                   FastAPI 0.104 pins anyio<4. Every call is checked against and recorded in the
                   spend ledger (src/dj/spend.py); over cap it raises like any other failure.
Every backend raises on any failure so callers fall back as before.
"""

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from . import spend

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
    _require_loaded(model)
    if "qwen3" in model.lower():
        system += "\n/no_think"
    # Reasoning models (Gemma 4, Qwen3) think before answering; 400 tokens left no answer
    body = {"model": model, "temperature": 0.8, "max_tokens": 2000,
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


def _require_loaded(model: str) -> None:
    """Refuse unless `model` is ALREADY loaded (#6926). A request naming an unloaded model
    makes LM Studio JIT-load it onto Solace's GPU, which is Todd's to grant, not ours."""
    root = local_base_url().rsplit("/v1", 1)[0]
    try:
        with urllib.request.urlopen(f"{root}/api/v0/models", timeout=5) as resp:
            models = json.loads(resp.read().decode("utf-8")).get("data", [])
    except Exception as e:
        raise RuntimeError(f"cannot confirm {model} is loaded ({e}); refusing a JIT load")
    if not any(m.get("id") == model and m.get("state") == "loaded" for m in models):
        raise RuntimeError(f"{model} is not loaded in LM Studio; refusing to JIT-load it")


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


_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_TIMEOUT_S = 60


def patter_model() -> str:
    return os.getenv("DJ_PATTER_MODEL", "claude-haiku-5-5").strip() or "claude-haiku-5-5"


def planner_model() -> str:
    return os.getenv("DJ_PLANNER_MODEL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"


def _anthropic_key() -> str:
    """The API key from the environment or the env file. Never logged, never returned to callers."""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    env_file = Path(os.getenv("DJ_ANTHROPIC_ENV_FILE", "Q:/Pantheon/.env"))
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == "ANTHROPIC_API_KEY":
                return value.strip().strip('"').strip("'")
    except OSError:
        pass
    raise RuntimeError("ANTHROPIC_API_KEY not found in environment or DJ_ANTHROPIC_ENV_FILE")


def anthropic_messages(body: dict, purpose: str, timeout: float = _ANTHROPIC_TIMEOUT_S) -> dict:
    """POST one Messages API request after the spend check; record its usage. Returns the JSON.

    Raises spend.CapExceeded over cap, RuntimeError on HTTP/refusal, so callers fall back."""
    spend.check()
    req = urllib.request.Request(
        _ANTHROPIC_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": _anthropic_key(),
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Anthropic API {e.code}: {detail}") from None
    spend.record(data.get("model") or body["model"], purpose, data.get("usage") or {})
    if data.get("stop_reason") == "refusal":
        raise RuntimeError("Anthropic API refused the request")
    return data


def anthropic_complete(system: str, prompt: str, model: str = None, purpose: str = "patter",
                       effort: str = "low", max_tokens: int = 2000) -> str:
    """One text completion on the Anthropic API. The system prompt is cached (it is the
    stable part: base voice + persona + Chris style); the prompt carries the per-break facts."""
    data = anthropic_messages({
        "model": model or patter_model(), "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": effort},
    }, purpose)
    text = "".join(b.get("text", "") for b in data.get("content") or []
                   if b.get("type") == "text").strip()
    if not text:
        raise ValueError(f"Empty completion from {data.get('model')} "
                         f"(stop_reason={data.get('stop_reason')})")
    return text


def complete(system: str, prompt: str, backend_name: str = None, model: str = None) -> str:
    """Blocking completion on a non-OpenAI backend (claude_cli, local, anthropic). Raises on failure."""
    name = backend_name or backend()
    if name == "anthropic":
        return anthropic_complete(system, prompt, model=model)
    if name == "local":
        return local_complete(system, prompt, model=model)
    if name == "claude_cli":
        return claude_cli_complete(system, prompt, **({"model": model} if model else {}))
    raise ValueError(f"unknown DJ_LLM backend {name!r}")
