"""J1939 simulator entry point.

See `python main.py --help` or `python -m j1939sim --help` for details.
"""
from j1939sim.app import run


if __name__ == "__main__":
    raise SystemExit(run())
