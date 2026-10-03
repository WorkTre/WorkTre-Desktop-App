"""
Desk screenshot token client.

Issue, renew, and revoke tokens against WORKTRE_BASE_URL. Secrets travel in the
POST body only. Attendance callers must treat every failure as non-fatal.
"""

import json
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

try:
    import certifi
except ImportError:  # pragma: no cover - certifi ships with requests
    certifi = None

from ..config import constants, settings
from ..platform.utils import get_app_data_dir
from . import dpapi


_FORBIDDEN_QUERY_KEYS = ("token", "password", "username")
_AUTH_REFRESH_ERRORS = ("reauth_required", "token_expired", "token_invalid")
# These failures are not infrastructure outages and must not arm the retry backoff.
_NO_FAILURE_BACKOFF = frozenset({
    "invalid_credentials",
    "rate_limited",
    "reauth_required",
    "token_expired",
    "token_invalid",
    "no_token",
    "superseded",
    "backoff",
})
_LOGGER_NAME = "worktre.desk_token"


@dataclass
class TokenResult:
    """Outcome of one token HTTP call. ``repr`` never includes the token."""

    ok: bool
    error: Optional[str] = None
    retry_after: Optional[float] = None
    token: Optional[str] = None
    employee_id: Optional[str] = None
    status_code: Optional[int] = None

    def __repr__(self) -> str:
        return (
            f"TokenResult(ok={self.ok}, error={self.error}, "
            f"status_code={self.status_code}, has_token={bool(self.token)})"
        )


def error_code_from_body(body: Any) -> Optional[str]:
    """Read a server error name from ``error`` or ``code``."""
    if not isinstance(body, dict):
        return None
    value = body.get("error")
    if value is None or value == "":
        value = body.get("code")
    if value is None or value == "":
        return None
    return str(value)


def _to_epoch(value: Any) -> Optional[float]:
    """Parse a unix timestamp (seconds or ms) or an ISO-8601 string."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 1e12:
            number = number / 1000.0
        return number
    if isinstance(value, str):
        text = value.strip()
        try:
            number = float(text)
            if number > 1e12:
                number = number / 1000.0
            return number
        except ValueError:
            pass
        from datetime import datetime, timezone
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return None


def _record_from_body(body: Dict[str, Any], now: Optional[float] = None) -> Optional[dict]:
    token = body.get("token")
    if not isinstance(token, str) or not token:
        return None
    now = time.time() if now is None else now
    expires = _to_epoch(body.get("expires_at"))
    if expires is None:
        try:
            expires = now + float(body.get("ttl_seconds"))
        except (TypeError, ValueError):
            expires = now + float(constants.DAY)
    employee = body.get("employee_id")
    return {
        "token": token,
        "employee_id": "" if employee is None else str(employee),
        "expires_at": body.get("expires_at"),
        "expires_at_epoch": expires,
        "chain_expires_at": body.get("chain_expires_at"),
        "chain_expires_at_epoch": _to_epoch(body.get("chain_expires_at")),
    }


def _retry_after_seconds(body: Any, response) -> float:
    raw = None
    if isinstance(body, dict) and body.get("retry_after") is not None:
        raw = body.get("retry_after")
    elif response is not None:
        headers = getattr(response, "headers", {}) or {}
        raw = headers.get("Retry-After")
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        seconds = 60.0
    if seconds < 0:
        seconds = 0.0
    return seconds


def _assert_url_has_no_secrets(url: str) -> None:
    parsed = urlparse(url)
    keys = {key.lower() for key in parse_qs(parsed.query)}
    if keys.intersection(_FORBIDDEN_QUERY_KEYS):
        raise ValueError("refusing secret in URL")
    lowered = url.lower()
    for key in _FORBIDDEN_QUERY_KEYS:
        if f"{key}=" in lowered:
            raise ValueError("refusing secret in URL")


def _ssl_verify():
    if not settings.VERIFY_SSL:
        return False
    if certifi is not None:
        return certifi.where()
    return True


class TokenStore:
    """DPAPI-backed token file. Without DPAPI the record stays in memory only."""

    def __init__(self, directory: str):
        self.directory = directory
        self.path = os.path.join(directory, constants.DESK_TOKEN_FILE)
        self._memory: Optional[dict] = None

    def save(self, record: dict) -> bool:
        self._memory = dict(record)
        if not dpapi.is_available():
            return False
        try:
            blob = dpapi.protect(json.dumps(record).encode("utf-8"))
            os.makedirs(self.directory, exist_ok=True)
            temporary = self.path + ".tmp"
            with open(temporary, "wb") as handle:
                handle.write(blob)
            os.replace(temporary, self.path)
            return True
        except Exception:
            return False

    def load(self) -> Optional[dict]:
        if not dpapi.is_available():
            return dict(self._memory) if self._memory else None
        if not os.path.exists(self.path):
            return dict(self._memory) if self._memory else None
        try:
            with open(self.path, "rb") as handle:
                blob = handle.read()
            payload = json.loads(dpapi.unprotect(blob).decode("utf-8"))
        except Exception:
            return dict(self._memory) if self._memory else None
        if not isinstance(payload, dict):
            return None
        self._memory = payload
        return dict(payload)

    def persisted(self) -> bool:
        return os.path.exists(self.path)

    def clear(self) -> None:
        self._memory = None
        for path in (self.path, self.path + ".tmp"):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


class TokenManager:
    """Thread-safe issue / renew / revoke client. HTTP timeout is 10 seconds."""

    def __init__(
        self,
        logger=None,
        storage_dir: Optional[str] = None,
        credential_loader: Optional[Callable] = None,
        on_reauth_notice: Optional[Callable] = None,
        computer_name: Optional[str] = None,
        app_version: Optional[str] = None,
    ):
        self.logger = logger
        self._store = TokenStore(storage_dir or get_app_data_dir(constants.APP_NAME))
        self._credential_loader = credential_loader or _default_credential_loader
        self._reauth_handler = on_reauth_notice
        self._computer_name = computer_name
        self._app_version = app_version
        self._lock = threading.RLock()
        self._maintain_gate = threading.Lock()
        self._record: Optional[dict] = None
        self._generation = 0
        self._blocked_until = 0.0
        self._failure_blocked_until = 0.0
        self._failure_backoff_seconds = 0.0
        self._employee_id: Optional[str] = None
        self._credentials_rejected = False
        self._reauth_notice_sent = False

    def set_reauth_handler(self, handler: Optional[Callable]) -> None:
        self._reauth_handler = handler

    def set_employee_id(self, employee_id) -> None:
        with self._lock:
            self._employee_id = None if employee_id is None else str(employee_id)

    def set_app_version(self, version) -> None:
        self._app_version = None if version is None else str(version)

    def set_computer_name(self, name: Optional[str]) -> None:
        self._computer_name = name

    def snapshot(self) -> dict:
        """Non-secret view of the in-memory token."""
        with self._lock:
            record = self._record or {}
            return {
                "has_token": bool(record.get("token")),
                "employee_id": record.get("employee_id"),
                "expires_at_epoch": record.get("expires_at_epoch"),
                "chain_expires_at_epoch": record.get("chain_expires_at_epoch"),
            }

    def get_upload_token(self) -> Optional[str]:
        """Current token for a screenshot upload, or None."""
        try:
            with self._lock:
                current = self._usable_token_locked(self._record)
                if current:
                    return current
            loaded = self._store.load()
            if not loaded:
                return None
            with self._lock:
                current = self._usable_token_locked(self._record)
                if current:
                    return current
                if not self._usable_token_locked(loaded):
                    return None
                self._record = loaded
                return loaded.get("token")
        except Exception:
            self._log("could not read upload token", "error")
            return None

    def issue(
        self,
        username: str,
        password: str,
        computer_name: Optional[str] = None,
        app_version: Optional[str] = None,
        reset_rejection: bool = False,
        ignore_backoff: bool = False,
    ) -> TokenResult:
        """POST /desktoken/issue. Does not retry. Manual login sets ``ignore_backoff``."""
        if not username or not password:
            return TokenResult(ok=False, error="bad_request")
        with self._lock:
            if reset_rejection:
                self._credentials_rejected = False
                self._reauth_notice_sent = False
            if self._rate_limited_locked():
                return TokenResult(
                    ok=False,
                    error="rate_limited",
                    retry_after=self._retry_remaining_locked(),
                )
            # A SOAP sign-in always tries once. Keep-alive and upload recovery do not.
            if not (ignore_backoff or reset_rejection) and self._failure_limited_locked():
                return TokenResult(
                    ok=False,
                    error="backoff",
                    retry_after=self._failure_remaining_locked(),
                )
            generation = self._generation
        fields = {"username": username, "password": password}
        computer = computer_name if computer_name is not None else self._computer_name_value()
        version = app_version if app_version is not None else self._app_version_value()
        if computer:
            fields["computer_name"] = computer
        if version:
            fields["app_version"] = version
        result, record = self._call("issue", constants.DESK_TOKEN_ISSUE_URL, fields)
        return self._finish_mutation(result, record, generation, invalid_sets_rejection=True)

    def renew(self) -> TokenResult:
        """POST /desktoken/renew. The server cancels the previous token."""
        with self._lock:
            if self._rate_limited_locked():
                return TokenResult(
                    ok=False,
                    error="rate_limited",
                    retry_after=self._retry_remaining_locked(),
                )
            if self._failure_limited_locked():
                return TokenResult(
                    ok=False,
                    error="backoff",
                    retry_after=self._failure_remaining_locked(),
                )
            token = (self._record or {}).get("token")
            generation = self._generation
        if not token:
            return TokenResult(ok=False, error="no_token")
        result, record = self._call("renew", constants.DESK_TOKEN_RENEW_URL, {"token": token})
        return self._finish_mutation(result, record, generation, invalid_sets_rejection=False)

    def revoke(self) -> TokenResult:
        """POST /desktoken/revoke and delete the stored token. Best effort."""
        with self._lock:
            limited = self._rate_limited_locked()
            retry_after = self._retry_remaining_locked()
            token = (self._record or {}).get("token")
            self._clear_locked()
        if not token:
            return TokenResult(ok=True)
        if limited:
            return TokenResult(ok=False, error="rate_limited", retry_after=retry_after)
        result, _record = self._call("revoke", constants.DESK_TOKEN_REVOKE_URL, {"token": token})
        if result.error == "rate_limited":
            with self._lock:
                self._set_rate_limit_locked(result.retry_after or 60)
        return result

    def revoke_async(self) -> None:
        """Revoke without blocking logout."""
        threading.Thread(target=self._revoke_background, name="desk-token-revoke", daemon=True).start()

    def issue_async(
        self,
        username: str,
        password: str,
        reset_rejection: bool = False,
        ignore_backoff: bool = False,
    ) -> None:
        """Issue after SOAP login. Returns immediately."""
        threading.Thread(
            target=self._issue_background,
            args=(username, password, reset_rejection, ignore_backoff),
            name="desk-token-issue",
            daemon=True,
        ).start()

    def crash_login_async(self, employee_id) -> None:
        """After crash_login: issue only when Remember me has a password."""
        threading.Thread(
            target=self._crash_background,
            args=(employee_id,),
            name="desk-token-crash",
            daemon=True,
        ).start()

    def maintain_async(self) -> None:
        """Keep-alive hook. Overlapping calls are dropped, never queued into a loop."""
        threading.Thread(target=self._maintain_background, name="desk-token-maintain", daemon=True).start()

    def handle_crash_login(self, employee_id) -> str:
        """
        Synchronous crash-login policy.

        Returns ``issued``, ``issue_failed``, ``restored``, or ``none``.
        """
        self.set_employee_id(employee_id)
        saved = self._saved_credentials()
        if saved:
            result = self.issue(saved[0], saved[1])
            return "issued" if result.ok else "issue_failed"
        if self.restore_stored(employee_id):
            return "restored"
        return "none"

    def restore_stored(self, employee_id) -> bool:
        """Reuse a stored token for this employee when it has not expired."""
        try:
            record = self._store.load()
        except Exception:
            self._log("stored token could not be read", "error")
            return False
        if not record or not record.get("token"):
            return False
        if str(record.get("employee_id")) != str(employee_id):
            self._log("stored desk token belongs to a different employee")
            return False
        if self._epoch_expired(record.get("expires_at_epoch")):
            self._log("stored desk token is expired")
            return False
        with self._lock:
            self._record = record
            self._employee_id = str(employee_id)
        self._log("reused stored desk token")
        return True

    def maintain(self) -> TokenResult:
        """Renew inside the lead window. Never raises. Does not sleep."""
        try:
            with self._lock:
                if self._rate_limited_locked():
                    return TokenResult(
                        ok=False,
                        error="rate_limited",
                        retry_after=self._retry_remaining_locked(),
                    )
                record = dict(self._record) if self._record else None
            if not record or not record.get("token"):
                return self._issue_saved_quietly()
            if not self._within_renew_window(record):
                return TokenResult(ok=True)
            renewed = self.renew()
            if renewed.ok or renewed.error == "rate_limited":
                return renewed
            if renewed.error in _AUTH_REFRESH_ERRORS:
                return self._issue_saved_or_notify(renewed.error)
            return renewed
        except Exception:
            self._log("token maintenance failed", "error")
            return TokenResult(ok=False, error="error")

    def recover_after_rejected_token(self) -> Optional[str]:
        """
        Upload helper: renew once, otherwise issue with the saved password.

        Returns a fresh token, or None so the caller can upload without one.
        """
        try:
            with self._lock:
                if self._rate_limited_locked() or self._failure_limited_locked():
                    return None
                has_token = bool(self._record and self._record.get("token"))
            renewed_error = None
            if has_token:
                renewed = self.renew()
                if renewed.ok and renewed.token:
                    return renewed.token
                if renewed.error == "rate_limited" or renewed.error == "backoff":
                    return None
                if _arms_failure_backoff(renewed):
                    return None
                renewed_error = renewed.error
            saved = None if self._credentials_rejected else self._saved_credentials()
            if saved:
                issued = self.issue(saved[0], saved[1])
                if issued.ok and issued.token:
                    return issued.token
                if issued.error == "rate_limited":
                    return None
                if renewed_error == "reauth_required" or issued.error in (
                    "invalid_credentials",
                    "reauth_required",
                ):
                    self._notify_reauth_once()
                    self.clear_local()
                return None
            if renewed_error == "reauth_required":
                self._notify_reauth_once()
                self.clear_local()
            elif renewed_error in ("token_expired", "token_invalid"):
                self.clear_local()
            return None
        except Exception:
            self._log("token recovery failed", "error")
            return None

    def clear_local(self) -> None:
        with self._lock:
            self._clear_locked()

    def _issue_background(
        self,
        username: str,
        password: str,
        reset_rejection: bool,
        ignore_backoff: bool = False,
    ) -> None:
        try:
            self.issue(
                username,
                password,
                reset_rejection=reset_rejection,
                ignore_backoff=ignore_backoff,
            )
        except Exception:
            self._log("background issue failed", "error")

    def _crash_background(self, employee_id) -> None:
        try:
            self.handle_crash_login(employee_id)
        except Exception:
            self._log("background crash token setup failed", "error")

    def _maintain_background(self) -> None:
        if not self._maintain_gate.acquire(blocking=False):
            return
        try:
            self.maintain()
        except Exception:
            self._log("background maintenance failed", "error")
        finally:
            self._maintain_gate.release()

    def _revoke_background(self) -> None:
        try:
            self.revoke()
        except Exception:
            self._log("revoke failed", "warning")

    def _issue_saved_quietly(self) -> TokenResult:
        with self._lock:
            if self._failure_limited_locked():
                return TokenResult(
                    ok=False,
                    error="backoff",
                    retry_after=self._failure_remaining_locked(),
                )
            rejected = self._credentials_rejected
        if rejected:
            return TokenResult(ok=False, error="invalid_credentials")
        saved = self._saved_credentials()
        if not saved:
            return TokenResult(ok=False, error="no_token")
        return self.issue(saved[0], saved[1])

    def _issue_saved_or_notify(self, reason: str) -> TokenResult:
        saved = None if self._credentials_rejected else self._saved_credentials()
        if saved:
            issued = self.issue(saved[0], saved[1])
            if issued.ok or issued.error == "rate_limited":
                return issued
            if reason == "reauth_required" or issued.error in ("invalid_credentials", "reauth_required"):
                self._notify_reauth_once()
                self.clear_local()
            return issued
        if reason == "reauth_required":
            self._notify_reauth_once()
            self.clear_local()
        elif reason in ("token_expired", "token_invalid"):
            self.clear_local()
        return TokenResult(ok=False, error=reason)

    def _call(self, action: str, url: str, fields: Dict[str, str]) -> Tuple[TokenResult, Optional[dict]]:
        try:
            response = _post_form(url, fields)
        except ValueError:
            self._log(f"{action} refused: secret in URL", "error")
            return TokenResult(ok=False, error="bad_request"), None
        except Exception:
            self._log(f"{action} transport failed", "warning")
            return TokenResult(ok=False, error="network"), None
        result, record = _interpret(response, action)
        level = "debug" if result.ok else "warning"
        self._log(f"{action} status={result.status_code} error={result.error or '-'}", level)
        return result, record

    def _finish_mutation(
        self,
        result: TokenResult,
        record: Optional[dict],
        generation: int,
        invalid_sets_rejection: bool,
    ) -> TokenResult:
        with self._lock:
            if result.error == "rate_limited":
                self._set_rate_limit_locked(result.retry_after or 60)
                return result
            success = bool(result.ok and record)
            if success:
                self._reset_failure_backoff_locked()
            if self._generation != generation:
                return TokenResult(ok=False, error="superseded", status_code=result.status_code)
            if success:
                self._store_record_locked(record)
                self._credentials_rejected = False
                self._reauth_notice_sent = False
                result.token = record.get("token")
                result.employee_id = record.get("employee_id")
                return result
            if invalid_sets_rejection and result.error == "invalid_credentials":
                self._credentials_rejected = True
            if _arms_failure_backoff(result):
                self._arm_failure_backoff_locked(result)
            return result

    def _store_record_locked(self, record: dict) -> None:
        self._record = dict(record)
        if record.get("employee_id"):
            self._employee_id = str(record["employee_id"])
        saved = self._store.save(self._record)
        if saved:
            self._log("desk token stored")
        elif dpapi.is_available():
            self._log("desk token kept in memory; disk save failed", "warning")
        else:
            self._log("desk token kept in memory; DPAPI unavailable")

    def _clear_locked(self) -> None:
        # Backoff stays. Dropping the token must not make the next keep-alive retry immediately.
        self._record = None
        self._generation += 1
        self._store.clear()

    def _usable_token_locked(self, record: Optional[dict]) -> Optional[str]:
        if not record or not record.get("token"):
            return None
        if self._epoch_expired(record.get("expires_at_epoch")):
            return None
        employee = record.get("employee_id")
        if self._employee_id and employee and str(employee) != str(self._employee_id):
            return None
        return record.get("token")

    def _within_renew_window(self, record: dict) -> bool:
        expires = record.get("expires_at_epoch")
        if expires is None:
            return True
        try:
            return float(expires) - time.time() <= constants.DESK_TOKEN_RENEW_LEAD
        except (TypeError, ValueError):
            return True

    def _epoch_expired(self, expires) -> bool:
        if expires is None:
            return False
        try:
            return float(expires) <= time.time()
        except (TypeError, ValueError):
            return False

    def _rate_limited_locked(self) -> bool:
        return time.time() < self._blocked_until

    def _retry_remaining_locked(self) -> float:
        return max(0.0, self._blocked_until - time.time())

    def _set_rate_limit_locked(self, seconds: float) -> None:
        try:
            delay = float(seconds)
        except (TypeError, ValueError):
            delay = 60.0
        if delay < 0:
            delay = 0.0
        self._blocked_until = time.time() + delay

    def _failure_limited_locked(self) -> bool:
        return time.time() < self._failure_blocked_until

    def _failure_remaining_locked(self) -> float:
        return max(0.0, self._failure_blocked_until - time.time())

    def _reset_failure_backoff_locked(self) -> None:
        self._failure_backoff_seconds = 0.0
        self._failure_blocked_until = 0.0

    def _arm_failure_backoff_locked(self, result: TokenResult) -> None:
        maximum = float(constants.DESK_TOKEN_FAILURE_BACKOFF_MAX)
        if result.status_code == 404 or result.error == "endpoint_unavailable":
            delay = maximum
        elif self._failure_backoff_seconds <= 0:
            delay = float(constants.DESK_TOKEN_FAILURE_BACKOFF_INITIAL)
        else:
            delay = min(self._failure_backoff_seconds * 2, maximum)
        self._failure_backoff_seconds = delay
        self._failure_blocked_until = time.time() + delay
        self._log(f"backing off {int(delay)}s error={result.error or '-'}", "warning")

    def _saved_credentials(self) -> Optional[Tuple[str, str]]:
        try:
            loaded = self._credential_loader()
        except Exception:
            self._log("saved credentials could not be read", "error")
            return None
        if not loaded:
            return None
        email = ""
        password = ""
        if isinstance(loaded, dict):
            email = loaded.get("email") or loaded.get("username") or ""
            password = loaded.get("password") or ""
        elif isinstance(loaded, (tuple, list)) and len(loaded) >= 2:
            email, password = loaded[0], loaded[1]
        if email and password:
            return str(email), str(password)
        return None

    def _computer_name_value(self) -> str:
        if self._computer_name:
            return str(self._computer_name)
        try:
            return socket.gethostname() or ""
        except Exception:
            return ""

    def _app_version_value(self) -> str:
        if self._app_version:
            return str(self._app_version)
        version = getattr(settings, "APP_VERSION", None)
        return str(version) if version else ""

    def _notify_reauth_once(self) -> None:
        with self._lock:
            if self._reauth_notice_sent:
                return
            self._reauth_notice_sent = True
            handler = self._reauth_handler
        self._log("reauth required; attendance continues")
        if not handler:
            return
        try:
            handler()
        except Exception:
            self._log("reauth notice failed", "error")

    def _log(self, message: str, level: str = "info") -> None:
        text = "[DeskToken] " + self._redact(str(message))
        logger = logging.getLogger(_LOGGER_NAME)
        getattr(logger, level if level in ("debug", "info", "warning", "error") else "info")(text)
        if self.logger is not None and self.logger is not logger:
            method = getattr(self.logger, level, None)
            if callable(method):
                try:
                    method(text)
                except Exception:
                    pass

    def _redact(self, message: str) -> str:
        token = None
        with self._lock:
            if self._record:
                token = self._record.get("token")
        if token and token in message:
            message = message.replace(token, "[redacted]")
        return message


def _post_form(url: str, fields: Dict[str, str]):
    _assert_url_has_no_secrets(url)
    return requests.post(
        url,
        data=fields,
        timeout=constants.DESK_TOKEN_TIMEOUT,
        verify=_ssl_verify(),
        allow_redirects=False,
    )


def _interpret(response, action: str) -> Tuple[TokenResult, Optional[dict]]:
    status = getattr(response, "status_code", 0) or 0
    body: Dict[str, Any] = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            body = parsed
    except Exception:
        body = {}
    error = error_code_from_body(body)
    if action == "revoke" and status == 200:
        return TokenResult(ok=True, status_code=status), None
    if status == 404:
        return TokenResult(ok=False, error="endpoint_unavailable", status_code=status), None
    if status == 429 or error == "rate_limited":
        return (
            TokenResult(
                ok=False,
                error="rate_limited",
                retry_after=_retry_after_seconds(body, response),
                status_code=status,
            ),
            None,
        )
    if status == 200 and (body.get("status") == "ok" or body.get("token")):
        record = _record_from_body(body)
        if not record:
            return TokenResult(ok=False, error="bad_response", status_code=status), None
        return (
            TokenResult(
                ok=True,
                token=record.get("token"),
                employee_id=record.get("employee_id"),
                status_code=status,
            ),
            record,
        )
    if status == 401:
        return TokenResult(ok=False, error=error or "unauthorized", status_code=status), None
    if status == 400:
        return TokenResult(ok=False, error=error or "bad_request", status_code=status), None
    if 500 <= status <= 599:
        return TokenResult(ok=False, error=error or "server_error", status_code=status), None
    return TokenResult(ok=False, error=error or "http_error", status_code=status), None


def _arms_failure_backoff(result: TokenResult) -> bool:
    """404, 5xx, transport errors, and unusable 200s. Auth failures do not."""
    if result.ok or not result.error:
        return False
    if result.status_code == 404 or result.error == "endpoint_unavailable":
        return True
    return result.error not in _NO_FAILURE_BACKOFF


def _default_credential_loader():
    try:
        from .security import get_remembered_user
        return get_remembered_user()
    except Exception:
        return None


_MANAGER: Optional[TokenManager] = None
_MANAGER_LOCK = threading.Lock()


def get_token_manager(logger=None, storage_dir: Optional[str] = None) -> TokenManager:
    """Process-wide token manager used by login and screenshot upload."""
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = TokenManager(logger=logger, storage_dir=storage_dir)
        elif logger is not None and _MANAGER.logger is None:
            _MANAGER.logger = logger
        return _MANAGER


def reset_token_manager(manager: Optional[TokenManager] = None) -> None:
    """Test helper."""
    global _MANAGER
    with _MANAGER_LOCK:
        _MANAGER = manager
