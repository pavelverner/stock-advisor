"""
Deník obchodů – ukládá záznamy nákupů/prodejů a počítá P&L.

Úložiště (automaticky vybráno v pořadí priority):
  1. PostgreSQL – pokud je nastaven DATABASE_URL v Streamlit secrets / env
                  Funguje s Supabase, Neon, Railway, atd. (všechny mají free tier)
                  Data přežijí restarty Streamlit Cloud.
  2. Google Sheets – pokud je nastaven GSHEETS_URL + GSHEETS_CREDS (service account JSON)
  3. SQLite (lokálně) – fallback pro lokální vývoj.

Nastavení persistentního úložiště (doporučeno: Supabase):
  1. Registruj se na supabase.com (zdarma, 500 MB)
  2. Vytvoř nový projekt → Settings → Database → Connection string (URI)
  3. Zkopíruj URI a ulož jako DATABASE_URL do Streamlit secrets:
       DATABASE_URL = "postgresql://postgres:[heslo]@[host]:5432/postgres"
"""
import os
import json
import sqlite3
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "trades.db"

COLS = ["id", "date", "ticker", "name", "action", "price", "shares",
        "total", "signal_str", "reasons", "note"]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id         SERIAL PRIMARY KEY,
    date       TEXT    NOT NULL,
    ticker     TEXT    NOT NULL,
    name       TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    price      REAL    NOT NULL,
    shares     REAL    NOT NULL,
    total      REAL    NOT NULL,
    signal_str REAL,
    reasons    TEXT,
    note       TEXT
)
"""

# ── Detekce backendu ──────────────────────────────────────────────────────────

def _get_secret(key: str) -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, "")


def _use_pg() -> bool:
    return bool(_get_secret("DATABASE_URL"))


def _use_sheets() -> bool:
    return bool(_get_secret("GSHEETS_URL")) and bool(_get_secret("GSHEETS_CREDS"))


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND A – PostgreSQL (Supabase / Neon / Railway…)
# ══════════════════════════════════════════════════════════════════════════════

def _pg_conn():
    import psycopg2
    import psycopg2.pool
    import streamlit as st

    @st.cache_resource
    def _pool(url: str):
        return psycopg2.pool.SimpleConnectionPool(1, 5, url)

    pool = _pool(_get_secret("DATABASE_URL"))
    con  = pool.getconn()
    con.autocommit = False
    return con, pool


def _pg_put(con, pool):
    """Vrátí spojení zpět do poolu."""
    try:
        pool.putconn(con)
    except Exception:
        pass


def _pg_init():
    con, pool = _pg_conn()
    try:
        with con.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id         SERIAL PRIMARY KEY,
                    date       TEXT    NOT NULL,
                    ticker     TEXT    NOT NULL,
                    name       TEXT    NOT NULL,
                    action     TEXT    NOT NULL,
                    price      REAL    NOT NULL,
                    shares     REAL    NOT NULL,
                    total      REAL    NOT NULL,
                    signal_str REAL,
                    reasons    TEXT,
                    note       TEXT
                )
            """)
        con.commit()
    finally:
        _pg_put(con, pool)


def _pg_get_all() -> pd.DataFrame:
    try:
        _pg_init()
        con, pool = _pg_conn()
        try:
            df = pd.read_sql("SELECT * FROM trades ORDER BY date DESC", con)
        finally:
            _pg_put(con, pool)
        return df
    except Exception as e:
        _log(f"PG read error: {e}")
        return pd.DataFrame(columns=COLS)


def _pg_append(row: dict) -> int:
    try:
        _pg_init()
        con, pool = _pg_conn()
        try:
            with con.cursor() as cur:
                cur.execute(
                    """INSERT INTO trades (date, ticker, name, action, price, shares, total,
                       signal_str, reasons, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id""",
                    (row["date"], row["ticker"], row["name"], row["action"],
                     row["price"], row["shares"], row["total"],
                     row.get("signal_str", 0), row.get("reasons", "[]"), row.get("note", "")),
                )
                new_id = cur.fetchone()[0]
            con.commit()
        finally:
            _pg_put(con, pool)
        return new_id
    except Exception as e:
        _log(f"PG append error: {e}")
        return -1


def _pg_delete(trade_id: int):
    try:
        con, pool = _pg_conn()
        try:
            with con.cursor() as cur:
                cur.execute("DELETE FROM trades WHERE id = %s", (trade_id,))
            con.commit()
        finally:
            _pg_put(con, pool)
    except Exception as e:
        _log(f"PG delete error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND B – Google Sheets (service account, soukromá tabulka)
# ══════════════════════════════════════════════════════════════════════════════

def _sheets_client():
    import gspread
    import json as _json
    from google.oauth2.service_account import Credentials
    creds_json = _get_secret("GSHEETS_CREDS")
    creds_dict = _json.loads(creds_json)
    scopes = ["https://spreadsheets.google.com/feeds",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    url = _get_secret("GSHEETS_URL")
    sh  = gc.open_by_url(url)
    try:
        ws = sh.worksheet("Obchody")
    except Exception:
        ws = sh.add_worksheet(title="Obchody", rows=1000, cols=len(COLS))
        ws.append_row(COLS)
    return ws


def _sheets_get_all() -> pd.DataFrame:
    try:
        ws = _sheets_client()
        data = ws.get_all_records()
        if not data:
            return pd.DataFrame(columns=COLS)
        return pd.DataFrame(data)
    except Exception as e:
        _log(f"Sheets read error: {e}")
        return pd.DataFrame(columns=COLS)


def _sheets_append(row: dict):
    try:
        ws = _sheets_client()
        df = _sheets_get_all()
        new_id = int(df["id"].max()) + 1 if not df.empty and "id" in df.columns and len(df) else 1
        row["id"] = new_id
        ws.append_row([row.get(c, "") for c in COLS])
        return new_id
    except Exception as e:
        _log(f"Sheets append error: {e}")
        return -1


def _sheets_delete(trade_id: int):
    try:
        ws = _sheets_client()
        df = _sheets_get_all()
        if df.empty:
            return
        idx = df.index[df["id"].astype(str) == str(trade_id)].tolist()
        if idx:
            ws.delete_rows(idx[0] + 2)
    except Exception as e:
        _log(f"Sheets delete error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND C – SQLite (lokální fallback)
# ══════════════════════════════════════════════════════════════════════════════

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT    NOT NULL,
                ticker     TEXT    NOT NULL,
                name       TEXT    NOT NULL,
                action     TEXT    NOT NULL,
                price      REAL    NOT NULL,
                shares     REAL    NOT NULL,
                total      REAL    NOT NULL,
                signal_str REAL,
                reasons    TEXT,
                note       TEXT
            )
        """)


def _sqlite_get_all() -> pd.DataFrame:
    init_db()
    with _conn() as con:
        return pd.read_sql("SELECT * FROM trades ORDER BY date DESC", con)


def _sqlite_append(row: dict) -> int:
    init_db()
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO trades (date, ticker, name, action, price, shares, total,
               signal_str, reasons, note) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (row["date"], row["ticker"], row["name"], row["action"],
             row["price"], row["shares"], row["total"],
             row.get("signal_str", 0), row.get("reasons", "[]"), row.get("note", "")),
        )
        return cur.lastrowid


def _sqlite_delete(trade_id: int):
    init_db()
    with _conn() as con:
        con.execute("DELETE FROM trades WHERE id = ?", (trade_id,))


# ══════════════════════════════════════════════════════════════════════════════
# Veřejné API (volá app.py)
# ══════════════════════════════════════════════════════════════════════════════

def _log(msg: str):
    print(f"[trade_journal] {msg}")


def add_trade(
    ticker: str,
    name: str,
    action: str,
    price: float,
    shares: float,
    signal_strength: float = 0.0,
    reasons: list | None = None,
    note: str = "",
    date: str | None = None,
) -> int:
    row = {
        "date":       date or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ticker":     ticker.upper(),
        "name":       name,
        "action":     action.upper(),
        "price":      price,
        "shares":     shares,
        "total":      round(price * shares, 4),
        "signal_str": signal_strength,
        "reasons":    json.dumps(reasons or [], ensure_ascii=False),
        "note":       note,
    }
    if _use_pg():
        return _pg_append(row)
    if _use_sheets():
        return _sheets_append(row)
    return _sqlite_append(row)


def get_trades() -> pd.DataFrame:
    if _use_pg():
        return _pg_get_all()
    if _use_sheets():
        return _sheets_get_all()
    return _sqlite_get_all()


def delete_trade(trade_id: int):
    if _use_pg():
        _pg_delete(trade_id)
    elif _use_sheets():
        _sheets_delete(trade_id)
    else:
        _sqlite_delete(trade_id)


def import_from_csv(csv_bytes: bytes) -> int:
    import io
    df = pd.read_csv(io.BytesIO(csv_bytes))
    required = {"ticker", "name", "action", "price", "shares"}
    if not required.issubset(df.columns):
        raise ValueError(f"CSV musí obsahovat sloupce: {required}")
    count = 0
    for _, row in df.iterrows():
        try:
            reasons = json.loads(row["reasons"]) if "reasons" in row and pd.notna(row.get("reasons")) else []
        except Exception:
            reasons = []
        add_trade(
            ticker=str(row["ticker"]),
            name=str(row.get("name", row["ticker"])),
            action=str(row["action"]),
            price=float(row["price"]),
            shares=float(row["shares"]),
            signal_strength=float(row.get("signal_str", 0) or 0),
            reasons=reasons,
            note=str(row.get("note", "") or ""),
            date=str(row.get("date", "")) or None,
        )
        count += 1
    return count


# ── Výkonnostní analýza ───────────────────────────────────────────────────────

def _current_price(ticker: str) -> float | None:
    try:
        df = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
        if df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return float(df["Close"].iloc[-1])
    except Exception:
        return None


def get_performance(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    rows = []
    for _, r in df.iterrows():
        cur    = _current_price(r["ticker"])
        entry  = float(r["price"])
        shares = float(r["shares"])
        action = r["action"]

        if action == "BUY" and cur is not None:
            pnl_pct = (cur - entry) / entry * 100
            pnl_abs = (cur - entry) * shares
            status  = "Otevřená"
        elif action == "BUY":
            pnl_pct = pnl_abs = None
            status  = "Data N/A"
        else:
            pnl_pct = pnl_abs = None
            cur     = None
            status  = "Prodej"

        try:
            reasons = json.loads(r.get("reasons") or "[]")
        except Exception:
            reasons = []

        rows.append({
            "id":          r["id"],
            "Datum":       str(r["date"])[:10],
            "Název":       r["name"],
            "Ticker":      r["ticker"],
            "Akce":        action,
            "Vstup":       entry,
            "Počet":       shares,
            "Investováno": entry * shares,
            "Aktuální":    cur,
            "P&L %":       pnl_pct,
            "P&L Kč/USD":  pnl_abs,
            "Status":      status,
            "Poznámka":    r.get("note", ""),
            "Důvody":      " · ".join(reasons[:2]) if reasons else "",
        })

    return pd.DataFrame(rows)


def get_stats(perf_df: pd.DataFrame) -> dict:
    if perf_df.empty:
        return {}

    open_pos = perf_df[perf_df["Status"] == "Otevřená"]
    if open_pos.empty:
        return {"total_trades": len(perf_df), "open_positions": 0}

    pnl      = open_pos["P&L %"].dropna()
    abs_pnl  = open_pos["P&L Kč/USD"].dropna()
    invested = open_pos["Investováno"].sum()
    winners  = (pnl > 0).sum()
    total    = len(pnl)

    return {
        "total_trades":   len(perf_df),
        "open_positions": total,
        "win_rate":       winners / total * 100 if total else 0,
        "winners":        int(winners),
        "losers":         int((pnl < 0).sum()),
        "total_pnl_abs":  float(abs_pnl.sum()),
        "total_invested": float(invested),
        "total_pnl_pct":  float(abs_pnl.sum() / invested * 100) if invested else 0,
        "best_trade":     float(pnl.max()) if not pnl.empty else 0,
        "worst_trade":    float(pnl.min()) if not pnl.empty else 0,
        "avg_pnl":        float(pnl.mean()) if not pnl.empty else 0,
    }
