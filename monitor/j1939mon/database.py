"""Declarative J1939 decode table.

Maps each supported PGN to the signals it carries. Every signal is
described by a `SignalSpec` whose `decode` callable transcribes the
byte-level extraction (little-endian assembly, scale, offset) for that
signal. Display-unit conversions of the original dashboard are kept:
temperatures are converted to degF and boost pressure to psi.

Notes:
    - PGN 0xFEF2 instantaneous fuel economy (SPN 184) is read from
      bytes 3-4 and the 0xFCC2 plug-status nibble (SPN 7898) from the
      upper nibble of byte 8, matching SAE J1939-71 byte positions and
      the companion simulator's encoder.
    - PGN 0xF096 charging state is a 2-bit field in the upper bits of
      byte 5; the remaining bits are masked off so J1939 0xFF padding
      in unused bit positions does not corrupt the state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

DecodeFn = Callable[[Sequence[int]], "float | str"]


@dataclass(frozen=True)
class SignalSpec:
    """Decode description of a single signal within a PGN.

    Attributes:
        name: Human-readable signal name.
        label_id: Id of the GTK label that displays this signal.
        unit: Display unit ("" for state/text signals).
        decode: Callable turning the 8 data bytes into a physical value.
        fmt: Format string applied to numeric values.
    """

    name: str
    label_id: str
    unit: str
    decode: DecodeFn
    fmt: str = "{:.2f}"


def u16le(data: Sequence[int], index: int) -> int:
    """Assemble an unsigned 16-bit little-endian value at `index`."""
    return data[index] + data[index + 1] * 256


def u32le(data: Sequence[int], index: int) -> int:
    """Assemble an unsigned 32-bit little-endian value at `index`."""
    return (
        data[index]
        + data[index + 1] * 256
        + data[index + 2] * 256 * 256
        + data[index + 3] * 256 * 256 * 256
    )


def _plug_state(data: Sequence[int]) -> str:
    value = (data[7] >> 4) & 0x0F
    return "Is Charging" if value == 4 else "Not Charging"


_HVESSS1_STATES = {
    0: "Charging Off",
    64: "Charging On",
    128: "Error",
    192: "Not Available",
}


def _hvesss1_state(data: Sequence[int]) -> str:
    return _HVESSS1_STATES[data[4] & 0xC0]


def _vep15_packs(data: Sequence[int]) -> str:
    batt1 = u16le(data, 0)
    batt2 = u16le(data, 2)
    batt3 = u16le(data, 4)
    batt4 = u16le(data, 6)
    return f"{batt1}/{batt2}/{batt3}/{batt4}"


PGN_DECODERS: dict[int, tuple[SignalSpec, ...]] = {
    0xF004: (
        SignalSpec(
            name="Engine Speed",
            label_id="engine_speed",
            unit="rpm",
            decode=lambda d: u16le(d, 3) * 0.125,
        ),
    ),
    0xFEE5: (
        SignalSpec(
            name="Engine Hours",
            label_id="engine_hour",
            unit="h",
            decode=lambda d: u32le(d, 0) * 0.05,
        ),
    ),
    0xFEEF: (
        SignalSpec(
            name="Engine Oil Pressure",
            label_id="engine_oil_pressure",
            unit="kPa",
            decode=lambda d: d[3] * 4.0,
        ),
        SignalSpec(
            name="Engine Oil Level",
            label_id="engine_oil_level",
            unit="%",
            decode=lambda d: d[2] * 0.4,
        ),
    ),
    0xFEEE: (
        SignalSpec(
            name="Engine Coolant Temperature",
            label_id="engine_temperature",
            unit="degF",
            decode=lambda d: (d[0] - 40) * 1.8 + 32.0,
        ),
    ),
    0xFEF7: (
        SignalSpec(
            name="Battery Voltage",
            label_id="battery_voltage",
            unit="V",
            decode=lambda d: u16le(d, 4) * 0.05,
        ),
    ),
    0xFEFC: (
        SignalSpec(
            name="Fuel Level",
            label_id="fuel_level",
            unit="%",
            decode=lambda d: d[1] * 0.4,
        ),
    ),
    0xFEF1: (
        SignalSpec(
            name="Vehicle Speed",
            label_id="vehicle_speed",
            unit="km/h",
            decode=lambda d: u16le(d, 1) * 0.00390625,
        ),
    ),
    0xFEF6: (
        SignalSpec(
            name="Engine Boost Pressure",
            label_id="engine_boost_pressure",
            unit="psi",
            decode=lambda d: d[1] * 2.0 * 0.145,
        ),
        SignalSpec(
            name="Intake Manifold Temperature",
            label_id="manifold_temperature",
            unit="degF",
            decode=lambda d: (d[2] - 40) * 1.8 + 32.0,
        ),
    ),
    0xFEF2: (
        SignalSpec(
            name="Instant Fuel Economy",
            label_id="instant_fuel_economy",
            unit="km/L",
            decode=lambda d: u16le(d, 2) * 0.001953125,
        ),
        SignalSpec(
            name="Instant Fuel Rate",
            label_id="instant_fuel_rate",
            unit="L/h",
            decode=lambda d: u16le(d, 0) * 0.05,
        ),
    ),
    0xF003: (
        SignalSpec(
            name="Engine Load",
            label_id="engine_load",
            unit="%",
            decode=lambda d: float(d[2]),
        ),
        SignalSpec(
            name="Accelerator Position",
            label_id="accelerator_position",
            unit="%",
            decode=lambda d: d[1] * 0.4,
        ),
    ),
    0xFEE0: (
        SignalSpec(
            name="Total Vehicle Distance",
            label_id="total_vehicle_distance",
            unit="km",
            decode=lambda d: u32le(d, 4) * 0.125,
        ),
    ),
    0xFCC2: (
        SignalSpec(
            name="State of Charge",
            label_id="soc",
            unit="%",
            decode=lambda d: d[4] * 0.4,
        ),
        SignalSpec(
            name="Plug Status",
            label_id="plug",
            unit="",
            decode=_plug_state,
        ),
    ),
    0xFAD4: (
        SignalSpec(
            name="EVSE AC Current",
            label_id="current_ac",
            unit="A",
            decode=lambda d: u16le(d, 2) * 0.05,
        ),
    ),
    0xFC5E: (
        SignalSpec(
            name="State of Health",
            label_id="soh",
            unit="%",
            decode=lambda d: d[0] * 0.4,
        ),
    ),
    0xF096: (
        SignalSpec(
            name="HV Energy Storage Charging State",
            label_id="hvesss1",
            unit="",
            decode=_hvesss1_state,
        ),
    ),
    0xFB4F: (
        SignalSpec(
            name="Total Energy Consumed",
            label_id="tec",
            unit="kWh",
            decode=lambda d: u32le(d, 4) / 100,
        ),
    ),
    0xFB97: (
        SignalSpec(
            name="SLI Battery Packs",
            label_id="vep15",
            unit="",
            decode=_vep15_packs,
        ),
    ),
}


def supported_pgns() -> tuple[int, ...]:
    """Return every PGN the decode table understands."""
    return tuple(PGN_DECODERS.keys())
