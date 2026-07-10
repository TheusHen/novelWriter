"""
novelWriter – Synchronisation Service Tests
============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import shutil

from pathlib import Path

from novelwriter.sync.remote import MemoryRemote
from novelwriter.sync.service import ProjectSynchroniser

PROJECT_ID = "0575ad0e-c0bc-4e93-892e-83246c1e6438"
DOC_NAME = "content/0000000000001.nwd"


def testProjectSynchroniser_MergesIndependentDocumentChanges(tmp_path):
    """Concurrent edits in separate lines are merged."""
    remote = MemoryRemote()
    first = _makeProject(tmp_path / "first", "First\nSecond\nThird\n")
    syncA = ProjectSynchroniser(remote, "desktop")
    firstOutcome = syncA.sync(first, PROJECT_ID)
    second = tmp_path / "second"
    shutil.copytree(first, second)

    _writeDocument(first, "One\nSecond\nThird\n")
    secondOutcome = syncA.sync(first, PROJECT_ID)
    _writeDocument(second, "First\nSecond\nThree\n")
    thirdOutcome = ProjectSynchroniser(remote, "mobile").sync(second, PROJECT_ID)

    assert firstOutcome.revision == 1
    assert secondOutcome.revision == 2
    assert thirdOutcome.revision == 3
    assert thirdOutcome.conflicts == ()
    assert _readDocument(second) == "One\nSecond\nThree\n"


def testProjectSynchroniser_LeavesOverlappingChangesForReview(tmp_path):
    """Concurrent edits in one line are not overwritten."""
    remote = MemoryRemote()
    first = _makeProject(tmp_path / "first", "First\n")
    syncA = ProjectSynchroniser(remote, "desktop")
    syncA.sync(first, PROJECT_ID)
    second = tmp_path / "second"
    shutil.copytree(first, second)

    _writeDocument(first, "One\n")
    syncA.sync(first, PROJECT_ID)
    _writeDocument(second, "Uno\n")
    outcome = ProjectSynchroniser(remote, "mobile").sync(second, PROJECT_ID)

    assert outcome.revision == 2
    assert outcome.pushedFiles == 0
    assert outcome.conflicts == (DOC_NAME,)
    assert "<<<<<<< LOCAL" in _readDocument(second)


def testProjectSynchroniser_PullsProjectToNewDevice(tmp_path):
    """A new device receives a complete paired project before editing."""
    remote = MemoryRemote()
    source = _makeProject(tmp_path / "source", "Write anywhere\n")
    ProjectSynchroniser(remote, "desktop").sync(source, PROJECT_ID)
    target = tmp_path / "mobile"

    outcome = ProjectSynchroniser(remote, "mobile").pull(target, PROJECT_ID)

    assert outcome.revision == 1
    assert outcome.pulledFiles == 2
    assert _readDocument(target) == "Write anywhere\n"


def _makeProject(path: Path, text: str) -> Path:
    (path / "content").mkdir(parents=True)
    (path / "nwProject.nwx").write_text("project", encoding="utf-8")
    _writeDocument(path, text)
    return path


def _writeDocument(path: Path, text: str) -> None:
    (path / DOC_NAME).write_text(text, encoding="utf-8")


def _readDocument(path: Path) -> str:
    return (path / DOC_NAME).read_text(encoding="utf-8")
