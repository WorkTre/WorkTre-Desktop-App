"""QA extra tests: migration failure paths, secrets in logs, JPEG fallback, SOAP
escaping, attendance isolation, packaging import."""
import base64
import json
import logging
import os
import threading
import time
import types
import xml.etree.ElementTree as ET
from io import BytesIO

import pytest
import requests
from cryptography.fernet import Fernet

from src.config import constants
from src.utils import dpapi, security, screenshot
from src.utils.screenshot import ScreenshotManager

from qa_helpers import (
    FakeResponse, ListLogger, PASSWORD, TOKEN_A, TOKEN_A2, USERNAME,
    make_manager, ok_body, route, seed, use_xor_dpapi,
)


@pytest.fixture(autouse=True)
def _no_real_http(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("unexpected real HTTP")
    monkeypatch.setattr(requests, "post", boom)


def write_legacy(d, email=USERNAME, password=PASSWORD):
    key = Fernet.generate_key()
    (d / constants.KEY_FILE).write_bytes(key)
    (d / constants.DATA_FILE).write_text(json.dumps(
        {"email": email, "password": Fernet(key).encrypt(password.encode()).decode()}))


# ---------------------------------------------------------------- migration

def test_migration_protect_raises_keeps_legacy(tmp_path, monkeypatch):
    use_xor_dpapi(monkeypatch)
    write_legacy(tmp_path)

    def fail(_):
        raise dpapi.DpapiError("boom")
    monkeypatch.setattr(dpapi, "protect", fail)
    sm = security.SecurityManager(base_dir=str(tmp_path))
    assert sm.load_credentials() == {"email": USERNAME, "password": PASSWORD}
    assert (tmp_path / constants.KEY_FILE).exists() and (tmp_path / constants.DATA_FILE).exists()
    assert not (tmp_path / constants.DPAPI_CREDENTIALS_FILE).exists()
    assert not (tmp_path / (constants.DPAPI_CREDENTIALS_FILE + ".tmp")).exists()


def test_migration_replace_fails_keeps_legacy(tmp_path, monkeypatch):
    use_xor_dpapi(monkeypatch)
    write_legacy(tmp_path)
    real_replace = os.replace

    def fail_replace(a, b):
        if str(b).endswith(constants.DPAPI_CREDENTIALS_FILE):
            raise PermissionError("locked")
        return real_replace(a, b)
    monkeypatch.setattr(security.os, "replace", fail_replace)
    sm = security.SecurityManager(base_dir=str(tmp_path))
    assert sm.load_credentials()["password"] == PASSWORD
    assert (tmp_path / constants.DATA_FILE).exists()
    assert not (tmp_path / (constants.DPAPI_CREDENTIALS_FILE + ".tmp")).exists()


@pytest.mark.parametrize("content", ["{not json", json.dumps({"email": "x"}), json.dumps([1, 2])])
def test_corrupt_legacy_falls_back_to_sign_in(tmp_path, monkeypatch, content, capsys):
    use_xor_dpapi(monkeypatch)
    (tmp_path / constants.KEY_FILE).write_bytes(Fernet.generate_key())
    (tmp_path / constants.DATA_FILE).write_text(content)
    assert security.SecurityManager(base_dir=str(tmp_path)).load_credentials() is None
    assert not (tmp_path / constants.KEY_FILE).exists()
    assert not (tmp_path / constants.DATA_FILE).exists()


def test_orphan_legacy_key_only_is_removed(tmp_path, monkeypatch):
    use_xor_dpapi(monkeypatch)
    (tmp_path / constants.KEY_FILE).write_bytes(Fernet.generate_key())
    assert security.SecurityManager(base_dir=str(tmp_path)).load_credentials() is None
    assert not (tmp_path / constants.KEY_FILE).exists()


def test_legacy_deleted_only_after_verified_dpapi_save(tmp_path, monkeypatch):
    """FINDING L-migration-verify: the DPAPI write is not read back before the legacy pair
    is deleted. If the written blob cannot be decrypted, the password is lost."""
    use_xor_dpapi(monkeypatch)
    write_legacy(tmp_path)
    monkeypatch.setattr(dpapi, "protect", lambda data: b"\x00garbage")  # write 'succeeds'
    sm = security.SecurityManager(base_dir=str(tmp_path))
    sm.load_credentials()
    # On the next launch the saved password must still be recoverable from somewhere.
    again = security.SecurityManager(base_dir=str(tmp_path)).load_credentials()
    assert again and again["password"] == PASSWORD


def test_transient_read_error_does_not_delete_remember_me(tmp_path, monkeypatch):
    """FINDING L-dpapi-delete: _read_dpapi_credentials() deletes remember_me.dpapi on ANY
    exception, including a transient open/unprotect failure (AV lock, profile not loaded)."""
    use_xor_dpapi(monkeypatch)
    sm = security.SecurityManager(base_dir=str(tmp_path))
    assert sm.save_credentials(USERNAME, PASSWORD)

    def flaky(_):
        raise dpapi.DpapiError("CryptUnprotectData failed (winerror=1722)")
    monkeypatch.setattr(dpapi, "unprotect", flaky)
    monkeypatch.setattr(dpapi, "unprotect_status", flaky)  # ADAPTATION @cb8d9e8
    assert sm.load_credentials() is None
    assert (tmp_path / constants.DPAPI_CREDENTIALS_FILE).exists()


def test_concurrent_first_launch_loads_do_not_lose_credentials(tmp_path, monkeypatch):
    use_xor_dpapi(monkeypatch)
    write_legacy(tmp_path)
    results = []

    def load():
        results.append(security.SecurityManager(base_dir=str(tmp_path)).load_credentials())
    threads = [threading.Thread(target=load) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert (tmp_path / constants.DPAPI_CREDENTIALS_FILE).exists()
    assert security.SecurityManager(base_dir=str(tmp_path)).load_credentials()["password"] == PASSWORD


def test_token_store_save_failure_does_not_leave_stale_token(tmp_path, monkeypatch):
    """FINDING L-stale-file: when the DPAPI save of a renewed token fails, the previous
    (server-cancelled) token stays on disk and is reloaded after a restart."""
    use_xor_dpapi(monkeypatch)
    logger = ListLogger()
    tm = make_manager(tmp_path, logger)
    seed(tm)

    def fail(_):
        raise dpapi.DpapiError("x")
    monkeypatch.setattr(dpapi, "protect", fail)
    route(monkeypatch, lambda *a: FakeResponse(200, ok_body(TOKEN_A2)))
    assert tm.renew().ok
    restarted = make_manager(tmp_path, logger)
    restarted.set_employee_id("7")
    assert restarted.get_upload_token() != TOKEN_A


# ---------------------------------------------------------------- secrets in logs

def test_no_secrets_in_logs_on_transport_errors_and_debug(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    logger = ListLogger()

    def handler(url, data, kw):
        # requests exceptions can embed the URL and even the request body
        raise requests.exceptions.ConnectionError(f"failed {url} body={data!r}")

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USERNAME, PASSWORD))
    tm.issue(USERNAME, PASSWORD, reset_rejection=True, ignore_backoff=True)
    seed(tm)
    tm._reset_failure_backoff_locked()
    tm.renew()
    tm.revoke()
    seed(tm)
    ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data="abc")
    out = capsys.readouterr()
    combined = "\n".join([logger.text, caplog.text, out.out, out.err])
    for secret in (PASSWORD, TOKEN_A, USERNAME):
        assert secret not in combined, secret


def test_no_secrets_in_logs_on_server_error_bodies(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    logger = ListLogger()

    def handler(url, data, kw):
        if "/desktoken/" in url:
            return FakeResponse(500, {"error": f"db failed for {data.get('username')} {data.get('password')} {data.get('token')}"})
        return FakeResponse(401, {"error": f"token_invalid {data.get('token')}"})

    route(monkeypatch, handler)
    tm = make_manager(tmp_path, logger, loader=lambda: (USERNAME, PASSWORD))
    tm.issue(USERNAME, PASSWORD, reset_rejection=True, ignore_backoff=True)
    seed(tm)
    tm._reset_failure_backoff_locked()
    ScreenshotManager(logger=logger, token_manager=tm).upload("7", base64_data="abc")
    out = capsys.readouterr()
    combined = "\n".join([logger.text, caplog.text, out.out, out.err])
    for secret in (PASSWORD, TOKEN_A, USERNAME):
        assert secret not in combined, secret


def test_soap_login_does_not_log_username(monkeypatch, caplog, capsys):
    """FINDING L-username-logs (pre-existing): the PR claims no username in logs, but
    soap_client.login logs 'Login successful for user: <username>' and JSApi.login prints
    it too. Not introduced by this PR."""
    from src.api import soap_client
    caplog.set_level(logging.DEBUG)
    client = soap_client.SOAPClient.__new__(soap_client.SOAPClient)
    client.logger = logging.getLogger("qa.soap")
    client.action_builder = types.SimpleNamespace(login=lambda: "login")
    client._make_request = lambda action, payload: "<x/>"
    client._parse_soap_response = lambda resp, tag: {"EID": "7"}
    monkeypatch.setattr(soap_client, "get_dynamic_ip", lambda: "1.2.3.4", raising=False)
    client.login(USERNAME, PASSWORD)
    out = capsys.readouterr()
    assert USERNAME not in caplog.text + out.out + out.err


# ---------------------------------------------------------------- JPEG fallback

def _noise(w, h, mode="RGB", seed=3):
    import random
    rng = random.Random(seed)
    from PIL import Image
    bands = len(mode)
    return Image.frombytes(mode, (w, h), bytes(rng.randrange(256) for _ in range(w * h * bands)))


def _png_b64(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.mark.parametrize("mode", ["RGBA", "P", "LA", "L"])
def test_jpeg_fallback_handles_modes(tmp_path, monkeypatch, mode):
    from PIL import Image
    img = _noise(120, 80, "RGB").convert(mode)
    b64 = _png_b64(img)
    monkeypatch.setattr(screenshot, "MAX_UPLOAD_BASE64_CHARS", len(b64) - 1)
    sm = ScreenshotManager(logger=ListLogger(), token_manager=make_manager(tmp_path, ListLogger()))
    fitted = sm._fit_upload_payload(b64)
    assert fitted is not None and fitted[1] == "JPEG"
    assert Image.open(BytesIO(base64.b64decode(fitted[0]))).format == "JPEG"


def test_jpeg_fallback_real_12mb_limit_three_monitor_capture(tmp_path):
    """Triple 1080p noise capture (worst case for PNG) at the real 12 MB limit."""
    img = _noise(5760, 1080, "RGB", seed=9)
    b64 = _png_b64(img)
    assert len(b64) > screenshot.MAX_UPLOAD_BASE64_CHARS
    sm = ScreenshotManager(logger=ListLogger(), token_manager=make_manager(tmp_path, ListLogger()))
    t0 = time.time()
    fitted = sm._fit_upload_payload(b64)
    assert fitted and fitted[1] == "JPEG" and len(fitted[0]) <= screenshot.MAX_UPLOAD_BASE64_CHARS
    assert time.time() - t0 < 30


def test_downscale_loop_terminates_for_narrow_image(tmp_path, monkeypatch):
    """FINDING I-downscale: once width reaches 1 px with height > 1 the loop can spin
    forever (new size == old size, `seen` stops growing). Only reachable for absurd
    aspect ratios; guarded here with a timeout."""
    img = _noise(2, 4000, "RGB")
    sm = ScreenshotManager(logger=ListLogger(), token_manager=make_manager(tmp_path, ListLogger()))
    done = []
    t = threading.Thread(target=lambda: done.append(sm._downscale_until_fit(img, 10, "x" * 1000)), daemon=True)
    t.start()
    t.join(10)
    assert done, "downscale loop did not terminate within 10 s"


# ---------------------------------------------------------------- SOAP escaping

def _client():
    from src.api.soap_client import SOAPClient
    return SOAPClient.__new__(SOAPClient)


def _old_envelope(method, parameters):
    param_xml = ''
    for key, value in parameters.items():
        param_xml += f'<{key}>{value}</{key}>\n'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope 
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:web="https://worktre.com/">
   <soapenv:Header/>
   <soapenv:Body>
      <web:{method}>
         {param_xml}
      </web:{method}>
   </soapenv:Body>
</soapenv:Envelope>'''


@pytest.mark.parametrize("value", ['a&b', '<x>', 'p"q', "p'q", '&amp;', ']]>', 'naïve-ü', 'None'])
def test_soap_values_round_trip_exactly(value):
    xml = _client()._build_soap_envelope("login", {"employeeaccount": "u", "password": value})
    root = ET.fromstring(xml.encode("utf-8"))
    got = [e.text for e in root.iter() if e.tag == "password"][0]
    assert got == value  # not double-escaped, not double-decoded


def test_soap_ordinary_values_byte_identical_to_old():
    params = {"employeeaccount": "noman.s", "password": "Abc123!", "ComputerName": "PC-1",
              "wtversion": "2.2.3", "ipaddress": "10.0.0.1", "EID": 7, "flag": None}
    assert _client()._build_soap_envelope("login", params) == _old_envelope("login", params)


def test_soap_control_characters_stay_well_formed():
    """FINDING I-xml-ctrl: XML 1.0 forbids most C0 control chars; escape() does not
    strip them, so a pasted password with e.g. \\x01 still yields malformed XML."""
    xml = _client()._build_soap_envelope("login", {"password": "a\x01b"})
    ET.fromstring(xml.encode("utf-8"))


# ---------------------------------------------------------------- attendance isolation

def _app(monkeypatch):
    from src import main as m
    app = m.WorkTreApp.__new__(m.WorkTreApp)
    app.state = m.AppState()
    app.logger = logging.getLogger("qa.app")
    app.app_version = "2.2.3"
    app.notification_manager = None
    app.inactivity_manager = None
    app.lock_window_size = lambda: None
    app.unlock_window_size = lambda: None
    app._stop_service_interval = lambda: None
    app.api_client = types.SimpleNamespace(
        login=lambda u, p: {"status": True, "data": {"EID": "7"}},
        logout=lambda *a: {"status": True, "logged_out": True},
    )
    return m, app


def test_login_not_blocked_by_slow_or_broken_token_service(monkeypatch, tmp_path):
    from src.utils import desk_token
    m, app = _app(monkeypatch)
    desk_token.reset_token_manager(make_manager(tmp_path, ListLogger()))

    def slow(*a, **k):
        time.sleep(3)
        raise requests.exceptions.Timeout()
    monkeypatch.setattr(requests, "post", slow)
    t0 = time.time()
    assert app.login("u", "p")["status"] is True
    assert time.time() - t0 < 0.5

    def broken(*a, **k):
        raise RuntimeError("token manager exploded")
    monkeypatch.setattr(desk_token, "get_token_manager", broken)
    assert app.login("u", "p")["status"] is True
    desk_token.reset_token_manager(None)


def test_logout_soap_unaffected_by_revoke_failure(monkeypatch, tmp_path):
    from src.utils import desk_token
    m, app = _app(monkeypatch)
    app.state.is_logged_in = True
    app.state.current_user = "7"

    def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(desk_token, "get_token_manager", broken)
    assert app.logout()["logged_out"] is True
    assert app.state.is_logged_in is False


def test_desk_token_import_works_when_main_runs_as_script():
    """FINDING H-frozen-import: WorkTre.spec builds from 'src/main.py' (run as __main__).
    _desk_token_manager() uses `from .utils.desk_token import ...`, which raises
    ImportError without a parent package, so the packaged EXE never issues, renews or
    revokes a token (errors are swallowed and logged)."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    g = {"__name__": "__qa_script__", "__package__": None, "__file__": str(root / "src/main.py")}
    exec(compile((root / "src/main.py").read_text(encoding="utf-8"), "src/main.py", "exec"), g)
    App = g["WorkTreApp"]
    app = App.__new__(App)
    app.logger = None
    app.app_version = "2.2.3"
    app._desk_token_manager()
