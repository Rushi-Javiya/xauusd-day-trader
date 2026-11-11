import pytest

pytest.importorskip("langgraph")

from helpers import find_signal_time, start  # noqa: E402

from xauusd_trader.agent.broker import PaperBroker  # noqa: E402
from xauusd_trader.agent.graph import Deps, build_graph  # noqa: E402
from xauusd_trader.common import TD, iso, parse_time  # noqa: E402


class FreshTerminalBroker(PaperBroker):
    """Behaves like a just-launched MT5 terminal: the first `bad_ticks` tick reads are stamped 2h early."""
    replay = False

    def __init__(self, *a, bad_ticks=0, **kw):
        super().__init__(*a, **kw)
        self.bad_ticks, self.tick_calls = bad_ticks, 0

    async def tick(self, symbol):
        t = await super().tick(symbol)
        self.tick_calls += 1
        if self.tick_calls <= self.bad_ticks:
            t = dict(t, time=iso(parse_time(t["time"]) - TD(hours=2)))
        return t


def setup(rows, cfg, bad_ticks, tries=7):
    cfg["contract_size_confirmed"] = True
    now = find_signal_time(rows, cfg)
    broker = FreshTerminalBroker(rows, cfg, as_of_ny=now, bad_ticks=bad_ticks)
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    deps = Deps(broker=broker, cfg=cfg, clock=lambda: now, news_loader=lambda: [], setups=("orb",),
                sleep=fake_sleep, sync_tries=tries, sync_wait_s=10.0, track_handled=False)
    return broker, deps, slept


def test_a_good_clock_needs_no_waiting(rows, cfg):
    broker, deps, slept = setup(rows, cfg, bad_ticks=0)
    res = start(build_graph(deps))
    assert "__interrupt__" in res and slept == [] and broker.tick_calls >= 1


def test_waits_for_a_freshly_started_terminal_to_sync_then_carries_on(rows, cfg):
    broker, deps, slept = setup(rows, cfg, bad_ticks=3)
    res = start(build_graph(deps))
    assert "__interrupt__" in res                       # got through to a ticket
    assert slept == [10.0, 10.0, 10.0]
    assert any("waited 30s for the MT5 terminal" in line for line in res["log"])


def test_gives_up_when_the_clock_never_corrects_and_trades_nothing(rows, cfg):
    broker, deps, slept = setup(rows, cfg, bad_ticks=99, tries=4)
    res = start(build_graph(deps))
    assert res["outcome"] == "PREFLIGHT_FAILED" and "bars" not in res
    assert len(slept) == 3 and broker.sent == []        # no sleep after the last attempt


def test_bars_are_never_read_before_the_clock_is_confirmed(rows, cfg):
    broker, deps, _ = setup(rows, cfg, bad_ticks=99, tries=2)
    calls = []
    orig = broker.rates

    async def spy(*a, **kw):
        calls.append(1)
        return await orig(*a, **kw)

    broker.rates = spy
    start(build_graph(deps))
    assert calls == []
