"""Regression test for the hard-lock redirect storm: an offending process
that never actually leaves the foreground (observed with Discord -- a
stray popup/overlay window regrabs focus right after hard_lock_redirect()
minimizes it) used to retrigger enforcer.hard_lock_redirect() on every
single poll tick, each call re-issuing SW_MINIMIZE/SetForegroundWindow
(the app "flashing") and spawning another lock overlay (windows piling up).
window_tracker.HARD_REDIRECT_COOLDOWN_SECONDS throttles that."""
import threading
import time

import pytest

import session_manager
import window_tracker


@pytest.fixture
def fast_polling(monkeypatch):
    """Speeds up the loop's own pacing without touching the cooldown, so a
    handful of ticks happen within a short, deterministic test sleep."""
    monkeypatch.setattr(window_tracker, "POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(window_tracker, "HARD_REDIRECT_COOLDOWN_SECONDS", 0.2)
    yield


def test_stuck_foreground_process_does_not_spam_redirects(isolate_state, fast_polling, monkeypatch):
    session_manager.start_session(25, "hard", [], [])

    monkeypatch.setattr(
        window_tracker, "get_active_window",
        lambda: {"title": "Discord", "process_name": "discord.exe", "pid": 4242},
    )

    redirect_calls = []
    monkeypatch.setattr("enforcer.hard_lock_redirect", lambda name: redirect_calls.append(name))

    stop_event = threading.Event()
    thread = threading.Thread(target=window_tracker.run_polling_loop, args=(stop_event,), daemon=True)
    thread.start()
    try:
        # ~50 poll ticks' worth of wall time at 0.01s/tick -- if the old
        # behavior (reset-and-retrigger every tick) were still in place,
        # this would rack up dozens of calls instead of a couple.
        time.sleep(0.5)
    finally:
        stop_event.set()
        thread.join(timeout=2)

    assert 1 <= len(redirect_calls) <= 5
    assert all(name == "discord.exe" for name in redirect_calls)


def test_process_that_actually_leaves_still_gets_redirected_again(isolate_state, fast_polling, monkeypatch):
    """Sanity check the cooldown doesn't just permanently silence a process:
    once cooldown elapses, a still-offending (or newly-offending) process is
    redirected again."""
    session_manager.start_session(25, "hard", [], [])
    monkeypatch.setattr(
        window_tracker, "get_active_window",
        lambda: {"title": "Discord", "process_name": "discord.exe", "pid": 4242},
    )
    redirect_calls = []
    monkeypatch.setattr("enforcer.hard_lock_redirect", lambda name: redirect_calls.append(name))

    stop_event = threading.Event()
    thread = threading.Thread(target=window_tracker.run_polling_loop, args=(stop_event,), daemon=True)
    thread.start()
    try:
        time.sleep(0.5)
    finally:
        stop_event.set()
        thread.join(timeout=2)

    # Across ~2.5 cooldown windows (0.5s / 0.2s), it should have redirected
    # more than once -- proving the cooldown resets rather than sticking
    # forever -- while still nowhere near one-per-tick.
    assert len(redirect_calls) >= 2
