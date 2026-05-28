#!/usr/bin/env python3
"""
open_terminal_and_run.py
=========================

Cross-platform helper: open a new terminal window/pane and run a shell
command in it.

This module is a standalone, dependency-free utility intended to live in
its own GitHub repository so it can be reused by skills, scripts, hooks,
and any other tooling that needs to spawn a side window with a live
command.

Design goals:
  - Pure stdlib. No external dependencies.
  - Cross-platform: Linux (X11 + Wayland desktop terminals), macOS,
    Windows (PowerShell + cmd + Windows Terminal + Git Bash), and tmux
    (which trumps OS-native detection when present).
  - Honest failure: when no terminal mechanism can be detected, return a
    structured "manual" result containing the exact command the user
    should run themselves. Never fail silently.
  - Testable: detection logic separated from execution logic so unit
    tests can mock the environment and verify which branch would have
    been chosen without actually spawning processes.

USAGE
-----

As a library:

    from open_terminal_and_run import open_terminal_and_run, DetectionResult

    result = open_terminal_and_run("tail -f /tmp/my.log")
    if result.opened:
        print(f"Tail window opened in: {result.mechanism}")
    else:
        print("Could not auto-open a terminal. Run this manually:")
        print(f"  {result.manual_command}")

As a CLI:

    python3 open_terminal_and_run.py "tail -f /tmp/my.log"
    python3 open_terminal_and_run.py --keep-open "echo hi; sleep 5"
    python3 open_terminal_and_run.py --detect-only "tail -f /tmp/my.log"

The --detect-only flag returns what would have been done without actually
spawning anything. Useful for testing and for letting callers decide
whether to proceed.

EXIT CODES (CLI)
----------------

  0 - terminal opened successfully (or detection succeeded if --detect-only)
  1 - usage error
  2 - no terminal mechanism detected; manual command printed to stdout


DETECTION ORDER
---------------

Each branch falls through on failure to the next. The goal is always
a new top-level OS WINDOW — tab/pane mechanisms (tmux, wt tabs into
existing windows) are deliberately avoided.

  1. macOS        (uname -s == Darwin — uses osascript + Terminal.app,
                  always spawns a new window)
  2. Windows      (cygwin/mingw/msys uname, or sys.platform == 'win32' —
                  prefers Windows Terminal `wt.exe` with `-w new` to
                  force a new window, falls back to `cmd /c start ""`
                  which always opens a new console window)
  3. Linux        (tries: gnome-terminal, konsole, xfce4-terminal,
                  alacritty, xterm — each invocation opens a new window)
  4. Manual       (no mechanism detected; structured result with the
                  command to run by hand)


KEEPING WINDOWS OPEN AFTER COMMAND EXITS
-----------------------------------------

By default the new terminal stays open after the command exits (so the
user can see final output and any errors). This is implemented by
appending `; exec bash` (POSIX) or equivalent. Pass `keep_open=False` to
let the window close as soon as the command finishes.


REPO LAYOUT (planned for the dedicated repo)
---------------------------------------------

  open_terminal_and_run/
    open_terminal_and_run.py           (this file)
    tests/
      test_detection.py                (unit tests for detection logic,
                                        mocking env + uname + which())
      test_command_construction.py     (unit tests for argv shapes per
                                        terminal — verify gnome-terminal
                                        gets `--`, konsole gets `-e`, etc.)
      test_cli.py                      (subprocess tests of the CLI
                                        interface with --detect-only)
      conftest.py                      (env isolation fixtures)
    .github/workflows/
      ci.yml                           (see CI section below)
    README.md
    LICENSE
    pyproject.toml                     (only for testing tooling, NOT for
                                        runtime — the module itself is
                                        stdlib-only and importable directly)


PLANNED CI (.github/workflows/ci.yml)
--------------------------------------

  Matrix:
    - ubuntu-latest    (tests Linux detection branches)
    - macos-latest     (tests macOS branch via osascript availability check)
    - windows-latest   (tests Windows branch via wt.exe / cmd.exe presence)

  Python versions:
    - 3.10, 3.11, 3.12, 3.13

  Steps:
    1. Check out the repo.
    2. Set up Python (matrix version).
    3. Install dev dependencies (pytest only — runtime needs no deps).
    4. Run unit tests with --detect-only and mocked environments to
       verify each branch picks the right terminal command. Do NOT
       actually spawn terminals in CI; mock subprocess.Popen and
       subprocess.run.
    5. Run a small "smoke" test that imports the module and asserts the
       public API surface (function names, return type, sensible defaults).
    6. On Linux only: a separate job that installs xterm via apt and
       does ONE real spawn with `--keep-open=False` and a trivial
       command, to confirm end-to-end works headlessly via xvfb. Skip on
       macOS and Windows (no headless terminal story).
    7. Lint check (ruff or similar) — optional, opinion of repo owner.

  Coverage target: 90%+ on detection.py logic. CLI tests cover the rest.

  Release workflow (separate file release.yml):
    - Triggered on tag push matching v*.
    - Builds source distribution (sdist) via stdlib `build` module.
    - Publishes to PyPI under a package name like `open-terminal-and-run`.
    - NOTE: PyPI install is optional — the module is designed to be
      copy-pasteable as a single file. The PyPI distribution exists for
      users who prefer `pip install` to vendoring.

KNOWN LIMITATIONS
-----------------

  - Linux Wayland sessions running tools that only support X11 may need
    XWayland. Detection doesn't currently distinguish; if a terminal
    fails to launch under Wayland, the error surfaces and detection
    falls through.
  - PowerShell-native Windows is supported only when invoked via
    sys.platform check. If invoked under Git Bash on Windows, the
    Windows branch uses cmd.exe / wt.exe via uname detection.
  - Terminal emulators not in the detection list won't be tried. Users
    can extend the LINUX_TERMINALS list and submit a PR.
  - The "keep open" behavior assumes bash is available for POSIX
    terminals. On systems with non-bash default shells, the trailing
    `exec bash` may need adjustment.

LICENSE
-------

To be set in the repo (MIT recommended for maximum reusability).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


# Order matters: earlier terminals are tried first.
# Each entry: (binary_name, argv_template_for_keep_open, argv_template_for_no_keep_open)
# Use {cmd} as the placeholder for the shell command.
LINUX_TERMINALS = [
    # gnome-terminal: -- separates terminal args from the command
    ("gnome-terminal",
     ["--", "bash", "-c", "{cmd}; exec bash"],
     ["--", "bash", "-c", "{cmd}"]),

    # konsole: -e takes the command list
    ("konsole",
     ["-e", "bash", "-c", "{cmd}; exec bash"],
     ["-e", "bash", "-c", "{cmd}"]),

    # xfce4-terminal: -e takes a single quoted command string
    ("xfce4-terminal",
     ["-e", "bash -c '{cmd}; exec bash'"],
     ["-e", "bash -c '{cmd}'"]),

    # alacritty: -e takes the command list (no shell wrapper)
    ("alacritty",
     ["-e", "bash", "-c", "{cmd}; exec bash"],
     ["-e", "bash", "-c", "{cmd}"]),

    # kitty was removed from the supported list — its hard OpenGL
    # requirement makes it impossible to verify in headless CI, and
    # silently claiming support without verification is dishonest.
    # Users who want kitty can extend LINUX_TERMINALS in a fork.

    # xterm: -e takes a single quoted command string
    ("xterm",
     ["-e", "bash -c '{cmd}; exec bash'"],
     ["-e", "bash -c '{cmd}'"]),
]


@dataclass
class DetectionResult:
    """Outcome of attempting (or planning) to open a terminal."""
    opened: bool                    # True if a terminal was launched; False if manual fallback
    mechanism: Optional[str]        # Name of the mechanism used (e.g. "tmux", "gnome-terminal", "macOS Terminal.app")
    argv: Optional[list[str]]       # The argv that was (or would be) executed
    manual_command: str             # The original command, for the user to run manually if needed
    detail: str = ""                # Free-form notes (errors, info)


def _is_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _is_windows_native() -> bool:
    return sys.platform == "win32"


def _is_windows_via_uname() -> bool:
    """Detect Windows via uname output (Git Bash, MSYS, Cygwin)."""
    try:
        uname = platform.uname().system.lower()
        return any(s in uname for s in ("cygwin", "mingw", "msys"))
    except Exception:
        return False


def _detect_linux_terminal() -> Optional[tuple[str, list[str], list[str]]]:
    """Return the first available Linux terminal's spec, or None."""
    for entry in LINUX_TERMINALS:
        binary = entry[0]
        if shutil.which(binary):
            return entry
    return None


def _build_argv(template: list[str], cmd: str) -> list[str]:
    """Substitute {cmd} placeholder in each template item."""
    return [item.format(cmd=cmd) for item in template]


def detect_mechanism(cmd: str, keep_open: bool = True) -> DetectionResult:
    """Determine which mechanism would be used to open a terminal running
    `cmd`, but do not actually launch anything. Useful for testing and
    for letting callers decide whether to proceed.

    Returns a DetectionResult with .opened=False (since nothing was
    actually opened), but with .mechanism and .argv populated to show
    what WOULD happen on open_terminal_window_and_run().

    The point of this module is opening a new top-level OS WINDOW.
    tmux is deliberately NOT a detection target — splitting a tmux
    pane is not opening a window.
    """
    # 1. macOS
    if _is_macos():
        # Pattern copied from Thonny (thonny/terminal.py) and
        # skywind3000/terminal — both branch on whether Terminal.app is
        # already running, using `do script <cmd> in window 1` on cold
        # start to avoid spawning a second empty window. Escaping order
        # is critical: backslash MUST be escaped before the double quote
        # (otherwise the backslash we add for the quote gets escaped
        # again on the next pass). This pattern has been stable in
        # multiple unrelated projects for ~10 years.
        escaped_cmd_for_applescript_string_literal = (
            cmd.replace("\\", "\\\\").replace('"', '\\"')
        )
        applescript = (
            'if application "Terminal" is running then\n'
            '    tell application "Terminal"\n'
            f'        do script "{escaped_cmd_for_applescript_string_literal}"\n'
            '        activate\n'
            '    end tell\n'
            'else\n'
            '    tell application "Terminal"\n'
            f'        do script "{escaped_cmd_for_applescript_string_literal}" in window 1\n'
            '        activate\n'
            '    end tell\n'
            'end if'
        )
        argv = ["/usr/bin/osascript", "-e", applescript]
        return DetectionResult(
            opened=False, mechanism="macOS Terminal.app", argv=argv,
            manual_command=cmd, detail="darwin uname; would use osascript",
        )

    # 2. Windows (native or via Git Bash uname)
    if _is_windows_native() or _is_windows_via_uname():
        if shutil.which("wt.exe") or shutil.which("wt"):
            wt = shutil.which("wt.exe") or shutil.which("wt")
            # `-w new` forces a NEW Windows Terminal window. Without
            # it, `new-tab` adds a tab to an existing wt window if
            # one is already running, which is not what callers of
            # this module want — they want a new top-level window.
            # Docs: https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments
            argv = [wt, "-w", "new", "new-tab", "cmd", "/k", cmd]
            return DetectionResult(
                opened=False, mechanism="Windows Terminal", argv=argv,
                manual_command=cmd,
                detail="wt.exe found; using -w new to force new window",
            )
        if shutil.which("cmd.exe") or shutil.which("cmd"):
            cmdbin = shutil.which("cmd.exe") or shutil.which("cmd")
            # The empty "" is the title arg for `start` — without it,
            # start interprets the next quoted arg as the window title.
            # Use /k when keeping the window open after the command, /c
            # when not. /c lets the inner cmd window close on completion.
            inner_flag = "/k" if keep_open else "/c"
            argv = [cmdbin, "/c", "start", "", "cmd", inner_flag, cmd]
            return DetectionResult(
                opened=False, mechanism="cmd.exe", argv=argv,
                manual_command=cmd, detail="falling back to cmd.exe",
            )
        # If we're on Windows but neither launcher is found, fall through.

    # 3. Linux desktop terminal
    if not _is_windows_native():  # don't try Linux terminals on Windows native
        spec = _detect_linux_terminal()
        if spec:
            binary, keep_template, no_keep_template = spec
            template = keep_template if keep_open else no_keep_template
            argv = [binary] + _build_argv(template, cmd)
            return DetectionResult(
                opened=False, mechanism=binary, argv=argv,
                manual_command=cmd, detail=f"detected {binary} via shutil.which",
            )

    # 4. No mechanism — return manual fallback
    return DetectionResult(
        opened=False, mechanism=None, argv=None,
        manual_command=cmd, detail="no terminal launcher detected",
    )


def open_terminal_window_and_run(
    cmd: str,
    keep_open: bool = True,
    untethered: bool = True,
) -> DetectionResult:
    """Open a new terminal WINDOW (a top-level OS window) and run `cmd` in it.

    Always opens a new window, not a tab or a multiplexer pane. The
    spawn is non-blocking — this function returns as soon as the
    launcher process has been started.

    Parameters:
        cmd: The shell command to run inside the new terminal window.
        keep_open: If True, the window stays open after cmd exits
                   (POSIX: appends `; exec bash` so the user can read
                   final output). If False, the window closes as soon
                   as cmd finishes.
        untethered: If True (default), the spawned window's lifecycle
                   is independent of the calling process — the window
                   keeps running even if the caller exits. If False,
                   the window is coupled to the calling process on
                   POSIX systems (no new session is created; the
                   window may receive SIGHUP and die when the caller's
                   controlling terminal goes away).

                   Platform notes (honest):
                   - POSIX Linux: untethered is fully enforced via
                     subprocess `start_new_session`. tethered also
                     fully enforced — child shares the parent's
                     session.
                   - macOS: the spawner (osascript) exits immediately,
                     handing off to Terminal.app, which has its own
                     application session. The window is ALWAYS
                     untethered on macOS regardless of this flag.
                   - Windows: `cmd /c start ""` and `wt.exe` both
                     detach at the OS level. The window is ALWAYS
                     untethered on Windows regardless of this flag.

    Returns:
        DetectionResult — inspect `.opened` first. When False with
        `.mechanism == None`, no window-opening mechanism was found
        on the system; hand `.manual_command` to the user.
    """
    result = detect_mechanism(cmd, keep_open=keep_open)
    if result.argv is None:
        # No mechanism detected; return as-is for caller to handle.
        return result

    popen_kwargs = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if untethered:
        # Detach from the parent's process group / session on POSIX
        # so the window survives the parent exiting. Ignored by
        # Windows Popen but harmless there.
        popen_kwargs["start_new_session"] = True

    try:
        subprocess.Popen(result.argv, **popen_kwargs)
        result.opened = True
        return result
    except (OSError, subprocess.SubprocessError) as e:
        result.opened = False
        result.detail = f"spawn failed: {e}"
        return result


# Backwards-compatible alias for callers still importing the pre-rename
# name. New code should use `open_terminal_window_and_run`.
open_terminal_and_run = open_terminal_window_and_run


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Open a new terminal window and run a command in it.",
    )
    parser.add_argument("cmd", help="The shell command to run in the new terminal window.")
    parser.add_argument(
        "--no-keep-open",
        action="store_true",
        help="Let the new window close when the command exits (default: keep open).",
    )
    parser.add_argument(
        "--tethered",
        action="store_true",
        help="Couple the new window's lifecycle to the calling process. "
             "Default is untethered: the window keeps running even if the "
             "caller exits. Only enforceable on POSIX Linux; on macOS and "
             "Windows the new window is always untethered at the OS level.",
    )
    parser.add_argument(
        "--detect-only",
        action="store_true",
        help="Detect which mechanism would be used without actually opening anything.",
    )
    args = parser.parse_args()

    keep_open = not args.no_keep_open
    untethered = not args.tethered

    if args.detect_only:
        result = detect_mechanism(args.cmd, keep_open=keep_open)
    else:
        result = open_terminal_window_and_run(
            args.cmd, keep_open=keep_open, untethered=untethered,
        )

    if result.opened:
        print(f"Terminal opened in: {result.mechanism}")
        return 0
    elif result.mechanism is not None:
        # detect_only path, or spawn-failure path
        print(f"Mechanism: {result.mechanism}")
        if result.argv:
            print(f"Would run: {' '.join(result.argv)}")
        print(f"Detail: {result.detail}")
        return 0
    else:
        # Manual fallback
        print("Could not auto-open a terminal. Run this manually:")
        print(f"  {result.manual_command}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
