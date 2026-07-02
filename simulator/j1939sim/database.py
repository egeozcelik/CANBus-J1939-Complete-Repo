"""J1939 signal and PGN definition database.

This module defines every PGN and SPN broadcast by the simulator from a
single source of truth, so scale, offset and byte positions are updated
in one place; the tests and the UI both consume these definitions.

Sources:
    - SAE J1939-71 Application Layer
    - SAE J1939-71 Common Parameter Group Descriptions

Notes:
    - All bit positions are zero-indexed, i.e. "byte 2" in the README
      corresponds to start_bit 8.
    - All multi-byte signals are placed in little endian (Intel) order.
    - The 0xFE00-0xFEFF and 0xFF00-0xFFFF ranges are reserved for
      proprietary B/A; the custom EV PGNs in this project (0x4400,
      0x4600, 0x4800) are broadcast in PDU1 format for demo purposes,
      with destination set to the global broadcast address.
    - Signals with SPNs numbered 900001+ are proprietary EV signals;
      the SOC and plug-status signals share PGN 0xFCC2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .protocol import Priority, Signal


@dataclass(frozen=True)
class PgnDefinition:
    """Broadcast metadata of a PGN.

    Attributes:
        pgn: 18-bit Parameter Group Number.
        name: Standard short name (e.g. EEC1, CCVS, LFE).
        description: Human-readable description.
        transmission_rate_ms: Broadcast period in milliseconds. 0 means
            the PGN is only sent on request (request-on-demand).
        priority: J1939 priority (default 6).
        source_address: Address of the ECU broadcasting this PGN.
        destination_address: Target for PDU1 PGNs. Ignored for PDU2.
    """

    pgn: int
    name: str
    description: str
    transmission_rate_ms: int = 1000
    priority: Priority = Priority.NORMAL
    source_address: int = 0x00
    destination_address: int = 0xFF

    @property
    def hex_label(self) -> str:
        return f"0x{self.pgn:04X}"


PGN_DATABASE: dict[int, PgnDefinition] = {
    0xFEF1: PgnDefinition(
        pgn=0xFEF1,
        name="CCVS",
        description="Cruise Control / Vehicle Speed",
        transmission_rate_ms=100,
        source_address=0x00,
    ),
    0xFEF6: PgnDefinition(
        pgn=0xFEF6,
        name="IC1",
        description="Inlet/Exhaust Conditions 1",
        transmission_rate_ms=500,
        source_address=0x00,
    ),
    0xFEF7: PgnDefinition(
        pgn=0xFEF7,
        name="VEP1",
        description="Vehicle Electrical Power 1",
        transmission_rate_ms=1000,
        source_address=0x00,
    ),
    0xFEF2: PgnDefinition(
        pgn=0xFEF2,
        name="LFE",
        description="Fuel Economy (Liquid)",
        transmission_rate_ms=100,
        source_address=0x00,
    ),
    0xFEE5: PgnDefinition(
        pgn=0xFEE5,
        name="HOURS",
        description="Engine Hours, Revolutions",
        transmission_rate_ms=1000,
        source_address=0x00,
    ),
    0xFEEE: PgnDefinition(
        pgn=0xFEEE,
        name="ET1",
        description="Engine Temperature 1",
        transmission_rate_ms=1000,
        source_address=0x00,
    ),
    0xFEEF: PgnDefinition(
        pgn=0xFEEF,
        name="EFL/P1",
        description="Engine Fluid Level / Pressure 1",
        transmission_rate_ms=500,
        source_address=0x00,
    ),
    0xFEFC: PgnDefinition(
        pgn=0xFEFC,
        name="DD",
        description="Dash Display",
        transmission_rate_ms=1000,
        source_address=0x17,
    ),
    0xFEE0: PgnDefinition(
        pgn=0xFEE0,
        name="VD",
        description="Vehicle Distance (Total / Trip)",
        transmission_rate_ms=1000,
        source_address=0x00,
    ),
    0xF003: PgnDefinition(
        pgn=0xF003,
        name="EEC2",
        description="Electronic Engine Controller 2",
        transmission_rate_ms=50,
        source_address=0x00,
    ),
    0xF004: PgnDefinition(
        pgn=0xF004,
        name="EEC1",
        description="Electronic Engine Controller 1",
        transmission_rate_ms=20,
        source_address=0x00,
    ),
    0x4400: PgnDefinition(
        pgn=0x4400,
        name="EV_MOTOR",
        description="EV Motor Status (proprietary)",
        transmission_rate_ms=100,
        source_address=0xF6,
        destination_address=0xFF,
    ),
    0x4600: PgnDefinition(
        pgn=0x4600,
        name="EV_BATT_PWR",
        description="EV Battery Power (proprietary)",
        transmission_rate_ms=100,
        source_address=0xF6,
        destination_address=0xFF,
    ),
    0x4800: PgnDefinition(
        pgn=0x4800,
        name="EV_BATT_TEMP",
        description="EV Battery Temperature (proprietary)",
        transmission_rate_ms=500,
        source_address=0xF6,
        destination_address=0xFF,
    ),
    0xFCC2: PgnDefinition(
        pgn=0xFCC2,
        name="HVESDS1",
        description="High Voltage Energy Storage Diagnostic Status 1",
        transmission_rate_ms=1000,
        source_address=0xF6,
    ),
    0xFAD4: PgnDefinition(
        pgn=0xFAD4,
        name="EVSE_AC",
        description="EVSE AC RMS Voltage",
        transmission_rate_ms=1000,
        source_address=0xF6,
    ),
    0xFC5E: PgnDefinition(
        pgn=0xFC5E,
        name="HVESS1_SOH",
        description="HV Energy Storage State of Health",
        transmission_rate_ms=5000,
        source_address=0xF6,
    ),
    0xF096: PgnDefinition(
        pgn=0xF096,
        name="HVESSS1",
        description="HV Energy Storage System Status 1",
        transmission_rate_ms=1000,
        source_address=0xF6,
    ),
    0xFB4F: PgnDefinition(
        pgn=0xFB4F,
        name="TEC",
        description="Total Energy Consumption",
        transmission_rate_ms=1000,
        source_address=0xF6,
    ),
    0xFB97: PgnDefinition(
        pgn=0xFB97,
        name="VEP15",
        description="Vehicle Electrical Power 15",
        transmission_rate_ms=1000,
        source_address=0xF6,
    ),
}

SIGNAL_DATABASE: dict[str, Signal] = {
    "vehicle_speed": Signal(
        spn=84,
        name="Wheel-Based Vehicle Speed",
        pgn=0xFEF1,
        start_bit=8,
        bit_length=16,
        scale=1.0 / 256.0,
        offset=0.0,
        unit="km/h",
        minimum=0.0,
        maximum=250.996,
    ),
    "engine_boost_pressure": Signal(
        spn=102,
        name="Engine Intake Manifold #1 Pressure",
        pgn=0xFEF6,
        start_bit=8,
        bit_length=8,
        scale=2.0,
        offset=0.0,
        unit="kPa",
        minimum=0.0,
        maximum=500.0,
    ),
    "manifold_temperature": Signal(
        spn=105,
        name="Engine Intake Manifold 1 Temperature",
        pgn=0xFEF6,
        start_bit=16,
        bit_length=8,
        scale=1.0,
        offset=-40.0,
        unit="degC",
        minimum=-40.0,
        maximum=210.0,
    ),
    "battery_voltage": Signal(
        spn=168,
        name="Battery Potential / Power Input 1",
        pgn=0xFEF7,
        start_bit=32,
        bit_length=16,
        scale=0.05,
        offset=0.0,
        unit="V",
        minimum=0.0,
        maximum=3212.75,
    ),
    "instant_fuel_rate": Signal(
        spn=183,
        name="Engine Fuel Rate",
        pgn=0xFEF2,
        start_bit=0,
        bit_length=16,
        scale=0.05,
        offset=0.0,
        unit="L/h",
        minimum=0.0,
        maximum=3212.75,
    ),
    "instant_fuel_economy": Signal(
        spn=184,
        name="Engine Instantaneous Fuel Economy",
        pgn=0xFEF2,
        start_bit=16,
        bit_length=16,
        scale=1.0 / 512.0,
        offset=0.0,
        unit="km/L",
        minimum=0.0,
        maximum=125.498,
    ),
    "engine_hour": Signal(
        spn=247,
        name="Engine Total Hours of Operation",
        pgn=0xFEE5,
        start_bit=0,
        bit_length=32,
        scale=0.05,
        offset=0.0,
        unit="h",
        minimum=0.0,
        maximum=210_554_060.75,
    ),
    "engine_temperature": Signal(
        spn=110,
        name="Engine Coolant Temperature",
        pgn=0xFEEE,
        start_bit=0,
        bit_length=8,
        scale=1.0,
        offset=-40.0,
        unit="degC",
        minimum=-40.0,
        maximum=210.0,
    ),
    "engine_oil_level": Signal(
        spn=98,
        name="Engine Oil Level",
        pgn=0xFEEF,
        start_bit=16,
        bit_length=8,
        scale=0.4,
        offset=0.0,
        unit="%",
        minimum=0.0,
        maximum=100.0,
    ),
    "engine_oil_pressure": Signal(
        spn=100,
        name="Engine Oil Pressure",
        pgn=0xFEEF,
        start_bit=24,
        bit_length=8,
        scale=4.0,
        offset=0.0,
        unit="kPa",
        minimum=0.0,
        maximum=1000.0,
    ),
    "fuel_level": Signal(
        spn=96,
        name="Fuel Level 1",
        pgn=0xFEFC,
        start_bit=8,
        bit_length=8,
        scale=0.4,
        offset=0.0,
        unit="%",
        minimum=0.0,
        maximum=100.0,
    ),
    "total_vehicle_distance": Signal(
        spn=245,
        name="Total Vehicle Distance",
        pgn=0xFEE0,
        start_bit=32,
        bit_length=32,
        scale=0.125,
        offset=0.0,
        unit="km",
        minimum=0.0,
    ),
    "accelerator_position": Signal(
        spn=91,
        name="Accelerator Pedal Position 1",
        pgn=0xF003,
        start_bit=8,
        bit_length=8,
        scale=0.4,
        offset=0.0,
        unit="%",
        minimum=0.0,
        maximum=100.0,
    ),
    "engine_load": Signal(
        spn=92,
        name="Engine Percent Load At Current Speed",
        pgn=0xF003,
        start_bit=16,
        bit_length=8,
        scale=1.0,
        offset=0.0,
        unit="%",
        minimum=0.0,
        maximum=250.0,
    ),
    "engine_speed": Signal(
        spn=190,
        name="Engine Speed",
        pgn=0xF004,
        start_bit=24,
        bit_length=16,
        scale=0.125,
        offset=0.0,
        unit="rpm",
        minimum=0.0,
        maximum=8031.875,
    ),
    "motor_speed": Signal(
        spn=900_001,
        name="EV Motor Speed",
        pgn=0x4400,
        start_bit=16,
        bit_length=16,
        scale=0.5,
        offset=0.0,
        unit="rpm",
        minimum=0.0,
        maximum=32767.5,
        description="Proprietary EV motor speed",
    ),
    "motor_temp": Signal(
        spn=900_002,
        name="EV Motor Temperature",
        pgn=0x4400,
        start_bit=32,
        bit_length=8,
        scale=1.0,
        offset=-40.0,
        unit="degC",
        minimum=-40.0,
        maximum=210.0,
        description="Proprietary EV motor temperature",
    ),
    "mcu_temp": Signal(
        spn=900_003,
        name="Motor Control Unit Temperature",
        pgn=0x4400,
        start_bit=40,
        bit_length=8,
        scale=1.0,
        offset=-40.0,
        unit="degC",
        minimum=-40.0,
        maximum=210.0,
        description="Proprietary MCU temperature",
    ),
    "battery_voltage_ev": Signal(
        spn=900_004,
        name="EV Battery Pack Voltage",
        pgn=0x4600,
        start_bit=0,
        bit_length=16,
        scale=0.015,
        offset=0.0,
        unit="V",
        minimum=0.0,
        maximum=983.025,
        description="Proprietary EV battery pack voltage",
    ),
    "battery_current": Signal(
        spn=900_005,
        name="EV Battery Pack Current",
        pgn=0x4600,
        start_bit=16,
        bit_length=16,
        scale=0.05,
        offset=0.0,
        unit="A",
        minimum=0.0,
        maximum=3275.0,
        description="Proprietary EV battery pack current",
    ),
    "highest_temp": Signal(
        spn=900_006,
        name="EV Battery Highest Cell Temperature",
        pgn=0x4800,
        start_bit=0,
        bit_length=8,
        scale=1.0,
        offset=-40.0,
        unit="degC",
        minimum=-40.0,
        maximum=210.0,
    ),
    "pack_temp": Signal(
        spn=900_007,
        name="EV Battery Pack Average Temperature",
        pgn=0x4800,
        start_bit=8,
        bit_length=8,
        scale=1.0,
        offset=0.0,
        unit="degC",
        minimum=0.0,
        maximum=255.0,
    ),
    "soc": Signal(
        spn=7895,
        name="HV Battery State of Charge",
        pgn=0xFCC2,
        start_bit=32,
        bit_length=8,
        scale=0.4,
        offset=0.0,
        unit="%",
        minimum=0.0,
        maximum=100.0,
    ),
    "plug": Signal(
        spn=7898,
        name="EVSE Connector Plug Status",
        pgn=0xFCC2,
        start_bit=60,
        bit_length=4,
        scale=1.0,
        offset=0.0,
        unit="state",
        minimum=0.0,
        maximum=15.0,
        description="0=Not Charging, 4=Charging (per HVESDS1 standard)",
    ),
    "current_ac": Signal(
        spn=12867,
        name="EVSE1 AC RMS Current",
        pgn=0xFAD4,
        start_bit=16,
        bit_length=16,
        scale=0.05,
        offset=0.0,
        unit="A",
        minimum=0.0,
        maximum=3212.75,
    ),
    "soh": Signal(
        spn=8121,
        name="HV Battery State of Health",
        pgn=0xFC5E,
        start_bit=0,
        bit_length=8,
        scale=0.4,
        offset=0.0,
        unit="%",
        minimum=0.0,
        maximum=100.0,
    ),
    "hvesss1": Signal(
        spn=8207,
        name="HV Energy Storage System Charging State",
        pgn=0xF096,
        start_bit=38,
        bit_length=2,
        scale=1.0,
        offset=0.0,
        unit="state",
        minimum=0.0,
        maximum=3.0,
        description="0=Idle, 1=AC charging, 2=DC charging",
    ),
    "tec": Signal(
        spn=900_008,
        name="Total Energy Consumed",
        pgn=0xFB4F,
        start_bit=32,
        bit_length=32,
        scale=0.01,
        offset=0.0,
        unit="kWh",
        minimum=0.0,
    ),
    "vep15": Signal(
        spn=9368,
        name="Vehicle Electrical Power 15 - Voltage 1",
        pgn=0xFB97,
        start_bit=0,
        bit_length=16,
        scale=1.0,
        offset=0.0,
        unit="Ah",
        minimum=0.0,
        maximum=64255.0,
    ),
}


def signals_for_pgn(pgn: int) -> list[Signal]:
    """Return every signal belonging to the given PGN."""
    return [s for s in SIGNAL_DATABASE.values() if s.pgn == pgn]


def all_pgns() -> Iterable[PgnDefinition]:
    """Return all defined PGNs."""
    return PGN_DATABASE.values()


def get_signal(key: str) -> Signal:
    """Fetch a signal by its short key (e.g. 'engine_speed')."""
    if key not in SIGNAL_DATABASE:
        raise KeyError(f"Unknown signal key: {key!r}")
    return SIGNAL_DATABASE[key]


def get_pgn(pgn: int) -> PgnDefinition:
    """Fetch a PGN definition by number."""
    if pgn not in PGN_DATABASE:
        raise KeyError(f"Unknown PGN: 0x{pgn:04X}")
    return PGN_DATABASE[pgn]
