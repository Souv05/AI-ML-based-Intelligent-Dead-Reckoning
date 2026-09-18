#!/usr/bin/env python3
"""
Server Keep-Alive Script
-------------------------
Periodically sends ping requests to the server endpoint (e.g. Render, Railway, Heroku)
to keep it alive and prevent automatic sleeping/inactivity spindown (every 5-10 minutes).

Usage:
    # Run continuously with 5-10 min random interval:
    python keep_alive.py --url https://your-app.onrender.com/health

    # Run using environment variable:
    export SERVER_URL="https://your-app.onrender.com/health"
    python keep_alive.py

    # Run once (ideal for Cron / GitHub Actions):
    python keep_alive.py --url https://your-app.onrender.com/health --once

    # Custom interval (e.g. fixed 5 minutes):
    python keep_alive.py --url https://your-app.onrender.com/health --interval 300
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = os.environ.get(
    "SERVER_URL",
    os.environ.get("HEALTH_CHECK_URL", "http://localhost:8000/health"),
)
DEFAULT_MIN_INTERVAL = 300  # 5 minutes in seconds
DEFAULT_MAX_INTERVAL = 600  # 10 minutes in seconds
DEFAULT_TIMEOUT = 15        # Timeout in seconds


def ping(url: str, timeout: float = DEFAULT_TIMEOUT) -> tuple[bool, int, float, str]:
    """Send an HTTP GET request to the specified URL.

    Returns:
        (success: bool, status_code: int, latency_seconds: float, message: str)
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KeepAlive-Pinger/1.0 (+https://github.com)",
            "Accept": "*/*",
        },
    )
    start_time = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            latency = time.monotonic() - start_time
            return True, response.status, latency, "OK"
    except urllib.error.HTTPError as e:
        latency = time.monotonic() - start_time
        return False, e.code, latency, f"HTTP Error: {e.reason}"
    except urllib.error.URLError as e:
        latency = time.monotonic() - start_time
        return False, 0, latency, f"URL Error: {e.reason}"
    except Exception as e:
        latency = time.monotonic() - start_time
        return False, 0, latency, f"Error: {e}"


def run_keep_alive(
    url: str,
    min_interval: int,
    max_interval: int,
    timeout: float,
    once: bool = False,
) -> None:
    """Main keep-alive loop."""
    # Ensure stdout/stderr handle unicode safely on Windows legacy encodings
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass

    print("=" * 60)
    print("[INFO] Server Keep-Alive Service Started")
    print(f"Target URL:    {url}")
    print(f"Mode:          {'Single ping (--once)' if once else 'Continuous loop'}")
    if not once:
        if min_interval == max_interval:
            print(f"Interval:      {min_interval}s ({min_interval / 60:.1f} min)")
        else:
            print(
                f"Interval:      {min_interval}s - {max_interval}s "
                f"({min_interval / 60:.1f} - {max_interval / 60:.1f} min random jitter)"
            )
    print(f"Timeout:       {timeout}s")
    print("=" * 60)

    total_pings = 0
    successful_pings = 0

    try:
        while True:
            total_pings += 1
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            print(f"\n[{now_str}] Ping #{total_pings} -> {url} ...", end=" ", flush=True)
            success, code, latency, msg = ping(url, timeout=timeout)

            if success:
                successful_pings += 1
                print(f"[SUCCESS] Code: {code} | Latency: {latency:.3f}s")
            else:
                print(f"[FAILED] Code: {code} | Latency: {latency:.3f}s | {msg}")

            if once:
                print(f"\nCompleted single ping check. Exit code: {0 if success else 1}")
                sys.exit(0 if success else 1)

            # Calculate next sleep duration
            if min_interval == max_interval:
                sleep_seconds = min_interval
            else:
                sleep_seconds = random.randint(min_interval, max_interval)

            next_run = datetime.fromtimestamp(
                time.time() + sleep_seconds, tz=timezone.utc
            ).strftime("%H:%M:%S UTC")

            print(
                f"[STATS] {successful_pings}/{total_pings} successful | "
                f"Next ping in {sleep_seconds}s ({sleep_seconds / 60:.1f} min) at ~{next_run}"
            )

            time.sleep(sleep_seconds)

    except KeyboardInterrupt:
        print("\n\n[STOPPED] Keep-alive script stopped by user (Ctrl+C). Exiting.")
        sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Periodically ping a web server endpoint to keep it awake."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_URL,
        help=f"Target URL to ping (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Fixed interval in seconds (overrides --min-interval and --max-interval)",
    )
    parser.add_argument(
        "--min-interval",
        type=int,
        default=DEFAULT_MIN_INTERVAL,
        help=f"Minimum sleep interval in seconds (default: {DEFAULT_MIN_INTERVAL}s / 5m)",
    )
    parser.add_argument(
        "--max-interval",
        type=int,
        default=DEFAULT_MAX_INTERVAL,
        help=f"Maximum sleep interval in seconds (default: {DEFAULT_MAX_INTERVAL}s / 10m)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT}s)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ping once and exit (useful for cron jobs or CI/CD pipelines)",
    )

    args = parser.parse_args()

    min_int = args.interval if args.interval is not None else args.min_interval
    max_int = args.interval if args.interval is not None else args.max_interval

    if min_int > max_int:
        parser.error("--min-interval cannot be greater than --max-interval")

    run_keep_alive(
        url=args.url,
        min_interval=min_int,
        max_interval=max_int,
        timeout=args.timeout,
        once=args.once,
    )


if __name__ == "__main__":
    main()
