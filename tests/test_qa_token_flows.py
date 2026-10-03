"""QA extra tests: retry rule, logout races, account switch, backoff, clock skew.

Tests assert the behaviour the PR claims / the review expects. A failure here
maps to a finding in review-caabfbd.md (see the FINDING tag in each docstring).
"""
import os
import threading
import time

import pytest
import requests

from src.config import constants
from src.utils import desk_token
from src.utils.screenshot import ScreenshotManager

from qa_helpers import (
    FakeResponse, ListLogger, PASSWORD, TOKEN_A, TOKEN_A2, TOKEN_B, USERNAME,
    make_manager, ok_body, route, seed, use_xor_dpapi,
)


@pytest.fixture(autouse=True)
def _no_real_http(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("unexpected real HTTP")
    monkeypatch.setattr(requests, "post", boom)


@pytest.fixture
def logger():
    return ListLogger()


# ---------------------------------------------------------------- 401 retry rule

def test_upload_401_retries_exactly_once_even_if_server_keeps_rejecting(tmp_path, logger, monkeypatch):
    calls = {"upload": 0, "renew": 0, "issue": 0}

    def handler(url, data, kw):
        if url == constants.DESK_TOKEN_RENEW_URL:
            calls["renew"] += 1
            return FakeResponse(200, ok_body(TOKEN_A2 if calls["renew"] == 1 else TOKEN_B))
        if url == constants.DESK_TOKEN_ISSUE_URL:
            calls["issue"] += 1
            return FakeResponse(200, ok_body(TOKEN_B))
        calls["upload"] += 1
        return FakeResponse(401, {"error": "token_invalid"})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USERNAME, PASSWORD))
    seed(tm)
    assert ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data="abc") is False
    assert calls == {"upload": 2, "renew": 1, "issue": 0}


def test_upload_401_other_code_is_not_retried(tmp_path, logger, monkeypatch):
    calls = []

    def handler(url, data, kw):
        calls.append(url)
        return FakeResponse(401, {"error": "forbidden"})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    seed(tm)
    assert ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data="abc") is False
    assert len(calls) == 1


def test_upload_401_with_refresh_failing_retries_once_tokenless(tmp_path, logger, monkeypatch):
    uploads = []

    def handler(url, data, kw):
        if "/desktoken/" in url:
            return FakeResponse(503, {})
        uploads.append(dict(data))
        return FakeResponse(401, {"error": "token_expired"})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    seed(tm)
    assert ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data="abc") is False
    assert len(uploads) == 2 and "token" not in uploads[1]


# ---------------------------------------------------------------- logout races

def test_logout_during_inflight_issue_leaves_no_token(tmp_path, logger, monkeypatch):
    use_xor_dpapi(monkeypatch)
    entered, release = threading.Event(), threading.Event()

    def handler(url, data, kw):
        if url == constants.DESK_TOKEN_ISSUE_URL:
            entered.set()
            release.wait(5)
            return FakeResponse(200, ok_body(TOKEN_A))
        return FakeResponse(200, {"status": "ok"})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    tm.set_employee_id("7")
    tm.issue_async(USERNAME, PASSWORD, reset_rejection=True, ignore_backoff=True)
    assert entered.wait(5)
    tm.revoke()  # logout while issue is on the wire
    release.set()
    time.sleep(0.3)
    assert tm.get_upload_token() is None
    assert not os.path.exists(tm._store.path)


def test_logout_before_issue_thread_captures_generation(tmp_path, logger, monkeypatch):
    """FINDING L-logout-race: generation is captured inside the worker thread, so a
    logout that lands before the worker runs does not cancel it."""
    use_xor_dpapi(monkeypatch)
    route(monkeypatch, lambda url, data, kw: FakeResponse(200, ok_body(TOKEN_A)))
    deferred = []
    real_start = threading.Thread.start

    def defer_start(self):
        if self.name == "desk-token-issue":
            deferred.append(self)
        else:
            real_start(self)

    monkeypatch.setattr(threading.Thread, "start", defer_start)
    tm = make_manager(tmp_path, logger)
    tm.issue_async(USERNAME, PASSWORD, reset_rejection=True, ignore_backoff=True)
    tm.revoke()  # user logs out (or inactivity logout) before the worker is scheduled
    monkeypatch.setattr(threading.Thread, "start", real_start)
    for t in deferred:
        t.start(); t.join(5)
    assert tm.get_upload_token() is None, "token stored after logout"


def test_maintain_after_logout_does_not_issue_from_saved_password(tmp_path, logger, monkeypatch):
    """FINDING L-logout-race: maintain() has no 'signed in' gate; a keep-alive tick that
    races logout re-issues a token from Remember me after the user logged out."""
    use_xor_dpapi(monkeypatch)
    issued = []

    def handler(url, data, kw):
        if url == constants.DESK_TOKEN_ISSUE_URL:
            issued.append(1)
            return FakeResponse(200, ok_body(TOKEN_A))
        return FakeResponse(200, {"status": "ok"})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USERNAME, PASSWORD))
    tm.set_session("7", USERNAME)  # ADAPTATION @cb8d9e8: login() now calls set_session(eid, username)
    seed(tm)
    tm.revoke()
    tm.maintain()  # keep-alive worker that was already spawned when logout happened
    assert issued == [] and tm.get_upload_token() is None


def test_token_file_deleted_on_logout_when_network_down(tmp_path, logger, monkeypatch):
    use_xor_dpapi(monkeypatch)

    def handler(url, data, kw):
        raise requests.exceptions.ConnectionError("offline")

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    seed(tm)
    assert os.path.exists(tm._store.path)
    res = tm.revoke()
    assert res.ok is False
    assert not os.path.exists(tm._store.path)
    assert tm.get_upload_token() is None


def test_token_file_deleted_on_logout_when_rate_limited(tmp_path, logger, monkeypatch):
    use_xor_dpapi(monkeypatch)
    route(monkeypatch, lambda *a: FakeResponse(200, {}))
    tm = make_manager(tmp_path, logger)
    seed(tm)
    tm._blocked_until = time.time() + 600
    tm.revoke()
    assert not os.path.exists(tm._store.path)


def test_logout_after_restart_revokes_disk_token_on_server(tmp_path, logger, monkeypatch):
    """FINDING L-revoke-disk: revoke() only revokes the in-memory token. After a restart
    (token only on disk) logout deletes the file but never tells the server."""
    use_xor_dpapi(monkeypatch)
    revoked = []

    def handler(url, data, kw):
        revoked.append(data.get("token"))
        return FakeResponse(200, {"status": "ok"})

    route(monkeypatch, handler)
    first = make_manager(tmp_path, logger)
    seed(first)
    restarted = make_manager(tmp_path, logger)  # new process, nothing in memory yet
    restarted.revoke()
    assert not os.path.exists(restarted._store.path)
    assert revoked == [TOKEN_A]


# ---------------------------------------------------------------- account switch

def test_disk_token_of_user_a_not_used_for_user_b(tmp_path, logger, monkeypatch):
    use_xor_dpapi(monkeypatch)
    a = make_manager(tmp_path, logger)
    seed(a, employee_id="100")
    b = make_manager(tmp_path, logger)
    b.set_employee_id("200")
    assert b.get_upload_token() is None
    assert b.restore_stored("200") is False


def test_crash_login_for_b_with_saved_password_of_a_does_not_bind_a_token(tmp_path, logger, monkeypatch):
    """FINDING H-account-switch: handle_crash_login() issues with whatever Remember me
    holds; _store_record_locked() then overwrites the active EID with the token's EID, so
    user B's uploads carry user A's token."""
    use_xor_dpapi(monkeypatch)

    def handler(url, data, kw):
        assert data["username"] == "user.a"
        return FakeResponse(200, ok_body(TOKEN_A, employee_id="100"))

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: ("user.a", PASSWORD))
    tm.set_employee_id("200")          # B is the signed-in employee
    tm.handle_crash_login("200")
    assert tm.get_upload_token() is None, "user A's token is offered for user B's upload"


def test_upload_sends_token_only_if_bound_to_upload_userid(tmp_path, logger, monkeypatch):
    """FINDING H-account-switch: ScreenshotManager never compares the token's EID with the
    upload userid."""
    use_xor_dpapi(monkeypatch)
    uploads = []

    def handler(url, data, kw):
        if "/desktoken/" in url:
            return FakeResponse(200, ok_body(TOKEN_A, employee_id="100"))
        uploads.append(dict(data))
        return FakeResponse(200, {})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: ("user.a", PASSWORD))
    tm.set_employee_id("200")
    tm.handle_crash_login("200")
    ScreenshotManager(logger=logger, token_manager=tm).upload("200", base64_data="abc")
    assert "token" not in uploads[0] or uploads[0]["token"] != TOKEN_A


def test_unchecking_remember_me_clears_saved_password(tmp_path, monkeypatch):
    """FINDING H-account-switch (enabler, pre-existing): main.js calls
    save_remembered_user('', '') when Remember me is unchecked, but save_credentials()
    returns False and keeps the previous user's DPAPI file. The token manager then uses
    those stale credentials for crash/recovery/maintain issues."""
    use_xor_dpapi(monkeypatch)
    from src.utils import security
    sm = security.SecurityManager(base_dir=str(tmp_path))
    assert sm.save_credentials("user.a", PASSWORD)
    sm.save_credentials("", "")  # user B signs in with Remember me unchecked
    assert sm.load_credentials() is None


# ---------------------------------------------------------------- AlreadyLogin double issue

def test_login_plus_crashlogin_issues_one_token(tmp_path, logger, monkeypatch):
    """FINDING M-double-issue: main.js always calls crashlogin right after a successful
    AlreadyLogin SOAP login. login() schedules issue_async and crashlogin() schedules
    handle_crash_login(), which issues again with the Remember me password."""
    issued = []
    lock = threading.Lock()

    def handler(url, data, kw):
        with lock:
            issued.append(url)
            n = len(issued)
        return FakeResponse(200, ok_body(TOKEN_A if n == 1 else TOKEN_A2, employee_id="7"))

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USERNAME, PASSWORD))
    tm.set_employee_id("7")
    tm.issue(USERNAME, PASSWORD, reset_rejection=True, ignore_backoff=True)  # from login()
    tm.handle_crash_login("7")                                                # from crashlogin()
    assert len(issued) == 1, f"{len(issued)} tokens issued for one sign-in"


# ---------------------------------------------------------------- concurrent renew

def test_rejected_concurrent_renew_does_not_wipe_newer_token(tmp_path, logger, monkeypatch):
    """FINDING M-renew-race: maintain() and upload recovery can renew the same token at
    once. The loser gets token_invalid (server cancelled the old token) and then calls
    clear_local(), discarding the winner's fresh token."""
    use_xor_dpapi(monkeypatch)
    server = {"valid": {TOKEN_A}}
    lock = threading.Lock()
    loser_waiting = threading.Event()
    winner_done = threading.Event()

    def handler(url, data, kw):
        if url == constants.DESK_TOKEN_RENEW_URL:
            if threading.current_thread().name == "loser":
                loser_waiting.set()
                winner_done.wait(5)
            with lock:
                if data["token"] in server["valid"]:
                    server["valid"] = {TOKEN_A2}
                    return FakeResponse(200, ok_body(TOKEN_A2))
                return FakeResponse(401, {"error": "token_invalid"})
        raise AssertionError(url)

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)  # no Remember me
    seed(tm, expires_in=600)              # inside the 1 h renew window

    loser = threading.Thread(target=tm.recover_after_rejected_token, name="loser")
    loser.start()
    assert loser_waiting.wait(5)
    tm.maintain()          # winner: renews A -> A2 and stores A2
    winner_done.set()
    loser.join(5)
    assert tm.get_upload_token() == TOKEN_A2, "valid renewed token was discarded"


# ---------------------------------------------------------------- backoff / 404 / 429

def test_live_404_one_attempt_then_hour_backoff_without_log_spam(tmp_path, logger, monkeypatch):
    clock = {"now": 1_800_000_000.0}
    monkeypatch.setattr(desk_token.time, "time", lambda: clock["now"])
    calls = []

    def handler(url, data, kw):
        calls.append(url)
        return FakeResponse(404, {})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USERNAME, PASSWORD))
    tm.set_session("7", USERNAME)  # ADAPTATION @cb8d9e8: saved password only used for the signed-in username
    tm.issue(USERNAME, PASSWORD, reset_rejection=True, ignore_backoff=True)  # manual login
    tm.handle_crash_login("7")                                                # AlreadyLogin
    for _ in range(11):                                                       # 55 min of keep-alives
        clock["now"] += 300
        tm.maintain()
    assert len(calls) == 1
    warnings = [m for m in logger.messages if m.startswith(("warning", "error"))]
    assert len(warnings) <= 2, warnings
    clock["now"] += 301  # past one hour
    tm.maintain()
    assert len(calls) == 2
    tm.issue(USERNAME, PASSWORD, reset_rejection=True, ignore_backoff=True)  # manual login always tries
    assert len(calls) == 3


def test_429_retry_after_header_respected(tmp_path, logger, monkeypatch):
    clock = {"now": 1_800_000_000.0}
    monkeypatch.setattr(desk_token.time, "time", lambda: clock["now"])
    calls = []

    def handler(url, data, kw):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(429, {"error": "rate_limited"}, headers={"Retry-After": "120"})
        return FakeResponse(200, ok_body(TOKEN_A, now=clock["now"]))

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USERNAME, PASSWORD))
    tm.set_session("7", USERNAME)  # ADAPTATION @cb8d9e8
    assert tm.issue(USERNAME, PASSWORD).error == "rate_limited"
    clock["now"] += 60
    assert tm.maintain().error == "rate_limited"
    assert tm.issue(USERNAME, PASSWORD, ignore_backoff=True, reset_rejection=True).error == "rate_limited"
    assert len(calls) == 1
    clock["now"] += 61
    assert tm.maintain().ok
    assert len(calls) == 2


# ---------------------------------------------------------------- clock skew

def _skewed(monkeypatch, skew):
    """Server clock = real; local clock = server + skew."""
    clock = {"server": 1_800_000_000.0}
    monkeypatch.setattr(desk_token.time, "time", lambda: clock["server"] + skew)
    return clock


def test_clock_behind_still_renews_before_server_expiry(tmp_path, logger, monkeypatch):
    """FINDING M-clock-skew: expires_at (server absolute) is trusted over ttl_seconds, so a
    PC clock 2 h slow does not renew until after the server has already expired the token."""
    clock = _skewed(monkeypatch, -7200)
    renews = []

    def handler(url, data, kw):
        if url == constants.DESK_TOKEN_ISSUE_URL:
            return FakeResponse(200, ok_body(TOKEN_A, now=clock["server"]))
        renews.append(clock["server"])
        return FakeResponse(200, ok_body(TOKEN_A2, now=clock["server"]))

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    issued_at = clock["server"]
    assert tm.issue(USERNAME, PASSWORD).ok
    while clock["server"] < issued_at + 86400 and not renews:
        clock["server"] += 300
        tm.maintain()
    assert renews and renews[0] < issued_at + 86400, "token expired on the server before renewal"


def test_clock_far_ahead_does_not_renew_every_keepalive(tmp_path, logger, monkeypatch):
    """FINDING M-clock-skew: a PC clock >23 h fast makes every fresh token look inside the
    renew window (or expired), so each 5-min keep-alive renews and uploads go tokenless."""
    clock = _skewed(monkeypatch, 25 * 3600)
    renews = []

    def handler(url, data, kw):
        if url == constants.DESK_TOKEN_RENEW_URL:
            renews.append(1)
        return FakeResponse(200, ok_body(TOKEN_A if not renews else TOKEN_A2, now=clock["server"]))

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger)
    assert tm.issue(USERNAME, PASSWORD).ok
    for _ in range(6):
        clock["server"] += 300
        tm.maintain()
    assert len(renews) <= 1, f"{len(renews)} renews in 30 minutes"
    assert tm.get_upload_token() is not None


# ---------------------------------------------------------------- reauth notice

def test_reauth_required_without_password_notifies_once_and_uploads_continue(tmp_path, logger, monkeypatch):
    notices, uploads = [], []

    def handler(url, data, kw):
        if "/desktoken/" in url:
            return FakeResponse(401, {"error": "reauth_required"})
        uploads.append(dict(data))
        return FakeResponse(200, {})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, notices=notices)
    seed(tm, expires_in=600)
    tm.maintain()
    tm.maintain()
    sm = ScreenshotManager(logger=logger, token_manager=tm)
    assert sm.upload("7", base64_data="abc")
    assert notices == ["shown"]
    assert "token" not in uploads[-1]
