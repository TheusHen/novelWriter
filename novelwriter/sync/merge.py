"""
novelWriter – Three-Way Text Merge
==================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True, slots=True)
class MergeResult:
    """The merged text and whether a human decision remains necessary."""

    text: str
    hasConflicts: bool


def mergeText(base: str, local: str, remote: str) -> MergeResult:
    """Merge line edits, preserving both sides when their edits overlap."""
    if local == remote:
        return MergeResult(local, False)
    if local == base:
        return MergeResult(remote, False)
    if remote == base:
        return MergeResult(local, False)

    baseLines = base.splitlines(keepends=True)
    localChanges = _changes(baseLines, local.splitlines(keepends=True))
    remoteChanges = _changes(baseLines, remote.splitlines(keepends=True))
    result: list[str] = []
    position = 0
    localPos = 0
    remotePos = 0
    conflict = False

    while localPos < len(localChanges) or remotePos < len(remoteChanges):
        localChange = localChanges[localPos] if localPos < len(localChanges) else None
        remoteChange = remoteChanges[remotePos] if remotePos < len(remoteChanges) else None
        starts = [change.start for change in (localChange, remoteChange) if change]
        start = min(starts)
        result.extend(baseLines[position:start])

        if localChange and remoteChange and _overlap(localChange, remoteChange):
            end = max(localChange.end, remoteChange.end)
            if localChange.lines == remoteChange.lines:
                result.extend(localChange.lines)
            else:
                conflict = True
                result.extend(_conflictLines(localChange.lines, remoteChange.lines))
            position = end
            localPos += 1
            remotePos += 1
        elif localChange and localChange.start == start:
            result.extend(localChange.lines)
            position = localChange.end
            localPos += 1
        elif remoteChange:
            result.extend(remoteChange.lines)
            position = remoteChange.end
            remotePos += 1

    result.extend(baseLines[position:])
    return MergeResult("".join(result), conflict)


@dataclass(frozen=True, slots=True)
class _Change:
    start: int
    end: int
    lines: list[str]


def _changes(base: list[str], changed: list[str]) -> list[_Change]:
    matcher = SequenceMatcher(a=base, b=changed, autojunk=False)
    return [_Change(i1, i2, changed[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


def _overlap(left: _Change, right: _Change) -> bool:
    if left.start == left.end == right.start == right.end:
        return left.start == right.start
    return (left.start < right.end and right.start < left.end) or left.start == right.start


def _conflictLines(local: list[str], remote: list[str]) -> list[str]:
    return ["<<<<<<< LOCAL\n", *local, "=======\n", *remote, ">>>>>>> REMOTE\n"]
