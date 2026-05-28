# open_terminal_and_run

Cross-platform, stdlib-only Python helper that opens a new terminal window/pane and runs a shell command inside it. Non-blocking. Predictable failure mode. Designed for AI agents and automation scripts that want to surface a live process to the user without taking over the agent's own stdout.

[![CI](https://github.com/RandyHaylor/open_terminal_and_run/actions/workflows/ci.yml/badge.svg)](https://github.com/RandyHaylor/open_terminal_and_run/actions/workflows/ci.yml)

---

## Designed for AI agents — what you get

When an AI agent calls `open_terminal_and_run(cmd)`:

- **Non-blocking.** Returns immediately. The agent keeps running. The command runs in a separate window/pane the user can watch.
- **Never raises.** Always returns a `DetectionResult`. The agent inspects fields to decide next action.
- **Honest failure.** If nothing on the system can spawn a window (headless server, locked-down CI, no terminal emulator installed), the result carries the exact shell command the agent should hand back to the user — so the agent can fall back to a "please run this yourself" instruction without guessing.
- **Stdlib-only.** No dependencies for the agent to manage. Vendor the single file or `pip install`.

The intended pattern is: agent decides "this would be better shown to the user in its own window" (a long build, a `tail -f`, a dev server, an interactive REPL) → calls this module → either it opens, or the agent communicates the manual fallback. Agent never blocks waiting for the spawned process.

---

## Quick start (the copy-paste form)

### Vendor the single file

```bash
curl -O https://raw.githubusercontent.com/RandyHaylor/open_terminal_and_run/main/open_terminal_and_run.py
```

### Or pip install

```bash
pip install git+https://github.com/RandyHaylor/open_terminal_and_run.git
```

### The minimal AI-agent integration

```python
from open_terminal_and_run import open_terminal_and_run

result = open_terminal_and_run("tail -f /var/log/app.log")

if result.opened:
    # Window is up. Agent moves on.
    agent_say(f"Opened a side terminal ({result.mechanism}) tailing the log.")
else:
    # Couldn't spawn. Agent tells the user what to run.
    agent_say(
        "I couldn't open a terminal automatically. "
        f"Please run this in a terminal yourself:\n\n    {result.manual_command}"
    )
```

That's the contract. Two branches. No exceptions.

---

## The `DetectionResult` contract — what AI agents read

Every call returns a `DetectionResult` dataclass:

| Field            | Type              | Meaning |
|------------------|-------------------|---------|
| `opened`         | `bool`            | `True` if the spawn succeeded. `False` otherwise — **always check this first.** |
| `mechanism`      | `str` or `None`   | Which path was used: `"tmux"`, `"macOS Terminal.app"`, `"Windows Terminal"`, `"cmd.exe"`, `"gnome-terminal"`, `"konsole"`, `"xfce4-terminal"`, `"alacritty"`, `"xterm"`, or `None` if no mechanism was found. |
| `argv`           | `list[str]` or `None` | The exact argv that was (or would have been) passed to `subprocess.Popen`. Useful for logging/debug. `None` only when no mechanism was detected. |
| `manual_command` | `str`             | The original shell command the agent passed in. When `opened=False`, this is what the agent should surface to the user as the manual-run instruction. |
| `detail`         | `str`             | Free-form note ("$TMUX is set; would split a tmux pane", "spawn failed: <errno>", etc.). For logs/telemetry. |

### Reading the contract as a decision tree

```
result = open_terminal_and_run(cmd)

if result.opened:
    # SUCCESS. Window is live.
    # Tell the user where to look. result.mechanism names it.

elif result.mechanism is not None:
    # Detection found something, but the actual Popen failed.
    # Rare. result.detail says why. Treat as a manual-fallback case.

else:
    # No mechanism on this machine.
    # Hand result.manual_command back to the user verbatim.
```

---

## Integration patterns

### Pattern 1 — Python AI agent that wants a side process visible

```python
from open_terminal_and_run import open_terminal_and_run

def show_to_user_in_side_terminal(shell_command: str, what_for: str) -> str:
    """Try to surface `shell_command` in a new terminal window. Returns a
    message the agent should speak to the user."""
    result = open_terminal_and_run(shell_command)
    if result.opened:
        return f"Opened a side terminal ({result.mechanism}) running: {what_for}"
    return (
        f"I couldn't open a side terminal for {what_for!r}. "
        f"Run this yourself when ready:\n\n    {result.manual_command}\n"
    )
```

### Pattern 2 — Detect-only (plan without acting)

When the agent wants to know *whether* a terminal can be opened before deciding what to do (e.g. choosing between "tail the log in a side window" vs. "stream the log inline"):

```python
from open_terminal_and_run import detect_mechanism

plan = detect_mechanism("tail -f app.log")
if plan.mechanism is None:
    # Headless or locked-down env. Don't try to spawn — stream inline.
    stream_log_inline()
else:
    # Spawn is viable. Do it.
    open_terminal_and_run("tail -f app.log")
```

`detect_mechanism` is pure — it never spawns anything. Same return shape; `opened` is always `False`.

### Pattern 3 — Shell-out from a non-Python agent

Other-language agents (Node, Go, Rust, etc.) can invoke the CLI and parse exit codes:

```bash
python3 open_terminal_and_run.py "tail -f /tmp/app.log"
case $? in
  0) echo "opened" ;;
  2) echo "no terminal mechanism — give the command to the user" ;;
  *) echo "usage error" ;;
esac
```

Exit codes:
- `0` — opened successfully (or detection succeeded when `--detect-only`)
- `1` — usage error (bad CLI args)
- `2` — no mechanism detected; the command was printed to stdout for the user

### Pattern 4 — Inside a Claude Code skill / agent SDK tool

```python
# Inside a skill that runs a long task and wants to show it to the user
from open_terminal_and_run import open_terminal_and_run

def run_long_task_in_side_window(task_command: str) -> dict:
    result = open_terminal_and_run(task_command, keep_open=True)
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

### Pattern 5 — Background tail for an MCP server / autonomous loop

```python
from open_terminal_and_run import open_terminal_and_run

# Agent has just started a long-running process. Surface its log.
open_terminal_and_run(f"tail -f {logfile_path}", keep_open=True)
# Agent immediately continues — no blocking, no awaiting.
```

---

## Handling the manual fallback (critical for agents)

`open_terminal_and_run` will return `opened=False` with `mechanism=None` when:

- Running on a Linux server with no desktop and no `$TMUX` set
- Running in a Docker container with no terminal emulator installed
- Running in a restricted CI environment
- Running on Windows Server Core (no `wt.exe`, no graphical `cmd` host)
- Running on macOS without Terminal.app reachable (very unusual)

In every one of those cases the agent gets `result.manual_command` containing the verbatim command the user can copy-paste into their own terminal. **An agent should never report the operation as failed in this case** — it should report it as "deferred to user" and pass along the command.

```python
result = open_terminal_and_run(cmd)
if result.opened:
    return f"running in {result.mechanism}"
return f"please run in your own terminal: {result.manual_command}"
```

---

## `keep_open` — should the window stay after the command exits?

```python
open_terminal_and_run("./build.sh", keep_open=True)   # default: stay open
open_terminal_and_run("./quick-task.sh", keep_open=False)  # close on completion
```

- `keep_open=True` (default) — POSIX terminals append `; exec bash` so the user can see final output and errors after the command exits. Best default for interactive use.
- `keep_open=False` — window closes as soon as the command finishes. Good for one-shot probes.

Note: the keep-open behavior is honored on Linux terminal emulators and is implicit on macOS Terminal.app (AppleScript `do script` leaves the window open). Windows wt.exe and cmd.exe currently always keep the window open.

---

## Detection order

The module tries each branch and falls through to the next on failure:

1. **tmux** — if `$TMUX` is set, split-pane in the current session. Works across any OS where tmux is running. Most reliable.
2. **macOS** — `osascript` + `Terminal.app` (canonical Thonny / skywind3000 pattern, see below).
3. **Windows** — prefers `wt.exe` (Windows Terminal), falls back to `cmd.exe`.
4. **Linux desktop** — first available of: `gnome-terminal` → `konsole` → `xfce4-terminal` → `alacritty` → `xterm`.
5. **Manual fallback** — `DetectionResult(opened=False, mechanism=None, manual_command=cmd)`.

---

## When NOT to use this module

This module is for **side-channel display to the user**. It is not the right tool when:

- You need the command's stdout/stderr back in the agent. Use `subprocess.run` instead.
- You need to wait for the command to finish. This module is fire-and-forget.
- You need pipes, env-var capture, structured exit handling. Use `subprocess` directly.
- You're inside a CI job that has no display. Use `subprocess.run` and capture/log output.

This module gives the user a window. If the agent needs the data, the agent should run the command itself.

---

## Verified working — see the live screenshots

Every push to `main` runs each supported mechanism end-to-end in CI: a real terminal window opens, a sentinel-writing command runs inside it, and a screenshot is captured. The screenshots are uploaded to the [v0.1.0 release](https://github.com/RandyHaylor/open_terminal_and_run/releases/tag/v0.1.0) and overwritten on every successful build — the release page always shows current proof-of-life for every mechanism.

**End-to-end CI-verified each push:**

- tmux (Linux)
- xterm, gnome-terminal, konsole, xfce4-terminal, alacritty (Linux)
- Windows Terminal (`wt.exe`)
- Windows cmd.exe

**Supported but untested in CI:**

- **macOS Terminal.app via osascript.** GitHub-hosted macOS runners cannot run this end-to-end: AppleEvent automation is TCC-gated with no UI to approve the prompt, `open -a Terminal file.command` needs a logged-in Aqua session that hosted runners don't provide, and TCC.db pre-approval is impossible because SIP is enabled on the runner. See [actions/runner-images #553](https://github.com/actions/runner-images/issues/553) and [#7531](https://github.com/actions/runner-images/issues/7531).

  The macOS code path uses the canonical AppleScript pattern that [Thonny](https://github.com/thonny/thonny/blob/master/thonny/terminal.py) and [skywind3000/terminal](https://github.com/skywind3000/terminal) have shipped for ~10 years: `osascript` with an inline `tell application "Terminal" / do script / activate` block that branches on whether Terminal is already running (cold-start case uses `in window 1` to avoid leaving an empty extra window). Backslash-then-quote escape order. The CI matrix exercises this branch with mocked unit tests on `macos-latest` but does not real-spawn it.

---

## CLI

For non-Python agents and shell scripts:

```bash
python3 open_terminal_and_run.py "tail -f /tmp/my.log"
python3 open_terminal_and_run.py --no-keep-open "echo hi; sleep 5"
python3 open_terminal_and_run.py --detect-only "tail -f /tmp/my.log"
```

`--detect-only` plans without spawning — same return shape, useful for agents that want to inspect what *would* happen before committing.

---

## Tests

```bash
pip install pytest
pytest -v
```

20 unit tests covering every detection branch with mocked `shutil.which`, `platform.system`, and `sys.platform`. CLI is tested via subprocess with `--detect-only`. CI runs Ubuntu/macOS/Windows × Python 3.10–3.13, plus the per-mechanism real-spawn matrix (see above).

---

## License

MIT — see [LICENSE](LICENSE).
