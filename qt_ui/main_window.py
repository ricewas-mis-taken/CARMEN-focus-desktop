"""The real Qt main window: sidebar nav (Calendar / Finished) +
QStackedWidget content, replacing calendar_gui.py's Tk `.tkraise()` frame
switching and Stage 1's placeholder stand-in. Two tabs are populated:
Calendar (qt_ui/calendar_page.py) and Finished (qt_ui/finished_tab.py) --
the former Focus tab's controls (session start/status, pause/resume,
nuclear end) now live at the top of Finished, since starting a session and
reviewing finished ones are both part of the same day-to-day loop.
"""
from PySide6.QtCore import Qt
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from qt_ui.calendar_page import CalendarPage
from qt_ui.finished_tab import FinishedTab
from qt_ui.tasks_tab import TasksTab

_win = None


def open_main_window():
    global _win
    if _win is not None and _win.isVisible():
        _win.raise_()
        _win.activateWindow()
        return
    _win = _MainWindow()
    _win.show()


def refresh_calendar_views():
    """Called after an event is saved/deleted (qt_ui/event_editor.py) so
    any already-open calendar/finished views pick up the change -- the Qt
    equivalent of the Tk version's _refresh_all_calendar_views() walking
    _state["refresh_callbacks"]. A no-op if the main window isn't open."""
    if _win is None:
        return
    _win._pages["calendar"].refresh()
    _win._pages["finished"].refresh()


_NORMAL_SIZE = (800, 800)


class _MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Carmen Focus")
        self.resize(*_NORMAL_SIZE)
        self.setMinimumSize(540, 540)
        self._was_maximized = False

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack)
        root_layout.addWidget(content, 1)

        self._pages = {}
        self._add_page("calendar", CalendarPage())
        self._add_page("tasks", TasksTab())
        self._add_page("finished", FinishedTab())

        self._show_tab("calendar")

    def _add_page(self, key, widget):
        self._pages[key] = widget
        self._stack.addWidget(widget)

    def _build_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(180)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("Carmen Focus")
        title.setObjectName("SidebarTitle")
        layout.addWidget(title)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        nav_items = [("calendar", "📅  Calendar"), ("tasks", "🎯  Tasks"), ("finished", "✅  Finished")]
        for key, label in nav_items:
            button = QPushButton(label)
            button.setProperty("class", "NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked, k=key: self._show_tab(k))
            layout.addWidget(button)
            self._nav_group.addButton(button)
            if key == "calendar":
                button.setChecked(True)

        layout.addStretch(1)
        return sidebar

    def _show_tab(self, key):
        self._stack.setCurrentWidget(self._pages[key])

    def changeEvent(self, event):
        # Qt restores a "restore down" (un-maximize) click to whatever
        # normalGeometry() happened to be recorded as -- which drifts away
        # from square if the window was ever resized (by the user dragging
        # an edge, or a previous maximize/restore round-trip) while still
        # maximized, or if the OS snapped it during the maximize animation.
        # Re-asserting a fixed 800x800 right after the state flips back to
        # Normal keeps "restore" always landing on the same square size
        # instead of a stretched rectangle.
        if event.type() == QEvent.WindowStateChange:
            is_maximized = bool(self.windowState() & Qt.WindowMaximized)
            if self._was_maximized and not is_maximized:
                self.resize(*_NORMAL_SIZE)
            self._was_maximized = is_maximized
        super().changeEvent(event)
