import asyncio
import os
import sys

import pytest

pytest.importorskip("langchain_mcp_adapters")

from xauusd_trader.agent.broker import BrokerError, McpBroker  # noqa: E402

SERVER = os.path.join(os.path.dirname(__file__), "fake_mt5_server.py")


def run(coro_fn):
    async def main():
        async with McpBroker(command=sys.executable, args=[SERVER], terminal_path="C:/mt5/terminal64.exe") as b:
            return await coro_fn(b)
    return asyncio.run(main())


def test_roundtrip_over_real_stdio():
    async def go(b):
        assert await b.initialize() is True
        acct = await b.account_info()
        info = await b.symbol_info("XAUUSD")
        tick = await b.tick("XAUUSD")
        rates = await b.rates("XAUUSD", 5, 3)
        return acct, info, tick, rates

    acct, info, tick, rates = run(go)
    assert acct["trade_mode"] == 0
    assert info["trade_contract_size"] is None
    assert tick["ask"] > tick["bid"]
    assert len(rates) == 3 and rates[0]["time"].startswith("2026-01-12T15")


def test_state_persists_across_calls_in_one_session():
    async def go(b):
        with pytest.raises(BrokerError, match="not initialized"):
            await b.account_info()
        await b.initialize()
        return await b.account_info()

    assert run(go)["currency"] == "USD"


def test_orders_use_the_servers_request_schema():
    req = {"action": 1, "symbol": "XAUUSD", "volume": 0.1, "type": 0, "price": 3997.22, "sl": 3990.0, "tp": 4010.0}

    async def go(b):
        assert b._wrap_request("order_send", req) == {"request": req}
        chk = await b.order_check(req)
        res = await b.order_send(req)
        return chk, res

    chk, res = run(go)
    assert chk["retcode"] == 0 and chk["request"]["sl"] == 3990.0
    assert res["retcode"] == 10009 and res["order"] == 42


def test_server_errors_become_broker_errors():
    req = {"action": 1, "symbol": "XAUUSD", "volume": 5.0, "type": 0, "price": 1.0}

    async def go(b):
        with pytest.raises(BrokerError, match="INVALID_VOLUME"):
            await b.order_send(req)

    run(go)


def test_unknown_tool_is_reported():
    async def go(b):
        with pytest.raises(BrokerError, match="no tool"):
            await b._call("does_not_exist")

    run(go)


def test_initialize_without_terminal_path_explains_what_to_set(monkeypatch):
    monkeypatch.delenv("MT5_PATH", raising=False)

    async def main():
        async with McpBroker(command=sys.executable, args=[SERVER]) as b:
            with pytest.raises(BrokerError, match="mt5_path"):
                await b.initialize()

    asyncio.run(main())
