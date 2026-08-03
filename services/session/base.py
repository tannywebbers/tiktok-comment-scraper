"""Session abstractions for the TikTok comment scraper.

This module defines the data structure a session provider hands to the HTTP
layer and the interface every provider must implement. Concrete providers
live in sibling modules (e.g. ``static_provider``).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


class SessionValidationError(Exception):
    """Raised when an active session fails validation."""


@dataclass
class SessionData:
    """Everything the HTTP layer needs to build an authenticated request.

    Attributes:
        headers: HTTP headers sent with every request.
        cookies: HTTP cookies attached to every request.
        query_params: Static query parameters for the comments API. The
            per-request values (``aweme_id``, ``count``, ``cursor``) are added
            by the HTTP layer.
        browser_info: Browser identity and UI state used to fingerprint the
            session.
        device_info: Device identity and locale information.
        user_agent: The user-agent reported by the session's browser.
        tokens: Signed request tokens (``msToken``, ``X-Bogus``,
            ``_signature``).
    """

    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, Any] = field(default_factory=dict)
    browser_info: Dict[str, Any] = field(default_factory=dict)
    device_info: Dict[str, Any] = field(default_factory=dict)
    user_agent: str = ""
    tokens: Dict[str, str] = field(default_factory=dict)


class SessionProvider(ABC):
    """Interface for providers that supply request sessions."""

    @abstractmethod
    def get_session(self) -> SessionData:
        """Return a usable session."""

    @abstractmethod
    def refresh_session(self) -> SessionData:
        """Return a fresh session, replacing any cached one."""

    @abstractmethod
    def validate_session(self) -> bool:
        """Return ``True`` if the active session is valid, ``False`` otherwise."""
