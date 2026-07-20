"""Tasks tab: one "card" per recurring task (dashboard-card style, like the
Calendar/Finished month grid's day cells), each showing today's progress
toward its target minutes and its banked "vacation" time. Business logic
(scheduling, pause-aware worked-time, vacation balance) lives in
tasks_store.py -- this module is presentation + wiring a card's Start/Pause/
End buttons to session_manager, the same session engine the Focus panel
(qt_ui/finished_tab.py) and calendar events (calendar_scheduler.py) use, via
start_session(source="task", event_id=<task id>, event_title=<task name>).

Card states (per-card, not global):
  idle    -- shows today's progress + vacation bars. Clicking the card
             (anywhere except the gear icon) arms it.
  armed   -- the progress/vacation content is blurred; a Start Task overlay
             (duration field, "Until I burnout", Start/Cancel buttons) sits
             on top, unblurred, as *sibling* widgets rather than children of
             the blurred content -- QGraphicsBlurEffect blurs its whole
             widget subtree, so the trigger controls can't live inside it.
             Clicking the card background (or the Start button) starts the
             task; clicking into the duration field or Cancel does not,
             since Qt delivers the press to that child widget instead of
             bubbling it up to the card's own mousePressEvent.
  running -- shown when session_manager reports an active session whose
             source/eventId matches this task (polled on the shared status
             timer below, not stored as card state) -- countdown, Pause/
             Resume, End Task.

Only one session can run at a time app-wide (session_manager's model), so
any card other than the one actually running is dimmed and ignores clicks
while some session -- task or otherwise -- is active.
"""
from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsBlurEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import session_history
import session_manager
import tasks_store
from qt_ui.task_editor import open_task_editor

STATUS_REFRESH_MS = 1000
CARD_MIN_WIDTH = 260
CARDS_PER_ROW = 3


def _format_minutes(total_minutes):
    total_minutes = int(round(total_minutes))
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class TasksTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        layout.addLayout(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setSpacing(16)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        self._cards = {}
        self.refresh()

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._tick)
        self._status_timer.start(STATUS_REFRESH_MS)

    def _build_header(self):
        header = QHBoxLayout()
        title = QLabel("Tasks")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch(1)
        add_button = QPushButton("+ Add Task")
        add_button.setProperty("class", "AccentButton")
        add_button.clicked.connect(lambda: open_task_editor(on_saved=lambda _t: self.refresh()))
        header.addWidget(add_button)
        return header

    def refresh(self):
        """Full rebuild -- called after a task is added/edited/deleted, or
        when this tab first opens. Cheaper per-tick updates (progress bars,
        countdown) go through _tick()/each card's update_dynamic() instead."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards = {}

        tasks = [t for t in tasks_store.load_tasks() if not t.get("archived")]
        if not tasks:
            empty_label = QLabel("No tasks yet -- click “+ Add Task” to create one.")
            empty_label.setStyleSheet("color: #8A8F98;")
            self._grid.addWidget(empty_label, 0, 0)
        for index, task in enumerate(tasks):
            row, col = divmod(index, CARDS_PER_ROW)
            card = _TaskCard(task, on_changed=self.refresh)
            self._grid.addWidget(card, row, col)
            self._cards[task["id"]] = card
        self._tick()

    def _tick(self):
        status = session_manager.get_status()
        sessions = session_history.load_all()
        for card in self._cards.values():
            card.update_dynamic(status, sessions)


class _TaskCard(QFrame):
    def __init__(self, task, on_changed):
        super().__init__()
        self._task = task
        self._on_changed = on_changed
        self._armed = False
        self._until_burnout = False

        self.setProperty("class", "TaskCard")
        self.setMinimumWidth(CARD_MIN_WIDTH)
        self.setCursor(Qt.PointingHandCursor)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        outer.addLayout(self._build_header_row())

        # Everything that gets blurred while armed lives in this one
        # sub-widget -- see module docstring for why the trigger controls
        # must NOT be inside it.
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content_layout.addLayout(self._build_progress_section())
        content_layout.addLayout(self._build_vacation_section())
        outer.addWidget(self._content)

        self._armed_overlay = self._build_armed_overlay()
        outer.addWidget(self._armed_overlay)
        self._armed_overlay.setVisible(False)

        self._running_panel = self._build_running_panel()
        outer.addWidget(self._running_panel)
        self._running_panel.setVisible(False)

        self._blur = QGraphicsBlurEffect(self._content)
        self._blur.setBlurRadius(0)
        self._content.setGraphicsEffect(self._blur)

    # --- static sections ---

    def _build_header_row(self):
        row = QHBoxLayout()
        name_label = QLabel(self._task["name"])
        name_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        row.addWidget(name_label, 1)

        gear = QPushButton("⚙")
        gear.setFixedSize(26, 26)
        gear.setProperty("class", "SecondaryButton")
        gear.setToolTip("Edit task")
        gear.clicked.connect(self._open_editor)
        row.addWidget(gear)
        return row

    def _build_progress_section(self):
        col = QVBoxLayout()
        self._progress_label = QLabel()
        self._progress_label.setStyleSheet("font-size: 11px; color: #8A8F98;")
        col.addWidget(self._progress_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(10)
        self._progress_bar.setProperty("class", "TaskProgressBar")
        self._progress_bar.setStyleSheet(f"QProgressBar::chunk {{ background: {self._task.get('color', '#5B8DEF')}; }}")
        col.addWidget(self._progress_bar)
        return col

    def _build_vacation_section(self):
        row = QHBoxLayout()
        self._vacation_label = QLabel()
        self._vacation_label.setStyleSheet("font-size: 11px; color: #8A8F98;")
        row.addWidget(self._vacation_label, 1)
        self._cash_in_button = QPushButton("Cash in vacation")
        self._cash_in_button.setProperty("class", "SecondaryButton")
        self._cash_in_button.clicked.connect(self._cash_in)
        row.addWidget(self._cash_in_button)
        return row

    def _build_armed_overlay(self):
        overlay = QWidget()
        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        duration_row = QHBoxLayout()
        self._duration_edit = QLineEdit()
        self._duration_edit.setPlaceholderText("minutes")
        duration_row.addWidget(self._duration_edit)
        self._burnout_button = QPushButton("Until I burnout")
        self._burnout_button.setCheckable(True)
        self._burnout_button.setProperty("class", "SecondaryButton")
        self._burnout_button.toggled.connect(self._toggle_burnout)
        duration_row.addWidget(self._burnout_button)
        layout.addLayout(duration_row)

        button_row = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self._disarm)
        button_row.addWidget(cancel_button)
        start_button = QPushButton("Start Task")
        start_button.setProperty("class", "AccentButton")
        start_button.clicked.connect(self._start_task)
        button_row.addWidget(start_button)
        layout.addLayout(button_row)

        return overlay

    def _build_running_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._countdown_label = QLabel()
        self._countdown_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(self._countdown_label)

        button_row = QHBoxLayout()
        self._pause_button = QPushButton("Pause")
        self._pause_button.clicked.connect(self._pause_resume)
        button_row.addWidget(self._pause_button)
        end_button = QPushButton("End Task")
        end_button.setProperty("class", "SecondaryButton")
        end_button.clicked.connect(self._end_task)
        button_row.addWidget(end_button)
        layout.addLayout(button_row)

        return panel

    # --- state transitions ---

    def mousePressEvent(self, event):
        # Only reachable for clicks that landed on the card itself or a
        # non-interactive child (labels, bars) -- QLineEdit/QPushButton
        # children consume their own press events and never bubble here.
        if self._is_locked_by_other_session():
            super().mousePressEvent(event)
            return
        if not self._armed and not self._running_panel.isVisible():
            self._arm()
        elif self._armed:
            self._start_task()
        super().mousePressEvent(event)

    def _arm(self):
        self._armed = True
        self._blur.setBlurRadius(6)
        self._armed_overlay.setVisible(True)
        self._duration_edit.setText(str(self._today_required_minutes()))

    def _disarm(self):
        self._armed = False
        self._blur.setBlurRadius(0)
        self._armed_overlay.setVisible(False)
        self._burnout_button.setChecked(False)

    def _toggle_burnout(self, checked):
        self._until_burnout = checked
        self._duration_edit.setDisabled(checked)

    def _open_editor(self):
        open_task_editor(self._task, on_saved=lambda _t: self._on_changed())

    def _start_task(self):
        if self._until_burnout:
            duration_minutes = tasks_store.BURNOUT_MINUTES
        else:
            try:
                duration_minutes = float(self._duration_edit.text())
                if duration_minutes <= 0:
                    raise ValueError
            except ValueError:
                return

        session_manager.start_session(
            duration_minutes,
            self._task.get("lockMode", "soft"),
            self._task.get("processWhitelist", []),
            self._task.get("domainWhitelist", []),
            source="task",
            event_id=self._task["id"],
            event_title=self._task["name"],
        )
        self._disarm()

    def _pause_resume(self):
        if session_manager.get_status()["isPaused"]:
            session_manager.resume_session()
        else:
            session_manager.pause_session()

    def _end_task(self):
        session_manager.end_session(end_type="manual")

    def _cash_in(self):
        sessions = session_history.load_all()
        balance = tasks_store.vacation_balance_minutes(self._task, sessions)
        if balance <= 0:
            QMessageBox.information(self, "Carmen Focus", "No vacation time banked yet for this task.")
            return
        minutes, ok = QInputDialog.getInt(
            self, "Cash in vacation",
            f"Minutes to cash in against today (up to {int(balance)}):",
            min(int(balance), self._task.get("targetMinutes", 0) or int(balance)), 1, int(balance),
        )
        if not ok:
            return
        try:
            self._task = tasks_store.cash_in(self._task["id"], date.today(), minutes, sessions)
        except ValueError as exc:
            QMessageBox.warning(self, "Carmen Focus", str(exc))
            return
        self._on_changed()

    # --- dynamic refresh (called every tick by TasksTab) ---

    def _today_required_minutes(self):
        return tasks_store.required_minutes_for_date(self._task, date.today())

    def _is_locked_by_other_session(self):
        status = session_manager.get_status()
        if not status["isActive"]:
            return False
        return not (status.get("source") == "task" and status.get("eventId") == self._task["id"])

    def update_dynamic(self, status, sessions):
        today = date.today()
        required = self._today_required_minutes()
        logged_seconds = tasks_store.logged_seconds_for_date(self._task, today, sessions, live_status=status)
        logged_minutes = logged_seconds / 60

        pct = 100 if required <= 0 else min(100, int(logged_minutes / required * 100))
        self._progress_bar.setValue(pct if (required > 0 or logged_minutes > 0) else 0)
        if required <= 0:
            self._progress_label.setText(f"{_format_minutes(logged_minutes)} logged · not scheduled today")
        else:
            self._progress_label.setText(f"{_format_minutes(logged_minutes)} of {_format_minutes(required)} today")

        balance = tasks_store.vacation_balance_minutes(self._task, sessions)
        self._vacation_label.setText(f"\U0001F3D6 {_format_minutes(balance)} vacation banked")
        self._cash_in_button.setEnabled(balance > 0 and not self._is_running())

        is_running = status.get("isActive") and status.get("source") == "task" and status.get("eventId") == self._task["id"]
        locked_by_other = self._is_locked_by_other_session()

        if is_running:
            if self._armed:
                self._disarm()
            self._content.setVisible(False)
            self._armed_overlay.setVisible(False)
            self._running_panel.setVisible(True)
            minutes, seconds = divmod(status.get("secondsRemaining", 0), 60)
            paused = " (paused)" if status.get("isPaused") else ""
            self._countdown_label.setText(f"{minutes}m {seconds}s remaining{paused}")
            self._pause_button.setText("Resume" if status.get("isPaused") else "Pause")
        else:
            self._running_panel.setVisible(False)
            self._content.setVisible(True)
            if self._armed and locked_by_other:
                self._disarm()

        self.setEnabled(not locked_by_other)
        self.setProperty("locked", locked_by_other)
        self.style().unpolish(self)
        self.style().polish(self)

    def _is_running(self):
        status = session_manager.get_status()
        return status.get("isActive") and status.get("source") == "task" and status.get("eventId") == self._task["id"]
