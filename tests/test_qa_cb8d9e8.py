"""QA extra tests written for PR #2 @ cb8d9e8 (new head). Not part of the repo.

A failing test maps to a finding in review-cb8d9e8.md (FINDING tag in docstring)."""
import base64
import json
import logging
import os
import threading
import time
import types
from io import BytesIO

import pytest
import requests

from src.config import constants
from src.utils import desk_token, screenshot, security
from src.utils.screenshot import ScreenshotManager

from qa_helpers import (
    FakeResponse, ListLogger, PASSWORD, TOKEN_A, TOKEN_A2, TOKEN_B,
    make_manager, ok_body, route, seed, use_xor_dpapi,
)

USER_A, EID_A = "user.a@example.com", "100"
USER_B, EID_B = "user.b@example.com", "200"
PW_A, PW_B = "Pw-A-&<>-111", "Pw-B-&<>-222"


@pytest.fixture(autouse=True)
def _no_real_http(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("unexpected real HTTP")
    monkeypatch.setattr(requests, "post", boom)


@pytest.fixture
def logger():
    return ListLogger()


def _png_b64(w=64, h=48, seed=1):
    import random
    from PIL import Image
    rng = random.Random(seed)
    img = Image.frombytes("RGB", (w, h), bytes(rng.randrange(256) for _ in range(w * h * 3)))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ============================================================ CRITICAL regression

def test_module_take_screenshot_async_path_works(monkeypatch):
    """FINDING C1: cb8d9e8 inserted module-level _size_rejected() above upload_async,
    queue_upload, _start_queue_processor and stop, which are now nested (dead) code inside
    that function. ScreenshotManager.upload_async no longer exists, so the app's only
    screenshot path (main._take_screenshot -> screenshot.take_screenshot(user)) raises
    AttributeError and no screenshot is ever uploaded."""
    called = []
    monkeypatch.setattr(ScreenshotManager, "upload", lambda self, uid, *a, **k: called.append(uid) or True)
    monkeypatch.setattr(screenshot, "_screenshot_manager", None)
    assert screenshot.take_screenshot("7") is True
    time.sleep(0.2)
    assert called == ["7"]


def test_main_take_screenshot_reaches_upload(monkeypatch):
    """FINDING C1 through the real app entry (WorkTreApp._take_screenshot)."""
    from src import main as m
    app = m.WorkTreApp.__new__(m.WorkTreApp)
    app.state = m.AppState()
    app.state.current_user = "7"
    errors = []
    app.logger = types.SimpleNamespace(error=errors.append, info=lambda *a: None)
    app.lazy = types.SimpleNamespace(get_screenshot=lambda: screenshot)
    called = []
    monkeypatch.setattr(ScreenshotManager, "upload", lambda self, uid, *a, **k: called.append(uid) or True)
    monkeypatch.setattr(screenshot, "_screenshot_manager", None)
    app._take_screenshot()
    time.sleep(0.5)
    assert not errors, errors
    assert called == ["7"]


# ============================================================ H2 employee switch

def _server(log, eids={USER_A: EID_A, USER_B: EID_B}, slow_revoke=None):
    tokens = {USER_A: TOKEN_A, USER_B: TOKEN_B}

    def handler(url, data, kw):
        log.append((url.rsplit("/", 1)[-1].split("?")[0], dict(data)))
        if url == constants.DESK_TOKEN_ISSUE_URL:
            return FakeResponse(200, ok_body(tokens[data["username"]], employee_id=eids[data["username"]]))
        if url == constants.DESK_TOKEN_REVOKE_URL:
            if slow_revoke:
                slow_revoke()
            return FakeResponse(200, {"status": "ok"})
        if url == constants.DESK_TOKEN_RENEW_URL:
            return FakeResponse(200, ok_body(TOKEN_A2, employee_id=EID_A))
        return FakeResponse(200, {})  # ss_upload
    return handler


def test_switch_a_logout_b_login_without_remember_me(tmp_path, logger, monkeypatch):
    """A signs in with Remember me, logs out; B signs in (Remember me unticked) on the
    same OS user / same token manager. A's token never accompanies B's upload."""
    use_xor_dpapi(monkeypatch)
    sm = security.SecurityManager(base_dir=str(tmp_path))
    log = []
    route(monkeypatch, _server(log))
    tm = make_manager(tmp_path, logger, loader=lambda: (lambda c: (c["email"], c["password"]) if c else None)(sm.load_credentials()))
    # A: main.js saves creds, login() -> set_session + issue
    assert sm.save_credentials(USER_A, PW_A)
    tm.set_session(EID_A, USER_A)
    assert tm.issue(USER_A, PW_A, reset_rejection=True, ignore_backoff=True).ok
    assert tm.get_upload_token(EID_A) == TOKEN_A
    tm.revoke()  # logout
    assert tm.get_upload_token(EID_A) is None
    # B: Remember me unticked -> save_remembered_user("", "") -> clear
    sm.save_credentials("", "")
    assert sm.load_credentials() is None
    tm.set_session(EID_B, USER_B)
    assert tm.issue(USER_B, PW_B, reset_rejection=True, ignore_backoff=True).ok
    assert tm.handle_crash_login(EID_B) == "skipped"  # AlreadyLogin crashlogin right after
    ScreenshotManager(logger=logger, token_manager=tm).upload(EID_B, base64_data="abc")
    uploads = [d for (k, d) in log if k == "index"]
    assert uploads and uploads[-1].get("token") == TOKEN_B
    assert all(d.get("token") != TOKEN_A for (k, d) in log if k in ("index", "renew"))
    # A's token never used after logout for anything but revoke
    after_logout = log[[i for i, (k, _) in enumerate(log) if k == "revoke"][0] + 1:]
    assert all(TOKEN_A not in json.dumps(d) for (_, d) in after_logout)


def test_switch_b_with_saved_password_of_a_never_issues_with_a(tmp_path, logger, monkeypatch):
    use_xor_dpapi(monkeypatch)
    log = []
    route(monkeypatch, _server(log))
    tm = make_manager(tmp_path, logger, loader=lambda: (USER_A, PW_A))  # A's Remember me left behind
    tm.set_session(EID_B, USER_B)
    assert tm.handle_crash_login(EID_B) in ("none", "skipped")
    tm.maintain()
    assert tm.recover_after_rejected_token(EID_B) is None
    assert not any(d.get("username") == USER_A for (_, d) in log)
    assert tm.get_upload_token(EID_B) is None


def test_issue_with_mismatched_employee_is_not_stored(tmp_path, logger, monkeypatch):
    use_xor_dpapi(monkeypatch)
    log = []
    route(monkeypatch, _server(log, eids={USER_A: EID_A, USER_B: EID_A}))  # server says B's creds -> EID A
    tm = make_manager(tmp_path, logger)
    tm.set_session(EID_B, USER_B)
    res = tm.issue(USER_B, PW_B, reset_rejection=True, ignore_backoff=True)
    assert res.error == "employee_mismatch"
    assert tm.get_upload_token(EID_B) is None and tm.get_upload_token() is None
    assert not os.path.exists(tm._store.path)


def test_upload_userid_mismatch_sends_no_token(tmp_path, logger, monkeypatch):
    use_xor_dpapi(monkeypatch)
    log = []
    route(monkeypatch, _server(log))
    tm = make_manager(tmp_path, logger)
    seed(tm, employee_id=EID_A)
    ScreenshotManager(logger=logger, token_manager=tm).upload(EID_B, base64_data="abc")
    assert "token" not in [d for (k, d) in log if k == "index"][0]


def test_b_login_while_a_revoke_in_flight_keeps_b_token(tmp_path, logger, monkeypatch):
    """FINDING N3: revoke() clears the local record only after the network revoke returns.
    If B's issue is on the wire when A's revoke returns, the generation bump marks B's fresh
    token 'superseded' and revokes it: B works the whole session without a token (silently,
    no notice, when Remember me is off)."""
    use_xor_dpapi(monkeypatch)
    issue_on_wire, revoke_may_return = threading.Event(), threading.Event()
    log = []

    def handler(url, data, kw):
        log.append((url.rsplit("/", 1)[-1], dict(data)))
        if url == constants.DESK_TOKEN_REVOKE_URL:
            if data.get("token") == TOKEN_A:
                assert issue_on_wire.wait(5)
            return FakeResponse(200, {"status": "ok"})
        if url == constants.DESK_TOKEN_ISSUE_URL:
            issue_on_wire.set()
            assert revoke_may_return.wait(5)
            return FakeResponse(200, ok_body(TOKEN_B, employee_id=EID_B))
        raise AssertionError(url)

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    tm.set_session(EID_A, USER_A)
    seed(tm, employee_id=EID_A)
    rv = threading.Thread(target=tm.revoke)  # A logs out (revoke_async)
    rv.start()
    tm.set_session(EID_B, USER_B)            # B signs in a moment later
    iss = threading.Thread(target=tm.issue, args=(USER_B, PW_B), kwargs=dict(reset_rejection=True, ignore_backoff=True))
    iss.start()
    rv.join(5)
    revoke_may_return.set()
    iss.join(5)
    assert tm.get_upload_token(EID_B) == TOKEN_B, f"B lost its token: {[k for k, _ in log]}"


# ============================================================ L1/L2 logout

def test_renew_completing_during_revoke_does_not_survive_logout(tmp_path, logger, monkeypatch):
    """FINDING L1 (partial): revoke() only clears locally after the network call, and only
    if the record still holds the revoked token. A keep-alive renew that lands while the
    revoke is on the wire stores A2, and A2 survives logout in memory and on disk."""
    use_xor_dpapi(monkeypatch)
    revoke_entered, renew_done = threading.Event(), threading.Event()

    def handler(url, data, kw):
        if url == constants.DESK_TOKEN_REVOKE_URL:
            revoke_entered.set()
            renew_done.wait(5)
            return FakeResponse(200, {"status": "ok"})
        if url == constants.DESK_TOKEN_RENEW_URL:
            return FakeResponse(200, ok_body(TOKEN_A2, employee_id="7"))
        raise AssertionError(url)

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    tm.set_session("7", USERNAME_PLACEHOLDER)
    seed(tm, expires_in=600)  # inside renew window
    rv = threading.Thread(target=tm.revoke)
    rv.start()
    assert revoke_entered.wait(5)
    tm.maintain()       # keep-alive worker spawned just before logout
    renew_done.set()
    rv.join(5)
    assert tm.get_upload_token() is None, "renewed token survived logout"
    assert not os.path.exists(tm._store.path)


USERNAME_PLACEHOLDER = "qa.user.a@example.com"


def test_logout_while_busy_hold_still_deletes_token(tmp_path, logger, monkeypatch):
    """FINDING N2 (behaviour change vs caabfbd, documented as intended in the PR body):
    revoke() returns early when a 429/503 hold is active and never clears the local token,
    so the token stays in memory and desk_token.dpapi survives logout."""
    use_xor_dpapi(monkeypatch)
    calls = []

    def handler(url, data, kw):
        calls.append(url)
        if url == constants.DESK_TOKEN_RENEW_URL:
            return FakeResponse(503, {"status": "error", "error": "busy"}, headers={"Retry-After": "30"})
        return FakeResponse(200, {"status": "ok"})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    seed(tm, expires_in=600)
    assert tm.maintain().error == "busy"
    tm.revoke()  # user logs out within the 30 s busy window
    assert tm.get_upload_token() is None
    assert not os.path.exists(tm._store.path)


# ============================================================ 503 busy contract

@pytest.mark.parametrize("retry_after,expect", [("45", 45), (None, 30), ("http-date", 90)])
def test_503_busy_holds_retry_after_without_backoff_or_notice(tmp_path, logger, monkeypatch, retry_after, expect):
    clock = {"now": 1_800_000_000.0}
    monkeypatch.setattr(desk_token.time, "time", lambda: clock["now"])
    notices, calls = [], []
    headers = {}
    if retry_after == "http-date":
        from email.utils import formatdate
        headers["Retry-After"] = formatdate(clock["now"] + 90, usegmt=True)
    elif retry_after:
        headers["Retry-After"] = retry_after

    def handler(url, data, kw):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(503, {"status": "error", "error": "busy"}, headers=headers)
        return FakeResponse(200, ok_body(TOKEN_A2, employee_id="7", now=clock["now"]))

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: ("qa.user.a@example.com", PASSWORD), notices=notices)
    tm.set_session("7", "qa.user.a@example.com")
    with tm._lock:
        tm._record = {"token": TOKEN_A, "employee_id": "7", "issued_at": clock["now"] - 86000,
                      "ttl_seconds": 86400, "expires_at_epoch": clock["now"] + 400}
    assert tm.maintain().error == "busy"
    assert tm._failure_backoff_seconds == 0 and tm._failure_blocked_until == 0
    assert tm.get_upload_token("7") == TOKEN_A  # token kept
    clock["now"] += expect - 1
    assert tm.maintain().error == "rate_limited"
    assert tm.recover_after_rejected_token("7") is None
    assert tm.issue("qa.user.a@example.com", PASSWORD, reset_rejection=True, ignore_backoff=True).error == "rate_limited"
    assert len(calls) == 1
    clock["now"] += 2
    assert tm.maintain().ok
    assert len(calls) == 2 and notices == []


def test_503_without_busy_code_is_outage_backoff(tmp_path, logger, monkeypatch):
    route(monkeypatch, lambda u, d, k: FakeResponse(503, {}))
    tm = make_manager(tmp_path, logger)
    res = tm.issue("u", "p")
    assert res.error == "server_error" and tm._failure_backoff_seconds > 0


# ============================================================ upload size contract

def _upload_server(statuses, posts):
    it = iter(statuses)

    def handler(url, data, kw):
        if "/desktoken/" in url:
            return FakeResponse(503, {"status": "error", "error": "busy"})
        posts.append(dict(data))
        status, body = next(it, (413, {"status": "error", "error": "too_large"}))
        return FakeResponse(status, body)
    return handler


@pytest.mark.parametrize("statuses,expect_posts,ok", [
    ([(413, {"status": "error", "error": "too_large"}), (200, {})], 2, True),
    ([(413, {"status": "error", "error": "too_large"})] * 5, 2, False),
    ([(413, {})] * 5, 2, False),
    ([(400, {"status": "error", "error": "too_large"})] * 5, 2, False),
    ([(400, {"status": "error", "error": "payload_too_large"}), (200, {})], 2, True),
    ([(400, {"status": "error", "error": "bad_request"})] * 5, 1, False),
    ([(400, {})] * 5, 1, False),
    ([(500, {})] * 5, 1, False),
    ([(401, {"error": "token_invalid"}), (413, {"error": "too_large"}), (413, {"error": "too_large"})], 3, False),
    ([(413, {"error": "too_large"}), (401, {"error": "token_invalid"})], 2, False),
])
def test_size_reject_single_retry_no_loop(tmp_path, logger, monkeypatch, statuses, expect_posts, ok):
    posts = []
    route(monkeypatch, _upload_server(statuses, posts))
    tm = make_manager(tmp_path, logger)
    seed(tm)
    b64 = _png_b64(200, 150)
    res = ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data=b64)
    assert res is ok and len(posts) == expect_posts
    if expect_posts >= 2 and statuses[0][0] in (413, 400):
        assert posts[1]["format"] == "JPEG" and len(posts[1]["file"]) <= screenshot.SIZE_RETRY_BASE64_CHARS


def test_size_retry_on_undecodable_payload_does_not_retry(tmp_path, logger, monkeypatch):
    posts = []
    route(monkeypatch, _upload_server([(413, {"error": "too_large"})] * 3, posts))
    tm = make_manager(tmp_path, logger)
    assert ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data="abc") is False
    assert len(posts) == 1


def test_pre_upload_jpeg_switch_at_6mb(tmp_path, logger, monkeypatch):
    assert screenshot.MAX_UPLOAD_BASE64_CHARS == 6 * 1024 * 1024
    assert screenshot.SIZE_RETRY_BASE64_CHARS == 3 * 1024 * 1024
    b64 = _png_b64(120, 90)
    monkeypatch.setattr(screenshot, "MAX_UPLOAD_BASE64_CHARS", len(b64) - 1)
    posts = []
    route(monkeypatch, _upload_server([(200, {})], posts))
    tm = make_manager(tmp_path, logger)
    assert ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data=b64)
    assert posts[0]["format"] == "JPEG"


def test_png_at_exactly_limit_stays_png(tmp_path, logger, monkeypatch):
    b64 = _png_b64(40, 30)
    monkeypatch.setattr(screenshot, "MAX_UPLOAD_BASE64_CHARS", len(b64))
    posts = []
    route(monkeypatch, _upload_server([(200, {})], posts))
    assert ScreenshotManager(logger=logger, token_manager=make_manager(tmp_path, logger)).upload("7", base64_data=b64)
    assert posts[0]["format"] == "PNG"


# ============================================================ M3/M4/L4/L5 spot checks

def test_crash_login_skips_when_token_issued_under_3_min(tmp_path, logger, monkeypatch):
    use_xor_dpapi(monkeypatch)
    issued = []
    route(monkeypatch, lambda u, d, k: issued.append(u) or FakeResponse(200, ok_body(TOKEN_A, employee_id="7")))
    tm = make_manager(tmp_path, logger, loader=lambda: (USER_A, PW_A))
    tm.set_session("7", USER_A)
    tm.issue(USER_A, PW_A, reset_rejection=True, ignore_backoff=True)
    assert tm.handle_crash_login("7") == "skipped"
    assert len(issued) == 1
    with tm._lock:
        tm._record["issued_at"] -= 181
    assert tm.handle_crash_login("7") == "issued"
    assert len(issued) == 2


def test_crash_login_skips_while_issue_in_flight(tmp_path, logger, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    issued = []

    def handler(u, d, k):
        issued.append(u)
        entered.set()
        release.wait(5)
        return FakeResponse(200, ok_body(TOKEN_A, employee_id="7"))

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USER_A, PW_A))
    tm.set_session("7", USER_A)
    tm.issue_async(USER_A, PW_A, reset_rejection=True, ignore_backoff=True)
    assert entered.wait(5)
    assert tm.handle_crash_login("7") == "skipped"
    release.set()
    time.sleep(0.2)
    assert len(issued) == 1


@pytest.mark.parametrize("code", ["token_expired", "token_invalid", "reauth_required"])
def test_notice_when_token_dies_without_remember_me(tmp_path, logger, monkeypatch, code):
    notices = []
    route(monkeypatch, lambda u, d, k: FakeResponse(401, {"error": code}))
    tm = make_manager(tmp_path, logger, notices=notices)
    tm.set_session("7", USER_A)
    seed(tm, expires_in=600)
    tm.maintain()
    tm.maintain()
    assert notices == ["shown"] and tm.get_upload_token() is None


def test_stale_token_invalid_does_not_clear_newer_token(tmp_path, logger, monkeypatch):
    tm = make_manager(tmp_path, logger)
    seed(tm, token=TOKEN_A2)
    tm._reject_current_token(TOKEN_A, "token_invalid")
    assert tm.get_upload_token() == TOKEN_A2


def test_no_username_password_token_in_any_log_full_session(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    use_xor_dpapi(monkeypatch)
    logger = ListLogger()
    n = {"i": 0}

    def handler(url, data, kw):
        n["i"] += 1
        echo = f"{data.get('username')} {data.get('password')} {data.get('token')}"
        seq = [FakeResponse(503, {"error": echo}), FakeResponse(400, {"error": echo}),
               FakeResponse(401, {"error": echo, "code": echo}), FakeResponse(200, ok_body(TOKEN_A, employee_id="7"))]
        return seq[n["i"] % 4]

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USER_A, PW_A))
    tm.set_session("7", USER_A)
    for _ in range(4):
        tm.issue(USER_A, PW_A, reset_rejection=True, ignore_backoff=True)
        tm._reset_failure_backoff_locked()
        tm.maintain()
        ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data="abc")
    tm.revoke()
    out = capsys.readouterr()
    text = "\n".join([logger.text, caplog.text, out.out, out.err])
    for secret in (USER_A, PW_A, TOKEN_A):
        assert secret not in text, secret
