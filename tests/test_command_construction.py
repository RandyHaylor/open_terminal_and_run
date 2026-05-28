"""Verify argv shapes per terminal — gnome-terminal gets `--`, konsole gets `-e`, etc."""
import pytest
import open_terminal_and_run as otr


@pytest.fixture(autouse=True)
def linux_env(monkeypatch):
    for key in ("TMUX", "TMUX_PANE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(otr.sys, "platform", "linux")
    monkeypatch.setattr(otr.platform, "system", lambda: "Linux")


def _only(name, monkeypatch):
    monkeypatch.setattr(otr.shutil, "which",
                       lambda n: f"/usr/bin/{n}" if n == name else None)


def test_gnome_terminal_uses_dash_dash(monkeypatch):
    _only("gnome-terminal", monkeypatch)
    r = otr.detect_mechanism("ls", keep_open=True)
    assert r.argv[:2] == ["gnome-terminal", "--"]
    assert "exec bash" in r.argv[-1]


def test_konsole_uses_dash_e(monkeypatch):
    _only("konsole", monkeypatch)
    r = otr.detect_mechanism("ls", keep_open=True)
    assert r.argv[0] == "konsole"
    assert r.argv[1] == "-e"


def test_xterm_uses_dash_e_with_quoted_string(monkeypatch):
    _only("xterm", monkeypatch)
    r = otr.detect_mechanism("ls", keep_open=True)
    assert r.argv[0] == "xterm"
    assert r.argv[1] == "-e"
    assert r.argv[2].startswith("bash -c '")


def test_keep_open_false_omits_exec_bash(monkeypatch):
    _only("gnome-terminal", monkeypatch)
    r = otr.detect_mechanism("ls", keep_open=False)
    assert "exec bash" not in r.argv[-1]


def test_keep_open_true_appends_exec_bash(monkeypatch):
    _only("konsole", monkeypatch)
    r = otr.detect_mechanism("ls", keep_open=True)
    assert r.argv[-1].endswith("; exec bash")


def test_cmd_placeholder_substituted(monkeypatch):
    _only("alacritty", monkeypatch)
    r = otr.detect_mechanism("tail -f /tmp/x.log", keep_open=False)
    joined = " ".join(r.argv)
    assert "tail -f /tmp/x.log" in joined
    assert "{cmd}" not in joined
