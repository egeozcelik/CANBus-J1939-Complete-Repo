"""Windows desktop entry point (Tkinter GUI).

This is the script PyInstaller freezes into the single-click `.exe`.
It launches the Tkinter front-end, which defaults to the hardware-free
`virtual` CAN backend so it runs anywhere with no drivers installed.

    python desktop_app.py          # run from source
    build_windows.bat              # package into dist/J1939-Simulator.exe

Any unexpected startup error is written to `j1939-simulator-error.log`
next to the executable and shown in a dialog, so a packaged build never
fails silently on an end user's machine.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _crash(exc: BaseException) -> None:
    report = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        (base / "j1939-simulator-error.log").write_text(report, encoding="utf-8")
    except Exception:
        pass
    try:
        import tkinter.messagebox as mb
        mb.showerror("J1939 Simulator - startup error", report)
    except Exception:
        print(report, file=sys.stderr)


def _main() -> int:
    from j1939sim.tk_app import main
    return main()


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - last-resort crash reporter
        _crash(exc)
        raise SystemExit(1)
