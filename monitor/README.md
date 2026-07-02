# J1939 Monitor

A standalone **SAE J1939 receiver and live dashboard** for Linux, designed for embedded targets (on-board computers, in-vehicle tablets, industrial panels) that consume J1939 traffic over **SocketCAN**. It listens on a CAN interface with an event-driven `python-can` notifier, extracts PGNs from 29-bit extended identifiers with spec-correct PDU1/PDU2 logic, decodes payloads through a declarative signal table and renders the physical values on a GTK 3 dashboard — or on the console in headless mode.

## Features

- **17 supported PGNs**: standard J1939-71 engine/vehicle parameters plus EV battery and charging groups (full table below).
- **Event-driven reception**: a `can.Notifier` background thread delivers frames the moment they arrive — no polling, no shelling out.
- **UI-safe threading**: decoded updates are coalesced under a lock and flushed to GTK with a single pending `GLib.idle_add`, so a busy bus cannot flood the main loop.
- **Headless mode**: prints a per-second snapshot of all decoded values; needs no GTK and runs on any `python-can` backend.
- **Kiosk support**: `--fullscreen` for embedded panels.
- **31 unit tests** covering PGN extraction and every decode formula with known payloads.

## Architecture

```
main.py / python -m j1939mon
        │
        ▼
app.py ──── argparse CLI, GUI/headless dispatch (lazy GTK import)
        │
        ├── GUI:      controller.py ── GTK window (ui/monitor.glade + ui/style.css)
        │                   ▲          coalesced updates via GLib.idle_add
        │                   │          1 Hz watchdog -> status panel
        └── headless: headless.py ──── 1 Hz console snapshots
                            ▲
              receiver.py ──┴───────── can.Bus + can.Notifier (background thread)
                    │                  filters extended IDs
                    ▼
              protocol.py ──────────── 29-bit ID -> 18-bit PGN (PDU1/PDU2)
              database.py ──────────── PGN_DECODERS declarative decode table
              decoder.py  ──────────── applies the table to 8-byte payloads
```

The notifier thread never touches GTK. Each incoming frame is filtered (`is_extended_id`), its PGN extracted, its payload decoded into `DecodedSignal` objects and handed to the consumer callback. The GTK controller merges these into a pending dictionary and schedules at most one idle flush at a time; the headless renderer simply keeps the latest snapshot and prints it once per second.

| Module | Responsibility |
|---|---|
| `j1939mon/app.py` | CLI parsing, GUI/headless orchestration |
| `j1939mon/protocol.py` | PGN extraction from 29-bit identifiers |
| `j1939mon/database.py` | `PGN_DECODERS` — declarative per-signal decode table |
| `j1939mon/decoder.py` | Applies the table to a frame, formats values |
| `j1939mon/receiver.py` | `CanReceiver` — bus lifecycle + notifier listener |
| `j1939mon/controller.py` | GTK dashboard controller |
| `j1939mon/headless.py` | Console snapshot renderer |
| `j1939mon/logging_setup.py` | Console + rotating-file logging |
| `j1939mon/exceptions.py` | Typed error hierarchy |

## Prerequisites

On the Linux target, the CAN interface must be up before starting the monitor — the application deliberately does not touch link configuration (that is an administrative operation requiring root):

```bash
sudo ip link set can0 up type can bitrate 250000
```

For hardware-free testing, create a virtual SocketCAN device:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

## Installation

```bash
sudo apt install python3-gi gir1.2-gtk-3.0        # GTK 3 + PyGObject (GUI mode)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Headless mode needs only `python-can` — no GTK required.

## Running

```bash
python main.py                                    # GUI on socketcan/can0
python main.py --channel vcan0                    # GUI on a virtual device
python main.py --fullscreen                       # kiosk mode for embedded panels
python main.py --headless                         # console snapshots
```

| Flag | Description | Default |
|---|---|---|
| `--interface` | python-can interface | `socketcan` |
| `--channel` | CAN channel | `can0` |
| `--headless` | Console output instead of GUI | off |
| `--fullscreen` | Fullscreen dashboard | off |
| `--log-level` | DEBUG / INFO / WARNING / ERROR | `INFO` |

There is intentionally no `--bitrate` flag: a SocketCAN client cannot set the link bitrate; it is configured with `ip link` (see Prerequisites).

### Pairing with the simulator

The companion [simulator](../simulator/) generates matching traffic. On Linux, over `vcan0` (see Prerequisites):

```bash
python ../simulator/main.py --headless --interface socketcan --channel vcan0 &
python main.py --interface socketcan --channel vcan0
```

Without kernel modules, python-can's `udp_multicast` interface links the two processes over loopback networking (Linux/macOS, requires `pip install msgpack`):

```bash
python ../simulator/main.py --headless --interface udp_multicast --channel 239.74.163.2 &
python main.py --headless --interface udp_multicast --channel 239.74.163.2
```

Note that the `virtual` interface is process-local — it works for unit tests, not for bridging two separate processes.

## Supported PGNs

| PGN | Group | Signals (scale) |
|---|---|---|
| `0xF004` | EEC1 | Engine speed: bytes 4-5 × 0.125 rpm |
| `0xF003` | EEC2 | Engine load: byte 3 %, accelerator: byte 2 × 0.4 % |
| `0xFEF1` | CCVS | Vehicle speed: bytes 2-3 × 1/256 km/h |
| `0xFEF2` | LFE | Fuel rate: bytes 1-2 × 0.05 L/h, fuel economy: bytes 3-4 × 1/512 km/L |
| `0xFEF6` | IC1 | Boost: byte 2 × 2.0 kPa → psi, manifold temp: byte 3 − 40 °C → °F |
| `0xFEF7` | VEP1 | Battery voltage: bytes 5-6 × 0.05 V |
| `0xFEE5` | HOURS | Engine hours: bytes 1-4 × 0.05 h |
| `0xFEEE` | ET1 | Coolant temp: byte 1 − 40 °C → °F |
| `0xFEEF` | EFL/P1 | Oil pressure: byte 4 × 4.0 kPa, oil level: byte 3 × 0.4 % |
| `0xFEFC` | DD | Fuel level: byte 2 × 0.4 % |
| `0xFEE0` | VD | Total distance: bytes 5-8 × 0.125 km |
| `0xFCC2` | HVESDS1 | SoC: byte 5 × 0.4 %, plug status: upper nibble of byte 8 |
| `0xFAD4` | EVSE AC | AC current: bytes 3-4 × 0.05 A |
| `0xFC5E` | HVESS SOH | SoH: byte 1 × 0.4 % |
| `0xF096` | HVESSS1 | Charging state: byte 5 ∈ {0, 64, 128, 192} |
| `0xFB4F` | TEC | Total energy: bytes 5-8 ÷ 100 kWh |
| `0xFB97` | VEP15 | Four SLI battery packs: 4 × u16 |

Byte positions are 1-indexed as in the J1939-71 documents. Temperatures and boost pressure keep the original dashboard's display units (°F / psi).

## Testing

```bash
pip install pytest
python -m pytest
```

All 31 tests are pure-function tests (no hardware, no GTK): PGN extraction edge cases (PDU1 vs PDU2, data page, priority masking) and one known-payload test per decode formula.

## Extending

### Adding a new PGN

1. Add an entry to `PGN_DECODERS` in `j1939mon/database.py`:

```python
0xFECA: (
    SignalSpec(
        name="Active DTC Count",
        label_id="dtc_count",
        unit="",
        decode=lambda d: float(d[0]),
        fmt="{:.0f}",
    ),
),
```

2. Add a value `GtkLabel` with id `dtc_count` (plus a caption label) to `ui/monitor.glade` — the controller discovers labels automatically from the decode table.

3. Add a known-payload test in `tests/test_database.py`.

Helpers `u16le(data, i)` and `u32le(data, i)` cover little-endian multi-byte signals; for irregular decodes (nibbles, enums, composite strings) write a small function like `_plug_state` in `database.py`.

### Editing the UI

The layout lives in `ui/monitor.glade` (editable with [Glade](https://glade.gnome.org/) 3.40+); the theme in `ui/style.css`. The controller binds `startbtn`, `exit_btn`, `pano` and every `label_id` present in the decode table.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Failed to open CAN bus` | Interface down or wrong channel. Check `ip link show can0`; bring it up first. |
| `No data..` on the status panel | Link is up but silent — check wiring/termination, bitrate mismatch, or whether the transmitter is running. |
| `ImportError: gi` | PyGObject/GTK missing — install `python3-gi` or run `--headless`. |
| Values look frozen | Reception paused (Stop pressed) or the source stopped broadcasting; the watchdog flags staleness after 2 s. |

## Linux smoke checklist

```bash
sudo modprobe vcan && sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0
python ../simulator/main.py --headless --interface socketcan --channel vcan0 &
python main.py --interface socketcan --channel vcan0    # GUI opens, press Start, values update
```
