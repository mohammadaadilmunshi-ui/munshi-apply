from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_browser_executable(explicit: str | None = None) -> str:
    """Resolve an already-installed Chromium-family browser; never download one."""
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    configured = str(os.getenv("MUNSHI_BROWSER_EXECUTABLE") or "").strip()
    if configured:
        candidates.append(configured)

    for command in (
        "google-chrome",
        "google-chrome-stable",
        "microsoft-edge",
        "chromium",
        "chromium-browser",
    ):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(resolved)

    candidates.extend(
        [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        path = str(Path(candidate).expanduser())
        if path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise RuntimeError(
        "No supported installed browser was found; set MUNSHI_BROWSER_EXECUTABLE explicitly"
    )
