"""Widget-level tests for the ported tray nuclear-end dialog
(qt_ui/nuclear_dialog.py)."""
from unittest.mock import MagicMock

import qt_ui.nuclear_dialog as nuclear_dialog
import session_manager


def _fake_icon():
    icon = MagicMock()
    return icon


def test_empty_reason_does_not_end_session(qtbot, isolate_state):
    session_manager.start_session(25, "soft", [], [])
    icon = _fake_icon()

    win = nuclear_dialog._NuclearReasonDialog(icon, format_end_summary=lambda s: "summary")
    qtbot.addWidget(win)

    win._confirm()

    assert "reason" in win._status_label.text().lower()
    assert session_manager.is_active()
    icon.notify.assert_not_called()


def test_reason_given_ends_session_and_notifies(qtbot, isolate_state):
    session_manager.start_session(25, "soft", [], [])
    icon = _fake_icon()

    win = nuclear_dialog._NuclearReasonDialog(icon, format_end_summary=lambda s: "summary text")
    qtbot.addWidget(win)
    win._reason_edit.setText("needed a break")
    win._confirm()

    assert not session_manager.is_active()
    icon.notify.assert_called_once()
    icon.update_menu.assert_called_once()
