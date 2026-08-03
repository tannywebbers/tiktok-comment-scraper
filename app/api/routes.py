"""API routes for the TikTok comment service.

FastAPI only orchestrates requests and responses here. All scraping logic
lives in ``services.scraper.scrape_comments`` and is reused as-is.

Endpoints are declared as synchronous ``def`` so FastAPI runs them in its
thread pool: each request gets its own thread, its own ``scrape_comments``
call, and therefore its own isolated session and runtime state.
"""

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.api.exceptions import (
    APIError,
    InternalError,
    InvalidURLError,
    RateLimitedError,
    VideoNotFoundError,
)
from app.api.models import (
    CommentItem,
    CommentRequest,
    CommentResponse,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
)
from config import API_VERSION, SAVE_OUTPUT_JSON
from models.result import ScrapeError
from services.scraper import scrape_comments
from utils.extractor import VideoUrlError, validate_video_url

logger = logging.getLogger(__name__)

router = APIRouter()

# Scraper error codes that map to a non-500 HTTP response.
_URL_ERROR_CODES = (
    "EMPTY_URL",
    "MALFORMED_URL",
    "NOT_TIKTOK_URL",
    "SHORT_LINK",
    "NOT_VIDEO_URL",
)


def _to_api_error(error: ScrapeError) -> APIError:
    """Translate a scraper error into an API error response."""
    code = error.code
    if code in _URL_ERROR_CODES:
        return InvalidURLError()
    if code == "HTTP_404":
        return VideoNotFoundError()
    if code == "HTTP_429":
        return RateLimitedError()
    return InternalError()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report service liveness. Never triggers scraping."""
    return HealthResponse(status="ok", version=API_VERSION)


@router.post(
    "/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_200_OK,
)
def create_comments(
    payload: CommentRequest, request: Request
) -> CommentResponse:
    """Scrape and return the comments of a TikTok video.

    The URL is validated before any scraping begins; invalid URLs are
    rejected with HTTP 400. Everything else is delegated to
    :func:`services.scraper.scrape_comments`.
    """
    request_id = str(getattr(request.state, "request_id", ""))

    try:
        video_id = validate_video_url(payload.url)
    except VideoUrlError:
        raise InvalidURLError()

    result = scrape_comments(
        payload.url, save_output_json=SAVE_OUTPUT_JSON
    )

    if not result.success:
        api_error = _to_api_error(result.error)
        logger.info(
            "Scrape request_id=%s video_id=%s elapsed_ms=%d "
            "comment_count=%d retry_count=%d status=%d success=False",
            request_id,
            result.video_id,
            result.elapsed_ms,
            result.comment_count,
            result.retry_count,
            api_error.status_code,
        )
        raise api_error

    logger.info(
        "Scrape request_id=%s video_id=%s elapsed_ms=%d "
        "comment_count=%d retry_count=%d status=200 success=True",
        request_id,
        result.video_id,
        result.elapsed_ms,
        result.comment_count,
        result.retry_count,
    )

    return CommentResponse(
        success=True,
        request_id=request_id,
        video_id=result.video_id,
        comment_count=result.comment_count,
        elapsed_ms=result.elapsed_ms,
        comments=[CommentItem(**comment.to_dict()) for comment in result.comments],
    )


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
def not_found(request: Request, path: str) -> JSONResponse:
    """Return a structured JSON 404 for unmatched routes and methods.

    Starlette's routing layer answers unmatched paths with a plain
    ``{"detail": ...}`` body before the app-level exception handlers run, so
    this catch-all route guarantees the same structured error contract as
    every other response.
    """
    logger.info("Not found request_id=%s method=%s path=%s", request.state.request_id, request.method, path)
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            success=False,
            request_id=str(getattr(request.state, "request_id", "")),
            error=ErrorDetail(code="NOT_FOUND", message="Not Found"),
        ).model_dump(),
    )
