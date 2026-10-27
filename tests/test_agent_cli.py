import datetime as dt

import pytest

pytest.importorskip("langgraph")

from helpers import start  # noqa: E402

from xauusd_trader.agent.cli import retryable, seconds_to_next_bar, window_end  # noqa: E402
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
