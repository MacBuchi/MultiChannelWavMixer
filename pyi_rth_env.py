"""
PyInstaller runtime hook — executed before any user code.
Adds common macOS binary paths (Homebrew, MacPorts, /usr/local) to PATH
so that pydub can locate ffmpeg/ffprobe inside the .app bundle.
"""

import os

_extra_paths = [
    "/opt/homebrew/bin",  # Apple Silicon Homebrew
    "/usr/local/bin",  # Intel Homebrew / manual installs
    "/opt/local/bin",  # MacPorts
    "/usr/bin",
    "/bin",
]

# Prepend missing paths (preserve anything already set, e.g. by launchd)
current = os.environ.get("PATH", "").split(":")
additions = [p for p in _extra_paths if p not in current and os.path.isdir(p)]
if additions:
    os.environ["PATH"] = ":".join(additions + current)
