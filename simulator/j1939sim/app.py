"""Application orchestrator.

Boots the controller according to the configuration when invoked from
the CLI or via `python -m j1939sim`.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import AppConfig, load_config
from .logging_setup import configure_logging
from .model import VehicleModel
from .transport import CanTransport

logger = logging.getLogger(__name__)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SAE J1939 CAN traffic simulator.",
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default="config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--interface",
        type=str,
        default=None,
        help="CAN interface (overrides config): ixxat, virtual, socketcan, ...",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="CAN channel (overrides config)",
    )
    parser.add_argument(
        "--bitrate",
        type=int,
        default=None,
        help="CAN bitrate (overrides config)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="DEBUG | INFO | WARNING | ERROR",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the engine without opening the GUI (for automation).",
    )
    return parser


def _resolve_paths() -> tuple[Path, Path]:
    """Resolve the Glade and CSS asset paths relative to the project root."""
    project_root = Path(__file__).resolve().parent.parent
    return (
        project_root / "ui" / "simulator.glade",
        project_root / "ui" / "style.css",
    )


def _build_transport_factory(config: AppConfig):
    bus_cfg = config.bus

    def factory() -> CanTransport:
        return CanTransport(
            interface=bus_cfg.interface,
            channel=bus_cfg.channel,
            bitrate=bus_cfg.bitrate,
            send_timeout=bus_cfg.send_timeout,
            max_retries=bus_cfg.max_retries,
            **bus_cfg.extra,
        )

    return factory


def run(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.interface:
        config.bus.interface = args.interface
    if args.channel:
        config.bus.channel = args.channel
    if args.bitrate:
        config.bus.bitrate = args.bitrate
    if args.log_level:
        config.logging.level = args.log_level.upper()

    configure_logging(level=config.logging.level, log_file=config.logging.file)
    logger.info("Starting J1939 simulator (interface=%s, channel=%s, bitrate=%d)",
                config.bus.interface, config.bus.channel, config.bus.bitrate)

    if args.headless:
        return _run_headless(config)
    return _run_gui(config)


def _run_gui(config: AppConfig) -> int:
    glade_path, css_path = _resolve_paths()
    if not glade_path.exists():
        logger.error("Glade file not found: %s", glade_path)
        return 1

    from .controller import AppController

    controller = AppController(
        glade_path=glade_path,
        css_path=css_path,
        transport_factory=_build_transport_factory(config),
        model=VehicleModel(is_ev_mode=config.simulation.ev_mode),
        tick_interval_ms=config.simulation.tick_interval_ms,
        source_address_override=config.simulation.source_address,
    )
    controller.run()
    return 0


def _run_headless(config: AppConfig) -> int:
    """Headless mode: run the engine without a GUI until Ctrl+C."""
    import time
    from .engine import SimulationEngine

    factory = _build_transport_factory(config)
    transport = factory()
    transport.connect()
    model = VehicleModel(is_ev_mode=config.simulation.ev_mode)
    engine = SimulationEngine(
        transport=transport,
        signal_provider=model.as_signal_map,
        source_address=config.simulation.source_address,
    )

    engine.start()
    tick_dt = config.simulation.tick_interval_ms / 1000.0

    logger.info("Headless mode active. Press Ctrl+C to exit.")
    try:
        while True:
            model.step(tick_dt)
            engine.tick()
            time.sleep(tick_dt)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
    finally:
        engine.stop()
        transport.disconnect()

    return 0
