"""Keep the Radio Free Luna FastAPI server alive on Windows (#6914).
The server runs from the project virtual environment and writes to its own log.
Health is checked through /health and confirmed with netstat when refused.
Two consecutive down results trigger a relaunch; unknown results never do.
A boot grace period and hourly storm guard prevent rapid restart loops.
Supervisor state is logged and written atomically to a JSON health file.
A PID lock prevents multiple supervisors, while status and --once aid operations.
No process is ever terminated by this supervisor.
"""

import argparse
import atexit
import json
import logging
import logging.handlers
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


INTERVAL = 30
BOOT_GRACE = 120
STORM_WINDOW = 3600
STORM_LIMIT = 3
HEARTBEAT_INTERVAL = 600
PROBE_TIMEOUT = 5

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
RUNTIME_DIR = ROOT / "data" / "runtime"
HEALTH_PATH = RUNTIME_DIR / "rfl_health.json"
LOCK_PATH = RUNTIME_DIR / "rfl_supervisor.lock"
SERVER_LOG_PATH = LOG_DIR / "rfl_server.out.log"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def configured_port():
    value = int(os.environ.get("PORT", "8080"))
    if not 1 <= value <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    return value


PORT = configured_port()


def _port_has_listener(port):
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0].upper() != "TCP":
            continue
        if fields[3].upper() != "LISTENING":
            continue

        host, separator, port_text = fields[1].rpartition(":")
        if (
            separator
            and host in {"0.0.0.0", "127.0.0.1"}
            and port_text.isdigit()
            and int(port_text) == port
        ):
            return True

    return False


def probe(port=PORT):
    url = f"http://127.0.0.1:{port}/health"

    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as response:
            if response.getcode() != 200:
                return "unknown"
            try:
                payload = json.load(response)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                return "unknown"
            return "up" if payload.get("status") == "healthy" else "unknown"
    except ConnectionRefusedError:
        listening = _port_has_listener(port)
        return "down" if listening is False else "unknown"
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError):
            listening = _port_has_listener(port)
            return "down" if listening is False else "unknown"
        return "unknown"
    except (
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return "unknown"


def launch_server():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # The server's own stdout; keep one previous copy instead of growing forever
    if SERVER_LOG_PATH.exists() and SERVER_LOG_PATH.stat().st_size > 20 * 1024 * 1024:
        os.replace(SERVER_LOG_PATH, SERVER_LOG_PATH.with_suffix(".log.1"))
    with SERVER_LOG_PATH.open("ab", buffering=0) as output:
        return subprocess.Popen(
            [str(VENV_PYTHON), "main.py"],
            cwd=str(ROOT),
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )


def _local_iso(timestamp):
    return datetime.fromtimestamp(timestamp).astimezone().isoformat()


def configure_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("rfl_supervisor")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        SUPERVISOR_LOG_PATH,
        maxBytes=1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


SUPERVISOR_LOG_PATH = LOG_DIR / "supervisor.log"


class Supervisor:
    def __init__(
        self,
        probe=probe,
        launch=launch_server,
        clock=time.time,
        port=PORT,
        health_path=HEALTH_PATH,
        logger=None,
    ):
        self.probe_function = probe
        self.launch_function = launch
        self.clock = clock
        self.port = port
        self.health_path = Path(health_path)
        self.logger = logger or logging.getLogger("rfl_supervisor")

        self.state = None
        self.down_streak = 0
        self.last_up_at = None
        self.last_launch_at = None
        self.last_launch_epoch = None
        self.relaunch_times = []
        self.server_process = None
        self.server_exit_logged = False
        self.last_heartbeat_at = None
        self.storm_logged = False

    def _set_state(self, state):
        if state != self.state:
            previous = self.state if self.state is not None else "initial"
            self.logger.info("state %s -> %s", previous, state)
            self.state = state

    def _check_server_process(self):
        if self.server_process is None:
            return

        returncode = self.server_process.poll()
        if returncode is not None and not self.server_exit_logged:
            self.logger.info("server exited returncode=%s", returncode)
            self.server_exit_logged = True

    def _server_pid(self):
        if self.server_process is None:
            return None
        if self.server_process.poll() is not None:
            return None
        return self.server_process.pid

    def _prune_relaunches(self, now):
        cutoff = now - STORM_WINDOW
        self.relaunch_times = [
            launched_at
            for launched_at in self.relaunch_times
            if launched_at > cutoff
        ]

    def _in_boot_grace(self, now):
        return (
            self.last_launch_epoch is not None
            and now - self.last_launch_epoch < BOOT_GRACE
        )

    def _write_health(self, now):
        payload = {
            "state": self.state,
            "checked_at": _local_iso(now),
            "last_up_at": self.last_up_at,
            "relaunches_last_hour": len(self.relaunch_times),
            "last_launch_at": self.last_launch_at,
            "supervisor_pid": os.getpid(),
            "server_pid": self._server_pid(),
            "port": self.port,
        }

        self.health_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.health_path.with_name(self.health_path.name + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as output:
            json.dump(payload, output, separators=(",", ":"))
            output.write("\n")
        os.replace(temporary_path, self.health_path)

    def _heartbeat(self, now, result):
        if self.last_heartbeat_at is None:
            self.last_heartbeat_at = now
            return

        if now - self.last_heartbeat_at >= HEARTBEAT_INTERVAL:
            self.logger.info("heartbeat state=%s probe=%s", self.state, result)
            self.last_heartbeat_at = now

    def tick(self, now):
        self._check_server_process()
        self._prune_relaunches(now)

        try:
            result = self.probe_function()
        except Exception:
            self.logger.exception("probe failed")
            result = "unknown"

        if result not in {"up", "down", "unknown"}:
            self.logger.error("invalid probe result %r", result)
            result = "unknown"

        if result == "up":
            self.last_up_at = _local_iso(now)

        storm_active = len(self.relaunch_times) >= STORM_LIMIT
        if not storm_active:
            self.storm_logged = False

        if storm_active:
            self.down_streak = 0
            if not self.storm_logged:
                self.logger.error("storm")
                self.storm_logged = True
            next_state = "storm"
        elif self._in_boot_grace(now) or (result != "up" and self._server_pid() is not None):
            # Our own child is still alive (a slow boot, not a death): wait, never stack a
            # second server on top of it
            self.down_streak = 0
            next_state = "up" if result == "up" else "launching"
        elif result == "down":
            self.down_streak += 1
            next_state = "down"

            if self.down_streak >= 2:
                self.down_streak = 0
                try:
                    process = self.launch_function()
                except Exception:
                    self.logger.exception("relaunch failed")
                else:
                    self.server_process = process
                    self.server_exit_logged = False
                    self.last_launch_epoch = now
                    self.last_launch_at = _local_iso(now)
                    self.relaunch_times.append(now)
                    self.logger.info(
                        "relaunch server_pid=%s relaunches_last_hour=%s",
                        process.pid,
                        len(self.relaunch_times),
                    )

                    if len(self.relaunch_times) >= STORM_LIMIT:
                        self.logger.error("storm")
                        self.storm_logged = True
                        next_state = "storm"
                    else:
                        next_state = "launching"
        else:
            self.down_streak = 0
            next_state = result

        self._set_state(next_state)
        self._heartbeat(now, result)

        try:
            self._write_health(now)
        except OSError:
            self.logger.exception("health file write failed")

        return self.state


def pid_is_alive(pid):
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return result.returncode == 0 and re.search(
        rf"(?<!\d){re.escape(str(pid))}(?!\d)", result.stdout
    ) is not None


def acquire_lock():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()

    while True:
        try:
            descriptor = os.open(
                LOCK_PATH,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            try:
                existing_text = LOCK_PATH.read_text(encoding="ascii").strip()
                existing_pid = int(existing_text)
            except (OSError, ValueError):
                existing_pid = None

            if existing_pid is not None and pid_is_alive(existing_pid):
                print(f"RFL supervisor is already running with PID {existing_pid}")
                return False

            try:
                LOCK_PATH.unlink()
            except FileNotFoundError:
                pass
            continue

        try:
            os.write(descriptor, f"{current_pid}\n".encode("ascii"))
        finally:
            os.close(descriptor)
        return True


def release_lock():
    try:
        owner = int(LOCK_PATH.read_text(encoding="ascii").strip())
    except (FileNotFoundError, OSError, ValueError):
        return

    if owner == os.getpid():
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def print_status():
    try:
        print(HEALTH_PATH.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        print("no health file")
    except OSError as exc:
        print(f"unable to read health file: {exc}")

    print(f"probe: {probe()}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Radio Free Luna server supervisor")
    parser.add_argument("command", nargs="?", choices=("run", "status"), default="run")
    parser.add_argument(
        "--once",
        action="store_true",
        help="perform one supervisor iteration and exit",
    )
    args = parser.parse_args(argv)

    if args.command == "status":
        print_status()
        return 0

    if not acquire_lock():
        return 0

    atexit.register(release_lock)
    logger = configure_logging()
    supervisor = Supervisor(logger=logger)

    try:
        while True:
            supervisor.tick(supervisor.clock())
            if args.once:
                break
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        logger.info("supervisor interrupted")
    finally:
        release_lock()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
