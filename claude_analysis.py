"""
AI analýza – multi-horizont (krátkodobý/střednědobý/dlouhodobý), peer comparison.

Priorita AI providera:
  1. Claude  (ANTHROPIC_API_KEY) – nejkvalitnější
  2. Groq    (GROQ_API_KEY)      – free tier, LLaMA3, velmi rychlý
  3. Gemini  (GEMINI_API_KEY)    – free tier, 1 M tokenů/den
"""
import os
import json
import yfinance as yf
import pandas as pd

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


def _get_secret(key: str) -> str:
    """Přečte klíč z Streamlit secrets nebo env proměnné."""
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, "")


# ── Provider detekce ──────────────────────────────────────────────────────────

def _get_provider() -> str | None:
    """Vrátí název dostupného AI providera v pořadí priorit: claude → groq → gemini."""
    if _get_secret("ANTHROPIC_API_KEY"):
        return "claude"
    if _get_secret("GROQ_API_KEY"):
        return "groq"
    if _get_secret("GEMINI_API_KEY"):
        return "gemini"
    return None


# ── Volání jednotlivých providerů ─────────────────────────────────────────────

def _call_claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=_get_secret("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=_get_secret("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content(prompt)
    return resp.text.strip()


def _call_groq(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=_get_secret("GROQ_API_KEY"))
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    return resp.choices[0].message.content.strip()


def _call_ai(prompt: str) -> tuple[str, str]:
    """
    Zavolá AI providera podle dostupnosti.
    Vrátí (text_odpovědi, název_providera).
    Raises RuntimeError pokud žádný provider není dostupný.
    """
    provider = _get_provider()
    if provider == "claude":
        return _call_claude(prompt), "Claude"
    if provider == "gemini":
        return _call_gemini(prompt), "Gemini"
    if provider == "groq":
        return _call_groq(prompt), "Groq"
    raise RuntimeError(
        "Žádný AI klíč nenalezen. Nastav ANTHROPIC_API_KEY, GEMINI_API_KEY nebo GROQ_API_KEY."
    )


# ── Pomocná funkce – čištění JSON z odpovědi ──────────────────────────────────

def _parse_json(text: str) -> dict:
    """Vyčistí markdown backticky a parsuje JSON."""
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── Hlavní analýza ────────────────────────────────────────────────────────────

def _sig_summary(sig: dict | None) -> str:
    """Zkrácený textový souhrn signálů pro prompt."""
    if not sig:
        return "Nedostupné"
    action = sig.get("action", "HOLD")
    rsi    = sig.get("rsi", 50)
    ema_trend = (
        "rostoucí (Bullish)"
        if sig.get("ema20", 0) > sig.get("ema50", 0) > sig.get("ema200", 0)
        else "klesající (Bearish)"
        if sig.get("ema20", 0) < sig.get("ema50", 0) < sig.get("ema200", 0)
        else "smíšený"
    )
    buys  = sig.get("buy_signals", [])
    sells = sig.get("sell_signals", [])
    vol   = sig.get("volume_anomaly", {})
    vol_s = f" | Nezvyklý objem {vol.get('ratio',1):.1f}x ({vol.get('direction','')})" if vol.get("is_anomaly") else ""
    return (
        f"Signál: {action} (BUY: {len(buys)}, SELL: {len(sells)}) | "
        f"RSI: {rsi:.1f} | EMA: {ema_trend}{vol_s}\n"
        f"  BUY důvody: {', '.join(buys) if buys else 'žádné'}\n"
        f"  SELL důvody: {', '.join(sells) if sells else 'žádné'}"
    )


def analyze_stock_with_claude(
    ticker: str,
    short_signals: dict,
    medium_signals: dict | None,
    long_signals: dict | None,
    news: list[dict],
    ai_sentiment: dict,
    macro: dict | None = None,
) -> dict:
    """
    Multi-horizont AI analýza akcie.
    Vrátí: {ok, short, medium, long, provider}
    Každý horizont má: {action_hint, confidence, summary, events, risk_factors, opportunity}
    """
    headlines = [n.get("title", "") for n in news[:10] if n.get("title")]
    headlines_str = "\n".join(f"- {h}" for h in headlines) if headlines else "Žádné zprávy."
    sentiment_score = ai_sentiment.get("score", 0)
    sentiment_label = ai_sentiment.get("dominant", "neutral")
    n_pos = ai_sentiment.get("positive", 0)
    n_neg = ai_sentiment.get("negative", 0)

    prompt = f"""Jsi senior analytik finančních trhů. Analyzuj akcii {ticker} ze TŘÍ časových horizontů.
DŮLEŽITÉ: Celá odpověď včetně všech polí JSON musí být výhradně v češtině. Žádná anglická slova.

KRÁTKODOBÉ technické signály (data za 3 měsíce – RSI, MACD, Bollinger, Stochastic):
{_sig_summary(short_signals)}

STŘEDNĚDOBÉ technické signály (data za 1 rok – EMA 50/200 trendy dominují):
{_sig_summary(medium_signals)}

DLOUHODOBÉ technické signály (data za 2 roky – EMA 200 a makro trend):
{_sig_summary(long_signals)}

SENTIMENT ZPRÁV (FinBERT AI):
- Skóre: {sentiment_score:+.2f} (-1=velmi negativní, +1=velmi pozitivní)
- Celkový tón: {sentiment_label} ({n_pos} pozitivní, {n_neg} negativní)

AKTUÁLNÍ ZPRÁVY:
{headlines_str}

Odpověz PŘESNĚ v tomto JSON formátu (bez markdown backticks). VŠE MUSÍ BÝT V ČEŠTINĚ:
{{
  "short": {{
    "action_hint": "koupit|prodat|čekat|sledovat",
    "confidence": "nízká|střední|vysoká",
    "summary": "2-3 věty pro krátkodobého obchodníka (týdny až 3 měsíce) – co dělat nyní a proč",
    "events": ["konkrétní krátkodobá tržní událost 1", "událost 2"],
    "risk_factors": ["krátkodobé riziko 1", "riziko 2"],
    "opportunity": "Jedna věta o krátkodobé příležitosti nebo varování"
  }},
  "medium": {{
    "action_hint": "koupit|prodat|čekat|sledovat",
    "confidence": "nízká|střední|vysoká",
    "summary": "2-3 věty pro střednědobého investora (6 měsíců až 2 roky) – trend a pozice",
    "risk_factors": ["střednědobé riziko 1"],
    "opportunity": "Jedna věta o střednědobé příležitosti"
  }},
  "long": {{
    "action_hint": "koupit|prodat|čekat|sledovat",
    "confidence": "nízká|střední|vysoká",
    "summary": "2-3 věty pro dlouhodobého investora (3+ roky) – fundamentální a sektorová pozice firmy",
    "risk_factors": ["dlouhodobé riziko 1"],
    "opportunity": "Jedna věta o dlouhodobé příležitosti nebo hrozbě"
  }}
}}"""

    try:
        text, provider = _call_ai(prompt)
        data = _parse_json(text)
        data["ok"] = True
        data["provider"] = provider
        return data
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON parse error: {e}"}
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Peer comparison ───────────────────────────────────────────────────────────

def get_peer_comparison(ticker: str, period: str = "3mo") -> dict:
    """
    Porovnání s konkurencí.
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
            chg = (price_end - price_start) / price_start * 100

            normalized = (df["Close"] / price_start * 100).tolist()
            dates      = [str(d.date()) for d in df.index]

            results[t] = {
                "chg_pct":    round(chg, 2),
                "price":      round(price_end, 2),
                "normalized": normalized,
                "dates":      dates,
                "is_main":    t == ticker,
            }
        except Exception:
            pass

    if not results:
        return {"ok": False, "error": "Nepodařilo se načíst peer data"}

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
