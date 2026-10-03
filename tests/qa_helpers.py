"""Shared helpers for QA extra tests (PR #2, written @ caabfbd, adapted @ cb8d9e8). Not part of the repo.

ADAPTATION @cb8d9e8: dpapi gained unprotect_status() (8467fde, entropy); the XOR fake
now patches it too, else every DPAPI read-back fails on Linux."""
import json
import threading
import time

import requests

from src.utils import dpapi
from src.utils.desk_token import TokenManager

PASSWORD = "Qa-Pw-&<>\"'-7c1e"
USERNAME = "qa.user.a@example.com"
TOKEN_A = "a1" * 32
TOKEN_A2 = "a2" * 32
TOKEN_B = "b1" * 32


class ListLogger:
    def __init__(self):
        self.messages = []
        self.lock = threading.Lock()

    def _add(self, level, message):
        with self.lock:
            self.messages.append(f"{level}:{message}")

    def info(self, m): self._add("info", m)
    def error(self, m): self._add("error", m)
    def debug(self, m): self._add("debug", m)
    def warning(self, m): self._add("warning", m)
    def critical(self, m): self._add("critical", m)

    @property
    def text(self):
        return "\n".join(self.messages)


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def ok_body(token, employee_id="7", ttl=86400, now=None):
    now = time.time() if now is None else now
    return {
        "status": "ok",
        "token": token,
        "employee_id": employee_id,
        "expires_at": int(now + ttl),
        "ttl_seconds": ttl,
        "chain_expires_at": int(now + 7 * 86400),
    }


def use_xor_dpapi(monkeypatch):
    def xor(data):
        return bytes(b ^ 0x5A for b in data)
    monkeypatch.setattr(dpapi, "is_available", lambda: True)
    monkeypatch.setattr(dpapi, "protect", xor)
    monkeypatch.setattr(dpapi, "unprotect", xor)
    monkeypatch.setattr(dpapi, "unprotect_status", lambda data: (xor(data), False))


def route(monkeypatch, handler):
    def _post(url, data=None, **kwargs):
        assert isinstance(data, dict)
        for key in ("token=", "password=", "username="):
            assert key not in url.lower()
        return handler(url, data, kwargs)
    monkeypatch.setattr(requests, "post", _post)


def make_manager(tmp_path, logger, loader=None, notices=None):
    return TokenManager(
        logger=logger,
        storage_dir=str(tmp_path),
        credential_loader=(loader or (lambda: None)),
        on_reauth_notice=(lambda: notices.append("shown")) if notices is not None else None,
        computer_name="QA-PC",
        app_version="2.2.3",
    )


def seed(manager, token=TOKEN_A, employee_id="7", expires_in=86400):
    record = {
        "token": token,
        "employee_id": str(employee_id),
        "expires_at_epoch": time.time() + expires_in,
        "chain_expires_at_epoch": time.time() + 7 * 86400,
    }
    with manager._lock:
        manager._record = dict(record)
        manager._employee_id = str(employee_id)
    manager._store.save(record)
    return record
