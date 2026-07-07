# J1939 Simulator

A PC-side **SAE J1939 CAN traffic generator** with a GTK 3 control panel and a fully scriptable headless mode. It emulates the frames a heavy-duty (or electric) vehicle broadcasts on its CAN bus, so receiver devices — on-board units, telematics gateways, dashboards, data loggers — can be validated on the bench instead of in the field.

## Windows: one-click executable

GTK 3 is Linux-first and awkward to install on Windows, so the project ships a **self-contained Windows desktop build** (Tkinter) that reuses the *same* backend — protocol, signal database, vehicle-dynamics model and broadcast engine — packaged into a **single double-click `.exe` with no Python, GTK or CAN driver to install**:

```powershell
cd simulator
build_windows.bat            # produces dist\J1939-Simulator.exe
dist\J1939-Simulator.exe     # double-click it, then press START SIMULATION
```

It defaults to the hardware-free `virtual` CAN bus, so it runs on any PC. Hold **THROTTLE** / **BRAKE** (or tick **Auto-drive**) to move the vehicle model; switch the log between raw **Frames** and decoded **Values**; flip **Plug** / **AC Charging** to exercise the EV signals. To transmit on a real bench, pick **ixxat** (or vector / kvaser / pcan / socketcan) from the Interface selector — see the [end-to-end bench](../README.md#system-architecture--the-end-to-end-bench).

<p align="center">
  <img src="../docs/images/can-generator.gif" alt="J1939 Simulator generating CAN traffic live" width="860"/>
</p>
<p align="center"><i>The desktop app generating live J1939 traffic over the virtual bus, in the decoded "Values" view.</i></p>

<p align="center">
  <img src="../docs/images/simulator-app.png" alt="J1939 Simulator broadcasting raw CAN frames over the virtual bus" width="860"/>
</p>
<p align="center"><i>Live broadcast over the virtual bus — 20 PGNs streaming as raw 29-bit J1939 frames, driven by the vehicle-dynamics model.</i></p>

<p align="center">
  <img src="../docs/images/simulator-app-values.png" alt="J1939 Simulator decoded value view with EV pack charging" width="860"/>
</p>
<p align="center"><i>The same traffic in decoded <b>Values</b> view, with the EV pack charging (plug connected, AC charging on — note the negative pack current).</i></p>

## Features

- **20 PGNs / 30 signals** out of the box: standard J1939-71 parameters (EEC1, EEC2, CCVS, LFE, ET1, EFL/P1, VEP1, HOURS, DD, VD, IC1) plus EV battery/charging PGNs (HVESDS1, HVESSS1, EVSE, SOH, TEC, VEP15) and proprietary EV motor/battery groups.
- **Protocol-accurate**: 29-bit extended identifiers composed per SAE J1939-21, correct PDU1/PDU2 handling, little-endian signal packing with scale/offset/range clamping.
- **Vehicle dynamics model**: signal values are driven by a first-order dynamic model (throttle raises rpm, rpm raises speed and fuel rate, SOC drains and recharges), not static numbers.
- **Hardware-agnostic**: any `python-can` backend — Ixxat, Vector, Kvaser, Peak, SocketCAN — or the built-in `virtual` loop-back for hardware-free operation and CI.
- **Per-PGN scheduling**: each PGN broadcasts on its own period (20 ms for EEC1 up to 5 s for SOH), mirroring real bus timing.
- **26 unit tests** covering protocol primitives, database consistency and the scheduler.

## Architecture

```
main.py / python -m j1939sim
        │
        ▼
app.py ──── argparse CLI, config loading, GUI/headless dispatch
        │
        ├── GUI:      controller.py ── GTK window (ui/simulator.glade + ui/style.css)
        │                   │          buttons/switches -> model inputs
        │                   │          GLib.timeout_add -> engine.tick()
        │                   ▼
        └── headless: engine.py ────── per-PGN broadcast scheduler
                            │          packs signals into 8-byte frames
                            │
              model.py ─────┤          vehicle dynamics -> signal values
              database.py ──┤          PGN_DATABASE + SIGNAL_DATABASE (single source of truth)
              protocol.py ──┤          J1939Id + Signal encode/decode primitives
                            ▼
              transport.py ─────────── python-can facade (retry, timeout, lifecycle)
```

Data flows one way: UI (or the headless loop) steps the **model**, the **engine** reads the model's signal map on each tick, packs every due PGN into an 8-byte frame using the **database** definitions and the **protocol** primitives, and sends it through the **transport**. After each broadcast a `BroadcastEvent` is emitted back to the UI log panel.

| Module | Responsibility |
|---|---|
| `j1939sim/app.py` | CLI parsing, config resolution, GUI/headless orchestration |
| `j1939sim/config.py` | `config.yaml` loader with dataclasses and safe defaults |
| `j1939sim/protocol.py` | `J1939Id` (29-bit ID composition) and `Signal` (bit-level encode/decode) |
| `j1939sim/database.py` | `PGN_DATABASE` and `SIGNAL_DATABASE` definitions |
| `j1939sim/model.py` | `VehicleModel` — dynamic signal value generation |
| `j1939sim/engine.py` | `SimulationEngine` — per-PGN periodic scheduler |
| `j1939sim/transport.py` | `CanTransport` — python-can facade with retry/backoff |
| `j1939sim/controller.py` | GTK controller binding the UI to the engine |
| `j1939sim/logging_setup.py` | Console + rotating-file logging |
| `j1939sim/exceptions.py` | Typed error hierarchy |

## Installation

### Linux

```bash
sudo apt install python3-gi gir1.2-gtk-3.0        # GTK 3 + PyGObject (GUI mode)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Windows

The [one-click executable](#windows-one-click-executable) above needs nothing installed. To run the desktop app from source, or to rebuild the `.exe`:

```powershell
pip install python-can pyinstaller     # PyYAML optional, only for config files
python desktop_app.py                  # run the Tkinter desktop app from source
build_windows.bat                      # or repackage dist\J1939-Simulator.exe
```

The GTK control panel (`python main.py`) is Linux-first; on Windows use the Tkinter desktop app above. Headless mode needs only `python-can`:

```powershell
python main.py --headless --interface virtual --channel demo
```

## Running

### GUI

```bash
python main.py
```

Press **Start Simulation** to connect the configured bus and begin broadcasting. The UP/DOWN buttons apply throttle/brake to the vehicle model; the plug and AC-charging switches drive the EV charging signals. The log panel can show raw frames (`Can Data Log`) or decoded physical values (`Value Log`).

### Headless

```bash
python main.py --headless --interface virtual --channel demo
```

Runs the same engine without a GUI until Ctrl+C — useful for soak tests, CI pipelines, or feeding the companion [monitor](../monitor/) application.

### CLI flags

| Flag | Description | Default |
|---|---|---|
| `-c, --config` | Path to YAML config | `config.yaml` |
| `--interface` | python-can interface (overrides config) | from config (`virtual`) |
| `--channel` | CAN channel (overrides config) | from config (`0`) |
| `--bitrate` | CAN bitrate (overrides config) | from config (`250000`) |
| `--log-level` | DEBUG / INFO / WARNING / ERROR | from config (`INFO`) |
| `--headless` | Run without the GUI | off |

### config.yaml

```yaml
bus:
  interface: "virtual"     # ixxat | vector | kvaser | pcan | socketcan | virtual
  channel: 0               # e.g. "vcan0" for socketcan
  bitrate: 250000
simulation:
  tick_interval_ms: 50
  ev_mode: true
logging:
  level: "INFO"
```

For real hardware, set e.g. `interface: "ixxat"`, `channel: 0` — or on Linux `interface: "socketcan"`, `channel: "can0"` after `sudo ip link set can0 up type can bitrate 250000`.

## Testing

```bash
pip install pytest
python -m pytest
```

All 26 tests run hardware-free: protocol round-trips against known-good CAN IDs (`0x18F00401` for EEC1), signal bit-packing with known raw values, database consistency (no bit overlaps, all signals fit 8 bytes), and scheduler behavior over the `virtual` bus.

## Extending

### Adding a new PGN and signal

1. Add the PGN to `PGN_DATABASE` in `j1939sim/database.py`:

```python
0xFEEB: PgnDefinition(
    pgn=0xFEEB,
    name="CI",
    description="Component Identification",
    transmission_rate_ms=1000,
    source_address=0x00,
),
```

2. Add its signals to `SIGNAL_DATABASE` (bit positions are zero-indexed; "byte 2" in J1939-71 means `start_bit=8`):

```python
"my_signal": Signal(
    spn=1234,
    name="My Signal",
    pgn=0xFEEB,
    start_bit=8,
    bit_length=16,
    scale=0.05,
    offset=0.0,
    unit="V",
),
```

3. Provide a value for the new key in `VehicleModel.as_signal_map()` (`j1939sim/model.py`). The scheduler picks up the new PGN automatically on the next start.

4. To display it in the GUI, add a `GtkLabel` with a unique id to `ui/simulator.glade` and map it in `_LABEL_MAP` in `j1939sim/controller.py`.

The database tests (`tests/test_database.py`) will immediately flag bit overlaps or out-of-frame signals.

### Editing the UI

The layout lives in `ui/simulator.glade` (editable with [Glade](https://glade.gnome.org/) 3.40+) and the theme in `ui/style.css`. Widget ids referenced by the controller are listed in `_LABEL_MAP` and `_wire_widgets()` in `j1939sim/controller.py`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Failed to open CAN bus` | Interface/channel mismatch, or hardware driver not installed. Try `--interface virtual` to isolate. |
| `ImportError: gi` | PyGObject/GTK missing — install `python3-gi`, or use `--headless`. |
| No frames on `socketcan` | Bring the link up first: `sudo ip link set can0 up type can bitrate 250000`. |
| Tx queue warnings in the log | Bus overloaded or no receiver ACKing frames; reduce tick rate or check wiring/termination. |

## Linux smoke checklist

```bash
sudo modprobe vcan && sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0
python main.py --interface socketcan --channel vcan0      # GUI opens, Start Simulation
candump vcan0                                             # frames visible
```
