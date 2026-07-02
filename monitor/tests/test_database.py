"""Decode-table tests with known payloads.

Each test feeds a crafted 8-byte payload through `decode_frame` and
asserts the exact physical value, locking the decode formulas in
executable form.
"""
import pytest

from j1939mon.database import PGN_DECODERS
from j1939mon.decoder import decode_frame


def test_engine_speed_f004():
    """u16le at bytes 4-5 x 0.125: 0x1068 = 4200 -> 525.0 rpm."""
    data = [0, 0, 0, 0x68, 0x10, 0, 0, 0]
    decoded = decode_frame(0xF004, data)
    assert decoded["engine_speed"].value == 525.0
    assert decoded["engine_speed"].text == "525.00"


def test_engine_hours_fee5():
    data = [0x10, 0x27, 0, 0, 0, 0, 0, 0]
    decoded = decode_frame(0xFEE5, data)
    assert decoded["engine_hour"].value == pytest.approx(10000 * 0.05)


def test_oil_pressure_and_level_feef():
    data = [0, 0, 100, 50, 0, 0, 0, 0]
    decoded = decode_frame(0xFEEF, data)
    assert decoded["engine_oil_pressure"].value == 200.0
    assert decoded["engine_oil_level"].value == 40.0


def test_engine_temperature_feee_fahrenheit():
    """90 degC raw -> (90-40)*1.8+32 = 122.0 degF."""
    data = [130, 0, 0, 0, 0, 0, 0, 0]
    decoded = decode_frame(0xFEEE, data)
    assert decoded["engine_temperature"].value == 194.0
    assert decoded["engine_temperature"].unit == "degF"


def test_battery_voltage_fef7():
    data = [0, 0, 0, 0, 0x28, 0x02, 0, 0]
    decoded = decode_frame(0xFEF7, data)
    assert decoded["battery_voltage"].value == pytest.approx(552 * 0.05)


def test_fuel_level_fefc():
    data = [0, 125, 0, 0, 0, 0, 0, 0]
    decoded = decode_frame(0xFEFC, data)
    assert decoded["fuel_level"].value == 50.0


def test_vehicle_speed_fef1():
    """u16le at bytes 2-3 x 1/256: 0x4000 = 16384 -> 64.0 km/h."""
    data = [0, 0x00, 0x40, 0, 0, 0, 0, 0]
    decoded = decode_frame(0xFEF1, data)
    assert decoded["vehicle_speed"].value == 64.0


def test_boost_and_manifold_fef6():
    data = [0, 100, 60, 0, 0, 0, 0, 0]
    decoded = decode_frame(0xFEF6, data)
    assert decoded["engine_boost_pressure"].value == pytest.approx(100 * 2.0 * 0.145)
    assert decoded["manifold_temperature"].value == pytest.approx((60 - 40) * 1.8 + 32.0)


def test_fuel_economy_and_rate_fef2():
    """SPN 184 economy at bytes 3-4, SPN 183 rate at bytes 1-2."""
    data = [0x20, 0x03, 0x00, 0x02, 0, 0, 0, 0]
    decoded = decode_frame(0xFEF2, data)
    assert decoded["instant_fuel_rate"].value == pytest.approx(0x0320 * 0.05)
    assert decoded["instant_fuel_economy"].value == pytest.approx(0x0200 * 0.001953125)


def test_load_and_accelerator_f003():
    data = [0, 125, 85, 0, 0, 0, 0, 0]
    decoded = decode_frame(0xF003, data)
    assert decoded["engine_load"].value == 85.0
    assert decoded["accelerator_position"].value == 50.0


def test_total_distance_fee0():
    data = [0, 0, 0, 0, 0x40, 0x0D, 0x03, 0]
    decoded = decode_frame(0xFEE0, data)
    assert decoded["total_vehicle_distance"].value == pytest.approx(0x030D40 * 0.125)


def test_soc_and_plug_fcc2():
    data = [0, 0, 0, 0, 200, 0, 0, 0x40]
    decoded = decode_frame(0xFCC2, data)
    assert decoded["soc"].value == 80.0
    assert decoded["plug"].value == "Is Charging"

    data[7] = 0x00
    decoded = decode_frame(0xFCC2, data)
    assert decoded["plug"].value == "Not Charging"


def test_ac_current_fad4():
    data = [0, 0, 0x40, 0x01, 0, 0, 0, 0]
    decoded = decode_frame(0xFAD4, data)
    assert decoded["current_ac"].value == pytest.approx(0x0140 * 0.05)


def test_soh_fc5e():
    data = [240, 0, 0, 0, 0, 0, 0, 0]
    decoded = decode_frame(0xFC5E, data)
    assert decoded["soh"].value == 96.0


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0x00, "Charging Off"),
        (0x40, "Charging On"),
        (0x80, "Error"),
        (0xC0, "Not Available"),
        (0x7F, "Charging On"),
        (0xFF, "Not Available"),
    ],
)
def test_charging_state_f096(raw, expected):
    data = [0, 0, 0, 0, raw, 0, 0, 0]
    decoded = decode_frame(0xF096, data)
    assert decoded["hvesss1"].value == expected


def test_total_energy_fb4f():
    data = [0, 0, 0, 0, 100, 0, 0, 0]
    decoded = decode_frame(0xFB4F, data)
    assert decoded["tec"].value == 1.0


def test_battery_packs_fb97():
    data = [1, 0, 2, 0, 3, 0, 4, 0]
    decoded = decode_frame(0xFB97, data)
    assert decoded["vep15"].value == "1/2/3/4"


def test_unknown_pgn_returns_empty():
    assert decode_frame(0xABCD, [0] * 8) == {}


def test_short_payload_is_skipped():
    decoded = decode_frame(0xF004, [0, 0])
    assert decoded == {}


def test_every_spec_has_unique_label_id():
    seen: set[str] = set()
    for specs in PGN_DECODERS.values():
        for spec in specs:
            assert spec.label_id not in seen, f"duplicate label id: {spec.label_id}"
            seen.add(spec.label_id)


def test_every_spec_decodes_a_full_frame():
    for pgn, specs in PGN_DECODERS.items():
        decoded = decode_frame(pgn, [0] * 8)
        assert set(decoded) == {s.label_id for s in specs}, f"PGN 0x{pgn:04X} incomplete"
