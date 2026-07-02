"""Hardware-agnostic CAN transport layer.

A thin facade over the `python-can` library. The hardware backend is
configured at runtime; the `virtual` interface can be used for tests.

Example interfaces:
    - "ixxat"       : Ixxat USB-to-CAN
    - "vector"      : Vector CANcase XL / VN series
    - "kvaser"      : Kvaser USBcan
    - "pcan"        : Peak-System PCAN-USB
    - "socketcan"   : Linux SocketCAN (vcan0, can0, ...)
    - "virtual"     : Loop-back (for tests)
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

import can

from .exceptions import TransportError

logger = logging.getLogger(__name__)


class CanTransport:
    """Synchronous facade for a CAN bus connection.

    Bundles retry, timeout handling and connection lifecycle behind a
    uniform API. The UI and the simulation engine use this class and
    never depend on hardware directly.

    Usage example:

        with CanTransport("virtual", "vcan0", 250_000) as tx:
            tx.send(message)
    """

    def __init__(
        self,
        interface: str,
        channel: str | int,
        bitrate: int = 250_000,
        send_timeout: float = 0.1,
        max_retries: int = 3,
        retry_backoff: float = 0.05,
        **bus_kwargs,
    ) -> None:
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self.send_timeout = send_timeout
        self.max_retries = max(1, max_retries)
        self.retry_backoff = retry_backoff
        self._bus_kwargs = bus_kwargs
        self._bus: can.BusABC | None = None

    @property
    def is_connected(self) -> bool:
        return self._bus is not None

    def connect(self) -> None:
        """Connect to the CAN bus. Not idempotent; raises if called twice."""
        if self._bus is not None:
            raise TransportError("CAN bus is already connected")

        logger.info(
            "Connecting to CAN bus: interface=%s channel=%s bitrate=%d",
            self.interface,
            self.channel,
            self.bitrate,
        )
        try:
            self._bus = can.Bus(
                interface=self.interface,
                channel=self.channel,
                bitrate=self.bitrate,
                **self._bus_kwargs,
            )
        except Exception as exc:
            raise TransportError(f"Failed to open CAN bus: {exc}") from exc

    def disconnect(self) -> None:
        """Close the connection. Idempotent."""
        if self._bus is None:
            return
        try:
            self._bus.shutdown()
        finally:
            self._bus = None
            logger.info("CAN bus connection closed")

    def send(self, message: can.Message) -> bool:
        """Send a message. Returns True on success.

        Retries with a light backoff when the transmit queue is full.
        """
        if self._bus is None:
            raise TransportError("connect() must be called before sending")

        for attempt in range(1, self.max_retries + 1):
            try:
                self._bus.send(message, timeout=self.send_timeout)
                return True
            except can.CanError as exc:
                lower = str(exc).lower()
                if "queue" in lower or "transmit" in lower:
                    logger.warning(
                        "Tx queue full (%d/%d): %s",
                        attempt,
                        self.max_retries,
                        exc,
                    )
                    time.sleep(self.retry_backoff * attempt)
                    continue
                logger.error(
                    "CAN send error (%d/%d): %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt == self.max_retries:
                    return False
        return False

    def __enter__(self) -> "CanTransport":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()


@contextmanager
def open_transport(
    interface: str,
    channel: str | int,
    bitrate: int = 250_000,
    **kwargs,
) -> Iterator[CanTransport]:
    """Context manager for short-lived usage."""
    transport = CanTransport(interface=interface, channel=channel, bitrate=bitrate, **kwargs)
    transport.connect()
    try:
        yield transport
    finally:
        transport.disconnect()
