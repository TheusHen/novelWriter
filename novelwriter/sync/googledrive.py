"""
novelWriter – Google Drive Synchronisation Remote
=================================================

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

from base64 import b64decode, b64encode
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from novelwriter.sync.model import contentHash
from novelwriter.sync.remote import RemoteHead

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.appdata"


class GoogleDriveError(RuntimeError):
    """An error returned by the Google Drive synchronisation backend."""


class GoogleDriveRemote:
    """Content-addressed synchronisation storage in a Drive app-data folder."""

    def __init__(self, accessToken: str) -> None:
        if not accessToken.strip():
            raise ValueError("A Google OAuth access token is required")
        self._accessToken = accessToken

    def getHead(self, projectId: str) -> RemoteHead | None:
        """Return the current project head together with its ETag."""
        found = self._findFile(self._headName(projectId))
        if found is None:
            return None
        fileId = found["id"]
        data, headers = self._request("GET", f"/files/{fileId}", query={"alt": "media"})
        manifestHash = data.decode("ascii").strip()
        etag = headers.get("etag")
        if len(manifestHash) != 64 or not etag:
            raise GoogleDriveError("The Google Drive synchronisation head is invalid")
        return RemoteHead(manifestHash, f"{fileId}|{b64encode(etag.encode()).decode()}")

    def getManifest(self, manifestHash: str) -> bytes:
        """Download one immutable revision manifest."""
        return self._getImmutable(self._manifestName(manifestHash))

    def putManifest(self, data: bytes) -> str:
        """Store a manifest by its content address."""
        manifestHash = contentHash(data)
        self._putImmutable(self._manifestName(manifestHash), data, "application/json")
        return manifestHash

    def getObject(self, objectHash: str) -> bytes:
        """Download one immutable file content object."""
        return self._getImmutable(self._objectName(objectHash))

    def putObject(self, data: bytes) -> str:
        """Store a file content object by its content address."""
        objectHash = contentHash(data)
        self._putImmutable(self._objectName(objectHash), data, "application/octet-stream")
        return objectHash

    def compareAndSetHead(self, projectId: str, expectedVersion: str | None, manifestHash: str) -> bool:
        """Advance the project head using Drive's HTTP ETag precondition."""
        if expectedVersion is None:
            if self._findFile(self._headName(projectId)) is not None:
                return False
            self._createFile(self._headName(projectId), manifestHash.encode(), "text/plain")
            return True

        try:
            fileId, encodedEtag = expectedVersion.split("|", maxsplit=1)
            etag = b64decode(encodedEtag).decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise GoogleDriveError("The Google Drive synchronisation version is invalid") from exc
        try:
            self._request(
                "PATCH",
                f"/files/{fileId}",
                query={"uploadType": "media"},
                data=manifestHash.encode(),
                contentType="text/plain",
                upload=True,
                headers={"If-Match": etag},
            )
        except GoogleDriveError as exc:
            if "HTTP 412" in str(exc):
                return False
            raise
        return True

    def _getImmutable(self, name: str) -> bytes:
        found = self._findFile(name)
        if found is None:
            raise GoogleDriveError(f"Synchronisation object '{name}' was not found")
        data, _ = self._request("GET", f"/files/{found['id']}", query={"alt": "media"})
        return data

    def _putImmutable(self, name: str, data: bytes, contentType: str) -> None:
        if self._findFile(name) is None:
            self._createFile(name, data, contentType)

    def _findFile(self, name: str) -> dict[str, str] | None:
        escaped = name.replace("'", "\\'")
        data, _ = self._request(
            "GET",
            "/files",
            query={
                "spaces": "appDataFolder",
                "q": f"name = '{escaped}' and trashed = false",
                "fields": "files(id,name)",
            },
        )
        try:
            files = json.loads(data).get("files", [])
        except json.JSONDecodeError as exc:
            raise GoogleDriveError("Google Drive returned an invalid file list") from exc
        return files[0] if files else None

    def _createFile(self, name: str, data: bytes, contentType: str) -> None:
        boundary = f"novelwriter-{uuid.uuid4().hex}"
        metadata = json.dumps({"name": name, "parents": ["appDataFolder"]}, separators=(",", ":")).encode()
        body = b"\r\n".join((
            f"--{boundary}".encode(),
            b"Content-Type: application/json; charset=UTF-8",
            b"",
            metadata,
            f"--{boundary}".encode(),
            f"Content-Type: {contentType}".encode(),
            b"",
            data,
            f"--{boundary}--".encode(),
            b"",
        ))
        self._request(
            "POST",
            "/files",
            query={"uploadType": "multipart"},
            data=body,
            contentType=f"multipart/related; boundary={boundary}",
            upload=True,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        data: bytes | None = None,
        contentType: str | None = None,
        upload: bool = False,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, Any]:
        url = f"{DRIVE_UPLOAD if upload else DRIVE_API}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        requestHeaders = {"Authorization": f"Bearer {self._accessToken}"}
        if contentType:
            requestHeaders["Content-Type"] = contentType
        if headers:
            requestHeaders.update(headers)
        request = Request(url, data=data, headers=requestHeaders, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read(), response.headers
        except HTTPError as exc:
            raise GoogleDriveError(f"Google Drive request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise GoogleDriveError("Could not connect to Google Drive") from exc

    @staticmethod
    def _objectName(objectHash: str) -> str:
        return f"nw-sync-object-{objectHash}"

    @staticmethod
    def _manifestName(manifestHash: str) -> str:
        return f"nw-sync-manifest-{manifestHash}"

    @staticmethod
    def _headName(projectId: str) -> str:
        return f"nw-sync-head-{projectId}"
