"""
ARIS — Scheduler
Runs the full pipeline on a recurring interval.
"""

from __future__ import annotations

import time
import signal
import threading
from typing import Optional

import schedule
from rich.console import Console

from agents.orchestrator import Orchestrator
from utils.cache import get_logger

log     = get_logger("aris.scheduler")
console = Console()

_stop_event = threading.Event()


def _handle_signal(sig, frame):
    console.print("\n[yellow]Shutdown signal received — stopping scheduler.[/yellow]")
    _stop_event.set()


def run_watch(interval_hours: int = 24, lookback_days: int = 7):
    """
    Run the full ARIS pipeline every `interval_hours` hours.
    Runs once immediately on startup, then on schedule.
    Graceful shutdown on SIGINT (Ctrl+C) or SIGTERM.
    """
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    orchestrator = Orchestrator()

    def job():
        console.rule("[bold blue]ARIS Scheduled Run[/bold blue]")
        log.info("Starting scheduled pipeline run…")
        result = orchestrator.run_full(lookback_days=lookback_days)
        log.info("Scheduled run complete: %s", result)

    # Run immediately, then schedule
    job()
    schedule.every(interval_hours).hours.do(job)

    console.print(
        f"[dim]Scheduler active — next run in {interval_hours}h. "
        f"Press Ctrl+C to stop.[/dim]"
    )

    while not _stop_event.is_set():
        schedule.run_pending()
        time.sleep(30)   # check every 30 seconds

    console.print("[dim]Scheduler stopped.[/dim]")
