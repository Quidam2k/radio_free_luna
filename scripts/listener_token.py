"""Manage invited listeners for the station (#6915/#6918).

  python scripts/listener_token.py add <name>     # prints the token ONCE
  python scripts/listener_token.py revoke <name>
  python scripts/listener_token.py list

A listener opens http://<station>:8080/?t=<token> (or /stream.mp3?t=<token>) once; the
server sets a cookie after that. Loopback needs no token.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.listener_auth import add_listener, load_listeners, revoke_listener  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["add", "revoke", "list"])
    ap.add_argument("name", nargs="?")
    args = ap.parse_args(argv)
    if args.action == "list":
        for name in sorted(load_listeners()):
            print(name)
        return 0
    if not args.name:
        ap.error("name required")
    if args.action == "add":
        print(f"{args.name}: {add_listener(args.name)}")
        print("Shown once. Listener URL: http://<station>:8080/stream.mp3?t=<token>")
        return 0
    if not revoke_listener(args.name):
        print(f"no listener named {args.name}")
        return 1
    print(f"revoked {args.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
