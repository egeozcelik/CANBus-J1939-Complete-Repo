"""GTK UI controller.

Uses the `ui/simulator.glade` layout while wiring UI events to the
engine and the model through a clean controller architecture. The GTK
main thread is managed from a single place.

Two key principles in the UI <-> engine integration:
  1. CAN transmission happens in a GLib timeout (engine.tick()), so
     the UI thread never blocks.
  2. After each engine broadcast, the BroadcastEvent listener updates
     the log panel. The listener is marshalled back onto the UI thread
     via GLib.idle_add.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Mapping

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, GLib  # noqa: E402

from .database import PGN_DATABASE, SIGNAL_DATABASE
from .engine import BroadcastEvent, SimulationEngine
from .model import VehicleModel
from .transport import CanTransport

logger = logging.getLogger(__name__)


_LABEL_MAP: dict[str, str] = {
    "vehicle_speed": "vehicles_speed",
    "engine_boost_pressure": "engine_boost_pressure",
    "manifold_temperature": "manifold_temperature",
    "battery_voltage": "battery_voltage",
    "instant_fuel_economy": "instant_fuel_economy",
    "instant_fuel_rate": "instant_fuel_rate",
    "engine_hour": "engine_hour",
    "engine_temperature": "engine_temperature",
    "engine_oil_pressure": "engine_oil_pressure",
    "engine_oil_level": "engine_oil_level",
    "fuel_level": "fuel_level",
    "total_vehicle_distance": "tvd_label",
    "engine_load": "engine_load",
    "accelerator_position": "accelerator_position",
    "engine_speed": "engine_speed",
    "motor_speed": "motor_speed",
    "motor_temp": "motor_temp",
    "mcu_temp": "mcu_temp",
    "battery_voltage_ev": "battery_voltage_ev",
    "battery_current": "battery_current",
    "soc": "soc",
    "highest_temp": "highest_temp",
    "pack_temp": "pack_temp",
    "current_ac": "current_ac",
    "soh": "soh",
    "tec": "tec",
    "vep15": "vep15",
}


class AppController:
    """Single-window UI controller.

    `transport_factory` is a callable producing a fresh transport on
    every start-simulation click; alternatively an already connected
    transport can be injected at construction time.
    """

    def __init__(
        self,
        glade_path: str | Path,
        css_path: str | Path,
        transport_factory: Callable[[], CanTransport],
        model: VehicleModel | None = None,
        tick_interval_ms: int = 50,
        source_address_override: int | None = None,
    ) -> None:
        self.glade_path = str(glade_path)
        self.css_path = str(css_path)
        self.transport_factory = transport_factory
        self.tick_interval_ms = max(10, tick_interval_ms)
        self.source_address_override = source_address_override

        self.model = model or VehicleModel()
        self.transport: CanTransport | None = None
        self.engine: SimulationEngine | None = None

        self._tick_source_id: int | None = None
        self._refresh_source_id: int | None = None
        self._log_format = "can_data_log"
        self._last_tick_time = 0.0

        self.builder = Gtk.Builder()
        self.builder.add_from_file(self.glade_path)

        self.window = self.builder.get_object("MainWindow")
        if self.window is None:
            raise RuntimeError("MainWindow not found in the Glade file")

        self._wire_widgets()
        self._apply_css()
        self._reset_status_labels()
        self.window.connect("destroy", self._on_destroy)

    def _wire_widgets(self) -> None:
        b = self.builder.get_object
        self.start_btn = b("start_simulation")
        self.exit_btn = b("exit_btn")
        self.up_btn = b("increase_speed_btn")
        self.down_btn = b("decrease_speed_btn")
        self.refresh_btn = b("refresh_btn")
        self.text_view = b("log_text_view")
        self.text_buffer = self.text_view.get_buffer()
        self.can_data_log_btn = b("can_data_log")
        self.can_value_log_btn = b("value_log")
        self.plug_switch = b("switch_plug")
        self.charge_switch = b("hvesss1_switch")
        self.vehicle_speed_lbl = b("vehicle_speed_label_left")
        self.rpm_lbl = b("rpm_label_left")

        self.status_labels: dict[str, Gtk.Label] = {}
        for sig_key, glade_id in _LABEL_MAP.items():
            obj = b(glade_id)
            if obj is not None:
                self.status_labels[sig_key] = obj
            else:
                logger.warning("Glade widget not found: %s", glade_id)

        self.start_btn.connect("clicked", self._on_start_clicked)
        self.exit_btn.connect("clicked", self._on_exit_clicked)
        self.up_btn.connect("clicked", self._on_accelerate_clicked)
        self.down_btn.connect("clicked", self._on_decelerate_clicked)
        self.refresh_btn.connect("clicked", self._on_refresh_clicked)
        self.can_data_log_btn.connect("clicked", self._on_data_log_format)
        self.can_value_log_btn.connect("clicked", self._on_value_log_format)

        self.plug_switch.connect("notify::active", self._on_plug_toggle)
        self.charge_switch.connect("notify::active", self._on_charge_toggle)

        self.can_data_log_btn.get_style_context().add_class("button-selected")
        self.can_value_log_btn.get_style_context().add_class("button-unselected")

        self.append_log("[SYSTEM] Ready. Press 'Start Simulation' to connect.")

    def _apply_css(self) -> None:
        if not Path(self.css_path).exists():
            logger.warning("CSS file not found: %s", self.css_path)
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(self.css_path)
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def run(self) -> None:
        self.window.show_all()
        Gtk.main()

    def _on_start_clicked(self, _widget) -> None:
        if self.engine and self.engine.is_running:
            self._stop_simulation()
        else:
            self._start_simulation()

    def _start_simulation(self) -> None:
        try:
            self.transport = self.transport_factory()
            self.transport.connect()
        except Exception as exc:
            logger.exception("Transport connection failed")
            self.append_log(f"[ERROR] Failed to open CAN bus: {exc}")
            return

        self.engine = SimulationEngine(
            transport=self.transport,
            signal_provider=self.model.as_signal_map,
            source_address=self.source_address_override,
            listener=self._on_broadcast_event,
        )
        self.engine.start()
        self.start_btn.set_label("Stop Simulation")

        self._tick_source_id = GLib.timeout_add(self.tick_interval_ms, self._tick)
        self._refresh_source_id = GLib.timeout_add(200, self._refresh_status_labels)
        self.append_log(
            f"[SYSTEM] Simulation started (tick={self.tick_interval_ms}ms, "
            f"interface={self.transport.interface}, channel={self.transport.channel})"
        )

    def _stop_simulation(self) -> None:
        if self._tick_source_id is not None:
            GLib.source_remove(self._tick_source_id)
            self._tick_source_id = None
        if self._refresh_source_id is not None:
            GLib.source_remove(self._refresh_source_id)
            self._refresh_source_id = None

        if self.engine:
            self.engine.stop()
            self.engine = None
        if self.transport:
            self.transport.disconnect()
            self.transport = None

        self.start_btn.set_label("Start Simulation")
        self._reset_status_labels()
        self.append_log("[SYSTEM] Simulation stopped.")

    def _tick(self) -> bool:
        if self.engine is None or not self.engine.is_running:
            return False
        import time as _time
        now = _time.monotonic()
        dt = self.tick_interval_ms / 1000.0
        if self._last_tick_time:
            dt = max(0.001, now - self._last_tick_time)
        self._last_tick_time = now

        self.model.step(dt)
        self.engine.tick()
        return True

    def _refresh_status_labels(self) -> bool:
        if self.engine is None:
            return False
        values = self.model.as_signal_map()
        for key, label in self.status_labels.items():
            if key in values:
                label.set_text(self._format_value(key, values[key]))
        self.vehicle_speed_lbl.set_text(f"Vehicle Speed: {values['vehicle_speed']:.1f}")
        self.rpm_lbl.set_text(f"RPM: {values['engine_speed']:.0f}")
        return True

    def _format_value(self, key: str, value: float) -> str:
        sig = SIGNAL_DATABASE.get(key)
        if sig is None:
            return f"{value:.2f}"
        unit = f" {sig.unit}" if sig.unit else ""
        if sig.bit_length <= 8 and sig.scale >= 1.0:
            return f"{value:.0f}{unit}"
        return f"{value:.2f}{unit}"

    def _reset_status_labels(self) -> None:
        for label in self.status_labels.values():
            label.set_text("    -   ")
        self.vehicle_speed_lbl.set_text("Vehicle Speed: -")
        self.rpm_lbl.set_text("RPM: -")

    def _on_accelerate_clicked(self, _widget) -> None:
        self.model.request_accelerate(0.7)
        self.append_log("[INPUT] Accelerator pressed")
        GLib.timeout_add(500, self._release_pedal_after_press)

    def _on_decelerate_clicked(self, _widget) -> None:
        self.model.request_decelerate(0.7)
        self.append_log("[INPUT] Brake pressed")
        GLib.timeout_add(500, self._release_pedal_after_press)

    def _release_pedal_after_press(self) -> bool:
        self.model.release_pedal()
        return False

    def _on_refresh_clicked(self, _widget) -> None:
        self.text_buffer.set_text("")

    def _on_data_log_format(self, _widget) -> None:
        self._log_format = "can_data_log"
        self.can_data_log_btn.get_style_context().remove_class("button-unselected")
        self.can_data_log_btn.get_style_context().add_class("button-selected")
        self.can_value_log_btn.get_style_context().remove_class("button-selected")
        self.can_value_log_btn.get_style_context().add_class("button-unselected")

    def _on_value_log_format(self, _widget) -> None:
        self._log_format = "value_log"
        self.can_data_log_btn.get_style_context().remove_class("button-selected")
        self.can_data_log_btn.get_style_context().add_class("button-unselected")
        self.can_value_log_btn.get_style_context().remove_class("button-unselected")
        self.can_value_log_btn.get_style_context().add_class("button-selected")

    def _on_plug_toggle(self, switch, _param) -> None:
        plugged = switch.get_active()
        self.model.set_plug_state(plugged)
        self.append_log(f"[INPUT] Plug state: {'CONNECTED' if plugged else 'DISCONNECTED'}")

    def _on_charge_toggle(self, switch, _param) -> None:
        active = switch.get_active()
        self.model.set_ac_charging(active)
        self.append_log(f"[INPUT] AC charging: {'ON' if active else 'OFF'}")

    def _on_broadcast_event(self, event: BroadcastEvent) -> None:
        GLib.idle_add(self._format_event_log, event)

    def _format_event_log(self, event: BroadcastEvent) -> bool:
        if self._log_format == "can_data_log":
            line = (
                f"[TX {'OK' if event.success else 'ERR'}] "
                f"PGN=0x{event.pgn_definition.pgn:04X} "
                f"({event.pgn_definition.name}) "
                f"ID=0x{event.can_id:08X} "
                f"DATA={event.data.hex(' ').upper()}"
            )
            self.append_log(line)
        else:
            for key, value in event.signal_values.items():
                sig = SIGNAL_DATABASE.get(key)
                unit = sig.unit if sig else ""
                self.append_log(
                    f"[TX {'OK' if event.success else 'ERR'}] "
                    f"{key}: {value:.2f} {unit}".strip()
                )
        return False

    def append_log(self, text: str) -> None:
        end_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(end_iter, text + "\n")
        adj = self.text_view.get_vadjustment()
        GLib.idle_add(adj.set_value, adj.get_upper())

    def _on_exit_clicked(self, _widget) -> None:
        self.window.destroy()

    def _on_destroy(self, _widget) -> None:
        if self.engine and self.engine.is_running:
            self._stop_simulation()
        Gtk.main_quit()
