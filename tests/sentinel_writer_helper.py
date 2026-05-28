"""Tiny cross-platform helper invoked inside the spawned terminal.

Writes the literal text "READY" to the path passed as the first argument.
Using a python helper instead of `echo > file` sidesteps per-shell
redirection quoting differences (cmd.exe vs bash vs zsh vs fish).
"""
import sys
from pathlib import Path

if __name__ == "__main__":
    target_path = Path(sys.argv[1])
    target_path.write_text("READY")
