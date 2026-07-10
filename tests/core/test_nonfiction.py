"""
novelWriter – Non-Fiction Workspace Tests
==========================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

from novelwriter.core.nonfiction import NonfictionNotebook
from novelwriter.core.project import NWProject

from tests.helpers import buildTestProject


def testNonfictionNotebook_SaveLoad(tmp_path):
    """Structured research data survives a portable JSON round trip."""
    path = tmp_path / "nonfiction.json"
    notebook = NonfictionNotebook()

    notebook.enable(path)
    entryId = notebook.addEntry("sources", {"title": "Primary source", "url": "https://example.com"})

    assert notebook.save() is True
    loaded = NonfictionNotebook()
    assert loaded.load(path) is True
    assert loaded.data["sources"] == [{"id": entryId, "title": "Primary source", "url": "https://example.com"}]


def testNWProject_CreateNonfictionWorkspace(fncPath, mockGUI, mockRnd):
    """A project receives topic, evidence and process templates."""
    project = NWProject()
    buildTestProject(project, fncPath)

    assert project.nonfiction.enabled is False
    assert project.createNonfictionWorkspace() is True
    assert project.createNonfictionWorkspace() is False
    assert project.saveProject() is True

    names = {item.itemName for item in project.tree}
    assert {
        "Chapters by Theme",
        "Sources and References",
        "Interviews",
        "Data and Evidence",
        "Hypotheses and Results",
        "Chronology",
        "Process Journal",
        "Reader Exercises",
        "Experience and Claims",
    } <= names
    assert (fncPath / "meta" / "nonfiction.json").is_file()
    assert any(
        "| Claim | Source | Method | Confidence |" in project.storage.getDocumentText(item.itemHandle)
        for item in project.tree
    )

    project.closeProject()
