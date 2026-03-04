"""Rich-based terminal UI helpers for SiteSwiper."""

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from siteswiper.config import CAMPSITE_BY_SITE_ID
from siteswiper.latency import PROBE_HOST

console = Console()


def print_banner():
    """Display the SiteSwiper banner."""
    banner = Text()
    banner.append("  ____  _ _       ____          _                 \n", style="bold cyan")
    banner.append(" / ___|(_) |_ ___/ ___|_      _(_)_ __   ___ _ __ \n", style="bold cyan")
    banner.append(" \\___ \\| | __/ _ \\___ \\ \\ /\\ / / | '_ \\ / _ \\ '__|\n", style="bold cyan")
    banner.append("  ___) | | ||  __/___) \\ V  V /| | |_) |  __/ |   \n", style="bold cyan")
    banner.append(" |____/|_|\\__\\___|____/ \\_/\\_/ |_| .__/ \\___|_|   \n", style="bold cyan")
    banner.append("                                  |_|              \n", style="bold cyan")
    banner.append("        Ontario Parks Campsite Booking Tool\n", style="dim")

    console.print(Panel(banner, border_style="cyan", padding=(0, 2)))


def print_capture_guide():
    """Display step-by-step instructions for capturing the booking request."""
    steps = """
[bold]How to capture your booking request:[/bold]

[cyan]Step 1:[/cyan] Open your browser and log in to [link]https://reservations.ontarioparks.ca[/link]

[cyan]Step 2:[/cyan] Navigate to the campsite you want to book. Select your dates
        and get to the point where you can click "Add to Cart" or "Book".
        [yellow]DO NOT click the button yet![/yellow]

[cyan]Step 3:[/cyan] Open Developer Tools:
        [dim]Chrome/Edge:[/dim]  Press [bold]F12[/bold] or [bold]Ctrl+Shift+I[/bold] (Cmd+Option+I on Mac)
        [dim]Firefox:[/dim]     Press [bold]F12[/bold] or [bold]Ctrl+Shift+I[/bold] (Cmd+Option+I on Mac)

[cyan]Step 4:[/cyan] Click the [bold]Network[/bold] tab in Developer Tools.
        Check the [bold]"Preserve log"[/bold] checkbox (important!).
        You can filter by [bold]"Fetch/XHR"[/bold] to reduce noise.

[cyan]Step 5:[/cyan] Now click the [bold]"Add to Cart"[/bold] or booking button on the page.

[cyan]Step 6:[/cyan] In the Network tab, look for the POST request that was made.
        It will typically be one of the larger requests.
        Look for URLs containing keywords like: [bold]cart[/bold], [bold]booking[/bold],
        [bold]reservation[/bold], [bold]add[/bold], or [bold]create[/bold].

[cyan]Step 7:[/cyan] [bold]Right-click[/bold] on that request and select:
        [dim]Chrome:[/dim]  "Copy" -> [bold]"Copy as cURL (bash)"[/bold]
        [dim]Firefox:[/dim] "Copy Value" -> [bold]"Copy as cURL"[/bold]

[cyan]Step 8:[/cyan] Paste the copied command below.

[yellow]Tip:[/yellow] If you're capturing this in advance (practice run), you can test
     with any request. The important thing is to capture the exact format
     so you know what to look for on booking day.

[yellow]Important:[/yellow] Session cookies expire! Capture this [bold]10-15 minutes before 7:00 AM[/bold]
           on booking day for best results.
"""
    console.print(Panel(steps.strip(), title="[bold]Request Capture Guide[/bold]",
                        border_style="green", padding=(1, 2)))


def print_template_guide():
    """Display instructions for the template-based workflow."""
    steps = """
[bold]Creating a request from a saved template[/bold]

You're about to modify a previously captured booking request to target a
different campsite. This is how you book a site that isn't available yet
(e.g., a site that opens at 7:00 AM).

[cyan]1.[/cyan] [bold]Edit booking fields[/bold] — choose "Edit booking fields (dates, site ID, park ID)":
   [bold]startDate[/bold]          — arrival date (YYYY-MM-DD)
   [bold]endDate[/bold]            — departure date (YYYY-MM-DD)
   [bold]resourceId[/bold]         — the campsite number (site ID)
   [bold]resourceLocationId[/bold] — the park ID (same for all sites in the same park)

   Changes are written to all nested locations in the request body automatically.

[cyan]2.[/cyan] Choose [bold]"Done editing"[/bold] and save the request.

[dim]After saving, use the main menu to complete the remaining steps:[/dim]
[cyan]3.[/cyan] [bold]Regenerate session UUIDs[/bold] (menu option 2)
[cyan]4.[/cyan] [bold]Refresh cookies[/bold] (menu option 3) — do this 10-15 min before 7:00 AM
[cyan]5.[/cyan] [bold]Set up pre-commit request[/bold] (menu option 4)
[cyan]6.[/cyan] [bold]Schedule and fire[/bold] (menu option 5)

[yellow]Tip:[/yellow] To find your target site's [bold]resourceId[/bold], browse to the site on
     Ontario Parks and look at the URL — it contains the ID as a parameter.
     The [bold]resourceLocationId[/bold] (park) is also in the URL and stays the same
     for all sites within the same park.
"""
    console.print(Panel(steps.strip(), title="[bold]Template Workflow[/bold]",
                        border_style="green", padding=(1, 2)))


def print_pre_commit_guide():
    """Display instructions for capturing the pre-commit (step 1) request."""
    steps = """
[bold]What is the pre-commit request?[/bold]

Ontario Parks requires two sequential requests to complete a booking:

[cyan]Step 1 — Pre-commit:[/cyan] Fires when you click the first "Reserve" button.
  Creates a server-side cart + resource blocker and returns fresh session UUIDs.
  SiteSwiper fires this first, extracts the UUIDs, and injects them into Step 2.

[cyan]Step 2 — Commit:[/cyan] The [bold]/api/cart/commit[/bold] POST (already saved).
  Uses the UUIDs from Step 1 to finalise the reservation.

[bold]How to capture Step 1:[/bold]

[cyan]1.[/cyan] Open DevTools (F12) → [bold]Network[/bold] tab.
   Check [bold]"Preserve log"[/bold]. Filter by [bold]"Fetch/XHR"[/bold].

[cyan]2.[/cyan] Clear the log. Navigate to any [bold]available[/bold] campsite (can be a different
   site from your target — we just need the right request format).

[cyan]3.[/cyan] Click the first booking button that initiates the checkout flow
   (e.g., the site tile, "Reserve", or "Add to Cart") so that a popup or
   checkout step appears.

[cyan]4.[/cyan] In the Network tab, find the first POST that fired [bold]before[/bold] the popup.
   Common URLs:
   [dim]  /api/cart/resourceblocker[/dim]
   [dim]  /api/cart/add[/dim]
   [dim]  /api/availability/.../lock[/dim]

[cyan]5.[/cyan] Click the request → [bold]Preview[/bold] or [bold]Response[/bold] tab. Verify the response
   is JSON containing keys like [bold]cartUid[/bold], [bold]bookings[/bold], [bold]resourceBlockers[/bold].

[cyan]6.[/cyan] Right-click → Copy → [bold]"Copy as cURL (bash)"[/bold]. Paste it below.

[yellow]Note:[/yellow] SiteSwiper will replace the booking fields (dates, site ID) with
      the values from your commit request before firing at 7:00 AM.
      You only need a valid session structure — the fields don't need to
      match your target campsite.
"""
    console.print(Panel(steps.strip(), title="[bold]Pre-Commit Request Capture[/bold]",
                        border_style="cyan", padding=(1, 2)))


def print_morning_of_guide():
    """Display instructions for the morning-of booking preparation flow."""
    steps = """
[bold]What this flow does (in one pass):[/bold]

  [cyan]1.[/cyan] Regenerates fresh session UUIDs in your saved commit request
  [cyan]2.[/cyan] Refreshes your session cookies from the CURL you paste below
  [cyan]3.[/cyan] Attaches the pasted request as the pre-commit step (with booking
     fields automatically synced to your target site)

[bold]How to get the CURL:[/bold]

[cyan]1.[/cyan] Open [link]https://reservations.ontarioparks.ca[/link] in your browser and log in.

[cyan]2.[/cyan] Open DevTools ([bold]F12[/bold]) → [bold]Network[/bold] tab.
   Check [bold]"Preserve log"[/bold]. Filter by [bold]"Fetch/XHR"[/bold]. Clear the log.

[cyan]3.[/cyan] Find any campsite that is [bold]currently available[/bold] for booking
   (it does not need to be your target site — any available site works).

[cyan]4.[/cyan] Click the booking button on that site (e.g., the site tile, "Reserve",
   or "Add to Cart") to trigger the checkout flow.

[cyan]5.[/cyan] In the Network tab, find the [bold]first POST request[/bold] that fired.
   Common URLs:
   [dim]  /api/cart/resourceblocker[/dim]
   [dim]  /api/cart/add[/dim]
   [dim]  /api/availability/.../lock[/dim]

[cyan]6.[/cyan] Verify the response contains keys like [bold]cartUid[/bold], [bold]bookings[/bold],
   [bold]resourceBlockers[/bold] (Preview or Response tab).

[cyan]7.[/cyan] Right-click the request → Copy → [bold]"Copy as cURL (bash)"[/bold]. Paste it below.

[yellow]Why any available site works:[/yellow] The cookies in the CURL are session-wide,
  not site-specific. SiteSwiper will automatically overwrite the site/dates
  in the pre-commit body with the values from your commit request.

[yellow]Important:[/yellow] Do this [bold]10-15 minutes before 7:00 AM[/bold] on booking day.
           Session cookies expire — the closer to fire time, the better.
"""
    console.print(Panel(steps.strip(), title="[bold]Morning-of Flow Guide[/bold]",
                        border_style="blue", padding=(1, 2)))


def print_op_booking_fields(fields: dict):
    """Display the 4 key Ontario Parks booking fields in a clear table."""
    table = Table(title="Ontario Parks Booking Fields", border_style="green", padding=(0, 1))
    table.add_column("Field", style="bold green")
    table.add_column("Value", style="white")
    table.add_column("Description", style="dim")

    table.add_row("startDate", str(fields["startDate"]), "Arrival date")
    table.add_row("endDate", str(fields["endDate"]), "Departure date")

    resource_id = fields["resourceId"]
    campsite_info = CAMPSITE_BY_SITE_ID.get(resource_id)
    if campsite_info:
        camp_name, camp_number = campsite_info
        resource_display = f"{resource_id}  ({camp_name} #{camp_number})"
        resource_desc = "Site ID (Campsite)"
    else:
        resource_display = str(resource_id)
        resource_desc = "Site ID"
    table.add_row("resourceId", resource_display, resource_desc)

    table.add_row("resourceLocationId", str(fields["resourceLocationId"]), "Park ID")

    console.print(table)
    console.print()


def print_request_summary(parsed: dict, title: str = "Parsed Request"):
    """Display a formatted summary of a parsed request."""
    table = Table(title=title, show_header=False, border_style="cyan",
                  padding=(0, 2), expand=True)
    table.add_column("Field", style="bold cyan", width=12)
    table.add_column("Value", style="white")

    table.add_row("Method", f"[bold]{parsed['method']}[/bold]")
    table.add_row("URL", parsed["url"])
    table.add_row("Host", parsed.get("host", "?"))
    table.add_row("Path", parsed.get("path", "?"))

    # Headers count
    headers = parsed.get("headers", {})
    header_count = len(headers)
    table.add_row("Headers", f"{header_count} headers")

    # Cookies count
    cookies = parsed.get("cookies", {})
    cookie_count = len(cookies)
    cookie_style = "green" if cookie_count > 0 else "yellow"
    table.add_row("Cookies", f"[{cookie_style}]{cookie_count} cookies[/{cookie_style}]")

    # Body preview
    body = parsed.get("body")
    if body:
        preview = body[:100] + "..." if len(body) > 100 else body
        table.add_row("Body", f"[dim]{preview}[/dim]")
    else:
        table.add_row("Body", "[dim]None[/dim]")

    table.add_row("SSL Verify", str(parsed.get("verify_ssl", True)))

    console.print(table)
    console.print()


def print_headers_table(headers: dict):
    """Display all headers in a table."""
    table = Table(title="Request Headers", border_style="blue", padding=(0, 1))
    table.add_column("#", style="dim", width=4)
    table.add_column("Header", style="cyan")
    table.add_column("Value", style="white", max_width=80)

    for idx, (key, value) in enumerate(headers.items(), 1):
        # Truncate long values
        display_val = value[:80] + "..." if len(value) > 80 else value
        table.add_row(str(idx), key, display_val)

    console.print(table)
    console.print()


def print_cookies_table(cookies: dict):
    """Display all cookies in a table."""
    if not cookies:
        console.print("[dim]No cookies found.[/dim]")
        return

    table = Table(title="Cookies", border_style="yellow", padding=(0, 1))
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", style="yellow")
    table.add_column("Value", style="white", max_width=60)

    for idx, (key, value) in enumerate(cookies.items(), 1):
        display_val = value[:60] + "..." if len(value) > 60 else value
        table.add_row(str(idx), key, display_val)

    console.print(table)
    console.print()


def print_body_params(body_info: dict):
    """Display parsed body parameters."""
    if not body_info:
        console.print("[dim]Body is not parseable as form data or JSON.[/dim]")
        return

    body_type = body_info["type"].upper()
    table = Table(title=f"Body Parameters ({body_type})", border_style="magenta", padding=(0, 1))
    table.add_column("#", style="dim", width=4)
    table.add_column("Parameter", style="magenta")
    table.add_column("Value", style="white", max_width=60)

    for idx, (key, value) in enumerate(body_info["params"].items(), 1):
        display_val = str(value)
        if len(display_val) > 60:
            display_val = display_val[:60] + "..."
        table.add_row(str(idx), key, display_val)

    console.print(table)
    console.print()


def print_ntp_status(offset_ms: float):
    """Display NTP sync status with color coding."""
    abs_offset = abs(offset_ms)

    if abs_offset < 50:
        color = "green"
        status = "Excellent"
    elif abs_offset < 200:
        color = "yellow"
        status = "Good"
    else:
        color = "red"
        status = "Poor - consider syncing your system clock"

    direction = "ahead" if offset_ms > 0 else "behind"
    console.print(Panel(
        f"[bold]Clock Offset:[/bold] [{color}]{offset_ms:+.1f} ms[/{color}] "
        f"(your clock is {abs_offset:.1f}ms {direction})\n"
        f"[bold]Status:[/bold] [{color}]{status}[/{color}]",
        title="[bold]NTP Time Sync[/bold]",
        border_style=color,
    ))


def print_results(results: list[dict]):
    """Display execution results."""
    has_server_delta = any(r.get("server_delta_ms") is not None for r in results)

    table = Table(title="Execution Results", border_style="green", padding=(0, 1))
    table.add_column("Attempt", style="dim", width=8)
    table.add_column("Status", width=8)
    table.add_column("Time (ms)", width=10)
    if has_server_delta:
        table.add_column("Server T+", width=12)
    table.add_column("Result", max_width=60)

    for r in results:
        status_code = r.get("status_code", "?")
        if isinstance(status_code, int) and 200 <= status_code < 300:
            status_style = "bold green"
        elif isinstance(status_code, int) and 400 <= status_code < 500:
            status_style = "bold yellow"
        else:
            status_style = "bold red"

        row = [
            str(r.get("attempt", "?")),
            f"[{status_style}]{status_code}[/{status_style}]",
            f"{r.get('elapsed_ms', 0):.0f}",
        ]
        if has_server_delta:
            delta = r.get("server_delta_ms")
            row.append(f"{delta:.0f}ms" if delta is not None else "-")
        row.append(r.get("summary", ""))
        table.add_row(*row)

    console.print(table)
    console.print()


def print_countdown_status(remaining: float, target_str: str, request_summary: str, phase: str):
    """Print a single countdown status line (used with Live display)."""
    if remaining > 3600:
        time_str = f"{remaining/3600:.1f} hours"
    elif remaining > 60:
        mins = int(remaining // 60)
        secs = remaining % 60
        time_str = f"{mins}m {secs:05.2f}s"
    else:
        time_str = f"{remaining:06.3f}s"

    if remaining > 10:
        color = "cyan"
    elif remaining > 2:
        color = "yellow"
    else:
        color = "red bold"

    table = Table(show_header=False, border_style="cyan", expand=True, padding=(0, 2))
    table.add_column("Field", style="bold", width=14)
    table.add_column("Value")

    table.add_row("Target Time", f"[bold]{target_str}[/bold]")
    table.add_row("T-minus", f"[{color}]{time_str}[/{color}]")
    table.add_row("Request", request_summary)
    table.add_row("Phase", phase)

    return Panel(table, title="[bold cyan]SiteSwiper Countdown[/bold cyan]", border_style="cyan")


def prompt_input(prompt_text: str, default: str = "") -> str:
    """Prompt the user for input with optional default."""
    if default:
        result = console.input(f"[bold cyan]{prompt_text}[/bold cyan] [{default}]: ")
        return result.strip() or default
    return console.input(f"[bold cyan]{prompt_text}[/bold cyan]: ").strip()


def prompt_confirm(prompt_text: str, default: bool = True) -> bool:
    """Prompt the user for a yes/no confirmation."""
    default_str = "Y/n" if default else "y/N"
    result = console.input(f"[bold cyan]{prompt_text}[/bold cyan] [{default_str}]: ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes")


def prompt_choice(prompt_text: str, choices: list[str]) -> int:
    """Prompt the user to pick from a numbered list.

    Returns:
        The 0-based index of the chosen option.
    """
    console.print(f"\n[bold cyan]{prompt_text}[/bold cyan]")
    for idx, choice in enumerate(choices):
        console.print(f"  [bold]{idx}[/bold]) {choice}")
    console.print()

    while True:
        raw = console.input("[bold cyan]Enter choice: [/bold cyan]").strip()
        try:
            choice_idx = int(raw)
            if 0 <= choice_idx < len(choices):
                return choice_idx
        except ValueError:
            pass
        console.print(f"[red]Please enter a number between 0 and {len(choices) - 1}.[/red]")


# ---------------------------------------------------------------------------
# Latency probe display helpers
# ---------------------------------------------------------------------------

BAR_MAX_WIDTH = 40


def render_latency_progress(
    one_way_samples: list[float | None],
    total: int,
    next_in: float | None = None,
) -> Panel:
    """Return a Rich Panel with a live bar chart of latency probe results.

    Args:
        one_way_samples: Estimated one-way latency per probe in ms (None = timeout).
        total: Total number of probes planned.
        next_in: Seconds until the next probe fires, for countdown display.
    """
    good = [v for v in one_way_samples if v is not None]
    scale = max(good) if good else 100.0

    table = Table(show_header=True, border_style="cyan", padding=(0, 1))
    table.add_column("Probe", style="dim", width=6)
    table.add_column("One-way", width=10)
    table.add_column("Latency chart", min_width=44)

    for i, ow in enumerate(one_way_samples, 1):
        if ow is None:
            table.add_row(str(i), "[red]TIMEOUT[/red]", "")
        else:
            bar_len = max(1, round((ow / scale) * BAR_MAX_WIDTH))
            bar = "█" * bar_len
            color = "green" if ow < 20 else ("yellow" if ow < 50 else "red")
            table.add_row(
                str(i),
                f"[{color}]{ow:.1f}ms[/{color}]",
                f"[{color}]{bar}[/{color}]",
            )

    done = len(one_way_samples)
    if done < total:
        if next_in is not None:
            status = (
                f"  [dim]{done}/{total} probes complete — "
                f"next probe in [bold cyan]{next_in:.0f}s[/bold cyan][/dim]"
            )
        else:
            status = f"  [dim]{done}/{total} probes complete...[/dim]"
    else:
        status = f"  [bold green]All {total} probes complete.[/bold green]"

    return Panel(
        Group(table, Text.from_markup(status)),
        title=f"[bold]Latency to {PROBE_HOST}[/bold]",
        border_style="cyan",
    )


def print_latency_explanation():
    """Display the pre-fire offset concept explanation."""
    console.print(Panel(
        "[bold]What is the pre-fire offset?[/bold]\n\n"
        "When SiteSwiper fires your booking request at T-0, that request must\n"
        "travel across the internet before it reaches Ontario Parks' server.\n"
        "This travel time is called [italic]one-way latency[/italic].\n\n"
        "The [bold cyan]pre-fire offset[/bold cyan] tells SiteSwiper to fire the request\n"
        "[italic]N milliseconds early[/italic], so it [bold]arrives[/bold] at the server as\n"
        "close to the booking open time (7:00:00 AM) as possible.\n\n"
        "[bold yellow]⚠  Important:[/bold yellow] If the offset is [bold]too large[/bold], "
        "your request will arrive\n"
        "[bold red]BEFORE[/bold red] the site is open for booking and will be rejected.\n\n"
        "[bold green]Recommendation:[/bold green] Start with the [bold]10th percentile[/bold]. "
        "It represents a\n"
        "fast-connection day, giving you a good chance of arriving near T-0\n"
        "while keeping a safe margin against premature rejection.",
        title="[bold]Understanding the Pre-fire Offset[/bold]",
        border_style="blue",
        padding=(1, 2),
    ))
    console.print()


def print_latency_percentiles(
    p10: float,
    p25: float,
    p50: float,
    n_good: int,
    n_total: int,
):
    """Display a latency percentile summary table."""
    table = Table(
        title="One-way Latency Percentiles",
        border_style="green",
        padding=(0, 2),
    )
    table.add_column("Percentile", style="bold")
    table.add_column("One-way latency", style="bold cyan")
    table.add_column("Note", style="dim")

    table.add_row("10th  (p10)", f"{p10:.0f} ms", "Fast day — recommended starting point")
    table.add_row("25th  (p25)", f"{p25:.0f} ms", "Slightly more conservative")
    table.add_row("50th  (median)", f"{p50:.0f} ms", "Average — most conservative")

    failed = n_total - n_good
    note = f"Based on {n_good} successful probe(s)"
    if failed:
        note += f" ({failed} timeout(s) excluded)"

    console.print(table)
    console.print(f"  [dim]{note}[/dim]")
    console.print()
