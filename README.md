# TikTok Comment Scraper API

A production-ready FastAPI service that scrapes live comments from TikTok
videos and returns them as structured JSON.

The scraping engine lives in the `services/` package and is fully independent
of FastAPI. The `app/` package is a thin HTTP layer: it validates the request,
calls `scrape_comments(video_url)`, and shapes the response. The scraper is
stateless and concurrency-safe — every request builds its own browser session
and its own pagination/deduplication state.

## Features

- `POST /comments` — scrape and return every comment of a TikTok video
- `GET /health` — lightweight liveness probe (never launches a browser)
- Automatic retry with exponential backoff for transient TikTok failures
- Deduplication by comment ID across pages
- Structured JSON errors (never stack traces)
- Per-request UUIDs echoed in the body and `X-Request-ID` header
- Concurrency-safe: each request is fully isolated

## Installation

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Local development

Scrape a video from the command line (no server required):

```bash
python cli.py "https://www.tiktok.com/@user/video/123456789"
```

Run the test suites:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 10000   # run the server, then:
```

Interactive API docs are available at:

- Swagger UI: `http://localhost:10000/docs`
- ReDoc: `http://localhost:10000/redoc`

## Running the API

```bash
uvicorn main:app --host 0.0.0.0 --port 10000
```

or, using the built-in runner:

```bash
python main.py            # port from $PORT, defaults to 10000
```

## API endpoints

### `GET /health`

Returns the service status without any scraping.

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

### `POST /comments`

Scrapes the comments of a TikTok video.

Request body:

```json
{
  "url": "https://www.tiktok.com/@user/video/123456789"
}
```

Sample request:

```bash
curl -X POST http://localhost:10000/comments \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.tiktok.com/@user/video/123456789"}'
```

#### Success (200)

```json
{
  "success": true,
  "request_id": "2f4c0e6a-8b7d-4a5e-9c1f-3d8e2a1b0c9d",
  "video_id": "123456789",
  "comment_count": 483,
  "elapsed_ms": 6217,
  "comments": [
    {
      "comment_id": "7391234567890123456",
      "username": "user_handle",
      "nickname": "Display Name",
      "text": "Love this video!",
      "create_time": 1784230607
    }
  ]
}
```

#### Errors

| Status | Code              | Body `error.message`                                        |
|--------|-------------------|-------------------------------------------------------------|
| 400    | `INVALID_URL`     | Invalid TikTok video URL.                                   |
| 404    | `VIDEO_NOT_FOUND` | Unable to retrieve comments for this video.                 |
| 429    | `RATE_LIMITED`    | TikTok temporarily rejected the request.                    |
| 500    | `INTERNAL_ERROR`  | Unexpected server error.                                    |

Example error response:

```json
{
  "success": false,
  "request_id": "4f2d0c7a-9b3e-4d1f-a5c2-6e8b1f3a0d7e",
  "error": {
    "code": "INVALID_URL",
    "message": "Invalid TikTok video URL."
  }
}
```

## Environment variables

All values have safe production defaults; set the matching variable to
override.

| Variable              | Default     | Description                                              |
|-----------------------|-------------|----------------------------------------------------------|
| `DEBUG`               | `false`     | FastAPI debug mode. Never affects error responses.       |
| `LOG_LEVEL`           | `INFO`      | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).    |
| `API_VERSION`         | `1.0.0`     | Version reported by `/health` and OpenAPI metadata.      |
| `SAVE_OUTPUT_JSON`    | `false`     | Write scrape results to `output.json` (debug only).      |
| `PLAYWRIGHT_HEADLESS` | `true`      | Run the session browser headless.                        |
| `REQUEST_TIMEOUT`     | `30`        | HTTP timeout in seconds per comments page request.       |
| `PORT`                | `10000`     | Port used by `python main.py` (Render sets this).        |

## Architecture

```
main.py                  FastAPI app, startup logging, request-ID middleware
app/api/routes.py        POST /comments, GET /health
app/api/models.py        Pydantic request/response schemas
app/api/exceptions.py    Structured error hierarchy + exception handlers
services/scraper.py      scrape_comments(video_url) -> ScrapeResult
services/comments.py     HTTP layer (retryable, session-scoped requests)
services/parser.py       Defensive JSON -> Comment parsing
services/session/        Browser/static session providers + manager
services/diagnostics/    Request/response inspectors and recorder
services/analyzer/       Response analysis engine
models/                  Comment, ScrapeResult
utils/extractor.py       TikTok URL validation and video-ID extraction
cli.py                   Command-line scraper for local development
```

## Deployment on Render

Two options:

### Option A — Render Blueprint (recommended)

A `render.yaml` blueprint is included. Push this repository to GitHub, then in
Render choose **New > Blueprint** and select the repo. Render will create the
service with:

- Build: `bash build.sh`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

### Option B — Manual Web Service

1. Create a new **Web Service** and connect the repository.
2. **Runtime**: Python 3.13
3. **Build command**: `bash build.sh`
4. **Start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Health check path**: `/health`
6. Optional env vars: `LOG_LEVEL=INFO`, `PLAYWRIGHT_HEADLESS=true`,
   `SAVE_OUTPUT_JSON=false`.

Notes:

- The free tier is sufficient for low traffic; each `/comments` request
  launches a short-lived headless Chromium session (closed automatically), so
  memory usage scales with request concurrency.
- No database, authentication, caching, or rate limiting is included by
  design.
