"""Broker adapters. The graph only talks to the `Broker` interface, so the same agent runs against
the real MT5 MCP server (McpBroker) or a deterministic replay (PaperBroker) in tests and demos.

Completed bars only: `rates` never returns the still-forming bar."""
import datetime as dt
import json
from typing import Any, Dict, List, Optional, Protocol, Sequence

from ..common import TD, bars_from_rows, iso, parse_time


class BrokerError(RuntimeError):
    pass


class Broker(Protocol):
    replay: bool   # True for simulated brokers: skips wall-clock freshness checks

    async def initialize(self) -> bool: ...
    async def account_info(self) -> Dict[str, Any]: ...
    async def symbol_info(self, symbol: str) -> Dict[str, Any]: ...
    async def tick(self, symbol: str) -> Dict[str, Any]: ...
    async def rates(self, symbol: str, timeframe_min: int, count: int) -> List[Dict[str, Any]]: ...
    async def order_check(self, request: Dict[str, Any]) -> Dict[str, Any]: ...
    async def order_send(self, request: Dict[str, Any]) -> Dict[str, Any]: ...


# ---- MCP -------------------------------------------------------------------
def parse_tool_result(res) -> Any:
    """CallToolResult -> python object. Handles structuredContent and JSON text blocks."""
    texts = [c.text for c in (res.content or []) if getattr(c, "type", "") == "text"]
    if getattr(res, "isError", False):
        raise BrokerError(" ".join(texts) or "MCP tool error")
    sc = getattr(res, "structuredContent", None)
    if sc is not None:
        return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
    if not texts:
        return None
    vals = []
    for t in texts:
        try:
            vals.append(json.loads(t))
        except ValueError:
            vals.append(t)
    return vals[0] if len(vals) == 1 else vals


class McpBroker:
    """Talks to `mcp-metatrader5-server` over stdio. One persistent session: MT5 state (initialize)
    lives inside the server process, so a new process per call would lose it.
    Never calls `login`: attach to the terminal you are already logged in to."""
    replay = False

    def __init__(self, command: str = "uvx", args: Optional[Sequence[str]] = None, env: Optional[dict] = None):
        self.command = command
        self.args = list(args) if args is not None else ["--from", "mcp-metatrader5-server", "mt5mcp"]
        self.env = env
        self._cm = None
        self._session = None
        self._schemas: Dict[str, dict] = {}

    async def __aenter__(self):
        from langchain_mcp_adapters.client import MultiServerMCPClient
        conn: Dict[str, Any] = {"transport": "stdio", "command": self.command, "args": self.args}
        if self.env:
            conn["env"] = self.env
        self._client = MultiServerMCPClient({"mt5": conn})
        self._cm = self._client.session("mt5")
        self._session = await self._cm.__aenter__()
        listed = await self._session.list_tools()
        self._schemas = {t.name: (t.inputSchema or {}) for t in listed.tools}
        return self

    async def __aexit__(self, *exc):
        if self._cm is not None:
            await self._cm.__aexit__(*exc)

    @property
    def session(self):
        return self._session

    async def _call(self, name: str, args: Optional[dict] = None) -> Any:
        if name not in self._schemas:
            raise BrokerError("MCP server has no tool %r (has: %s)" % (name, ", ".join(sorted(self._schemas))))
        return parse_tool_result(await self._session.call_tool(name, args or {}))

    def _wrap_request(self, tool: str, request: dict) -> dict:
        """The docs say 'flat fields', the signature says `request: OrderRequest`. Follow the real schema."""
        props = self._schemas.get(tool, {}).get("properties", {})
        return {"request": request} if "request" in props else dict(request)

    async def initialize(self) -> bool:
        return bool(await self._call("initialize"))

    async def account_info(self):
        return await self._call("get_account_info")

    async def symbol_info(self, symbol):
        await self._call("symbol_select", {"symbol": symbol, "visible": True})
        return await self._call("get_symbol_info", {"symbol": symbol})

    async def tick(self, symbol):
        return await self._call("get_symbol_info_tick", {"symbol": symbol})

    async def rates(self, symbol, timeframe_min, count):
        # start_pos=1 skips the forming bar
        return await self._call("copy_rates_from_pos", {"symbol": symbol, "timeframe": timeframe_min,
                                                        "start_pos": 1, "count": count})

    async def order_check(self, request):
        return await self._call("order_check", self._wrap_request("order_check", request))

    async def order_send(self, request):
        return await self._call("order_send", self._wrap_request("order_send", request))


# ---- paper / replay --------------------------------------------------------
class PaperBroker:
    """Deterministic replay broker. `rows` are raw bars (server-time stamps) like the MT5 export.
    Orders fill instantly at the last close (+ spread for buys). Always a demo account."""
    replay = True

    def __init__(self, rows: List[dict], cfg: dict, as_of_ny: Optional[dt.datetime] = None,
                 spread: float = 0.28, trade_mode: int = 0, contract_size: Optional[float] = 100.0):
        self.cfg, self.spread, self.trade_mode, self.contract_size = cfg, spread, trade_mode, contract_size
        bars = bars_from_rows(rows, cfg)
        raw = sorted(rows, key=lambda r: parse_time(r["time"]))
        self._pairs = list(zip(bars, raw))
        self.as_of = as_of_ny
        self.checked: List[dict] = []
        self.sent: List[dict] = []

    def _visible(self):
        tf = TD(minutes=self.cfg["tf_minutes"])
        return [(b, r) for b, r in self._pairs if self.as_of is None or b["t"] + tf <= self.as_of]

    async def initialize(self):
        return True

    async def account_info(self):
        return {"trade_mode": self.trade_mode, "currency": self.cfg["account_ccy"], "leverage": 100,
                "balance": self.cfg["account_balance"]}

    async def symbol_info(self, symbol):
        return {"name": symbol, "digits": 2, "point": 0.01, "trade_contract_size": self.contract_size,
                "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100.0, "filling_mode": 2,
                "trade_stops_level": 20, "spread": int(self.spread * 100)}

    async def tick(self, symbol):
        vis = self._visible()
        if not vis:
            raise BrokerError("no bars")
        b, r = vis[-1]
        bid = b["c"]
        label = iso(parse_time(r["time"]) + TD(minutes=self.cfg["tf_minutes"]))
        return {"bid": bid, "ask": round(bid + self.spread, 2), "time": label}

    async def rates(self, symbol, timeframe_min, count):
        return [r for _, r in self._visible()][-count:]

    async def order_check(self, request):
        self.checked.append(request)
        return {"retcode": 0, "comment": "Done"}

    async def order_send(self, request):
        self.sent.append(request)
        n = len(self.sent)
        return {"retcode": 10009, "deal": 9000 + n, "order": 5000 + n, "volume": request["volume"],
                "price": request["price"], "comment": "paper fill"}

