"""
novelWriter – Project Synchronisation Service
==============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import uuid

from dataclasses import dataclass
from typing import TYPE_CHECKING

from novelwriter.sync.conflicts import SyncConflict, SyncConflictError, loadConflicts, saveConflicts
from novelwriter.sync.merge import mergeText
from novelwriter.sync.model import SyncManifest, contentHash, utcNow
from novelwriter.sync.nwd import composeNwd, splitNwd
from novelwriter.sync.project import fileEntries, loadSyncState, projectFiles, saveSyncState, writeProjectFiles

if TYPE_CHECKING:
    from pathlib import Path

    from novelwriter.sync.remote import SyncRemote


@dataclass(frozen=True, slots=True)
class SyncOutcome:
    """The result of a pull-and-push operation."""

    revision: int
    pulledFiles: int
    pushedFiles: int
    conflicts: tuple[str, ...]
    manifestHash: str


class ProjectSynchroniser:
    """Synchronise a project through any compatible remote backend."""

    def __init__(self, remote: SyncRemote, deviceId: str | None = None) -> None:
        self._remote = remote
        self._deviceId = deviceId or str(uuid.uuid4())

    def sync(self, projectPath: Path, projectId: str) -> SyncOutcome:
        """Reconcile local files with the remote head, then publish a revision."""
        if conflicts := loadConflicts(projectPath, projectId):
            raise SyncConflictError(tuple(entry.path for entry in conflicts))
        local = projectFiles(projectPath)
        head = self._remote.getHead(projectId)
        if head is None:
            outcome = self._publish(projectId, local, None, None, 0, 0, ())
            saveSyncState(projectPath, projectId, outcome.manifestHash)
            return outcome

        remoteManifest = self._readManifest(head.manifestHash)
        if remoteManifest.projectId != projectId:
            raise ValueError("Synchronisation manifest belongs to another project")
        remote = self._readFiles(remoteManifest)
        baseHash = loadSyncState(projectPath, projectId)
        if baseHash is None:
            if local != remote:
                raise RuntimeError("Download the project before synchronising this device")
            saveSyncState(projectPath, projectId, head.manifestHash)
            return SyncOutcome(remoteManifest.revision, 0, 0, (), head.manifestHash)
        base = self._readFiles(self._readManifest(baseHash))
        merged, conflicts, pulled = self._mergeFiles(base, local, remote)
        if merged != local:
            writeProjectFiles(projectPath, merged)
        if conflicts:
            saveSyncState(projectPath, projectId, head.manifestHash)
            saveConflicts(projectPath, projectId, tuple(conflicts))
            return SyncOutcome(
                remoteManifest.revision, pulled, 0, tuple(entry.path for entry in conflicts), head.manifestHash
            )
        if merged == remote:
            saveSyncState(projectPath, projectId, head.manifestHash)
            return SyncOutcome(remoteManifest.revision, pulled, 0, (), head.manifestHash)
        outcome = self._publish(projectId, merged, head.version, head.manifestHash, remoteManifest.revision, pulled, ())
        saveSyncState(projectPath, projectId, outcome.manifestHash)
        return outcome

    def pull(self, projectPath: Path, projectId: str) -> SyncOutcome:
        """Download the latest project revision to pair a new device."""
        if conflicts := loadConflicts(projectPath, projectId):
            raise SyncConflictError(tuple(entry.path for entry in conflicts))
        head = self._remote.getHead(projectId)
        if head is None:
            raise RuntimeError("The project has not been uploaded yet")
        manifest = self._readManifest(head.manifestHash)
        if manifest.projectId != projectId:
            raise ValueError("Synchronisation manifest belongs to another project")
        files = self._readFiles(manifest)
        writeProjectFiles(projectPath, files)
        saveSyncState(projectPath, projectId, head.manifestHash)
        return SyncOutcome(manifest.revision, len(files), 0, (), head.manifestHash)

    def _publish(
        self,
        projectId: str,
        files: dict[str, bytes],
        expectedVersion: str | None,
        parent: str | None,
        previousRevision: int,
        pulledFiles: int,
        conflicts: tuple[str, ...],
    ) -> SyncOutcome:
        entries = fileEntries(files)
        for path, data in files.items():
            if self._remote.putObject(data) != entries[path].hash:
                raise RuntimeError("Synchronisation remote returned an invalid object hash")
        manifest = SyncManifest(projectId, self._deviceId, previousRevision + 1, parent, utcNow(), entries)
        manifestHash = self._remote.putManifest(manifest.toBytes())
        if not self._remote.compareAndSetHead(projectId, expectedVersion, manifestHash):
            raise RuntimeError("The project changed remotely; synchronise again to merge the new revision")
        return SyncOutcome(manifest.revision, pulledFiles, len(files), conflicts, manifestHash)

    def _readFiles(self, manifest: SyncManifest) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        for path, entry in manifest.files.items():
            data = self._remote.getObject(entry.hash)
            if len(data) != entry.size or contentHash(data) != entry.hash:
                raise RuntimeError("Synchronisation remote returned corrupted content")
            files[path] = data
        return files

    def _readManifest(self, manifestHash: str) -> SyncManifest:
        """Read a manifest only after verifying its content address."""
        data = self._remote.getManifest(manifestHash)
        if contentHash(data) != manifestHash:
            raise RuntimeError("Synchronisation remote returned a corrupt manifest")
        return SyncManifest.fromBytes(data)

    def _mergeFiles(
        self, base: dict[str, bytes], local: dict[str, bytes], remote: dict[str, bytes]
    ) -> tuple[dict[str, bytes], list[SyncConflict], int]:
        result: dict[str, bytes] = {}
        conflicts: list[SyncConflict] = []
        pulled = 0
        for path in sorted(set(base) | set(local) | set(remote)):
            baseData = base.get(path)
            localData = local.get(path)
            remoteData = remote.get(path)
            if (
                path.endswith(".nwd")
                and isinstance(baseData, bytes)
                and isinstance(localData, bytes)
                and isinstance(remoteData, bytes)
            ):
                merged, conflict = self._mergeDocument(baseData, localData, remoteData)
                if conflict:
                    conflicts.append(SyncConflict(path, baseData, localData, remoteData))
                else:
                    result[path] = merged
                    pulled += int(merged != localData)
                continue
            if localData == remoteData:
                if localData is not None:
                    result[path] = localData
                continue
            if localData == baseData:
                if remoteData is not None:
                    result[path] = remoteData
                    pulled += 1
                continue
            if remoteData == baseData:
                if localData is not None:
                    result[path] = localData
                continue
            if localData is None:
                if remoteData is not None:
                    result[path] = remoteData
                    pulled += 1
                continue
            if remoteData is not None and path.endswith(".nwd") and baseData is not None:
                merged, conflict = self._mergeDocument(baseData, localData, remoteData)
                if conflict:
                    conflicts.append(SyncConflict(path, baseData, localData, remoteData))
                else:
                    result[path] = merged
                    pulled += int(merged != localData)
            else:
                result[path] = localData
                conflicts.append(SyncConflict(path, baseData, localData, remoteData))
        return result, conflicts, pulled

    @staticmethod
    def _mergeDocument(baseData: bytes, localData: bytes, remoteData: bytes) -> tuple[bytes, bool]:
        """Merge user-authored body text while excluding volatile NWD metadata."""
        base = splitNwd(baseData)
        local = splitNwd(localData)
        remote = splitNwd(remoteData)
        if local.body == remote.body:
            return localData, False
        if local.body == base.body:
            return remoteData, False
        if remote.body == base.body:
            return localData, False
        merged = mergeText(base.body, local.body, remote.body)
        if merged.hasConflicts:
            return localData, True
        return composeNwd(local if local.header else remote, merged.text), False
