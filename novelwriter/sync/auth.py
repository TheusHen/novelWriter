"""
novelWriter – Google OAuth Credentials
=======================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import secrets
import time
import webbrowser

from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from novelwriter import CONFIG
from novelwriter.sync.googledrive import DRIVE_SCOPE, GoogleDriveRemote

try:
    import keyring
except ImportError:  # pragma: no cover
    keyring = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from pathlib import Path


logger = logging.getLogger(__name__)

KEYRING_SERVICE = "novelWriter.googleDrive"
KEYRING_USER = "desktop-oauth"
TOKEN_FILE = "google-token.json"


class GoogleAuthError(RuntimeError):
    """An error while connecting the application to Google OAuth."""


@dataclass(frozen=True, slots=True)
class OAuthClient:
    """The public configuration of an installed Google OAuth client."""

    clientId: str
    clientSecret: str
    authUri: str
    tokenUri: str

    @classmethod
    def fromFile(cls, path: Path) -> OAuthClient:
        """Load a Google Cloud desktop OAuth client JSON file."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GoogleAuthError("Could not read the Google OAuth client file") from exc
        if not isinstance(raw, dict):
            raise GoogleAuthError("Select a Desktop OAuth client JSON file from Google Cloud")
        inner = raw.get("installed")
        if not isinstance(inner, dict):
            raise GoogleAuthError("Select a Desktop OAuth client JSON file from Google Cloud")
        clientId = inner.get("client_id")
        clientSecret = inner.get("client_secret")
        authUri = inner.get("auth_uri")
        tokenUri = inner.get("token_uri")
        if not (
            isinstance(clientId, str)
            and clientId
            and isinstance(clientSecret, str)
            and clientSecret
            and isinstance(authUri, str)
            and authUri
            and isinstance(tokenUri, str)
            and tokenUri
        ):
            raise GoogleAuthError("The Google OAuth client file is incomplete")
        return cls(clientId, clientSecret, authUri, tokenUri)


@dataclass(frozen=True, slots=True)
class OAuthToken:
    """A refreshable OAuth access token."""

    accessToken: str
    refreshToken: str
    expiresAt: float

    @property
    def isExpired(self) -> bool:
        """Return whether a refresh is required before an API call."""
        return self.expiresAt <= time.time() + 60


class GoogleOAuth:
    """Desktop OAuth authorisation with PKCE and a loopback callback."""

    @classmethod
    def authorise(cls, client: OAuthClient, timeout: int = 300) -> OAuthToken:
        """Open the browser consent flow and return an access and refresh token."""
        server = _CallbackServer(("127.0.0.1", 0), _CallbackHandler)
        redirectUri = f"http://127.0.0.1:{server.server_port}/"
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(32)
        query = urlencode({
            "client_id": client.clientId,
            "redirect_uri": redirectUri,
            "response_type": "code",
            "scope": DRIVE_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        if not webbrowser.open(f"{client.authUri}?{query}"):
            raise GoogleAuthError("Could not open the browser for Google authorisation")
        server.timeout = 1
        deadline = time.monotonic() + timeout
        while server.result is None and time.monotonic() < deadline:
            server.handle_request()
        if server.result is None:
            raise GoogleAuthError("Google authorisation timed out")
        if server.result.get("state") != state:
            raise GoogleAuthError("Google authorisation returned an invalid state")
        if error := server.result.get("error"):
            raise GoogleAuthError(f"Google authorisation failed: {error}")
        code = server.result.get("code")
        if not code:
            raise GoogleAuthError("Google authorisation did not return a code")
        values = cls._tokenRequest(
            client,
            {
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirectUri,
            },
        )
        refresh = values.get("refresh_token")
        if not isinstance(refresh, str) or not refresh:
            raise GoogleAuthError("Google did not issue a refresh token")
        return cls._makeToken(values, refresh)

    @classmethod
    def refresh(cls, client: OAuthClient, token: OAuthToken) -> OAuthToken:
        """Exchange a stored refresh token for a new short-lived access token."""
        values = cls._tokenRequest(client, {"grant_type": "refresh_token", "refresh_token": token.refreshToken})
        return cls._makeToken(values, token.refreshToken)

    @staticmethod
    def _tokenRequest(client: OAuthClient, values: dict[str, str]) -> dict[str, Any]:
        data = urlencode({"client_id": client.clientId, "client_secret": client.clientSecret, **values}).encode()
        request = Request(client.tokenUri, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise GoogleAuthError("Could not exchange the Google OAuth token") from exc
        if not isinstance(payload, dict):
            raise GoogleAuthError("Google returned an invalid OAuth token")
        return payload

    @staticmethod
    def _makeToken(values: dict[str, Any], refresh: str) -> OAuthToken:
        access = values.get("access_token")
        lifetime = values.get("expires_in")
        if not isinstance(access, str) or not access or not isinstance(lifetime, int | float):
            raise GoogleAuthError("Google returned an incomplete OAuth token")
        return OAuthToken(access, refresh, time.time() + float(lifetime))


class GoogleCredentialStore:
    """Store the desktop token in the OS credential vault or a local data file."""

    def save(self, client: OAuthClient, token: OAuthToken) -> None:
        """Save credentials without placing a token in a project or source file."""
        payload = json.dumps({"client": asdict(client), "token": asdict(token)})
        if keyring is not None:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USER, payload)
                return
            except Exception:
                logger.debug("OS keyring unavailable; storing credentials in the user data path")
        try:
            path = self._tokenPath()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            raise GoogleAuthError("Could not store Google credentials securely") from exc

    def remote(self) -> GoogleDriveRemote:
        """Return an authenticated Drive remote, refreshing its token when needed."""
        client, token = self._load()
        if token.isExpired:
            token = GoogleOAuth.refresh(client, token)
            self.save(client, token)
        return GoogleDriveRemote(token.accessToken)

    def isConnected(self) -> bool:
        """Return whether credentials were previously configured."""
        try:
            return self._readRaw() is not None
        except Exception:
            return False

    def clear(self) -> None:
        """Remove stored credentials from the keyring and the file fallback."""
        if keyring is not None:
            with contextlib.suppress(Exception):
                keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
        path = self._tokenPath()
        if path.is_file():
            with contextlib.suppress(OSError):
                path.unlink()

    def _load(self) -> tuple[OAuthClient, OAuthToken]:
        try:
            raw = self._readRaw()
            if not raw:
                raise GoogleAuthError("Connect Google Drive before synchronising")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise GoogleAuthError("Connect Google Drive before synchronising")
            client_raw = data.get("client")
            token_raw = data.get("token")
            if not isinstance(client_raw, dict) or not isinstance(token_raw, dict):
                raise GoogleAuthError("Connect Google Drive before synchronising")
            client = OAuthClient(
                str(client_raw["clientId"]),
                str(client_raw["clientSecret"]),
                str(client_raw["authUri"]),
                str(client_raw["tokenUri"]),
            )
            token = OAuthToken(
                str(token_raw["accessToken"]),
                str(token_raw["refreshToken"]),
                float(token_raw["expiresAt"]),
            )
        except GoogleAuthError:
            raise
        except Exception as exc:
            raise GoogleAuthError("Connect Google Drive before synchronising") from exc
        return client, token

    def _readRaw(self) -> str | None:
        if keyring is not None:
            try:
                value = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
                if value:
                    return value
            except Exception:
                logger.debug("OS keyring unavailable while reading credentials")
        path = self._tokenPath()
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return None

    @staticmethod
    def _tokenPath() -> Path:
        return CONFIG.dataPath(TOKEN_FILE)


class _CallbackServer(HTTPServer):
    result: dict[str, str] | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        server = self.server
        if isinstance(server, _CallbackServer):
            server.result = {key: values[0] for key, values in query.items() if values}
        message = b"<html><body><h2>novelWriter connected.</h2><p>You may close this tab.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

    def log_message(self, fmt: str, *args: object) -> None:
        return
