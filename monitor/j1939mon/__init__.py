"""J1939 monitor package.

A standalone Linux application that receives SAE J1939 traffic over a
python-can interface (typically SocketCAN), decodes the payloads into
physical values and displays them on a GTK dashboard or the console.
"""
from .protocol import extract_pgn
from .database import PGN_DECODERS, SignalSpec
from .decoder import DecodedSignal, decode_frame
from .receiver import CanReceiver

__version__ = "1.0.0"
__all__ = [
    "extract_pgn",
    "PGN_DECODERS",
    "SignalSpec",
    "DecodedSignal",
    "decode_frame",
    "CanReceiver",
]
