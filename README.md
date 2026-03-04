# SiteSwiper 🏕️

Ontario Parks campsite booking automation tool. Captures the exact HTTP request your browser makes when booking a campsite, then fires it at precisely 7:00 AM using NTP-synchronized timing — bypassing browser UI latency.

## How it works

Ontario Parks releases campsites at **7:00 AM EST**, 5 months in advance. Sites sell out in seconds. SiteSwiper:

1. **Guides you** through capturing the real booking request from your browser's Developer Tools
2. **Schedules it** to fire at exactly 7:00 AM using NTP clock correction + sub-millisecond spin-wait timing
3. **Pre-warms** the TCP/TLS connection 10 seconds before T-0 (saves ~100–300ms)
4. **Fires early** by a configurable offset (e.g. 100–200ms) so the request *arrives* at the server closer to T-0
5. **Two-step mode:** fires a pre-commit request first to create the server-side resource blocker, extracts fresh UUIDs from the response, injects them into the commit body, then fires the commit immediately after
6. **Auto-syncs XSRF tokens** — ensures the double-submit CSRF cookie and header match before firing
7. **Retries** immediately if the first attempt fails
8. **Logs** every response in full to `~/.siteswiper/logs/` for post-mortem debugging

---

## Quick Start

### Prerequisites

- Python 3.10 or later
- Visual Studio Code (free — download from https://code.visualstudio.com)
- An Ontario Parks account: https://reservations.ontarioparks.ca

### Install

Clone the SiteSwiper repository (paste the GitHub link into VS Code's "Clone Repository" prompt, or use the terminal), then paste this into the terminal:

```
pip install -r requirements.txt
```

> **Playwright / Chromium:** SiteSwiper uses a built-in browser to capture session data automatically. The first time you run the tool it will install the Playwright package and download the Chromium browser (~170 MB) automatically — no extra steps needed.

### Run

```
python run.py
```

---

## Workflow Overview

SiteSwiper has **two phases**: setup (done in advance) and morning-of (done before 7:00 AM. Start at 6:30am to minimize stress).

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SETUP PHASE                         MORNING-OF          LAUNCH
  (days/weeks before booking day)     (10–15 min          (7:00 AM)
                                       before 7 AM)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────────┐         ┌───────────────┐   ┌─────────────────┐
  │ 1. Capture new request  │         │               │   │                 │
  │    (any available site) │──save──▶│ 2. Morning-of │   │ 3. Schedule &   │
  │                         │         │    Flow       │──▶│    fire         │
  │    OR                   │         │               │   │                 │
  │                         │         │  ✓ Fresh UUIDs│   │  T-10s: prewarm │
  │    Use preset template  │         │  ✓ Session    │   │  T-2s:  spinwait│
  │    (built-in starting   │         │    captured   │   │  T-0:   fire! 🎯│
  │     point)              │         │    auto or    │   │                 │
  │                         │         │    manually   │   └────────┬────────┘
  │    Create from template │         │  ✓ Pre-commit │            │
  │    (set your target     │         │    attached   │            │
  │     site & dates)       │         │               │            │
  └─────────────────────────┘         └───────────────┘            │
                                                                    ▼
                                                         4. Complete checkout
                                                            in browser
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Phase 1 — Setup (do this in advance)

### Step 1A — Get a starting request

> **Goal:** Give SiteSwiper a booking request in the exact format Ontario Parks expects. There are three ways — pick whichever is easiest.

#### Option A — Use the built-in preset template (easiest, recommended for new users)

Run SiteSwiper and choose **`1 — Use preset template`**. SiteSwiper loads a pre-built request skeleton, walks you through editing the booking fields (dates, site ID, park ID), then saves it. You still need to refresh your session cookies in the Morning-of Flow, but you skip the manual browser capture at this stage.

#### Option B — Capture from your browser manually

Run SiteSwiper and choose **`0 — Capture new request`**, then:

1. Log in to https://reservations.ontarioparks.ca
2. Navigate to **any available campsite** and select some dates — mid-week sites in May work well
3. Get to the page where the **"Reserve"** button is visible — **don't click it yet**
4. Open Developer Tools (`F12`) → **Network** tab → enable **"Preserve log"** → filter to **Fetch/XHR**
5. In the filter box, type `Method:POST` to show only POST requests; clear the log right before clicking Reserve to make it easier to find
6. Click **Reserve**
7. Find the first POST request with **"commit"** in the URL — it will be 3–5 KB in size
8. Right-click it → **"Copy as cURL (bash)"** (Chrome/Edge) or **"Copy Value > Copy as cURL"** (Firefox)
9. Paste the cURL into SiteSwiper

### Step 1B — Create from template (set your target site and dates)

> **Goal:** Replace the placeholder site/dates from Step 1A with your actual target campsite.

Run SiteSwiper and choose **`1 — Create from template`**:

1. Select your saved template request
2. Choose **"Edit booking fields"** — SiteSwiper extracts the 4 key fields and lets you edit them:

   | Field | What it is | Example |
   |-------|-----------|---------|
   | `startDate` | Arrival date | `2026-07-15` |
   | `endDate` | Departure date | `2026-07-17` |
   | `resourceId` | Campsite number (site ID) | `-2147475036` |
   | `resourceLocationId` | Park ID | `-2147483600` |

   Changes are written to **all 7 nested locations** in the JSON body automatically. SiteSwiper also offers to update the `Referer` header to match.

3. Save as a new request (e.g. `algonquin-site-042`)

> **How to find your target site's IDs:** Browse to the site on Ontario Parks and check the URL — it contains `resourceId` and `resourceLocationId` as URL parameters. The park ID (`resourceLocationId`) is the same for all sites in the same park. Find these ahead of time and save them somewhere — they don't change.
> **Some Sites are Pre-loaded** As examples, some campsites at Granite Saddle are preloaded to make it easier

> **Why "Edit booking fields" and not "Edit body parameters"?** The POST body is a deeply nested ~5 KB JSON blob where dates and site IDs appear in multiple locations that must stay in sync. "Edit booking fields" understands the Ontario Parks structure and handles all 7 nested paths for you.

---

## Phase 2 — Morning-of Flow (10–15 min before 7:00 AM)

> **Goal:** Refresh your session, regenerate IDs, and attach the pre-commit step — all in one pass.

Run SiteSwiper and choose **`3 — Morning-of Flow`**:

```
  Morning-of Flow does three things automatically:

  Step 1/3 ── Regenerates session UUIDs in your saved request
               (cartUid, bookingUid, resourceBlockerUid, cartTransactionUid)

  Step 2/3 ── Captures a fresh session from any available site
               (automated browser or manual paste — your choice)
               ↳ Refreshes session cookies on your request
               ↳ Syncs the X-XSRF-TOKEN header with the new XSRF-TOKEN cookie
               ↳ Syncs your personal info (name, phone, address) into the commit body

  Step 3/3 ── Attaches the captured request as the pre-commit step
               ↳ Booking fields (site/dates) auto-synced to your original commit request
```

### Step 2/3 — Capture options

When prompted, SiteSwiper asks how you want to capture the session:

#### Option A — Automated (recommended)

Choose **`0 — Automated — open a browser window`**. SiteSwiper:

1. Opens a Chromium browser window on the Ontario Parks site
2. Displays an overlay in the top-left corner with step-by-step instructions
3. You navigate to **any available campsite** and stop before clicking Reserve
4. Click the **"I'm ready"** button in the overlay
5. Click **Reserve** on the Ontario Parks page
6. SiteSwiper automatically captures the network request — the overlay confirms success
7. Leave the browser window open or close it; the terminal continues automatically

#### Option B — Manual (paste cURL)

Choose **`1 — Manual — paste a cURL command`**, then:

1. Go to https://reservations.ontarioparks.ca in your browser (stay logged in)
2. Open DevTools (`F12`) → **Network** tab → **Preserve log** → filter **Fetch/XHR** → clear the log
3. Find **any currently available campsite** (doesn't need to be your target)
4. Click the booking button on that site to trigger the checkout flow
5. In the Network tab, find the **first POST** that fired (URL like `/api/cart/add`)
6. Verify its response contains `cartUid`, `bookings`, `resourceBlockers`
7. Right-click → **Copy as cURL (bash)** → paste into SiteSwiper

> **Why any available site works:** Cookies are session-wide, not site-specific. SiteSwiper automatically overwrites the site/dates in the pre-commit body with the values from your commit request. You're just using the available site to get a fresh request format and valid cookies.

> **Timing matters:** Session cookies expire. Run the Morning-of Flow **10-20 minutes before 7:00 AM** — close enough that the cookies are still valid when you fire.

---

## Phase 3 — Launch (at 7:00 AM)

### Step 3 — Schedule and fire 🎯

Run SiteSwiper and choose **`4 — Schedule and fire`**:

1. Select your prepared request
2. Confirm target time (defaults to next 7:00 AM EST)
3. Set max retries (default: 5)
4. Set **pre-fire offset** in milliseconds — see [Pre-fire offset](#pre-fire-offset)
5. SiteSwiper syncs with NTP and starts the countdown:

```
  T-10s  ── Connection pre-warmed (TCP + TLS handshake)
  T-2s   ── Precision spin-wait engages (sub-millisecond accuracy)
  T-0    ── Pre-commit fires → UUIDs extracted → Commit fires 🎯
           ↳ Up to 5 rapid retries on failure
```

6. Full response logs saved to `~/.siteswiper/logs/<timestamp>/attempt_N.json`

### Step 4 — Complete checkout

After a successful booking, open your browser and complete the checkout process on Ontario Parks to finalize the reservation. You may see an **"Acknowledge"** popup — click through it.

---

## Main Menu

```
  0 — Capture new request      Capture a cURL from your browser (first-time setup)
  1 — Use preset template      Start from a built-in request skeleton (no browser capture needed)
  2 — Create from template     Set your target site/dates on a saved template
  3 — Morning-of Flow          Refresh UUIDs, cookies, and pre-commit in one pass ← booking day
  4 — Schedule and fire        Countdown + fire at 7:00 AM
  ─────────────────────────────────────────────────────────────────────────────
  5 — List saved requests      View and delete saved requests
  6 — Measure server latency   25 probes over 5 min → recommended pre-fire offset
  7 — Tools                    Individual utilities (see below)
  8 — Exit
```

### Tools submenu

```
  0 — Refresh cookies          Apply fresh session cookies from a new cURL
  1 — Set up pre-commit        Attach a pre-commit step to a saved request
  2 — Dry run                  Test the countdown without sending a request
  3 — Check clock sync         Show NTP offset and clock accuracy
  4 — Back
```

---

## Technical Details

### Two-step booking

Ontario Parks `/api/cart/commit` validates the submitted cart body against a **server-side resource blocker record**. That record is created when you click "Reserve" and a pre-commit request fires (e.g., POST to `/api/cart/resourceblocker`). The commit body must contain `cartUid`, `bookingUid`, and `resourceBlockerUid` values matching the server-side record — stale or randomly generated UUIDs are rejected with HTTP 400 ("Invalid Blocker" or "ResourceUnavailable").

SiteSwiper solves this with **two-step execution** at T-0:

```
  1. Pre-commit fires (no retries — creates the server-side cart + resource blocker)
  2. SiteSwiper extracts 4 fresh UUIDs from the response
  3. UUIDs are injected into the commit body at all nested paths
  4. Commit fires immediately, referencing the freshly created server-side cart
```

If the pre-commit fails or UUID extraction fails, the commit is skipped and the error is reported. Both steps are logged separately.

### XSRF token sync

Ontario Parks uses the double-submit CSRF pattern: the `XSRF-TOKEN` cookie value must exactly match the `X-XSRF-TOKEN` request header. SiteSwiper syncs these automatically before firing and after each retry (the server rotates the token on every response).

### Timing precision

| Phase | Method | Accuracy |
|-------|--------|---------|
| T > 2s | `time.sleep()` in short intervals | Low CPU, ~50ms |
| T ≤ 2s | Busy spin on `time.perf_counter()` | Sub-millisecond |
| Clock | NTP median offset (Google, NIST, pool.ntp.org) | ±50ms typical |

### Connection pre-warming

At T-10s, SiteSwiper sends a HEAD request to Ontario Parks to establish the TCP handshake and TLS session. The booking request at T-0 then only needs to transmit the HTTP payload — saving 100–300ms.

### Pre-fire offset

Even with a pre-warmed connection, your request still takes time to travel to Ontario Parks' server. The pre-fire offset fires the request slightly *before* T-0 so it *arrives* at the server closer to the exact release moment.

**How to calibrate:**

When the server returns a timestamp in its response (which the commit endpoint does), SiteSwiper shows the **server delta** — the gap between when you fired and when the server processed the request. That's your ideal offset.

1. Run a test attempt on a non-release day
2. Check the results table — the **Server T+** column shows the delta directly
3. Set the pre-fire offset to that value

> A starting assumption of **25–50ms** is reasonable. Ontario Parks latency is typically 25–200ms. Don't fire too early — you can't take it back.

Use **`5 — Measure server latency`** to run 25 probes over 5 minutes and get a percentile-based recommendation.

### Response logs

After every run, SiteSwiper saves the full response for each attempt:

```
~/.siteswiper/logs/<timestamp>/attempt_N.json
```

Each file contains: request method/URL, response status, all headers, full response body, elapsed time, and whether the attempt succeeded. Primary tool for diagnosing failures.

### Session cookie warning

If you load a request saved more than 4 hours ago, SiteSwiper warns you. Ontario Parks sessions expire — stale cookies cause immediate authentication failures.

---

## Files

```
SiteSwiper/
├── siteswiper/
│   ├── cli.py              — Main menu and workflow orchestration
│   ├── curl_parser.py      — cURL parser (Chrome & Firefox formats)
│   ├── display.py          — Rich-based terminal UI
│   ├── executor.py         — HTTP firing with retries and XSRF sync
│   ├── storage.py          — Save/load requests as JSON
│   ├── time_sync.py        — NTP sync + precision countdown
│   ├── browser_capture.py  — Playwright browser automation for automated cURL capture
│   └── config.py           — Configurable constants
├── run.py              — Entry point
└── requirements.txt
```

## Configuration

Edit `siteswiper/config.py` to adjust:

| Setting | Default | Description |
|---------|---------|-------------|
| `DEFAULT_FIRE_HOUR` | `7` | Hour to fire (24h, local timezone) |
| `TIMEZONE` | `America/Toronto` | Timezone for default fire time |
| `DEFAULT_MAX_RETRIES` | `5` | Rapid-fire retry attempts |
| `DEFAULT_PREFIRE_OFFSET_MS` | `0` | ms to fire before T-0; calibrate using server delta |
| `PREWARM_SECONDS_BEFORE` | `10` | Seconds before T-0 to pre-warm connection |
| `SPIN_WAIT_THRESHOLD_SECONDS` | `2` | Switch from sleep to spin-wait N seconds before T-0 |
| `COOKIE_FRESHNESS_WARNING_HOURS` | `4` | Warn if saved request is older than this |
| `LOG_DIR` | `~/.siteswiper/logs` | Directory for full response logs |
