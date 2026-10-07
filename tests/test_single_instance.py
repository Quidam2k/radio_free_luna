"""Cross-process single-instance lock tests. # #3840"""

import importlib.util
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

import pytest

from src.single_instance import acquire

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and importlib.util.find_spec("fcntl") is None,
    reason="Requires Windows named mutexes or fcntl.flock",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HOLDER_SCRIPT = """
import time
from src.single_instance import ensure_single_instance

ensure_single_instance()
print("HELD", flush=True)
time.sleep(30)
"""
ACQUIRE_SCRIPT = """
import sys
from src.single_instance import ALREADY_RUNNING_EXIT, acquire

sys.exit(ALREADY_RUNNING_EXIT if acquire() is None else 0)
"""


@pytest.fixture
def instance_env(monkeypatch):
    name = f"Local\\RFL-test-{uuid.uuid4().hex}"
    monkeypatch.setenv("RFL_INSTANCE_MUTEX", name)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _start_holder(env):
    return subprocess.Popen(
        [sys.executable, "-c", HOLDER_SCRIPT],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_held(process, timeout=20):
    lines = queue.Queue()

    def read_stdout():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=read_stdout, daemon=True).start()
    deadline = time.monotonic() + timeout
    observed = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail(f"Timed out waiting for HELD; stdout: {observed!r}")
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            pytest.fail(f"Timed out waiting for HELD; stdout: {observed!r}")
        if line is None:
            pytest.fail(
                f"Holder closed stdout before HELD; stdout: {observed!r}"
            )
        observed.append(line.rstrip())
        if line.strip() == "HELD":
            return


def _cleanup(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_second_copy_exits_3(instance_env):
    holder = None
    try:
        holder = _start_holder(instance_env)
        _wait_for_held(holder)
        second = subprocess.run(
            [sys.executable, "-c", HOLDER_SCRIPT],
            cwd=REPO_ROOT,
            env=instance_env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert second.returncode == 3, second.stderr
        assert "already running" in second.stderr
    finally:
        _cleanup(holder)


def test_lock_released_when_holder_dies(instance_env):
    holder = None
    successor = None
    try:
        holder = _start_holder(instance_env)
        _wait_for_held(holder)
        holder.kill()
        holder.wait(timeout=20)

        successor = _start_holder(instance_env)
        _wait_for_held(successor)
    finally:
        try:
            _cleanup(successor)
        finally:
            _cleanup(holder)


def test_acquire_in_process(instance_env):
    name = instance_env["RFL_INSTANCE_MUTEX"]
    assert acquire(name) is not None

    second = subprocess.run(
        [sys.executable, "-c", ACQUIRE_SCRIPT],
        cwd=REPO_ROOT,
        env=instance_env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert second.returncode == 3, second.stderr


def test_main_takes_the_lock_before_starting():  # #3840
    """The helper tests above prove nothing if main.py stops calling it: the station's
    __main__ block must take the lock BEFORE asyncio.run(main())."""
    import ast

    tree = ast.parse((REPO_ROOT / "main.py").read_text(encoding="utf-8"))
    guard = next(
        node for node in tree.body
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test)
    )
    calls = [ast.unparse(n.func) for n in ast.walk(guard) if isinstance(n, ast.Call)]
    assert "ensure_single_instance" in calls and "asyncio.run" in calls
    assert calls.index("ensure_single_instance") < calls.index("asyncio.run")
