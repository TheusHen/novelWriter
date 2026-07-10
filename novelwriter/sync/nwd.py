"""
novelWriter – Synchronised Document Content
============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import hashlib

from dataclasses import dataclass
from time import time

from novelwriter.common import formatTimeStamp


@dataclass(frozen=True, slots=True)
class NwdText:
    """The volatile document header and synchronisable document body."""

    header: tuple[str, ...]
    body: str


def splitNwd(data: bytes) -> NwdText:
    """Separate novelWriter's volatile header from its user-authored text."""
    text = data.decode("utf-8")
    lines = text.splitlines(keepends=True)
    index = 0
    while index < min(len(lines), 10) and lines[index].startswith("%%~"):
        index += 1
    return NwdText(tuple(lines[:index]), "".join(lines[index:]))


def composeNwd(template: NwdText, body: str) -> bytes:
    """Create a valid document, refreshing only generated metadata fields."""
    if template.header and body and not body.endswith("\n"):
        body += "\n"
    if not template.header:
        return body.encode("utf-8")

    bodyHash = hashlib.sha1(body.encode("utf-8")).hexdigest()
    now = formatTimeStamp(time())
    header: list[str] = []
    for line in template.header:
        if line.startswith("%%~hash:"):
            header.append(f"%%~hash: {bodyHash}\n")
        elif line.startswith("%%~date:"):
            created, _, _ = line.removeprefix("%%~date:").strip().partition("/")
            header.append(f"%%~date: {created or now}/{now}\n")
        else:
            header.append(line)
    return ("".join(header) + body).encode("utf-8")
