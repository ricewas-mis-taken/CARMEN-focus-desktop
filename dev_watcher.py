"""--dev only: watches the project's .py files and restarts the process on
any change, so editing code doesn't require manually killing and relaunching
the tray app.

Mirrors auto_updater.py's shape (a background thread flips a
threading.Event and calls an on_update_ready callback that main.py wires to
the same graceful-quit path as the tray's Quit button) -- restart itself
happens the same way an auto-update restart does, via os.execv in main.py
once the Qt event loop exits.
"""
import os
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from calendar_log import logger

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

_restart_requested = threading.Event()


def restart_was_requested():
    return _restart_requested.is_set()


class _RestartOnPyChange(FileSystemEventHandler):
    def __init__(self, on_change_ready):
        self._on_change_ready = on_change_ready

    def _handle(self, event):
        if event.is_directory or not event.src_path.endswith(".py"):
            return
        if _restart_requested.is_set():
            return  # already restarting -- ignore further events (e.g. save-triggered duplicates)
        print(f"[dev] {event.src_path} changed -- restarting")
        _restart_requested.set()
        self._on_change_ready()

    def on_modified(self, event):
        self._handle(event)

    def on_created(self, event):
        self._handle(event)

    def on_moved(self, event):
        self._handle(event)


def start(on_change_ready):
    """on_change_ready() is called, from watchdog's own background thread,
    the moment a .py file changes -- main.py wires it to the same graceful
    quit path as the tray's Quit button, then re-execs the process once the
    Qt event loop exits (see restart_was_requested())."""
    observer = Observer()
    observer.schedule(_RestartOnPyChange(on_change_ready), REPO_ROOT, recursive=True)
    observer.start()
    logger.info("dev_watcher: watching %s for .py changes", REPO_ROOT)
    return observer
