"""Unit tests for detection logic — mock env + uname + which()."""
import platform
import pytest

import open_terminal_and_run as otr


def test_tmux_wins_when_env_set(clean_env):
    clean_env.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
    result = otr.detect_mechanism("echo hi")
    assert result.mechanism == "tmux"
    assert result.argv == ["tmux", "split-window", "-h", "echo hi"]
    assert result.opened is False  # detect-only never opens


def test_macos_branch(clean_env):
    clean_env.setattr(otr.platform, "system", lambda: "Darwin")
    clean_env.setattr(otr.sys, "platform", "darwin")
    result = otr.detect_mechanism('say "hi"')
    assert result.mechanism == "macOS Terminal.app"
    assert result.argv[0].endswith("osascript")
    # Quotes in cmd must be escaped inside the AppleScript
    assert '\\"hi\\"' in result.argv[2]
    # Cold-start branch should use `in window 1` to avoid extra window
    assert "in window 1" in result.argv[2]
    # Should activate Terminal to bring window to foreground
    assert "activate" in result.argv[2]


def test_macos_branch_escapes_backslash_before_quote(clean_env):
    """Escape order matters: backslash first, then quote. Otherwise the
    backslash added when escaping a quote would itself get escaped."""
    clean_env.setattr(otr.platform, "system", lambda: "Darwin")
    clean_env.setattr(otr.sys, "platform", "darwin")
    result = otr.detect_mechanism(r'echo "C:\path"')
    # Expect the backslash to appear as \\\\ in the AppleScript literal
    # (one literal backslash escaped for AppleScript string syntax)
    assert "\\\\path" in result.argv[2]


def test_windows_prefers_wt(clean_env):
    clean_env.setattr(otr.sys, "platform", "win32")
    clean_env.setattr(otr.platform, "system", lambda: "Windows")
    clean_env.setattr(otr.shutil, "which",
                     lambda name: r"C:\wt.exe" if name in ("wt.exe", "wt") else None)
    result = otr.detect_mechanism("dir")
    assert result.mechanism == "Windows Terminal"
    assert result.argv[0] == r"C:\wt.exe"
    assert "new-tab" in result.argv


def test_windows_falls_back_to_cmd(clean_env):
    clean_env.setattr(otr.sys, "platform", "win32")
    clean_env.setattr(otr.platform, "system", lambda: "Windows")
    clean_env.setattr(otr.shutil, "which",
                     lambda name: r"C:\Windows\System32\cmd.exe" if name in ("cmd.exe", "cmd") else None)
    result = otr.detect_mechanism("dir")
    assert result.mechanism == "cmd.exe"
    assert "/c" in result.argv
    assert "start" in result.argv


def test_linux_picks_first_available(clean_env):
    clean_env.setattr(otr.sys, "platform", "linux")
    clean_env.setattr(otr.platform, "system", lambda: "Linux")
    # Only konsole exists
    clean_env.setattr(otr.shutil, "which",
                     lambda name: f"/usr/bin/{name}" if name == "konsole" else None)
    result = otr.detect_mechanism("ls")
    assert result.mechanism == "konsole"
    assert result.argv[0] == "konsole"


def test_linux_priority_gnome_over_xterm(clean_env):
    clean_env.setattr(otr.sys, "platform", "linux")
    clean_env.setattr(otr.platform, "system", lambda: "Linux")
    clean_env.setattr(otr.shutil, "which",
                     lambda name: f"/usr/bin/{name}" if name in ("gnome-terminal", "xterm") else None)
    result = otr.detect_mechanism("ls")
    assert result.mechanism == "gnome-terminal"


def test_no_mechanism_returns_manual(no_terminals):
    no_terminals.setattr(otr.sys, "platform", "linux")
    no_terminals.setattr(otr.platform, "system", lambda: "Linux")
    result = otr.detect_mechanism("ls")
    assert result.mechanism is None
    assert result.argv is None
    assert result.manual_command == "ls"
    assert result.opened is False


def test_tmux_beats_macos(clean_env):
    clean_env.setenv("TMUX", "x")
    clean_env.setattr(otr.platform, "system", lambda: "Darwin")
    result = otr.detect_mechanism("ls")
    assert result.mechanism == "tmux"
