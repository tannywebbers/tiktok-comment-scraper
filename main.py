"""FastAPI application entry point for the TikTok comment scraper.

Run locally::

    uvicorn main:app --host 0.0.0.0 --port 10000

or ``python main.py``. The port defaults to ``PORT`` (Render sets it) and
falls back to 10000.
"""

import logging
import os
import platform
import sys
import uuid

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.exceptions import register_exception_handlers
from app.api.routes import router
from config import API_VERSION, BROWSER_HEADLESS, DEBUG, LOG_LEVEL, SESSION_PROVIDER

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Set the root logging level from configuration."""
    level = logging.DEBUG if DEBUG else LOG_LEVEL
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a UUID request ID to every request and response.

    The ID is stored on ``request.state.request_id`` so routes and exception
    handlers can echo it in the response body, and it is also returned in the
    ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        logger.debug(
            "Request started request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="TikTok Comment Scraper API",
        description="REST API for retrieving structured TikTok comments.",
        version=API_VERSION,
        debug=DEBUG,
    )
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    app.include_router(router)
    return app


_configure_logging()
app = create_app()

logger.info("TikTok Comment Scraper API started")
logger.info("API version: %s", API_VERSION)
logger.info("Python version: %s", platform.python_version())
logger.info("Session provider: %s", SESSION_PROVIDER)
logger.info("Debug mode: %s", DEBUG)
logger.info("Headless mode: %s", BROWSER_HEADLESS)

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        sys.exit("uvicorn is required to run the server: pip install uvicorn")
    port = int(os.environ.get("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
