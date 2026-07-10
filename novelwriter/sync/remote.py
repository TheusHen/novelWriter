"""
novelWriter – Synchronisation Remote Interface
===============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RemoteHead:
    """The current remote manifest and its compare-and-set version."""

    manifestHash: str
    version: str


class SyncRemote(Protocol):
    """Content-addressed storage operations required by the protocol."""

    def getHead(self, projectId: str) -> RemoteHead | None:
        """Return the latest head, or None for a new project."""
        ...

    def getManifest(self, manifestHash: str) -> bytes:
        """Return a previously stored manifest."""
        ...

    def putManifest(self, data: bytes) -> str:
        """Store a manifest and return its immutable content address."""
        ...

    def getObject(self, objectHash: str) -> bytes:
        """Return a previously stored content object."""
        ...

    def putObject(self, data: bytes) -> str:
        """Store a content object and return its immutable content address."""
        ...

    def compareAndSetHead(self, projectId: str, expectedVersion: str | None, manifestHash: str) -> bool:
        """Set the project head only when the known remote version matches."""
        ...


class MemoryRemote:
    """An in-memory implementation used by tests and mobile prototypes."""

    def __init__(self) -> None:
        self._heads: dict[str, RemoteHead] = {}
        self._manifests: dict[str, bytes] = {}
        self._objects: dict[str, bytes] = {}
        self._version = 0

    def getHead(self, projectId: str) -> RemoteHead | None:
        """Return the head stored for a test project."""
        return self._heads.get(projectId)

    def getManifest(self, manifestHash: str) -> bytes:
        """Return an immutable test manifest."""
        return self._manifests[manifestHash]

    def putManifest(self, data: bytes) -> str:
        """Store an immutable test manifest."""
        from novelwriter.sync.model import contentHash

        manifestHash = contentHash(data)
        self._manifests.setdefault(manifestHash, data)
        return manifestHash

    def getObject(self, objectHash: str) -> bytes:
        """Return an immutable test object."""
        return self._objects[objectHash]

    def putObject(self, data: bytes) -> str:
        """Store an immutable test object."""
        from novelwriter.sync.model import contentHash

        objectHash = contentHash(data)
        self._objects.setdefault(objectHash, data)
        return objectHash

    def compareAndSetHead(self, projectId: str, expectedVersion: str | None, manifestHash: str) -> bool:
        """Update a test head when its version has not changed."""
        current = self._heads.get(projectId)
        if (current.version if current else None) != expectedVersion:
            return False
        self._version += 1
        self._heads[projectId] = RemoteHead(manifestHash, str(self._version))
        return True
