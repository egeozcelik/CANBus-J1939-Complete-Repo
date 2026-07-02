"""J1939 protocol tests.

Verifies at the unit level that J1939Id and Signal conform to SAE
J1939-21. These tests require no hardware.
"""
import pytest

from j1939sim.exceptions import ProtocolError
from j1939sim.protocol import (
    GLOBAL_DESTINATION,
    J1939Id,
    Priority,
    Signal,
    make_empty_frame,
)


class TestJ1939Id:
    def test_eec1_round_trip(self):
        """Known-good arbitration ID for PGN 0xF004 (EEC1)."""
        ident = J1939Id.from_pgn(0xF004, source_address=0x01, priority=Priority.NORMAL)
        assert ident.pgn == 0xF004
        assert ident.is_pdu2
        assert ident.to_can_id() == 0x18F00401

    def test_pdu1_pgn_carries_destination(self):
        ident = J1939Id.from_pgn(0xEA00, source_address=0xF6, destination=0x33)
        assert ident.is_pdu1
        assert ident.pdu_specific == 0x33
        assert ident.destination_address == 0x33
        assert ident.pgn == 0xEA00

    def test_pdu2_pgn_includes_group_extension(self):
        ident = J1939Id.from_pgn(0xFEF1, source_address=0x00)
        assert ident.is_pdu2
        assert ident.pgn == 0xFEF1
        assert ident.destination_address is None

    def test_can_id_round_trip(self):
        ident = J1939Id.from_pgn(0xFEF1, source_address=0x05, priority=Priority.HIGH)
        can_id = ident.to_can_id()
        decoded = J1939Id.from_can_id(can_id)
        assert decoded.pgn == ident.pgn
        assert decoded.source_address == ident.source_address
        assert decoded.priority == ident.priority

    def test_global_destination_default(self):
        ident = J1939Id.from_pgn(0xEA00, source_address=0x01)
        assert ident.destination_address == GLOBAL_DESTINATION

    def test_invalid_priority_raises(self):
        with pytest.raises(ProtocolError):
            J1939Id(priority=8, data_page=0, pdu_format=0xF0,
                    pdu_specific=0x04, source_address=0x01)

    def test_invalid_can_id_raises(self):
        with pytest.raises(ProtocolError):
            J1939Id.from_can_id(0xFFFFFFFF)


class TestSignal:
    def test_engine_speed_encoding_known_value(self):
        """SPN 190 Engine Speed: 1234.5 RPM -> raw 9876 (0x2694) at bytes 4-5.

        scale = 0.125, raw = 1234.5 / 0.125 = 9876 = 0x2694.
        Little endian byte sequence: [0x94, 0x26] at start_bit 24.
        """
        engine_speed = Signal(
            spn=190,
            name="Engine Speed",
            pgn=0xF004,
            start_bit=24,
            bit_length=16,
            scale=0.125,
            offset=0.0,
            unit="rpm",
        )
        frame = make_empty_frame()
        engine_speed.write_to_frame(frame, 1234.5)
        assert frame[3] == 0x94
        assert frame[4] == 0x26
        assert engine_speed.read_from_frame(frame) == 1234.5

    def test_signal_round_trip(self):
        boost = Signal(
            spn=102, name="Boost", pgn=0xFEF6,
            start_bit=8, bit_length=8, scale=2.0, offset=0.0, unit="kPa",
        )
        frame = make_empty_frame()
        boost.write_to_frame(frame, 100.0)
        assert boost.read_from_frame(frame) == 100.0

    def test_signal_clamps_to_range(self):
        s = Signal(
            spn=1, name="x", pgn=0xFEF6,
            start_bit=0, bit_length=8, scale=1.0, offset=0.0,
            minimum=0.0, maximum=100.0,
        )
        frame = make_empty_frame()
        s.write_to_frame(frame, 250.0)
        assert s.read_from_frame(frame) == 100.0

    def test_signal_with_offset(self):
        """Engine temperature: -40 C offset, 1 C/bit."""
        s = Signal(
            spn=110, name="Temp", pgn=0xFEEE,
            start_bit=0, bit_length=8, scale=1.0, offset=-40.0,
            minimum=-40.0, maximum=210.0,
        )
        frame = make_empty_frame()
        s.write_to_frame(frame, 0.0)
        assert frame[0] == 40
        assert s.read_from_frame(frame) == 0.0

    def test_signal_overflow_rejected_at_construction(self):
        with pytest.raises(ProtocolError):
            Signal(spn=1, name="x", pgn=0, start_bit=60, bit_length=16,
                   scale=1.0, offset=0.0)

    def test_zero_scale_rejected(self):
        with pytest.raises(ProtocolError):
            Signal(spn=1, name="x", pgn=0, start_bit=0, bit_length=8,
                   scale=0.0, offset=0.0)
