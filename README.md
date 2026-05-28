# open_terminal_window_and_run

Cross-platform, stdlib-only Python helper that opens a new terminal **window** (a top-level OS window — not a pane, not a tab) and runs a shell command inside it. Non-blocking. Predictable failure mode. Designed for AI agents and automation scripts.

[![CI](https://github.com/RandyHaylor/open_terminal_window_and_run/actions/workflows/ci.yml/badge.svg)](https://github.com/RandyHaylor/open_terminal_window_and_run/actions/workflows/ci.yml)

---

## Scope — what "open a terminal window" means here

This module always and only opens a **new top-level OS window**. It does not split panes (tmux), does not add tabs to existing terminal sessions, and does not run the command inline. If a brand-new draggable/closable window is not what you need, this is not the right module.

Specifically:
- tmux is **not** a detection target. Even when `$TMUX` is set, this module ignores it and reaches for a real window-opening mechanism.
- Windows Terminal (`wt.exe`) is invoked with `-w new` so each spawn opens a new window (not a tab in an existing wt window).
- macOS uses `osascript` against Terminal.app's `do script` (with `in window 1` on cold start) — always a new window.
- Linux desktop terminals (`gnome-terminal`, `konsole`, etc.) each open a new window per invocation.

---

## Designed for AI agents — the contract

When an AI agent calls `open_terminal_window_and_run(cmd)`:

- **Non-blocking.** Returns immediately. The agent keeps running. The command runs in a separate window the user can watch.
- **Never raises.** Always returns a `DetectionResult`. The agent inspects fields to decide next action.
- **Honest failure.** If nothing on the system can spawn a window, the result carries the exact shell command the agent should hand to the user as a manual-run instruction.
- **Untethered by default.** The spawned window keeps running even if the calling process exits. Configurable.
- **Stdlib-only.** No dependencies. Vendor the single file or `pip install`.

---

## Quick start

### Vendor the single file

```bash
curl -O https://raw.githubusercontent.com/RandyHaylor/open_terminal_window_and_run/main/open_terminal_window_and_run.py
```

### Or pip install

```bash
pip install git+https://github.com/RandyHaylor/open_terminal_window_and_run.git
```

### Minimal AI-agent integration

```python
from open_terminal_window_and_run import open_terminal_window_and_run

result = open_terminal_window_and_run("tail -f /var/log/app.log")

if result.opened:
    agent_say(f"Opened a side terminal ({result.mechanism}) tailing the log.")
else:
    agent_say(
        "I couldn't open a terminal automatically. "
        f"Please run this in a terminal yourself:\n\n    {result.manual_command}"
    )
```

---

## The `untethered` parameter

```python
open_terminal_window_and_run("./long_build.sh", untethered=True)   # default
open_terminal_window_and_run("./short_task.sh", untethered=False)
```

- **`untethered=True`** (default) — the new window's lifecycle is independent of the caller. The window keeps running even if the calling process exits. This is what AI agents almost always want: fire the window, agent terminates or moves on, user keeps watching the window.
- **`untethered=False`** — the new window is coupled to the calling process. On POSIX Linux this is enforced by *not* creating a new session, so SIGHUP from the parent's controlling terminal will propagate and close the new window when the caller dies.

**Platform honesty:** the tethered/untethered distinction is only meaningfully enforceable on POSIX Linux. On macOS, the spawner (`osascript`) exits immediately and hands off to Terminal.app which has its own application session — the window is always untethered there. On Windows, `cmd /c start ""` and `wt.exe` both detach at the OS level — always untethered. The parameter is accepted on all platforms but does nothing on macOS/Windows.

---

## The `DetectionResult` contract

| Field            | Type              | Meaning |
|------------------|-------------------|---------|
| `opened`         | `bool`            | `True` if the spawn succeeded. **Always check this first.** |
| `mechanism`      | `str` or `None`   | `"macOS Terminal.app"`, `"Windows Terminal"`, `"cmd.exe"`, `"gnome-terminal"`, `"konsole"`, `"xfce4-terminal"`, `"alacritty"`, `"xterm"`, or `None` if no mechanism was found. |
| `argv`           | `list[str]` or `None` | The exact argv passed (or that would have been passed) to `subprocess.Popen`. `None` only when no mechanism was detected. |
| `manual_command` | `str`             | The original command. When `opened=False`, hand this to the user. |
| `detail`         | `str`             | Free-form note for logs/telemetry. |

### Reading it as a decision tree

```python
result = open_terminal_window_and_run(cmd)

if result.opened:
    # SUCCESS. Window is live. result.mechanism names it.

elif result.mechanism is not None:
    # Detection found something, but Popen failed (rare).
    # result.detail says why. Treat as manual-fallback.

else:
    # No mechanism on this machine.
    # Surface result.manual_command to the user verbatim.
```

---

## Integration patterns

### Pattern 1 — Python AI agent surfacing a side process

```python
from open_terminal_window_and_run import open_terminal_window_and_run

def show_to_user_in_side_terminal(shell_command: str, what_for: str) -> str:
    result = open_terminal_window_and_run(shell_command)
    if result.opened:
        return f"Opened a side terminal ({result.mechanism}) running: {what_for}"
    return (
        f"I couldn't open a side terminal for {what_for!r}. "
        f"Run this yourself:\n\n    {result.manual_command}\n"
    )
```

### Pattern 2 — Detect-only (plan without acting)

```python
from open_terminal_window_and_run import detect_mechanism

plan = detect_mechanism("tail -f app.log")
if plan.mechanism is None:
    stream_log_inline()  # headless env; don't try to spawn
else:
    open_terminal_window_and_run("tail -f app.log")
```

`detect_mechanism` is pure — it never spawns.

### Pattern 3 — Non-Python agent shelling out to the CLI

```bash
python3 open_terminal_window_and_run.py "tail -f /tmp/app.log"
case $? in
  0) echo "opened" ;;
  2) echo "no mechanism — surface command to user" ;;
  *) echo "usage error" ;;
esac
```

Exit codes: `0` opened (or detected), `1` usage error, `2` no mechanism (command printed to stdout).

### Pattern 4 — Inside a Claude Code skill / Agent SDK tool

```python
from open_terminal_window_and_run import open_terminal_window_and_run

def run_long_task_in_side_window(task_command: str) -> dict:
    result = open_terminal_window_and_run(task_command, keep_open=True)
    return {
        "spawned": result.opened,
        "mechanism": result.mechanism,
        "user_message": (
            f"Watch progress in the {result.mechanism} window."
            if result.opened else
            f"Please run this yourself: `{result.manual_command}`"
        ),
    }
```

### Pattern 5 — Tethered spawn (window dies with the agent)

```python
# Window terminates when the agent process exits — useful when the
# window is purely diagnostic for the agent's own run.
open_terminal_window_and_run("htop", untethered=False)
```

---

## The manual fallback (critical for agents)

`open_terminal_window_and_run` returns `opened=False` with `mechanism=None` when:

- Linux server with no desktop installed
- Docker container with no terminal emulator
- Restricted CI environment
- Windows Server Core (no `wt.exe`, no graphical console host)
- macOS without Terminal.app reachable

The agent gets `result.manual_command` containing the verbatim command. **Report this as "deferred to user," not "failed."**

---

## `keep_open` — should the window stay after the command exits?

```python
open_terminal_window_and_run("./build.sh", keep_open=True)   # default
open_terminal_window_and_run("./quick.sh", keep_open=False)
```

- `keep_open=True` (default): POSIX terminals append `; exec bash` so the user can read final output. Best for interactive use.
- `keep_open=False`: window closes when the command finishes. Good for one-shot probes.

Note: keep-open is honored on Linux. macOS Terminal.app's `do script` always leaves the window open. Windows `wt.exe` and `cmd.exe` currently always keep the window open.

---

## Detection order

Each branch falls through to the next on failure. tmux is intentionally not in the list (panes aren't windows).

1. **macOS** — `osascript` + `Terminal.app` (canonical Thonny / skywind3000 pattern)
2. **Windows** — `wt.exe -w new` (forces new window), falls back to `cmd /c start ""`
3. **Linux desktop** — first available of: `gnome-terminal` → `konsole` → `xfce4-terminal` → `alacritty` → `xterm`
4. **Manual fallback** — `DetectionResult(opened=False, mechanism=None, manual_command=cmd)`

---

## When NOT to use this module

- Need the command's stdout/stderr back in your code → use `subprocess.run`.
- Need to wait for the command to finish → this module is fire-and-forget.
- Inside a CI job with no display → use `subprocess.run` and capture/log output.

This module gives the user a window. If the agent needs the data, the agent should run the command itself.

---

## Verified working — live screenshots in the release

Every push to `main` runs each supported mechanism end-to-end in CI: a real window opens, a sentinel-writing command runs inside it, a screenshot is captured. Screenshots are uploaded to the [v0.2.0 release](https://github.com/RandyHaylor/open_terminal_window_and_run/releases/tag/v0.2.0) and overwritten on every successful build.

**End-to-end CI-verified each push:**

- xterm, gnome-terminal, konsole, xfce4-terminal, alacritty (Linux)
- Windows Terminal (`wt.exe` with `-w new`)
- Windows cmd.exe

**Supported but untested in CI:**

- **macOS Terminal.app via osascript.** GitHub-hosted macOS runners cannot real-spawn this: AppleEvent automation is TCC-gated with no UI to approve the prompt, `open -a Terminal file.command` needs a logged-in Aqua session that hosted runners don't provide, and TCC.db pre-approval is impossible because SIP is enabled on the runner. See [actions/runner-images #553](https://github.com/actions/runner-images/issues/553) and [#7531](https://github.com/actions/runner-images/issues/7531).

  The macOS code path uses the canonical AppleScript pattern that [Thonny](https://github.com/thonny/thonny/blob/master/thonny/terminal.py) and [skywind3000/terminal](https://github.com/skywind3000/terminal) have shipped for ~10 years. The CI exercises this branch with mocked unit tests on `macos-latest` but does not real-spawn it.

---

## CLI

```bash
python3 open_terminal_window_and_run.py "tail -f /tmp/my.log"
python3 open_terminal_window_and_run.py --no-keep-open "echo hi; sleep 5"
python3 open_terminal_window_and_run.py --tethered "htop"
python3 open_terminal_window_and_run.py --detect-only "tail -f /tmp/my.log"
```

---

## Tests

```bash
pip install pytest
pytest -v
```

24 unit tests covering every detection branch with mocked `shutil.which`, `platform.system`, and `sys.platform`. CLI is tested via subprocess with `--detect-only`. CI runs Ubuntu/macOS/Windows × Python 3.10–3.13, plus the per-mechanism real-spawn matrix.

---

## License

MIT — see [LICENSE](LICENSE).
