"""Desk token, screenshot upload, and Remember me storage tests."""

import base64
import json
import logging
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from cryptography.fernet import Fernet

from src.config import constants
from src.utils import desk_token, dpapi, screenshot, security
from src.utils.desk_token import TokenManager
from src.utils.screenshot import (
    JPEG_FALLBACK_QUALITY,
    ScreenshotManager,
    _encode_jpeg_base64,
)

PASSWORD = "Pw-Unique-Should-Not-Log-9f3a"
TOKEN = "0123456789abcdef" * 4  # 64 hex
OTHER_TOKEN = "fedcba9876543210" * 4
REAL_POST = requests.post


class ListLogger:
    def __init__(self):
        self.messages = []

    def _add(self, level, message):
        self.messages.append(f"{level}:{message}")

    def info(self, message):
        self._add("info", message)

    def error(self, message):
        self._add("error", message)

    def debug(self, message):
        self._add("debug", message)

    def warning(self, message):
        self._add("warning", message)

    def critical(self, message):
        self._add("critical", message)

    @property
    def text(self):
        return "\n".join(self.messages)


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = json.dumps(body)
        self.url = ""

    def json(self):
        return self._body


def ok_body(token, employee_id=7, ttl=86400, expires_at=None, chain_expires_at=None):
    now = time.time()
    return {
        "status": "ok",
        "token": token,
        "employee_id": employee_id,
        "expires_at": now + ttl if expires_at is None else expires_at,
        "ttl_seconds": ttl,
        "chain_expires_at": now + 7 * 86400 if chain_expires_at is None else chain_expires_at,
    }


def assert_url_has_no_secrets(url, data=None, kwargs=None):
    parsed = parse_qs(urlparse(url).query)
    for key in ("token", "password", "username"):
        assert key not in parsed
        assert f"{key}=" not in url.lower()
    kwargs = kwargs or {}
    assert not kwargs.get("params")
    assert kwargs.get("files") is None
    assert kwargs.get("json") is None
    if isinstance(data, dict):
        # Secrets belong in the form body, never the URL.
        return
    if isinstance(data, str):
        assert "password=" not in url


def seed_token(manager, token=TOKEN, employee_id="7", expires_in=86400):
    record = {
        "token": token,
        "employee_id": str(employee_id),
        "expires_at_epoch": time.time() + expires_in,
        "chain_expires_at_epoch": time.time() + 7 * 86400,
    }
    manager._record = dict(record)
    manager._employee_id = str(employee_id)
    manager._store._memory = dict(record)
    return record


@pytest.fixture(autouse=True)
def _block_unexpected_http(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError(f"unexpected HTTP call args={args!r} kwargs_keys={list(kwargs)}")

    monkeypatch.setattr(requests, "post", boom)


@pytest.fixture
def logger():
    return ListLogger()


def make_manager(tmp_path, logger, loader=None, notices=None):
    def _loader():
        return None if loader is None else loader()

    def _notice():
        if notices is not None:
            notices.append("shown")

    return TokenManager(
        logger=logger,
        storage_dir=str(tmp_path),
        credential_loader=_loader,
        on_reauth_notice=_notice,
        computer_name="TEST-PC",
        app_version="2.2.3",
    )


def route(monkeypatch, handler):
    def _post(url, data=None, **kwargs):
        assert_url_has_no_secrets(url, data, kwargs)
        assert isinstance(data, dict)
        return handler(url, data, kwargs)

    monkeypatch.setattr(requests, "post", _post)


def freeze_desk_clock(monkeypatch, start=None):
    """Mutable stand-in for ``desk_token.time.time``. Equal to the deadline is allowed."""
    state = {"now": time.time() if start is None else float(start)}

    def _now():
        return state["now"]

    monkeypatch.setattr(desk_token.time, "time", _now)
    return state


class TestTokenHttp:
    def test_issue_renew_revoke_200(self, tmp_path, logger, monkeypatch):
        calls = []

        def handler(url, data, kwargs):
            calls.append((url, dict(data)))
            if url == constants.DESK_TOKEN_ISSUE_URL:
                assert data["username"] == "ada"
                assert data["password"] == PASSWORD
                assert data["computer_name"] == "TEST-PC"
                assert data["app_version"] == "2.2.3"
                assert "token" not in data
                return FakeResponse(200, ok_body(TOKEN, employee_id=7))
            if url == constants.DESK_TOKEN_RENEW_URL:
                assert data == {"token": TOKEN}
                return FakeResponse(200, ok_body(OTHER_TOKEN, employee_id=7))
            if url == constants.DESK_TOKEN_REVOKE_URL:
                assert data == {"token": OTHER_TOKEN}
                return FakeResponse(200, {"status": "ok"})
            raise AssertionError(url)

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        issued = manager.issue("ada", PASSWORD)
        assert issued.ok
        assert issued.token == TOKEN
        assert issued.employee_id == "7"
        assert manager.get_upload_token() == TOKEN

        renewed = manager.renew()
        assert renewed.ok
        assert renewed.token == OTHER_TOKEN
        assert manager.get_upload_token() == OTHER_TOKEN

        revoked = manager.revoke()
        assert revoked.ok
        assert manager.get_upload_token() is None
        assert [url for url, _data in calls] == [
            constants.DESK_TOKEN_ISSUE_URL,
            constants.DESK_TOKEN_RENEW_URL,
            constants.DESK_TOKEN_REVOKE_URL,
        ]

    def test_issue_401_and_400_and_code_field(self, tmp_path, logger, monkeypatch):
        bodies = [
            (401, {"status": "error", "error": "invalid_credentials"}),
            (400, {"status": "error", "code": "bad_request"}),
        ]
        seen = {"n": 0}

        def handler(url, data, kwargs):
            status, body = bodies[seen["n"]]
            seen["n"] += 1
            return FakeResponse(status, body)

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        invalid = manager.issue("ada", PASSWORD)
        assert invalid.ok is False
        assert invalid.error == "invalid_credentials"
        assert manager.get_upload_token() is None

        bad = manager.issue("ada", "other-password", reset_rejection=True)
        assert bad.ok is False
        assert bad.error == "bad_request"

    def test_renew_401_each_code_including_code_field(self, tmp_path, logger, monkeypatch):
        responses = [
            (401, {"error": "reauth_required"}),
            (401, {"error": "token_expired"}),
            (401, {"code": "token_invalid"}),
        ]
        seen = {"n": 0}

        def handler(url, data, kwargs):
            status, body = responses[seen["n"]]
            seen["n"] += 1
            return FakeResponse(status, body)

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        errors = []
        for _status, body in responses:
            seed_token(manager)
            result = manager.renew()
            errors.append(result.error)
            assert result.ok is False
            assert result.status_code == 401
        assert errors == ["reauth_required", "token_expired", "token_invalid"]

    def test_revoke_401(self, tmp_path, logger, monkeypatch):
        def handler(url, data, kwargs):
            assert data["token"] == TOKEN
            return FakeResponse(401, {"error": "token_invalid"})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        seed_token(manager)
        result = manager.revoke()
        assert result.ok is False
        assert result.error == "token_invalid"
        assert manager.get_upload_token() is None

    def test_429_retry_after_blocks_immediate_repeat(self, tmp_path, logger, monkeypatch):
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            return FakeResponse(429, {"status": "error", "error": "rate_limited", "retry_after": "30"})

        def no_sleep(*_args, **_kwargs):
            raise AssertionError("token client must not sleep on 429")

        monkeypatch.setattr(desk_token.time, "sleep", no_sleep)
        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)

        issued = manager.issue("ada", PASSWORD)
        assert issued.error == "rate_limited"
        assert issued.retry_after == 30
        again = manager.issue("ada", PASSWORD)
        assert again.error == "rate_limited"
        assert calls["n"] == 1

        seed_token(manager)
        manager._blocked_until = 0
        renewed = manager.renew()
        assert renewed.error == "rate_limited"
        assert renewed.retry_after == 30
        assert manager.renew().error == "rate_limited"
        assert calls["n"] == 2

        seed_token(manager)
        manager._blocked_until = 0
        revoked = manager.revoke()
        assert revoked.error == "rate_limited"
        assert revoked.retry_after == 30
        assert calls["n"] == 3

    def test_iso_expiry_is_stored(self, tmp_path, logger, monkeypatch):
        def handler(url, data, kwargs):
            return FakeResponse(200, ok_body(
                TOKEN,
                expires_at="2030-01-02T03:04:05Z",
                chain_expires_at="2030-01-09T03:04:05Z",
            ))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        assert manager.issue("ada", PASSWORD).ok
        snap = manager.snapshot()
        assert snap["has_token"] is True
        assert snap["expires_at_epoch"] > time.time()
        assert snap["chain_expires_at_epoch"] > snap["expires_at_epoch"]

    def test_invalid_credentials_are_not_retried_by_maintain(self, tmp_path, logger, monkeypatch):
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            return FakeResponse(401, {"error": "invalid_credentials"})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        assert manager.issue("ada", PASSWORD).error == "invalid_credentials"
        assert manager.maintain().error == "invalid_credentials"
        assert calls["n"] == 1

    def test_maintain_renews_inside_the_hour_only(self, tmp_path, logger, monkeypatch):
        calls = []

        def handler(url, data, kwargs):
            calls.append(url)
            return FakeResponse(200, ok_body(OTHER_TOKEN))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        seed_token(manager, expires_in=7200)
        assert manager.maintain().ok
        assert calls == []

        seed_token(manager, expires_in=1800)
        renewed = manager.maintain()
        assert renewed.ok
        assert calls == [constants.DESK_TOKEN_RENEW_URL]
        assert manager.get_upload_token() == OTHER_TOKEN


class TestFailureBackoff:
    def test_maintain_404_issues_once_inside_the_hour(self, tmp_path, logger, monkeypatch):
        clock = freeze_desk_clock(monkeypatch)
        start = clock["now"]
        calls = []

        def handler(url, data, kwargs):
            calls.append(url)
            assert data["password"] == PASSWORD
            return FakeResponse(404, {"error": "not_found"})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        manager.set_session("7", "ada")
        first = manager.maintain()
        assert first.error == "endpoint_unavailable"
        assert first.status_code == 404

        for step in (0, 60, 300, 3599):
            clock["now"] = start + step
            again = manager.maintain()
            assert again.error == "backoff"
            assert calls == [constants.DESK_TOKEN_ISSUE_URL]

        clock["now"] = start + 3600
        assert manager.maintain().error == "endpoint_unavailable"
        assert calls == [constants.DESK_TOKEN_ISSUE_URL, constants.DESK_TOKEN_ISSUE_URL]
        assert PASSWORD not in logger.text

    def test_maintain_5xx_backoff_doubles_from_five_minutes(self, tmp_path, logger, monkeypatch):
        clock = freeze_desk_clock(monkeypatch)
        start = clock["now"]
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            assert url == constants.DESK_TOKEN_ISSUE_URL
            return FakeResponse(503, {})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        manager.set_session("7", "ada")

        assert manager.maintain().error == "server_error"
        assert calls["n"] == 1

        clock["now"] = start + 299
        assert manager.maintain().error == "backoff"
        assert calls["n"] == 1

        clock["now"] = start + 300
        assert manager.maintain().status_code == 503
        assert calls["n"] == 2

        clock["now"] = start + 300 + 599
        assert manager.maintain().error == "backoff"
        assert calls["n"] == 2

        clock["now"] = start + 300 + 600
        assert manager.maintain().status_code == 503
        assert calls["n"] == 3

    def test_success_resets_failure_backoff(self, tmp_path, logger, monkeypatch):
        clock = freeze_desk_clock(monkeypatch)
        start = clock["now"]
        planned = [
            FakeResponse(500, {}),
            FakeResponse(200, ok_body(TOKEN)),
            FakeResponse(500, {}),
            FakeResponse(500, {}),
        ]
        calls = {"n": 0}

        def handler(url, data, kwargs):
            response = planned[calls["n"]]
            calls["n"] += 1
            return response

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        manager.set_session("7", "ada")

        assert manager.maintain().status_code == 500
        clock["now"] = start + 300
        assert manager.maintain().ok
        assert manager.get_upload_token() == TOKEN

        manager.clear_local()
        assert manager.get_upload_token() is None
        assert manager.maintain().status_code == 500
        assert calls["n"] == 3

        clock["now"] = start + 300 + 299
        assert manager.maintain().error == "backoff"
        assert calls["n"] == 3

        clock["now"] = start + 300 + 300
        assert manager.maintain().status_code == 500
        assert calls["n"] == 4

    def test_manual_login_bypasses_failure_backoff(self, tmp_path, logger, monkeypatch):
        clock = freeze_desk_clock(monkeypatch)
        start = clock["now"]
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            assert data["password"] == PASSWORD
            return FakeResponse(404, {})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        manager.set_session("7", "ada")
        assert manager.maintain().error == "endpoint_unavailable"
        assert calls["n"] == 1

        clock["now"] = start + 10
        assert manager.maintain().error == "backoff"
        assert manager.issue("ada", PASSWORD).error == "backoff"
        assert calls["n"] == 1

        logged_in = manager.issue("ada", PASSWORD, ignore_backoff=True)
        assert logged_in.error == "endpoint_unavailable"
        assert calls["n"] == 2

        assert manager.maintain().error == "backoff"
        assert calls["n"] == 2
        assert PASSWORD not in logger.text

    def test_recover_respects_failure_backoff(self, tmp_path, logger, monkeypatch):
        clock = freeze_desk_clock(monkeypatch)
        start = clock["now"]
        calls = []

        def handler(url, data, kwargs):
            calls.append(url)
            if url == constants.DESK_TOKEN_RENEW_URL:
                return FakeResponse(503, {})
            return FakeResponse(404, {})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        manager.set_session("7", "ada")

        assert manager.recover_after_rejected_token() is None
        assert calls == [constants.DESK_TOKEN_ISSUE_URL]
        assert manager.recover_after_rejected_token() is None
        assert calls == [constants.DESK_TOKEN_ISSUE_URL]

        clock["now"] = start + 3600
        manager.clear_local()
        seed_token(manager, expires_in=30)
        manager._record["expires_at_epoch"] = clock["now"] + 30
        assert manager.recover_after_rejected_token() is None
        assert calls == [constants.DESK_TOKEN_ISSUE_URL, constants.DESK_TOKEN_RENEW_URL]
        assert manager.recover_after_rejected_token() is None
        assert calls == [constants.DESK_TOKEN_ISSUE_URL, constants.DESK_TOKEN_RENEW_URL]
        assert PASSWORD not in logger.text

    def test_transport_error_uses_the_five_minute_backoff(self, tmp_path, logger, monkeypatch):
        clock = freeze_desk_clock(monkeypatch)
        start = clock["now"]
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            raise ConnectionError("down")

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        manager.set_session("7", "ada")
        assert manager.maintain().error == "network"
        clock["now"] = start + 299
        assert manager.maintain().error == "backoff"
        assert calls["n"] == 1
        clock["now"] = start + 300
        assert manager.maintain().error == "network"
        assert calls["n"] == 2


class TestReauth:
    def test_reauth_with_saved_password_issues(self, tmp_path, logger, monkeypatch):
        notices = []
        calls = []

        def handler(url, data, kwargs):
            calls.append((url, dict(data)))
            if url == constants.DESK_TOKEN_RENEW_URL:
                return FakeResponse(401, {"error": "reauth_required"})
            if url == constants.DESK_TOKEN_ISSUE_URL:
                assert data["username"] == "ada"
                assert data["password"] == PASSWORD
                return FakeResponse(200, ok_body(OTHER_TOKEN, employee_id=7))
            raise AssertionError(url)

        route(monkeypatch, handler)
        manager = make_manager(
            tmp_path, logger, loader=lambda: {"email": "ada", "password": PASSWORD}, notices=notices
        )
        manager.set_session("7", "ada")
        seed_token(manager, expires_in=60)
        result = manager.maintain()
        assert result.ok
        assert result.token == OTHER_TOKEN
        assert notices == []
        assert manager.get_upload_token() == OTHER_TOKEN
        assert calls[0][0] == constants.DESK_TOKEN_RENEW_URL
        assert calls[1][0] == constants.DESK_TOKEN_ISSUE_URL

    def test_reauth_without_saved_password_notifies_once(self, tmp_path, logger, monkeypatch):
        notices = []
        calls = []

        def handler(url, data, kwargs):
            calls.append(url)
            return FakeResponse(401, {"code": "reauth_required"})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: None, notices=notices)
        seed_token(manager, expires_in=60)
        result = manager.maintain()
        assert result.ok is False
        assert result.error == "reauth_required"
        assert notices == ["shown"]
        assert calls == [constants.DESK_TOKEN_RENEW_URL]
        assert manager.get_upload_token() is None
        assert manager.maintain().error == "no_token"
        assert notices == ["shown"]
        assert calls == [constants.DESK_TOKEN_RENEW_URL]

    def test_crash_login_issues_only_with_saved_password(self, tmp_path, logger, monkeypatch):
        calls = []

        def handler(url, data, kwargs):
            calls.append((url, dict(data)))
            return FakeResponse(200, ok_body(OTHER_TOKEN, employee_id=9))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        manager.set_session("9", "ada")
        seed_token(manager, employee_id="9")
        assert manager.handle_crash_login("9") == "issued"
        assert calls[0][0] == constants.DESK_TOKEN_ISSUE_URL
        assert calls[0][1]["password"] == PASSWORD

    def test_crash_login_reuses_unexpired_token_without_password(self, tmp_path, logger, monkeypatch):
        def handler(url, data, kwargs):
            raise AssertionError("issue must not run without a saved password")

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: None)
        seed_token(manager, employee_id="9", expires_in=3600)
        manager._record = None
        assert manager.handle_crash_login("9") == "restored"
        assert manager.get_upload_token() == TOKEN

        manager._record = None
        assert manager.handle_crash_login("someone-else") == "none"
        assert manager.get_upload_token() is None

        manager._store._memory["expires_at_epoch"] = time.time() - 5
        manager._store._memory["employee_id"] = "9"
        assert manager.handle_crash_login("9") == "none"


class TestUpload:
    def _manager(self, tmp_path, logger, loader=None, notices=None):
        return make_manager(tmp_path, logger, loader=loader, notices=notices)

    def test_retry_once_on_token_expired_then_renew(self, tmp_path, logger, monkeypatch):
        uploads = []
        token_calls = []

        def handler(url, data, kwargs):
            if "/desktoken/" in url:
                token_calls.append(url)
                assert list(data) == ["token"]
                return FakeResponse(200, ok_body(OTHER_TOKEN, employee_id=42))
            uploads.append(dict(data))
            if len(uploads) == 1:
                assert data["token"] == TOKEN
                return FakeResponse(401, {"status": "error", "error": "token_expired"})
            assert data["token"] == OTHER_TOKEN
            return FakeResponse(200, {"status": "ok"})

        route(monkeypatch, handler)
        tokens = self._manager(tmp_path, logger)
        tokens.set_session("42", "ada")
        seed_token(tokens, employee_id="42")
        manager = ScreenshotManager(logger=logger, token_manager=tokens)
        assert manager.upload("42", base64_data="abc") is True
        assert len(uploads) == 2
        assert token_calls == [constants.DESK_TOKEN_RENEW_URL]

    def test_retry_once_issues_when_renew_cannot(self, tmp_path, logger, monkeypatch):
        uploads = []

        def handler(url, data, kwargs):
            if url == constants.DESK_TOKEN_RENEW_URL:
                return FakeResponse(401, {"error": "token_invalid"})
            if url == constants.DESK_TOKEN_ISSUE_URL:
                assert data["password"] == PASSWORD
                return FakeResponse(200, ok_body(OTHER_TOKEN, employee_id=42))
            if url == constants.DESK_TOKEN_REVOKE_URL:
                return FakeResponse(200, {"status": "ok"})
            uploads.append(dict(data))
            if len(uploads) == 1:
                return FakeResponse(401, {"code": "token_expired"})
            return FakeResponse(200, {})

        route(monkeypatch, handler)
        tokens = self._manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        tokens.set_session("42", "ada")
        seed_token(tokens, employee_id="42")
        manager = ScreenshotManager(logger=logger, token_manager=tokens)
        assert manager.upload("42", base64_data="abc") is True
        assert len(uploads) == 2
        assert uploads[1]["token"] == OTHER_TOKEN

    def test_tokenless_fallback_when_refresh_fails(self, tmp_path, logger, monkeypatch):
        uploads = []
        notices = []

        def handler(url, data, kwargs):
            if "/desktoken/" in url:
                return FakeResponse(401, {"error": "reauth_required"})
            uploads.append(dict(data))
            if len(uploads) == 1:
                return FakeResponse(401, {"error": "token_expired"})
            return FakeResponse(200, {})

        route(monkeypatch, handler)
        tokens = self._manager(tmp_path, logger, loader=lambda: None, notices=notices)
        tokens.set_session("42", "ada")
        seed_token(tokens, employee_id="42")
        manager = ScreenshotManager(logger=logger, token_manager=tokens)
        assert manager.upload("42", base64_data="abc") is True
        assert len(uploads) == 2
        assert "token" not in uploads[1]
        assert notices == ["shown"]

    def test_tokenless_upload_when_no_token(self, tmp_path, logger, monkeypatch):
        uploads = []

        def handler(url, data, kwargs):
            if "/desktoken/" in url:
                raise AssertionError("tokenless upload must not call desktoken")
            uploads.append(dict(data))
            assert "userid=42" in url
            return FakeResponse(200, {})

        route(monkeypatch, handler)
        tokens = self._manager(tmp_path, logger)
        manager = ScreenshotManager(logger=logger, token_manager=tokens)
        assert manager.upload("42", base64_data="abc") is True
        assert len(uploads) == 1
        assert "token" not in uploads[0]
        assert uploads[0]["format"] == "PNG"

    def test_form_body_percent_encodes_base64_plus(self, tmp_path, logger, monkeypatch):
        captured = []

        def fake_send(self, request, **kwargs):
            captured.append(request)
            response = requests.Response()
            response.status_code = 200
            response._content = b"{}"
            response.url = request.url
            response.headers = requests.structures.CaseInsensitiveDict()
            response.request = request
            return response

        monkeypatch.setattr(requests, "post", REAL_POST)
        monkeypatch.setattr(requests.sessions.Session, "send", fake_send)

        file_value = "ab+c/d="
        assert "+" in file_value
        tokens = self._manager(tmp_path, logger)
        manager = ScreenshotManager(logger=logger, token_manager=tokens)
        assert manager.upload("42", base64_data=file_value) is True

        assert len(captured) == 1
        prepared = captured[0]
        body = prepared.body
        if isinstance(body, bytes):
            body = body.decode("ascii")
        content_type = prepared.headers["Content-Type"]
        assert content_type.startswith("application/x-www-form-urlencoded")
        assert "%2B" in body
        assert "%2F" in body
        assert "%3D" in body
        assert "+" not in body
        assert "format=PNG" in body
        assert "userid=42" in prepared.url
        assert "token=" not in prepared.url
        assert "password=" not in prepared.url
        assert "username=" not in prepared.url

    def test_jpeg_reencode_when_png_base64_exceeds_limit(self, tmp_path, logger, monkeypatch):
        pytest.importorskip("PIL")
        from PIL import Image

        image = _noise_image(160, 120)
        png_b64 = _png_b64(image)
        jpeg_len = len(_encode_jpeg_base64(image, JPEG_FALLBACK_QUALITY))
        assert len(png_b64) > jpeg_len
        monkeypatch.setattr(screenshot, "MAX_UPLOAD_BASE64_CHARS", jpeg_len)

        saves = []
        real_save = Image.Image.save

        def spy_save(self, fp, format=None, **params):
            if format == "JPEG":
                saves.append({"quality": params.get("quality"), "size": self.size})
            return real_save(self, fp, format=format, **params)

        monkeypatch.setattr(Image.Image, "save", spy_save)
        posted = _capture_upload(monkeypatch)

        tokens = self._manager(tmp_path, logger)
        manager = ScreenshotManager(logger=logger, token_manager=tokens)
        assert manager.upload("42", base64_data=png_b64) is True

        assert posted[0]["format"] == "JPEG"
        decoded = Image.open(BytesIO(base64.b64decode(posted[0]["file"])))
        assert decoded.size == image.size
        assert saves
        assert all(item["quality"] == 80 for item in saves)
        assert all(item["size"] == image.size for item in saves)
        text = logger.text
        assert "re-encoding as JPEG" in text
        assert "Downscaling" not in text
        assert str(len(png_b64)) in text
        assert png_b64 not in text
        assert posted[0]["file"] not in text

    def test_downscale_when_jpeg_still_exceeds_limit(self, tmp_path, logger, monkeypatch):
        pytest.importorskip("PIL")
        from PIL import Image

        image = _noise_image(160, 120, seed=2)
        png_b64 = _png_b64(image)
        full_jpeg = _encode_jpeg_base64(image, JPEG_FALLBACK_QUALITY)
        tiny = image.resize((8, 6))
        tiny_len = len(_encode_jpeg_base64(tiny, JPEG_FALLBACK_QUALITY))
        assert len(full_jpeg) > tiny_len
        monkeypatch.setattr(screenshot, "MAX_UPLOAD_BASE64_CHARS", tiny_len)

        saves = []
        real_save = Image.Image.save

        def spy_save(self, fp, format=None, **params):
            if format == "JPEG":
                saves.append({"quality": params.get("quality"), "size": self.size})
            return real_save(self, fp, format=format, **params)

        monkeypatch.setattr(Image.Image, "save", spy_save)
        posted = _capture_upload(monkeypatch)

        tokens = self._manager(tmp_path, logger)
        manager = ScreenshotManager(logger=logger, token_manager=tokens)
        assert manager.upload("42", base64_data=png_b64) is True

        uploaded = posted[0]
        assert uploaded["format"] == "JPEG"
        assert len(uploaded["file"]) <= tiny_len
        decoded = Image.open(BytesIO(base64.b64decode(uploaded["file"])))
        assert decoded.size[0] < image.size[0]
        assert decoded.size[1] < image.size[1]
        assert abs((decoded.size[0] / decoded.size[1]) - (image.size[0] / image.size[1])) < 0.08
        assert any(item["size"][0] < image.size[0] and item["quality"] == 80 for item in saves)
        assert all(item["quality"] == 80 for item in saves)
        text = logger.text
        assert "Downscaling" in text
        assert str(len(png_b64)) in text
        assert png_b64 not in text
        assert uploaded["file"] not in text
        assert full_jpeg not in text


class TestDpapi:
    def test_roundtrip_on_windows(self):
        if not dpapi.is_available():
            pytest.skip("DPAPI round-trip needs Windows")
        blob = dpapi.protect(b"round-trip-secret")
        assert blob != b"round-trip-secret"
        assert dpapi.unprotect(blob) == b"round-trip-secret"

    def test_non_windows_protect_is_unavailable(self):
        if dpapi.is_available():
            pytest.skip("non-Windows fallback")
        with pytest.raises(dpapi.DpapiUnavailable):
            dpapi.protect(b"secret")
        with pytest.raises(dpapi.DpapiUnavailable):
            dpapi.unprotect(b"secret")

    def test_token_stays_in_memory_when_dpapi_unavailable(self, tmp_path, logger, monkeypatch):
        monkeypatch.setattr(dpapi, "is_available", lambda: False)

        def handler(url, data, kwargs):
            return FakeResponse(200, ok_body(TOKEN, employee_id=4))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        assert manager.issue("ada", PASSWORD).ok
        assert manager.get_upload_token() == TOKEN
        assert list(tmp_path.iterdir()) == []

        restarted = make_manager(tmp_path, logger)
        restarted.set_employee_id("4")
        assert restarted.get_upload_token() is None
        assert restarted.restore_stored("4") is False


class TestRememberMe:
    def test_migrates_fernet_file_to_dpapi_and_deletes_legacy(self, tmp_path, monkeypatch, capsys):
        _use_xor_dpapi(monkeypatch)
        _write_legacy(tmp_path, "ada@example.com", PASSWORD)
        manager = security.SecurityManager(base_dir=str(tmp_path))
        loaded = manager.load_credentials()
        assert loaded == {"email": "ada@example.com", "password": PASSWORD}
        assert not (tmp_path / constants.KEY_FILE).exists()
        assert not (tmp_path / constants.DATA_FILE).exists()
        blob = (tmp_path / constants.DPAPI_CREDENTIALS_FILE).read_bytes()
        assert PASSWORD.encode() not in blob
        assert b"ada@example.com" not in blob

        again = security.SecurityManager(base_dir=str(tmp_path)).load_credentials()
        assert again["password"] == PASSWORD
        captured = capsys.readouterr()
        assert PASSWORD not in captured.out
        assert PASSWORD not in captured.err

    def test_failed_legacy_decrypt_deletes_files(self, tmp_path, capsys):
        (tmp_path / constants.KEY_FILE).write_bytes(Fernet.generate_key())
        (tmp_path / constants.DATA_FILE).write_text(
            json.dumps({"email": "ada@example.com", "password": "not-fernet"}),
            encoding="utf-8",
        )
        manager = security.SecurityManager(base_dir=str(tmp_path))
        assert manager.load_credentials() is None
        assert not (tmp_path / constants.KEY_FILE).exists()
        assert not (tmp_path / constants.DATA_FILE).exists()
        captured = capsys.readouterr()
        assert "not-fernet" not in captured.out
        assert "not-fernet" not in captured.err

    def test_legacy_kept_when_dpapi_cannot_save(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dpapi, "is_available", lambda: False)
        _write_legacy(tmp_path, "ada@example.com", PASSWORD)
        manager = security.SecurityManager(base_dir=str(tmp_path))
        assert manager.load_credentials()["password"] == PASSWORD
        assert (tmp_path / constants.KEY_FILE).exists()
        assert (tmp_path / constants.DATA_FILE).exists()
        assert not (tmp_path / constants.DPAPI_CREDENTIALS_FILE).exists()

    def test_new_save_uses_dpapi_only(self, tmp_path, monkeypatch):
        _use_xor_dpapi(monkeypatch)
        manager = security.SecurityManager(base_dir=str(tmp_path))
        assert manager.save_credentials("ada@example.com", PASSWORD) is True
        assert not (tmp_path / constants.KEY_FILE).exists()
        assert not (tmp_path / constants.DATA_FILE).exists()
        blob = (tmp_path / constants.DPAPI_CREDENTIALS_FILE).read_bytes()
        assert PASSWORD.encode() not in blob
        assert manager.load_credentials()["password"] == PASSWORD
        assert manager.clear_credentials() is True
        assert not (tmp_path / constants.DPAPI_CREDENTIALS_FILE).exists()

    def test_save_without_dpapi_does_not_write_the_password(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dpapi, "is_available", lambda: False)
        manager = security.SecurityManager(base_dir=str(tmp_path))
        assert manager.save_credentials("ada@example.com", PASSWORD) is False
        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert PASSWORD.encode() not in path.read_bytes()


class TestLogsAndUrls:
    def test_secrets_do_not_appear_in_logs(self, tmp_path, logger, monkeypatch, caplog, capsys):
        def handler(url, data, kwargs):
            if url == constants.DESK_TOKEN_ISSUE_URL:
                return FakeResponse(200, ok_body(TOKEN))
            if url == constants.DESK_TOKEN_RENEW_URL:
                return FakeResponse(401, {"error": "token_expired", "token": TOKEN})
            if "/ss_upload/" in url:
                return FakeResponse(200, {"status": "ok", "token": TOKEN})
            raise AssertionError(url)

        route(monkeypatch, handler)
        caplog.set_level(logging.DEBUG)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        assert manager.issue("ada", PASSWORD).ok
        seed_token(manager, expires_in=30)
        manager.renew()
        shots = ScreenshotManager(logger=logger, token_manager=manager)
        assert shots.upload("42", base64_data="ab+c/d=") is True

        combined = "\n".join([logger.text, caplog.text, capsys.readouterr().out, capsys.readouterr().err])
        assert PASSWORD not in combined
        assert TOKEN not in combined
        assert OTHER_TOKEN not in combined

    def test_source_does_not_put_secrets_in_urls(self):
        root = Path(__file__).resolve().parents[1]
        files = [
            "src/utils/desk_token.py",
            "src/utils/screenshot.py",
            "src/utils/security.py",
            "src/main.py",
            "src/config/constants.py",
        ]
        for relative in files:
            text = (root / relative).read_text(encoding="utf-8")
            for needle in ("?token=", "?password=", "?username=", "&token=", "&password=", "&username="):
                assert needle not in text, f"{needle} in {relative}"


def _noise_image(width, height, seed=1):
    from PIL import Image
    import random

    rng = random.Random(seed)
    raw = bytes(rng.randrange(256) for _ in range(width * height * 3))
    return Image.frombytes("RGB", (width, height), raw)


def _png_b64(image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _capture_upload(monkeypatch):
    posted = []

    def handler(url, data, kwargs):
        posted.append(dict(data))
        return FakeResponse(200, {})

    route(monkeypatch, handler)
    return posted


def _use_xor_dpapi(monkeypatch):
    def xor(data: bytes) -> bytes:
        return bytes(byte ^ 0x5A for byte in data)

    monkeypatch.setattr(dpapi, "is_available", lambda: True)
    monkeypatch.setattr(dpapi, "protect", lambda data: xor(data))
    monkeypatch.setattr(dpapi, "unprotect", lambda data: xor(data))
    monkeypatch.setattr(dpapi, "unprotect_status", lambda data: (xor(data), False))


class TestQaFixes:
    def test_refuses_token_for_a_different_employee(self, tmp_path, logger, monkeypatch):
        def handler(url, data, kwargs):
            return FakeResponse(200, ok_body(TOKEN, employee_id=7))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("Ada", PASSWORD))
        manager.set_session("8", "ada")
        refused = manager.issue("ada", PASSWORD)
        assert refused.ok is False
        assert refused.error == "employee_mismatch"
        assert manager.get_upload_token("8") is None
        assert manager.get_upload_token("7") is None

        manager.set_session("7", "ada")
        assert manager.issue("ada", PASSWORD, ignore_backoff=True).ok
        shots = ScreenshotManager(logger=logger, token_manager=manager)
        posted = []

        def upload_handler(url, data, kwargs):
            posted.append(dict(data))
            return FakeResponse(200, {})

        route(monkeypatch, upload_handler)
        assert shots.upload("7", base64_data="abc") is True
        assert posted[0]["token"] == TOKEN
        assert shots.upload("8", base64_data="abc") is True
        assert "token" not in posted[1]

    def test_saved_password_requires_the_signed_in_username(self, tmp_path, logger, monkeypatch):
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            return FakeResponse(200, ok_body(TOKEN, employee_id=7))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: (" Ada ", PASSWORD))
        manager.set_session("9", "other@example.com")
        assert manager.handle_crash_login("9") == "none"
        assert calls["n"] == 0
        manager.set_session("7", "ada")
        assert manager.handle_crash_login("7") == "issued"
        assert calls["n"] == 1

    def test_untick_remember_me_deletes_the_file(self, tmp_path, monkeypatch):
        _use_xor_dpapi(monkeypatch)
        manager = security.SecurityManager(base_dir=str(tmp_path))
        assert manager.save_credentials("ada@example.com", PASSWORD) is True
        assert (tmp_path / constants.DPAPI_CREDENTIALS_FILE).exists()
        assert manager.save_credentials("", "") is True
        assert not (tmp_path / constants.DPAPI_CREDENTIALS_FILE).exists()

    def test_concurrent_renew_uses_the_winner_and_skips(self, tmp_path, logger, monkeypatch):
        import threading

        clock = freeze_desk_clock(monkeypatch)
        started = threading.Event()
        release = threading.Event()
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            started.set()
            assert release.wait(2)
            return FakeResponse(200, ok_body(OTHER_TOKEN, employee_id=7, ttl=86400))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        manager.set_session("7", "ada")
        seed_token(manager, employee_id="7", expires_in=60)
        manager._record["expires_at_epoch"] = clock["now"] + 60

        first = {}
        second = {}

        def run_first():
            first["result"] = manager.renew()

        def run_second():
            second["result"] = manager.renew()

        thread = threading.Thread(target=run_first)
        thread.start()
        assert started.wait(2)
        other = threading.Thread(target=run_second)
        other.start()
        time.sleep(0.05)
        release.set()
        thread.join(2)
        other.join(2)
        assert calls["n"] == 1
        assert first["result"].token == OTHER_TOKEN
        assert second["result"].ok
        assert second["result"].token == OTHER_TOKEN
        assert manager.get_upload_token("7") == OTHER_TOKEN

    def test_stale_token_invalid_does_not_clear_the_current_token(self, tmp_path, logger, monkeypatch):
        def handler(url, data, kwargs):
            manager._record = {
                "token": OTHER_TOKEN,
                "employee_id": "7",
                "expires_at_epoch": time.time() + 86400,
            }
            return FakeResponse(401, {"error": "token_invalid"})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: None, notices=[])
        manager.set_session("7", "ada")
        seed_token(manager, employee_id="7", expires_in=30)
        result = manager.maintain()
        assert result.error == "token_invalid"
        assert manager.get_upload_token("7") == OTHER_TOKEN

    def test_local_expiry_ignores_a_clock_that_is_slow_or_fast(self, tmp_path, logger, monkeypatch):
        clock = freeze_desk_clock(monkeypatch)
        local = clock["now"]
        ttl = 86400
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                # Local clock is 2 hours slow, so the server's expires_at is ahead of local+ttl.
                return FakeResponse(200, ok_body(
                    TOKEN,
                    employee_id=7,
                    ttl=ttl,
                    expires_at=local + ttl + 2 * 3600,
                    chain_expires_at=local + ttl + 2 * 3600 + 6 * 86400,
                ))
            return FakeResponse(200, ok_body(OTHER_TOKEN, employee_id=7, ttl=ttl))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        manager.set_session("7", "ada")
        issued = manager.issue("ada", PASSWORD)
        assert issued.ok
        assert manager.snapshot()["expires_at_epoch"] == local + ttl
        clock["now"] = local + ttl - 3600 - 1
        assert manager.maintain().ok
        assert calls["n"] == 1
        clock["now"] = local + ttl - 3600
        assert manager.maintain().token == OTHER_TOKEN
        assert calls["n"] == 2

        fast = make_manager(tmp_path, logger)
        fast_clock = local + 25 * 3600
        clock["now"] = fast_clock
        calls["n"] = 0

        def fast_handler(url, data, kwargs):
            calls["n"] += 1
            return FakeResponse(200, ok_body(
                TOKEN,
                employee_id=4,
                ttl=ttl,
                expires_at=fast_clock + ttl - 25 * 3600,
                chain_expires_at=fast_clock + 7 * 86400,
            ))

        route(monkeypatch, fast_handler)
        fast.set_session("4", "ada")
        assert fast.issue("ada", PASSWORD).ok
        assert fast.snapshot()["expires_at_epoch"] == fast_clock + ttl
        assert fast.get_upload_token("4") == TOKEN
        assert fast.maintain().ok
        assert calls["n"] == 1
        stored = dict(fast._record)
        restarted = make_manager(tmp_path, logger)
        restarted._store._memory = stored
        restarted._record = None
        clock["now"] = fast_clock + 10
        assert restarted.restore_stored("4") is True
        assert restarted.snapshot()["expires_at_epoch"] == stored["issued_at"] + stored["ttl_seconds"]
        assert restarted.get_upload_token("4") == TOKEN

    def test_crash_login_skips_a_recent_or_inflight_issue(self, tmp_path, logger, monkeypatch):
        clock = freeze_desk_clock(monkeypatch)
        calls = {"n": 0}

        def handler(url, data, kwargs):
            calls["n"] += 1
            return FakeResponse(200, ok_body(TOKEN, employee_id=7))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: ("ada", PASSWORD))
        manager.set_session("7", "ada")
        assert manager.issue("ada", PASSWORD).ok
        assert manager.handle_crash_login("7") == "skipped"
        assert calls["n"] == 1
        clock["now"] += constants.DESK_TOKEN_RECENT_ISSUE
        assert manager.handle_crash_login("7") == "skipped"
        clock["now"] += 1
        assert manager.handle_crash_login("7") == "issued"
        assert calls["n"] == 2

        manager._issue_inflight = True
        manager._inflight_employee_id = "7"
        assert manager.handle_crash_login("7") == "skipped"
        assert calls["n"] == 2

    def test_token_expired_without_remember_me_notifies_once(self, tmp_path, logger, monkeypatch):
        notices = []

        def handler(url, data, kwargs):
            return FakeResponse(401, {"error": "token_expired"})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger, loader=lambda: None, notices=notices)
        manager.set_session("7", "ada")
        seed_token(manager, employee_id="7", expires_in=30)
        assert manager.maintain().error == "token_expired"
        assert notices == ["shown"]
        assert manager.get_upload_token() is None
        assert manager.maintain().error == "no_token"
        assert notices == ["shown"]

    def test_logout_during_issue_revokes_the_late_token(self, tmp_path, logger, monkeypatch):
        revoked = []

        def handler(url, data, kwargs):
            if url == constants.DESK_TOKEN_ISSUE_URL:
                manager.clear_local()
                return FakeResponse(200, ok_body(TOKEN, employee_id=7))
            revoked.append(data.get("token"))
            return FakeResponse(200, {"status": "ok"})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        manager.set_session("7", "ada")
        result = manager.issue("ada", PASSWORD)
        assert result.error == "superseded"
        assert manager.get_upload_token("7") is None
        assert revoked == [TOKEN]
        assert TOKEN not in logger.text
        assert PASSWORD not in logger.text

    def test_logout_revokes_a_stored_token_before_deleting_it(self, tmp_path, logger, monkeypatch):
        seen = {}

        def handler(url, data, kwargs):
            seen["token"] = data.get("token")
            seen["still_stored"] = manager._store._memory is not None
            return FakeResponse(200, {"status": "ok"})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        seed_token(manager, employee_id="7")
        manager._record = None
        assert manager.revoke().ok
        assert seen["token"] == TOKEN
        assert seen["still_stored"] is False
        assert manager._store._memory is None
        assert manager.get_upload_token() is None

    def test_failed_renew_save_drops_the_old_disk_token(self, tmp_path, logger, monkeypatch):
        _use_xor_dpapi(monkeypatch)

        def handler(url, data, kwargs):
            if url == constants.DESK_TOKEN_ISSUE_URL:
                return FakeResponse(200, ok_body(TOKEN, employee_id=7))
            return FakeResponse(200, ok_body(OTHER_TOKEN, employee_id=7))

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        manager.set_session("7", "ada")
        assert manager.issue("ada", PASSWORD).ok
        path = tmp_path / constants.DESK_TOKEN_FILE
        assert path.exists()
        manager._record["expires_at_epoch"] = time.time() + 30

        def fail_protect(data):
            raise OSError("disk full")

        monkeypatch.setattr(dpapi, "protect", fail_protect)
        assert manager.renew().ok
        assert not path.exists()
        assert manager.get_upload_token("7") == OTHER_TOKEN

    def test_server_error_text_is_not_logged(self, tmp_path, logger, monkeypatch):
        secret = "db password for ada@example.com failed"

        def handler(url, data, kwargs):
            return FakeResponse(500, {"error": secret})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        assert manager.issue("ada", PASSWORD).error == secret
        assert secret not in logger.text
        assert "ada@example.com" not in logger.text
        assert "error=other" in logger.text
        assert "status=500" in logger.text

    def test_migration_verifies_before_deleting_legacy(self, tmp_path, monkeypatch):
        _use_xor_dpapi(monkeypatch)
        _write_legacy(tmp_path, "ada@example.com", PASSWORD)
        real_open = open
        reads = {"n": 0}

        def guarded(path, mode="r", *args, **kwargs):
            name = str(path)
            if name.endswith(constants.DPAPI_CREDENTIALS_FILE) and "r" in mode:
                reads["n"] += 1
                raise PermissionError("locked")
            return real_open(path, mode, *args, **kwargs)

        monkeypatch.setattr("builtins.open", guarded)
        manager = security.SecurityManager(base_dir=str(tmp_path))
        loaded = manager.load_credentials()
        assert loaded["password"] == PASSWORD
        assert (tmp_path / constants.KEY_FILE).exists()
        assert (tmp_path / constants.DATA_FILE).exists()
        assert (tmp_path / constants.DPAPI_CREDENTIALS_FILE).exists()
        assert reads["n"] >= 1

    def test_definite_decrypt_failure_deletes_only_the_dpapi_file(self, tmp_path, monkeypatch):
        _use_xor_dpapi(monkeypatch)
        manager = security.SecurityManager(base_dir=str(tmp_path))
        assert manager.save_credentials("ada@example.com", PASSWORD) is True
        path = tmp_path / constants.DPAPI_CREDENTIALS_FILE
        assert path.exists()

        def broken(data):
            raise dpapi.DpapiError("CryptUnprotectData failed (winerror=13)", winerror=13)

        monkeypatch.setattr(dpapi, "unprotect_status", broken)
        assert manager.load_credentials() is None
        assert not path.exists()

    def test_retry_after_http_date(self, tmp_path, logger, monkeypatch):
        from email.utils import formatdate

        clock = freeze_desk_clock(monkeypatch)
        when = formatdate(clock["now"] + 30, usegmt=True)

        def handler(url, data, kwargs):
            return FakeResponse(429, {"error": "rate_limited"}, headers={"Retry-After": when})

        route(monkeypatch, handler)
        manager = make_manager(tmp_path, logger)
        result = manager.issue("ada", PASSWORD)
        assert result.error == "rate_limited"
        assert abs(result.retry_after - 30) < 1.5

    def test_entropy_is_used_for_new_blobs_and_legacy_blobs_still_open(self, monkeypatch):
        calls = []

        def fake_unprotect(data, entropy):
            calls.append(entropy)
            if entropy is not None:
                raise dpapi.DpapiError(
                    "no entropy on this blob",
                    winerror=dpapi.ERROR_INVALID_DATA,
                )
            return b"plain"

        def fake_protect(data, entropy):
            calls.append(("protect", entropy))
            return b"cipher"

        monkeypatch.setattr(dpapi, "is_available", lambda: True)
        monkeypatch.setattr(dpapi, "_unprotect_windows", fake_unprotect)
        monkeypatch.setattr(dpapi, "_protect_windows", fake_protect)
        plain, legacy = dpapi.unprotect_status(b"blob")
        assert plain == b"plain"
        assert legacy is True
        assert dpapi.protect(b"x") == b"cipher"
        assert calls[0] == dpapi.APP_ENTROPY
        assert calls[1] is None
        assert calls[2] == ("protect", dpapi.APP_ENTROPY)

    def test_transient_dpapi_error_does_not_retry_or_delete(self, tmp_path, monkeypatch):
        real_status = dpapi.unprotect_status
        _use_xor_dpapi(monkeypatch)
        manager = security.SecurityManager(base_dir=str(tmp_path))
        assert manager.save_credentials("ada@example.com", PASSWORD) is True
        path = tmp_path / constants.DPAPI_CREDENTIALS_FILE
        calls = []

        def fake_unprotect(data, entropy):
            calls.append(entropy)
            if entropy is not None:
                raise dpapi.DpapiError("CryptUnprotectData failed (winerror=1722)", winerror=1722)
            raise dpapi.DpapiError("CryptUnprotectData failed (winerror=13)", winerror=13)

        monkeypatch.setattr(dpapi, "unprotect_status", real_status)
        monkeypatch.setattr(dpapi, "is_available", lambda: True)
        monkeypatch.setattr(dpapi, "_unprotect_windows", fake_unprotect)
        assert manager.load_credentials() is None
        assert calls == [dpapi.APP_ENTROPY]
        assert path.exists()

    def test_non_finite_retry_after_uses_the_default(self, tmp_path, logger, monkeypatch):
        route(monkeypatch, lambda url, data, kwargs: FakeResponse(
            429, {"error": "rate_limited"}, headers={"Retry-After": "nan"}
        ))
        manager = make_manager(tmp_path, logger)
        result = manager.issue("ada", PASSWORD)
        assert result.error == "rate_limited"
        assert result.retry_after == 60

        route(monkeypatch, lambda url, data, kwargs: FakeResponse(
            503, {"error": "busy"}, headers={"Retry-After": "inf"}
        ))
        manager._blocked_until = 0
        busy = manager.issue("ada", PASSWORD)
        assert busy.error == "busy"
        assert busy.retry_after == 30

    def test_503_busy_honours_retry_after_without_backoff_or_notice(
        self, tmp_path, logger, monkeypatch
    ):
        from email.utils import formatdate

        clock = freeze_desk_clock(monkeypatch)
        start = clock["now"]
        notices = []
        calls = []

        def handler(url, data, kwargs):
            calls.append(url)
            if len(calls) == 1:
                return FakeResponse(503, {"error": "busy"}, headers={"Retry-After": "45"})
            if len(calls) == 2:
                when = formatdate(clock["now"] + 20, usegmt=True)
                return FakeResponse(503, {"error": "busy"}, headers={"Retry-After": when})
            return FakeResponse(503, {"error": "busy"})

        route(monkeypatch, handler)
        manager = make_manager(
            tmp_path, logger, loader=lambda: ("ada", PASSWORD), notices=notices
        )
        manager.set_session("7", "ada")

        issued = manager.issue("ada", PASSWORD)
        assert issued.error == "busy"
        assert issued.status_code == 503
        assert issued.retry_after == 45
        assert manager.issue("ada", PASSWORD).error == "rate_limited"
        assert calls == [constants.DESK_TOKEN_ISSUE_URL]
        assert manager._failure_blocked_until == 0
        assert manager._failure_backoff_seconds == 0
        assert notices == []
        assert "error=busy" in logger.text
        assert "sign in" not in logger.text.lower()

        clock["now"] = start + 45
        again = manager.issue("ada", PASSWORD)
        assert again.error == "busy"
        assert abs(again.retry_after - 20) < 1.5
        assert len(calls) == 2
        clock["now"] = start + 45 + 19
        assert manager.issue("ada", PASSWORD).error == "rate_limited"
        assert len(calls) == 2

        clock["now"] = start + 45 + 20
        missing = manager.issue("ada", PASSWORD)
        assert missing.error == "busy"
        assert missing.retry_after == 30
        assert len(calls) == 3
        assert manager._failure_backoff_seconds == 0
        assert notices == []

        seed_token(manager, expires_in=30)
        manager._record["expires_at_epoch"] = clock["now"] + 30
        manager._blocked_until = 0

        def renew_busy(url, data, kwargs):
            calls.append(url)
            assert "password" not in data
            return FakeResponse(503, {"error": "busy"}, headers={"Retry-After": "12"})

        route(monkeypatch, renew_busy)
        renewed = manager.maintain()
        assert renewed.error == "busy"
        assert renewed.retry_after == 12
        assert calls[-1] == constants.DESK_TOKEN_RENEW_URL
        assert manager.maintain().error == "rate_limited"
        assert calls.count(constants.DESK_TOKEN_RENEW_URL) == 1
        assert constants.DESK_TOKEN_ISSUE_URL not in calls[3:]
        assert notices == []
        assert PASSWORD not in logger.text

    def test_upload_guard_is_six_megabytes_and_size_reject_retries_under_three(
        self, tmp_path, logger, monkeypatch
    ):
        pytest.importorskip("PIL")
        from PIL import Image

        assert screenshot.MAX_UPLOAD_BASE64_CHARS == 6 * 1024 * 1024
        assert screenshot.SIZE_RETRY_BASE64_CHARS == 3 * 1024 * 1024

        image = _noise_image(80, 60, seed=3)
        png_b64 = _png_b64(image)
        tiny = image.resize((8, 6))
        tiny_len = len(_encode_jpeg_base64(tiny, JPEG_FALLBACK_QUALITY))
        monkeypatch.setattr(screenshot, "SIZE_RETRY_BASE64_CHARS", tiny_len)
        posted = []

        def handler(url, data, kwargs):
            posted.append(dict(data))
            if len(posted) == 1:
                return FakeResponse(413, {"error": "too_large"})
            return FakeResponse(200, {})

        route(monkeypatch, handler)
        manager = ScreenshotManager(logger=logger, token_manager=self_manager(tmp_path, logger))
        assert manager.upload("42", base64_data=png_b64) is True
        assert len(posted) == 2
        assert posted[0]["format"] == "PNG"
        assert posted[1]["format"] == "JPEG"
        assert len(posted[1]["file"]) <= tiny_len
        assert len(posted[1]["file"]) < len(posted[0]["file"])
        decoded = Image.open(BytesIO(base64.b64decode(posted[1]["file"])))
        assert decoded.size[0] < image.size[0]
        assert decoded.size[1] < image.size[1]
        assert png_b64 not in logger.text

        for code in ("too_large", "payload_too_large", "file_too_large"):
            posted.clear()

            def reject_size(url, data, kwargs, code=code):
                posted.append(dict(data))
                if len(posted) == 1:
                    return FakeResponse(400, {"error": code})
                return FakeResponse(200, {})

            route(monkeypatch, reject_size)
            assert manager.upload("42", base64_data=png_b64) is True
            assert len(posted) == 2
            assert posted[0]["format"] == "PNG"
            assert posted[1]["format"] == "JPEG"
            assert len(posted[1]["file"]) <= tiny_len

        posted.clear()

        def reject_plain_400(url, data, kwargs):
            posted.append(dict(data))
            return FakeResponse(400, {"error": "bad_request"})

        route(monkeypatch, reject_plain_400)
        assert manager.upload("42", base64_data=png_b64) is False
        assert len(posted) == 1
        assert posted[0]["format"] == "PNG"

        posted.clear()

        def keep_rejecting(url, data, kwargs):
            posted.append(dict(data))
            return FakeResponse(413, {})

        route(monkeypatch, keep_rejecting)
        assert manager.upload("42", base64_data=png_b64) is False
        assert len(posted) == 2
        assert posted[1]["format"] == "JPEG"

    def test_downscale_gives_up_and_still_sends(self, tmp_path, logger, monkeypatch):
        pytest.importorskip("PIL")
        image = _noise_image(64, 48, seed=4)
        png_b64 = _png_b64(image)
        monkeypatch.setattr(screenshot, "MAX_UPLOAD_BASE64_CHARS", 1)
        monkeypatch.setattr(screenshot, "MAX_DOWNSCALE_STEPS", 4)
        posted = _capture_upload(monkeypatch)
        manager = ScreenshotManager(logger=logger, token_manager=self_manager(tmp_path, logger))
        assert manager.upload("42", base64_data=png_b64) is True
        assert posted[0]["format"] == "JPEG"
        assert len(posted[0]["file"]) > 1
        assert "smallest" in logger.text

    def test_take_screenshot_and_queue_call_upload(self, tmp_path, logger, monkeypatch):
        called = []

        def fake_upload(self, user_id, *args, **kwargs):
            called.append(user_id)
            return True

        monkeypatch.setattr(screenshot.time, "sleep", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(ScreenshotManager, "upload", fake_upload)
        monkeypatch.setattr(screenshot, "_screenshot_manager", None)
        assert screenshot.take_screenshot("7") is True
        deadline = time.time() + 2
        while called != ["7"] and time.time() < deadline:
            time.sleep(0.02)
        assert called == ["7"]

        manager = screenshot.get_screenshot_manager()
        manager.queue_upload("9")
        deadline = time.time() + 2
        while called != ["7", "9"] and time.time() < deadline:
            time.sleep(0.02)
        assert called == ["7", "9"]
        manager.stop()


def self_manager(tmp_path, logger):
    return make_manager(tmp_path, logger)


def _write_legacy(directory: Path, email: str, password: str) -> None:
    key = Fernet.generate_key()
    encrypted = Fernet(key).encrypt(password.encode("utf-8")).decode("ascii")
    (directory / constants.KEY_FILE).write_bytes(key)
    (directory / constants.DATA_FILE).write_text(
        json.dumps({"email": email, "password": encrypted}),
        encoding="utf-8",
    )
