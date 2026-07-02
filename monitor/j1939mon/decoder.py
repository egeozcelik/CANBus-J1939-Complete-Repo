"""Frame decoding built on top of the declarative decode table."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from .database import PGN_DECODERS, SignalSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DecodedSignal:
    """A single decoded signal ready for display.

    `text` holds the formatted value without unit (what the dashboard
    label shows); `value` holds the raw physical value or state string.
    """

    name: str
    label_id: str
    unit: str
    value: float | str
    text: str


def decode_frame(pgn: int, data: Sequence[int]) -> dict[str, DecodedSignal]:
    """Decode one 8-byte payload for the given PGN.

    Returns a mapping of label ids to decoded signals; unknown PGNs
    yield an empty mapping. Signals that fail to decode (e.g. short
    payloads) are skipped and logged.
    """
    specs = PGN_DECODERS.get(pgn)
    if not specs:
        return {}

    decoded: dict[str, DecodedSignal] = {}
    for spec in specs:
        try:
            value = spec.decode(data)
        except (IndexError, TypeError) as exc:
            logger.warning("Decode failed for %s (PGN 0x%04X): %s", spec.name, pgn, exc)
            continue
        if isinstance(value, str):
            text = value
        else:
            value = round(value, 2)
            text = spec.fmt.format(value)
        decoded[spec.label_id] = DecodedSignal(
            name=spec.name,
            label_id=spec.label_id,
            unit=spec.unit,
            value=value,
            text=text,
        )
    return decoded
