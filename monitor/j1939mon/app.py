"""Application orchestrator.

Parses the CLI, builds a receiver factory and dispatches to the GTK
dashboard or the headless console renderer. GTK imports happen lazily
so headless mode runs on systems without PyGObject.
"""
from __future__ import annotations

import argparse
import functools
import logging

from .logging_setup import configure_logging
from .receiver import CanReceiver

logger = logging.getLogger(__name__)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SAE J1939 CAN bus monitor and live dashboard.",
        epilog=(
            "SocketCAN bitrate is configured on the link, not by this "
            "application: sudo ip link set can0 up type can bitrate 250000"
        ),
    )
    parser.add_argument(
        "--interface",
        type=str,
        default="socketcan",
        help="python-can interface: socketcan, virtual, pcan, ... (default: socketcan)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default="can0",
        help="CAN channel, e.g. can0, vcan0 (default: can0)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Print decoded values to the console instead of opening the GUI.",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Open the dashboard fullscreen (kiosk mode for embedded panels).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="DEBUG | INFO | WARNING | ERROR",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    configure_logging(level=args.log_level.upper())
    logger.info(
        "Starting J1939 monitor (interface=%s, channel=%s)",
        args.interface,
        args.channel,
    )

    receiver_factory = functools.partial(
        CanReceiver,
        interface=args.interface,
        channel=args.channel,
    )

    if args.headless:
        from .headless import HeadlessMonitor

        return HeadlessMonitor(receiver_factory).run()

    from .controller import MonitorController

    controller = MonitorController(
        receiver_factory=receiver_factory,
        fullscreen=args.fullscreen,
    )
    controller.run()
    return 0
