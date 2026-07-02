"""Event-driven CAN reception via python-can.

A `can.Notifier` runs a background thread that delivers every incoming
frame to `_J1939Listener`. The listener filters extended-identifier
frames, extracts the PGN, decodes the payload through the decode table
and hands the result to the consumer callback.

The callback is invoked on the notifier thread; GUI consumers must
marshal updates back onto their main loop themselves.
"""
from __future__ import annotations

import logging
from typing import Callable

import can

from .decoder import DecodedSignal, decode_frame
from .exceptions import BusError
from .protocol import extract_pgn

logger = logging.getLogger(__name__)

UpdateCallback = Callable[[dict[str, DecodedSignal]], None]


class _J1939Listener(can.Listener):
    """Filters, decodes and forwards incoming J1939 frames."""

    def __init__(self, on_update: UpdateCallback, is_enabled: Callable[[], bool]) -> None:
        self._on_update = on_update
        self._is_enabled = is_enabled

    def on_message_received(self, msg: can.Message) -> None:
        if not msg.is_extended_id or not self._is_enabled():
            return
        pgn = extract_pgn(msg.arbitration_id)
        updates = decode_frame(pgn, msg.data)
        if not updates:
            return
        logger.debug(
            "RX PGN=0x%04X ID=0x%08X data=%s",
            pgn,
            msg.arbitration_id,
            msg.data.hex().upper(),
        )
        try:
            self._on_update(updates)
        except Exception:
            logger.exception("Error in update callback")

    def on_error(self, exc: Exception) -> None:
        logger.error("CAN receive error: %s", exc)


class CanReceiver:
    """Lifecycle wrapper around `can.Bus` + `can.Notifier`.

    Usage:

        receiver = CanReceiver("socketcan", "can0", on_update=handle)
        receiver.start()
        ...
        receiver.stop()

    `set_enabled(False)` pauses decoding without tearing down the bus.
    """

    def __init__(
        self,
        interface: str,
        channel: str | int,
        on_update: UpdateCallback,
        **bus_kwargs,
    ) -> None:
        self.interface = interface
        self.channel = channel
        self._on_update = on_update
        self._bus_kwargs = bus_kwargs
        self._bus: can.BusABC | None = None
        self._notifier: can.Notifier | None = None
        self._enabled = True

    @property
    def is_running(self) -> bool:
        return self._notifier is not None

    def set_enabled(self, enabled: bool) -> None:
        """Pause or resume frame decoding while keeping the bus open."""
        self._enabled = enabled

    def start(self) -> None:
        """Open the bus and start the notifier thread."""
        if self._notifier is not None:
            raise BusError("Receiver is already running")

        logger.info(
            "Opening CAN bus: interface=%s channel=%s",
            self.interface,
            self.channel,
        )
        try:
            self._bus = can.Bus(
                interface=self.interface,
                channel=self.channel,
                **self._bus_kwargs,
            )
        except Exception as exc:
            raise BusError(f"Failed to open CAN bus: {exc}") from exc

        listener = _J1939Listener(self._on_update, lambda: self._enabled)
        self._notifier = can.Notifier(self._bus, [listener])
        logger.info("Receiver started")

    def stop(self) -> None:
        """Stop the notifier and close the bus. Idempotent."""
        if self._notifier is not None:
            self._notifier.stop()
            self._notifier = None
        if self._bus is not None:
            self._bus.shutdown()
            self._bus = None
            logger.info("Receiver stopped, CAN bus closed")

    def __enter__(self) -> "CanReceiver":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
