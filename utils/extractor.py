"""Extract numeric TikTok video IDs from TikTok URLs.

``validate_video_url`` is the production entry point: it rejects every URL
that is not a full TikTok video URL and returns the numeric video ID.
``extract_video_id`` is kept as a thin compatibility wrapper that raises a
plain :class:`ValueError`.
"""

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

_VIDEO_PATH_PATTERN = re.compile(r"/video/(\d+)")
_EMBED_PATH_PATTERN = re.compile(r"/embed/v\d+/(\d+)")
_SHORT_LINK_PATH_PATTERN = re.compile(r"^/(?:t/)?[\w-]+/?$")
_QUERY_ID_KEYS = ("video_id", "aweme_id", "itemId", "item_id")


class VideoUrlError(ValueError):
    """Raised when a URL is not a valid TikTok video URL.

    Attributes:
        code: Machine-readable error code. One of ``EMPTY_URL``,
            ``MALFORMED_URL``, ``NOT_TIKTOK_URL``, ``SHORT_LINK`` or
            ``NOT_VIDEO_URL``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _extract_id_from_parsed(parsed) -> Optional[str]:
    """Pull a numeric video ID from an already-parsed TikTok URL, if any."""
    for pattern in (_VIDEO_PATH_PATTERN, _EMBED_PATH_PATTERN):
        match = pattern.search(parsed.path)
        if match:
            return match.group(1)

    for key in _QUERY_ID_KEYS:
        values = parse_qs(parsed.query).get(key)
        if values and values[0].isdigit():
            return values[0]

    return None


def validate_video_url(url: str) -> str:
    """Validate ``url`` as a TikTok video URL and return its video ID.

    Accepts full ``https://www.tiktok.com/@user/video/<id>`` URLs, plain
    ``/video/<id>`` URLs, embed URLs, and URLs that carry the ID in a query
    parameter. Rejects empty strings, malformed URLs, non-TikTok URLs, short
    links that need a redirect, and TikTok pages that are not videos.

    Args:
        url: The TikTok video URL to validate.

    Returns:
        The numeric video ID as a string.

    Raises:
        VideoUrlError: With a machine-readable ``code`` when the URL is not a
            valid TikTok video URL.
    """
    if not isinstance(url, str) or not url.strip():
        raise VideoUrlError("EMPTY_URL", "URL must not be empty")

    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise VideoUrlError("MALFORMED_URL", f"Malformed URL: {url!r}")

    if not re.search(r"(^|\.)tiktok\.com$", parsed.netloc, re.IGNORECASE):
        raise VideoUrlError("NOT_TIKTOK_URL", f"Not a TikTok URL: {url!r}")

    if _SHORT_LINK_PATH_PATTERN.match(parsed.path):
        raise VideoUrlError(
            "SHORT_LINK",
            f"Cannot resolve short TikTok link {url!r} without following a "
            "redirect; use the full /@user/video/<id> URL instead.",
        )

    video_id = _extract_id_from_parsed(parsed)
    if video_id is None:
        raise VideoUrlError(
            "NOT_VIDEO_URL", f"Not a TikTok video URL: {url!r}"
        )

    return video_id


def extract_video_id(url: str) -> str:
    """Extract the numeric video ID from any TikTok URL.

    Handles ``/@user/video/<id>``, ``/video/<id>``, embed URLs, and URLs that
    carry the ID in a query parameter.

    Args:
        url: A TikTok video URL.

    Returns:
        The numeric video ID as a string.

    Raises:
        ValueError: If the URL is not a valid TikTok video URL.
    """
    try:
        return validate_video_url(url)
    except VideoUrlError as exc:
        raise ValueError(str(exc)) from exc
