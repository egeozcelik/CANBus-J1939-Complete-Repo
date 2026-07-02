"""J1939 broadcast scheduler engine.

Supports an individual broadcast period (ms) per PGN. A single tick
function broadcasts every PGN that is due; the UI side calls this tick
at regular intervals via GLib.timeout_add.

Design notes:
  - The engine knows nothing about hardware; it sends through CanTransport.
  - The engine uses `model.as_signal_map()` as its signal source.
  - When several signals belong to one PGN, they are all packed into a
    single 8-byte frame (J1939-21 multi-signal frame composition).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

import can

from .database import (
    PGN_DATABASE,
    PgnDefinition,
    SIGNAL_DATABASE,
    signals_for_pgn,
)
from .protocol import J1939Id, NULL_BYTE
from .transport import CanTransport

logger = logging.getLogger(__name__)


FrameListener = Callable[["BroadcastEvent"], None]


@dataclass
class BroadcastEvent:
    """Observer data for a broadcast PGN."""

    timestamp: float
    pgn_definition: PgnDefinition
    can_id: int
    data: bytes
    success: bool
    signal_values: Mapping[str, float] = field(default_factory=dict)


@dataclass
class _ScheduledPgn:
    pgn_def: PgnDefinition
    period_s: float
    next_due: float


class SimulationEngine:
    """Periodic J1939 broadcast scheduler.

    Usage:

        engine = SimulationEngine(transport, model, source_address=0x01)
        engine.start()
        engine.tick()
        engine.stop()
    """

    def __init__(
        self,
        transport: CanTransport,
        signal_provider: Callable[[], Mapping[str, float]],
        source_address: int | None = None,
        listener: FrameListener | None = None,
    ) -> None:
        """Initialize the engine.

        Args:
            transport: A connected CanTransport instance.
            signal_provider: Function providing a physical-value mapping,
                typically `VehicleModel.as_signal_map`.
            source_address: Global SA override for all PGNs. When None,
                each PGN uses its own SA.
            listener: Optional callback invoked after every broadcast.
        """
        self.transport = transport
        self.signal_provider = signal_provider
        self.source_address_override = source_address
        self.listener = listener
        self._schedule: list[_ScheduledPgn] = []
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            logger.warning("Engine is already running")
            return

        self._schedule = []
        now = time.monotonic()
        for pgn_def in PGN_DATABASE.values():
            if pgn_def.transmission_rate_ms <= 0:
                continue
            self._schedule.append(
                _ScheduledPgn(
                    pgn_def=pgn_def,
                    period_s=pgn_def.transmission_rate_ms / 1000.0,
                    next_due=now,
                )
            )
        self._running = True
        logger.info("Engine started, %d PGNs scheduled", len(self._schedule))

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._schedule = []
        logger.info("Engine stopped")

    def tick(self) -> int:
        """Broadcast every PGN that is due. Returns the number sent."""
        if not self._running:
            return 0

        now = time.monotonic()
        sent_count = 0
        signal_values = self.signal_provider()

        for scheduled in self._schedule:
            if now < scheduled.next_due:
                continue
            self._broadcast_pgn(scheduled.pgn_def, signal_values)
            scheduled.next_due += scheduled.period_s
            if scheduled.next_due < now:
                scheduled.next_due = now + scheduled.period_s
            sent_count += 1

        return sent_count

    def broadcast_now(self, pgn: int) -> bool:
        """Broadcast a specific PGN once, immediately (request-style)."""
        if pgn not in PGN_DATABASE:
            raise KeyError(f"Unknown PGN: 0x{pgn:04X}")
        return self._broadcast_pgn(PGN_DATABASE[pgn], self.signal_provider())

    def _broadcast_pgn(
        self,
        pgn_def: PgnDefinition,
        signal_values: Mapping[str, float],
    ) -> bool:
        frame = bytearray([NULL_BYTE] * 8)
        used_signals: dict[str, float] = {}

        for key, signal in SIGNAL_DATABASE.items():
            if signal.pgn != pgn_def.pgn:
                continue
            if key not in signal_values:
                continue
            value = signal_values[key]
            signal.write_to_frame(frame, value)
            used_signals[key] = value

        sa = (
            self.source_address_override
            if self.source_address_override is not None
            else pgn_def.source_address
        )
        j1939_id = J1939Id.from_pgn(
            pgn_def.pgn,
            source_address=sa,
            priority=pgn_def.priority,
            destination=pgn_def.destination_address,
        )
        can_id = j1939_id.to_can_id()

        message = can.Message(
            arbitration_id=can_id,
            is_extended_id=True,
            dlc=8,
            data=bytes(frame),
        )

        success = self.transport.send(message)

        logger.debug(
            "TX PGN=0x%04X (%s) ID=0x%08X data=%s success=%s",
            pgn_def.pgn,
            pgn_def.name,
            can_id,
            frame.hex().upper(),
            success,
        )

        if self.listener is not None:
            event = BroadcastEvent(
                timestamp=time.time(),
                pgn_definition=pgn_def,
                can_id=can_id,
                data=bytes(frame),
                success=success,
                signal_values=used_signals,
            )
            try:
                self.listener(event)
            except Exception:
                logger.exception("Error in listener callback")

        return success
