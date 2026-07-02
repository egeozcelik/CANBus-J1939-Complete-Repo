"""Exception hierarchy specific to the monitor."""


class MonitorError(Exception):
    """Base class for all monitor errors."""


class BusError(MonitorError):
    """CAN bus connection or receive errors."""
