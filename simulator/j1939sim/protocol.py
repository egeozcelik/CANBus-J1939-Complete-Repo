"""SAE J1939-21 protocol primitives.

This module is responsible for:
  - Decomposing the 29-bit extended CAN identifier into its J1939 fields
  - Composing the PGN correctly according to the PDU1/PDU2 formats
  - Encoding and decoding signals with scale, offset, bit start/length
  - Writing signals into the 8-byte CAN data buffer in little endian
    (Intel) byte order

The design is fully independent of hardware and UI, and is verified
by unit tests.

J1939 ID field layout (MSB to LSB):
  bit 28..26  -> Priority    (3 bits, default 6)
  bit 25      -> Reserved    (1 bit, must always be 0)
  bit 24      -> Data Page   (1 bit, 0 for J1939-71)
  bit 23..16  -> PDU Format  (PF, 8 bits)
  bit 15..8   -> PDU Specific (PS, 8 bits)
                  destination address when PF < 240
                  group extension when PF >= 240
  bit 7..0    -> Source Address (SA, 8 bits)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Final

from .exceptions import ProtocolError


class Priority(IntEnum):
    """J1939 priority values (3 bits).

    A lower numeric value means higher priority; per the CAN bus
    arbitration rule, 0 propagates fastest.
    """

    HIGHEST = 0
    CRITICAL = 2
    HIGH = 3
    NORMAL = 6
    LOWEST = 7


PDU2_THRESHOLD: Final[int] = 240
"""PF >= 240 -> PDU2 (broadcast, PS = group extension)."""

GLOBAL_DESTINATION: Final[int] = 0xFF
"""The 'global' address representing a broadcast for PDU1 messages."""

NULL_BYTE: Final[int] = 0xFF
"""Fill value for unused/unassigned bytes in J1939."""


@dataclass(frozen=True)
class J1939Id:
    """A 29-bit CAN identifier conforming to the J1939 standard.

    Fields are not computed directly from a PGN; instead a factory
    method (`from_pgn`) splits the PGN into its parts correctly.
    """

    priority: int
    data_page: int
    pdu_format: int
    pdu_specific: int
    source_address: int
    reserved: int = 0

    def __post_init__(self) -> None:
        for name, value, max_value in (
            ("priority", self.priority, 7),
            ("reserved", self.reserved, 1),
            ("data_page", self.data_page, 1),
            ("pdu_format", self.pdu_format, 0xFF),
            ("pdu_specific", self.pdu_specific, 0xFF),
            ("source_address", self.source_address, 0xFF),
        ):
            if not 0 <= value <= max_value:
                raise ProtocolError(
                    f"field {name} must be within [0, {max_value}], "
                    f"got: {value}"
                )

    @property
    def is_pdu1(self) -> bool:
        """PDU1 format when PF < 240 (peer-to-peer / addressed)."""
        return self.pdu_format < PDU2_THRESHOLD

    @property
    def is_pdu2(self) -> bool:
        """PDU2 format when PF >= 240 (broadcast)."""
        return self.pdu_format >= PDU2_THRESHOLD

    @property
    def pgn(self) -> int:
        """The 18-bit Parameter Group Number.

        PDU1: PGN = (DP << 16) | (PF << 8)         (PS excluded, it is the destination)
        PDU2: PGN = (DP << 16) | (PF << 8) | PS    (PS is the group extension)
        """
        if self.is_pdu1:
            return (self.data_page << 16) | (self.pdu_format << 8)
        return (self.data_page << 16) | (self.pdu_format << 8) | self.pdu_specific

    @property
    def destination_address(self) -> int | None:
        """Destination address for PDU1, None for PDU2."""
        return self.pdu_specific if self.is_pdu1 else None

    def to_can_id(self) -> int:
        """The 29-bit extended CAN identifier."""
        return (
            ((self.priority & 0x7) << 26)
            | ((self.reserved & 0x1) << 25)
            | ((self.data_page & 0x1) << 24)
            | ((self.pdu_format & 0xFF) << 16)
            | ((self.pdu_specific & 0xFF) << 8)
            | (self.source_address & 0xFF)
        )

    @classmethod
    def from_can_id(cls, can_id: int) -> "J1939Id":
        """Build a J1939Id from a raw 29-bit CAN ID."""
        if not 0 <= can_id <= 0x1FFFFFFF:
            raise ProtocolError(
                f"CAN ID must be within the 29-bit range, got: 0x{can_id:X}"
            )
        return cls(
            priority=(can_id >> 26) & 0x7,
            reserved=(can_id >> 25) & 0x1,
            data_page=(can_id >> 24) & 0x1,
            pdu_format=(can_id >> 16) & 0xFF,
            pdu_specific=(can_id >> 8) & 0xFF,
            source_address=can_id & 0xFF,
        )

    @classmethod
    def from_pgn(
        cls,
        pgn: int,
        source_address: int = 0x00,
        priority: int = Priority.NORMAL,
        destination: int = GLOBAL_DESTINATION,
    ) -> "J1939Id":
        """Build a J1939Id from a PGN.

        For PDU1 PGNs the `destination` argument becomes the PS field;
        for PDU2 PGNs the PS is taken from the lower 8 bits of the PGN.
        """
        if not 0 <= pgn <= 0x3FFFF:
            raise ProtocolError(f"PGN must be within the 18-bit range, got: 0x{pgn:X}")

        data_page = (pgn >> 16) & 0x1
        pdu_format = (pgn >> 8) & 0xFF
        if pdu_format >= PDU2_THRESHOLD:
            pdu_specific = pgn & 0xFF
        else:
            pdu_specific = destination & 0xFF

        return cls(
            priority=priority,
            data_page=data_page,
            pdu_format=pdu_format,
            pdu_specific=pdu_specific,
            source_address=source_address,
        )

    def __str__(self) -> str:
        return (
            f"J1939Id(prio={self.priority}, PGN=0x{self.pgn:05X}, "
            f"SA=0x{self.source_address:02X})"
        )


@dataclass(frozen=True)
class Signal:
    """SAE J1939 SPN signal definition.

    An SPN sits at a specific bit position inside the 8-byte data field
    of a PGN. It converts to a physical value through the equation
    `physical = raw * scale + offset`. Since J1939 byte order is little
    endian (Intel), multi-byte values are placed low byte first during
    encoding.
    """

    spn: int
    name: str
    pgn: int
    start_bit: int
    bit_length: int
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.bit_length <= 0 or self.bit_length > 64:
            raise ProtocolError(
                f"bit_length must be within [1, 64]: {self.bit_length}"
            )
        if self.start_bit < 0 or self.start_bit + self.bit_length > 64:
            raise ProtocolError(
                f"Signal {self.name} does not fit in the 8-byte frame "
                f"(start_bit={self.start_bit}, bit_length={self.bit_length})"
            )
        if self.scale == 0:
            raise ProtocolError(f"scale cannot be 0 for {self.name}")

    @property
    def max_raw(self) -> int:
        """The highest raw value the signal can carry."""
        return (1 << self.bit_length) - 1

    def encode(self, physical_value: float) -> int:
        """Convert the physical value to a raw integer and clamp it."""
        if self.minimum is not None:
            physical_value = max(physical_value, self.minimum)
        if self.maximum is not None:
            physical_value = min(physical_value, self.maximum)
        raw = round((physical_value - self.offset) / self.scale)
        return max(0, min(raw, self.max_raw))

    def decode(self, raw_value: int) -> float:
        """Convert a raw value to its physical unit."""
        return raw_value * self.scale + self.offset

    def write_to_frame(self, frame: bytearray, physical_value: float) -> None:
        """Place the signal into the 8-byte CAN data in little endian order.

        The `frame` argument is updated in place. The signal's bits are
        cleared first, then the raw value's bits are written one by one.
        """
        if len(frame) != 8:
            raise ProtocolError(
                f"A J1939 frame must be 8 bytes, got: {len(frame)} bytes"
            )
        raw = self.encode(physical_value)

        for i in range(self.bit_length):
            bit_pos = self.start_bit + i
            byte_index = bit_pos // 8
            bit_index = bit_pos % 8
            if (raw >> i) & 0x1:
                frame[byte_index] |= 1 << bit_index
            else:
                frame[byte_index] &= ~(1 << bit_index) & 0xFF

    def read_from_frame(self, frame: bytes | bytearray) -> float:
        """Read the signal from 8-byte CAN data and return the physical value."""
        if len(frame) != 8:
            raise ProtocolError(
                f"A J1939 frame must be 8 bytes, got: {len(frame)} bytes"
            )
        raw = 0
        for i in range(self.bit_length):
            bit_pos = self.start_bit + i
            byte_index = bit_pos // 8
            bit_index = bit_pos % 8
            if (frame[byte_index] >> bit_index) & 0x1:
                raw |= 1 << i
        return self.decode(raw)


def make_empty_frame() -> bytearray:
    """Produce an 8-byte empty frame filled with NULL_BYTE (0xFF)."""
    return bytearray([NULL_BYTE] * 8)
