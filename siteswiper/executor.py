"""HTTP request execution with connection pre-warming and retries."""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from siteswiper.config import LOG_DIR, REQUEST_TIMEOUT_SECONDS, DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY_MS


@dataclass
class ExecutionResult:
    """Result of a single request attempt."""
    attempt: int
    status_code: int | None
    body: str
    elapsed_ms: float
    success: bool
    error: str | None = None
    summary: str = ""
    server_ts: str | None = None
    server_delta_ms: float | None = None


class RequestExecutor:
    """Builds and fires HTTP requests from parsed cURL data.

    Supports connection pre-warming, dry-run mode, and rapid-fire retries.
    """

    def __init__(self, parsed_request: dict, dry_run: bool = False):
        self.parsed = parsed_request
        self.dry_run = dry_run
        self._client: httpx.Client | None = None
        self._log_dir: Path | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create the httpx client."""
        if self._client is None:
            self._client = httpx.Client(
                http2=True,
                verify=self.parsed.get("verify_ssl", True),
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        return self._client

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def _get_log_dir(self) -> Path:
        """Get or create a timestamped log directory for this execution run."""
        if self._log_dir is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self._log_dir = LOG_DIR / timestamp
            self._log_dir.mkdir(parents=True, exist_ok=True)
        return self._log_dir

    @property
    def log_dir(self) -> Path | None:
        """The log directory for this run, or None if no requests have been logged."""
        return self._log_dir

    def _log_response(self, attempt: int, response: httpx.Response, elapsed_ms: float,
                      success: bool, summary: str, *,
                      fire_time: datetime | None = None,
                      server_ts: str | None = None,
                      server_delta_ms: float | None = None) -> None:
        """Save the full response to a log file for post-mortem debugging."""
        log_dir = self._get_log_dir()
        log_entry = {
            "attempt": attempt,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fire_timestamp": fire_time.isoformat() if fire_time else None,
            "request": {
                "method": self.parsed["method"],
                "url": self.parsed["url"],
            },
            "response": {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            },
            "elapsed_ms": round(elapsed_ms, 2),
            "success": success,
            "summary": summary,
        }
        if server_ts is not None:
            log_entry["server_timestamp"] = server_ts
            log_entry["server_delta_ms"] = server_delta_ms
        log_file = log_dir / f"attempt_{attempt}.json"
        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)

    def _log_error(self, attempt: int, elapsed_ms: float, error: str) -> None:
        """Save an error result to a log file."""
        log_dir = self._get_log_dir()
        log_entry = {
            "attempt": attempt,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": {
                "method": self.parsed["method"],
                "url": self.parsed["url"],
            },
            "response": None,
            "elapsed_ms": round(elapsed_ms, 2),
            "success": False,
            "error": error,
        }
        log_file = log_dir / f"attempt_{attempt}.json"
        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)

    def prewarm(self) -> bool:
        """Pre-warm the connection by performing a HEAD request.

        This establishes the TCP + TLS handshake so the actual booking request
        only needs to send/receive data (saving ~100-300ms).

        Returns:
            True if connection was successfully warmed.
        """
        if self.dry_run:
            return True

        client = self._get_client()
        try:
            # HEAD request to the same host to establish the connection
            url = self.parsed["url"]
            # Use the base URL (scheme + host) for the warmup
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            client.head(base_url, headers={"User-Agent": self.parsed.get("headers", {}).get("User-Agent", "")})
            return True
        except Exception:
            # Connection warmup is best-effort; don't fail the whole operation
            return False

    def _build_request_kwargs(self) -> dict:
        """Build the httpx request keyword arguments from parsed data."""
        kwargs = {
            "method": self.parsed["method"],
            "url": self.parsed["url"],
        }

        # Headers (exclude Cookie header since we pass cookies separately)
        headers = dict(self.parsed.get("headers", {}))
        headers.pop("Cookie", None)
        if headers:
            kwargs["headers"] = headers

        # Cookies
        cookies = self.parsed.get("cookies", {})
        if cookies:
            kwargs["cookies"] = cookies

        # Body
        body = self.parsed.get("body")
        if body:
            # Determine if it's form data or raw content
            content_type = headers.get("Content-Type", headers.get("content-type", ""))
            if "application/x-www-form-urlencoded" in content_type:
                kwargs["data"] = body
            elif "application/json" in content_type:
                kwargs["content"] = body.encode()
            else:
                kwargs["content"] = body.encode() if isinstance(body, str) else body

        return kwargs

    @staticmethod
    def _parse_server_timestamp(body: str) -> datetime | None:
        """Try to parse the response body as a server-side timestamp.

        Ontario Parks' /api/cart/commit returns a bare quoted ISO-8601
        timestamp on success, e.g. ``"2026-02-26T12:00:00.2194438Z"``.
        """
        text = body.strip().strip('"').strip()
        if not text:
            return None
        try:
            # Replace trailing Z with +00:00 for Python 3.10 compat
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            # Truncate fractional seconds beyond 6 digits (microseconds)
            text = re.sub(r"(\.\d{6})\d+", r"\1", text)
            return datetime.fromisoformat(text)
        except (ValueError, TypeError):
            return None

    def _update_cookies_from_response(self, response: httpx.Response) -> None:
        """Propagate Set-Cookie values (especially XSRF-TOKEN) into self.parsed.

        This ensures subsequent retries use the freshly rotated token.
        """
        for name, value in response.cookies.items():
            self.parsed.setdefault("cookies", {})[name] = value
        new_xsrf = response.cookies.get("XSRF-TOKEN")
        if new_xsrf:
            self.parsed.setdefault("headers", {})["X-XSRF-TOKEN"] = new_xsrf

    def fire_once(self, attempt: int = 1) -> ExecutionResult:
        """Fire the request once.

        Args:
            attempt: The attempt number (for logging).

        Returns:
            ExecutionResult with response details.
        """
        if self.dry_run:
            return ExecutionResult(
                attempt=attempt,
                status_code=200,
                body="[DRY RUN] Request was not actually sent.",
                elapsed_ms=0.0,
                success=True,
                summary="Dry run - no request sent",
            )

        client = self._get_client()
        kwargs = self._build_request_kwargs()

        fire_time = datetime.now(timezone.utc)
        start = time.perf_counter()
        try:
            response = client.request(**kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            success = self.is_booking_success(response)
            body_text = response.text[:2000]  # Limit body size for display

            # Try to parse server-side timestamp from response body
            server_ts = None
            server_delta_ms = None
            parsed_ts = self._parse_server_timestamp(response.text)
            if parsed_ts is not None:
                server_ts = parsed_ts.isoformat()
                server_delta_ms = round(
                    (parsed_ts - fire_time).total_seconds() * 1000, 1
                )

            summary = self._make_summary(
                response.status_code, body_text, success,
                server_delta_ms=server_delta_ms,
            )

            # Log the full response (not truncated) for debugging
            self._log_response(
                attempt, response, elapsed_ms, success, summary,
                fire_time=fire_time, server_ts=server_ts,
                server_delta_ms=server_delta_ms,
            )

            # Propagate rotated XSRF token so subsequent retries use it
            self._update_cookies_from_response(response)

            return ExecutionResult(
                attempt=attempt,
                status_code=response.status_code,
                body=body_text,
                elapsed_ms=elapsed_ms,
                success=success,
                summary=summary,
                server_ts=server_ts,
                server_delta_ms=server_delta_ms,
            )

        except httpx.TimeoutException:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._log_error(attempt, elapsed_ms, "Request timed out")
            return ExecutionResult(
                attempt=attempt,
                status_code=None,
                body="",
                elapsed_ms=elapsed_ms,
                success=False,
                error="Request timed out",
                summary="TIMEOUT",
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._log_error(attempt, elapsed_ms, str(e))
            return ExecutionResult(
                attempt=attempt,
                status_code=None,
                body="",
                elapsed_ms=elapsed_ms,
                success=False,
                error=str(e),
                summary=f"ERROR: {e}",
            )

    def fire_with_retries(self, max_retries: int = DEFAULT_MAX_RETRIES,
                          delay_ms: int = DEFAULT_RETRY_DELAY_MS) -> list[ExecutionResult]:
        """Fire the request with rapid-fire retries.

        Stops on:
          - 2xx response (success)
          - 4xx response (client error — retrying won't help)

        Retries on:
          - 5xx response (server error)
          - Timeout
          - Connection error

        Args:
            max_retries: Maximum number of attempts.
            delay_ms: Milliseconds to wait between retries.

        Returns:
            List of all ExecutionResults (one per attempt).
        """
        results = []

        for attempt in range(1, max_retries + 1):
            result = self.fire_once(attempt=attempt)
            results.append(result)

            # Stop on success
            if result.success:
                break

            # Stop on 4xx (client errors won't be fixed by retrying)
            if result.status_code and 400 <= result.status_code < 500:
                break

            # Wait before retry (except on last attempt)
            if attempt < max_retries and delay_ms > 0:
                time.sleep(delay_ms / 1000)

        return results

    @staticmethod
    def is_booking_success(response: httpx.Response) -> bool:
        """Heuristic to determine if a booking request succeeded.

        Checks for:
          - 2xx status code
          - Absence of common failure indicators in response body
        """
        if response.status_code < 200 or response.status_code >= 300:
            return False

        body_lower = response.text.lower()

        # Common failure indicators
        failure_keywords = [
            "unavailable",
            "no longer available",
            "already booked",
            "sold out",
            "error occurred",
            "session expired",
            "please try again",
            # Session/auth failures that return 200 with a login page
            "sign in",
            "sign-in",
            "log in",
            "login",
            "authentication required",
            "access denied",
            # Ontario Parks specific
            "not available",
            "cannot be added",
            "could not be completed",
            "no sites available",
        ]

        for keyword in failure_keywords:
            if keyword in body_lower:
                return False

        return True

    @staticmethod
    def _make_summary(status_code: int, body: str, success: bool, *,
                      server_delta_ms: float | None = None) -> str:
        """Create a short summary of the response."""
        if success:
            base = f"HTTP {status_code} - Success"
            if server_delta_ms is not None:
                base += f" (server T+{server_delta_ms:.0f}ms)"
            return base

        body_lower = body.lower()
        if "unavailable" in body_lower or "no longer available" in body_lower or "not available" in body_lower:
            return f"HTTP {status_code} - Site unavailable"
        elif "session expired" in body_lower:
            return f"HTTP {status_code} - Session expired"
        elif any(kw in body_lower for kw in ("sign in", "sign-in", "log in", "login", "authentication required")):
            return f"HTTP {status_code} - Session expired (login page returned)"
        elif "already booked" in body_lower or "sold out" in body_lower:
            return f"HTTP {status_code} - Already booked"
        elif "cannot be added" in body_lower or "could not be completed" in body_lower:
            return f"HTTP {status_code} - Booking rejected"
        elif status_code >= 500:
            return f"HTTP {status_code} - Server error"
        elif status_code >= 400:
            return f"HTTP {status_code} - Client error"
        else:
            return f"HTTP {status_code}"

    def fire_two_step(
        self,
        step1_executor: "RequestExecutor",
        on_step1_done: "callable | None" = None,
    ) -> "tuple[ExecutionResult, list[ExecutionResult] | None]":
        """Fire step 1, inject UUIDs from its response, then fire step 2 with retries.

        Step 1 is fired exactly once — no retries, to avoid creating duplicate
        server-side carts or resource blockers.  If step 1 fails or UUID
        injection fails, step 2 is skipped and None is returned for its results.

        Args:
            step1_executor: RequestExecutor configured for the pre-commit request.
            on_step1_done: Optional callback invoked with the step 1 result
                           immediately after it fires (useful for live display).

        Returns:
            (step1_result, step2_results).  step2_results is None if step 1
            failed or UUID extraction/injection failed.
        """
        from siteswiper.curl_parser import apply_op_uuids_from_step1_response

        if self.dry_run:
            step1_result = ExecutionResult(
                attempt=1,
                status_code=200,
                body="[DRY RUN] Step 1 not sent.",
                elapsed_ms=0.0,
                success=True,
                summary="Dry run - step 1 not sent",
            )
            if on_step1_done:
                on_step1_done(step1_result)
            step2_results = self.fire_with_retries()
            return step1_result, step2_results

        # Fire step 1 directly so we have access to the full (untruncated) body
        # for UUID extraction.
        client = step1_executor._get_client()
        kwargs = step1_executor._build_request_kwargs()
        body_full = ""

        fire_time = datetime.now(timezone.utc)
        start = time.perf_counter()
        try:
            response = client.request(**kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            body_full = response.text
            body_display = body_full[:2000]
            success = self.is_booking_success(response)

            server_ts = None
            server_delta_ms = None
            parsed_ts = self._parse_server_timestamp(response.text)
            if parsed_ts is not None:
                server_ts = parsed_ts.isoformat()
                server_delta_ms = round(
                    (parsed_ts - fire_time).total_seconds() * 1000, 1
                )

            summary = self._make_summary(
                response.status_code, body_display, success,
                server_delta_ms=server_delta_ms,
            )
            step1_executor._log_response(
                1, response, elapsed_ms, success, summary,
                fire_time=fire_time, server_ts=server_ts,
                server_delta_ms=server_delta_ms,
            )
            step1_result = ExecutionResult(
                attempt=1,
                status_code=response.status_code,
                body=body_display,
                elapsed_ms=elapsed_ms,
                success=success,
                summary=summary,
                server_ts=server_ts,
                server_delta_ms=server_delta_ms,
            )
        except httpx.TimeoutException:
            elapsed_ms = (time.perf_counter() - start) * 1000
            step1_executor._log_error(1, elapsed_ms, "Request timed out")
            step1_result = ExecutionResult(
                attempt=1, status_code=None, body="",
                elapsed_ms=elapsed_ms, success=False,
                error="Request timed out", summary="TIMEOUT",
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            step1_executor._log_error(1, elapsed_ms, str(e))
            step1_result = ExecutionResult(
                attempt=1, status_code=None, body="",
                elapsed_ms=elapsed_ms, success=False,
                error=str(e), summary=f"ERROR: {e}",
            )

        if on_step1_done:
            on_step1_done(step1_result)

        if not step1_result.success:
            return step1_result, None

        # Propagate cookies/XSRF from step 1 response to step 2.
        self._update_cookies_from_response(response)

        # Inject UUIDs from step 1 full response body into the step 2 body
        try:
            self.parsed["body"] = apply_op_uuids_from_step1_response(
                self.parsed["body"], body_full
            )
        except (ValueError, KeyError, json.JSONDecodeError, AttributeError, TypeError) as e:
            # Preserve step 1's success status — the server accepted the
            # request even though we can't extract UUIDs for step 2.
            # Some endpoints (e.g. /api/cart/commit) return a bare timestamp
            # on success rather than a JSON cart object, which means step 1
            # may have already completed the booking.
            step1_result.error = f"UUID injection failed: {e}"
            return step1_result, None

        # Fire step 2 with retries
        step2_results = self.fire_with_retries()
        return step1_result, step2_results

    def get_dry_run_summary(self) -> str:
        """Return a detailed summary of what would be sent (for dry run display)."""
        kwargs = self._build_request_kwargs()
        lines = [
            f"Method:  {kwargs['method']}",
            f"URL:     {kwargs['url']}",
        ]

        headers = kwargs.get("headers", {})
        if headers:
            lines.append(f"Headers: {len(headers)} headers")
            for key, value in headers.items():
                val_preview = value[:60] + "..." if len(value) > 60 else value
                lines.append(f"         {key}: {val_preview}")

        cookies = kwargs.get("cookies", {})
        if cookies:
            lines.append(f"Cookies: {len(cookies)} cookies")

        data = kwargs.get("data") or kwargs.get("content")
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            preview = data[:200] + "..." if len(str(data)) > 200 else str(data)
            lines.append(f"Body:    {preview}")

        return "\n".join(lines)
