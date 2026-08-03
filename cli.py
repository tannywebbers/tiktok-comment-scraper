"""Command-line entry point for the TikTok comment scraper (local dev).

The scraping logic lives in :func:`services.scraper.scrape_comments`; this
module only wires it to the command line. ``DEFAULT_POST_URL`` is used solely
when no URL is supplied, for local development and testing.

Named ``cli.py`` (not ``app.py``) so it does not collide with the ``app``
package that hosts the FastAPI service (see ``main.py``).
"""

import sys

from config import DEFAULT_POST_URL, SAVE_OUTPUT_JSON
from models.result import ScrapeResult
from services.scraper import scrape_comments


def main(post_url: str) -> ScrapeResult:
    """Scrape every comment of a TikTok video and return the result.

    Args:
        post_url: TikTok URL of the video to scrape.
    """
    return scrape_comments(post_url, save_output_json=SAVE_OUTPUT_JSON)


if __name__ == "__main__":
    post_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_POST_URL

    result = main(post_url)
    if result.success:
        print(
            f"\nScrape complete: {result.comment_count} comments "
            f"in {result.elapsed_ms} ms"
        )
    else:
        print(f"\nERROR: {result.error.message}")
        sys.exit(1)
