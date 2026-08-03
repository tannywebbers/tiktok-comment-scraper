"""Request and response inspectors for the diagnostics layer.

Each inspector captures a single HTTP interaction and returns a serializable
snapshot. Inspectors never raise on malformed input: JSON decoding failures
are reflected in the snapshot instead of bubbling up to the scraper.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _with_query(url: str, params: Optional[Dict[str, Any]]) -> str:
    """Append ``params`` to ``url`` as a query string."""
    if not params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def _pretty_json(body: str) -> Optional[str]:
    """Pretty-print ``body`` if it is valid JSON, otherwise return ``None``.

    Never raises.
    """
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return json.dumps(parsed, ensure_ascii=False, indent=4)


@dataclass
class RequestSnapshot:
    """Serializable description of an outgoing request.

    Attributes:
        url: Full request URL, including any query parameters.
        method: HTTP method.
        headers: Request headers.
        cookies: Request cookies.
        params: Query parameters sent with the request.
        provider: Name of the session provider that produced the session.
        timestamp: When the request was captured (ISO 8601).
    """

    url: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict of this snapshot."""
        return asdict(self)


@dataclass
class ResponseSnapshot:
    """Serializable description of a received response.

    Attributes:
        status_code: HTTP status code.
        final_url: URL of the last response after any redirects.
        headers: Response headers.
        cookies: Cookies received with the response.
        redirect_chain: Every hop in the redirect chain, in order.
        content_type: Value of the ``Content-Type`` response header.
        response_length: Length of the raw response body in characters.
        elapsed_seconds: Wall-clock time spent on the request.
        is_json: Whether the body decoded as valid JSON.
        body_json: Pretty-printed JSON body, or ``None`` if not JSON.
        raw_body: Raw response body text.
    """

    status_code: int = 0
    final_url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    redirect_chain: List[Dict[str, Any]] = field(default_factory=list)
    content_type: str = ""
    response_length: int = 0
    elapsed_seconds: float = 0.0
    is_json: bool = False
    body_json: Optional[str] = None
    raw_body: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict of this snapshot."""
        return asdict(self)


class RequestInspector:
    """Captures the details of an outgoing request."""

    def capture(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        provider: str = "",
    ) -> RequestSnapshot:
        """Build a :class:`RequestSnapshot` from the given request values.

        Args:
            url: Base request URL. Query parameters from ``params`` are
                appended to it in the snapshot.
            method: HTTP method (defaults to ``"GET"``).
            headers: Request headers.
            cookies: Request cookies.
            params: Query parameters sent with the request.
            provider: Name of the session provider that produced the session.

        Returns:
            A serializable :class:`RequestSnapshot`.
        """
        return RequestSnapshot(
            url=_with_query(url, params),
            method=method,
            headers=dict(headers or {}),
            cookies=dict(cookies or {}),
            params=dict(params or {}),
            provider=provider,
        )


class ResponseInspector:
    """Captures the details of a received response."""

    def capture(
        self,
        response: Any,
        elapsed_seconds: float = 0.0,
    ) -> ResponseSnapshot:
        """Build a :class:`ResponseSnapshot` from a ``requests`` response.

        Defensive against partially-populated response objects: missing
        attributes fall back to empty values instead of raising.

        Args:
            response: A ``requests.Response`` (or compatible) object.
            elapsed_seconds: Wall-clock time spent on the request.

        Returns:
            A serializable :class:`ResponseSnapshot`. JSON decoding failures
            never raise; they are reflected as ``is_json=False``.
        """
        status_code = getattr(response, "status_code", 0)
        final_url = getattr(response, "url", "")
        headers = dict(getattr(response, "headers", {}) or {})
        history = getattr(response, "history", None) or []

        redirects = [
            {
                "status_code": getattr(hop, "status_code", 0),
                "url": getattr(hop, "url", ""),
                "headers": dict(getattr(hop, "headers", {}) or {}),
            }
            for hop in history
        ]

        content_type = headers.get("Content-Type", "")
        raw_body = getattr(response, "text", "")
        body_json = _pretty_json(raw_body)

        cookies = {}
        cookies_jar = getattr(response, "cookies", None)
        if cookies_jar is not None:
            cookies = {cookie.name: cookie.value for cookie in cookies_jar}

        return ResponseSnapshot(
            status_code=status_code,
            final_url=final_url,
            headers=headers,
            cookies=cookies,
            redirect_chain=redirects,
            content_type=content_type,
            response_length=len(raw_body),
            elapsed_seconds=elapsed_seconds,
            is_json=body_json is not None,
            body_json=body_json,
            raw_body=raw_body,
        )
