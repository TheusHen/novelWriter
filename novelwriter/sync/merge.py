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


@dataclass(frozen=True, slots=True)
class _Change:
    """One replacement over a half-open range in the common base."""

    start: int
    end: int
    lines: tuple[str, ...]


def mergeText(base: str, local: str, remote: str) -> MergeResult:
    """Merge line changes, producing no output for an unresolved conflict."""
    if local == remote:
        return MergeResult(local, False)
    if local == base:
        return MergeResult(remote, False)
    if remote == base:
        return MergeResult(local, False)

    baseLines = tuple(base.splitlines(keepends=True))
    localChanges = _changes(baseLines, tuple(local.splitlines(keepends=True)))
    remoteChanges = _changes(baseLines, tuple(remote.splitlines(keepends=True)))
    result: list[str] = []
    position = 0
    localIndex = 0
    remoteIndex = 0

    while localIndex < len(localChanges) or remoteIndex < len(remoteChanges):
        start = min(
            change.start
            for change in (
                localChanges[localIndex] if localIndex < len(localChanges) else None,
                remoteChanges[remoteIndex] if remoteIndex < len(remoteChanges) else None,
            )
            if change is not None
        )
        result.extend(baseLines[position:start])
        end = start
        localGroup, localIndex, end = _takeRegion(localChanges, localIndex, start, end)
        remoteGroup, remoteIndex, end = _takeRegion(remoteChanges, remoteIndex, start, end)

        while True:
            oldEnd = end
            moreLocal, localIndex, end = _takeRegion(localChanges, localIndex, start, end)
            moreRemote, remoteIndex, end = _takeRegion(remoteChanges, remoteIndex, start, end)
            localGroup.extend(moreLocal)
            remoteGroup.extend(moreRemote)
            if end == oldEnd:
                break

        localText = _apply(baseLines, start, end, localGroup)
        remoteText = _apply(baseLines, start, end, remoteGroup)
        if not localGroup:
            result.extend(remoteText)
        elif not remoteGroup or localText == remoteText:
            result.extend(localText)
        else:
            return MergeResult("", True)
        position = end

    result.extend(baseLines[position:])
    return MergeResult("".join(result), False)


def _changes(base: tuple[str, ...], changed: tuple[str, ...]) -> tuple[_Change, ...]:
    matcher = SequenceMatcher(a=base, b=changed, autojunk=False)
    return tuple(_Change(i1, i2, changed[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal")


def _takeRegion(changes: tuple[_Change, ...], index: int, start: int, end: int) -> tuple[list[_Change], int, int]:
    result: list[_Change] = []
    while index < len(changes) and _inRegion(changes[index], start, end):
        change = changes[index]
        result.append(change)
        end = max(end, change.end)
        index += 1
    return result, index, end


def _inRegion(change: _Change, start: int, end: int) -> bool:
    if start == end:
        return change.start == start
    return change.start < end and change.end > start


def _apply(base: tuple[str, ...], start: int, end: int, changes: list[_Change]) -> tuple[str, ...]:
    if not changes:
        return base[start:end]
    result: list[str] = []
    position = start
    for change in changes:
        result.extend(base[position : change.start])
        result.extend(change.lines)
        position = change.end
    result.extend(base[position:end])
    return tuple(result)
