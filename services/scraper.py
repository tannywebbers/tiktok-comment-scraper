"""Public entry point for scraping TikTok comments.

This module exposes :func:`scrape_comments`, the single reusable function
that drives a complete scrape. Every call is fully independent: it validates
the URL, creates its own browser session, paginates and deduplicates the
comments, and returns a :class:`ScrapeResult`. No global mutable state is
shared between executions, so concurrent requests are safe.
"""

import json
import time
from typing import List, Tuple

from config import (
    MAX_ATTEMPTS,
    OUTPUT_FILE,
    PAGE_SIZE,
    RETRY_DELAYS,
    SAVE_OUTPUT_JSON,
)
from models.comment import Comment
from models.result import ScrapeError, ScrapeResult
from services.comments import TikTokRequestError, fetch_comments
from services.parser import has_more, parse_comments
from services.session.base import SessionValidationError
from services.session.browser_provider import BrowserSessionError
from services.session.manager import SessionManager, create_session_manager
from utils.extractor import VideoUrlError, validate_video_url


def _error_code(exc: Exception) -> str:
    """Map an exception to a machine-readable error code."""
    if isinstance(exc, VideoUrlError):
        return exc.code
    if isinstance(exc, (SessionValidationError, BrowserSessionError)):
        return "SESSION_ERROR"
    if isinstance(exc, TikTokRequestError):
        if exc.code:
            return exc.code
        if exc.status_code is not None:
            return f"HTTP_{exc.status_code}"
        return "REQUEST_FAILED"
    return "INTERNAL_ERROR"


def _elapsed_ms(started: float) -> int:
    """Return wall-clock milliseconds elapsed since ``started``."""
    return int((time.perf_counter() - started) * 1000)


def _request_page(
    session_manager: SessionManager, post_id: str, cursor: int
) -> Tuple[dict, int]:
    """Fetch one page, retrying transient failures with exponential backoff.

    Args:
        session_manager: Session manager for this scrape execution.
        post_id: Numeric TikTok video ID.
        cursor: Pagination cursor for the page to fetch.

    Returns:
        The parsed JSON payload and the number of retries performed.

    Raises:
        TikTokRequestError: If the page could not be fetched after all
            attempts, or the failure is not retryable.
    """
    retries = 0
    for attempt in range(MAX_ATTEMPTS):
        try:
            data = fetch_comments(post_id, cursor, session_manager)
            return data, retries
        except TikTokRequestError as exc:
            exc.attempts = attempt + 1
            if not exc.retryable or attempt == MAX_ATTEMPTS - 1:
                raise
            retries += 1
            delay = RETRY_DELAYS[attempt]
            print(
                f"Transient failure, retrying in {delay}s "
                f"(retry {retries}/{MAX_ATTEMPTS - 1})"
            )
            time.sleep(delay)

    raise TikTokRequestError("Exhausted retry attempts")


def _write_output_json(result: ScrapeResult) -> None:
    """Write the scrape result to ``output.json`` (debug only)."""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=4)


def _log_summary(
    result: ScrapeResult, request_count: int, retry_count: int
) -> None:
    """Print the concise production summary for one scrape."""
    print(f"Video ID: {result.video_id or 'unknown'}")
    print(f"Request count: {request_count}")
    print(f"Comments fetched: {result.comment_count}")
    print(f"Elapsed time: {result.elapsed_ms} ms")
    print(f"Retry count: {retry_count}")
    if result.success:
        print("Success: True")
    else:
        print("Success: False")
        print(f"Error: {result.error.message if result.error else 'unknown'}")
    print("------------------------------------------")


def scrape_comments(
    video_url: str, save_output_json: bool = SAVE_OUTPUT_JSON
) -> ScrapeResult:
    """Scrape every comment of a TikTok video.

    Each call is independent and concurrency-safe: it creates its own browser
    session and its own pagination and deduplication state. The video URL is
    always supplied by the caller.

    Args:
        video_url: Full TikTok video URL (e.g.
            ``https://www.tiktok.com/@user/video/<id>``).
        save_output_json: When ``True``, also write the result to
            ``output.json``. Defaults to ``config.SAVE_OUTPUT_JSON`` and is
            debug only.

    Returns:
        A :class:`ScrapeResult`. Failures are returned as ``success=False``
        with a structured error, never raised.
    """
    started = time.perf_counter()
    request_count = 0
    retry_count = 0

    print("------------------------------------------")
    print("Scrape started")

    try:
        video_id = validate_video_url(video_url)
    except VideoUrlError as exc:
        result = ScrapeResult(
            success=False,
            elapsed_ms=_elapsed_ms(started),
            error=ScrapeError(code=exc.code, message=str(exc)),
        )
        _log_summary(result, request_count, retry_count)
        return result

    comments: List[Comment] = []
    seen_ids: set = set()
    cursor = 0

    try:
        session_manager = create_session_manager(video_url=video_url)

        while True:
            try:
                data, retries = _request_page(session_manager, video_id, cursor)
            except TikTokRequestError as exc:
                request_count += getattr(exc, "attempts", 1)
                raise
            request_count += retries + 1
            retry_count += retries

            for comment in parse_comments(data):
                if comment.comment_id in seen_ids:
                    continue
                seen_ids.add(comment.comment_id)
                comments.append(comment)

            if has_more(data):
                cursor += PAGE_SIZE
            else:
                break

        result = ScrapeResult(
            success=True,
            video_id=video_id,
            comment_count=len(comments),
            elapsed_ms=_elapsed_ms(started),
            retry_count=retry_count,
            comments=comments,
        )
    except (TikTokRequestError, SessionValidationError, BrowserSessionError) as exc:
        result = ScrapeResult(
            success=False,
            video_id=video_id,
            elapsed_ms=_elapsed_ms(started),
            retry_count=retry_count,
            error=ScrapeError(code=_error_code(exc), message=str(exc)),
        )
    except Exception as exc:  # noqa: BLE001
        result = ScrapeResult(
            success=False,
            video_id=video_id,
            elapsed_ms=_elapsed_ms(started),
            retry_count=retry_count,
            error=ScrapeError(code="INTERNAL_ERROR", message=str(exc)),
        )

    if result.success and save_output_json:
        _write_output_json(result)

    _log_summary(result, request_count, retry_count)
    return result
