# Orders through the MT5 MCP server (demo first)

Preconditions: risk.json says PASS with the hash of the current plan.json and is not expired; the account is a demo account (confirm via `get_account_info`); the MCP order tools are set to "Needs approval".

1. Re-read live prices with `get_symbol_info_tick`. If price moved more than about 0.5 x the stop distance from the plan entry, stop and re-plan. Do not chase.
2. Show a plain ticket: symbol, side, lots, entry ~, stop, take-profit, max loss at stop in account currency, flat-by time. Ask the user to reply **yes** to that exact ticket. Anything else = no order.
3. Build the request for the `mcp-metatrader5-server` (Qoyyuum) tools. Fields are **flat** (do not wrap in `"request"`) and **integers**, not names: `action` 1 (market deal), `type` 0 (buy) or 1 (sell), `price` = ask for buy / bid for sell, `volume` in lots, `sl`, `tp`, `deviation` about 20, `magic` 777001, `comment` "xauusd-skill" (max 31 chars). Omit optional fields instead of passing 0 or null.
4. Call `order_check` first (retcode 0 = OK). `type_filling` is 0 FOK, 1 IOC, 2 RETURN; the server auto-detects it when omitted, so only set it if the check complains. Only then `order_send`. Success retcodes are 10009 (done) and 10010 (partial). The app will ask for approval again; that is the second safety net.
5. Report the result (ticket, fill price, retcode) and run `journal.py add --ticket N --fill PRICE`.
6. Closing: `positions_get`, send the opposite market order referencing the position ticket, then `journal.py close`. At `flat_by` NY, remind the user to flatten everything. Never widen a stop.
   Filling gotcha: the symbol's `filling_mode` is a bit flag (1 = FOK allowed, 2 = IOC allowed), while the order's `type_filling` is an enum (0 FOK, 1 IOC, 2 RETURN). Vantage XAUUSD reports `filling_mode` 2, so orders need `type_filling` 1 (IOC), not 2.
7. Never loop orders, never place pending/averaging orders the plan did not define, never trade a second position because the first one is losing.
