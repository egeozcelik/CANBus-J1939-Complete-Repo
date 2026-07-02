"""Consistency tests for the PGN/Signal database."""
import pytest

from j1939sim.database import (
    PGN_DATABASE,
    SIGNAL_DATABASE,
    get_pgn,
    get_signal,
    signals_for_pgn,
)


def test_each_signal_references_known_pgn():
    """Every signal must belong to a defined PGN."""
    for key, signal in SIGNAL_DATABASE.items():
        assert signal.pgn in PGN_DATABASE, (
            f"signal {key} references an undefined PGN ({signal.pgn:#06X})"
        )


def test_signals_within_8_byte_frame():
    """No signal may exceed the 8-byte boundary."""
    for key, signal in SIGNAL_DATABASE.items():
        assert signal.start_bit + signal.bit_length <= 64, (
            f"signal {key} does not fit in the 8-byte frame"
        )


def test_no_overlapping_signals_per_pgn():
    """Signals within the same PGN must not overlap at the bit level."""
    for pgn_def in PGN_DATABASE.values():
        bits_used: dict[int, str] = {}
        for sig in signals_for_pgn(pgn_def.pgn):
            for bit in range(sig.start_bit, sig.start_bit + sig.bit_length):
                if bit in bits_used:
                    pytest.fail(
                        f"PGN 0x{pgn_def.pgn:04X}: {sig.name} overlaps "
                        f"{bits_used[bit]} at bit {bit}"
                    )
                bits_used[bit] = sig.name


def test_get_signal_returns_known_keys():
    sig = get_signal("engine_speed")
    assert sig.spn == 190


def test_get_signal_unknown_raises():
    with pytest.raises(KeyError):
        get_signal("does_not_exist")


def test_get_pgn_returns_definition():
    pgn = get_pgn(0xF004)
    assert pgn.name == "EEC1"


def test_pgn_transmission_rates_positive_or_zero():
    for pgn in PGN_DATABASE.values():
        assert pgn.transmission_rate_ms >= 0


def test_engine_speed_signal_known_position():
    """SAE J1939-71 EEC1: SPN 190 bytes 4-5 -> start_bit 24, len 16."""
    sig = get_signal("engine_speed")
    assert sig.start_bit == 24
    assert sig.bit_length == 16
    assert sig.scale == 0.125


def test_vehicle_speed_signal_known_position():
    """SAE J1939-71 CCVS: SPN 84 bytes 2-3 -> start_bit 8, len 16."""
    sig = get_signal("vehicle_speed")
    assert sig.start_bit == 8
    assert sig.bit_length == 16
    assert sig.scale == pytest.approx(1.0 / 256.0)
