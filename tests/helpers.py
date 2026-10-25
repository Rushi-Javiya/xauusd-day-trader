import asyncio

from xauusd_trader import levels, strategy
from xauusd_trader import plan as planmod
from xauusd_trader.common import bars_from_rows, group_days, parse_iso

THREAD = {"configurable": {"thread_id": "t1"}}


def find_signal_time(rows, cfg):
    """A deterministic day/time where the ORB setup fires early and yields a sizable plan."""
    by_day = group_days(bars_from_rows(rows, cfg))
    for date in sorted(by_day)[20:]:
        if date.weekday() > 4 or len(by_day[date]) < 100:
            continue
        lv = levels.compute(by_day, date, cfg)
        for s in strategy.find_signals(by_day[date], lv, cfg, ("orb",)):
            p, err = planmod.price_plan(s, cfg)
            if err or planmod.size_plan(p, cfg)[0] is None:
                continue
            t = parse_iso(s["time"])
            if t.hour < 11:
                return t
    raise AssertionError("no usable signal in synthetic data")


def invoke(graph, payload):
    return asyncio.run(graph.ainvoke(payload, THREAD))


def start(graph):
    return invoke(graph, {"log": []})
