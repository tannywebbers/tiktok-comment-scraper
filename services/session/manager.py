"""Manages the active session and the provider that supplies it.

Provider selection is driven by ``config.SESSION_PROVIDER`` so the provider
can be swapped (e.g. static -> browser) without touching the HTTP layer.
"""

from config import DEFAULT_POST_URL, SESSION_PROVIDER
from services.session.base import SessionData, SessionProvider, SessionValidationError
from services.session.browser_provider import BrowserSessionProvider
from services.session.static_provider import StaticSessionProvider

# Name of the provider used when no explicit name is given.
PROVIDER_NAME = SESSION_PROVIDER


def build_provider(
    name: str = PROVIDER_NAME, video_url: str = DEFAULT_POST_URL
) -> SessionProvider:
    """Instantiate the session provider selected by ``name``.

    Args:
        name: Identifier of the provider to build (``"static"`` or
            ``"browser"``).
        video_url: Video page the browser provider visits to collect a session.

    Returns:
        A configured :class:`SessionProvider`.

    Raises:
        ValueError: If ``name`` does not match a known provider.
    """
    if name == "static":
        return StaticSessionProvider()
    if name == "browser":
        return BrowserSessionProvider(video_url=video_url)

    raise ValueError(f"Unknown session provider: {name!r}")


def create_session_manager(video_url: str = DEFAULT_POST_URL) -> "SessionManager":
    """Build a :class:`SessionManager` wired to the configured provider.

    Args:
        video_url: Video page the browser provider visits to collect a
            session. Defaults to ``config.DEFAULT_POST_URL`` for local
            development; production callers always pass the real URL.
    """
    return SessionManager(build_provider(PROVIDER_NAME, video_url=video_url))


class SessionManager:
    """Caches the active session and validates it on behalf of the HTTP layer."""

    def __init__(self, provider: SessionProvider) -> None:
        self._provider = provider
        self._session = None
        print(f"Using provider: {type(provider).__name__}")

    def get_session(self) -> SessionData:
        """Return the cached session, building it from the provider on first use."""
        if self._session is None:
            self._session = self._provider.get_session()
        return self._session

    def refresh(self) -> SessionData:
        """Replace the cached session with a fresh one from the provider."""
        self._session = self._provider.refresh_session()
        return self._session

    def validate(self) -> bool:
        """Validate the active session, raising on failure.

        Returns:
            ``True`` when the session is valid.

        Raises:
            SessionValidationError: If the provider reports an invalid session.
        """
        if not self._provider.validate_session():
            raise SessionValidationError("Active session failed validation")

        print("Session validated")
        return True
