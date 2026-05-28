"""Real-spawn verification harness with optional screenshot capture.

Spawns a terminal via open_terminal_window_and_run, runs a helper inside it that
writes a sentinel file + prints a banner + sleeps. Verifies the sentinel
appears, then (optionally) captures a screenshot of the still-visible
window using platform-appropriate tools.

Exit codes:
    0 success (sentinel observed and, if requested, screenshot saved)
    2 spawn returned opened=False
    3 mechanism mismatch (silent fallback)
    4 timeout waiting for sentinel
    5 screenshot capture failed
"""
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import open_terminal_window_and_run as otr  # noqa: E402


HELPER_SCRIPT_PATH = Path(__file__).resolve().parent / "sentinel_writer_helper.py"


def build_in_terminal_command(sentinel_path: Path, hold_seconds: int) -> str:
    """Return the shell command that will run INSIDE the spawned terminal.

    Invokes the python helper with the sentinel path and hold duration.
    On Windows we route through a .bat wrapper to avoid cmd.exe's bizarre
    /c quote rules when nested under `start "" cmd /c "..."`.
    """
    python_executable = sys.executable
    if sys.platform == "win32":
        wrapper_bat_path = sentinel_path.with_suffix(".bat")
        wrapper_bat_path.write_text(
            "@echo off\r\n"
            f'"{python_executable}" "{HELPER_SCRIPT_PATH}" '
            f'"{sentinel_path}" {hold_seconds}\r\n',
            encoding="ascii",
        )
        return str(wrapper_bat_path)
    return (f"{shlex.quote(python_executable)} "
            f"{shlex.quote(str(HELPER_SCRIPT_PATH))} "
            f"{shlex.quote(str(sentinel_path))} "
            f"{hold_seconds}")


def hide_wt_from_which() -> None:
    """Force Windows branch to fall through to cmd.exe by hiding wt."""
    original_which = shutil.which

    def which_without_wt(name, *a, **kw):
        if name in ("wt", "wt.exe"):
            return None
        return original_which(name, *a, **kw)

    otr.shutil.which = which_without_wt


def capture_screenshot_to_path(output_path: Path, mechanism: str) -> bool:
    """Capture a screenshot of the spawned terminal using platform tools.
    Returns True on success."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if mechanism == "tmux":
        # tmux is a pane, not a window — capture its text and render
        # to PNG via Pillow.
        return capture_tmux_pane_as_png(output_path)

    if sys.platform == "darwin":
        # macOS: screencapture grabs the full display
        result = subprocess.run(
            ["screencapture", "-x", str(output_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[harness] screencapture failed: {result.stderr}",
                  file=sys.stderr)
            return False
        return output_path.exists()

    if sys.platform == "win32":
        # PowerShell desktop capture
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            "$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
            "$bmp = New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
            "$g = [System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
            f'$bmp.Save("{output_path}");'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[harness] powershell screenshot failed: {result.stderr}",
                  file=sys.stderr)
            return False
        return output_path.exists()

    # Linux (under xvfb): use ImageMagick `import`
    if shutil.which("import"):
        result = subprocess.run(
            ["import", "-window", "root", str(output_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[harness] import failed: {result.stderr}",
                  file=sys.stderr)
            return False
        return output_path.exists()
    print("[harness] no screenshot tool available (need ImageMagick)",
          file=sys.stderr)
    return False


def capture_tmux_pane_as_png(output_path: Path) -> bool:
    """Run `tmux capture-pane -p` to grab the pane's text content and
    render it to a PNG using Pillow."""
    capture = subprocess.run(
        ["tmux", "capture-pane", "-t", "otr_session", "-p"],
        capture_output=True, text=True,
    )
    if capture.returncode != 0:
        print(f"[harness] tmux capture-pane failed: {capture.stderr}",
              file=sys.stderr)
        return False
    pane_text = capture.stdout or "(empty pane)"
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[harness] Pillow not installed; falling back to .txt",
              file=sys.stderr)
        output_path.with_suffix(".txt").write_text(pane_text)
        return False

    lines = pane_text.splitlines() or [""]
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    line_height = 18
    image_height = max(200, line_height * len(lines) + 20)
    image_width = 1000
    image = Image.new("RGB", (image_width, image_height), color=(20, 20, 30))
    draw = ImageDraw.Draw(image)
    draw.text((10, 5), "tmux capture-pane (otr_session)",
              fill=(200, 200, 200), font=font)
    for line_index, line_text in enumerate(lines):
        draw.text((10, 25 + line_index * line_height),
                  line_text, fill=(220, 220, 220), font=font)
    image.save(output_path)
    return output_path.exists()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-mechanism", required=True)
    parser.add_argument("--sentinel", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--hide-wt", action="store_true")
    parser.add_argument("--hold-seconds", type=int, default=12,
                        help="How long the helper sleeps inside the new "
                             "window — leaves it visible for screenshots.")
    parser.add_argument("--screenshot-output-path", default=None,
                        help="If given, capture a screenshot to this path "
                             "after sentinel is observed.")
    parser.add_argument("--screenshot-delay-seconds", type=float, default=3.0,
                        help="Pause between sentinel-detected and screenshot, "
                             "to give the terminal time to fully render.")
    args = parser.parse_args()

    sentinel_path = Path(args.sentinel)
    if sentinel_path.exists():
        sentinel_path.unlink()

    if args.hide_wt:
        hide_wt_from_which()

    in_terminal_command = build_in_terminal_command(sentinel_path, args.hold_seconds)
    print(f"[harness] in_terminal_command = {in_terminal_command!r}")

    # keep_open=True so the spawned window stays alive long enough for the
    # screenshot; the in-terminal command's own sleep is what actually
    # determines visibility duration.
    spawn_result = otr.open_terminal_window_and_run(in_terminal_command, keep_open=True)
    print(f"[harness] mechanism = {spawn_result.mechanism!r}")
    print(f"[harness] opened    = {spawn_result.opened}")
    print(f"[harness] argv      = {spawn_result.argv!r}")
    print(f"[harness] detail    = {spawn_result.detail!r}")

    if not spawn_result.opened:
        print(f"[harness] FAIL: opened=False ({spawn_result.detail})",
              file=sys.stderr)
        return 2

    if spawn_result.mechanism != args.expected_mechanism:
        print(f"[harness] FAIL: expected mechanism {args.expected_mechanism!r}, "
              f"got {spawn_result.mechanism!r}", file=sys.stderr)
        return 3

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if sentinel_path.exists():
            print(f"[harness] sentinel observed: {sentinel_path.read_text().strip()!r}")
            break
        time.sleep(0.5)
    else:
        print(f"[harness] FAIL: timed out after {args.timeout}s waiting for "
              f"{sentinel_path}", file=sys.stderr)
        return 4

    if args.screenshot_output_path:
        print(f"[harness] waiting {args.screenshot_delay_seconds}s for window "
              "to render before screenshot...")
        time.sleep(args.screenshot_delay_seconds)
        ok = capture_screenshot_to_path(
            Path(args.screenshot_output_path), spawn_result.mechanism,
        )
        if not ok:
            print("[harness] FAIL: screenshot capture failed", file=sys.stderr)
            return 5
        print(f"[harness] screenshot saved: {args.screenshot_output_path}")

    print("[harness] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
