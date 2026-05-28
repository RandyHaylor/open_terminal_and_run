"""Unit tests for detection logic — mock env + uname + which()."""
import platform
import pytest

import open_terminal_window_and_run as otr


def test_tmux_env_is_ignored_because_pane_is_not_a_window(clean_env):
    """tmux splits a pane — not a new top-level window. Even if $TMUX is
    set, detection must fall through to a real window-opening mechanism."""
    clean_env.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
    clean_env.setattr(otr.platform, "system", lambda: "Linux")
    clean_env.setattr(otr.sys, "platform", "linux")
    clean_env.setattr(otr.shutil, "which",
                     lambda name: f"/usr/bin/{name}" if name == "xterm" else None)
    result = otr.detect_mechanism("ls")
    assert result.mechanism == "xterm"  # NOT tmux


def test_macos_branch(clean_env):
    clean_env.setattr(otr.platform, "system", lambda: "Darwin")
    clean_env.setattr(otr.sys, "platform", "darwin")
    result = otr.detect_mechanism('say "hi"')
    assert result.mechanism == "macOS Terminal.app"
    assert result.argv[0].endswith("osascript")
    assert '\\"hi\\"' in result.argv[2]
    assert "in window 1" in result.argv[2]
    assert "activate" in result.argv[2]


def test_macos_branch_escapes_backslash_before_quote(clean_env):
    clean_env.setattr(otr.platform, "system", lambda: "Darwin")
    clean_env.setattr(otr.sys, "platform", "darwin")
    result = otr.detect_mechanism(r'echo "C:\path"')
    assert "\\\\path" in result.argv[2]


def test_windows_terminal_forces_new_window(clean_env):
    """wt.exe alone with `new-tab` would attach to the existing wt window
    if one is running. We must pass `-w new` to force a new top-level
    window."""
    clean_env.setattr(otr.sys, "platform", "win32")
    clean_env.setattr(otr.platform, "system", lambda: "Windows")
    clean_env.setattr(otr.shutil, "which",
                     lambda name: r"C:\wt.exe" if name in ("wt.exe", "wt") else None)
    result = otr.detect_mechanism("dir")
    assert result.mechanism == "Windows Terminal"
    assert result.argv[0] == r"C:\wt.exe"
    # `-w new` must appear before `new-tab`
    assert "-w" in result.argv
    assert "new" in result.argv
    w_index = result.argv.index("-w")
    assert result.argv[w_index + 1] == "new"


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
    clean_env.setattr(otr.shutil, "which",
                     lambda name: f"/usr/bin/{name}" if name == "konsole" else None)
    result = otr.detect_mechanism("ls")
    assert result.mechanism == "konsole"


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


def test_macos_picked_when_no_terminals_on_path(clean_env):
    """macOS branch must fire regardless of $TMUX status — only platform
    matters now that tmux is not a detection target."""
    clean_env.setenv("TMUX", "x")  # should be ignored
    clean_env.setattr(otr.platform, "system", lambda: "Darwin")
    clean_env.setattr(otr.sys, "platform", "darwin")
    result = otr.detect_mechanism("ls")
    assert result.mechanism == "macOS Terminal.app"


def test_open_terminal_window_and_run_passes_untethered_true_by_default(monkeypatch):
    """Verify the default spawn uses start_new_session=True (POSIX detach)."""
    monkeypatch.setattr(otr.sys, "platform", "linux")
    monkeypatch.setattr(otr.platform, "system", lambda: "Linux")
    monkeypatch.setattr(otr.shutil, "which",
                       lambda name: f"/usr/bin/{name}" if name == "xterm" else None)
    captured_kwargs = {}

    class FakePopen:
        def __init__(self, argv, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(otr.subprocess, "Popen", FakePopen)
    result = otr.open_terminal_window_and_run("ls")
    assert result.opened is True
    assert captured_kwargs.get("start_new_session") is True


def test_open_terminal_window_and_run_tethered_skips_new_session(monkeypatch):
    """untethered=False must NOT pass start_new_session=True."""
    monkeypatch.setattr(otr.sys, "platform", "linux")
    monkeypatch.setattr(otr.platform, "system", lambda: "Linux")
    monkeypatch.setattr(otr.shutil, "which",
                       lambda name: f"/usr/bin/{name}" if name == "xterm" else None)
    captured_kwargs = {}

    class FakePopen:
        def __init__(self, argv, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(otr.subprocess, "Popen", FakePopen)
    result = otr.open_terminal_window_and_run("ls", untethered=False)
    assert result.opened is True
    assert "start_new_session" not in captured_kwargs


def test_backwards_compat_alias_open_terminal_and_run_exists():
    """Old import name should still work."""
    assert otr.open_terminal_and_run is otr.open_terminal_window_and_run
