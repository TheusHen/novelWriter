"""
novelWriter – Synchronisation Conflict Store
=============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import base64
import json
import os

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from novelwriter.sync.project import writeProjectFiles

CONFLICT_PATH = Path(".novelwriter-sync") / "conflicts.json"
CONFLICT_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class SyncConflict:
    """The three immutable versions needed to resolve one file conflict."""

    path: str
    base: bytes | None
    local: bytes | None
    remote: bytes | None


class SyncConflictError(RuntimeError):
    """Raised when a project has unresolved synchronisation conflicts."""

    def __init__(self, conflicts: tuple[str, ...]) -> None:
        super().__init__("Resolve synchronisation conflicts before synchronising again")
        self.conflicts = conflicts


def loadConflicts(projectPath: Path, projectId: str) -> tuple[SyncConflict, ...]:
    """Load unresolved conflicts for the requested project."""
    path = projectPath / CONFLICT_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(data, dict) or data.get("schema") != CONFLICT_SCHEMA or data.get("projectId") != projectId:
        return ()
    entries = data.get("files")
    if not isinstance(entries, dict):
        return ()
    result: list[SyncConflict] = []
    for name, value in entries.items():
        if isinstance(name, str) and isinstance(value, dict):
            try:
                result.append(
                    SyncConflict(
                        name, _unpack(value.get("base")), _unpack(value.get("local")), _unpack(value.get("remote"))
                    )
                )
            except ValueError:
                continue
    return tuple(result)


def saveConflicts(projectPath: Path, projectId: str, conflicts: tuple[SyncConflict, ...]) -> None:
    """Persist conflicts outside portable project data so they cannot be published."""
    path = projectPath / CONFLICT_PATH
    if not conflicts:
        with suppress(FileNotFoundError):
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": CONFLICT_SCHEMA,
        "projectId": projectId,
        "files": {
            entry.path: {"base": _pack(entry.base), "local": _pack(entry.local), "remote": _pack(entry.remote)}
            for entry in conflicts
        },
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def resolveConflict(projectPath: Path, projectId: str, name: str, data: bytes | None) -> None:
    """Apply an explicit user resolution and remove that conflict from the store."""
    conflicts = list(loadConflicts(projectPath, projectId))
    if name not in {entry.path for entry in conflicts}:
        raise ValueError("Unknown synchronisation conflict")
    if data is not None:
        writeProjectFiles(projectPath, {name: data})
    remaining = tuple(entry for entry in conflicts if entry.path != name)
    saveConflicts(projectPath, projectId, remaining)


def _pack(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode("ascii") if data is not None else None


def _unpack(data: object) -> bytes | None:
    if data is None:
        return None
    if not isinstance(data, str):
        raise ValueError("Invalid synchronisation conflict")
    try:
        return base64.b64decode(data, validate=True)
    except ValueError as exc:
        raise ValueError("Invalid synchronisation conflict") from exc
