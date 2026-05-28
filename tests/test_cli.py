"""Subprocess tests of the CLI interface — uses --detect-only so nothing spawns."""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "open_terminal_window_and_run.py"


def _run_cli(*args, env_overrides=None):
    env = os.environ.copy()
    env.pop("TMUX", None)
    env.pop("TMUX_PANE", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


def test_cli_help():
    r = _run_cli("--help")
    assert r.returncode == 0
    assert "shell command" in r.stdout.lower()


def test_cli_detect_only_does_not_spawn():
    r = _run_cli("--detect-only", "echo hi")
    assert r.returncode in (0, 2)
    assert ("Mechanism:" in r.stdout) or ("manually" in r.stdout)


def test_cli_tmux_env_does_not_trigger_pane_split():
    """Even with $TMUX set, the CLI must not pick tmux — only window mechanisms."""
    r = _run_cli("--detect-only", "echo hi",
                 env_overrides={"TMUX": "/tmp/fake,1,0"})
    # 0 = mechanism detected; 2 = manual fallback (bare runner with no GUI terminals).
    # Both are valid; what matters is that tmux is never the mechanism.
    assert r.returncode in (0, 2)
    assert "tmux" not in r.stdout.lower()


def test_cli_usage_error_when_missing_cmd():
    r = _run_cli()
    assert r.returncode != 0


def test_cli_tethered_flag_is_accepted():
    r = _run_cli("--detect-only", "--tethered", "echo hi")
    # 0 = mechanism found, 2 = manual fallback. Either proves the flag parsed
    # cleanly (parser would exit 2 with usage error if --tethered was unknown,
    # but the *message* would differ; here we check argparse didn't error).
    assert r.returncode in (0, 2)
    assert "unrecognized arguments" not in r.stderr.lower()


def test_public_api_surface():
    import importlib.util
    spec = importlib.util.spec_from_file_location("otr_smoke", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["otr_smoke"] = mod
    spec.loader.exec_module(mod)
    assert callable(mod.open_terminal_window_and_run)
    assert callable(mod.open_terminal_and_run)  # backwards-compat alias
    assert callable(mod.detect_mechanism)
    assert hasattr(mod, "DetectionResult")
    assert hasattr(mod, "LINUX_TERMINALS")
