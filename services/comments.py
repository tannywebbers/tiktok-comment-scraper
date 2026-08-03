"""HTTP layer for the TikTok comments API.

The client obtains every request value (headers, cookies, query parameters)
from the session manager. It never knows which provider produced the session
or where the values came from.

Every request and response is mirrored to the diagnostics layer and recorded
into the logs directory, then analyzed by the session analysis engine. The
comments parser only ever receives a payload the analyzer confirmed as JSON.
Recording and analysis failures are warnings only and never interrupt the
scrape.
"""

import json
import time
from typing import Any

import requests

from config import BASE_URL, PAGE_SIZE, REQUEST_TIMEOUT
from services.analyzer.analyzer import ResponseAnalyzer
from services.diagnostics.inspector import RequestInspector, ResponseInspector
from services.diagnostics.recorder import DiagnosticsRecorder
from services.session.base import SessionData
from services.session.manager import SessionManager

# HTTP status codes that are transient and safe to retry.
_RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)

_request_inspector = RequestInspector()
_response_inspector = ResponseInspector()
_diagnostics_recorder = DiagnosticsRecorder()
_response_analyzer = ResponseAnalyzer()


class TikTokRequestError(Exception):
    """Raised when the TikTok comments API returns an unexpected response.

    Attributes:
        retryable: ``True`` for transient failures (timeouts, connection
            errors, HTTP 429/5xx) that are safe to retry.
        status_code: HTTP status code when the failure came from an HTTP
            response, ``None`` otherwise.
        code: Optional explicit error code (e.g. ``INVALID_RESPONSE``) that
            takes precedence over the derived status-based code.
        attempts: Number of HTTP attempts made before the failure, filled in
            by the retry loop.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: Any = None,
        code: str = "",
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.code = code
        self.attempts = 0


def _provider_name(session_manager: SessionManager) -> str:
    """Name of the active session provider, read without touching the manager."""
    provider = getattr(session_manager, "_provider", None)
    if provider is None:
        return "unknown"
    return type(provider).__name__


def _record_diagnostics(request_snapshot: Any, response_snapshot: Any) -> None:
    """Persist diagnostics, warning instead of raising on failure."""
    try:
        _diagnostics_recorder.record(request_snapshot, response_snapshot)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not record diagnostics: {exc}")


def _analyze_response(request_snapshot: Any, response_snapshot: Any) -> Any:
    """Run the analysis engine and save its report, never raising."""
    try:
        report = _response_analyzer.analyze(request_snapshot, response_snapshot)
        _response_analyzer.save(report)
        return report
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: response analysis failed: {exc}")
        return None


def _log_summary(request_snapshot: Any, response_snapshot: Any) -> None:
    """Print a readable summary of the captured interaction."""
    json_detected = "YES" if response_snapshot.is_json else "NO"
    response_type = response_snapshot.content_type or "unknown"
    print("----------------------------------")
    print("Request started")
    print(f"Provider name: {request_snapshot.provider}")
    print(f"Request URL: {request_snapshot.url}")
    print(f"Status code: {response_snapshot.status_code}")
    print(f"Elapsed time: {response_snapshot.elapsed_seconds:.3f} seconds")
    print(f"Response type: {response_type}")
    print(f"JSON detected: {json_detected}")
    print("Logs saved to:")
    print(f"{_diagnostics_recorder.log_dir}")
    print("----------------------------------")


def _build_params(session: SessionData, post_id: str, cursor: int) -> dict:
    """Compose the full query parameters for one comments page request.

    Args:
        session: Active session supplying the static query parameters.
        post_id: Numeric TikTok video ID.
        cursor: Pagination cursor; ``0`` requests the first page.

    Returns:
        The complete ``params`` dictionary for the request.
    """
    params = dict(session.query_params)
    params["aweme_id"] = post_id
    params["count"] = str(PAGE_SIZE)
    params["cursor"] = str(cursor)
    return params


def fetch_comments(
    post_id: str, cursor: int, session_manager: SessionManager
) -> dict:
    """Fetch a single page of comments for a post.

    Args:
        post_id: Numeric TikTok video ID.
        cursor: Pagination cursor; ``0`` requests the first page.
        session_manager: Session manager supplying the session for this
            request. One manager is created per scrape execution so no state
            is shared across requests.

    Returns:
        The parsed JSON payload of the comments API as a dict.

    Raises:
        TikTokRequestError: If the request fails or the response body is not
            valid JSON. Transient failures (timeouts, connection errors,
            HTTP 429/5xx) are marked ``retryable=True``.
    """
    session = session_manager.get_session()
    session_manager.validate()

    params = _build_params(session, post_id, cursor)

    request_snapshot = _request_inspector.capture(
        url=BASE_URL,
        method="GET",
        headers=session.headers,
        cookies=session.cookies,
        params=params,
        provider=_provider_name(session_manager),
    )

    started = time.perf_counter()

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            headers=session.headers,
            cookies=session.cookies,
            timeout=REQUEST_TIMEOUT,
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise TikTokRequestError(
            f"Could not reach the TikTok comments API: {exc}", retryable=True
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise TikTokRequestError(
            f"Could not reach the TikTok comments API: {exc}"
        ) from exc

    elapsed = time.perf_counter() - started

    response_snapshot = _response_inspector.capture(response, elapsed)
    _record_diagnostics(request_snapshot, response_snapshot)
    _log_summary(request_snapshot, response_snapshot)

    report = _analyze_response(request_snapshot, response_snapshot)

    if response.status_code in _RETRYABLE_STATUS_CODES:
        raise TikTokRequestError(
            f"TikTok comments API returned transient HTTP {response.status_code}.",
            retryable=True,
            status_code=response.status_code,
        )

    if response.status_code >= 400:
        raise TikTokRequestError(
            f"TikTok comments API returned HTTP {response.status_code}.",
            status_code=response.status_code,
        )

    body = response.text

    is_json = report.json_detected if report is not None else response_snapshot.is_json
    if not is_json:
        reason = getattr(report, "possible_reason", "") if report is not None else ""
        reason_text = f" Possible reason: {reason}" if reason else ""
        raise TikTokRequestError(
            "TikTok comments API returned a non-JSON response "
            f"(HTTP {response.status_code}).{reason_text}",
            status_code=response.status_code,
            code="INVALID_RESPONSE",
        )

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        print(f"Body (first 500 characters): {body[:500]}")
        raise TikTokRequestError(
            "TikTok comments API returned a non-JSON response "
            f"(HTTP {response.status_code}).",
            status_code=response.status_code,
            code="INVALID_RESPONSE",
        ) from exc
