"""Encrypted Google Drive emergency-event journal for Muichiro.

This module stores explicitly submitted domain events. It intentionally does
NOT capture or replay arbitrary SQL: callers must provide an idempotent event
and a recovery handler before an operation can be safely replayed.
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_URL = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"
_TIMEOUT = (8, 25)


class JournalUnavailable(RuntimeError):
    """The emergency journal could not durably accept an event."""


def _config() -> dict[str, str]:
    keys = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
            "GOOGLE_JOURNAL_FOLDER_ID", "BACKUP_ENCRYPTION_PASSPHRASE")
    return {key: os.getenv(key, "").strip() for key in keys}


def is_configured() -> bool:
    return all(_config().values())


def get_status() -> dict[str, Any]:
    cfg = _config()
    missing = [k for k, value in cfg.items() if not value]
    return {"configured": not missing, "missing": missing,
            "destination": "google_drive" if not missing else None}


def _access_token(cfg: dict[str, str]) -> str:
    try:
        response = requests.post(TOKEN_URL, data={
            "client_id": cfg["GOOGLE_CLIENT_ID"],
            "client_secret": cfg["GOOGLE_CLIENT_SECRET"],
            "refresh_token": cfg["GOOGLE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }, timeout=_TIMEOUT)
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise JournalUnavailable("Google OAuth did not return an access token.")
        return token
    except (requests.RequestException, ValueError) as exc:
        raise JournalUnavailable("Google Drive authentication failed.") from exc


def _encrypt(data: bytes, passphrase: str) -> bytes:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    key = kdf.derive(passphrase.encode("utf-8"))
    ciphertext = AESGCM(key).encrypt(nonce, data, b"MuichiroEmergencyJournal:v1")
    return b"MUJ1" + salt + nonce + ciphertext


def append_event(event_type: str, payload: dict[str, Any], event_id: str | None = None) -> str:
    """Encrypt and upload one explicit event; return only after Drive confirms it."""
    cfg = _config()
    if not all(cfg.values()):
        raise JournalUnavailable("Emergency journal environment is incomplete.")
    if not event_type or not isinstance(payload, dict):
        raise ValueError("event_type and a dictionary payload are required")
    event_id = event_id or str(uuid.uuid4())
    if not isinstance(event_id, str) or not event_id or len(event_id) > 120 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in event_id):
        raise ValueError("event_id must contain only letters, numbers, hyphens, or underscores")
    event = {"version": 1, "event_id": event_id, "event_type": event_type,
             "created_at": datetime.now(timezone.utc).isoformat(), "payload": payload}
    try:
        raw = json.dumps(event, ensure_ascii=False, separators=(",", ":"),
                         sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Event payload must contain JSON-serializable values") from exc
    encrypted = _encrypt(raw, cfg["BACKUP_ENCRYPTION_PASSPHRASE"])
    token = _access_token(cfg)
    headers = {"Authorization": f"Bearer {token}"}
    # Check for an existing event file first, so a caller retrying the same
    # event_id does not create a second journal record.
    safe_id = event_id.replace("'", "\\'")
    query = (f"name = '{safe_id}.muj' and '{cfg['GOOGLE_JOURNAL_FOLDER_ID']}' in parents "
             "and trashed = false")
    try:
        found = requests.get(DRIVE_LIST_URL, headers=headers,
                             params={"q": query, "fields": "files(id,name)", "pageSize": 1},
                             timeout=_TIMEOUT)
        found.raise_for_status()
        if found.json().get("files"):
            return event_id
        metadata = {"name": f"{event_id}.muj",
                    "parents": [cfg["GOOGLE_JOURNAL_FOLDER_ID"]],
                    "mimeType": "application/octet-stream",
                    "appProperties": {"muichiro_event_id": event_id,
                                      "journal_version": "1"}}
        boundary = "muichiro-journal-boundary"
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                + json.dumps(metadata) + f"\r\n--{boundary}\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + encrypted + f"\r\n--{boundary}--".encode()
        upload = requests.post(DRIVE_URL, params={"uploadType": "multipart", "fields": "id,name"},
                               headers={**headers, "Content-Type": f"multipart/related; boundary={boundary}"},
                               data=body, timeout=_TIMEOUT)
        upload.raise_for_status()
        if not upload.json().get("id"):
            raise JournalUnavailable("Google Drive did not confirm the journal upload.")
        return event_id
    except requests.RequestException as exc:
        raise JournalUnavailable("Emergency journal upload could not be confirmed.") from exc
