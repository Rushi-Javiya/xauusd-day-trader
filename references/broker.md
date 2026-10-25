# Orders through the MT5 MCP server (demo first)

Preconditions: risk.json says PASS with the hash of the current plan.json and is not expired; the account is a demo account (confirm via `get_account_info`); the MCP order tools are set to "Needs approval".

1. Re-read live prices with `get_symbol_info_tick`. If price moved more than about 0.5 x the stop distance from the plan entry, stop and re-plan. Do not chase.
2. Show a plain ticket: symbol, side, lots, entry ~, stop, take-profit, max loss at stop in account currency, flat-by time. Ask the user to reply **yes** to that exact ticket. Anything else = no order.
3. Check the tool schemas first (names/params differ between MCP servers) and build the request: market order (`TRADE_ACTION_DEAL`), type BUY/SELL, price = ask for buy / bid for sell, `sl`, `tp`, `deviation` about 20 points, `magic` 777001, `comment` "xauusd-skill".
4. Call `order_check` first. If the retcode says invalid fill mode, switch the filling type (IOC, FOK, RETURN) according to `get_symbol_info`, then re-check. Only then `order_send`. The app will ask for approval again; that is the second safety net.
5. Report the result (ticket, fill price, retcode) and run `journal.py add --ticket N --fill PRICE`.
6. Closing: `positions_get`, send the opposite market order referencing the position ticket, then `journal.py close`. At `flat_by` NY, remind the user to flatten everything. Never widen a stop.
7. Never loop orders, never place pending/averaging orders the plan did not define, never trade a second position because the first one is losing.
