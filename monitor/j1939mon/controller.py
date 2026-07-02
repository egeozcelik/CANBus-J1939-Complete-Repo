"""GTK dashboard controller.

Binds the receiver to the GTK window defined in `ui/monitor.glade`.

Threading model: the python-can notifier thread never touches GTK.
Updates are coalesced into a lock-guarded pending dictionary; a single
`GLib.idle_add` flush is scheduled at a time, so high frame rates
cannot flood the main loop. A 1 Hz watchdog reports the reception
state on the status panel.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, GLib

from .database import PGN_DECODERS
from .decoder import DecodedSignal
from .receiver import CanReceiver

logger = logging.getLogger(__name__)

STALE_AFTER_S = 2.0


def _asset_paths() -> tuple[Path, Path]:
    """Resolve the Glade and CSS asset paths relative to the project root."""
    project_root = Path(__file__).resolve().parent.parent
    return (
        project_root / "ui" / "monitor.glade",
        project_root / "ui" / "style.css",
    )


class MonitorController:
    """Single-window controller for the live J1939 dashboard."""

    def __init__(
        self,
        receiver_factory: Callable[..., CanReceiver],
        fullscreen: bool = False,
    ) -> None:
        self.receiver_factory = receiver_factory
        self.receiver: CanReceiver | None = None
        self.fullscreen = fullscreen

        self._pending: dict[str, DecodedSignal] = {}
        self._pending_lock = threading.Lock()
        self._flush_scheduled = False
        self._last_rx_time = 0.0

        glade_path, css_path = _asset_paths()
        self.builder = Gtk.Builder()
        self.builder.add_from_file(str(glade_path))

        self.window = self.builder.get_object("MainWindow")
        if self.window is None:
            raise RuntimeError("MainWindow not found in the Glade file")
        self.window.set_position(Gtk.WindowPosition.CENTER)
        if fullscreen:
            self.window.fullscreen()

        self._apply_css(css_path)
        self._wire_widgets()
        self.window.connect("destroy", self._on_destroy)

    def _apply_css(self, css_path: Path) -> None:
        if not css_path.exists():
            logger.warning("CSS file not found: %s", css_path)
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _wire_widgets(self) -> None:
        b = self.builder.get_object
        self.pano_label = b("pano")
        self.start_btn = b("startbtn")
        self.exit_btn = b("exit_btn")
        self.start_btn.connect("clicked", self._on_start_stop_clicked)
        self.exit_btn.connect("clicked", self._on_exit_clicked)

        self.value_labels: dict[str, Gtk.Label] = {}
        for specs in PGN_DECODERS.values():
            for spec in specs:
                label = b(spec.label_id)
                if label is not None:
                    self.value_labels[spec.label_id] = label
                else:
                    logger.warning("Glade widget not found: %s", spec.label_id)

        self._reset_labels()
        self.pano_label.set_text("Waiting..")

    def run(self) -> None:
        self.window.show_all()
        self._watchdog_id = GLib.timeout_add_seconds(1, self._watchdog)
        Gtk.main()

    def _on_start_stop_clicked(self, _widget) -> None:
        if self.receiver is None:
            self._start_receiving()
        else:
            self._stop_receiving()

    def _start_receiving(self) -> None:
        try:
            self.receiver = self.receiver_factory(on_update=self._on_update)
            self.receiver.start()
        except Exception as exc:
            logger.exception("Failed to start receiver")
            self.receiver = None
            self.pano_label.set_text("Bus error")
            return
        self.start_btn.set_label("Stop")
        self.pano_label.set_text("Listening..")
        self._last_rx_time = 0.0

    def _stop_receiving(self) -> None:
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver = None
        self.start_btn.set_label("Start")
        self.pano_label.set_text("Waiting..")
        self._reset_labels()

    def _on_update(self, updates: dict[str, DecodedSignal]) -> None:
        """Receiver-thread entry point; coalesces updates for the UI."""
        with self._pending_lock:
            self._pending.update(updates)
            if self._flush_scheduled:
                return
            self._flush_scheduled = True
        GLib.idle_add(self._flush_pending)

    def _flush_pending(self) -> bool:
        with self._pending_lock:
            pending, self._pending = self._pending, {}
            self._flush_scheduled = False
        for label_id, signal in pending.items():
            label = self.value_labels.get(label_id)
            if label is not None:
                label.set_text(signal.text)
        self._last_rx_time = time.monotonic()
        return GLib.SOURCE_REMOVE

    def _watchdog(self) -> bool:
        if self.receiver is None:
            return GLib.SOURCE_CONTINUE
        if self._last_rx_time == 0.0:
            self.pano_label.set_text("Listening..")
        elif time.monotonic() - self._last_rx_time > STALE_AFTER_S:
            self.pano_label.set_text("No data..")
        else:
            self.pano_label.set_text("Processing\n Can Data..")
        return GLib.SOURCE_CONTINUE

    def _reset_labels(self) -> None:
        for label in self.value_labels.values():
            label.set_text("-")

    def _on_exit_clicked(self, _widget) -> None:
        self.window.destroy()

    def _on_destroy(self, _widget) -> None:
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver = None
        Gtk.main_quit()
