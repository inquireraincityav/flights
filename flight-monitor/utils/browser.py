"""Browser launch utilities for Playwright providers."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional

from config import HEADLESS

logger = logging.getLogger("flight_monitor")

_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]


def _find_chromium_executable() -> Optional[str]:
    """Find a usable Chromium executable outside Playwright's managed browsers."""
    pw_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if pw_path:
        base = Path(pw_path)
        for chromium_dir in sorted(base.glob("chromium*"), reverse=True):
            for name in ("chrome", "chromium", "headless_shell"):
                for exe in chromium_dir.rglob(name):
                    if exe.is_file() and os.access(exe, os.X_OK):
                        return str(exe)

    for path in (
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome-stable",
    ):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    return None


def get_launch_kwargs() -> dict:
    """Return kwargs for playwright chromium.launch().

    Detects a pre-installed Chromium (cloud environments, CI) and passes
    executable_path so the Playwright driver doesn't need its own download.
    Falls back to Playwright's default when nothing else is found.
    """
    kwargs: dict = {
        "headless": HEADLESS,
        "args": list(_LAUNCH_ARGS),
    }

    exe = _find_chromium_executable()
    if exe:
        kwargs["executable_path"] = exe
        logger.debug("Using system Chromium: %s", exe)

    return kwargs
