"""PGN extraction tests per SAE J1939-21."""
import pytest

from j1939mon.protocol import extract_pgn, source_address


def test_eec1_known_id():
    """The classic worked example: CAN ID 0x0CF00401 -> PGN 0xF004 (61444)."""
    assert extract_pgn(0x0CF00401) == 0xF004
    assert source_address(0x0CF00401) == 0x01


def test_pdu2_group_extension_included():
    assert extract_pgn(0x18FEF100) == 0xFEF1


def test_pdu1_destination_excluded():
    """For PDU1 (PF < 240) the PS byte is a destination, not part of the PGN."""
    assert extract_pgn(0x18EA3301) == 0xEA00


def test_data_page_bit_included():
    assert extract_pgn(0x19F00401) == 0x1F004


def test_priority_bits_ignored():
    assert extract_pgn(0x0CF00401) == extract_pgn(0x18F00401)


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        extract_pgn(0x20000000)
    with pytest.raises(ValueError):
        extract_pgn(-1)
