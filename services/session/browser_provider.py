"""Browser-backed session provider.

Launches a real browser (Playwright) for the duration of a single session,
visits the TikTok video page, and captures the cookies, user-agent, language,
timezone, viewport and screen size the HTTP client needs. The browser is
always closed before the provider returns, so no browser stays running
permanently.

The comments API only accepts a small set of query parameters. Experiments
against the live API confirmed that the full parameter set the browser's own
XHR requests carry causes the endpoint to answer with an empty 200 body,
while the minimal set (``aid``, ``app_name``, ``app_language`` plus the
per-page ``aweme_id``/``count``/``cursor``) reliably returns comments. This
provider therefore emits the minimal set. The signed tokens the browser
computes (``X-Gnarly``, ``X-Dynosaur``, ``X-Bogus``, ``msToken``, ...) cannot
be reproduced outside the page and are intentionally omitted; the API does
not require them for this endpoint. Every observed-but-omitted value is
logged during session capture instead of being invented.
"""

import re
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlparse

from config import BROWSER_HEADLESS, BROWSER_NAVIGATION_TIMEOUT_MS, DEFAULT_POST_URL
from services.session.base import SessionData, SessionProvider

# TikTok web platform constants (not per-session dynamic values).
_WEB_AID = "1988"
_WEB_APP_NAME = "tiktok_web"
_WEB_DEVICE_PLATFORM = "web_pc"
_WEB_BROWSER_NAME = "Mozilla"

# Query params the comments API requires. ``app_language`` is added from the
# captured browser language; ``aweme_id``/``count``/``cursor`` are added per
# page by the HTTP layer.
_QUERY_PARAMS: Dict[str, str] = {
    "aid": _WEB_AID,
    "app_name": _WEB_APP_NAME,
}

# Maps observable cookie/local storage names to a canonical id name.
_COOKIE_ID_KEYS: tuple = (
    ("device_id", "device_id"),
    ("odin_id", "odinId"),
    ("odinid", "odinId"),
    ("webid", "WebId"),
    ("s_v_web_id", "s_v_web_id"),
    ("ttwid", "ttwid"),
)

# JavaScript run inside the loaded page to capture browser/device facts.
_FACTS_SCRIPT = """() => {
    const read = (k) => {
        try {
            const v = window[k];
            return (v !== undefined && v !== null) ? String(v) : null;
        } catch (e) {
            return null;
        }
    };
    const readLocal = (k) => {
        try {
            const v = window.localStorage.getItem(k);
            return (v !== null && v !== '') ? v : null;
        } catch (e) {
            return null;
        }
    };
    const readQuery = (k) => {
        try {
            return new URLSearchParams(window.location.search).get(k);
        } catch (e) {
            return null;
        }
    };
    const ids = {};
    for (const key of ['device_id', 'web_id', 'odinId', 'odin_id', 'ttwid']) {
        const value = read(key) || readLocal(key) || readQuery(key);
        if (value) ids[key] = value;
    }
    const uaData = window.navigator.userAgentData;
    return {
        user_agent: navigator.userAgent,
        platform: navigator.platform || '',
        language: navigator.language || '',
        languages: navigator.languages || [],
        online: navigator.onLine,
        cookie_enabled: navigator.cookieEnabled,
        focus_state: document.hasFocus(),
        page_visible: !document.hidden,
        screen_width: String(screen.width),
        screen_height: String(screen.height),
        viewport_width: String(window.innerWidth),
        viewport_height: String(window.innerHeight),
        device_pixel_ratio: String(window.devicePixelRatio || 1),
        history_len: String(history.length),
        tz_name: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
        mobile: uaData && uaData.mobile ? true : false,
        ids: ids,
    };
}"""

_CHROME_UA_PATTERN = re.compile(r"(?:Headless)?Chrome/(\d+\.\d+\.\d+\.\d+)")


class BrowserSessionError(Exception):
    """Raised when a browser session cannot be established."""


def _browser_version(user_agent: str) -> str:
    """Strip the leading ``Mozilla/`` product token from a user-agent."""
    if user_agent.startswith("Mozilla/"):
        return user_agent[len("Mozilla/"):]
    return user_agent


def _chrome_version(user_agent: str) -> str:
    """Extract the ``Chrome/x.y.z.w`` (or ``HeadlessChrome/``) version token."""
    match = _CHROME_UA_PATTERN.search(user_agent)
    return match.group(1) if match else ""


def _os_from_platform(platform: str) -> str:
    """Map a navigator platform string to a short OS identifier."""
    lower = platform.lower()
    if "win" in lower:
        return "windows"
    if "mac" in lower:
        return "macos"
    if "linux" in lower:
        return "linux"
    return platform


def _primary_language(language: str) -> str:
    """Reduce a locale like ``en-US`` to its primary tag ``en``."""
    return language.split("-")[0].split("_")[0].lower()


def _accept_language(primary: str, languages: List[str]) -> str:
    """Build an ``Accept-Language`` header from navigator languages."""
    ordered = languages or [primary]
    parts: List[str] = []
    for index, language in enumerate(ordered):
        if index == 0:
            parts.append(language)
        else:
            quality = max(0.1, 1.0 - index * 0.1)
            parts.append(f"{language};q={quality:.1f}")
    return ", ".join(parts)


def _sec_ch_ua(user_agent: str) -> str:
    """Approximate Chrome's ``sec-ch-ua`` header from the user-agent."""
    version = _chrome_version(user_agent)
    if not version:
        return ""
    major = version.split(".")[0]
    if "HeadlessChrome" in user_agent:
        return (
            f'"HeadlessChrome";v="{major}", "Not.A/Brand";v="8", '
            f'"Chromium";v="{major}"'
        )
    return (
        f'"Google Chrome";v="{major}", "Chromium";v="{major}", '
        f'"Not=A?Brand";v="99"'
    )


def _sec_ch_ua_platform(platform: str) -> str:
    """Map a navigator platform string to Chrome's platform header value."""
    lower = platform.lower()
    if "win" in lower:
        return '"Windows"'
    if "mac" in lower:
        return '"macOS"'
    if "linux" in lower:
        return '"Linux"'
    if not platform:
        return '""'
    return f'"{platform}"'


def _ids_from_cookies(cookie_map: Dict[str, str]) -> Dict[str, str]:
    """Extract observable device/web id values from captured cookies."""
    ids: Dict[str, str] = {}
    lower_names = {name.lower(): name for name in cookie_map}
    for needle, key in _COOKIE_ID_KEYS:
        if needle in lower_names:
            ids[key] = cookie_map[lower_names[needle]]
    return ids


class BrowserSessionProvider(SessionProvider):
    """Session provider backed by a real browser (Playwright).

    Args:
        video_url: TikTok video page the browser visits to collect the
            session. Defaults to ``config.DEFAULT_POST_URL``.
    """

    def __init__(self, video_url: str = DEFAULT_POST_URL) -> None:
        self._video_url = video_url
        self._session = None

    def get_session(self) -> SessionData:
        """Return the browser-captured session, capturing it on first use."""
        if self._session is None:
            self._session = self._capture_session()
        return self._session

    def refresh_session(self) -> SessionData:
        """Launch a fresh browser session and return its data."""
        self._session = self._capture_session()
        return self._session

    def validate_session(self) -> bool:
        """Return ``True`` when the session has cookies and a user-agent."""
        session = self.get_session()
        if not session.cookies:
            return False
        if not session.user_agent:
            return False
        return True

    def _capture_session(self) -> SessionData:
        """Launch the browser, collect session data, and close it cleanly."""
        print("Launching browser session...")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserSessionError(
                "Playwright is not installed. Install it with `pip install playwright`."
            ) from exc

        observed = {}

        def _is_api_request(request: Any) -> bool:
            return "/api/" in request.url and "aid=1988" in request.url

        def _on_request(request: Any) -> None:
            if _is_api_request(request) and "url" not in observed:
                observed["url"] = request.url
                observed["headers"] = dict(request.headers)

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=BROWSER_HEADLESS)
                except Exception as exc:
                    raise BrowserSessionError(
                        f"Browser failed to start: {exc}"
                    ) from exc

                print("Browser started")

                try:
                    context = browser.new_context()
                    page = context.new_page()
                    page.on("request", _on_request)
                    try:
                        page.goto(
                            self._video_url,
                            wait_until="load",
                            timeout=BROWSER_NAVIGATION_TIMEOUT_MS,
                        )
                    except Exception:
                        page.goto(
                            self._video_url,
                            wait_until="domcontentloaded",
                            timeout=BROWSER_NAVIGATION_TIMEOUT_MS,
                        )
                    print("TikTok page loaded")

                    # Wait for the browser's own API request so the session can
                    # be compared with the real browser request.
                    if "url" not in observed:
                        try:
                            with page.expect_request(
                                _is_api_request,
                                timeout=8000,
                            ) as info:
                                pass
                            req = info.value
                            observed["url"] = req.url
                            observed["headers"] = dict(req.headers)
                        except Exception:
                            pass

                    cookies = context.cookies()
                    if not cookies:
                        raise BrowserSessionError(
                            "Could not collect cookies from the browser context"
                        )
                    print("Cookies collected")

                    facts = page.evaluate(_FACTS_SCRIPT)
                    session = self._build_session(cookies, facts)
                    self._log_comparison(observed, session)
                    print("Session created")
                finally:
                    browser.close()
                    print("Browser closed")

                return session
        except BrowserSessionError:
            raise
        except Exception as exc:
            raise BrowserSessionError(f"Browser session failed: {exc}") from exc

    def _build_session(
        self, cookies: List[Dict[str, Any]], facts: Dict[str, Any]
    ) -> SessionData:
        """Compose a :class:`SessionData` from captured cookies and facts."""
        cookie_map = {
            cookie["name"]: cookie["value"]
            for cookie in cookies
            if "tiktok.com" in cookie.get("domain", "")
        }

        cookie_ids = _ids_from_cookies(cookie_map)
        ids: Dict[str, str] = dict(facts.get("ids") or {})
        for key, value in cookie_ids.items():
            ids.setdefault(key, value)

        user_agent = facts.get("user_agent") or ""
        platform = facts.get("platform") or ""
        language = facts.get("language") or "en-US"
        tz_name = facts.get("tz_name") or ""

        browser_info: Dict[str, str] = {
            "browser_name": _WEB_BROWSER_NAME,
            "browser_version": _browser_version(user_agent),
            "browser_language": language,
            "browser_platform": platform,
            "browser_online": str(facts.get("online", True)).lower(),
            "screen_width": str(facts.get("screen_width") or ""),
            "screen_height": str(facts.get("screen_height") or ""),
            "viewport_width": str(facts.get("viewport_width") or ""),
            "viewport_height": str(facts.get("viewport_height") or ""),
            "device_pixel_ratio": str(facts.get("device_pixel_ratio") or "1"),
            "history_len": str(facts.get("history_len") or ""),
            "ids": ids,
        }

        device_info: Dict[str, str] = {
            "os": _os_from_platform(platform),
            "tz_name": tz_name,
            "device_id": ids.get("device_id", ""),
            "odinId": ids.get("odinId", ""),
            "ttwid": ids.get("ttwid", ""),
        }

        return SessionData(
            headers=self._build_headers(facts, user_agent, language, platform),
            cookies=cookie_map,
            query_params=self._build_query_params(facts),
            browser_info=browser_info,
            device_info=device_info,
            user_agent=user_agent,
        )

    def _build_headers(
        self, facts: Dict[str, Any], user_agent: str, language: str, platform: str
    ) -> Dict[str, str]:
        """Build the request headers from the captured browser session."""
        languages = facts.get("languages") or []
        mobile = bool(facts.get("mobile", False))
        sec_ch_ua = _sec_ch_ua(user_agent)

        headers: Dict[str, str] = {
            "accept": "*/*",
            "accept-language": _accept_language(language, languages),
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": self._video_url,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-ch-ua-mobile": "?1" if mobile else "?0",
            "sec-ch-ua-platform": _sec_ch_ua_platform(platform),
            "user-agent": user_agent,
        }

        if sec_ch_ua:
            headers["sec-ch-ua"] = sec_ch_ua

        return headers

    def _build_query_params(self, facts: Dict[str, Any]) -> Dict[str, str]:
        """Build the comments API query parameters from browser facts.

        Only the parameters the live comments API accepts are emitted. The
        full parameter set the browser's own requests carry makes the
        endpoint return an empty body, so everything beyond this minimal set
        is intentionally omitted and reported in the session comparison.
        """
        language = facts.get("language") or "en-US"
        params: Dict[str, str] = dict(_QUERY_PARAMS)
        params["app_language"] = _primary_language(language)
        return params

    def _log_comparison(
        self, observed: Dict[str, Any], session: SessionData
    ) -> None:
        """Log observed browser request values vs the session we build.

        Parameters the browser sends that we cannot reproduce (signed tokens,
        device ids, ...) are reported as omitted rather than invented.
        """
        if not observed:
            print("No browser API request observed; comparison skipped")
            return

        browser_params = dict(parse_qsl(urlparse(observed["url"]).query))
        print("--- Session comparison vs browser request ---")
        print(f"Observed browser request: {observed['url'][:120]}...")

        for key in sorted(browser_params):
            status = "reproduced" if key in session.query_params else "omitted"
            print(f"  param {key:<22} {status}")

        print("Headers sent by session:")
        for key in sorted(session.headers):
            print(f"  {key}")
        print("--------------------------------------------")
