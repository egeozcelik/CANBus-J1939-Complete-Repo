"""YAML-based configuration loader.

A simple contract:
    bus:
      interface: ixxat | virtual | socketcan | ...
      channel: 0 | "vcan0" | ...
      bitrate: 250000
      send_timeout: 0.1
      max_retries: 3
    simulation:
      tick_interval_ms: 50
      source_address: 0x01
      ev_mode: true
    logging:
      level: INFO
      file: null

Missing fields are filled with sensible defaults so there are no surprises.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import ConfigError


logger = logging.getLogger(__name__)


@dataclass
class BusConfig:
    interface: str = "virtual"
    channel: str | int = 0
    bitrate: int = 250_000
    send_timeout: float = 0.1
    max_retries: int = 3
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulationConfig:
    tick_interval_ms: int = 50
    source_address: int | None = None
    ev_mode: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str | None = None


@dataclass
class AppConfig:
    bus: BusConfig = field(default_factory=BusConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(path: str | Path | None) -> AppConfig:
    """Read the YAML file and return it as an `AppConfig`.

    Defaults are returned when `path` is None or the file does not exist.
    If the `pyyaml` package is not installed, the user gets a clear
    warning instead of an ImportError.
    """
    if path is None:
        return AppConfig()

    config_path = Path(path)
    if not config_path.exists():
        logger.warning("Config file not found: %s -> falling back to defaults", config_path)
        return AppConfig()

    try:
        import yaml
    except ImportError:
        logger.warning(
            "pyyaml is not installed. %s will be skipped and defaults used. "
            "You can override via CLI arguments (--interface, --channel, --bitrate).",
            config_path,
        )
        return AppConfig()

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path}: top level must be a mapping")

    bus_raw = raw.get("bus", {}) or {}
    sim_raw = raw.get("simulation", {}) or {}
    log_raw = raw.get("logging", {}) or {}

    bus_known = {"interface", "channel", "bitrate", "send_timeout", "max_retries"}
    bus_extra = {k: v for k, v in bus_raw.items() if k not in bus_known}

    return AppConfig(
        bus=BusConfig(
            interface=bus_raw.get("interface", "virtual"),
            channel=bus_raw.get("channel", 0),
            bitrate=int(bus_raw.get("bitrate", 250_000)),
            send_timeout=float(bus_raw.get("send_timeout", 0.1)),
            max_retries=int(bus_raw.get("max_retries", 3)),
            extra=bus_extra,
        ),
        simulation=SimulationConfig(
            tick_interval_ms=int(sim_raw.get("tick_interval_ms", 50)),
            source_address=_optional_int(sim_raw.get("source_address")),
            ev_mode=bool(sim_raw.get("ev_mode", True)),
        ),
        logging=LoggingConfig(
            level=str(log_raw.get("level", "INFO")).upper(),
            file=log_raw.get("file"),
        ),
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        return int(value, 0)
    return int(value)
