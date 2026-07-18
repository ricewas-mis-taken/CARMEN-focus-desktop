"""Tests the one architectural guarantee the whole Tkinter->PySide6
migration hinges on: a callable handed to qt_gui_thread.run_on_gui_thread()
from ANY thread actually executes on the thread that owns the
QApplication (the "Qt main thread"), matching the guarantee gui_thread.py
used to provide for Tk. Uses the real QApplication instance pytest-qt's
`qapp`/`qtbot` fixtures provide (offscreen, no visible window needed)."""
import threading
import time

import qt_gui_thread


def test_run_on_gui_thread_executes_on_qt_main_thread(qtbot, qapp):
    qt_gui_thread.start()
    main_thread = threading.current_thread()

    result = {}
    done = threading.Event()

    def marshaled_fn():
        result["thread"] = threading.current_thread()
        done.set()

    def call_from_background():
        # Give the main thread a beat to actually be idle in the Qt event
        # loop (qtbot.wait below pumps it) before emitting.
        qt_gui_thread.run_on_gui_thread(marshaled_fn)

    bg_thread = threading.Thread(target=call_from_background, daemon=True)
    bg_thread.start()
    bg_thread.join(timeout=2)

    # Pump the Qt event loop until the queued call lands (queued connections
    # only fire while the target thread's event loop is actually running).
    qtbot.waitUntil(lambda: done.is_set(), timeout=2000)

    assert result["thread"] is main_thread


def test_run_on_gui_thread_before_start_raises():
    qt_gui_thread._dispatcher = None
    try:
        try:
            qt_gui_thread.run_on_gui_thread(lambda: None)
            assert False, "expected RuntimeError before start() has run"
        except RuntimeError:
            pass
    finally:
        # Leave the dispatcher initialized again for any test that runs
        # after this one in the same session.
        qt_gui_thread.start()
