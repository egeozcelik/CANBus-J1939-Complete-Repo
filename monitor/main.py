"""J1939 monitor entry point.

See `python main.py --help` or `python -m j1939mon --help` for details.
"""
from j1939mon.app import run


if __name__ == "__main__":
    raise SystemExit(run())
