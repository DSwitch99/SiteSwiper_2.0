"""Main CLI — interactive menu and workflow orchestration."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from rich.live import Live
from rich.panel import Panel

from siteswiper.config import (
    CAMPSITES,
    COOKIE_FRESHNESS_WARNING_HOURS,
    DEFAULT_FIRE_HOUR,
    DEFAULT_FIRE_MINUTE,
    DEFAULT_FIRE_SECOND,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PREFIRE_OFFSET_MS,
    NTP_SERVERS,
    PRESET_CURL,
    PREWARM_SECONDS_BEFORE,
    TIMEZONE,
)
from siteswiper.curl_parser import (
    apply_op_booking_fields,
    apply_op_shopper_fields,
    extract_op_booking_fields,
    extract_op_shopper_fields,
    format_body_params,
    is_op_cart_commit,
    parse_curl,
    rebuild_body,
    regenerate_op_session_uuids,
    update_referer_params,
)
from siteswiper.display import (
    console,
    print_banner,
    print_body_params,
    print_capture_guide,
    print_cookies_table,
    print_countdown_status,
    print_headers_table,
    print_latency_explanation,
    print_latency_percentiles,
    print_morning_of_guide,
    print_ntp_status,
    print_op_booking_fields,
    print_pre_commit_guide,
    print_request_summary,
    print_results,
    print_template_guide,
    prompt_choice,
    prompt_confirm,
    prompt_input,
    render_latency_progress,
)
from siteswiper.executor import RequestExecutor
from siteswiper.storage import (
    delete_request,
    get_request_age_hours,
    list_requests,
    load_request,
    save_request,
)
from siteswiper.time_sync import TimeSynchronizer


# ---------------------------------------------------------------------------
# Capture workflow
# ---------------------------------------------------------------------------

def read_multiline_input() -> str:
    """Read multi-line input from the user, terminated by an empty line."""
    console.print("[dim]Paste your cURL command below. Press Enter twice when done:[/dim]")
    lines = []
    empty_count = 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            empty_count += 1
            if empty_count >= 1 and lines:
                break
        else:
            empty_count = 0
            lines.append(line)
    return "\n".join(lines)


def capture_flow() -> dict | None:
    """Walk the user through capturing and parsing a cURL command.

    Returns:
        The parsed request dict, or None if the user cancels.
    """
    print_capture_guide()

    console.print()
    curl_input = read_multiline_input()

    if not curl_input.strip():
        console.print("[yellow]No input received. Returning to menu.[/yellow]")
        return None

    try:
        parsed = parse_curl(curl_input)
    except ValueError as e:
        console.print(f"[red]Error parsing cURL command:[/red] {e}")
        console.print("[yellow]Please try again with a valid cURL command.[/yellow]")
        return None

    console.print()
    print_request_summary(parsed)

    # Show details if requested
    if prompt_confirm("View all headers?", default=False):
        print_headers_table(parsed["headers"])

    if parsed.get("cookies") and prompt_confirm("View all cookies?", default=False):
        print_cookies_table(parsed["cookies"])

    body_info = format_body_params(parsed.get("body"))
    if body_info and prompt_confirm("View body parameters?", default=False):
        print_body_params(body_info)

    # Offer modification
    if prompt_confirm("Modify any request parameters?", default=False):
        parsed = modify_request(parsed)

    return parsed


def _edit_booking_fields(parsed: dict) -> None:
    """Interactive editor for Ontario Parks booking fields (dates, site ID, park ID)."""
    fields = extract_op_booking_fields(parsed["body"])
    if not fields:
        console.print("[yellow]Could not extract booking fields from this request body.[/yellow]")
        return

    print_op_booking_fields(fields)

    console.print("[dim]Press Enter to keep the current value.[/dim]")

    new_start = prompt_input("Start date (YYYY-MM-DD)", fields["startDate"])
    new_end = prompt_input("End date (YYYY-MM-DD)", fields["endDate"])

    # Build campsite selection menu
    campsite_choices = [
        f"Campsite {num} — {name}  (Site ID: {sid})"
        for name, num, sid in CAMPSITES
    ]
    campsite_choices.append("Enter Site ID manually")
    site_idx = prompt_choice("Select campsite", campsite_choices)
    if site_idx < len(CAMPSITES):
        new_resource = CAMPSITES[site_idx][2]  # site_id is already an int
    else:
        new_resource = prompt_input("Site ID (resourceId)", str(fields["resourceId"]))
        try:
            new_resource = int(new_resource)
        except ValueError:
            console.print(f"[yellow]Warning: '{new_resource}' is not an integer, keeping as string.[/yellow]")

    new_location = prompt_input("Park ID (resourceLocationId)", str(fields["resourceLocationId"]))
    try:
        new_location = int(new_location)
    except ValueError:
        console.print(f"[yellow]Warning: '{new_location}' is not an integer, keeping as string.[/yellow]")

    new_fields = {
        "startDate": new_start,
        "endDate": new_end,
        "resourceId": new_resource,
        "resourceLocationId": new_location,
    }

    parsed["body"] = apply_op_booking_fields(parsed["body"], new_fields)
    console.print("[green]Booking fields updated across all 7 nested locations.[/green]")

    # Offer to update the Referer header too
    referer = parsed.get("headers", {}).get("Referer", "")
    if referer and ("startDate=" in referer or "resourceLocationId=" in referer):
        if prompt_confirm("Also update Referer header to match?", default=True):
            parsed["headers"]["Referer"] = update_referer_params(referer, new_fields)
            console.print("[green]Referer header updated.[/green]")

    print_op_booking_fields(new_fields)


def _regenerate_uuids(parsed: dict) -> None:
    """Regenerate session UUIDs in an Ontario Parks cart commit body."""
    try:
        new_body, mapping = regenerate_op_session_uuids(parsed["body"])
    except (KeyError, IndexError, TypeError) as e:
        console.print(f"[red]Failed to regenerate UUIDs:[/red] {e}")
        return

    parsed["body"] = new_body

    from rich.table import Table
    table = Table(title="Regenerated Session UUIDs", border_style="magenta", padding=(0, 1))
    table.add_column("UUID Group", style="magenta")
    table.add_column("New Value", style="white")
    for name, value in mapping.items():
        table.add_row(name, value)
    console.print(table)
    count = len(mapping)
    console.print(f"[green]{count} UUID groups regenerated.[/green]")
    console.print(
        "[dim]Note: resourceBlockerUid is validated server-side. "
        "Regenerated UUIDs only work with two-step mode (pre-commit attached).[/dim]"
    )


def modify_request(parsed: dict) -> dict:
    """Allow the user to modify parts of the parsed request."""
    op_mode = is_op_cart_commit(parsed)

    while True:
        choices = []
        if op_mode:
            choices.append("Edit booking fields (dates, site ID, park ID)")
            choices.append("Regenerate session UUIDs")
        choices.extend([
            "Change URL",
            "Edit a header",
            "Edit body parameters",
            "Refresh cookies from cURL",
            "Done editing",
        ])
        choice = prompt_choice("What would you like to modify?", choices)
        label = choices[choice]

        if label.startswith("Edit booking fields"):
            _edit_booking_fields(parsed)

        elif label.startswith("Regenerate session"):
            _regenerate_uuids(parsed)

        elif label == "Change URL":
            new_url = prompt_input("New URL", parsed["url"])
            if new_url:
                parsed["url"] = new_url
                from urllib.parse import urlparse
                p = urlparse(new_url)
                parsed["host"] = p.hostname
                parsed["path"] = p.path
                console.print("[green]URL updated.[/green]")

        elif label == "Edit a header":
            print_headers_table(parsed["headers"])
            header_name = prompt_input("Header name to edit (exact)")
            if header_name in parsed["headers"]:
                new_value = prompt_input(f"New value for {header_name}")
                parsed["headers"][header_name] = new_value
                console.print(f"[green]Header '{header_name}' updated.[/green]")
            else:
                console.print(f"[yellow]Header '{header_name}' not found.[/yellow]")

        elif label == "Edit body parameters":
            body_info = format_body_params(parsed.get("body"))
            if not body_info:
                console.print("[yellow]Body could not be parsed as form data or JSON.[/yellow]")
                raw_edit = prompt_confirm("Edit raw body text?", default=False)
                if raw_edit:
                    console.print(f"[dim]Current body:[/dim] {parsed.get('body', '')[:300]}")
                    new_body = prompt_input("New body")
                    if new_body:
                        parsed["body"] = new_body
                        console.print("[green]Body updated.[/green]")
            else:
                print_body_params(body_info)
                param_name = prompt_input("Parameter name to edit")
                if param_name in body_info["params"]:
                    current = body_info["params"][param_name]
                    new_value = prompt_input(f"New value for {param_name}", str(current))
                    body_info["params"][param_name] = new_value
                    parsed["body"] = rebuild_body(body_info)
                    console.print(f"[green]Parameter '{param_name}' updated.[/green]")
                else:
                    console.print(f"[yellow]Parameter '{param_name}' not found.[/yellow]")

        elif label == "Refresh cookies from cURL":
            console.print(
                "[dim]Paste any cURL from the Ontario Parks site (even a GET page load).\n"
                "SiteSwiper will extract the session cookies and apply them to this request.[/dim]"
            )
            curl_input = read_multiline_input()
            if curl_input.strip():
                try:
                    donor = parse_curl(curl_input)
                    new_cookies = donor.get("cookies", {})
                    if new_cookies:
                        old_count = len(parsed.get("cookies", {}))
                        parsed.setdefault("cookies", {}).update(new_cookies)
                        console.print(
                            f"[green]Cookies refreshed:[/green] {len(new_cookies)} cookies extracted, "
                            f"{len(parsed['cookies'])} total (was {old_count})."
                        )
                        # Sync X-XSRF-TOKEN header with the new XSRF-TOKEN cookie.
                        # Ontario Parks uses the double-submit CSRF pattern: the header
                        # and cookie must be identical or the server returns 400.
                        new_xsrf = new_cookies.get("XSRF-TOKEN")
                        if new_xsrf:
                            parsed.setdefault("headers", {})["X-XSRF-TOKEN"] = new_xsrf
                            console.print("[green]X-XSRF-TOKEN header synced with new XSRF-TOKEN cookie.[/green]")
                    else:
                        console.print("[yellow]No cookies found in that cURL command.[/yellow]")
                except ValueError as e:
                    console.print(f"[red]Error parsing cURL:[/red] {e}")
            else:
                console.print("[yellow]No input received.[/yellow]")

        elif label == "Done editing":
            break

    console.print()
    print_request_summary(parsed, title="Modified Request")
    return parsed


def save_flow(parsed: dict) -> str | None:
    """Prompt the user to save a captured request.

    Returns:
        The name it was saved under, or None if not saved.
    """
    if not prompt_confirm("Save this request for later?", default=True):
        return None

    name = prompt_input("Name for this request (e.g., 'algonquin-site-42')")
    if not name:
        console.print("[yellow]No name provided, not saving.[/yellow]")
        return None

    notes = prompt_input("Notes (optional)", "")
    path = save_request(name, parsed, notes=notes)
    console.print(f"[green]Saved to:[/green] {path}")
    return name


# ---------------------------------------------------------------------------
# Load / List workflows
# ---------------------------------------------------------------------------

def load_flow() -> dict | None:
    """Let the user select and load a saved request.

    Returns:
        The loaded request data dict, or None if cancelled.
    """
    requests = list_requests()
    if not requests:
        console.print("[yellow]No saved requests found.[/yellow]")
        console.print("[dim]Use 'Capture new request' to save one first.[/dim]")
        return None

    choices = [f"{r['name']}  ({r['method']} {r['host']}{' - ' + r.get('saved_at', '')[:10] if r.get('saved_at') else ''})"
               for r in requests]
    choices.append("Cancel")

    idx = prompt_choice("Select a saved request:", choices)
    if idx == len(choices) - 1:
        return None

    selected = requests[idx]
    data = load_request(selected["name"])

    console.print()
    print_request_summary(data["request"])

    # Check freshness
    age_hours = get_request_age_hours(data)
    if age_hours is not None and age_hours > COOKIE_FRESHNESS_WARNING_HOURS:
        console.print(
            f"[bold yellow]Warning:[/bold yellow] This request was saved "
            f"[bold]{age_hours:.1f} hours ago[/bold]. Session cookies may have expired!\n"
            f"Consider capturing a fresh request closer to your booking time."
        )
        console.print()

    return data


def list_flow():
    """Display all saved requests."""
    requests = list_requests()
    if not requests:
        console.print("[yellow]No saved requests found.[/yellow]")
        return

    from rich.table import Table
    table = Table(title="Saved Requests", border_style="cyan", padding=(0, 1))
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", style="cyan")
    table.add_column("Method", style="bold")
    table.add_column("Host", style="white")
    table.add_column("Saved", style="dim")

    for idx, r in enumerate(requests):
        saved_at = r.get("saved_at", "?")[:16].replace("T", " ")
        table.add_row(str(idx), r["name"], r["method"], r["host"], saved_at)

    console.print(table)
    console.print()

    # Offer delete
    if prompt_confirm("Delete any saved requests?", default=False):
        name = prompt_input("Name to delete")
        if delete_request(name):
            console.print(f"[green]Deleted '{name}'.[/green]")
        else:
            console.print(f"[yellow]Request '{name}' not found.[/yellow]")


# ---------------------------------------------------------------------------
# Schedule & Fire workflow
# ---------------------------------------------------------------------------

def get_target_time() -> datetime:
    """Prompt the user for the target fire time.

    Returns:
        A timezone-aware datetime for the target time.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)

    default_time = now.replace(
        hour=DEFAULT_FIRE_HOUR,
        minute=DEFAULT_FIRE_MINUTE,
        second=DEFAULT_FIRE_SECOND,
        microsecond=0,
    )
    # If it's already past 7 AM today, default to tomorrow
    if now >= default_time:
        default_time += timedelta(days=1)

    default_str = default_time.strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"[dim]Default target: {default_str} ({TIMEZONE})[/dim]")

    choices = [
        f"Use default ({default_str})",
        "Enter custom time",
        "Fire in N seconds (for testing)",
    ]
    choice = prompt_choice("When should the request fire?", choices)

    if choice == 0:
        return default_time

    elif choice == 1:
        time_str = prompt_input("Enter target time (YYYY-MM-DD HH:MM:SS)")
        try:
            target = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return target.replace(tzinfo=tz)
        except ValueError:
            console.print("[red]Invalid format. Using default.[/red]")
            return default_time

    elif choice == 2:
        seconds_str = prompt_input("Fire in how many seconds?", "30")
        try:
            seconds = int(seconds_str)
            return datetime.now(tz) + timedelta(seconds=seconds)
        except ValueError:
            console.print("[red]Invalid number. Using 30 seconds.[/red]")
            return datetime.now(tz) + timedelta(seconds=30)

    return default_time


def schedule_flow():
    """Full schedule-and-fire workflow."""
    # Step 1: Get request
    console.print("\n[bold]Step 1: Select a request to fire[/bold]")
    data = load_flow()
    if data is None:
        # Offer to capture a new one
        if prompt_confirm("Capture a new request instead?", default=True):
            parsed = capture_flow()
            if parsed is None:
                return
            save_flow(parsed)
        else:
            return
        pre_commit_parsed = None
    else:
        parsed = data["request"]
        pre_commit_parsed = data.get("pre_commit")
        if pre_commit_parsed:
            console.print(
                "[cyan]Two-step mode detected:[/cyan] a pre-commit (step 1) request is attached.\n"
                "[dim]SiteSwiper will fire step 1 first, extract fresh UUIDs, "
                "inject them into the commit body, then fire step 2.[/dim]"
            )

    # Auto-prepare Ontario Parks requests
    if is_op_cart_commit(parsed):
        if not pre_commit_parsed:
            # Warn: single-step mode lacks the pre-commit step that creates the
            # server-side resource blocker.  The commit endpoint validates
            # resourceBlockerUid against server state, so single-step usually
            # fails with 400 "Invalid Blocker" or "ResourceUnavailable".
            console.print()
            console.print(Panel(
                "[bold yellow]No pre-commit request attached.[/bold yellow]\n\n"
                "Ontario Parks validates [bold]resourceBlockerUid[/bold] against a server-side record\n"
                "created by the pre-commit request. Without it, the commit will likely fail\n"
                "with [bold]400 Bad Request[/bold] — \"Invalid Blocker\" or \"ResourceUnavailable\".\n\n"
                "[bold green]Recommended:[/bold green] Go back and use [bold]\"8 - Set up pre-commit request\"[/bold]\n"
                "to attach a pre-commit step. SiteSwiper will fire it first at T-0, extract\n"
                "fresh UUIDs from the server response, and inject them into the commit body.",
                title="[bold yellow]Two-Step Mode Required[/bold yellow]",
                border_style="yellow",
            ))
            if not prompt_confirm("Continue anyway with single-step mode?", default=False):
                return

        # Auto-sync XSRF token (double-submit CSRF pattern) — both modes
        xsrf_cookie = parsed.get("cookies", {}).get("XSRF-TOKEN")
        xsrf_header = parsed.get("headers", {}).get("X-XSRF-TOKEN")
        if xsrf_cookie and xsrf_cookie != xsrf_header:
            parsed.setdefault("headers", {})["X-XSRF-TOKEN"] = xsrf_cookie
            console.print("[green]X-XSRF-TOKEN header synced with cookie.[/green]")

    # Step 2: Target time
    console.print("\n[bold]Step 2: Set target time[/bold]")
    target = get_target_time()
    tz = ZoneInfo(TIMEZONE)
    target_str = target.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    console.print(f"[green]Target:[/green] {target_str}")

    # Step 3: Retry settings + pre-fire offset
    console.print("\n[bold]Step 3: Retry settings[/bold]")
    retries_str = prompt_input("Max retries", str(DEFAULT_MAX_RETRIES))
    try:
        max_retries = int(retries_str)
    except ValueError:
        max_retries = DEFAULT_MAX_RETRIES

    console.print("[dim]Pre-fire offset: fire N ms early to compensate for network latency.[/dim]")
    console.print("[dim]Use your measured round-trip time (elapsed_ms from logs) as a guide.[/dim]")
    offset_str = prompt_input("Pre-fire offset (ms)", str(DEFAULT_PREFIRE_OFFSET_MS))
    try:
        prefire_offset_ms = max(0, int(offset_str))
    except ValueError:
        prefire_offset_ms = DEFAULT_PREFIRE_OFFSET_MS
    prefire_offset_s = prefire_offset_ms / 1000.0

    # Step 4: NTP sync
    console.print("\n[bold]Step 4: Synchronizing clock...[/bold]")
    syncer = TimeSynchronizer()
    try:
        offset = syncer.sync()
        print_ntp_status(offset * 1000)
        console.print(f"[dim]Reached {syncer.servers_reached}/{len(NTP_SERVERS)} NTP servers[/dim]")
    except RuntimeError as e:
        console.print(f"[yellow]NTP sync failed:[/yellow] {e}")
        console.print("[yellow]Proceeding with local clock (may be inaccurate).[/yellow]")
        if not prompt_confirm("Continue without NTP sync?", default=True):
            return

    # Check remaining time
    remaining = syncer.seconds_until(target)
    if remaining < 0:
        console.print("[red]Target time has already passed![/red]")
        return
    elif remaining < 5:
        console.print("[yellow]Warning: Target time is very close![/yellow]")

    # Step 5: Confirm
    console.print()
    request_summary = f"{parsed['method']} {parsed.get('host', '?')}{parsed.get('path', '?')}"
    prefire_str = f"{prefire_offset_ms}ms early" if prefire_offset_ms > 0 else "disabled"
    mode_str = "Two-step (pre-commit → commit)" if pre_commit_parsed else "Single request"
    console.print(Panel(
        f"[bold]Target:[/bold]        {target_str}\n"
        f"[bold]Request:[/bold]       {request_summary}\n"
        f"[bold]Mode:[/bold]          {mode_str}\n"
        f"[bold]Retries:[/bold]       {max_retries}\n"
        f"[bold]Clock offset:[/bold]  {syncer.offset_ms:+.1f}ms\n"
        f"[bold]Pre-fire offset:[/bold] {prefire_str}",
        title="[bold]Ready to Fire[/bold]",
        border_style="green",
    ))

    if not prompt_confirm("Start countdown?", default=True):
        return

    # Step 6: Countdown + fire
    executor = RequestExecutor(parsed)
    step1_executor = RequestExecutor(pre_commit_parsed) if pre_commit_parsed else None

    try:
        console.print("\n[bold cyan]Countdown started...[/bold cyan]")
        console.print("[dim]Press Ctrl+C to abort.[/dim]\n")

        def on_tick(remaining_secs):
            """Update the countdown display."""
            if remaining_secs > PREWARM_SECONDS_BEFORE:
                phase = "Waiting..."
            elif remaining_secs > 2:
                phase = "Connection pre-warmed"
            else:
                phase = "[red bold]SPIN-WAIT ENGAGED[/red bold]"

            panel = print_countdown_status(remaining_secs, target_str, request_summary, phase)
            live.update(panel)

        def on_prewarm():
            """Pre-warm the connection (step 1's host in two-step mode)."""
            console.print("[cyan]Pre-warming connection...[/cyan]")
            warm_executor = step1_executor if step1_executor else executor
            success = warm_executor.prewarm()
            if success:
                console.print("[green]Connection pre-warmed.[/green]")
            else:
                console.print("[yellow]Pre-warm failed (will still attempt request).[/yellow]")

        with Live(console=console, refresh_per_second=4) as live:
            syncer.wait_until_with_prewarm(
                target,
                prewarm_callback=on_prewarm,
                prewarm_seconds=PREWARM_SECONDS_BEFORE,
                on_tick=on_tick,
                prefire_offset_s=prefire_offset_s,
            )

        if step1_executor:
            # Two-step mode: fire pre-commit, inject UUIDs, fire commit
            console.print("\n[bold green]FIRING TWO-STEP REQUEST![/bold green]\n")
            step1_result, step2_results = executor.fire_two_step(step1_executor)

            console.print("[bold cyan]Step 1 — Pre-commit:[/bold cyan]")
            print_results([{
                "attempt": step1_result.attempt,
                "status_code": step1_result.status_code,
                "elapsed_ms": step1_result.elapsed_ms,
                "server_delta_ms": step1_result.server_delta_ms,
                "summary": step1_result.summary,
            }])

            if step2_results is not None:
                console.print("[bold cyan]Step 2 — Commit:[/bold cyan]")
                print_results([{
                    "attempt": r.attempt,
                    "status_code": r.status_code,
                    "elapsed_ms": r.elapsed_ms,
                    "server_delta_ms": r.server_delta_ms,
                    "summary": r.summary,
                } for r in step2_results])
                successful = [r for r in step2_results if r.success]
            elif step1_result.success:
                # Step 1 succeeded but UUID injection failed — step 1 may
                # have already completed the booking (e.g. the server returned
                # a bare timestamp instead of a cart object with UUIDs).
                uuid_detail = step1_result.error or "Could not extract UUIDs from step 1 response."
                console.print(f"[yellow]Step 2 skipped:[/yellow] {uuid_detail}")
                console.print(
                    "[dim]Step 1 returned HTTP 200, so the booking may already "
                    "be complete. Check your cart in the browser.[/dim]"
                )
                successful = [step1_result]
            else:
                error_detail = step1_result.error or "Step 1 returned a non-2xx status."
                console.print(f"[red]Step 2 not fired:[/red] {error_detail}")
                successful = []

        else:
            # Single-step mode (unchanged)
            console.print("\n[bold green]FIRING REQUEST![/bold green]\n")
            results = executor.fire_with_retries(max_retries=max_retries)
            print_results([{
                "attempt": r.attempt,
                "status_code": r.status_code,
                "elapsed_ms": r.elapsed_ms,
                "server_delta_ms": r.server_delta_ms,
                "summary": r.summary,
            } for r in results])
            successful = [r for r in results if r.success]

        # Show log locations
        if executor.log_dir:
            console.print(f"[dim]Response logs saved to:[/dim] {executor.log_dir}")
        if step1_executor and step1_executor.log_dir:
            console.print(f"[dim]Step 1 logs saved to:[/dim] {step1_executor.log_dir}")
        console.print()

        # Check final outcome
        if successful:
            console.print(Panel(
                "[bold green]BOOKING REQUEST SUCCEEDED![/bold green]\n\n"
                "Now open your browser and check your Ontario Parks cart.\n"
                "Complete the checkout process to finalize your reservation.",
                border_style="green",
            ))
        else:
            console.print(Panel(
                "[bold red]All attempts failed.[/bold red]\n\n"
                "The campsite may have been taken by another user.\n"
                "Check the response logs for full details.",
                border_style="red",
            ))

            # Show last response body if available
            last_result = results[-1] if results else step1_result
            if last_result.body and prompt_confirm("View last response body?", default=False):
                console.print(Panel(last_result.body[:1000], title="Response Body", border_style="dim"))

    except KeyboardInterrupt:
        console.print("\n[yellow]Countdown aborted by user.[/yellow]")
    finally:
        executor.close()
        if step1_executor:
            step1_executor.close()


# ---------------------------------------------------------------------------
# Pre-commit setup workflow
# ---------------------------------------------------------------------------

def add_pre_commit_flow(request_name: str) -> None:
    """Capture and attach a pre-commit (step 1) request to an existing saved request.

    After this, "Schedule and fire" will automatically run the pre-commit
    request first, extract fresh UUIDs from its response, inject them into
    the commit body, then fire the commit.
    """
    try:
        data = load_request(request_name)
    except FileNotFoundError:
        console.print(f"[red]Request '{request_name}' not found.[/red]")
        return

    print_pre_commit_guide()

    console.print()
    curl_input = read_multiline_input()
    if not curl_input.strip():
        console.print("[yellow]No input received. Returning to menu.[/yellow]")
        return

    try:
        pre_commit_parsed = parse_curl(curl_input)
    except ValueError as e:
        console.print(f"[red]Error parsing cURL command:[/red] {e}")
        return

    console.print()
    print_request_summary(pre_commit_parsed, title="Step 1 (Pre-commit) Request")

    # Sync booking fields from the commit request to the pre-commit request.
    # The pre-commit cURL is typically captured from a different (available) site
    # used as a template, so its body contains the wrong site/dates.  We need to
    # overwrite them with the values from the commit request so step 1 creates
    # a resource blocker for the *correct* site.
    commit_fields = extract_op_booking_fields(data["request"].get("body", ""))
    pre_commit_fields = extract_op_booking_fields(pre_commit_parsed.get("body", ""))

    if commit_fields and pre_commit_fields:
        if commit_fields != pre_commit_fields:
            console.print()
            console.print("[yellow]The pre-commit request has different booking fields than your commit request:[/yellow]")
            console.print(f"  [dim]Pre-commit:[/dim] site {pre_commit_fields['resourceId']}, "
                          f"{pre_commit_fields['startDate']} → {pre_commit_fields['endDate']}, "
                          f"park {pre_commit_fields['resourceLocationId']}")
            console.print(f"  [dim]Commit:    [/dim] site {commit_fields['resourceId']}, "
                          f"{commit_fields['startDate']} → {commit_fields['endDate']}, "
                          f"park {commit_fields['resourceLocationId']}")
            if prompt_confirm("Update pre-commit to match your commit request?", default=True):
                pre_commit_parsed["body"] = apply_op_booking_fields(
                    pre_commit_parsed["body"], commit_fields
                )
                # Update Referer header in pre-commit if applicable
                pre_referer = pre_commit_parsed.get("headers", {}).get("Referer", "")
                if pre_referer and ("startDate=" in pre_referer or "resourceLocationId=" in pre_referer):
                    pre_commit_parsed["headers"]["Referer"] = update_referer_params(pre_referer, commit_fields)
                console.print("[green]Pre-commit booking fields synced with commit request.[/green]")
                print_op_booking_fields(commit_fields)
    elif commit_fields and not pre_commit_fields:
        console.print(
            "[dim]Could not extract booking fields from pre-commit body — "
            "make sure the site/dates are correct if you edited them.[/dim]"
        )

    if not prompt_confirm("Attach this as the pre-commit step?", default=True):
        return

    path = save_request(
        data["name"],
        data["request"],
        notes=data.get("notes", ""),
        pre_commit=pre_commit_parsed,
    )
    console.print(f"[green]Pre-commit request attached. Saved to:[/green] {path}")
    console.print(
        "[dim]When you 'Schedule and fire', SiteSwiper will fire the pre-commit "
        "request first, extract session UUIDs from its response, inject them "
        "into the commit body, then fire the commit.[/dim]"
    )


# ---------------------------------------------------------------------------
# Preset template workflow
# ---------------------------------------------------------------------------

def preset_template_flow() -> None:
    """Create a new request starting from the built-in preset template.

    Parses the embedded cURL, walks the user through editing booking fields
    (dates, site ID, park ID), then saves the result as a named request.
    The preset cookies are stale — the user must refresh them before firing.
    """
    console.print(
        "\n[bold]Built-in preset template[/bold]\n"
        "[dim]This is a real captured Ontario Parks cart/commit request. "
        "You'll customise the dates and target site, then refresh the cookies "
        "closer to booking time.[/dim]"
    )

    try:
        parsed = parse_curl(PRESET_CURL)
    except ValueError as e:
        console.print(f"[red]Error loading preset:[/red] {e}")
        return

    console.print()
    print_request_summary(parsed)

    console.print(
        "\n[bold yellow]Note:[/bold yellow] The session cookies embedded in the "
        "preset are expired. Use [bold]Morning-of Flow[/bold] (or "
        "[bold]Tools → Refresh cookies[/bold]) to replace them before firing."
    )

    print_template_guide()

    console.print("\n[bold]Edit request parameters[/bold]")
    parsed = modify_request(parsed)

    console.print("\n[bold]Save as new request[/bold]")
    save_flow(parsed)


# ---------------------------------------------------------------------------
# Template workflow
# ---------------------------------------------------------------------------

def template_flow():
    """Create a new request by modifying a saved template.

    This lets users prepare a booking request for a site that isn't available
    yet by starting from a captured request for a different (available) site,
    then swapping in the target site's parameters and fresh cookies.
    """
    console.print("\n[bold]Step 1: Select a template request[/bold]")
    data = load_flow()
    if data is None:
        return

    parsed = data["request"]

    # Show the template guide
    print_template_guide()

    # Let the user modify the request (body params, cookies, etc.)
    console.print("\n[bold]Step 2: Edit request parameters[/bold]")
    parsed = modify_request(parsed)

    # Save as a new request
    console.print("\n[bold]Step 3: Save as new request[/bold]")
    save_flow(parsed)


# ---------------------------------------------------------------------------
# Dry run workflow
# ---------------------------------------------------------------------------

def dry_run_flow():
    """Test the workflow without actually sending a request."""
    data = load_flow()
    if data is None:
        console.print("[yellow]No request selected.[/yellow]")
        return

    parsed = data["request"]
    executor = RequestExecutor(parsed, dry_run=True)

    try:
        console.print("\n[bold]Dry Run Summary:[/bold]")
        console.print(Panel(executor.get_dry_run_summary(), border_style="yellow"))

        if prompt_confirm("Run a timed dry-run (test countdown)?", default=True):
            target = get_target_time()
            tz = ZoneInfo(TIMEZONE)
            target_str = target.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")

            syncer = TimeSynchronizer()
            try:
                syncer.sync()
            except RuntimeError:
                pass  # OK for dry run

            request_summary = f"{parsed['method']} {parsed.get('host', '?')}{parsed.get('path', '?')}"

            try:
                with Live(console=console, refresh_per_second=4) as live:
                    def on_tick(remaining_secs):
                        phase = "[yellow]DRY RUN[/yellow] - Waiting..."
                        panel = print_countdown_status(remaining_secs, target_str, request_summary, phase)
                        live.update(panel)

                    syncer.wait_until(target, on_tick=on_tick)

                console.print("\n[bold yellow]DRY RUN - Would have fired request here.[/bold yellow]")
                result = executor.fire_once()
                console.print(f"[dim]Result: {result.summary}[/dim]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Dry run aborted.[/yellow]")
    finally:
        executor.close()


# ---------------------------------------------------------------------------
# Clock sync workflow
# ---------------------------------------------------------------------------

def clock_sync_flow():
    """Check NTP sync status."""
    console.print("\n[bold]Checking clock synchronization...[/bold]\n")
    syncer = TimeSynchronizer()

    try:
        offset = syncer.sync()
        print_ntp_status(offset * 1000)

        tz = ZoneInfo(TIMEZONE)
        true_time = syncer.get_true_datetime().astimezone(tz)
        local_time = datetime.now(tz)

        console.print(f"  [dim]NTP-corrected time:[/dim] {true_time.strftime('%H:%M:%S.%f')[:-3]}")
        console.print(f"  [dim]Local system time:[/dim]  {local_time.strftime('%H:%M:%S.%f')[:-3]}")
        console.print(f"  [dim]NTP servers reached:[/dim] {syncer.servers_reached}")
        console.print()

    except RuntimeError as e:
        console.print(f"[red]NTP sync failed:[/red] {e}")


# ---------------------------------------------------------------------------
# Morning-of Flow (combined: regenerate UUIDs + refresh cookies + pre-commit)
# ---------------------------------------------------------------------------

def morning_of_flow() -> None:
    """Combined morning-of booking preparation flow.

    Guides the user through three steps using a single CURL from any available site:
      1. Regenerate session UUIDs on the saved commit request.
      2. Refresh session cookies from the donor CURL.
      3. Attach the donor request as the pre-commit step (booking fields auto-synced).
    """
    # Step 1: Select request
    data = load_flow()
    if data is None:
        return

    parsed = data["request"]

    if not is_op_cart_commit(parsed):
        console.print("[yellow]This request does not look like an Ontario Parks cart commit.[/yellow]")
        return

    # Step 2: Regenerate session UUIDs
    console.print("\n[bold cyan]Step 1/3 — Regenerating session UUIDs[/bold cyan]")
    _regenerate_uuids(parsed)
    path = save_request(
        data["name"],
        parsed,
        notes=data.get("notes", ""),
        pre_commit=data.get("pre_commit"),
    )
    console.print(f"[green]UUIDs regenerated and saved to:[/green] {path}")

    # Step 3: Capture a cURL from an available site (automated or manual)
    console.print()
    capture_mode = prompt_choice(
        "Step 2/3 — How would you like to capture your session?",
        [
            "Automated  — open a browser window (recommended)",
            "Manual     — paste a cURL command",
        ],
    )

    if capture_mode == 0:
        console.print("\n[dim]Launching browser — follow the overlay instructions.[/dim]")
        from siteswiper.browser_capture import capture_commit_curl
        donor = capture_commit_curl()
        if donor is None:
            console.print("[yellow]Browser capture was cancelled or failed. Returning to menu.[/yellow]")
            return
        console.print("[green]Request captured successfully.[/green]")
    else:
        print_morning_of_guide()
        console.print("\n[bold cyan]Step 2/3 — Paste your cURL[/bold cyan]")
        curl_input = read_multiline_input()
        if not curl_input.strip():
            console.print("[yellow]No input received. Returning to menu.[/yellow]")
            return
        try:
            donor = parse_curl(curl_input)
        except ValueError as e:
            console.print(f"[red]Error parsing cURL:[/red] {e}")
            return

    # Step 4: Refresh cookies from the donor cURL
    console.print("\n[bold cyan]Step 3/3 — Refreshing cookies and attaching pre-commit[/bold cyan]")
    new_cookies = donor.get("cookies", {})
    if not new_cookies:
        console.print("[yellow]No cookies found in that cURL command.[/yellow]")
        return

    old_count = len(parsed.get("cookies", {}))
    parsed.setdefault("cookies", {}).update(new_cookies)
    console.print(
        f"[green]Cookies refreshed:[/green] {len(new_cookies)} extracted, "
        f"{len(parsed['cookies'])} total (was {old_count})."
    )

    new_xsrf = new_cookies.get("XSRF-TOKEN")
    if new_xsrf:
        parsed.setdefault("headers", {})["X-XSRF-TOKEN"] = new_xsrf
        console.print("[green]X-XSRF-TOKEN header synced.[/green]")

    # Sync personal info (name, phone, address) from pre-commit into commit body
    shopper_fields = extract_op_shopper_fields(donor.get("body", ""))
    if shopper_fields and any(v for v in shopper_fields.values() if v):
        parsed["body"] = apply_op_shopper_fields(parsed.get("body", "{}"), shopper_fields)
        console.print(
            f"[green]Personal info synced[/green] from pre-commit "
            f"([bold]{shopper_fields.get('firstName', '')} "
            f"{shopper_fields.get('lastName', '')}[/bold])."
        )

    # Step 5: Sync booking fields and attach donor as pre-commit
    commit_fields = extract_op_booking_fields(parsed.get("body", ""))
    pre_commit_fields = extract_op_booking_fields(donor.get("body", ""))

    if commit_fields and pre_commit_fields:
        if commit_fields != pre_commit_fields:
            donor["body"] = apply_op_booking_fields(donor["body"], commit_fields)
            pre_referer = donor.get("headers", {}).get("Referer", "")
            if pre_referer and ("startDate=" in pre_referer or "resourceLocationId=" in pre_referer):
                donor["headers"]["Referer"] = update_referer_params(pre_referer, commit_fields)
            console.print("[green]Pre-commit booking fields synced with your commit request.[/green]")
            print_op_booking_fields(commit_fields)
    elif commit_fields and not pre_commit_fields:
        console.print(
            "[dim]Could not extract booking fields from pre-commit body — "
            "verify dates/site are correct.[/dim]"
        )

    path = save_request(
        data["name"],
        parsed,
        notes=data.get("notes", ""),
        pre_commit=donor,
    )
    console.print(f"\n[bold green]Morning-of setup complete![/bold green] Saved to: {path}")
    console.print(
        "[dim]UUIDs regenerated, cookies refreshed, and pre-commit step attached.\n"
        "Use 'Schedule and fire' when ready.[/dim]"
    )


# ---------------------------------------------------------------------------
# Regenerate UUIDs workflow (top-level)
# ---------------------------------------------------------------------------

def regenerate_uuids_flow():
    """Regenerate session UUIDs on a saved request."""
    data = load_flow()
    if data is None:
        return

    parsed = data["request"]

    if not is_op_cart_commit(parsed):
        console.print("[yellow]This request does not look like an Ontario Parks cart commit.[/yellow]")
        return

    _regenerate_uuids(parsed)

    path = save_request(
        data["name"],
        parsed,
        notes=data.get("notes", ""),
        pre_commit=data.get("pre_commit"),
    )
    console.print(f"[green]Saved to:[/green] {path}")


# ---------------------------------------------------------------------------
# Refresh cookies workflow (top-level)
# ---------------------------------------------------------------------------

def refresh_cookies_flow():
    """Refresh session cookies on a saved request (and its pre-commit) from a new cURL."""
    data = load_flow()
    if data is None:
        return

    parsed = data["request"]
    pre_commit = data.get("pre_commit")

    console.print(
        "[dim]Paste any cURL from the Ontario Parks site (even a GET page load).\n"
        "SiteSwiper will extract the session cookies and apply them to this request.[/dim]"
    )
    curl_input = read_multiline_input()
    if not curl_input.strip():
        console.print("[yellow]No input received.[/yellow]")
        return

    try:
        donor = parse_curl(curl_input)
    except ValueError as e:
        console.print(f"[red]Error parsing cURL:[/red] {e}")
        return

    new_cookies = donor.get("cookies", {})
    if not new_cookies:
        console.print("[yellow]No cookies found in that cURL command.[/yellow]")
        return

    old_count = len(parsed.get("cookies", {}))
    parsed.setdefault("cookies", {}).update(new_cookies)
    console.print(
        f"[green]Cookies refreshed:[/green] {len(new_cookies)} cookies extracted, "
        f"{len(parsed['cookies'])} total (was {old_count})."
    )

    # Sync X-XSRF-TOKEN header with the new XSRF-TOKEN cookie
    new_xsrf = new_cookies.get("XSRF-TOKEN")
    if new_xsrf:
        parsed.setdefault("headers", {})["X-XSRF-TOKEN"] = new_xsrf
        console.print("[green]X-XSRF-TOKEN header synced with new XSRF-TOKEN cookie.[/green]")

    # Also refresh cookies on pre-commit request if one is attached
    if pre_commit:
        pre_commit.setdefault("cookies", {}).update(new_cookies)
        if new_xsrf:
            pre_commit.setdefault("headers", {})["X-XSRF-TOKEN"] = new_xsrf
        console.print("[green]Pre-commit request cookies also refreshed.[/green]")

    path = save_request(
        data["name"],
        parsed,
        notes=data.get("notes", ""),
        pre_commit=pre_commit,
    )
    console.print(f"[green]Saved to:[/green] {path}")


# ---------------------------------------------------------------------------
# Latency probe
# ---------------------------------------------------------------------------

def latency_probe_flow() -> None:
    """Measure one-way latency to Ontario Parks and recommend a pre-fire offset."""
    import time

    import httpx
    from rich.live import Live

    from siteswiper.latency import (
        PROBE_COUNT,
        PROBE_INTERVAL_S,
        PROBE_TIMEOUT_S,
        PROBE_URL,
        calc_percentile,
        one_way_ms,
        probe_once,
    )

    console.print(Panel(
        f"[bold]Measuring one-way latency to reservations.ontarioparks.ca[/bold]\n\n"
        f"[dim]Sending {PROBE_COUNT} HTTP HEAD requests over 5 minutes "
        f"(one every {PROBE_INTERVAL_S:.0f} seconds).\n"
        "Latency is estimated as half the round-trip time (RTT ÷ 2),\n"
        "matching the pre-warmed connection SiteSwiper uses at booking time.\n\n"
        "Press [bold]Ctrl+C[/bold] to stop early and use partial results.[/dim]",
        title="[bold cyan]Server Latency Probe[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))

    ow_samples: list[float | None] = []

    try:
        with httpx.Client(
            http2=True,
            timeout=PROBE_TIMEOUT_S,
            verify=True,
            follow_redirects=True,
        ) as client:
            # Silent warm-up to establish TCP/TLS (not counted in results)
            try:
                client.head(PROBE_URL)
            except Exception:
                pass

            with Live(
                render_latency_progress(ow_samples, PROBE_COUNT),
                refresh_per_second=2,
                console=console,
                transient=False,
            ) as live:
                for i in range(PROBE_COUNT):
                    rtt = probe_once(client)
                    ow = one_way_ms(rtt) if rtt is not None else None
                    ow_samples.append(ow)
                    live.update(render_latency_progress(ow_samples, PROBE_COUNT))

                    if i < PROBE_COUNT - 1:
                        deadline = time.monotonic() + PROBE_INTERVAL_S
                        while True:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                break
                            live.update(
                                render_latency_progress(ow_samples, PROBE_COUNT, next_in=remaining)
                            )
                            time.sleep(0.5)

    except KeyboardInterrupt:
        console.print(f"\n[yellow]Stopped early — {len(ow_samples)} probe(s) recorded.[/yellow]")
        if not ow_samples:
            return

    # --- Analysis ---
    good_ow = [v for v in ow_samples if v is not None]
    if not good_ow:
        console.print("[red]All probes timed out. Check your internet connection.[/red]")
        return

    p10 = calc_percentile(good_ow, 10)
    p25 = calc_percentile(good_ow, 25)
    p50 = calc_percentile(good_ow, 50)

    print_latency_explanation()
    print_latency_percentiles(p10, p25, p50, n_good=len(good_ow), n_total=len(ow_samples))

    offset_choices = [
        f"10th percentile  —  {p10:.0f} ms  (recommended)",
        f"25th percentile  —  {p25:.0f} ms",
        f"50th percentile (median)  —  {p50:.0f} ms",
        "Enter a custom value",
    ]
    idx = prompt_choice("Select your pre-fire offset", offset_choices)

    if idx == 0:
        chosen_ms = round(p10)
    elif idx == 1:
        chosen_ms = round(p25)
    elif idx == 2:
        chosen_ms = round(p50)
    else:
        raw = prompt_input("Custom offset (ms)", str(round(p10)))
        try:
            chosen_ms = max(0, int(raw))
        except ValueError:
            chosen_ms = round(p10)

    console.print(Panel(
        f"[bold cyan]Your pre-fire offset:[/bold cyan]  "
        f"[bold green]{chosen_ms} ms[/bold green]\n\n"
        f"When [bold]Schedule and fire[/bold] prompts for the pre-fire offset,\n"
        f"enter [bold cyan]{chosen_ms}[/bold cyan].",
        title="[bold]Pre-fire Offset Set[/bold]",
        border_style="green",
        padding=(1, 2),
    ))


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

MENU_OPTIONS = [
    # --- Primary workflow (in order) ---
    "Capture new request",
    "Use preset template",
    "Create from template",
    "Morning-of Flow",
    "Schedule and fire",
    # --- Utilities ---
    "List saved requests",
    "Measure server latency",
    "Tools",
    "Exit",
]

TOOLS_MENU_OPTIONS = [
    "Refresh cookies",
    "Set up pre-commit request",
    "Dry run",
    "Check clock sync",
    "Back",
]


def tools_flow() -> None:
    """Submenu for utility tools."""
    while True:
        try:
            choice = prompt_choice("Tools:", TOOLS_MENU_OPTIONS)
        except (KeyboardInterrupt, EOFError):
            return

        try:
            if choice == 0:  # Refresh cookies
                refresh_cookies_flow()

            elif choice == 1:  # Set up pre-commit request
                requests = list_requests()
                if not requests:
                    console.print("[yellow]No saved requests found. Capture a commit request first.[/yellow]")
                else:
                    choices = [r["name"] for r in requests] + ["Cancel"]
                    idx = prompt_choice("Select the saved commit request to attach a pre-commit step to:", choices)
                    if idx < len(requests):
                        add_pre_commit_flow(requests[idx]["name"])

            elif choice == 2:  # Dry run
                dry_run_flow()

            elif choice == 3:  # Check clock sync
                clock_sync_flow()

            elif choice == 4:  # Back
                return

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled.[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}")
            console.print("[dim]Returning to tools menu...[/dim]")

        console.print()


def main():
    """Main entry point for SiteSwiper."""
    print_banner()

    while True:
        try:
            choice = prompt_choice("What would you like to do?", MENU_OPTIONS)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        try:
            if choice == 0:  # Capture new request
                parsed = capture_flow()
                if parsed:
                    save_flow(parsed)

            elif choice == 1:  # Use preset template
                preset_template_flow()

            elif choice == 2:  # Create from template
                template_flow()

            elif choice == 3:  # Morning-of Flow
                morning_of_flow()

            elif choice == 4:  # Schedule and fire
                schedule_flow()

            elif choice == 5:  # List saved requests
                list_flow()

            elif choice == 6:  # Measure server latency
                latency_probe_flow()

            elif choice == 7:  # Tools
                tools_flow()

            elif choice == 8:  # Exit
                console.print("[dim]Goodbye![/dim]")
                break

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled.[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}")
            console.print("[dim]Returning to menu...[/dim]")

        console.print()


if __name__ == "__main__":
    main()
