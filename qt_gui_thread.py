"""Single Qt-main-thread dispatcher — the PySide6 replacement for
gui_thread.py's shared-Tk()-root pattern.

Qt widgets, like Tk widgets, may only be constructed/touched from the
thread that owns the QApplication (this app makes that the main thread —
see main.py). Every other thread that needs to open or update a window —
pystray's detached callback thread, window_tracker's polling thread (via
enforcer.py), any future WinRT toast callback — must marshal onto it
through this module instead of importing PySide6 directly.

Mechanism: one QObject singleton with a Signal(object) (the callable to
run), connected with an explicit Qt.QueuedConnection. Qt's own event loop
does the actual cross-thread hop — no manual queue, no polling loop, unlike
the old gui_thread.py's `root.after(50, poll_queue)` busy-poll.

Same two-function public surface as gui_thread.py (start(),
run_on_gui_thread(fn)) so every call site changes its import, not its
shape — except build_fn now takes no arguments, since Qt top-level widgets
don't need a shared `root` the way Tk Toplevels needed a shared Tk().
"""
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication

from calendar_log import logger

_dispatcher = None


class _Dispatcher(QObject):
    _request = Signal(object)

    def __init__(self):
        super().__init__()
        self._request.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, fn):
        try:
            fn()
        except Exception:
            logger.exception("qt_gui_thread callable failed")


def start():
    """Call once from main.py, on the Qt main thread, after QApplication()
    has been constructed and before any other thread calls
    run_on_gui_thread()."""
    global _dispatcher
    _dispatcher = _Dispatcher()


def run_on_gui_thread(build_fn):
    """Schedules build_fn() to run on the Qt main thread. Safe to call from
    any thread, including the main thread itself — routed through Qt's
    queued connection either way, so behavior doesn't depend on which
    thread the caller happens to be on."""
    if _dispatcher is None:
        raise RuntimeError("qt_gui_thread.start() must run before run_on_gui_thread()")
    _dispatcher._request.emit(build_fn)


def quit_app():
    """Terminates the Qt event loop (QApplication.exec()'s return point).

    Must go through this — never call QApplication.instance().quit()
    directly from a non-Qt thread (pystray's callback thread, in
    particular). Confirmed via a throwaway spike: a direct cross-thread
    call to .quit() silently does nothing and the process hangs forever.
    Routing it through the same queued-signal mechanism as every other
    GUI-thread marshal fixes it."""
    run_on_gui_thread(lambda: QApplication.instance().quit())
