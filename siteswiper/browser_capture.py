"""Automated browser-based capture of the Ontario Parks /api/cart/commit request.

Opens a headed Chromium window, displays an overlay guiding the user to
navigate to an available campsite, then intercepts the POST to
/api/cart/commit automatically when the user clicks Reserve.

Public API
----------
    ensure_playwright() -> None      # call at startup
    capture_commit_curl() -> dict | None

Returns a dict in exactly the same format as parse_curl(), or None if the
user cancelled or an error occurred.  The browser window is left open for
the user to close manually after capture.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Startup: ensure playwright package + Chromium binary are present
# ---------------------------------------------------------------------------

def _playwright_browsers_path() -> Path:
    """Return the directory where Playwright stores browser binaries.

    Mirrors Playwright's own resolution order:
      1. PLAYWRIGHT_BROWSERS_PATH env var
      2. Platform default (~/.cache/ms-playwright on Linux, etc.)
    """
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if custom:
        return Path(custom)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _chromium_is_installed() -> bool:
    """Return True if a Playwright-managed Chromium directory exists on disk."""
    try:
        browsers = _playwright_browsers_path()
        return browsers.exists() and any(
            d.is_dir() and d.name.startswith("chromium")
            for d in browsers.iterdir()
        )
    except Exception:
        return False


def ensure_playwright() -> None:
    """Ensure the playwright package and Chromium browser are installed.

    Called once at startup.  Both steps are skipped when already satisfied,
    so this is essentially free on subsequent runs.
    """
    from siteswiper.display import console

    # Step 1: Python package
    try:
        import playwright  # noqa: F401
    except ImportError:
        console.print("[dim]First-time setup: installing playwright...[/dim]")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            console.print(
                f"[red]Could not install playwright:[/red] "
                f"{exc.stderr.decode(errors='replace').strip()}\n"
                "[dim]Run manually:  pip install playwright[/dim]"
            )
            return

    # Step 2: Chromium binary
    if not _chromium_is_installed():
        console.print(
            "[dim]First-time setup: downloading Chromium browser "
            "(one-time, ~170 MB)...[/dim]"
        )
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
            )
            console.print("[green]Chromium installed.[/green]\n")
        except subprocess.CalledProcessError as exc:
            console.print(
                f"[red]Could not install Chromium:[/red] {exc}\n"
                "[dim]Run manually:  python -m playwright install chromium[/dim]"
            )


# ---------------------------------------------------------------------------
# Overlay JavaScript
# ---------------------------------------------------------------------------
# Injected via page.add_init_script() so it runs before any page JS on every
# navigation.  The MutationObserver re-attaches the overlay if a SPA framework
# replaces document.body.  Global flags survive client-side route changes.

_OVERLAY_JS = r"""
(function () {
    // Guard: inject only once per page context (reset on hard navigation).
    if (window.__ss_injected) return;
    window.__ss_injected = true;

    // Initialise flags on first injection only.
    if (typeof window.__ss_ready === 'undefined') window.__ss_ready = false;
    if (typeof window.__ss_state === 'undefined') window.__ss_state = 0;

    // -----------------------------------------------------------------------
    // State HTML
    // -----------------------------------------------------------------------
    var STATES = {
        0: '<div style="font-weight:700;font-size:14px;color:#63b3ed;margin-bottom:10px">&#9978;&#65039; SiteSwiper \u2014 Ready to Capture</div>'
         + '<div style="margin-bottom:12px">'
         + '1. Log in to Ontario Parks<br>'
         + '2. Find <strong>any available</strong> campsite<br>'
         + '3. Go to its booking page<br>'
         + '4. Stop <span style="color:#fbd38d"><strong>before</strong></span> clicking Reserve<br>'
         + '5. Click the button below &rarr; then click Reserve'
         + '</div>'
         + '<button id="__ss_btn" style="'
         + 'pointer-events:auto;width:100%;padding:9px 0;background:#3182ce;'
         + 'color:#fff;border:none;border-radius:6px;font-size:13px;'
         + 'font-weight:600;cursor:pointer;letter-spacing:0.02em">'
         + '\u2713 I\'m ready \u2014 watching for Reserve click'
         + '</button>',

        1: '<div style="font-weight:700;font-size:14px;color:#f6ad55;margin-bottom:10px">'
         + '&#9203; SiteSwiper \u2014 Watching\u2026</div>'
         + '<div>Click <strong style="color:#68d391">Reserve now!</strong> on<br>'
         + 'the campsite page.<br><br>'
         + '<span style="color:#a0aec0;font-size:12px">Intercepting network request\u2026</span>'
         + '</div>',

        2: '<div style="font-weight:700;font-size:14px;color:#68d391;margin-bottom:10px">'
         + '&#10003; SiteSwiper \u2014 Captured!</div>'
         + '<div>Request captured successfully.<br><br>'
         + '<span style="color:#a0aec0;font-size:12px">'
         + 'You can close this window.</span>'
         + '</div>',
    };

    // -----------------------------------------------------------------------
    // Build overlay element
    // -----------------------------------------------------------------------
    var overlay = document.createElement('div');
    overlay.id = '__ss_overlay';
    overlay.style.cssText = [
        'position:fixed', 'top:14px', 'left:14px', 'z-index:2147483647',
        'background:rgba(13,20,40,0.93)', 'color:#e2e8f0',
        'font-family:ui-monospace,"Cascadia Code","Fira Code",monospace',
        'font-size:13px', 'line-height:1.55', 'padding:15px 18px',
        'border-radius:10px', 'border:1.5px solid rgba(99,179,237,0.5)',
        'box-shadow:0 6px 28px rgba(0,0,0,0.6)', 'max-width:330px',
        'pointer-events:none', 'user-select:none',
    ].join(';');

    // -----------------------------------------------------------------------
    // Render state
    // -----------------------------------------------------------------------
    function renderState(s) {
        overlay.innerHTML = STATES[s] || STATES[0];
        window.__ss_state = s;
        if (s === 0) {
            var btn = document.getElementById('__ss_btn');
            if (btn) {
                btn.addEventListener('click', function () {
                    window.__ss_ready = true;
                    renderState(1);
                });
                btn.addEventListener('mouseover', function () { btn.style.background = '#2b6cb0'; });
                btn.addEventListener('mouseout',  function () { btn.style.background = '#3182ce'; });
            }
        }
    }

    // Expose setter for Python: page.evaluate("window.__ss_set_state(2)")
    window.__ss_set_state = renderState;

    // -----------------------------------------------------------------------
    // Attach to DOM
    // -----------------------------------------------------------------------
    function attach() {
        if (!document.getElementById('__ss_overlay')) {
            document.body.appendChild(overlay);
            renderState(window.__ss_state);
        }
    }

    if (document.body) {
        attach();
    } else {
        document.addEventListener('DOMContentLoaded', attach);
    }

    // MutationObserver: re-attach if a SPA framework replaces document.body
    new MutationObserver(function () {
        if (!document.getElementById('__ss_overlay') && document.body) {
            document.body.appendChild(overlay);
            renderState(window.__ss_state);
        }
    }).observe(document.documentElement, { childList: true, subtree: true });
})();
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_cookie_header(cookie_str: str) -> dict:
    """Split a Cookie header value into a name→value dict.

    Mirrors the cookie extraction logic in curl_parser.parse_curl().
    """
    cookies: dict[str, str] = {}
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


# Canonical Title-Case names for headers Ontario Parks is known to send.
# Playwright returns all header names in lowercase (HTTP/2 convention).
_CANONICAL_HEADERS: dict[str, str] = {
    "accept": "Accept",
    "accept-encoding": "Accept-Encoding",
    "accept-language": "Accept-Language",
    "app-language": "App-Language",
    "app-version": "app-version",
    "cache-control": "Cache-Control",
    "connection": "Connection",
    "content-length": "Content-Length",
    "content-type": "Content-Type",
    "cookie": "Cookie",
    "expires": "Expires",
    "origin": "Origin",
    "pragma": "Pragma",
    "referer": "Referer",
    "sec-ch-ua": "sec-ch-ua",
    "sec-ch-ua-mobile": "sec-ch-ua-mobile",
    "sec-ch-ua-platform": "sec-ch-ua-platform",
    "sec-fetch-dest": "Sec-Fetch-Dest",
    "sec-fetch-mode": "Sec-Fetch-Mode",
    "sec-fetch-site": "Sec-Fetch-Site",
    "user-agent": "User-Agent",
    "x-xsrf-token": "X-XSRF-TOKEN",
}


def _normalise_headers(raw: dict) -> dict:
    """Map lowercase Playwright header keys to the Title-Case names that
    parse_curl() produces, so downstream code can find X-XSRF-TOKEN etc.
    """
    out: dict[str, str] = {}
    for k, v in raw.items():
        if k.startswith(":"):
            continue  # skip HTTP/2 pseudo-headers (:method, :path, …)
        canonical = _CANONICAL_HEADERS.get(k.lower())
        if canonical is None:
            canonical = "-".join(part.capitalize() for part in k.split("-"))
        out[canonical] = v
    return out


async def _build_request_dict(request) -> dict:
    """Convert a Playwright Request to a parse_curl()-compatible dict.

    Must be awaited while the browser is still open — request.all_headers()
    requires a live browser context.
    """
    raw_headers = await request.all_headers()
    headers = _normalise_headers(raw_headers)

    # Drop headers that httpx must own / compute itself.
    # Accept-Encoding: if forwarded, httpx stops auto-decompressing and the
    # caller receives raw gzip bytes instead of text.
    # Content-Length: the captured value reflects the body at browser-capture
    # time. morning_of_flow() modifies the body (booking field sync, UUID
    # regeneration) before firing, so the captured length is stale. httpx
    # always computes Content-Length from the actual bytes passed as content=.
    headers.pop("Accept-Encoding", None)
    headers.pop("Content-Length", None)

    # Extract cookies from the Cookie header (lowercase key from Playwright)
    cookie_str = raw_headers.get("cookie", "")
    cookies = _parse_cookie_header(cookie_str)

    # Ensure the Cookie header in the headers dict uses the canonical name
    if cookie_str:
        headers["Cookie"] = cookie_str

    body: str = request.post_data or ""
    parsed_url = urlparse(request.url)

    return {
        "method": request.method.upper(),
        "url": request.url,
        "headers": headers,
        "cookies": cookies,
        "body": body,
        "compressed": True,   # let httpx handle decompression automatically
        "verify_ssl": True,
        "host": parsed_url.hostname,
        "path": parsed_url.path,
    }


# ---------------------------------------------------------------------------
# Capture log
# ---------------------------------------------------------------------------

def _save_capture_log(result: dict) -> None:
    """Persist the captured request dict to ~/.siteswiper/logs/captures/.

    The log file contains the full parse_curl()-compatible dict (headers,
    cookies, body) so that the capture can be inspected or replayed manually
    if a booking attempt fails.  Errors are silently ignored so a logging
    failure never aborts the capture.
    """
    try:
        from siteswiper.config import LOG_DIR
        from siteswiper.display import console

        captures_dir = LOG_DIR / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_file = captures_dir / f"capture_{timestamp}.json"

        log_entry = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source": "playwright_browser_capture",
            "request": result,
        }
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)

        console.print(
            f"[dim]Capture saved → {log_file}[/dim]"
        )
    except Exception:
        pass  # logging is best-effort


# ---------------------------------------------------------------------------
# Async core
# ---------------------------------------------------------------------------

_COMMIT_PATH = "/api/cart/commit"
_READY_TIMEOUT_MS = 600_000   # 10 minutes — time to navigate to a site
_REQUEST_TIMEOUT_S = 90       # 90 seconds after clicking Ready


async def _capture_async() -> dict | None:
    """Open Chromium, show the overlay, intercept the /api/cart/commit POST.

    Uses the manual playwright.start() pattern (not the async-with context
    manager) so the browser process is NOT terminated when the coroutine
    returns — the user closes the window themselves.

    Returns a parse_curl()-compatible dict on success, or None on timeout /
    cancellation.
    """
    from playwright.async_api import async_playwright, Error as PlaywrightError

    captured_request = None
    request_event = asyncio.Event()
    # Flag flipped after the user clicks Ready; prevents capturing background
    # API calls the site makes during normal navigation.
    window_ready: list[bool] = [False]

    playwright_obj = await async_playwright().start()

    try:
        try:
            browser = await playwright_obj.chromium.launch(headless=False)
        except PlaywrightError as exc:
            err = str(exc)
            if "Executable doesn't exist" in err or "playwright install" in err.lower():
                raise RuntimeError(
                    "Chromium browser binary not found.\n"
                    "Run:  python -m playwright install chromium"
                ) from exc
            raise

        context = await browser.new_context()
        page = await context.new_page()

        # Inject overlay on every hard navigation.
        await page.add_init_script(script=_OVERLAY_JS)

        # Re-inject after Playwright fires 'load' (covers edge-case reloads).
        async def _on_load():
            try:
                await page.evaluate(_OVERLAY_JS)
            except Exception:
                pass

        page.on("load", lambda _: asyncio.ensure_future(_on_load()))

        # Register the request listener BEFORE navigating so no request can
        # slip through before the handler is active.
        def _on_request(req) -> None:
            nonlocal captured_request
            if (
                window_ready[0]
                and _COMMIT_PATH in req.url
                and req.method.upper() == "POST"
                and not request_event.is_set()
            ):
                # Store the raw Playwright request object; we'll await its
                # headers in _build_request_dict() while the browser is live.
                captured_request = req
                request_event.set()

        page.on("request", _on_request)

        # Navigate to Ontario Parks.
        await page.goto(
            "https://reservations.ontarioparks.ca",
            wait_until="domcontentloaded",
        )

        # Wait for the user to click the "Ready" button in the overlay.
        try:
            await page.wait_for_function(
                "() => window.__ss_ready === true",
                timeout=_READY_TIMEOUT_MS,
                polling=500,
            )
        except Exception:
            # Timed out or browser closed.
            return None

        # Now start intercepting commit requests.
        window_ready[0] = True

        # Transition overlay to "Watching" state.
        try:
            await page.evaluate("window.__ss_set_state(1)")
        except Exception:
            pass

        # Wait for the intercepted request (90 s).
        try:
            await asyncio.wait_for(request_event.wait(), timeout=_REQUEST_TIMEOUT_S)
        except asyncio.TimeoutError:
            return None

        # Build the result dict while the browser is still alive.
        result = await _build_request_dict(captured_request)

        # Save the captured request to a log file for troubleshooting.
        _save_capture_log(result)

        # Transition overlay to "Captured!" state and leave browser open.
        try:
            await page.evaluate("window.__ss_set_state(2)")
        except Exception:
            pass

        # Return result — browser and playwright_obj are intentionally NOT
        # stopped so the user can inspect / close the window themselves.
        return result

    except Exception:
        # On any error, clean up to avoid orphaned browser processes.
        try:
            await playwright_obj.stop()
        except Exception:
            pass
        raise


# ---------------------------------------------------------------------------
# Public sync entry point
# ---------------------------------------------------------------------------

def capture_commit_curl() -> dict | None:
    """Open a Chromium browser and capture the Ontario Parks cart commit request.

    Wraps the async Playwright flow with asyncio.run() so it can be called
    from the synchronous morning_of_flow() in cli.py.

    The browser window is left open after capture; the user closes it.

    Returns:
        A dict matching parse_curl() output format, or None if:
          - The user closed the browser or timed out waiting for Ready
          - Playwright is not installed (ImportError)
          - The Chromium binary is not installed (RuntimeError)
          - Any other exception occurs
    """
    # Lazy import so missing Playwright doesn't break startup for users who
    # only use the manual path.
    try:
        import playwright  # noqa: F401
    except ImportError:
        from siteswiper.display import console
        console.print(
            "[red]Playwright is not installed.[/red]\n"
            "Run:  [bold]pip install playwright[/bold]\n"
            "Then: [bold]python -m playwright install chromium[/bold]"
        )
        return None

    try:
        return asyncio.run(_capture_async())
    except RuntimeError as exc:
        from siteswiper.display import console
        console.print(f"[red]Browser launch failed:[/red] {exc}")
        return None
    except KeyboardInterrupt:
        from siteswiper.display import console
        console.print("\n[yellow]Browser capture cancelled.[/yellow]")
        return None
    except Exception as exc:
        from siteswiper.display import console
        console.print(f"[red]Browser capture error:[/red] {exc}")
        return None
