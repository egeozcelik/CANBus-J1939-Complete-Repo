"""SAE J1939-21 identifier parsing.

Extracts the 18-bit Parameter Group Number from a 29-bit extended CAN
identifier with correct PDU1/PDU2 handling:

  bit 28..26 -> Priority
  bit 25     -> Reserved (part of the PGN as EDP in J1939-21 terms)
  bit 24     -> Data Page
  bit 23..16 -> PDU Format (PF)
  bit 15..8  -> PDU Specific (PS)
  bit 7..0   -> Source Address

For PDU1 frames (PF < 240) the PS byte is a destination address and is
excluded from the PGN; for PDU2 frames (PF >= 240) the PS byte is a
group extension and is part of the PGN.
"""
from __future__ import annotations

from typing import Final

PDU2_THRESHOLD: Final[int] = 240
MAX_29_BIT: Final[int] = 0x1FFFFFFF


def extract_pgn(can_id: int) -> int:
    """Return the 18-bit PGN encoded in a 29-bit CAN identifier."""
    if not 0 <= can_id <= MAX_29_BIT:
        raise ValueError(f"CAN ID must be within the 29-bit range, got: 0x{can_id:X}")
    pdu_format = (can_id >> 16) & 0xFF
    if pdu_format < PDU2_THRESHOLD:
        return (can_id >> 8) & 0x3FF00
    return (can_id >> 8) & 0x3FFFF


def source_address(can_id: int) -> int:
    """Return the source address byte of a 29-bit CAN identifier."""
    return can_id & 0xFF
