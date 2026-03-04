"""NTP time synchronization and precision countdown scheduling."""

import statistics
import time
from datetime import datetime, timezone

import ntplib

from siteswiper.config import NTP_SERVERS, SPIN_WAIT_THRESHOLD_SECONDS, SLEEP_INTERVAL_SECONDS


class TimeSynchronizer:
    """Handles NTP time synchronization and precision waiting.

    Uses NTP to measure the offset between the local clock and true time,
    then uses perf_counter for monotonic timing during the countdown.
    """

    def __init__(self):
        self.ntp_offset: float = 0.0  # seconds (positive = local clock ahead)
        self.sync_wall_time: float = 0.0  # time.time() at sync
        self.sync_perf_time: float = 0.0  # time.perf_counter() at sync
        self.synced: bool = False
        self.offsets: list[float] = []

    def sync(self) -> float:
        """Query NTP servers and calculate clock offset.

        Returns:
            Offset in seconds (positive = local clock is ahead of true time).

        Raises:
            RuntimeError: If no NTP servers could be reached.
        """
        client = ntplib.NTPClient()
        self.offsets = []

        for server in NTP_SERVERS:
            try:
                response = client.request(server, version=3, timeout=3)
                self.offsets.append(response.offset)
            except Exception:
                continue

        if not self.offsets:
            raise RuntimeError(
                "Could not reach any NTP servers. Check your internet connection.\n"
                f"Servers tried: {', '.join(NTP_SERVERS)}"
            )

        # Use median to avoid outlier influence
        self.ntp_offset = statistics.median(self.offsets)

        # Record reference points for monotonic timing
        self.sync_wall_time = time.time()
        self.sync_perf_time = time.perf_counter()
        self.synced = True

        return self.ntp_offset

    def get_true_time(self) -> float:
        """Get the NTP-corrected current time as a Unix timestamp.

        Uses perf_counter elapsed since sync for monotonic accuracy.
        Formula: true_time = sync_wall_time + ntp_offset + (perf_now - sync_perf)
        """
        if not self.synced:
            # Fall back to uncorrected time
            return time.time()

        elapsed = time.perf_counter() - self.sync_perf_time
        return self.sync_wall_time + self.ntp_offset + elapsed

    def get_true_datetime(self) -> datetime:
        """Get the NTP-corrected current time as a datetime object."""
        return datetime.fromtimestamp(self.get_true_time(), tz=timezone.utc)

    def seconds_until(self, target: datetime) -> float:
        """Calculate NTP-corrected seconds until the target time.

        Args:
            target: Target datetime (must be timezone-aware).

        Returns:
            Seconds remaining (negative if target has passed).
        """
        target_ts = target.timestamp()
        return target_ts - self.get_true_time()

    @property
    def offset_ms(self) -> float:
        """Get the NTP offset in milliseconds."""
        return self.ntp_offset * 1000

    @property
    def servers_reached(self) -> int:
        """Number of NTP servers successfully queried."""
        return len(self.offsets)

    def wait_until(self, target: datetime, on_tick=None,
                   prefire_offset_s: float = 0.0) -> None:
        """Wait until the target time with high precision.

        Strategy:
          - Until T-2s: sleep in intervals (low CPU), calling on_tick for UI updates
          - T-2s to T-0: tight spin-wait on perf_counter (sub-ms precision)

        Args:
            target: Target datetime (must be timezone-aware).
            on_tick: Optional callback(remaining_seconds) called during sleep phase.
            prefire_offset_s: Fire this many seconds early to compensate for network
                              latency (e.g., 0.1 = fire 100ms before target).
        """
        target_ts = target.timestamp() - prefire_offset_s

        # Phase 1: Sleep-based countdown (low CPU)
        while True:
            remaining = target_ts - self.get_true_time()

            if remaining <= SPIN_WAIT_THRESHOLD_SECONDS:
                break

            if on_tick:
                on_tick(remaining + prefire_offset_s)  # report true remaining to UI

            # Sleep for shorter intervals as we get closer
            if remaining > 60:
                time.sleep(SLEEP_INTERVAL_SECONDS)
            elif remaining > 10:
                time.sleep(0.25)
            else:
                time.sleep(0.05)

        # Phase 2: Spin-wait for sub-millisecond precision
        # Calculate the perf_counter target
        remaining = target_ts - self.get_true_time()
        spin_target = time.perf_counter() + remaining

        while time.perf_counter() < spin_target:
            pass  # Tight spin-wait

    def wait_until_with_prewarm(self, target: datetime, prewarm_callback=None,
                                 prewarm_seconds: float = 10.0, on_tick=None,
                                 prefire_offset_s: float = 0.0) -> None:
        """Wait until target, calling prewarm_callback at T-prewarm_seconds.

        Args:
            target: Target datetime.
            prewarm_callback: Called once at T-prewarm_seconds (e.g., to open TCP connection).
            prewarm_seconds: How many seconds before target to call prewarm.
            on_tick: Called periodically with remaining seconds.
            prefire_offset_s: Fire this many seconds early to compensate for network
                              latency (e.g., 0.1 = fire 100ms before target).
        """
        target_ts = target.timestamp() - prefire_offset_s
        prewarmed = False

        # Phase 1: Sleep-based countdown with prewarm check
        while True:
            remaining = target_ts - self.get_true_time()

            if remaining <= SPIN_WAIT_THRESHOLD_SECONDS:
                break

            # Prewarm check (relative to offset-adjusted target)
            if not prewarmed and prewarm_callback and remaining <= prewarm_seconds:
                prewarm_callback()
                prewarmed = True

            if on_tick:
                on_tick(remaining + prefire_offset_s)  # report true remaining to UI

            if remaining > 60:
                time.sleep(SLEEP_INTERVAL_SECONDS)
            elif remaining > 10:
                time.sleep(0.25)
            else:
                time.sleep(0.05)

        # Phase 2: Spin-wait
        remaining = target_ts - self.get_true_time()
        spin_target = time.perf_counter() + remaining

        while time.perf_counter() < spin_target:
            pass
