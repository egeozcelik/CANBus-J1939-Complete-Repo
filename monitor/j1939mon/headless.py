"""Headless console renderer.

Runs the same receiver pipeline as the GUI but prints a snapshot of
the latest decoded values to the console once per second. Useful for
embedded targets without a display, quick bus checks and CI runs
against the companion simulator.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .decoder import DecodedSignal
from .receiver import CanReceiver

logger = logging.getLogger(__name__)


class HeadlessMonitor:
    """Collects decoded signals and prints periodic snapshots."""

    def __init__(self, receiver_factory: Callable[..., CanReceiver], interval_s: float = 1.0) -> None:
        self.receiver_factory = receiver_factory
        self.interval_s = interval_s
        self._latest: dict[str, DecodedSignal] = {}
        self._lock = threading.Lock()

    def _on_update(self, updates: dict[str, DecodedSignal]) -> None:
        with self._lock:
            self._latest.update(updates)

    def _print_snapshot(self) -> None:
        with self._lock:
            snapshot = dict(self._latest)
        if not snapshot:
            logger.info("No J1939 data received yet")
            return
        width = max(len(sig.name) for sig in snapshot.values())
        lines = [
            f"  {sig.name:<{width}}  {sig.text} {sig.unit}".rstrip()
            for sig in sorted(snapshot.values(), key=lambda s: s.name)
        ]
        print(f"--- J1939 snapshot ({time.strftime('%H:%M:%S')}) ---")
        print("\n".join(lines))

    def run(self) -> int:
        receiver = self.receiver_factory(on_update=self._on_update)
        receiver.start()
        logger.info("Headless mode active. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(self.interval_s)
                self._print_snapshot()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt, shutting down...")
        finally:
            receiver.stop()
        return 0
