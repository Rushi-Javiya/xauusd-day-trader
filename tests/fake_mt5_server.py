"""Stand-in for mcp-metatrader5-server (same tool names and shapes) so McpBroker can be tested over real stdio."""
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

mcp = FastMCP("fake-mt5")
STATE = {"initialized": False}


class OrderRequest(BaseModel):
    action: int
    symbol: str
    volume: float
    type: int
    price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: Optional[int] = None
    magic: Optional[int] = None
    comment: Optional[str] = None
    type_filling: Optional[int] = None


@mcp.tool()
def initialize(path: str) -> bool:
    # the real server requires the terminal64.exe path
    STATE["initialized"] = True
    return True


def _need_init():
    if not STATE["initialized"]:
        raise ValueError("MT5 not initialized")


@mcp.tool()
def get_account_info() -> dict[str, Any]:
    _need_init()
    return {"trade_mode": 0, "currency": "USD", "leverage": 100, "balance": 5000.0}


@mcp.tool()
def symbol_select(symbol: str, visible: bool = True) -> bool:
    return True


@mcp.tool()
def get_symbol_info(symbol: str) -> dict[str, Any]:
    _need_init()
    return {"name": symbol, "trade_contract_size": None, "volume_min": 0.01, "filling_mode": 2}


@mcp.tool()
def get_symbol_info_tick(symbol: str) -> dict[str, Any]:
    return {"bid": 3996.94, "ask": 3997.22, "time": "2026-01-12T16:00:05+00:00"}


@mcp.tool()
def copy_rates_from_pos(symbol: str, timeframe: int, start_pos: int, count: int) -> list[dict[str, Any]]:
    _need_init()
    return [{"time": "2026-01-12T15:%02d:00+00:00" % (5 * i), "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
             "tick_volume": 10, "spread": 28, "real_volume": 0} for i in range(count)]


@mcp.tool()
def order_check(request: OrderRequest) -> dict[str, Any]:
    return {"retcode": 0, "comment": "Done", "request": request.model_dump(exclude_none=True)}


@mcp.tool()
def order_send(request: OrderRequest) -> dict[str, Any]:
    if request.volume > 1:
        raise ValueError("TRADE_RETCODE_INVALID_VOLUME - Invalid volume")
    return {"retcode": 10009, "deal": 1, "order": 42, "volume": request.volume, "price": request.price,
            "comment": "Request executed"}


if __name__ == "__main__":
    mcp.run()
