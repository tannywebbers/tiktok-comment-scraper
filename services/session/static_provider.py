"""Static session provider.

Holds every request value that used to be hardcoded in the monolithic script:
device ids, browser fingerprint, region, timezone, language and the signed
request tokens (``msToken``, ``X-Bogus``, ``_signature``). The HTTP layer
never sees these values directly; it only receives a :class:`SessionData`
object.
"""

from typing import Dict

from services.session.base import SessionData, SessionProvider

# HTTP headers sent with every request.
_HEADERS: Dict[str, str] = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9,fa;q=0.8",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://www.tiktok.com/explore",
    "sec-ch-ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
}

# Static query parameters for the comments API. Values are the decoded
# originals; ``requests`` re-encodes them equivalently when the URL is built.
_QUERY_PARAMS: Dict[str, str] = {
    "WebIdLastTime": "1729273214",
    "aid": "1988",
    "app_language": "en",
    "app_name": "tiktok_web",
    "browser_language": "en-US",
    "browser_name": "Mozilla",
    "browser_online": "true",
    "browser_platform": "Win32",
    "browser_version": (
        "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "channel": "tiktok_web",
    "cookie_enabled": "true",
    "data_collection_enabled": "false",
    "device_id": "7427171842932786693",
    "device_platform": "web_pc",
    "focus_state": "true",
    "from_page": "video",
    "history_len": "6",
    "is_fullscreen": "false",
    "is_page_visible": "true",
    "odinId": "7427171704705188869",
    "os": "windows",
    "priority_region": "",
    "referer": "",
    "region": "CA",
    "screen_height": "1080",
    "screen_width": "1920",
    "tz_name": "Asia/Tehran",
    "user_is_login": "false",
    "webcast_language": "en",
    "msToken": (
        "U488DBL2ELMV88PxvXu7bOKQJVxuv7LnhKNHsWaOT2uQhpGyj5M-7EmUsXBIS9HbQ"
        "_bQ35u3Za-f_hVhHMMYsH-4mxWPeJoUeMhgOHOvQ-IaKb5lr3DlgBIYJXCUc9MCexCHXig1u4a98hVjnec74fs="
    ),
    "X-Bogus": "DFSzswVYtfhANH-ltQ2xJbJ92U6T",
    "_signature": "_02B4Z6wo000017DRplgAAIDBt3uT.9qT9Zew0aLAAIsv87",
}

_BROWSER_KEYS: tuple = (
    "browser_name",
    "browser_version",
    "browser_language",
    "browser_platform",
    "browser_online",
    "screen_width",
    "screen_height",
    "focus_state",
    "is_fullscreen",
    "is_page_visible",
)

_DEVICE_KEYS: tuple = (
    "device_id",
    "device_platform",
    "odinId",
    "os",
    "region",
    "tz_name",
)

_TOKEN_KEYS: tuple = ("msToken", "X-Bogus", "_signature")

_REQUIRED_KEYS: tuple = ("msToken", "X-Bogus", "_signature", "device_id", "odinId", "WebIdLastTime")


class StaticSessionProvider(SessionProvider):
    """Provides a fixed session built from browser-captured values."""

    def __init__(self) -> None:
        self._session = SessionData(
            headers=dict(_HEADERS),
            cookies={},
            query_params=dict(_QUERY_PARAMS),
            browser_info={key: _QUERY_PARAMS[key] for key in _BROWSER_KEYS},
            device_info={key: _QUERY_PARAMS[key] for key in _DEVICE_KEYS},
            user_agent=_HEADERS["user-agent"],
            tokens={key: _QUERY_PARAMS[key] for key in _TOKEN_KEYS},
        )

    def get_session(self) -> SessionData:
        """Return the static session."""
        return self._session

    def refresh_session(self) -> SessionData:
        """Return the static session unchanged."""
        return self._session

    def validate_session(self) -> bool:
        """Return ``True`` when the session carries headers and required tokens."""
        if not self._session.headers or not self._session.query_params:
            return False

        return all(
            key in self._session.query_params and self._session.query_params[key]
            for key in _REQUIRED_KEYS
        )
