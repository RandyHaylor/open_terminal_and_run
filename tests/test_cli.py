"""Subprocess tests of the CLI interface — uses --detect-only so nothing spawns."""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "open_terminal_and_run.py"


def _run_cli(*args, env_overrides=None):
    env = os.environ.copy()
    # Strip TMUX so CI doesn't accidentally hit the tmux branch
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
    # Even if a real terminal exists on the host, --detect-only must not spawn.
    r = _run_cli("--detect-only", "echo hi")
    assert r.returncode in (0, 2)
    # Either a mechanism was detected, or manual fallback was printed.
    assert ("Mechanism:" in r.stdout) or ("manually" in r.stdout)


def test_cli_tmux_branch_via_env():
    # Force tmux branch by setting TMUX
    r = _run_cli("--detect-only", "echo hi", env_overrides={"TMUX": "/tmp/fake,1,0"})
    assert r.returncode == 0
    assert "tmux" in r.stdout


def test_cli_usage_error_when_missing_cmd():
    r = _run_cli()
    assert r.returncode != 0


def test_public_api_surface():
    import importlib.util
    spec = importlib.util.spec_from_file_location("otr_smoke", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["otr_smoke"] = mod  # dataclasses needs to resolve the module for string annotations
    spec.loader.exec_module(mod)
    assert callable(mod.open_terminal_and_run)
    assert callable(mod.detect_mechanism)
    assert hasattr(mod, "DetectionResult")
    assert hasattr(mod, "LINUX_TERMINALS")
