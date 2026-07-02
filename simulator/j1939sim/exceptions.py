"""Exception hierarchy specific to the simulator."""


class J1939SimError(Exception):
    """Base class for all simulator errors."""


class ProtocolError(J1939SimError):
    """Protocol-level errors (invalid PGN, out-of-range signal, etc.)."""


class TransportError(J1939SimError):
    """CAN transport layer errors (connection, send, hardware)."""


class ConfigError(J1939SimError):
    """Configuration file read/validation errors."""
