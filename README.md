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

**Best-effort (not CI-verifiable, works in real use):**
- macOS Terminal.app via osascript — GitHub-hosted macOS runners block
  AppleEvent automation via TCC permission gating with no UI to approve
  the prompt. Verified locally on real macOS; CI job runs with
  `continue-on-error: true` so the build doesn't fail.

## License

MIT — see [LICENSE](LICENSE).
