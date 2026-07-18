"""Entry point for the tray's "Session History" menu item. Widget
construction and formatting live in qt_ui/history_viewer.py; this module
just marshals onto the Qt main thread, same public surface as before the
Tkinter->PySide6 migration."""
import qt_gui_thread
import qt_ui.history_viewer as history_viewer


def open_history_viewer():
    qt_gui_thread.run_on_gui_thread(history_viewer.open_history_viewer)
