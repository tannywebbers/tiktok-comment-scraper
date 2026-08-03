"""Safe parsing of TikTok comments API responses."""

from typing import Any, Dict, List

from models.comment import Comment


def parse_comments(raw_data: Dict[str, Any]) -> List[Comment]:
    """Parse a TikTok comments response into structured Comment objects.

    Parsing is defensive: missing fields fall back to safe defaults and this
    function never raises ``KeyError``.

    Args:
        raw_data: JSON payload returned by the comments API.

    Returns:
        A list of ``Comment`` objects in the order they appear in the payload.
    """
    result: List[Comment] = []

    if not isinstance(raw_data, dict):
        return result

    for comment_data in raw_data.get("comments", []):
        user = comment_data.get("user", {})
        text = comment_data.get("text", "")
        if not text:
            text = comment_data.get("share_info", {}).get("desc", "")

        result.append(
            Comment(
                comment_id=str(comment_data.get("cid", "")),
                username=user.get("unique_id", ""),
                nickname=user.get("nickname", ""),
                text=text,
                create_time=comment_data.get("create_time", 0),
            )
        )

    return result


def has_more(raw_data: Dict[str, Any]) -> bool:
    """Report whether the API says more comment pages remain.

    Args:
        raw_data: JSON payload returned by the comments API.

    Returns:
        ``True`` if the ``has_more`` flag is set, ``False`` otherwise.
    """
    if not isinstance(raw_data, dict):
        return False

    return raw_data.get("has_more", 0) == 1
