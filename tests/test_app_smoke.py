"""
tests/test_app_smoke.py
-----------------------
Subprocess smoke-test for MultiChannelWavMixer.py.

Launches the GUI app as a child process, waits 6 seconds, verifies it is
still alive (i.e. no import error or immediate crash), then terminates it.

Skipped on platforms where the GUI backend is unavailable (Linux CI).
The pytest job in CI only runs on macos-latest, so this will always execute
there while remaining a safe no-op elsewhere.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Root of the repository — one level above this tests/ dir.
_REPO_ROOT = Path(__file__).parent.parent
_APP_SCRIPT = _REPO_ROOT / "MultiChannelWavMixer.py"

# Seconds the app must stay alive to be considered healthy.
_ALIVE_SECS = 6


@pytest.mark.skipif(
    sys.platform not in ("darwin", "win32"),
    reason="GUI smoke test requires a platform with a native display (macOS / Windows)",
)
def test_app_starts_and_stays_alive() -> None:
    """Launch the app and confirm it does not exit within _ALIVE_SECS seconds."""
    proc = subprocess.Popen(
        [sys.executable, str(_APP_SCRIPT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(_REPO_ROOT),
        env={**os.environ},
    )

    time.sleep(_ALIVE_SECS)
    exit_code = proc.poll()

    if exit_code is None:
        # Still running — healthy.
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return

    # Process exited before we got a chance to check — collect output and fail.
    _, stderr = proc.communicate(timeout=5)
    error_text = stderr.decode(errors="replace").strip()
    pytest.fail(
        f"App exited after {_ALIVE_SECS}s with code {exit_code}.\nstderr:\n{error_text[:2000]}"
    )
