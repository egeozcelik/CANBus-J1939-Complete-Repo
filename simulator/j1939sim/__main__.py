"""Entry point for running the package directly via `python -m j1939sim`."""
from .app import run

if __name__ == "__main__":
    raise SystemExit(run())
