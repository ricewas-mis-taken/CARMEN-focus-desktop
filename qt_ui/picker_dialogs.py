"""Qt port of picker_gui.py's three dialogs: the app whitelist picker, its
follow-up mid-session reason dialog, and the start-session timer dialog.

Uses the shared qt_ui/checklist.py component for the whitelist picker's
checkbox list -- the same component the event editor's process/domain
whitelist checklists use (qt_ui/event_editor.py), replacing both this
module's original Stage-1 ad-hoc duplicate and the old Tk
checklist_widget.py.

All three windows are non-modal (.show(), not .exec()) -- same as the
original Tk versions, which never used grab_set().
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import config
import installed_apps
import session_history
import session_manager
import qt_ui.checklist as checklist

_open_windows = set()


def _track(win):
    _open_windows.add(win)
    win.destroyed.connect(lambda: _open_windows.discard(win))
    return win


def open_whitelist_picker():
    _track(_WhitelistPicker()).show()


def open_timer_dialog():
    _track(_TimerDialog()).show()


class _Checklist:
    """Thin wrapper around qt_ui.checklist's function-based API, giving
    callers in this module the same object-with-methods shape the Stage-1
    ad-hoc _ScrollableChecklist had (add_row / add_separator_label /
    checked_keys / has_key), so _WhitelistPicker's logic below didn't need
    to change shape when the underlying checklist implementation was
    unified in Stage 5."""

    def __init__(self, height=280):
        self.widget, self._checkboxes_by_key, self._add_row = checklist.build_checklist(
            [], set(), height=height
        )

    def add_row(self, key, label, checked):
        self._add_row(key, label, checked)

    def add_separator_label(self, text):
        self._add_row.add_separator_label(text)

    def checked_keys(self):
        return checklist.get_checked(self._checkboxes_by_key)

    def has_key(self, key):
        return key.lower() in self._checkboxes_by_key


class _WhitelistPicker(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setObjectName("PopupBg")
        self.setWindowTitle("Carmen Focus — Pick Apps to Whitelist")
        self.resize(440, 640)

        self._session_active = session_manager.is_active()
        if self._session_active:
            self._saved = {name.lower() for name in session_manager.get_status()["processWhitelist"]}
        else:
            self._saved = {name.lower() for name in config.load_config().get("processWhitelist", [])}

        layout = QVBoxLayout(self)

        if self._session_active:
            instructions = (
                "A session is active — checked apps below are already allowed.\n"
                "Check any more you want to add. You'll be asked to explain each\n"
                "new one before it's added."
            )
        else:
            instructions = "Check the apps allowed during a focus session.\nPreviously saved picks are pre-checked."
        instructions_label = QLabel(instructions)
        instructions_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions_label)

        self._checklist = _Checklist()
        layout.addWidget(self._checklist.widget)

        if not self._session_active:
            self._add_quick_readd_rows()

        apps = installed_apps.list_installed_apps()
        if not apps:
            self._checklist.add_separator_label("No installed apps found.")
        for app in apps:
            self._checklist.add_row(
                app["process_name"],
                f"{app['display_name']}   ({app['process_name']})",
                checked=app["process_name"].lower() in self._saved,
            )

        manual_label = QLabel("Not listed? Add by name or file:")
        layout.addWidget(manual_label)

        manual_row = QHBoxLayout()
        self._manual_edit = QLineEdit()
        browse_button = QPushButton("Browse...")
        add_button = QPushButton("Add")
        browse_button.clicked.connect(self._browse_for_exe)
        add_button.clicked.connect(lambda: self._add_manual_entry(self._manual_edit.text()))
        self._manual_edit.returnPressed.connect(lambda: self._add_manual_entry(self._manual_edit.text()))
        manual_row.addWidget(self._manual_edit)
        manual_row.addWidget(browse_button)
        manual_row.addWidget(add_button)
        layout.addLayout(manual_row)

        self._manual_status = QLabel()
        self._manual_status.setStyleSheet("color: #c62828;")
        layout.addWidget(self._manual_status)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #2e7d32;")
        layout.addWidget(self._status_label)

        button_label = "Add Selected to Session" if self._session_active else "Save Whitelist"
        save_button = QPushButton(button_label)
        save_button.clicked.connect(self._save)
        layout.addWidget(save_button, alignment=Qt.AlignCenter)

    def _add_quick_readd_rows(self):
        # Only offered when picking the whitelist for the *next* session, not
        # mid-session -- a quick way to re-check whatever the previous
        # session actually ended up whitelisting.
        history = session_history.load_all()
        prev_session = history[-1] if history else None
        prev_additions = prev_session.get("processWhitelistAdditions", []) if prev_session else []
        prev_apps = prev_session.get("processWhitelist", []) if prev_session else []

        if prev_additions:
            self._checklist.add_separator_label("Added mid-session last time — quick re-add:")
            for addition in prev_additions:
                process_name = addition.get("process")
                if not process_name:
                    continue
                reason = addition.get("reason")
                label = f"{process_name}   — {reason}" if reason else process_name
                self._checklist.add_row(process_name, label, checked=False)

        if prev_apps:
            self._checklist.add_separator_label("From your last session — quick re-add:")
            for process_name in prev_apps:
                self._checklist.add_row(process_name, process_name, checked=False)

    def _add_manual_entry(self, process_name):
        # Reduce to just the basename even for a typed (not browsed) entry --
        # is_whitelisted() and enforcement everywhere else compare on
        # process name alone, never a full path.
        process_name = os.path.basename(process_name.strip())
        if not process_name:
            self._manual_status.setText("Enter an exe name or browse for a file.")
            return
        if not process_name.lower().endswith(".exe"):
            self._manual_status.setText("Process name must end in .exe.")
            return
        self._checklist.add_row(process_name, process_name, checked=True)
        self._manual_status.setText("")
        self._manual_edit.setText("")

    def _browse_for_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick an executable", "", "Executables (*.exe);;All files (*.*)"
        )
        if path:
            self._add_manual_entry(os.path.basename(path))

    def _save(self):
        selected = self._checklist.checked_keys()

        if self._session_active:
            extras = [name for name in selected if name.lower() not in self._saved]
            if not extras:
                self._status_label.setText("No new apps selected — nothing to add.")
                return
            self.close()
            _track(_ReasonDialog(extras)).show()
            return

        current_cfg = config.load_config()
        current_cfg["processWhitelist"] = selected
        config.save_config(current_cfg)
        self._status_label.setText(f"Saved {len(selected)} app(s) to the whitelist.")


class _ReasonDialog(QWidget):
    """Second page shown after saving mid-session extras -- one reason field
    per newly selected app, all required, before add_process_to_whitelist()
    actually applies any of them."""

    def __init__(self, process_names):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setObjectName("PopupBg")
        self.setWindowTitle("Carmen Focus — Explain Additions")
        self.resize(440, 480)
        self._process_names = process_names

        layout = QVBoxLayout(self)

        prompt = QLabel("Why does each of these need to be added to this session?")
        prompt.setWordWrap(True)
        prompt.setAlignment(Qt.AlignCenter)
        layout.addWidget(prompt)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        content.setObjectName("PopupBg")
        content_layout = QVBoxLayout(content)
        self._reason_edits = {}
        for process_name in process_names:
            name_label = QLabel(process_name)
            name_label.setStyleSheet("font-weight: bold;")
            content_layout.addWidget(name_label)
            edit = QLineEdit()
            content_layout.addWidget(edit)
            self._reason_edits[process_name] = edit
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #c62828;")
        layout.addWidget(self._status_label)

        button_row = QHBoxLayout()
        confirm_button = QPushButton("Confirm")
        cancel_button = QPushButton("Cancel")
        confirm_button.clicked.connect(self._confirm)
        cancel_button.clicked.connect(self.close)
        button_row.addStretch(1)
        button_row.addWidget(confirm_button)
        button_row.addWidget(cancel_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def _confirm(self):
        reasons = {name: edit.text().strip() for name, edit in self._reason_edits.items()}
        missing = [name for name, reason in reasons.items() if not reason]
        if missing:
            self._status_label.setText(f"Enter a reason for: {', '.join(missing)}")
            return

        added = 0
        for process_name, reason in reasons.items():
            _, addition = session_manager.add_process_to_whitelist(process_name, reason)
            if addition is not None:
                added += 1

        self.close()
        if added < len(reasons):
            # Session ended mid-form (naturally, nuclear, or via the API)
            # before every entry could be applied.
            QMessageBox.warning(
                None, "Carmen Focus",
                f"Session ended before all apps could be added — "
                f"{added} of {len(reasons)} were whitelisted.",
            )
        else:
            QMessageBox.information(
                None, "Carmen Focus", f"Added {added} app(s) to the session whitelist."
            )


class _TimerDialog(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setObjectName("PopupBg")
        self.setWindowTitle("Carmen Focus — Start Session")
        self.resize(300, 260)

        cfg = config.load_config()
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Duration (minutes)"))
        self._duration_edit = QLineEdit(str(cfg.get("last_duration_minutes", 25)))
        self._duration_edit.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._duration_edit)

        layout.addWidget(QLabel("Lock mode"))
        mode_row = QHBoxLayout()
        self._soft_radio = QRadioButton("Soft")
        self._hard_radio = QRadioButton("Hard")
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._soft_radio)
        mode_group.addButton(self._hard_radio)
        if cfg.get("last_lock_mode", "soft") == "hard":
            self._hard_radio.setChecked(True)
        else:
            self._soft_radio.setChecked(True)
        mode_row.addWidget(self._soft_radio)
        mode_row.addWidget(self._hard_radio)
        layout.addLayout(mode_row)

        process_count = len(cfg.get("processWhitelist", []))
        count_label = QLabel(f"Using saved whitelist: {process_count} app(s)")
        count_label.setStyleSheet("color: #888;")
        layout.addWidget(count_label)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #c62828;")
        layout.addWidget(self._status_label)

        start_button = QPushButton("Start Session")
        start_button.clicked.connect(self._start)
        layout.addWidget(start_button, alignment=Qt.AlignCenter)

    def _start(self):
        try:
            duration_minutes = float(self._duration_edit.text())
            if duration_minutes <= 0:
                raise ValueError
        except ValueError:
            self._status_label.setText("Enter a valid duration.")
            return

        lock_mode = "hard" if self._hard_radio.isChecked() else "soft"
        current_cfg = config.load_config()
        process_whitelist = current_cfg.get("processWhitelist", [])
        domain_whitelist = current_cfg.get("domainWhitelist", [])

        # Calls the same function POST /session/start uses, so this session
        # is immediately visible to the browser extension via GET /status.
        session_manager.start_session(duration_minutes, lock_mode, process_whitelist, domain_whitelist)

        current_cfg["last_duration_minutes"] = duration_minutes
        current_cfg["last_lock_mode"] = lock_mode
        config.save_config(current_cfg)

        self.close()
