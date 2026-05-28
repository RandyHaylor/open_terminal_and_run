"""Tiny cross-platform helper invoked inside the spawned terminal.

Usage:
    python sentinel_writer_helper.py <sentinel_path> [hold_seconds]

Writes "READY" to <sentinel_path>, prints a visible banner so the
spawned window has identifiable content for screenshots, then sleeps
for <hold_seconds> (default 12) to keep the window on screen while
the harness captures a screenshot.
"""
import sys
import time
from pathlib import Path


BANNER_LINES = [
    "================================================",
    "  open_terminal_window_and_run REAL SPAWN TEST WINDOW  ",
    "================================================",
]


def main():
    target_sentinel_path = Path(sys.argv[1])
    hold_seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    for line in BANNER_LINES:
        print(line, flush=True)
    print(f"sentinel = {target_sentinel_path}", flush=True)
    print(f"hold_seconds = {hold_seconds}", flush=True)

    target_sentinel_path.write_text("READY")
    print("[helper] sentinel written; holding window open for screenshot...",
          flush=True)
    time.sleep(hold_seconds)
    print("[helper] hold elapsed; window will close.", flush=True)


if __name__ == "__main__":
    main()
