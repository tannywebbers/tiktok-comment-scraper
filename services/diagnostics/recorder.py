"""Persistence for captured request/response diagnostics.

The recorder writes the snapshots captured by the inspectors into a logs
directory. Each record call produces a fixed set of files:
``request.json``, ``response.json``, ``response_headers.json``,
``cookies.json``, ``metadata.json`` and ``raw_response.txt``. When the
response was JSON, ``raw_response.json`` is written as well.
"""

import json
from pathlib import Path
from typing import Any, Dict

from config import LOGS_DIR
from services.diagnostics.inspector import RequestSnapshot, ResponseSnapshot


class DiagnosticsRecorder:
    """Writes request/response snapshots into the logs directory."""

    def __init__(self, log_dir: str = LOGS_DIR) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_dir(self) -> Path:
        """Path of the directory where logs are written."""
        return self._log_dir

    def record(
        self,
        request: RequestSnapshot,
        response: ResponseSnapshot,
    ) -> Path:
        """Persist ``request`` and ``response`` into the logs directory.

        Args:
            request: Captured outgoing request.
            response: Captured received response.

        Returns:
            The logs directory that received the files.
        """
        self._write_json("request.json", request.to_dict())
        self._write_json("response_headers.json", response.headers)
        self._write_json(
            "cookies.json",
            {
                "request_cookies": request.cookies,
                "response_cookies": response.cookies,
            },
        )
        self._write_json("response.json", self._response_payload(response))
        self._write_json("metadata.json", self._metadata(request, response))
        self._write_text("raw_response.txt", response.raw_body)
        if response.body_json is not None:
            self._write_text("raw_response.json", response.body_json)
        else:
            self._remove_file("raw_response.json")
        return self._log_dir

    def _remove_file(self, name: str) -> None:
        """Delete a stale log file, ignoring any errors."""
        path = self._log_dir / name
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _response_payload(self, response: ResponseSnapshot) -> Dict[str, Any]:
        """Serialize the response without duplicating headers or raw body."""
        return {
            "status_code": response.status_code,
            "final_url": response.final_url,
            "redirect_chain": response.redirect_chain,
            "content_type": response.content_type,
            "response_length": response.response_length,
            "elapsed_seconds": response.elapsed_seconds,
            "is_json": response.is_json,
            "body_json": response.body_json,
        }

    def _metadata(
        self, request: RequestSnapshot, response: ResponseSnapshot
    ) -> Dict[str, Any]:
        """Build a summary record linking the request and response."""
        return {
            "provider": request.provider,
            "method": request.method,
            "request_url": request.url,
            "request_timestamp": request.timestamp,
            "status_code": response.status_code,
            "final_url": response.final_url,
            "elapsed_seconds": response.elapsed_seconds,
            "content_type": response.content_type,
            "is_json": response.is_json,
            "response_length": response.response_length,
            "redirect_count": len(response.redirect_chain),
        }

    def _write_json(self, name: str, data: Any) -> None:
        self._write_text(name, json.dumps(data, ensure_ascii=False, indent=4))

    def _write_text(self, name: str, text: str) -> None:
        path = self._log_dir / name
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
