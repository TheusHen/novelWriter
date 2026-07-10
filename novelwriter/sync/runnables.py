"""
novelWriter – Synchronisation Background Tasks
===============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

from novelwriter.sync.auth import GoogleCredentialStore, GoogleOAuth, OAuthClient
from novelwriter.sync.service import ProjectSynchroniser

if TYPE_CHECKING:
    from pathlib import Path


class GoogleConnectTask(QRunnable):
    """Run the browser-based desktop OAuth consent flow outside the GUI thread."""

    def __init__(self, client: OAuthClient) -> None:
        super().__init__()
        self._client = client
        self.signals = GoogleConnectSignals()

    @pyqtSlot()
    def run(self) -> None:
        """Obtain a Google token or return the readable error."""
        try:
            self.signals.connected.emit(self._client, GoogleOAuth.authorise(self._client))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class GoogleConnectSignals(QObject):
    """Signals emitted by the desktop OAuth task."""

    connected = pyqtSignal(object, object)
    failed = pyqtSignal(str)


class GoogleSyncTask(QRunnable):
    """Synchronise a closed project without blocking the editor interface."""

    def __init__(self, projectPath: Path, projectId: str, operation: str) -> None:
        super().__init__()
        self._projectPath = projectPath
        self._projectId = projectId
        self._operation = operation
        self.signals = GoogleSyncSignals()

    @pyqtSlot()
    def run(self) -> None:
        """Run one safe sync or download operation."""
        try:
            remote = GoogleCredentialStore().remote()
            synchroniser = ProjectSynchroniser(remote)
            outcome = (
                synchroniser.pull(self._projectPath, self._projectId)
                if self._operation == "pull"
                else synchroniser.sync(self._projectPath, self._projectId)
            )
            self.signals.finished.emit(self._operation, outcome)
        except Exception as exc:
            self.signals.failed.emit(self._operation, str(exc))


class GoogleSyncSignals(QObject):
    """Signals emitted by a background synchronisation operation."""

    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)
