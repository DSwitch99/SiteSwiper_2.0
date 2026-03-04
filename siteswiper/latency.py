"""One-way latency probing for the Ontario Parks reservation server."""

import time

import httpx

PROBE_HOST = "reservations.ontarioparks.ca"
PROBE_URL = f"https://{PROBE_HOST}/"
PROBE_COUNT = 25
PROBE_INTERVAL_S = 12.0   # 25 probes × 12 s ≈ 5 min
PROBE_TIMEOUT_S = 10.0


def probe_once(client: httpx.Client) -> float | None:
    """Fire one HEAD request; return round-trip time in ms, or None on failure."""
    try:
        t0 = time.perf_counter()
        client.head(PROBE_URL, follow_redirects=True)
        return (time.perf_counter() - t0) * 1000.0
    except Exception:
        return None


def one_way_ms(rtt_ms: float) -> float:
    """Estimate one-way latency as RTT / 2."""
    return rtt_ms / 2.0


def calc_percentile(values: list[float], p: float) -> float:
    """Return the p-th percentile (0–100) of *values* using linear interpolation."""
    if not values:
        raise ValueError("Cannot compute percentile of an empty list")
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac
