"""Scheduling and frame composition tests for SimulationEngine.

Uses python-can's 'virtual' interface so the tests can run without
hardware.
"""
from __future__ import annotations

import time

import pytest

from j1939sim.engine import BroadcastEvent, SimulationEngine
from j1939sim.transport import CanTransport


@pytest.fixture
def transport():
    tx = CanTransport(interface="virtual", channel="test_channel", bitrate=250_000)
    tx.connect()
    yield tx
    tx.disconnect()


def make_signal_provider() -> dict[str, float]:
    return {
        "engine_speed": 612.0,
        "vehicle_speed": 50.0,
        "engine_temperature": 90.0,
        "fuel_level": 75.0,
        "soc": 80.0,
        "plug": 0.0,
    }


def test_engine_start_stop(transport):
    engine = SimulationEngine(transport, lambda: make_signal_provider())
    assert not engine.is_running
    engine.start()
    assert engine.is_running
    engine.stop()
    assert not engine.is_running


def test_engine_emits_events(transport):
    captured: list[BroadcastEvent] = []
    engine = SimulationEngine(
        transport,
        lambda: make_signal_provider(),
        listener=captured.append,
    )
    engine.start()

    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        engine.tick()
        time.sleep(0.02)
    engine.stop()

    assert len(captured) > 0
    assert all(ev.success for ev in captured)


def test_broadcast_now_specific_pgn(transport):
    engine = SimulationEngine(transport, lambda: make_signal_provider())
    engine.start()
    success = engine.broadcast_now(0xF004)
    assert success is True
    engine.stop()


def test_unknown_pgn_raises(transport):
    engine = SimulationEngine(transport, lambda: make_signal_provider())
    engine.start()
    with pytest.raises(KeyError):
        engine.broadcast_now(0xABCDE)
    engine.stop()
