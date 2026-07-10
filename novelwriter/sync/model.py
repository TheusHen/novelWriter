"""
novelWriter – Synchronisation Data Models
==========================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import hashlib
import json

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SYNC_SCHEMA = 1


def utcNow() -> str:
    """Return the current UTC time in a portable format."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def contentHash(data: bytes) -> str:
    """Return the SHA-256 checksum of synchronised file data."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class SyncFile:
    """A content-addressed file included in a project revision."""

    hash: str
    size: int

    def pack(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""
        return asdict(self)

    @classmethod
    def unpack(cls, data: dict[str, Any]) -> SyncFile:
        """Create an entry from JSON data."""
        fileHash = data.get("hash")
        fileSize = data.get("size")
        if not isinstance(fileHash, str) or len(fileHash) != 64:
            raise ValueError("Invalid synchronisation file hash")
        if not isinstance(fileSize, int) or fileSize < 0:
            raise ValueError("Invalid synchronisation file size")
        return cls(fileHash, fileSize)


@dataclass(frozen=True, slots=True)
class SyncManifest:
    """The complete immutable state of one project revision."""

    projectId: str
    deviceId: str
    revision: int
    parent: str | None
    createdAt: str
    files: dict[str, SyncFile]
    schema: int = SYNC_SCHEMA

    def pack(self) -> dict[str, Any]:
        """Return a stable JSON-compatible manifest representation."""
        return {
            "schema": self.schema,
            "projectId": self.projectId,
            "deviceId": self.deviceId,
            "revision": self.revision,
            "parent": self.parent,
            "createdAt": self.createdAt,
            "files": {path: entry.pack() for path, entry in sorted(self.files.items())},
        }

    def toBytes(self) -> bytes:
        """Serialise the manifest deterministically."""
        return (json.dumps(self.pack(), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode()

    def digest(self) -> str:
        """Return the content address of the manifest itself."""
        return contentHash(self.toBytes())

    @classmethod
    def fromBytes(cls, data: bytes) -> SyncManifest:
        """Read and validate a manifest stored by a remote backend."""
        try:
            raw = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid synchronisation manifest") from exc
        if not isinstance(raw, dict) or raw.get("schema") != SYNC_SCHEMA:
            raise ValueError("Unsupported synchronisation manifest")
        values = ("projectId", "deviceId", "createdAt")
        if any(not isinstance(raw.get(value), str) or not raw[value] for value in values):
            raise ValueError("Invalid synchronisation manifest identity")
        revision = raw.get("revision")
        parent = raw.get("parent")
        files = raw.get("files")
        if not isinstance(revision, int) or revision < 1:
            raise ValueError("Invalid synchronisation revision")
        if parent is not None and (not isinstance(parent, str) or len(parent) != 64):
            raise ValueError("Invalid synchronisation parent")
        if not isinstance(files, dict) or any(not isinstance(path, str) or not path for path in files):
            raise ValueError("Invalid synchronisation files")
        if any(not isinstance(entry, dict) for entry in files.values()):
            raise ValueError("Invalid synchronisation file entry")
        return cls(
            raw["projectId"],
            raw["deviceId"],
            revision,
            parent,
            raw["createdAt"],
            {path: SyncFile.unpack(entry) for path, entry in files.items()},
        )
