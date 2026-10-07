"""Process-lifetime single-instance lock for Radio Free Luna. #3840"""

import ctypes
import errno
import os
import sys
import tempfile

# Global\, not Local\: Local is per logon session, so a launch from another session
# (a scheduled task, a service) could otherwise run a second station. #3840
DEFAULT_NAME = r"Global\RadioFreeLuna-station"
ENV_NAME = "RFL_INSTANCE_MUTEX"
ALREADY_RUNNING_EXIT = 3
_held: object | None = None


def acquire(name: str | None = None) -> object | None:  #3840
    global _held
    name = name if name is not None else (os.environ.get(ENV_NAME) or DEFAULT_NAME)
    if sys.platform == "win32":
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR
        )
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, name)
        error = ctypes.get_last_error()
        if not handle:
            if error == 5:  # ACCESS_DENIED: it exists, created by a more privileged copy #3840
                return None
            raise OSError(error)
        if error == 183:
            kernel32.CloseHandle(handle)
            return None
        _held = handle
    else:
        import fcntl

        filename = "".join(c if c.isalnum() else "_" for c in name) + ".lock"
        handle = open(os.path.join(tempfile.gettempdir(), filename), "a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            if isinstance(exc, BlockingIOError) or exc.errno == errno.EWOULDBLOCK:
                return None
            raise
        _held = handle
    return _held


def ensure_single_instance(logger=None, name=None) -> None:  #3840
    if acquire(name) is None:
        resolved = name if name is not None else (
            os.environ.get(ENV_NAME) or DEFAULT_NAME
        )
        message = (
            "Radio Free Luna is already running (instance lock %s held); "
            "this copy exits without touching the port or the stream."
        )
        if logger is not None:
            logger.error(message, resolved)
        else:
            print(message % resolved, file=sys.stderr)
        sys.exit(ALREADY_RUNNING_EXIT)
