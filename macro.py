"""
Makro indikátory: Fear & Greed Index, VIX, 10Y Treasury, sektorové ETF.
"""
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# ── Sektorové ETF ─────────────────────────────────────────────────────────────
SECTOR_ETFS = {
    "Technologie":         "XLK",
    "Obrana & Průmysl":    "ITA",
    "Zdravotnictví":       "XLV",
    "Finance":             "XLF",
    "Energie":             "XLE",
    "Spotřeba":            "XLY",
    "Komunikace":          "XLC",
    "Materiály":           "XLB",
    "Utility":             "XLU",
    "Reality":             "XLRE",
}

# ── Fear & Greed ──────────────────────────────────────────────────────────────
def fetch_fear_greed() -> dict:
    """Stáhne CNN Fear & Greed Index."""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        fg = data.get("fear_and_greed", {})
        score = fg.get("score", None)
        rating = fg.get("rating", "unknown")
        prev   = data.get("fear_and_greed_historical", {})
        prev_week  = None
        prev_month = None
        if "data" in prev and len(prev["data"]) > 0:
            history = sorted(prev["data"], key=lambda x: x.get("x", 0))
            if len(history) >= 5:
                prev_week = history[-5].get("y")
            if len(history) >= 21:
                prev_month = history[-21].get("y")
        return {
            "score":      round(score, 1) if score else None,
            "rating":     rating,
            "prev_week":  round(prev_week, 1) if prev_week else None,
            "prev_month": round(prev_month, 1) if prev_month else None,
            "ok":         True,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fg_label(score: float) -> tuple[str, str]:
    """(popis, barva) podle skóre."""
    if score is None:
        return "N/A", "#888"
    if score <= 25:
        return "Extreme Fear", "#ef4444"
    if score <= 45:
        return "Fear", "#f97316"
    if score <= 55:
        return "Neutral", "#eab308"
    if score <= 75:
        return "Greed", "#84cc16"
    return "Extreme Greed", "#22c55e"


# ── Makro data z yfinance ─────────────────────────────────────────────────────
def fetch_macro_tickers() -> dict:
    """VIX, S&P 500, 10Y Treasury, Gold, DXY (USD index)."""
    tickers = {
        "VIX":        "^VIX",
        "S&P 500":    "^GSPC",
        "10Y Treasury": "^TNX",
        "Gold":       "GC=F",
        "USD Index":  "DX-Y.NYB",
    }
    results = {}
    for name, sym in tickers.items():
        try:
            df = yf.download(sym, period="5d", auto_adjust=True, progress=False)
            if df.empty:
                continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            price = float(df["Close"].iloc[-1])
            prev  = float(df["Close"].iloc[-2])
            chg   = (price - prev) / prev * 100
            results[name] = {"price": price, "chg": chg, "symbol": sym}
        except Exception:
            pass
    return results


# ── Sektorové ETF ─────────────────────────────────────────────────────────────
def fetch_sectors(period: str = "1mo") -> list[dict]:
    """Výkonnost sektorových ETF za zvolené období."""
    results = []
    for name, sym in SECTOR_ETFS.items():
        try:
            df = yf.download(sym, period=period, auto_adjust=True, progress=False)
            if df.empty or len(df) < 2:
                continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            price_now  = float(df["Close"].iloc[-1])
            price_prev = float(df["Close"].iloc[-2])
            price_start = float(df["Close"].iloc[0])
            chg_day    = (price_now - price_prev) / price_prev * 100
            chg_period = (price_now - price_start) / price_start * 100
            results.append({
                "name":       name,
                "symbol":     sym,
                "price":      price_now,
                "chg_day":    chg_day,
                "chg_period": chg_period,
            })
        except Exception:
            pass
    return sorted(results, key=lambda x: -x["chg_period"])
