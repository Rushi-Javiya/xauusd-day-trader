"""Shared helpers: config, time conversion (broker server time -> New York), bar loading."""
import csv, json, os, datetime as dt

WORKDIR = os.environ.get("GOLD_DIR", "gold")
TD = dt.timedelta

DEFAULTS = {
    "symbol": "XAUUSD",
    "account_balance": 5000.0,
    "account_ccy": "USD",
    "account_ccy_per_usd": 1.0,      # e.g. 0.92 if your account is EUR (EUR per 1 USD)
    "max_loss_per_trade_pct": 1.0,
    "daily_loss_limit_pct": 2.0,
    "max_trades_per_day": 3,
    "max_consecutive_losses": 2,
    "min_rr": 1.0,
    "target_r": 2.0,
    "contract_size": 100,            # oz per 1.00 lot: confirm with get_symbol_info
    "volume_min": 0.01,
    "volume_step": 0.01,
    "volume_max": 5.0,
    "digits": 2,
    "spread_usd": 0.35,              # typical spread in dollars (price units)
    "min_stop_usd": 2.0,
    "min_stop_spread_mult": 4.0,
    "stop_buffer_usd": 0.30,
    "tf_minutes": 5,
    "broker_offset_winter": 2,       # broker server time = UTC+2 in winter
    "broker_offset_summer": 3,       # ... UTC+3 when US daylight saving is on
    "range_start": "08:30",          # New York time
    "range_minutes": 15,
    "entry_cutoff": "11:30",
    "flat_by": "16:30",
    "or_min_usd": 3.0,
    "or_max_usd": 25.0,
    "retest_tol_atr": 0.35,
    "retest_max_bars": 12,
    "sweep_min_atr": 0.25,
    "news_before_min": 10,
    "news_after_min": 10,
    "verdict_valid_min": 10,
    "contract_size_confirmed": False,  # agent refuses to size trades until you confirm contract_size
    "bar_time_mode": "server",       # "server": bar stamps are broker server time; "utc": already true UTC
    "history_bars": 4500,            # M5 bars the agent pulls (~16 trading days, enough for 14d ATR)
    "max_price_drift_r": 0.5,        # refuse to send if live price moved more than this x stop distance
    "require_news_check": True,      # agent blocks when gold/news.json is missing
    "llm_model": "claude-haiku-5-5",         # ticket rationale and journal review
    "llm_news_model": "claude-sonnet-5-5",   # calendar research with web search
}


def path(*p):
    return os.path.join(WORKDIR, *p)


def ensure():
    os.makedirs(WORKDIR, exist_ok=True)


def load_config():
    cfg = dict(DEFAULTS)
    p = path("config.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    return cfg


def save_json(name, obj):
    ensure()
    with open(path(name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


def load_json(name, default=None):
    p = path(name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


# ---- time ------------------------------------------------------------------
def us_dst(utc):
    """True while US daylight saving time is in force (utc is a naive UTC datetime)."""
    y = utc.year
    d = dt.datetime(y, 3, 1)
    start = d + TD(days=(6 - d.weekday()) % 7 + 7, hours=7)     # 2nd Sunday March, 02:00 EST
    d = dt.datetime(y, 11, 1)
    end = d + TD(days=(6 - d.weekday()) % 7, hours=6)           # 1st Sunday Nov, 02:00 EDT
    return start <= utc < end


def to_ny(utc):
    return utc + TD(hours=-4 if us_dst(utc) else -5)


def ny_to_utc(ny):
    u = ny + TD(hours=4)
    return u if us_dst(u) else ny + TD(hours=5)


def server_to_utc(server_dt, cfg):
    guess = server_dt - TD(hours=cfg["broker_offset_winter"])
    off = cfg["broker_offset_summer"] if us_dst(guess) else cfg["broker_offset_winter"]
    return server_dt - TD(hours=off)


def now_ny():
    return to_ny(dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))


def parse_time(v):
    if isinstance(v, (int, float)):
        return dt.datetime(1970, 1, 1) + TD(seconds=float(v))
    s = str(v).strip()
    if "T" in s and len(s) > 10:
        # ISO 8601 (e.g. from the MCP server). The tz label is ignored on purpose:
        # MT5 stamps bars in broker server time whatever the label says; see bar_time_mode.
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    if " " not in s and "T" not in s and s.replace(".", "", 1).isdigit() and len(s) >= 9:
        return dt.datetime(1970, 1, 1) + TD(seconds=float(s))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S",
                "%Y.%m.%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise ValueError("unrecognised time: %r" % (v,))


def iso(t):
    return t.strftime("%Y-%m-%d %H:%M")


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M")


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def day_key(ny):
    """Trading day: rolls over at 17:00 New York (so Asian + London + NY sessions share a key)."""
    return (ny + TD(hours=7)).date()


# ---- bars ------------------------------------------------------------------
def load_bars(file, cfg):
    """Load JSON (list or {"bars": [...]}) or CSV (incl. MT5 export) -> list of dicts t,o,h,l,c.
    Times are broker SERVER time and are converted to New York time."""
    with open(file, encoding="utf-8-sig") as f:
        if file.lower().endswith(".csv"):
            sample = f.read(2048)
            f.seek(0)
            delim = "\t" if sample.count("\t") > sample.count(",") else ","
            rows = list(csv.DictReader(f, delimiter=delim))
        else:
            data = json.load(f)
            rows = data["bars"] if isinstance(data, dict) else data
    return bars_from_rows(rows, cfg)


def bars_from_rows(rows, cfg):
    """Rows of dicts (time, open, high, low, close) -> bars with New York time.
    cfg["bar_time_mode"]: "server" converts from broker server time, "utc" treats stamps as true UTC."""
    out = []
    for r in rows:
        r = {k.strip().strip("<>").lower(): v for k, v in r.items()}
        if "date" in r and "time" in r:
            t = parse_time(str(r["date"]) + " " + str(r["time"]))
        else:
            t = parse_time(r["time"])
        utc = t if cfg.get("bar_time_mode") == "utc" else server_to_utc(t, cfg)
        out.append({"t": to_ny(utc), "o": float(r["open"]), "h": float(r["high"]),
                    "l": float(r["low"]), "c": float(r["close"])})
    out.sort(key=lambda b: b["t"])
    return out


def atr(bars, n=14):
    if len(bars) < 2:
        return None
    trs = []
    for i in range(1, len(bars)):
        pc = bars[i - 1]["c"]
        trs.append(max(bars[i]["h"] - bars[i]["l"], abs(bars[i]["h"] - pc), abs(bars[i]["l"] - pc)))
    trs = trs[-n:]
    return sum(trs) / len(trs)


def group_days(bars):
    d = {}
    for b in bars:
        d.setdefault(day_key(b["t"]), []).append(b)
    return d
