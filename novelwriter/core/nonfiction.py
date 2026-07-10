"""
novelWriter – Non-Fiction Notebook Data
========================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import json
import uuid

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


NOTEBOOK_FILE = "nonfiction.json"
NOTEBOOK_SCHEMA = 1
NOTEBOOK_SECTIONS = (
    "topics",
    "processJournal",
    "sources",
    "interviews",
    "evidence",
    "exercises",
    "chronology",
    "hypotheses",
    "disclosures",
)


class NonfictionNotebook:
    """Portable structured notes for a non-fiction project."""

    __slots__ = ("_data", "_path")

    def __init__(self) -> None:
        self._data = self._emptyData()
        self._path: Path | None = None

    @property
    def enabled(self) -> bool:
        """Return whether this project has the non-fiction notebook enabled."""
        return self._path is not None

    @property
    def data(self) -> dict[str, Any]:
        """Return a copy of the portable non-fiction data."""
        return json.loads(json.dumps(self._data))

    def load(self, path: Path | None) -> bool:
        """Load notebook data when the project has a non-fiction profile."""
        self._data = self._emptyData()
        self._path = None
        if path is None or not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict) or data.get("schema") != NOTEBOOK_SCHEMA:
            return False
        for name in NOTEBOOK_SECTIONS:
            if not isinstance(data.get(name), list):
                return False
        self._data = data
        self._path = path
        return True

    def enable(self, path: Path) -> None:
        """Enable a new empty notebook at the project's portable meta path."""
        self._path = path
        self._data = self._emptyData()

    def addEntry(self, section: str, entry: dict[str, Any]) -> str:
        """Add a structured entry and return its stable identifier."""
        if section not in NOTEBOOK_SECTIONS:
            raise ValueError("Unknown non-fiction notebook section")
        if not isinstance(entry, dict):
            raise ValueError("A non-fiction notebook entry must be a dictionary")
        entryId = str(uuid.uuid4())
        self._data[section].append({"id": entryId, **entry})
        return entryId

    def save(self) -> bool:
        """Save the notebook in a deterministic portable JSON format."""
        if self._path is None:
            return True
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            temporary.replace(self._path)
        except OSError:
            return False
        return True

    @staticmethod
    def _emptyData() -> dict[str, Any]:
        return {"schema": NOTEBOOK_SCHEMA, "profile": "nonfiction", **{name: [] for name in NOTEBOOK_SECTIONS}}
