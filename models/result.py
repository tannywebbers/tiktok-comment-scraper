"""Structured result of a single scrape execution."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from models.comment import Comment


@dataclass
class ScrapeError:
    """Error details returned when a scrape fails.

    Attributes:
        code: Machine-readable error code (e.g. ``EMPTY_URL``,
            ``NOT_VIDEO_URL``, ``SESSION_ERROR``, ``HTTP_404``).
        message: Human-readable description of the failure.
    """

    code: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict of this error."""
        return {"code": self.code, "message": self.message}


@dataclass
class ScrapeResult:
    """Result of one independent scrape execution.

    Attributes:
        success: Whether the scrape completed successfully.
        video_id: Numeric TikTok video ID that was scraped.
        comment_count: Number of unique comments collected.
        elapsed_ms: Total wall-clock time of the scrape in milliseconds.
        comments: Collected comments, deduplicated by ``comment_id``.
        error: Error details when ``success`` is ``False``.
    """

    success: bool
    video_id: str = ""
    comment_count: int = 0
    elapsed_ms: int = 0
    retry_count: int = 0
    comments: List[Comment] = field(default_factory=list)
    error: Optional[ScrapeError] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return the public API contract dict for this result.

        Successful results omit ``error``; failed results carry it.
        """
        payload: Dict[str, Any] = {
            "success": self.success,
            "video_id": self.video_id,
            "comment_count": self.comment_count,
            "elapsed_ms": self.elapsed_ms,
            "retry_count": self.retry_count,
            "comments": [comment.to_dict() for comment in self.comments],
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload
