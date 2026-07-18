"""Entry point for the tray's "Open Carmen Focus" menu item. Widget
construction lives in qt_ui/main_window.py; this module just marshals onto
the Qt main thread, same public surface as before the Tkinter->PySide6
migration (see qt_gui_thread.py) so tray.py's caller didn't need to change.

The original Tk implementation this replaced (month grid, day schedule,
Focus tab, Finished tab, event editor) was ported piece by piece into the
qt_ui/ package across the migration's stages -- see qt_ui/main_window.py,
qt_ui/calendar_page.py, qt_ui/month_view.py, qt_ui/day_view.py,
qt_ui/day_layout.py, qt_ui/finished_tab.py,
qt_ui/event_editor.py, and qt_ui/next_up_widget.py.
"""
import qt_gui_thread
import qt_ui.main_window as main_window


def open_main_window():
    qt_gui_thread.run_on_gui_thread(main_window.open_main_window)
