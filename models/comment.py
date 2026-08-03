"""Structured representation of a TikTok comment."""

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class Comment:
    """A single comment scraped from the TikTok comments API.

    Attributes:
        comment_id: The comment's unique identifier (``cid``).
        username: The user's unique handle (``unique_id``).
        nickname: The user's display name (``nickname``).
        text: The comment content. Prefers the raw comment ``text`` field and
            falls back to ``share_info.desc`` when the raw text is empty.
        create_time: Unix timestamp of when the comment was created.
    """

    comment_id: str
    username: str
    nickname: str
    text: str
    create_time: int

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict of this comment."""
        return asdict(self)
