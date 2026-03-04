"""Configuration constants for SiteSwiper."""

import os
from pathlib import Path

# NTP servers for time synchronization (queried in order, median offset used)
NTP_SERVERS = [
    "time.google.com",
    "pool.ntp.org",
    "time.nist.gov",
]

# Default booking time
DEFAULT_FIRE_HOUR = 7
DEFAULT_FIRE_MINUTE = 0
DEFAULT_FIRE_SECOND = 0

# Timezone for Ontario Parks
TIMEZONE = "America/Toronto"

# Precision timing thresholds
SPIN_WAIT_THRESHOLD_SECONDS = 2.0  # Switch to spin-wait this many seconds before T-0
SLEEP_INTERVAL_SECONDS = 0.5       # Sleep interval during countdown (before spin-wait)

# Retry settings
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_DELAY_MS = 100  # Milliseconds between retries

# Pre-fire offset: fire this many ms before the target time to compensate for network latency
DEFAULT_PREFIRE_OFFSET_MS = 0  # 0 = disabled; try 50-200ms based on your measured round-trip time

# Connection pre-warm timing
PREWARM_SECONDS_BEFORE = 10  # Pre-warm connection this many seconds before T-0

# Request storage
STORAGE_DIR = Path(os.path.expanduser("~/.siteswiper/requests"))

# Response logs
LOG_DIR = Path(os.path.expanduser("~/.siteswiper/logs"))

# Session cookie freshness warning (hours)
COOKIE_FRESHNESS_WARNING_HOURS = 4

# Request timeout
REQUEST_TIMEOUT_SECONDS = 30

# ---------------------------------------------------------------------------
# Campsite lookup table
# Each entry: (campsite_name, campsite_number, site_id)
# ---------------------------------------------------------------------------
CAMPSITES: list[tuple[str, int, int]] = [
    ("Granite Saddle", 1034, -2147475109),
    ("Granite Saddle", 1036, -2147474728),
    ("Granite Saddle", 1037, -2147474328),
    ("Granite Saddle", 1038, -2147474445),
    ("Granite Saddle", 1039, -2147475127),
    ("Granite Saddle", 1040, -2147474942),
    ("Granite Saddle", 1041, -2147474676),
    ("Granite Saddle", 1042, -2147474731),
    ("Granite Saddle", 1043, -2147474493),
    ("Granite Saddle", 1044, -2147474539),
    ("Granite Saddle", 1045, -2147474627),
    ("Granite Saddle", 1046, -2147474326),
    ("Granite Saddle", 1047, -2147474261),
    ("Granite Saddle", 1048, -2147474988),
]

# Reverse lookup: site_id -> (campsite_name, campsite_number)
CAMPSITE_BY_SITE_ID: dict[int, tuple[str, int]] = {
    site_id: (name, number) for name, number, site_id in CAMPSITES
}
