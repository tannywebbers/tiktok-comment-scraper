"""Automatic response analysis for the TikTok comments API.

The analyzer inspects a captured request/response pair and produces a
serializable :class:`AnalysisReport`. It never raises on unexpected input:
every observation is recorded in the report instead. The report also drives
the recommendation engine, which turns the findings into actionable advice.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ANALYSIS_OUTPUT, LOGS_DIR

# HTML signals detected with a case-insensitive scan of the raw body.
_HTML_SIGNALS: Dict[str, str] = {
    "doctype": r"<!doctype\s+html",
    "captcha": r"\bcaptcha\b",
    "verify": r"\bverify\b",
    "login": r"\blogin\b",
    "access_denied": r"access\s+denied",
    "blocked": r"\bblocked\b",
    "forbidden": r"\bforbidden\b",
    "challenge": r"\bchallenge\b",
    "cloudflare": r"\bcloudflare\b",
}

# Maps each HTML signal to the report attribute it toggles.
_SIGNAL_ATTRS: Dict[str, str] = {
    "doctype": "doctype",
    "captcha": "contains_captcha",
    "verify": "contains_verify",
    "login": "contains_login",
    "access_denied": "contains_access_denied",
    "blocked": "contains_blocked",
    "forbidden": "contains_forbidden",
    "challenge": "contains_challenge",
    "cloudflare": "contains_cloudflare",
}

# Security headers worth surfacing in the report.
_SECURITY_HEADERS: tuple = (
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "x-xss-protection",
    "referrer-policy",
    "permissions-policy",
)

_HTML_STARTS = ("<!", "<html", "<head", "<body", "<script")


@dataclass
class AnalysisReport:
    """Serializable analysis of a single response."""

    response_type: str = "unknown"
    possible_reason: str = ""
    status_code: int = 0
    content_type: str = ""
    json_detected: bool = False
    html_detected: bool = False
    redirects: int = 0
    redirect_destinations: List[str] = field(default_factory=list)
    response_size: int = 0
    compression: str = ""
    server: str = ""
    security_headers: Dict[str, str] = field(default_factory=dict)
    cookies_sent: List[str] = field(default_factory=list)
    cookies_received: List[str] = field(default_factory=list)
    top_level_keys: List[str] = field(default_factory=list)
    has_comments: bool = False
    has_cursor: bool = False
    has_has_more: bool = False
    has_status_code: bool = False
    has_log_pb: bool = False
    doctype: bool = False
    script_tags: bool = False
    contains_captcha: bool = False
    contains_verify: bool = False
    contains_login: bool = False
    contains_access_denied: bool = False
    contains_blocked: bool = False
    contains_forbidden: bool = False
    contains_challenge: bool = False
    contains_cloudflare: bool = False
    html_signals: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    provider: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict of this report."""
        return asdict(self)


def _is_html_body(body: str) -> bool:
    """Return ``True`` when the raw body looks like an HTML document."""
    stripped = body.lstrip()
    return any(stripped.lower().startswith(start) for start in _HTML_STARTS)


class ResponseAnalyzer:
    """Inspects a captured request/response pair and builds a report."""

    def analyze(self, request: Any, response: Any) -> AnalysisReport:
        """Analyze ``request``/``response`` and return a report.

        Args:
            request: A :class:`RequestSnapshot` from the diagnostics layer.
            response: A :class:`ResponseSnapshot` from the diagnostics layer.

        Returns:
            A fully populated :class:`AnalysisReport`.
        """
        raw_body = response.raw_body or ""
        if isinstance(raw_body, bytes):
            raw_body = raw_body.decode("utf-8", errors="replace")

        report = AnalysisReport(
            provider=getattr(request, "provider", ""),
            status_code=response.status_code,
            content_type=response.content_type,
            json_detected=bool(response.is_json),
            redirects=len(response.redirect_chain),
            redirect_destinations=[hop["url"] for hop in response.redirect_chain],
            response_size=response.response_length,
            compression=response.headers.get("Content-Encoding", ""),
            server=response.headers.get("Server", ""),
            cookies_sent=sorted(request.cookies.keys()),
            cookies_received=sorted(response.cookies.keys()),
        )

        self._inspect_html(report, raw_body)
        report.html_detected = bool(report.html_signals) or _is_html_body(raw_body)
        report.response_type = self._classify(report)
        self._inspect_json(report, raw_body)
        self._inspect_security_headers(report, response)
        report.possible_reason = self._possible_reason(report)
        report.recommendations = self._recommendations(report)
        return report

    def save(
        self,
        report: AnalysisReport,
        log_dir: str = LOGS_DIR,
        filename: str = ANALYSIS_OUTPUT,
    ) -> Path:
        """Write ``report`` to ``log_dir/filename`` and return the path."""
        path = Path(log_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=4)
        return path

    def _classify(self, report: AnalysisReport) -> str:
        """Classify the response as ``json``, ``html`` or ``unknown``."""
        if report.json_detected:
            return "json"
        if report.html_detected:
            return "html"
        return "unknown"

    def _inspect_html(self, report: AnalysisReport, raw_body: str) -> None:
        """Scan the raw body for HTML challenge/block signals."""
        body = raw_body.lower()

        for signal, pattern in _HTML_SIGNALS.items():
            if re.search(pattern, body):
                setattr(report, _SIGNAL_ATTRS[signal], True)
                report.html_signals.append(signal)

        report.script_tags = "</script>" in body or "<script" in body

    def _inspect_json(self, report: AnalysisReport, raw_body: str) -> None:
        """Record top-level keys of a JSON payload."""
        if not report.json_detected:
            return

        parsed: Any = None
        try:
            parsed = json.loads(raw_body)
        except (json.JSONDecodeError, TypeError, ValueError):
            return

        if isinstance(parsed, dict):
            report.top_level_keys = sorted(parsed.keys())
            report.has_comments = "comments" in parsed
            report.has_cursor = "cursor" in parsed
            report.has_has_more = "has_more" in parsed
            report.has_status_code = "status_code" in parsed
            report.has_log_pb = "log_pb" in parsed

    def _inspect_security_headers(self, report: AnalysisReport, response: Any) -> None:
        """Collect security headers that were present in the response."""
        for header, value in response.headers.items():
            lower = header.lower()
            if lower in _SECURITY_HEADERS:
                report.security_headers[lower] = value

    def _possible_reason(self, report: AnalysisReport) -> str:
        """Pick the most likely reason for the response we received."""
        if report.response_type == "html":
            if report.contains_access_denied:
                return "Access Denied"
            if report.contains_cloudflare:
                return "Cloudflare Challenge"
            if report.contains_blocked:
                return "Blocked"
            if report.contains_challenge:
                return "Challenge Required"
            if report.contains_captcha:
                return "Captcha Required"
            if report.contains_login:
                return "Login Required"
            if report.contains_forbidden:
                return "Forbidden"
            return "HTML page returned"

        if report.response_type == "json":
            if report.status_code == 200:
                return "OK"
            return f"HTTP {report.status_code}"

        return "Unknown response format"

    def _recommendations(self, report: AnalysisReport) -> List[str]:
        """Generate actionable recommendations from the report findings."""
        recommendations: List[str] = []

        if not report.cookies_sent:
            recommendations.append(
                "Missing cookies: no cookies were sent with the request; "
                "the session may need refreshing or a browser provider."
            )

        if report.status_code in (401, 403) and report.response_type == "json":
            recommendations.append(
                "Session expired: HTTP 401/403 returned; refresh the session "
                "before retrying."
            )

        if report.response_type == "html":
            recommendations.append(
                "Received HTML instead of JSON: the API returned a page; the "
                "request was likely intercepted by a challenge or block."
            )
            if report.contains_login:
                recommendations.append(
                    "Login required: the response references a login flow; an "
                    "authenticated session may be needed."
                )
            if (
                report.contains_access_denied
                or report.contains_blocked
                or report.contains_forbidden
            ):
                recommendations.append(
                    "Likely blocked: access-control keywords were detected in "
                    "the response."
                )
            if (
                report.contains_captcha
                or report.contains_challenge
                or report.contains_cloudflare
            ):
                recommendations.append(
                    "Bot challenge detected: captcha/challenge/cloudflare "
                    "signals are present in the response."
                )

        if report.status_code in (403, 429):
            recommendations.append(
                "Likely blocked or rate-limited: HTTP 403/429 returned."
            )

        if report.redirects:
            recommendations.append(
                "Likely redirect: the request followed a redirect; verify the "
                "API endpoint is still correct."
            )

        if report.status_code == 404:
            recommendations.append(
                "Endpoint changed: HTTP 404 returned; the API path may have "
                "moved."
            )

        if report.response_type == "json" and not (
            report.has_comments or report.has_has_more
        ):
            recommendations.append(
                "Endpoint changed: JSON returned but the expected keys "
                "(comments, has_more) are missing."
            )

        if report.response_type == "unknown":
            recommendations.append(
                "Unknown response format: neither JSON nor HTML was detected."
            )

        return recommendations
