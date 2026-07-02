"""J1939 simulator package.

A simulation application that generates SAE J1939-21 compliant CAN
frames on top of a hardware-agnostic CAN transport layer.
"""
from .protocol import J1939Id, Signal, Priority
from .database import PGN_DATABASE, SIGNAL_DATABASE, PgnDefinition
from .transport import CanTransport, TransportError
from .engine import SimulationEngine
from .model import VehicleModel

__version__ = "2.0.0"
__all__ = [
    "J1939Id",
    "Signal",
    "Priority",
    "PGN_DATABASE",
    "SIGNAL_DATABASE",
    "PgnDefinition",
    "CanTransport",
    "TransportError",
    "SimulationEngine",
    "VehicleModel",
]
