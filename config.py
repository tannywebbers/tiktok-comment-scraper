"""Central configuration for the TikTok comment scraper.

Deployment-tunable values are read from environment variables so the same
codebase runs locally and on Render without edits. Every value keeps a safe
production default; set the matching environment variable to override it.

Browser and session values (headers, tokens, device ids, timezone, ...) are
owned by the session provider and intentionally not defined here.
"""

import os


def _env_bool(name: str, default: bool) -> bool:
    """Parse ``name`` as a boolean env var, falling back to ``default``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """Parse ``name`` as an integer env var, falling back to ``default``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Base URL of the TikTok comments API.
BASE_URL = "https://www.tiktok.com/api/comment/list/"

# Number of comments requested per API page. This drives both the ``count``
# query parameter and the cursor increment between pages.
PAGE_SIZE = 20

# Timeout in seconds for each HTTP request to the comments API.
REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", 30)

# Whether ``scrape_comments`` (and therefore the API) writes results to
# ``OUTPUT_FILE``. Debug only; normal execution never touches the filesystem.
SAVE_OUTPUT_JSON = _env_bool("SAVE_OUTPUT_JSON", False)

# File written when ``SAVE_OUTPUT_JSON`` is enabled.
OUTPUT_FILE = "output.json"

# Maximum number of attempts per comments page request.
MAX_ATTEMPTS = 3

# Exponential backoff (seconds) between retries of a transient failure.
RETRY_DELAYS = (1, 2, 4)

# Version reported by the health endpoint and API metadata.
API_VERSION = os.environ.get("API_VERSION", "1.0.0")

# FastAPI debug mode. Always off in production; structured error responses
# never expose stack traces regardless of this flag.
DEBUG = _env_bool("DEBUG", False)

# Root logging level for the API service.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Directory where the diagnostics layer writes request/response logs.
LOGS_DIR = "logs"

# File, inside LOGS_DIR, where the analyzer writes its response report.
ANALYSIS_OUTPUT = "analysis_report.json"

# Default post URL used when no argument is passed on the command line.
# Local development only; the API always requires a URL from the caller.
DEFAULT_POST_URL = "https://www.tiktok.com/@cakesbydammie_yyc/video/7401564223328881926"

# Session provider used by the HTTP layer: "browser" or "static".
# The browser provider reproduces the current browser session; "static"
# remains only as a legacy fallback for the 2024 hardcoded request.
SESSION_PROVIDER = "browser"

# Whether the browser provider runs headless (no visible window).
BROWSER_HEADLESS = _env_bool("PLAYWRIGHT_HEADLESS", True)

# Navigation timeout for the browser provider, in milliseconds.
BROWSER_NAVIGATION_TIMEOUT_MS = 60000
