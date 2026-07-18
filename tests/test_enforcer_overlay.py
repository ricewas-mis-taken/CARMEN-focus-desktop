"""Widget-level tests for the ported lock-overlay (qt_ui/enforcer_overlay.py)
-- the highest-priority Stage 1 port since it's the security-relevant
enforcement UI. Verifies window flags (frameless, always-on-top, non-modal),
the double-close guard, and the offending-process-name-gated Whitelist
button, without needing a real session or the real polling thread."""
from PySide6.QtCore import Qt

import qt_ui.enforcer_overlay as enforcer_overlay


def test_overlay_is_frameless_topmost_and_non_modal(qtbot, isolate_state):
    win = enforcer_overlay.build_overlay("test message", duration_ms=200)
    qtbot.addWidget(win)

    assert win.windowFlags() & Qt.FramelessWindowHint
    assert win.windowFlags() & Qt.WindowStaysOnTopHint
    # Never modal -- a system-wide input grab would freeze every other app,
    # not just the offending one (see enforcer.py's docstrings).
    assert win.windowModality() == Qt.NonModal

    win.close()


def test_overlay_close_is_idempotent(qtbot, isolate_state):
    win = enforcer_overlay.build_overlay("test message", duration_ms=200)
    qtbot.addWidget(win)

    win.close()
    win.close()  # must not raise, matches the Tk version's state["closed"] guard
    assert win._closed is True


def test_overlay_without_process_name_has_no_whitelist_button(qtbot, isolate_state):
    win = enforcer_overlay.build_overlay("test message", duration_ms=200)
    qtbot.addWidget(win)

    from PySide6.QtWidgets import QPushButton
    buttons = win.findChildren(QPushButton)
    assert not any(b.text() == "Whitelist" for b in buttons)
    win.close()


def test_overlay_with_process_name_has_whitelist_button(qtbot, isolate_state):
    win = enforcer_overlay.build_overlay("test message", duration_ms=200, offending_process_name="bad.exe")
    qtbot.addWidget(win)

    from PySide6.QtWidgets import QPushButton
    buttons = win.findChildren(QPushButton)
    assert any(b.text() == "Whitelist" for b in buttons)
    win.close()


def test_overlay_auto_closes_after_duration(qtbot, isolate_state):
    win = enforcer_overlay.build_overlay("test message", duration_ms=100)
    qtbot.addWidget(win)

    qtbot.waitUntil(lambda: win._closed, timeout=2000)


def test_whitelist_reason_dialog_requires_reason(qtbot, isolate_state):
    win = enforcer_overlay.build_whitelist_reason_dialog("app.exe")
    qtbot.addWidget(win)

    win._confirm()
    assert "reason" in win._status_label.text().lower()
    assert win.isVisible()
    win.close()


def test_whitelist_reason_dialog_confirm_calls_add_process_to_whitelist(qtbot, isolate_state):
    import session_manager

    session_manager.start_session(25, "soft", ["good.exe"], [])

    win = enforcer_overlay.build_whitelist_reason_dialog("app.exe")
    qtbot.addWidget(win)
    win._reason_edit.setText("needed for research")
    win._confirm()

    status = session_manager.get_status()
    assert "app.exe" in status["processWhitelist"]
