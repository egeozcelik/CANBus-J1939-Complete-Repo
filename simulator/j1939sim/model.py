"""Vehicle dynamics and signal value model.

Derives the signal values the simulator broadcasts. Instead of a static
dictionary, it uses a simple state model that mimics real-world
correlations:

  - An acceleration request raises rpm -> vehicle speed rises
    -> fuel consumption rises
  - A deceleration request does the opposite
  - SOC drains over time and rises while charging
  - Oil pressure and temperature track engine load

The model is intentionally simple; its goal is a believable simulation
that feeds the lower layers (engine.py) through a single interface. For
a detailed vehicle model, integration with tools such as pyfmi/Modelica
could be used instead.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class VehicleState:
    """Plain container for the vehicle's instantaneous physical state.

    Units: speeds in km/h and rpm, positions/levels in percent,
    temperatures in degC, pressures in kPa, fuel rate in L/h, fuel
    economy in km/L, hours in h, distance in km, voltages in V,
    currents in A, energy in kWh, capacity in Ah. `plug` is 0=unplugged
    and 4=plugged; `hvesss1` is 0=idle, 1=AC charging, 2=DC charging.
    """

    vehicle_speed: float = 0.0
    engine_speed: float = 800.0
    accelerator_position: float = 0.0
    engine_load: float = 10.0
    engine_temperature: float = 90.0
    engine_oil_pressure: float = 320.0
    engine_oil_level: float = 80.0
    engine_boost_pressure: float = 100.0
    manifold_temperature: float = 35.0
    instant_fuel_rate: float = 4.0
    instant_fuel_economy: float = 8.5
    fuel_level: float = 75.0
    engine_hour: float = 1234.5
    total_vehicle_distance: float = 25_430.0
    battery_voltage: float = 27.6

    motor_speed: float = 0.0
    motor_temp: float = 35.0
    mcu_temp: float = 38.0
    battery_voltage_ev: float = 580.0
    battery_current: float = 0.0
    soc: float = 78.0
    soh: float = 96.5
    highest_temp: float = 32.0
    pack_temp: float = 30.0
    current_ac: float = 0.0
    tec: float = 1234.56
    vep15: float = 12500.0

    plug: int = 0
    hvesss1: int = 0


@dataclass
class VehicleModel:
    """Vehicle dynamics model.

    Responds to acceleration and brake inputs and evolves the state
    smoothly over time. `accel_input` ranges from -1 (full brake)
    through 0 (coasting) to +1 (full throttle).
    """

    state: VehicleState = field(default_factory=VehicleState)
    rng: random.Random = field(default_factory=random.Random)
    accel_input: float = 0.0
    is_ev_mode: bool = True

    def request_accelerate(self, magnitude: float = 0.6) -> None:
        """Throttle pressed (corresponds to the UP button in the UI)."""
        self.accel_input = max(0.0, min(magnitude, 1.0))

    def request_decelerate(self, magnitude: float = 0.6) -> None:
        """Brake pressed (corresponds to the DOWN button in the UI)."""
        self.accel_input = -max(0.0, min(magnitude, 1.0))

    def release_pedal(self) -> None:
        """Release the pedal."""
        self.accel_input = 0.0

    def set_plug_state(self, plugged: bool) -> None:
        self.state.plug = 4 if plugged else 0
        if not plugged:
            self.state.hvesss1 = 0
            self.state.current_ac = 0.0
            self.state.battery_current = 0.0

    def set_ac_charging(self, charging: bool) -> None:
        if charging and self.state.plug == 4:
            self.state.hvesss1 = 1
            self.state.current_ac = 16.0
        else:
            self.state.hvesss1 = 0
            self.state.current_ac = 0.0

    def step(self, dt: float) -> None:
        """Advance the model by `dt` seconds."""
        s = self.state
        accel = self.accel_input

        accel_target = max(0.0, accel) * 100.0
        s.accelerator_position += (accel_target - s.accelerator_position) * min(1.0, dt * 4.0)
        s.accelerator_position = max(0.0, min(s.accelerator_position, 100.0))

        target_speed = self._target_speed_from_accel(accel)
        s.vehicle_speed += (target_speed - s.vehicle_speed) * min(1.0, dt * 0.5)
        s.vehicle_speed = max(0.0, min(s.vehicle_speed, 220.0))

        rpm_target = self._rpm_target(s.vehicle_speed, accel)
        s.engine_speed += (rpm_target - s.engine_speed) * min(1.0, dt * 1.5)
        s.engine_speed = max(700.0, min(s.engine_speed, 7500.0))

        s.engine_load = max(5.0, min(s.accelerator_position * 1.2 + 8.0, 100.0))
        s.engine_temperature = self._approach(s.engine_temperature, 92.0 + s.engine_load * 0.15, dt, rate=0.05)
        s.engine_boost_pressure = self._approach(
            s.engine_boost_pressure, 100.0 + s.engine_load * 1.4, dt, rate=2.0
        )
        s.manifold_temperature = self._approach(
            s.manifold_temperature, 35.0 + s.engine_load * 0.4, dt, rate=0.3
        )
        s.engine_oil_pressure = self._approach(
            s.engine_oil_pressure, 250.0 + s.engine_speed * 0.07, dt, rate=10.0
        )

        s.instant_fuel_rate = self._approach(
            s.instant_fuel_rate, 1.5 + s.engine_load * 0.4, dt, rate=0.5
        )
        if s.vehicle_speed > 1.0 and s.instant_fuel_rate > 0.1:
            s.instant_fuel_economy = max(0.5, s.vehicle_speed / max(s.instant_fuel_rate, 0.1))
        else:
            s.instant_fuel_economy = 0.0

        if s.instant_fuel_rate > 0.0:
            s.fuel_level = max(0.0, s.fuel_level - (s.instant_fuel_rate / 3600.0) * dt * 0.05)

        if s.vehicle_speed > 0.0:
            s.total_vehicle_distance += (s.vehicle_speed / 3600.0) * dt
            s.engine_hour += dt / 3600.0

        s.battery_voltage = 27.5 + math.sin(s.engine_speed / 1000.0) * 0.4

        if self.is_ev_mode:
            s.motor_speed = s.engine_speed * 5.0
            s.motor_temp = self._approach(
                s.motor_temp, 30.0 + s.engine_load * 0.5, dt, rate=0.4
            )
            s.mcu_temp = self._approach(
                s.mcu_temp, 28.0 + s.engine_load * 0.3, dt, rate=0.3
            )
            s.pack_temp = self._approach(
                s.pack_temp, 25.0 + s.engine_load * 0.25, dt, rate=0.2
            )
            s.highest_temp = s.pack_temp + 2.5

            if s.hvesss1 == 0:
                s.battery_current = max(0.0, s.engine_load * 1.8)
                s.battery_voltage_ev = 580.0 - s.battery_current * 0.05
                s.soc = max(0.0, s.soc - (s.battery_current / 3600.0) * dt * 0.02)
            else:
                s.battery_current = -16.0 if s.hvesss1 == 1 else -120.0
                s.battery_voltage_ev = 600.0
                s.soc = min(100.0, s.soc + (-s.battery_current / 3600.0) * dt * 0.05)

        s.tec += abs(s.battery_current) * s.battery_voltage_ev / 3600.0 * dt / 1000.0
        s.vep15 = max(0.0, s.vep15 - dt * 0.001)

        jitter = (self.rng.random() - 0.5) * 0.05
        s.vehicle_speed = max(0.0, s.vehicle_speed + jitter)

    @staticmethod
    def _approach(current: float, target: float, dt: float, rate: float) -> float:
        """Approach the target through a first-order low-pass filter."""
        alpha = min(1.0, dt * rate)
        return current + (target - current) * alpha

    def _target_speed_from_accel(self, accel: float) -> float:
        if accel > 0:
            return min(180.0, self.state.vehicle_speed + accel * 60.0)
        if accel < 0:
            return max(0.0, self.state.vehicle_speed + accel * 80.0)
        return max(0.0, self.state.vehicle_speed - 0.5)

    def _rpm_target(self, speed: float, accel: float) -> float:
        idle = 800.0
        cruise = idle + speed * 18.0
        boost = max(0.0, accel) * 1500.0
        return idle + cruise + boost

    def as_signal_map(self) -> Mapping[str, float]:
        """Return a mapping of signal keys to physical values.

        Keys correspond one-to-one with `database.SIGNAL_DATABASE`.
        """
        s = self.state
        return {
            "vehicle_speed": s.vehicle_speed,
            "engine_speed": s.engine_speed,
            "accelerator_position": s.accelerator_position,
            "engine_load": s.engine_load,
            "engine_temperature": s.engine_temperature,
            "engine_oil_pressure": s.engine_oil_pressure,
            "engine_oil_level": s.engine_oil_level,
            "engine_boost_pressure": s.engine_boost_pressure,
            "manifold_temperature": s.manifold_temperature,
            "instant_fuel_rate": s.instant_fuel_rate,
            "instant_fuel_economy": s.instant_fuel_economy,
            "fuel_level": s.fuel_level,
            "engine_hour": s.engine_hour,
            "total_vehicle_distance": s.total_vehicle_distance,
            "battery_voltage": s.battery_voltage,
            "motor_speed": s.motor_speed,
            "motor_temp": s.motor_temp,
            "mcu_temp": s.mcu_temp,
            "battery_voltage_ev": s.battery_voltage_ev,
            "battery_current": s.battery_current,
            "soc": s.soc,
            "soh": s.soh,
            "highest_temp": s.highest_temp,
            "pack_temp": s.pack_temp,
            "current_ac": s.current_ac,
            "tec": s.tec,
            "vep15": s.vep15,
            "plug": float(s.plug),
            "hvesss1": float(s.hvesss1),
        }
