"""Pydantic request and response schemas for the comment API.

The schemas mirror the public API contract: a single ``POST /comments``
endpoint and a lightweight health endpoint.
"""

from typing import List

from pydantic import BaseModel, Field


class CommentItem(BaseModel):
    """A single scraped comment."""

    comment_id: str
    username: str
    nickname: str
    text: str
    create_time: int


class CommentRequest(BaseModel):
    """Request body for ``POST /comments``."""

    url: str = Field(
        ...,
        min_length=1,
        description="Full TikTok video URL, e.g. "
        "https://www.tiktok.com/@user/video/123456789",
    )


class CommentResponse(BaseModel):
    """Successful response for ``POST /comments``."""

    success: bool
    request_id: str
    video_id: str
    comment_count: int
    elapsed_ms: int
    comments: List[CommentItem]


class ErrorDetail(BaseModel):
    """Structured error details."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Error response body shared by every failing request."""

    success: bool
    request_id: str
    error: ErrorDetail


class HealthResponse(BaseModel):
    """Response body for ``GET /health``."""

    status: str
    version: str
