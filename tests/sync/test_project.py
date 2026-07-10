"""
novelWriter – Synchronisation Project Tests
============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import pytest

from novelwriter.sync.project import projectFiles, writeProjectFiles


def testProjectFiles_ReadPortableData(tmp_path):
    """Only portable project data is read."""
    (tmp_path / "content").mkdir()
    (tmp_path / "meta").mkdir()
    (tmp_path / "nwProject.nwx").write_text("project", encoding="utf-8")
    (tmp_path / "content" / "0000000000001.nwd").write_text("text", encoding="utf-8")
    (tmp_path / "meta" / "nonfiction.json").write_text("{}", encoding="utf-8")
    (tmp_path / "meta" / "index.json").write_text("{}", encoding="utf-8")

    assert projectFiles(tmp_path) == {
        "nwProject.nwx": b"project",
        "content/0000000000001.nwd": b"text",
        "meta/nonfiction.json": b"{}",
    }


def testProjectFiles_RejectsNonProjectFolder(tmp_path):
    """A folder without a project file is rejected."""
    with pytest.raises(ValueError, match="not a novelWriter project"):
        projectFiles(tmp_path)


def testProjectFiles_WritesOnlyPortablePaths(tmp_path):
    """Remote data cannot escape the project folder."""
    writeProjectFiles(tmp_path, {"content/0000000000001.nwd": b"text"})

    assert (tmp_path / "content" / "0000000000001.nwd").read_bytes() == b"text"
    with pytest.raises(ValueError, match="Unsafe"):
        writeProjectFiles(tmp_path, {"../unsafe": b"text"})
