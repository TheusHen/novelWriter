"""
novelWriter – Synchronisation Project Files
============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import json
import os

from pathlib import Path, PurePosixPath

from novelwriter.constants import nwFiles
from novelwriter.sync.model import SyncFile, contentHash

SYNC_META_FILES = frozenset((nwFiles.BUILDS_FILE, nwFiles.DICT_FILE, "nonfiction.json"))
STATE_PATH = Path(".novelwriter-sync") / "state.json"


def projectFiles(projectPath: Path) -> dict[str, bytes]:
    """Read the portable project files that must follow the manuscript."""
    files: dict[str, bytes] = {}
    rootFile = projectPath / nwFiles.PROJ_FILE
    if not rootFile.is_file():
        raise ValueError("The selected folder is not a novelWriter project")
    files[nwFiles.PROJ_FILE] = rootFile.read_bytes()

    contentPath = projectPath / "content"
    if contentPath.is_dir():
        for path in sorted(contentPath.glob("*.nwd")):
            files[_relativePath(projectPath, path)] = path.read_bytes()

    metaPath = projectPath / "meta"
    for fileName in SYNC_META_FILES:
        path = metaPath / fileName
        if path.is_file():
            files[_relativePath(projectPath, path)] = path.read_bytes()
    return files


def writeProjectFiles(projectPath: Path, files: dict[str, bytes]) -> None:
    """Apply a synchronised portable project state atomically per file."""
    for name, data in files.items():
        relative = _safeRelativePath(name)
        path = projectPath / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.sync-tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)


def fileEntries(files: dict[str, bytes]) -> dict[str, SyncFile]:
    """Build immutable manifest entries for a project state."""
    return {path: SyncFile(contentHash(data), len(data)) for path, data in files.items()}


def loadSyncState(projectPath: Path, projectId: str) -> str | None:
    """Return the last manifest used by this device for the project."""
    path = projectPath / STATE_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    manifest = data.get("manifest") if isinstance(data, dict) and data.get("projectId") == projectId else None
    return manifest if isinstance(manifest, str) and len(manifest) == 64 else None


def saveSyncState(projectPath: Path, projectId: str, manifestHash: str) -> None:
    """Record the baseline used for the next three-way merge."""
    path = projectPath / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"projectId": projectId, "manifest": manifestHash}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _relativePath(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _safeRelativePath(name: str) -> Path:
    parts = name.split("/")
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in parts:
        raise ValueError("Unsafe synchronisation file path")
    if parts[0] not in {"content", "meta", nwFiles.PROJ_FILE}:
        raise ValueError("Unsafe synchronisation file path")
    if len(parts) > 2 or (parts[0] == "content" and not path.name.endswith(".nwd")):
        raise ValueError("Unsupported synchronisation file path")
    if parts[0] == "meta" and path.name not in SYNC_META_FILES:
        raise ValueError("Unsupported synchronisation file path")
    return Path(*path.parts)
