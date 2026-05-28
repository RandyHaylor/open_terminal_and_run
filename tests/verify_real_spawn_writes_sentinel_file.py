"""Real-spawn verification harness.

Spawns a terminal via open_terminal_and_run with a command that writes a
sentinel file inside the new window. Polls for the sentinel and exits 0
only if the file appears within the timeout. Also asserts that the
mechanism the module chose matches what the caller expected — catches
silent fallback to a different branch.

Usage:
    python tests/verify_real_spawn_writes_sentinel_file.py \
        --expected-mechanism xterm \
        --sentinel /tmp/sentinel_xterm.txt

Optional flags:
    --hide-wt        Make shutil.which return None for wt/wt.exe so the
                     Windows branch falls back to cmd.exe.
    --timeout N      Seconds to wait for the sentinel. Default 30.

Exit codes:
    0  sentinel observed; mechanism matched expected
    2  spawn returned opened=False
    3  mechanism mismatch (silent fallback)
    4  timeout waiting for sentinel
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import open_terminal_and_run as otr  # noqa: E402


def build_sentinel_writer_command(sentinel_path: Path) -> str:
    """Return a shell command that invokes the python sentinel-writer helper.

    Using a python helper instead of `echo > path` sidesteps per-shell
    redirection quoting issues (cmd.exe consumes `>` in the outer shell
    before `start` ever sees it, for example).
    """
    helper = Path(__file__).resolve().parent / "sentinel_writer_helper.py"
    python_executable = sys.executable
    if sys.platform == "win32":
        # Quote paths because temp/tool dirs on Windows can contain spaces.
        return f'"{python_executable}" "{helper}" "{sentinel_path}"'
    return (f"{shlex.quote(python_executable)} "
            f"{shlex.quote(str(helper))} "
            f"{shlex.quote(str(sentinel_path))}")


def hide_wt_from_which() -> None:
    """Monkey-patch shutil.which inside otr so it can't find wt/wt.exe.
    Forces the Windows branch to fall through to cmd.exe."""
    original_which = shutil.which

    def which_without_wt(name: str, *args, **kwargs):
        if name in ("wt", "wt.exe"):
            return None
        return original_which(name, *args, **kwargs)

    otr.shutil.which = which_without_wt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-mechanism", required=True,
                        help="Mechanism name detect_mechanism should return.")
    parser.add_argument("--sentinel", required=True,
                        help="Absolute path the spawned command will create.")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Seconds to wait for sentinel. Default 30.")
    parser.add_argument("--hide-wt", action="store_true",
                        help="Hide wt/wt.exe to force the cmd.exe branch on Windows.")
    args = parser.parse_args()

    sentinel_path = Path(args.sentinel)
    if sentinel_path.exists():
        sentinel_path.unlink()

    if args.hide_wt:
        hide_wt_from_which()

    command_to_run_in_new_window = build_sentinel_writer_command(sentinel_path)
    print(f"[harness] command_to_run_in_new_window = {command_to_run_in_new_window!r}")

    spawn_result = otr.open_terminal_and_run(command_to_run_in_new_window, keep_open=False)
    print(f"[harness] mechanism = {spawn_result.mechanism!r}")
    print(f"[harness] opened    = {spawn_result.opened}")
    print(f"[harness] argv      = {spawn_result.argv!r}")
    print(f"[harness] detail    = {spawn_result.detail!r}")

    if not spawn_result.opened:
        print(f"[harness] FAIL: spawn returned opened=False ({spawn_result.detail})",
              file=sys.stderr)
        return 2

    if spawn_result.mechanism != args.expected_mechanism:
        print(f"[harness] FAIL: expected mechanism {args.expected_mechanism!r}, "
              f"got {spawn_result.mechanism!r}", file=sys.stderr)
        return 3

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if sentinel_path.exists():
            try:
                contents = sentinel_path.read_text().strip()
            except OSError:
                contents = "<unreadable>"
            print(f"[harness] PASS: sentinel observed, contents={contents!r}")
            return 0
        time.sleep(0.5)

    print(f"[harness] FAIL: timed out after {args.timeout}s waiting for {sentinel_path}",
          file=sys.stderr)
    return 4


if __name__ == "__main__":
    sys.exit(main())
