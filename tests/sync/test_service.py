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

import pytest

from novelwriter.sync.conflicts import SyncConflictError, loadConflicts
from novelwriter.sync.remote import MemoryRemote
from novelwriter.sync.service import ProjectSynchroniser

PROJECT_ID = "0575ad0e-c0bc-4e93-892e-83246c1e6438"
DOC_NAME = "content/0000000000001.nwd"


def testProjectSynchroniser_MergesIndependentDocumentChanges(tmp_path):
    """Concurrent edits in separate lines are merged."""
    remote = MemoryRemote()
    first = _makeProject(tmp_path / "first", _nwd("First\nSecond\nThird\n"))
    syncA = ProjectSynchroniser(remote, "desktop")
    firstOutcome = syncA.sync(first, PROJECT_ID)
    second = tmp_path / "second"
    shutil.copytree(first, second)

    _writeDocument(first, _nwd("One\nSecond\nThird\n", "desktop"))
    secondOutcome = syncA.sync(first, PROJECT_ID)
    _writeDocument(second, _nwd("First\nSecond\nThree\n", "mobile"))
    thirdOutcome = ProjectSynchroniser(remote, "mobile").sync(second, PROJECT_ID)

    assert firstOutcome.revision == 1
    assert secondOutcome.revision == 2
    assert thirdOutcome.revision == 3
    assert thirdOutcome.conflicts == ()
    assert _documentBody(_readDocument(second)) == "One\nSecond\nThree\n"


def testProjectSynchroniser_LeavesOverlappingChangesForReview(tmp_path):
    """Concurrent edits in one line are not overwritten."""
    remote = MemoryRemote()
    first = _makeProject(tmp_path / "first", _nwd("First\n"))
    syncA = ProjectSynchroniser(remote, "desktop")
    syncA.sync(first, PROJECT_ID)
    second = tmp_path / "second"
    shutil.copytree(first, second)

    _writeDocument(first, _nwd("One\n", "desktop"))
    syncA.sync(first, PROJECT_ID)
    _writeDocument(second, _nwd("Uno\n", "mobile"))
    outcome = ProjectSynchroniser(remote, "mobile").sync(second, PROJECT_ID)

    assert outcome.revision == 2
    assert outcome.pushedFiles == 0
    assert outcome.conflicts == (DOC_NAME,)
    assert _documentBody(_readDocument(second)) == "Uno\n"
    assert loadConflicts(second, PROJECT_ID)[0].path == DOC_NAME
    with pytest.raises(SyncConflictError):
        ProjectSynchroniser(remote, "mobile").sync(second, PROJECT_ID)


def testProjectSynchroniser_PullsProjectToNewDevice(tmp_path):
    """A new device receives a complete paired project before editing."""
    remote = MemoryRemote()
    source = _makeProject(tmp_path / "source", _nwd("Write anywhere\n"))
    ProjectSynchroniser(remote, "desktop").sync(source, PROJECT_ID)
    target = tmp_path / "mobile"

    outcome = ProjectSynchroniser(remote, "mobile").pull(target, PROJECT_ID)

    assert outcome.revision == 1
    assert outcome.pulledFiles == 2
    assert _documentBody(_readDocument(target)) == "Write anywhere\n"


def _makeProject(path: Path, text: str) -> Path:
    (path / "content").mkdir(parents=True)
    (path / "nwProject.nwx").write_text("project", encoding="utf-8")
    _writeDocument(path, text)
    return path


def _writeDocument(path: Path, text: str) -> None:
    (path / DOC_NAME).write_text(text, encoding="utf-8")


def _readDocument(path: Path) -> str:
    return (path / DOC_NAME).read_text(encoding="utf-8")


def _nwd(body: str, source: str = "base") -> str:
    return (
        f"%%~name: Test\n%%~path: root/document\n%%~kind: NOVEL/DOCUMENT\n%%~hash: {source}\n"
        f"%%~date: 2026-01-01 00:00:00/2026-01-01 00:00:00\n{body}"
    )


def _documentBody(text: str) -> str:
    return "".join(line for line in text.splitlines(keepends=True) if not line.startswith("%%~"))
