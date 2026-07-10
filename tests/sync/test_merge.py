"""
novelWriter – Synchronisation Merge Tests
==========================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

from novelwriter.sync.merge import mergeText


def testMergeText_IndependentChanges():
    """Changes in separate lines are combined."""
    result = mergeText("First\nSecond\nThird\n", "One\nSecond\nThird\n", "First\nSecond\nThree\n")

    assert result.text == "One\nSecond\nThree\n"
    assert result.hasConflicts is False


def testMergeText_OverlappingChanges():
    """Overlapping changes are preserved as a conflict."""
    result = mergeText("First\n", "One\n", "Uno\n")

    assert result.text == "<<<<<<< LOCAL\nOne\n=======\nUno\n>>>>>>> REMOTE\n"
    assert result.hasConflicts is True
