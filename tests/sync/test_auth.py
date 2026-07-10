"""
novelWriter – Google OAuth Credential Tests
============================================

This file is a part of novelWriter
Copyright (C) 2026 novelWriter contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""  # noqa

from __future__ import annotations

import json

import pytest

from novelwriter.sync.auth import (
    GoogleAuthError,
    GoogleCredentialStore,
    OAuthClient,
    OAuthToken,
)


def testOAuthClient_FromFile(tmp_path):
    """A desktop client JSON file is accepted and incomplete files are rejected."""
    path = tmp_path / "client.json"
    path.write_text(
        json.dumps({
            "installed": {
                "client_id": "id.apps.googleusercontent.com",
                "client_secret": "secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }),
        encoding="utf-8",
    )
    client = OAuthClient.fromFile(path)
    assert client.clientId.endswith("apps.googleusercontent.com")

    path.write_text("{}", encoding="utf-8")
    with pytest.raises(GoogleAuthError):
        OAuthClient.fromFile(path)


def testGoogleCredentialStore_FileFallback(monkeypatch):
    """Credentials can be stored without an operating system keyring."""
    monkeypatch.setattr("novelwriter.sync.auth.keyring", None)
    client = OAuthClient(
        "id.apps.googleusercontent.com",
        "secret",
        "https://accounts.google.com/o/oauth2/auth",
        "https://oauth2.googleapis.com/token",
    )
    token = OAuthToken("access", "refresh", 9_999_999_999.0)
    store = GoogleCredentialStore()
    store.save(client, token)
    assert store.isConnected() is True
    remote = store.remote()
    assert remote._accessToken == "access"
    store.clear()
    assert store.isConnected() is False


def testGoogleCredentialStore_RequiresConnection(monkeypatch):
    """A missing credential raises a clear authorisation error."""
    monkeypatch.setattr("novelwriter.sync.auth.keyring", None)
    store = GoogleCredentialStore()
    store.clear()
    with pytest.raises(GoogleAuthError, match="Connect Google Drive"):
        store.remote()
