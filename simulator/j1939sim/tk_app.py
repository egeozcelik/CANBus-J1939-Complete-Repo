"""Tkinter desktop front-end for the J1939 simulator.

This is a self-contained, dependency-light alternative to the GTK
controller (`controller.py`). It exists so the simulator can be packaged
into a single-click Windows `.exe` with PyInstaller: Tkinter ships with
CPython, so no external GTK/MSYS2 runtime has to be bundled.

It reuses the entire hardware-agnostic backend unchanged:

    VehicleModel      -> signal values (vehicle dynamics)
    SimulationEngine  -> per-PGN broadcast scheduler
    CanTransport      -> python-can facade (defaults to the `virtual` bus)
    SIGNAL_DATABASE   -> signal metadata (units, scale)

By default it drives the built-in `virtual` python-can backend, so it
runs on any machine with zero CAN hardware -- ideal for demos and
screenshots. The interface selector lets you point it at real hardware
(Ixxat, Vector, Kvaser, Peak, SocketCAN) on a test bench.
"""
from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from typing import Callable

from .database import PGN_DATABASE, SIGNAL_DATABASE
from .engine import BroadcastEvent, SimulationEngine
from .model import VehicleModel
from .transport import CanTransport

# --- Theme ----------------------------------------------------------------
# Mirrors ui/style.css so the desktop app matches the GTK original.
BG = "#1a1d24"          # window background
CARD = "#22262f"        # panel background
CARD_HEAD = "#2c313c"   # panel header background
LOG_BG = "#0f1217"      # log panel background
FG = "#e6e6e6"          # primary text
MUTED = "#8b93a3"       # secondary text (signal names)
LOG_FG = "#c8d4e3"      # log text
YELLOW = "#ffd166"      # standard J1939 accent
TEAL = "#20c997"        # EV accent
AMBER = "#d39e00"       # start button
AMBER_HI = "#f1b100"
RED = "#b03a2e"         # exit button
RED_HI = "#c0392b"
BORDER = "#3b414e"
BTN = "#2c313c"
BTN_HI = "#353c4a"
GREEN = "#2ecc71"

# Interfaces offered in the selector. `virtual` needs no hardware.
INTERFACES = ["virtual", "ixxat", "vector", "kvaser", "pcan", "socketcan"]

# (signal key, display name) rows for each panel.
STANDARD_ROWS = [
    ("vehicle_speed", "Vehicle Speed"),
    ("engine_temperature", "Engine Coolant"),
    ("engine_boost_pressure", "Boost Pressure"),
    ("manifold_temperature", "Manifold Temp"),
    ("engine_oil_pressure", "Oil Pressure"),
    ("engine_oil_level", "Oil Level"),
    ("fuel_level", "Fuel Level"),
    ("instant_fuel_rate", "Fuel Rate"),
    ("instant_fuel_economy", "Fuel Economy"),
    ("battery_voltage", "Battery (VEP1)"),
    ("engine_hour", "Engine Hours"),
    ("total_vehicle_distance", "Total Distance"),
]

EV_ROWS = [
    ("engine_speed", "Engine Speed"),
    ("accelerator_position", "Accelerator"),
    ("engine_load", "Engine Load"),
    ("motor_speed", "Motor Speed"),
    ("motor_temp", "Motor Temp"),
    ("mcu_temp", "MCU Temp"),
    ("battery_voltage_ev", "Batt Voltage"),
    ("battery_current", "Batt Current"),
    ("soc", "State of Charge"),
    ("soh", "State of Health"),
    ("pack_temp", "Pack Temp"),
    ("highest_temp", "Highest Cell"),
    ("current_ac", "AC Current"),
    ("tec", "Energy Used"),
    ("vep15", "VEP15"),
]

MAX_LOG_LINES = 500
TICK_MS = 50            # engine tick period
REFRESH_MS = 150        # label refresh period
LOG_PUMP_MS = 120       # log flush period


def _unit(key: str) -> str:
    sig = SIGNAL_DATABASE.get(key)
    if not sig or not sig.unit or sig.unit == "state":
        return ""
    return "°C" if sig.unit == "degC" else sig.unit


def _fmt(key: str, value: float) -> str:
    """Format a physical value with sensible precision per signal."""
    unit = _unit(key)
    if key in ("engine_speed", "motor_speed", "vep15"):
        text = f"{value:,.0f}"
    elif key == "total_vehicle_distance":
        text = f"{value:,.1f}"
    elif key == "tec":
        text = f"{value:,.2f}"
    else:
        text = f"{value:.1f}"
    return f"{text} {unit}".strip()


class SimulatorApp:
    """Single-window Tkinter controller for the J1939 simulator."""

    def __init__(
        self,
        root: tk.Tk,
        transport_factory: Callable[[str], CanTransport],
        model: VehicleModel | None = None,
        autostart: bool = False,
        autodrive: bool = False,
    ) -> None:
        self.root = root
        self.transport_factory = transport_factory
        self.model = model or VehicleModel(is_ev_mode=True)

        self.transport: CanTransport | None = None
        self.engine: SimulationEngine | None = None
        self._running = False

        self._value_labels: dict[str, tk.Label] = {}
        self._events: deque[BroadcastEvent] = deque(maxlen=2000)
        self._log_mode = "frames"      # "frames" | "values"
        self._frame_count = 0
        self._fps = 0
        self._fps_window = 0
        self._fps_mark = time.monotonic()
        self._last_tick = 0.0
        self._auto = tk.BooleanVar(value=autodrive)
        self._auto_phase = 0.0
        self._log_lines = 0

        self._fonts()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)
        self._pump_log()
        if autostart:
            self.root.after(600, self._start)

    # -- fonts -------------------------------------------------------------
    def _fonts(self) -> None:
        self.f_ui = tkfont.Font(family="Segoe UI", size=10)
        self.f_ui_b = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_small = tkfont.Font(family="Segoe UI", size=9)
        self.f_title = tkfont.Font(family="Segoe UI Semibold", size=19, weight="bold")
        self.f_sub = tkfont.Font(family="Segoe UI", size=9)
        self.f_head = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_val = tkfont.Font(family="Consolas", size=12, weight="bold")
        self.f_log = tkfont.Font(family="Consolas", size=9)
        self.f_start = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        self.f_pill = tkfont.Font(family="Segoe UI", size=10, weight="bold")

    # -- layout ------------------------------------------------------------
    def _build(self) -> None:
        r = self.root
        r.title("J1939 Simulator")
        r.configure(bg=BG)
        r.grid_rowconfigure(1, weight=1)
        r.grid_columnconfigure(0, weight=0, minsize=270)
        r.grid_columnconfigure(1, weight=1)
        r.grid_columnconfigure(2, weight=0, minsize=300)

        self._build_header()
        self._build_standard_panel()
        self._build_log_panel()
        self._build_ev_panel()
        self._build_controls()

        # Size the window to fit its content at the current display DPI, and
        # forbid shrinking below that (so nothing is ever clipped).
        r.update_idletasks()
        r.minsize(r.winfo_reqwidth(), r.winfo_reqheight())

    def _build_header(self) -> None:
        head = tk.Frame(self.root, bg=BG)
        head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(14, 6))
        head.grid_columnconfigure(1, weight=1)

        left = tk.Frame(head, bg=BG)
        left.grid(row=0, column=0, sticky="w")
        tk.Label(
            left, text="CAN · SAE J1939 SIMULATOR", bg=BG, fg=FG, font=self.f_title
        ).pack(anchor="w")
        tk.Label(
            left,
            text="PC-side CAN traffic generator · python-can · hardware-agnostic",
            bg=BG, fg=MUTED, font=self.f_sub,
        ).pack(anchor="w")

        right = tk.Frame(head, bg=BG)
        right.grid(row=0, column=2, sticky="e")
        self.readout = tk.Label(
            right, text="Speed 0.0 km/h   ·   RPM 0", bg=BG, fg=FG, font=self.f_ui_b
        )
        self.readout.pack(anchor="e")
        self.status_pill = tk.Label(
            right, text="●  STOPPED", bg=BG, fg=MUTED, font=self.f_pill
        )
        self.status_pill.pack(anchor="e", pady=(2, 0))

    def _make_card(self, col: int, title: str, accent: str) -> tk.Frame:
        outer = tk.Frame(self.root, bg=BORDER)
        outer.grid(row=1, column=col, sticky="nsew", padx=(16 if col == 0 else 8,
                   16 if col == 2 else 8), pady=4)
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(inner, bg=CARD_HEAD)
        header.pack(fill="x")
        tk.Frame(header, bg=accent, width=4, height=26).pack(side="left")
        tk.Label(
            header, text=title, bg=CARD_HEAD, fg=FG, font=self.f_head
        ).pack(side="left", padx=8, pady=6)
        return inner

    def _add_rows(self, parent: tk.Frame, rows, accent: str) -> None:
        body = tk.Frame(parent, bg=CARD)
        body.pack(fill="both", expand=True, padx=10, pady=(4, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0)
        for i, (key, name) in enumerate(rows):
            tk.Label(
                body, text=name, bg=CARD, fg=MUTED, font=self.f_ui, anchor="w"
            ).grid(row=i, column=0, sticky="w", pady=1)
            val = tk.Label(
                body, text="—", bg=CARD, fg=accent, font=self.f_val, anchor="e"
            )
            val.grid(row=i, column=1, sticky="e", pady=1)
            self._value_labels[key] = val

    def _build_standard_panel(self) -> None:
        card = self._make_card(0, "STANDARD J1939", YELLOW)
        self._add_rows(card, STANDARD_ROWS, YELLOW)

    def _build_ev_panel(self) -> None:
        card = self._make_card(2, "EV · BATTERY", TEAL)
        self._add_rows(card, EV_ROWS, TEAL)

        toggles = tk.Frame(card, bg=CARD)
        toggles.pack(fill="x", padx=10, pady=(0, 10))
        self.plug_btn = tk.Button(
            toggles, text="PLUG · DISCONNECTED", font=self.f_ui_b,
            bg=BTN, fg=FG, activebackground=BTN_HI, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0, pady=7,
            command=self._toggle_plug,
        )
        self.plug_btn.pack(fill="x", pady=(0, 6))
        self.ac_btn = tk.Button(
            toggles, text="AC CHARGING · OFF", font=self.f_ui_b,
            bg=BTN, fg=FG, activebackground=BTN_HI, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0, pady=7,
            command=self._toggle_ac,
        )
        self.ac_btn.pack(fill="x")
        self._plug = False
        self._ac = False

    def _build_log_panel(self) -> None:
        card = self._make_card(1, "CAN TRAFFIC", "#5b8def")

        bar = tk.Frame(card, bg=CARD)
        bar.pack(fill="x", padx=10, pady=(6, 4))
        self.btn_frames = tk.Button(
            bar, text="Frames", font=self.f_ui, relief="flat", bd=0,
            highlightthickness=0, padx=14, pady=5, command=lambda: self._set_mode("frames"),
        )
        self.btn_frames.pack(side="left")
        self.btn_values = tk.Button(
            bar, text="Values", font=self.f_ui, relief="flat", bd=0,
            highlightthickness=0, padx=14, pady=5, command=lambda: self._set_mode("values"),
        )
        self.btn_values.pack(side="left", padx=(6, 0))
        tk.Button(
            bar, text="Clear", font=self.f_ui, relief="flat", bd=0,
            highlightthickness=0, padx=14, pady=5, bg=BTN, fg=FG,
            activebackground=BTN_HI, activeforeground=FG, command=self._clear_log,
        ).pack(side="left", padx=(6, 0))
        self.stats = tk.Label(
            bar, text="frames 0 · 0/s", bg=CARD, fg=MUTED, font=self.f_small
        )
        self.stats.pack(side="right")

        wrap = tk.Frame(card, bg=BORDER)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log = tk.Text(
            wrap, bg=LOG_BG, fg=LOG_FG, font=self.f_log, relief="flat", bd=0,
            highlightthickness=0, wrap="none", padx=8, pady=6, state="disabled",
            insertbackground=LOG_FG,
        )
        scroll = tk.Scrollbar(wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        self.log.tag_configure("ok", foreground=LOG_FG)
        self.log.tag_configure("sys", foreground=YELLOW)
        self.log.tag_configure("err", foreground=RED_HI)
        self._set_mode("frames")
        self._append("[SYSTEM] Ready. Press START SIMULATION to broadcast.", "sys")

    def _build_controls(self) -> None:
        bar = tk.Frame(self.root, bg=CARD_HEAD)
        bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(6, 14))
        for c in range(6):
            bar.grid_columnconfigure(c, weight=0)
        bar.grid_columnconfigure(2, weight=1)

        # Interface selector
        iface_box = tk.Frame(bar, bg=CARD_HEAD)
        iface_box.grid(row=0, column=0, sticky="w", padx=10, pady=10)
        tk.Label(iface_box, text="Interface", bg=CARD_HEAD, fg=MUTED,
                 font=self.f_small).pack(anchor="w")
        self.iface_var = tk.StringVar(value="virtual")
        self.iface_menu = tk.OptionMenu(iface_box, self.iface_var, *INTERFACES)
        self.iface_menu.configure(
            bg=BTN, fg=FG, activebackground=BTN_HI, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0, font=self.f_ui, width=10,
            anchor="w",
        )
        self.iface_menu["menu"].configure(bg=CARD, fg=FG,
                                          activebackground=AMBER, activeforeground=BG)
        self.iface_menu.pack(anchor="w")

        # Throttle / brake (hold to apply) + auto-drive
        drive = tk.Frame(bar, bg=CARD_HEAD)
        drive.grid(row=0, column=1, sticky="w", padx=10)
        self.throttle_btn = tk.Button(
            drive, text="▲  THROTTLE", font=self.f_ui_b, bg=BTN, fg=FG,
            activebackground=GREEN, activeforeground=BG, relief="flat", bd=0,
            highlightthickness=0, padx=16, pady=9,
        )
        self.throttle_btn.pack(side="left")
        self.throttle_btn.bind("<ButtonPress-1>", lambda e: self._throttle(True))
        self.throttle_btn.bind("<ButtonRelease-1>", lambda e: self._pedal_release())
        self.brake_btn = tk.Button(
            drive, text="▼  BRAKE", font=self.f_ui_b, bg=BTN, fg=FG,
            activebackground=RED_HI, activeforeground=FG, relief="flat", bd=0,
            highlightthickness=0, padx=16, pady=9,
        )
        self.brake_btn.pack(side="left", padx=(8, 0))
        self.brake_btn.bind("<ButtonPress-1>", lambda e: self._throttle(False))
        self.brake_btn.bind("<ButtonRelease-1>", lambda e: self._pedal_release())
        tk.Checkbutton(
            drive, text="Auto-drive", variable=self._auto, bg=CARD_HEAD, fg=MUTED,
            selectcolor=CARD, activebackground=CARD_HEAD, activeforeground=FG,
            font=self.f_ui, bd=0, highlightthickness=0,
        ).pack(side="left", padx=(12, 0))

        # Start / Exit
        self.start_btn = tk.Button(
            bar, text="START SIMULATION", font=self.f_start, bg=AMBER, fg=BG,
            activebackground=AMBER_HI, activeforeground=BG, relief="flat", bd=0,
            highlightthickness=0, padx=22, pady=10, command=self._toggle_run,
        )
        self.start_btn.grid(row=0, column=3, sticky="e", padx=(10, 6), pady=10)
        tk.Button(
            bar, text="EXIT", font=self.f_ui_b, bg=RED, fg="#fafafa",
            activebackground=RED_HI, activeforeground="#fafafa", relief="flat", bd=0,
            highlightthickness=0, padx=18, pady=10, command=self._on_exit,
        ).grid(row=0, column=4, sticky="e", padx=(0, 10), pady=10)

    # -- log helpers -------------------------------------------------------
    def _set_mode(self, mode: str) -> None:
        self._log_mode = mode
        sel = {"bg": AMBER, "fg": BG, "activebackground": AMBER_HI, "activeforeground": BG}
        uns = {"bg": BTN, "fg": FG, "activebackground": BTN_HI, "activeforeground": FG}
        self.btn_frames.configure(**(sel if mode == "frames" else uns))
        self.btn_values.configure(**(sel if mode == "values" else uns))

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._log_lines = 0

    def _append(self, text: str, tag: str = "ok") -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self._log_lines += 1
        if self._log_lines > MAX_LOG_LINES:
            trim = self._log_lines - MAX_LOG_LINES
            self.log.delete("1.0", f"{trim + 1}.0")
            self._log_lines -= trim
        self.log.see("end")
        self.log.configure(state="disabled")

    # -- input handlers ----------------------------------------------------
    def _throttle(self, up: bool) -> None:
        if not self._running:
            return
        if up:
            self.model.request_accelerate(0.85)
        else:
            self.model.request_decelerate(0.85)

    def _pedal_release(self) -> None:
        self.model.release_pedal()

    def _toggle_plug(self) -> None:
        self._plug = not self._plug
        self.model.set_plug_state(self._plug)
        if self._plug:
            self.plug_btn.configure(text="PLUG · CONNECTED", bg=TEAL, fg=BG)
        else:
            self.plug_btn.configure(text="PLUG · DISCONNECTED", bg=BTN, fg=FG)
            self._ac = False
            self.ac_btn.configure(text="AC CHARGING · OFF", bg=BTN, fg=FG)
        self._log_input(f"Plug {'CONNECTED' if self._plug else 'DISCONNECTED'}")

    def _toggle_ac(self) -> None:
        self._ac = not self._ac
        self.model.set_ac_charging(self._ac)
        active = self.model.state.hvesss1 == 1
        self._ac = active
        if active:
            self.ac_btn.configure(text="AC CHARGING · ON", bg=TEAL, fg=BG)
        else:
            self.ac_btn.configure(text="AC CHARGING · OFF", bg=BTN, fg=FG)
        self._log_input(f"AC charging {'ON' if active else 'OFF (plug first)'}")

    def _log_input(self, msg: str) -> None:
        self._append(f"[INPUT] {msg}", "sys")

    # -- run control -------------------------------------------------------
    def _toggle_run(self) -> None:
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        iface = self.iface_var.get()
        try:
            self.transport = self.transport_factory(iface)
            self.transport.connect()
        except Exception as exc:  # noqa: BLE001 - surfaced to the log panel
            self._append(f"[ERROR] Failed to open CAN bus ({iface}): {exc}", "err")
            self.transport = None
            return

        self.engine = SimulationEngine(
            transport=self.transport,
            signal_provider=self.model.as_signal_map,
            listener=self._on_event,
        )
        self.engine.start()
        self._running = True
        self._frame_count = 0
        self._last_tick = time.monotonic()
        self.start_btn.configure(text="STOP SIMULATION", bg=RED, fg="#fafafa",
                                 activebackground=RED_HI)
        self.status_pill.configure(text="●  RUNNING", fg=GREEN)
        self.iface_menu.configure(state="disabled")
        self._append(
            f"[SYSTEM] Simulation started · interface={self.transport.interface} "
            f"· channel={self.transport.channel} · {len(PGN_DATABASE)} PGNs", "sys")
        self._tick()
        self._refresh()

    def _stop(self) -> None:
        self._running = False
        if self.engine:
            self.engine.stop()
            self.engine = None
        if self.transport:
            self.transport.disconnect()
            self.transport = None
        self.start_btn.configure(text="START SIMULATION", bg=AMBER, fg=BG,
                                 activebackground=AMBER_HI)
        self.status_pill.configure(text="●  STOPPED", fg=MUTED)
        self.iface_menu.configure(state="normal")
        self.readout.configure(text="Speed 0.0 km/h   ·   RPM 0")
        for lbl in self._value_labels.values():
            lbl.configure(text="—")
        self._append("[SYSTEM] Simulation stopped.", "sys")

    # -- periodic loops ----------------------------------------------------
    def _tick(self) -> None:
        if not self._running or self.engine is None:
            return
        now = time.monotonic()
        dt = now - self._last_tick if self._last_tick else TICK_MS / 1000.0
        dt = max(0.001, min(dt, 0.5))
        self._last_tick = now

        if self._auto.get():
            self._auto_phase += dt
            # Slow 24 s throttle sweep so the dashboard stays alive on its own.
            import math
            wave = math.sin(self._auto_phase * (2 * math.pi / 24.0))
            if wave > 0.1:
                self.model.request_accelerate(min(1.0, wave))
            elif wave < -0.3:
                self.model.request_decelerate(min(1.0, -wave))
            else:
                self.model.release_pedal()

        self.model.step(dt)
        self.engine.tick()
        self.root.after(TICK_MS, self._tick)

    def _refresh(self) -> None:
        if not self._running:
            return
        values = self.model.as_signal_map()
        for key, lbl in self._value_labels.items():
            if key in values:
                lbl.configure(text=_fmt(key, values[key]))
        self.readout.configure(
            text=f"Speed {values['vehicle_speed']:.1f} km/h   ·   "
                 f"RPM {values['engine_speed']:.0f}")
        self.root.after(REFRESH_MS, self._refresh)

    def _on_event(self, event: BroadcastEvent) -> None:
        # Called on the Tk thread (from _tick); only buffer here.
        self._events.append(event)
        self._frame_count += 1
        self._fps_window += 1

    def _pump_log(self) -> None:
        # Drain buffered broadcast events into the Text widget at a steady rate.
        n = len(self._events)
        for _ in range(n):
            self._append(self._format_event(self._events.popleft()))

        now = time.monotonic()
        if now - self._fps_mark >= 1.0:
            self._fps = int(self._fps_window / (now - self._fps_mark))
            self._fps_window = 0
            self._fps_mark = now
        self.stats.configure(text=f"frames {self._frame_count:,} · {self._fps}/s")
        self.root.after(LOG_PUMP_MS, self._pump_log)

    def _format_event(self, e: BroadcastEvent) -> str:
        flag = "OK " if e.success else "ERR"
        if self._log_mode == "frames":
            return (f"[TX {flag}] PGN=0x{e.pgn_definition.pgn:04X} "
                    f"({e.pgn_definition.name}) ID=0x{e.can_id:08X} "
                    f"DATA={e.data.hex(' ').upper()}")
        parts = []
        for key, value in e.signal_values.items():
            parts.append(f"{key}={_fmt(key, value)}")
        body = ", ".join(parts) if parts else "(no mapped signals)"
        return f"[TX {flag}] {e.pgn_definition.name}: {body}"

    def _on_exit(self) -> None:
        if self._running:
            self._stop()
        self.root.destroy()


def _build_transport_factory() -> Callable[[str], CanTransport]:
    def factory(interface: str) -> CanTransport:
        channel = "demo" if interface == "virtual" else 0
        return CanTransport(interface=interface, channel=channel, bitrate=250_000)
    return factory


def _enable_dpi_awareness() -> None:
    """Render crisply on scaled Windows displays (no-op elsewhere)."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    import os
    _enable_dpi_awareness()
    autostart = os.environ.get("J1939_AUTOSTART", "") not in ("", "0", "false", "False")
    autodrive = os.environ.get("J1939_AUTODRIVE", "") not in ("", "0", "false", "False")
    root = tk.Tk()
    SimulatorApp(
        root,
        transport_factory=_build_transport_factory(),
        autostart=autostart,
        autodrive=autodrive,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
