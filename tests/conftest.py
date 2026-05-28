"""Env isolation fixtures so tests don't pick up the host's real terminal env."""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def clean_env(monkeypatch):
    """Strip TMUX and force a known platform-neutral env."""
    for key in ("TMUX", "TMUX_PANE"):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


@pytest.fixture
def no_terminals(monkeypatch):
    """Force shutil.which to find nothing."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    for key in ("TMUX", "TMUX_PANE"):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch
