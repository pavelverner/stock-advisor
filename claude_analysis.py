"""
AI analýza pomocí Claude API.
Funkce 1: Přirozený jazyk – shrnutí situace
Funkce 2: Detekce tržních událostí ze zpráv
Funkce 3: Porovnání s konkurencí (peer comparison)
"""
import os
import json
import yfinance as yf
import pandas as pd
import anthropic

# ── Peer skupiny pro portfolio ────────────────────────────────────────────────
PEER_GROUPS = {
    "NVDA":     {"name": "NVIDIA",            "peers": ["AMD", "INTC", "TSM", "AVGO", "QCOM"]},
    "AMD":      {"name": "AMD",               "peers": ["NVDA", "INTC", "TSM", "AVGO"]},
    "GOOGL":    {"name": "Alphabet",          "peers": ["META", "MSFT", "AMZN", "AAPL"]},
    "MSFT":     {"name": "Microsoft",         "peers": ["GOOGL", "AMZN", "CRM", "NOW", "ORCL"]},
    "PANW":     {"name": "Palo Alto",         "peers": ["CRWD", "FTNT", "ZS", "S"]},
    "AMZN":     {"name": "Amazon",            "peers": ["GOOGL", "MSFT", "BABA", "SHOP"]},
    "TSM":      {"name": "Taiwan Semi",       "peers": ["NVDA", "INTC", "AVGO", "AMAT"]},
    "VUSA.L":   {"name": "Vanguard S&P500",   "peers": ["CSPX.L", "SPY", "IVV"]},
    "IWDA.AS":  {"name": "iShares MSCI World","peers": ["SWDA.L", "VEA", "ACWI"]},
    "SAAB-B.ST":{"name": "SAAB",             "peers": ["RHM.DE", "LMT", "RTX", "BA.L"]},
    "RHM.DE":   {"name": "Rheinmetall",       "peers": ["SAAB-B.ST", "LMT", "NOC", "BA.L"]},
}


def _get_client() -> anthropic.Anthropic | None:
    """Vrátí Anthropic klienta nebo None pokud není API klíč."""
    # 1. Streamlit secrets
    try:
        import streamlit as st
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if key:
            return anthropic.Anthropic(api_key=key)
    except Exception:
        pass
    # 2. Env proměnná
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return anthropic.Anthropic(api_key=key)
    return None


def analyze_stock_with_claude(
    ticker: str,
    signals: dict,
    news: list[dict],
    ai_sentiment: dict,
    macro: dict | None = None,
) -> dict:
    """
    Funkce 1 + 2: Claude API analýza – shrnutí + detekce událostí.
    Vrátí: {summary, events, risk_factors, opportunity, confidence}
    """
    client = _get_client()
    if client is None:
        return {"ok": False, "error": "Chybí ANTHROPIC_API_KEY"}

    # Připrav kontext pro Claude
    action = signals.get("action", "HOLD")
    rsi = signals.get("rsi", 50)
    ema_trend = ("rostoucí" if signals.get("ema20", 0) > signals.get("ema50", 0) > signals.get("ema200", 0)
                 else "klesající" if signals.get("ema20", 0) < signals.get("ema50", 0) < signals.get("ema200", 0)
                 else "smíšený")

    buy_signals  = signals.get("buy_signals", [])
    sell_signals = signals.get("sell_signals", [])

    # Top 10 titulků zpráv
    headlines = [n.get("title", "") for n in news[:10] if n.get("title")]
    headlines_str = "\n".join(f"- {h}" for h in headlines) if headlines else "Žádné zprávy."

    # Sentiment
    sentiment_score = ai_sentiment.get("score", 0)
    sentiment_label = ai_sentiment.get("dominant", "neutral")
    n_pos = ai_sentiment.get("positive", 0)
    n_neg = ai_sentiment.get("negative", 0)

    # Volume anomálie
    vol_info = signals.get("volume_anomaly", {})
    vol_str = ""
    if vol_info.get("is_anomaly"):
        vol_str = f"POZOR: Nezvyklý objem obchodování – {vol_info.get('ratio', 1):.1f}x průměr!"

    prompt = f"""Jsi analytik finančních trhů. Analyzuj tuto situaci pro akcii {ticker} a odpověz v češtině.

TECHNICKÁ ANALÝZA:
- Signál: {action} (BUY signálů: {len(buy_signals)}, SELL signálů: {len(sell_signals)})
- RSI: {rsi:.1f} (pod 30 = přeprodaná, nad 70 = překoupená)
- Trend (EMA): {ema_trend}
- BUY důvody: {', '.join(buy_signals) if buy_signals else 'žádné'}
- SELL důvody: {', '.join(sell_signals) if sell_signals else 'žádné'}
{vol_str}

SENTIMENT ZPRÁV (FinBERT AI):
- Skóre: {sentiment_score:+.2f} (-1=velmi negativní, +1=velmi pozitivní)
- Celkový tón: {sentiment_label} ({n_pos} pozitivní, {n_neg} negativní)

AKTUÁLNÍ ZPRÁVY:
{headlines_str}

Odpověz PŘESNĚ v tomto JSON formátu (bez markdown backticks):
{{
  "summary": "2-3 věty shrnující celkovou situaci pro investora – co se děje a proč",
  "events": ["konkrétní tržní událost 1", "konkrétní tržní událost 2"],
  "risk_factors": ["riziko 1", "riziko 2"],
  "opportunity": "Jedna věta o příležitosti nebo varování pro investora",
  "confidence": "nízká|střední|vysoká",
  "action_hint": "koupit|prodat|čekat|sledovat"
}}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()

        # Očisti případné markdown bloky
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        data = json.loads(text)
        data["ok"] = True
        return data

    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON parse error: {e}", "raw": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_peer_comparison(ticker: str, period: str = "3mo") -> dict:
    """
    Funkce 3: Porovnání s konkurencí.
    Vrátí výkonnost tickeru vs. peers za dané období.
    """
    peer_info = PEER_GROUPS.get(ticker)
    if not peer_info:
        return {"ok": False, "error": "Žádná peer skupina pro tento ticker"}

    all_tickers = [ticker] + peer_info["peers"]
    results = {}

    for t in all_tickers:
        try:
            df = yf.download(t, period=period, auto_adjust=True, progress=False)
            if df.empty or len(df) < 5:
                continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            price_start = float(df["Close"].iloc[0])
            price_end   = float(df["Close"].iloc[-1])
            price_now   = price_end
            chg = (price_end - price_start) / price_start * 100

            # Normalizovaná série (báze = 100)
            normalized = (df["Close"] / price_start * 100).tolist()
            dates      = [str(d.date()) for d in df.index]

            results[t] = {
                "chg_pct":    round(chg, 2),
                "price":      round(price_now, 2),
                "normalized": normalized,
                "dates":      dates,
                "is_main":    t == ticker,
            }
        except Exception:
            pass

    if not results:
        return {"ok": False, "error": "Nepodařilo se načíst peer data"}

    # Rank podle výkonnosti
    ranked = sorted(results.items(), key=lambda x: -x[1]["chg_pct"])
    main_rank = next((i + 1 for i, (t, _) in enumerate(ranked) if t == ticker), None)

    return {
        "ok":        True,
        "ticker":    ticker,
        "name":      peer_info["name"],
        "peers":     peer_info["peers"],
        "results":   results,
        "ranked":    [(t, d["chg_pct"]) for t, d in ranked],
        "main_rank": main_rank,
        "total":     len(results),
        "period":    period,
    }
