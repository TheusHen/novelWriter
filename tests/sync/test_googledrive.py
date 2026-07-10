"""
novelWriter – Google Drive Remote Tests
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

from base64 import b64encode
from io import BytesIO
from urllib.error import HTTPError

import pytest

from novelwriter.sync.googledrive import GoogleDriveError, GoogleDriveRemote
from novelwriter.sync.model import contentHash


class _FakeResponse:
    def __init__(self, data: bytes, headers: dict[str, str] | None = None) -> None:
        self._data = data
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def testGoogleDriveRemote_RequiresToken():
    """An empty access token is rejected immediately."""
    with pytest.raises(ValueError, match="access token"):
        GoogleDriveRemote("   ")


def testGoogleDriveRemote_RoundTrip(monkeypatch):
    """Objects, manifests and heads use content addressing and ETags."""
    store: dict[str, tuple[bytes, str]] = {}
    files: dict[str, str] = {}
    etags: dict[str, str] = {}
    nextId = {"n": 0}

    def fakeUrlopen(request, timeout=30):
        method = request.get_method()
        url = request.full_url
        headers = {key.lower(): value for key, value in request.header_items()}
        if method == "GET" and "/files?" in url and "spaces=appDataFolder" in url:
            name = None
            if "name+%3D+" in url or "name%20%3D%20" in url or "name =" in url:
                # Extract name from encoded query
                from urllib.parse import parse_qs, urlparse

                query = parse_qs(urlparse(url).query)
                q = query.get("q", [""])[0]
                if "name = '" in q:
                    name = q.split("name = '", 1)[1].split("'", 1)[0]
            payload = {"files": []}
            if name and name in files:
                payload = {"files": [{"id": files[name], "name": name}]}
            return _FakeResponse(json.dumps(payload).encode())
        if method == "GET" and "/files/" in url and "alt=media" in url:
            fileId = url.split("/files/")[1].split("?")[0]
            data, etag = store[fileId]
            return _FakeResponse(data, {"etag": etag})
        if method == "POST" and "uploadType=multipart" in url:
            nextId["n"] += 1
            fileId = f"id{nextId['n']}"
            body = request.data
            # Multipart body ends with the file bytes before the closing boundary
            parts = body.split(b"\r\n\r\n")
            data = parts[-1]
            # strip trailing boundary marker
            data = data.rsplit(b"\r\n--", 1)[0]
            # Recover name from metadata JSON
            meta = json.loads(parts[1].split(b"\r\n")[0].decode())
            name = meta["name"]
            etag = f'"etag-{fileId}"'
            store[fileId] = (data, etag)
            files[name] = fileId
            etags[fileId] = etag
            return _FakeResponse(b"{}")
        if method == "PATCH" and "uploadType=media" in url:
            fileId = url.split("/files/")[1].split("?")[0]
            if headers.get("if-match") != etags[fileId]:
                raise HTTPError(url, 412, "Precondition Failed", hdrs=None, fp=BytesIO())  # type: ignore[arg-type]
            data = request.data
            etag = f'"etag-{fileId}-new"'
            store[fileId] = (data, etag)
            etags[fileId] = etag
            return _FakeResponse(b"{}")
        raise AssertionError(f"Unexpected request {method} {url}")

    monkeypatch.setattr("novelwriter.sync.googledrive.urlopen", fakeUrlopen)
    remote = GoogleDriveRemote("token")
    payload = b"hello-world"
    objectHash = remote.putObject(payload)
    assert objectHash == contentHash(payload)
    assert remote.getObject(objectHash) == payload

    manifest = b'{"schema":1}\n'
    manifestHash = remote.putManifest(manifest)
    assert remote.getManifest(manifestHash) == manifest

    assert remote.compareAndSetHead("proj", None, manifestHash) is True
    head = remote.getHead("proj")
    assert head is not None
    assert head.manifestHash == manifestHash

    # Stale create is rejected
    assert remote.compareAndSetHead("proj", None, manifestHash) is False

    # Successful CAS update
    newHash = contentHash(b"next")
    assert remote.compareAndSetHead("proj", head.version, newHash) is True
    updated = remote.getHead("proj")
    assert updated is not None
    assert updated.manifestHash == newHash

    # Stale CAS fails
    staleVersion = f"{updated.version.split('|')[0]}|{b64encode(b'wrong').decode()}"
    assert remote.compareAndSetHead("proj", staleVersion, contentHash(b"lost")) is False


def testGoogleDriveRemote_MissingObject(monkeypatch):
    """Missing immutable objects raise a Drive error."""

    def fakeUrlopen(request, timeout=30):
        return _FakeResponse(json.dumps({"files": []}).encode())

    monkeypatch.setattr("novelwriter.sync.googledrive.urlopen", fakeUrlopen)
    remote = GoogleDriveRemote("token")
    with pytest.raises(GoogleDriveError, match="was not found"):
        remote.getObject("0" * 64)
