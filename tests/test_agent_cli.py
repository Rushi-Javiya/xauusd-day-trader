import datetime as dt

import pytest

pytest.importorskip("langgraph")

from helpers import start  # noqa: E402

from xauusd_trader.agent.cli import (  # noqa: E402
    _every,
    classify,
    next_wake,
    poll_step,
    retryable,
    seconds_to_next_bar,
    seconds_to_next_poll,
    window_end,
)
from xauusd_trader.agent.graph import build_graph  # noqa: E402
from xauusd_trader.agent.llm import ScriptedLLM  # noqa: E402

D = dt.datetime
EARLY = D(2026, 1, 12, 9, 0)
LATE = D(2026, 1, 12, 11, 40)       # after the 11:30 cutoff


def res(outcome, *reasons):
    return {"outcome": outcome, "reasons": list(reasons)}


def test_window_end(cfg):
    assert window_end(EARLY, cfg) == D(2026, 1, 12, 11, 30)


@pytest.mark.parametrize("outcome", ["WAITING", "NO_SIGNAL", "CONFLICT", "STALE_DATA", "PRICE_MOVED"])
def test_transient_outcomes_are_retried(cfg, outcome):
    assert retryable(res(outcome), EARLY, cfg)


@pytest.mark.parametrize("outcome", ["PREFLIGHT_FAILED", "REFUSED", "REJECTED", "ORDER_PLACED", "ORDER_FAILED",
                                     "ORDER_CHECK_FAILED", "NOT_AUTHORIZED", "NEWS_UNCHECKED", "NO_DATA"])
def test_final_outcomes_stop_the_watch(cfg, outcome):
    assert not retryable(res(outcome), EARLY, cfg)


def test_nothing_is_retried_after_the_window_closes(cfg):
    assert not retryable(res("WAITING"), LATE, cfg)
    assert not retryable(res("NO_SIGNAL"), LATE, cfg)


def test_blocked_by_news_is_retried_but_limits_are_final(cfg):
    assert retryable(res("BLOCKED", "news blackout: CPI at 09:05 NY"), EARLY, cfg)
    assert not retryable(res("BLOCKED", "already 3 trades today (max 3)"), EARLY, cfg)
    assert not retryable(res("BLOCKED", "news blackout: CPI", "2 losses in a row today: stop trading"), EARLY, cfg)
    assert not retryable(res("BLOCKED", "worst case today -90 would break daily loss limit -100"), EARLY, cfg)


def test_seconds_to_next_bar_waits_for_the_close_plus_grace():
    assert seconds_to_next_bar(1000 * 300 + 10, 5, grace=15) == pytest.approx(305)      # 10 s into a bar
    assert seconds_to_next_bar(1000 * 300 + 299, 5, grace=15) == pytest.approx(16)      # 1 s before the close
    assert seconds_to_next_bar(1000 * 300, 5, grace=0) == pytest.approx(300)


def test_news_research_is_cached_across_watch_iterations(scenario):
    _, deps, _ = scenario
    deps.llm, deps.llm_news = ScriptedLLM("[]", "rationale"), True
    first = start(build_graph(deps))
    second = start(build_graph(deps))
    searches = [c for c in deps.llm.calls if c["web_search"]]
    assert len(searches) == 1
    assert any("cached" in line for line in second["log"]) and not any("cached" in line for line in first["log"])


# ---- always-on scheduling --------------------------------------------------
MON, FRI = D(2026, 1, 12), D(2026, 1, 16)     # a Monday and the Friday of the same week


def at(day, hh, mm=0):
    return day.replace(hour=hh, minute=mm)


def test_next_wake_before_the_session_is_ten_minutes_before_the_range(cfg):
    assert next_wake(at(MON, 0, 45), cfg) == at(MON, 8, 20)


def test_next_wake_during_the_session_is_now(cfg):
    assert next_wake(at(MON, 9, 7), cfg) == at(MON, 9, 7)
    assert next_wake(at(MON, 8, 20), cfg) == at(MON, 8, 20)


def test_next_wake_after_the_cutoff_is_tomorrow(cfg):
    assert next_wake(at(MON, 11, 30), cfg) == at(D(2026, 1, 13), 8, 20)
    assert next_wake(at(MON, 20, 0), cfg) == at(D(2026, 1, 13), 8, 20)


def test_next_wake_skips_the_weekend(cfg):
    assert next_wake(at(FRI, 15, 0), cfg) == at(D(2026, 1, 19), 8, 20)            # Friday afternoon -> Monday
    assert next_wake(at(D(2026, 1, 17), 12, 0), cfg) == at(D(2026, 1, 19), 8, 20)  # Saturday
    assert next_wake(at(D(2026, 1, 18), 23, 0), cfg) == at(D(2026, 1, 19), 8, 20)  # Sunday night


def test_next_wake_after_the_days_ticket_waits_for_tomorrow(cfg):
    assert next_wake(at(MON, 9, 7), cfg, done_today=True) == at(D(2026, 1, 13), 8, 20)
    assert next_wake(at(FRI, 9, 7), cfg, done_today=True) == at(D(2026, 1, 19), 8, 20)


def test_next_wake_follows_custom_session_times(cfg):
    cfg.update(range_start="03:00", entry_cutoff="06:30")
    assert next_wake(at(MON, 1, 0), cfg) == at(MON, 2, 50)
    assert next_wake(at(MON, 7, 0), cfg) == at(D(2026, 1, 13), 2, 50)


def test_classify_after_a_finished_attempt(cfg):
    assert classify(res("WAITING"), EARLY, cfg) == "RETRY"
    assert classify(res("ORDER_PLACED"), EARLY, cfg) == "DAY_DONE"
    assert classify(res("REJECTED"), EARLY, cfg) == "DAY_DONE"
    assert classify(res("REFUSED", "stop too tight"), EARLY, cfg) == "DAY_DONE"
    assert classify(res("BLOCKED", "already 3 trades today (max 3)"), EARLY, cfg) == "DAY_DONE"
    assert classify(res("NO_SIGNAL"), LATE, cfg) == "DAY_DONE"                    # cutoff passed: the day is over


def test_classify_config_and_safety_problems_stop_the_loop(cfg):
    assert classify(res("PREFLIGHT_FAILED", "account is not a demo account"), EARLY, cfg) == "FATAL"
    assert classify(res("PREFLIGHT_FAILED", "broker did not report contract size"), EARLY, cfg) == "FATAL"


def test_classify_terminal_not_ready_is_transient(cfg):
    assert classify(res("PREFLIGHT_FAILED", "MT5 initialize failed; is the terminal open?"), EARLY, cfg) == "BROKER_DOWN"

# ---- polling interval ------------------------------------------------------
def test_poll_defaults_to_one_bar_and_can_be_set_to_a_minute(cfg):
    assert poll_step(cfg) == 300
    cfg["poll_seconds"] = 60
    assert poll_step(cfg) == 60


def test_seconds_to_next_poll_aligns_to_the_interval_plus_grace():
    assert seconds_to_next_poll(1000 * 60 + 10, 60, grace=15) == pytest.approx(65)
    assert seconds_to_next_poll(1000 * 60 + 59, 60, grace=15) == pytest.approx(16)
    assert seconds_to_next_poll(1000 * 300 + 10, 300, grace=15) == pytest.approx(305)


def test_every_describes_the_interval(cfg):
    assert _every(cfg) == "5 minutes"
    cfg["poll_seconds"] = 60
    assert _every(cfg) == "1 minute"
    cfg["poll_seconds"] = 90
    assert _every(cfg) == "90 seconds"
