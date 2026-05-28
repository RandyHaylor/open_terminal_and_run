# open_terminal_and_run

Cross-platform, stdlib-only Python helper that opens a new terminal window/pane and runs a shell command inside it.

[![CI](https://github.com/RandyHaylor/open_terminal_and_run/actions/workflows/ci.yml/badge.svg)](https://github.com/RandyHaylor/open_terminal_and_run/actions/workflows/ci.yml)

## Why

Lots of scripts, hooks, and skills want to fire off a side terminal — a `tail -f`, a long build, an interactive REPL — without blocking the caller. Doing this reliably across tmux, macOS, Windows, and the half-dozen Linux desktop terminal emulators is annoying. This module hides that.

## Install

It's a single file with no runtime dependencies. Two options:

```bash
# Vendor it
curl -O https://raw.githubusercontent.com/RandyHaylor/open_terminal_and_run/main/open_terminal_and_run.py

# Or clone
git clone https://github.com/RandyHaylor/open_terminal_and_run.git
```

## Use as a library

```python
from open_terminal_and_run import open_terminal_and_run

result = open_terminal_and_run("tail -f /tmp/my.log")
if result.opened:
    print(f"opened via {result.mechanism}")
else:
    print(f"run this manually: {result.manual_command}")
```

## Use as a CLI

```bash
python3 open_terminal_and_run.py "tail -f /tmp/my.log"
python3 open_terminal_and_run.py --no-keep-open "echo hi; sleep 5"
python3 open_terminal_and_run.py --detect-only "tail -f /tmp/my.log"
```

Exit codes: `0` = opened (or detected), `1` = usage error, `2` = no mechanism, manual command printed.

## Detection order

1. tmux (if `$TMUX` is set)
2. macOS (`osascript` + `Terminal.app`)
3. Windows (`wt.exe`, falling back to `cmd.exe`)
4. Linux: gnome-terminal → konsole → xfce4-terminal → alacritty → xterm
5. Manual fallback (returns the command for the user to run by hand)

## Tests

```bash
pip install pytest
pytest -v
```

All detection branches are unit-tested with mocked `shutil.which` / `platform.system` / `sys.platform`. The CLI is tested via subprocess with `--detect-only`. CI runs on Ubuntu, macOS, and Windows across Python 3.10–3.13, plus a headless real-spawn smoke test using `xterm` under `xvfb`.

## Verified working — see the live screenshots

Every push to `main` runs each supported mechanism end-to-end in CI: a
real terminal window opens, a sentinel-writing command runs inside it,
and a screenshot is captured. The screenshots are uploaded to the
[v0.1.0 release](https://github.com/RandyHaylor/open_terminal_and_run/releases/tag/v0.1.0)
and overwritten on every successful build, so the release page always
shows current proof of life for every mechanism.

**End-to-end CI-verified each push:**
- tmux (Linux)
- xterm
- gnome-terminal
- konsole
- xfce4-terminal
- alacritty
- Windows Terminal (wt.exe)
- Windows cmd.exe

**Supported but untested in CI:**
- **macOS Terminal.app via osascript.** GitHub-hosted macOS runners cannot
  run this end-to-end: AppleEvent automation is TCC-gated with no UI to
  approve the prompt, `open -a Terminal file.command` needs a logged-in
  Aqua session that hosted runners don't have, and TCC.db pre-approval
  is impossible because SIP is enabled on the runner. Documented in
  [actions/runner-images #553](https://github.com/actions/runner-images/issues/553)
  and [#7531](https://github.com/actions/runner-images/issues/7531).

  The macOS code path uses the canonical AppleScript pattern that
  [Thonny](https://github.com/thonny/thonny/blob/master/thonny/terminal.py)
  and [skywind3000/terminal](https://github.com/skywind3000/terminal)
  have shipped for ~10 years: `osascript` with an inline
  `tell application "Terminal" / do script / activate` block that
  branches on whether Terminal is already running (cold-start case uses
  `in window 1` to avoid leaving an empty extra window). Backslash and
  double-quote escaping is order-sensitive — backslashes are escaped
  first. The CI matrix exercises this branch with mocked unit tests on
  `macos-latest`, but does not real-spawn it.

## License

MIT — see [LICENSE](LICENSE).
