import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from indicators import (
    compute_rsi,
    compute_macd,
    compute_bollinger,
    compute_emas,
    compute_stochastic,
    generate_signals,
)
from news_scraper import get_all_news, news_sentiment_summary
from macro import fetch_fear_greed, fetch_macro_tickers, fetch_sectors, fg_label
from earnings import get_portfolio_earnings
from backtest import run_backtest, backtest_summary_table

# ── Konfigurace stránky ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Advisor",
    page_icon="📈",
    layout="wide",
)

# ── Styly ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Základní karty ── */
.signal-buy  { background:#0d6e2f; color:#fff; padding:10px 20px; border-radius:8px;
               font-size:1.8rem; font-weight:700; text-align:center; }
.signal-sell { background:#8b0000; color:#fff; padding:10px 20px; border-radius:8px;
               font-size:1.8rem; font-weight:700; text-align:center; }
.signal-hold { background:#2a2a3a; color:#ccc; padding:10px 20px; border-radius:8px;
               font-size:1.8rem; font-weight:700; text-align:center; }
.card-buy    { background:#0a2e18; border:2px solid #22c55e; border-radius:10px;
               padding:14px; margin:6px 0; line-height:1.6; }
.card-sell   { background:#2e0a0a; border:2px solid #ef4444; border-radius:10px;
               padding:14px; margin:6px 0; line-height:1.6; }
.card-hold   { background:#1a1a2e; border:1px solid #444; border-radius:10px;
               padding:14px; margin:6px 0; line-height:1.6; }
.card-radar  { background:#1a1a0a; border:2px solid #f59e0b; border-radius:10px;
               padding:14px; margin:6px 0; line-height:1.6; }
.news-pos    { border-left:4px solid #22c55e; padding:8px 10px; margin:5px 0; }
.news-neg    { border-left:4px solid #ef4444; padding:8px 10px; margin:5px 0; }
.news-neu    { border-left:4px solid #888;    padding:8px 10px; margin:5px 0; }
.badge-buy   { background:#22c55e; color:#000; padding:3px 9px; border-radius:4px;
               font-weight:700; font-size:0.82rem; white-space:nowrap; }
.badge-sell  { background:#ef4444; color:#fff; padding:3px 9px; border-radius:4px;
               font-weight:700; font-size:0.82rem; white-space:nowrap; }
.badge-hold  { background:#555;    color:#fff; padding:3px 9px; border-radius:4px;
               font-weight:700; font-size:0.82rem; white-space:nowrap; }

/* ── Mobil – skryj padding hlavního kontejneru ── */
@media (max-width: 768px) {
    /* Zmenší padding okrajů */
    .block-container { padding: 0.5rem 0.6rem 2rem !important; }

    /* Sidebar button větší pro dotyk */
    [data-testid="stSidebarNavLink"] { font-size: 1.05rem !important; padding: 10px 0 !important; }

    /* Signálové boxy menší font */
    .signal-buy, .signal-sell, .signal-hold { font-size: 1.3rem !important; padding: 8px 14px !important; }

    /* Karty – zvětšit řádkování pro dotyk */
    .card-buy, .card-sell, .card-hold, .card-radar {
        padding: 12px 10px !important;
        font-size: 0.9rem !important;
        line-height: 1.8 !important;
    }

    /* Zprávy – větší klikatelná plocha */
    .news-pos, .news-neg, .news-neu { padding: 10px 8px !important; font-size: 0.88rem !important; }

    /* Metriky – menší label */
    [data-testid="stMetricLabel"]  { font-size: 0.75rem !important; }
    [data-testid="stMetricValue"]  { font-size: 1.2rem !important; }
    [data-testid="stMetricDelta"]  { font-size: 0.75rem !important; }

    /* Plotly grafy – plná šířka */
    .js-plotly-plot { width: 100% !important; }

    /* Nadpisy */
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.15rem !important; }
    h3 { font-size: 1rem !important; }
}

/* ── Tablet ── */
@media (max-width: 1024px) and (min-width: 769px) {
    .block-container { padding: 1rem 1.5rem 2rem !important; }
    .card-buy, .card-sell, .card-hold, .card-radar { font-size: 0.92rem !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Portfolio – akcie které vlastníš ─────────────────────────────────────────
PORTFOLIO = {
    "NVIDIA":                   ("NVDA",    "USD", "tech"),
    "AMD":                      ("AMD",     "USD", "tech"),
    "Alphabet Class A":         ("GOOGL",   "USD", "tech"),
    "Microsoft":                ("MSFT",    "USD", "tech"),
    "Vanguard S&P 500 Dist":    ("VUSA.L",  "GBP", "etf"),
    "iShares Core MSCI World":  ("IWDA.AS", "EUR", "etf"),
    "Palo Alto Networks":       ("PANW",    "USD", "tech"),
    "Amazon":                   ("AMZN",    "USD", "tech"),
    "SAAB":                     ("SAAB-B.ST","SEK","defense"),
    "Taiwan Semiconductor":     ("TSM",     "USD", "tech"),
    "Rheinmetall":              ("RHM.DE",  "EUR", "defense"),
}

# ── Radar – akcie rozdělené podle sektoru (mapování na sektorové ETF z macro.py)
# Sektor musí odpovídat klíčům v SECTOR_ETFS v macro.py
RADAR_STOCKS = {
    # Technologie (XLK)
    "Meta":             ("META",  "USD", "Technologie"),
    "Tesla":            ("TSLA",  "USD", "Technologie"),
    "ASML":             ("ASML",  "USD", "Technologie"),
    "CrowdStrike":      ("CRWD",  "USD", "Technologie"),
    "Palantir":         ("PLTR",  "USD", "Technologie"),
    "Broadcom":         ("AVGO",  "USD", "Technologie"),
    "ServiceNow":       ("NOW",   "USD", "Technologie"),
    "Apple":            ("AAPL",  "USD", "Technologie"),
    "Oracle":           ("ORCL",  "USD", "Technologie"),
    "Salesforce":       ("CRM",   "USD", "Technologie"),
    # Obrana & Průmysl (ITA)
    "BAE Systems":      ("BA.L",  "GBP", "Obrana & Průmysl"),
    "Airbus":           ("AIR.PA","EUR", "Obrana & Průmysl"),
    "Lockheed Martin":  ("LMT",   "USD", "Obrana & Průmysl"),
    "RTX":              ("RTX",   "USD", "Obrana & Průmysl"),
    "Northrop Grumman": ("NOC",   "USD", "Obrana & Průmysl"),
    "Leonardo":         ("LDO.MI","EUR", "Obrana & Průmysl"),
    # Zdravotnictví (XLV)
    "Eli Lilly":        ("LLY",   "USD", "Zdravotnictví"),
    "Novo Nordisk":     ("NVO",   "USD", "Zdravotnictví"),
    "Johnson & Johnson":("JNJ",   "USD", "Zdravotnictví"),
    "AbbVie":           ("ABBV",  "USD", "Zdravotnictví"),
    "UnitedHealth":     ("UNH",   "USD", "Zdravotnictví"),
    # Energie (XLE)
    "ExxonMobil":       ("XOM",   "USD", "Energie"),
    "Chevron":          ("CVX",   "USD", "Energie"),
    "Shell":            ("SHEL",  "USD", "Energie"),
    "BP":               ("BP",    "USD", "Energie"),
    "Equinor":          ("EQNR",  "USD", "Energie"),
    "Schlumberger":     ("SLB",   "USD", "Energie"),
    "Occidental":       ("OXY",   "USD", "Energie"),
    # Finance (XLF)
    "JPMorgan Chase":   ("JPM",   "USD", "Finance"),
    "Goldman Sachs":    ("GS",    "USD", "Finance"),
    "Visa":             ("V",     "USD", "Finance"),
    "Mastercard":       ("MA",    "USD", "Finance"),
    "Berkshire Hath.":  ("BRK-B", "USD", "Finance"),
    # Spotřeba (XLY)
    "Costco":           ("COST",  "USD", "Spotřeba"),
    "McDonald's":       ("MCD",   "USD", "Spotřeba"),
    "Nike":             ("NKE",   "USD", "Spotřeba"),
    "LVMH":             ("MC.PA", "EUR", "Spotřeba"),
    # Utility (XLU)
    "NextEra Energy":   ("NEE",   "USD", "Utility"),
    "Duke Energy":      ("DUK",   "USD", "Utility"),
    # Materiály (XLB)
    "Freeport-McMoRan": ("FCX",   "USD", "Materiály"),
    "Newmont":          ("NEM",   "USD", "Materiály"),
    "BHP":              ("BHP",   "USD", "Materiály"),
    # Komunikace (XLC)
    "Netflix":          ("NFLX",  "USD", "Komunikace"),
    "Walt Disney":      ("DIS",   "USD", "Komunikace"),
    "Spotify":          ("SPOT",  "USD", "Komunikace"),
}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Stock Advisor")
    page = st.radio(
        "Zobrazení",
        [
            "Portfolio přehled",
            "Detail akcie",
            "Radar – nové příležitosti",
            "Makro & Sentiment",
            "Earnings kalendář",
            "Korelace portfolia",
            "Backtest signálů",
            "Sektorový přehled",
        ],
        index=0,
    )
    st.divider()

    period_map = {
        "3 měsíce": "3mo",
        "6 měsíců": "6mo",
        "1 rok":    "1y",
        "2 roky":   "2y",
    }
    period_label = st.selectbox("Časové období", list(period_map.keys()), index=1)
    period = period_map[period_label]

    if page == "Detail akcie":
        all_stocks = dict(PORTFOLIO)
        all_stocks.update(RADAR_STOCKS)
        all_stocks["Vlastní ticker..."] = ("CUSTOM", "", "")
        stock_choice = st.selectbox("Akcie", list(all_stocks.keys()), index=0)
        if stock_choice == "Vlastní ticker...":
            custom = st.text_input("Ticker (např. AAPL)").upper().strip()
            detail_ticker = custom or "AAPL"
            detail_currency = "USD"
        else:
            detail_ticker, detail_currency, _ = all_stocks[stock_choice]

        show_ema = st.checkbox("EMA (20/50/200)", value=True)
        show_bb  = st.checkbox("Bollinger Bands", value=True)

    refresh = st.button("Obnovit data", use_container_width=True)
    st.divider()
    st.caption("**Disclaimer:** Pouze informativní nástroj. Nejedná se o finanční poradenství.")

# ── Cache funkce ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=900)
def load_data(ticker: str, period: str):
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


@st.cache_data(ttl=1800)
def load_news(ticker: str):
    return get_all_news(ticker)


@st.cache_data(ttl=900)
def scan_stocks(stock_dict: dict, period: str) -> list[dict]:
    """Načte data a signály pro všechny akcie ve slovníku."""
    results = []
    for name, (ticker, currency, sector) in stock_dict.items():
        df = load_data(ticker, period)
        if df is None or len(df) < 30:
            continue
        sig = generate_signals(df)
        price = float(df["Close"].iloc[-1])
        prev  = float(df["Close"].iloc[-2])
        chg_pct = (price - prev) / prev * 100

        # Skóre zpráv – pouze z cache pokud existuje, jinak 0
        news_score = 0.0

        results.append({
            "name":       name,
            "ticker":     ticker,
            "currency":   currency,
            "sector":     sector,
            "price":      price,
            "chg_pct":    chg_pct,
            "action":     sig["action"],
            "strength":   sig["strength"],
            "buy_n":      len(sig["buy_signals"]),
            "sell_n":     len(sig["sell_signals"]),
            "buy_reasons":  sig["buy_signals"],
            "sell_reasons": sig["sell_signals"],
            "rsi":        sig["rsi"],
            "ema_trend":  (
                "Bullish" if sig["ema20"] > sig["ema50"] > sig["ema200"]
                else "Bearish" if sig["ema20"] < sig["ema50"] < sig["ema200"]
                else "Smíšený"
            ),
        })
    return results


if refresh:
    st.cache_data.clear()


def _score_label(buy_n: int, sell_n: int, action: str) -> tuple[int, str]:
    """
    Převede počty signálů na skóre 1–10 a slovní popis.
    BUY: 1–10 (čím vyšší, tím silnější nákup)
    SELL: -1 až -10 (čím nižší, tím silnější prodej)
    HOLD: 0
    """
    MAX_SIGNALS = 8  # teoretické maximum indikátorů
    if action == "BUY":
        score = max(1, min(10, round(buy_n / MAX_SIGNALS * 10)))
        label = {1: "Slabý zájem", 2: "Slabý zájem", 3: "Mírný zájem",
                 4: "Mírný BUY", 5: "BUY", 6: "BUY", 7: "Silný BUY",
                 8: "Silný BUY", 9: "Velmi silný BUY", 10: "Extrémní BUY"}.get(score, "BUY")
        return score, label
    elif action == "SELL":
        score = max(1, min(10, round(sell_n / MAX_SIGNALS * 10)))
        label = {1: "Slabý tlak", 2: "Slabý tlak", 3: "Mírný tlak",
                 4: "Mírný SELL", 5: "SELL", 6: "SELL", 7: "Silný SELL",
                 8: "Silný SELL", 9: "Velmi silný SELL", 10: "Extrémní SELL"}.get(score, "SELL")
        return -score, label
    else:
        # HOLD – ukažeme tendenci
        if buy_n > sell_n:
            score = buy_n - sell_n
            return score, f"Spíše HOLD (lehký BUY tlak: {buy_n} vs {sell_n})"
        elif sell_n > buy_n:
            score = -(sell_n - buy_n)
            return score, f"Spíše HOLD (lehký SELL tlak: {sell_n} vs {buy_n})"
        return 0, "Neutrální HOLD"


def _score_bar_html(score: int) -> str:
    """Vizuální číselný ukazatel -10 až +10 jako mini progress bar."""
    # score je v rozsahu -10 až +10, 0 = střed
    clamped = max(-10, min(10, score))
    # Barva
    if clamped > 0:
        color = "#22c55e"
        width = int(clamped / 10 * 100)
        bar = f'<div style="display:inline-block;background:{color};width:{width}px;height:8px;border-radius:4px;vertical-align:middle"></div>'
        num = f'<span style="color:{color};font-weight:700;font-size:1rem">+{clamped}</span>'
    elif clamped < 0:
        color = "#ef4444"
        width = int(abs(clamped) / 10 * 100)
        bar = f'<div style="display:inline-block;background:{color};width:{width}px;height:8px;border-radius:4px;vertical-align:middle"></div>'
        num = f'<span style="color:{color};font-weight:700;font-size:1rem">{clamped}</span>'
    else:
        color = "#888"
        bar = f'<div style="display:inline-block;background:{color};width:4px;height:8px;border-radius:4px;vertical-align:middle"></div>'
        num = f'<span style="color:{color};font-weight:700;font-size:1rem">0</span>'
    return f'{num} /10 &nbsp;{bar}'


def _render_radar_card(r: dict, highlight: bool = False):
    action = r["action"]
    label  = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[action]
    css    = "card-buy" if action == "BUY" else "card-sell" if action == "SELL" else "card-hold"
    badge  = "badge-buy" if action == "BUY" else "badge-sell" if action == "SELL" else "badge-hold"
    if highlight:
        css = css + '" style="border-width:3px'
    arrow  = "▲" if r["chg_pct"] >= 0 else "▼"
    color  = "#22c55e" if r["chg_pct"] >= 0 else "#ef4444"
    reasons = (r["buy_reasons"] if action == "BUY" else r["sell_reasons"])[:3]
    reasons_html = " &nbsp;·&nbsp; ".join(
        f'<span style="color:#{"86efac" if action == "BUY" else "fca5a5"}">{s}</span>'
        for s in reasons
    )
    trend_color = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Smíšený": "#888"}[r["ema_trend"]]
    score, score_label = _score_label(r["buy_n"], r["sell_n"], action)
    score_html = _score_bar_html(score)
    sp = r.get("sector_chg")
    sp_str = (f'<span style="color:{"#22c55e" if (sp or 0) >= 0 else "#ef4444"}">'
              f'Sektor: {sp:+.1f}%</span>' if sp is not None else "")
    st.markdown(
        f'<div class="{css}">'
        f'<span class="{badge}">{label}</span> &nbsp;'
        f'{score_html} &nbsp; <span style="color:#aaa;font-size:0.8rem">{score_label}</span>'
        f'<br><strong style="font-size:1.05rem">{r["name"]}</strong>'
        f' <span style="color:#888;font-size:0.82rem">{r["ticker"]} · {r["sector"]}</span>'
        f' &nbsp;{r["price"]:.2f} {r["currency"]}'
        f' <span style="color:{color}">{arrow}{r["chg_pct"]:+.1f}%</span>'
        f' &nbsp;|&nbsp; RSI: <b>{r["rsi"]:.0f}</b>'
        f' &nbsp;|&nbsp; Trend: <span style="color:{trend_color}">{r["ema_trend"]}</span>'
        + (f' &nbsp;|&nbsp; {sp_str}' if sp_str else "")
        + (f'<br><small>{reasons_html}</small>' if reasons_html else "")
        + '</div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 1 – Portfolio přehled
# ═════════════════════════════════════════════════════════════════════════════
if page == "Portfolio přehled":
    st.title("Portfolio přehled")
    st.caption(f"Aktualizováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    with st.expander("Jak číst tento přehled?"):
        st.markdown("""
- **KOUPIT** (zelená) = alespoň 3 technické indikátory najednou naznačují, že akcie je podhodnocená nebo se chystá růst
- **PRODAT** (červená) = alespoň 3 indikátory naznačují, že akcie je předražená nebo se chystá klesat
- **DRŽET** (šedá) = indikátory si protiřečí nebo nejsou dostatečně výrazné → nic nedělej
- **RSI** = číslo 0–100. Pod 30 je akcie „levná" (přeprodaná), nad 70 „drahá" (překoupená)
- **Trend** = Bullish znamená rostoucí trend, Bearish klesající, Smíšený = nejasný
- **Síla signálu** = kolik % z maximálního počtu indikátorů souhlasí (60%+ = silný signál)
        """)

    with st.spinner("Načítám data pro celé portfolio..."):
        results = scan_stocks(PORTFOLIO, period)

    if not results:
        st.error("Nepodařilo se načíst data. Zkontroluj připojení.")
        st.stop()

    # ── Souhrnná lišta ────────────────────────────────────────────────────────
    buy_count  = sum(1 for r in results if r["action"] == "BUY")
    sell_count = sum(1 for r in results if r["action"] == "SELL")
    hold_count = sum(1 for r in results if r["action"] == "HOLD")

    # 2+2 na mobilu, 4 na desktopu
    row1 = st.columns(2)
    row2 = st.columns(2)
    row1[0].metric("Sledované akcie", len(results))
    row1[1].metric("KOUPIT", buy_count)
    row2[0].metric("PRODAT", sell_count)
    row2[1].metric("DRŽET",  hold_count)
    st.divider()

    # ── Karty akcií – nejprve akce, pak hold ─────────────────────────────────
    def action_order(r):
        return {"BUY": 0, "SELL": 1, "HOLD": 2}[r["action"]]

    sorted_results = sorted(results, key=action_order)

    for r in sorted_results:
        action = r["action"]
        css    = {"BUY": "card-buy", "SELL": "card-sell", "HOLD": "card-hold"}[action]
        badge  = {"BUY": "badge-buy", "SELL": "badge-sell", "HOLD": "badge-hold"}[action]
        label  = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[action]
        arrow  = "▲" if r["chg_pct"] >= 0 else "▼"
        color  = "#22c55e" if r["chg_pct"] >= 0 else "#ef4444"

        reasons_html = ""
        if action == "BUY" and r["buy_reasons"]:
            reasons_html = "<br>" + " &nbsp;·&nbsp; ".join(
                f'<span style="color:#86efac">{s}</span>' for s in r["buy_reasons"]
            )
        elif action == "SELL" and r["sell_reasons"]:
            reasons_html = "<br>" + " &nbsp;·&nbsp; ".join(
                f'<span style="color:#fca5a5">{s}</span>' for s in r["sell_reasons"]
            )

        score, score_label = _score_label(r["buy_n"], r["sell_n"], action)
        score_html = _score_bar_html(score)
        trend_color = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Smíšený": "#888"}[r["ema_trend"]]

        st.markdown(f"""
        <div class="{css}">
          <span class="{badge}">{label}</span>
          &nbsp; {score_html} &nbsp;
          <span style="color:#aaa;font-size:0.8rem">{score_label}</span>
          &nbsp;&nbsp;
          <strong style="font-size:1.05rem">{r['name']}</strong>
          <span style="color:#888;font-size:0.83rem"> {r['ticker']}</span>
          &nbsp;&nbsp;
          <span style="font-size:1.05rem">{r['price']:.2f} {r['currency']}</span>
          &nbsp;
          <span style="color:{color}">{arrow} {r['chg_pct']:+.1f}%</span>
          &nbsp;&nbsp;
          <span style="color:#aaa;font-size:0.82rem">
            RSI: <b>{r['rsi']:.0f}</b> &nbsp;|&nbsp;
            Trend: <span style="color:{trend_color}">{r['ema_trend']}</span>
          </span>
          {reasons_html}
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── RSI přehled – mini heatmapa ───────────────────────────────────────────
    st.subheader("RSI přehled portfolia")
    rsi_names  = [r["name"].split()[0] for r in results]
    rsi_values = [r["rsi"] for r in results]
    rsi_colors = [
        "#22c55e" if v < 35 else "#ef4444" if v > 65 else "#60a5fa"
        for v in rsi_values
    ]
    fig_rsi = go.Figure(go.Bar(
        x=rsi_names,
        y=rsi_values,
        marker_color=rsi_colors,
        text=[f"{v:.0f}" for v in rsi_values],
        textposition="outside",
    ))
    fig_rsi.add_hline(y=70, line=dict(color="#ef4444", dash="dash"), annotation_text="Overbought 70")
    fig_rsi.add_hline(y=30, line=dict(color="#22c55e", dash="dash"), annotation_text="Oversold 30")
    fig_rsi.update_layout(
        template="plotly_dark", height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(range=[0, 100]),
        showlegend=False,
    )
    st.plotly_chart(fig_rsi, use_container_width=True)

    # ── Výkonnost portfolia (změna %) ─────────────────────────────────────────
    st.subheader("Dnešní změna (%)")
    chg_names  = [r["name"].split()[0] for r in results]
    chg_values = [r["chg_pct"] for r in results]
    chg_colors = ["#22c55e" if v >= 0 else "#ef4444" for v in chg_values]
    fig_chg = go.Figure(go.Bar(
        x=chg_names, y=chg_values,
        marker_color=chg_colors,
        text=[f"{v:+.1f}%" for v in chg_values],
        textposition="outside",
    ))
    fig_chg.add_hline(y=0, line=dict(color="#666", width=1))
    fig_chg.update_layout(
        template="plotly_dark", height=260,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig_chg, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 2 – Detail akcie
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Detail akcie":
    ticker   = detail_ticker
    currency = detail_currency

    st.title(f"Detail – {ticker}")

    with st.spinner("Načítám data..."):
        df = load_data(ticker, period)

    if df is None or len(df) < 30:
        st.error(f"Nepodařilo se načíst data pro '{ticker}'.")
        st.stop()

    price_now  = float(df["Close"].iloc[-1])
    price_prev = float(df["Close"].iloc[-2])
    chg        = price_now - price_prev
    chg_pct    = chg / price_prev * 100
    high_52w   = float(df["Close"].tail(252).max())
    low_52w    = float(df["Close"].tail(252).min())
    vol_avg    = float(df["Volume"].tail(20).mean())
    vol_now    = float(df["Volume"].iloc[-1])
    vol_ratio  = vol_now / vol_avg if vol_avg > 0 else 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cena",         f"{price_now:.2f} {currency}", f"{chg:+.2f} ({chg_pct:+.1f}%)")
    c2.metric("52W Maximum",  f"{high_52w:.2f}")
    c3.metric("52W Minimum",  f"{low_52w:.2f}")
    c4.metric("Objem/průměr", f"{vol_ratio:.1f}x")

    st.divider()

    # Signály
    signals = generate_signals(df)
    action  = signals["action"]

    sig_col, detail_col = st.columns([1, 2])
    with sig_col:
        st.subheader("Doporučení")
        label = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[action]
        st.markdown(f'<div class="signal-{action.lower()}">{label}</div>', unsafe_allow_html=True)

        score, score_label = _score_label(
            len(signals["buy_signals"]), len(signals["sell_signals"]), action
        )
        score_html = _score_bar_html(score)
        st.markdown(
            f'<div style="margin:8px 0 4px">{score_html}'
            f' &nbsp;<span style="color:#aaa;font-size:0.85rem">{score_label}</span></div>',
            unsafe_allow_html=True,
        )
        if action != "HOLD":
            st.progress(signals["strength"], text=f"Shoda indikátorů: {signals['strength']*100:.0f}%")
        st.caption(f"BUY signálů: {len(signals['buy_signals'])} | SELL signálů: {len(signals['sell_signals'])}")

    with detail_col:
        st.subheader("Důvody")
        t1, t2 = st.tabs(["BUY signály", "SELL signály"])
        with t1:
            for s in signals["buy_signals"]:
                st.success(f"+ {s}")
            if not signals["buy_signals"]:
                st.info("Žádné")
        with t2:
            for s in signals["sell_signals"]:
                st.error(f"- {s}")
            if not signals["sell_signals"]:
                st.info("Žádné")

    st.divider()

    # Indikátory
    st.subheader("Technické indikátory")

    i1, i2, i3, i4, i5 = st.columns(5)
    rsi_v = signals["rsi"]
    i1.metric(
        "RSI (14)",
        f"{rsi_v:.1f}",
        "Oversold – levná" if rsi_v < 30 else "Overbought – drahá" if rsi_v > 70 else "Neutrální",
        help="RSI (Relative Strength Index) měří, zda je akcie překoupená nebo přeprodaná. "
             "Pod 30 = akcie je levná/přeprodaná → signál ke koupi. "
             "Nad 70 = akcie je drahá/překoupená → signál k prodeji. "
             "Rozsah 0–100.",
    )
    i2.metric(
        "MACD",
        f"{signals['macd']:.3f}",
        f"Signal linka: {signals['macd_signal']:.3f}",
        help="MACD porovnává dva klouzavé průměry (12 a 26 dní). "
             "Když MACD překříží signal linku zdola nahoru = BUY signál. "
             "Když ji překříží shora dolů = SELL signál. "
             "Kladná hodnota = krátkodobý trend je rychlejší než dlouhodobý (bullish).",
    )
    bb_pos = (price_now - signals["bb_lower"]) / max(signals["bb_upper"] - signals["bb_lower"], 0.01) * 100
    i3.metric(
        "Bollinger Bands",
        f"{bb_pos:.0f}%",
        "Blízko dna pásma" if bb_pos < 20 else "Blízko vrcholu pásma" if bb_pos > 80 else "Střed pásma",
        help="Bollinger Bands jsou tři pásma kolem průměrné ceny (±2 směrodatné odchylky). "
             "0% = cena je na spodním pásmu (podprůměrně levná, možný odraz nahoru). "
             "100% = cena je na horním pásmu (nadprůměrně drahá, možný pokles). "
             "50% = cena je přesně na průměru.",
    )
    i4.metric(
        "Stochastic K/D",
        f"{signals['stoch_k']:.0f} / {signals['stoch_d']:.0f}",
        "Oversold" if signals["stoch_k"] < 20 else "Overbought" if signals["stoch_k"] > 80 else "Neutrální",
        help="Stochastic oscilator porovnává aktuální cenu s cenovým rozsahem za posledních 14 dní. "
             "K = rychlá linka, D = pomalejší průměr K. "
             "Pod 20 = přeprodaná zóna (kandidát na nákup). "
             "Nad 80 = překoupená zóna (kandidát na prodej). "
             "Nejsilnější signál: K překříží D v extrémní zóně.",
    )
    trend = ("Bullish" if signals["ema20"] > signals["ema50"] > signals["ema200"]
             else "Bearish" if signals["ema20"] < signals["ema50"] < signals["ema200"]
             else "Smíšený")
    i5.metric(
        "Trend (EMA)",
        trend,
        f"EMA50: {signals['ema50']:.1f}",
        help="EMA (Exponential Moving Average) = klouzavý průměr ceny, který více váží poslední data. "
             "EMA 20 = průměr 20 dní, EMA 50 = 50 dní, EMA 200 = 200 dní. "
             "Bullish: EMA20 > EMA50 > EMA200 → krátkodobý trend roste rychleji než dlouhodobý. "
             "Bearish: opačné pořadí → klesající trend. "
             "Golden Cross: EMA20 překříží EMA50 nahoru = silný BUY signál.",
    )

    # Rozbalovací legenda pro méně zkušené uživatele
    with st.expander("Co znamenají tyto indikátory? (rozbal pro vysvětlení)"):
        st.markdown("""
**Jak systém funguje:** Sleduje 5 indikátorů najednou. Signál KOUPIT nebo PRODAT se zobrazí teprve
když **alespoň 3 indikátory souhlasí** — proto je konzervativní a nevydává falešné alarmy při každém malém pohybu.

| Indikátor | Co měří | Kdy říká KOUPIT | Kdy říká PRODAT |
|---|---|---|---|
| **RSI** | Síla trendu, přeprodanost | Pod 30 (levná) | Nad 70 (drahá) |
| **MACD** | Momentum trendu | Křížení nahoru | Křížení dolů |
| **Bollinger Bands** | Pozice vůči průměru | Cena pod spodním pásmem | Cena nad horním pásmem |
| **Stochastic** | Přeprodanost za 14 dní | K/D pod 20 | K/D nad 80 |
| **EMA trend** | Směr krátkodobého vs. dlouhodobého trendu | 20 > 50 > 200 | 20 < 50 < 200 |

**Bullish** = rostoucí trend, **Bearish** = klesající trend, **Oversold** = přeprodaná (levná), **Overbought** = překoupená (drahá).

> Žádný indikátor není 100% spolehlivý. Vždy kombinuj s vlastním úsudkem a zprávami.
        """)

    st.divider()

    # Graf
    close = df["Close"]
    rsi_s = compute_rsi(close)
    ml, sl, hist = compute_macd(close)
    ub, mb, lb = compute_bollinger(close)
    e20, e50, e200 = compute_emas(close)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.25, 0.20],
        vertical_spacing=0.04,
        subplot_titles=(f"{ticker} – Cena", "RSI (14)", "MACD"),
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=close,
        name="Cena",
        increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
    ), row=1, col=1)

    if show_bb:
        fig.add_trace(go.Scatter(x=df.index, y=ub, line=dict(color="rgba(100,149,237,0.4)", width=1), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=lb, line=dict(color="rgba(100,149,237,0.4)", width=1), fill="tonexty", fillcolor="rgba(100,149,237,0.08)", showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=mb, line=dict(color="rgba(100,149,237,0.6)", width=1, dash="dot"), name="BB Mid", showlegend=False), row=1, col=1)

    if show_ema:
        fig.add_trace(go.Scatter(x=df.index, y=e20,  line=dict(color="#f59e0b", width=1.5), name="EMA 20"),  row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=e50,  line=dict(color="#8b5cf6", width=1.5), name="EMA 50"),  row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=e200, line=dict(color="#ec4899", width=1.5), name="EMA 200"), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=rsi_s, line=dict(color="#60a5fa", width=1.5), name="RSI"), row=2, col=1)
    fig.add_hline(y=70, line=dict(color="#ef4444", dash="dash", width=1), row=2, col=1)
    fig.add_hline(y=30, line=dict(color="#22c55e", dash="dash", width=1), row=2, col=1)

    hcolors = ["#22c55e" if v >= 0 else "#ef4444" for v in hist]
    fig.add_trace(go.Bar(x=df.index, y=hist, marker_color=hcolors, showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=ml, line=dict(color="#60a5fa", width=1.5), name="MACD"),   row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=sl, line=dict(color="#f59e0b", width=1.5), name="Signal"), row=3, col=1)

    fig.update_layout(
        height=660, template="plotly_dark",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Zprávy
    st.subheader("Zprávy & Sentiment")
    with st.spinner("Načítám zprávy..."):
        news = load_news(ticker)

    if news:
        sent = news_sentiment_summary(news)
        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Pozitivní", sent["positive"])
        n2.metric("Negativní", sent["negative"])
        n3.metric("Neutrální",  sent["neutral"])
        dlabel = {"positive": "Pozitivní", "negative": "Negativní", "neutral": "Neutrální"}[sent["dominant"]]
        n4.metric("Celkový sentiment", dlabel, f"{sent['score']:+.2f}")
        st.markdown("---")
        for item in news[:15]:
            s   = item.get("sentiment", "neutral")
            css = {"positive": "news-pos", "negative": "news-neg", "neutral": "news-neu"}[s]
            ico = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}[s]
            sd  = f"{item['source']} · {item['date']}" if item["date"] else item["source"]
            smr = f"<br><small style='color:#aaa'>{item['summary']}</small>" if item["summary"] else ""
            st.markdown(
                f'<div class="{css}">{ico} <a href="{item["link"]}" target="_blank" style="color:inherit">'
                f'<strong>{item["title"]}</strong></a>'
                f'<br><small style="color:#888">{sd}</small>{smr}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("Zprávy se nepodařilo načíst.")


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 3 – Radar (nové příležitosti)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Radar – nové příležitosti":
    st.title("Radar – nové příležitosti")
    st.caption(f"{len(RADAR_STOCKS)} akcií ze všech sektorů. Signál = ≥3 shodné technické indikátory.")

    with st.expander("Jak radar funguje?"):
        st.markdown("""
Radar prohledává ~50 akcií pokrývající všechny hlavní sektory (energie, tech, finance, zdravotnictví...).

**Logika:**
1. Pro každou akcii spočítá 5 technických indikátorů (RSI, MACD, Bollinger Bands, Stochastic, EMA)
2. Pokud ≥3 indikátory najednou říkají BUY nebo SELL → signál
3. Výsledky jsou seřazeny podle sektoru a jeho aktuálního výkonu

**Proč „sektor roste, ale akcie ne"?** Sektorový ETF (např. XLE = energie) je průměr desítek firem.
Konkrétní akcie může zaostávat za sektorem z jiných důvodů (špatné výsledky, management...).
Technické indikátory to zachytí — akcie v silném sektoru BEZ BUY signálu je spíše slabý člen sektoru.

**Jak to číst:** Hledej akcie kde zároveň:
- Sektor je v zelených číslech (roste)
- Akcie má BUY signál od ≥3 indikátorů
→ to je tzv. **double confirmation** — silná příležitost.
        """)

    # ── Načtení sektorové výkonnosti ─────────────────────────────────────────
    with st.spinner("Načítám sektorová data..."):
        sector_perf_raw = fetch_sectors(period)
    sector_perf = {s["name"]: s["chg_period"] for s in sector_perf_raw}

    # ── Filtr sektoru v sidebaru ──────────────────────────────────────────────
    all_sectors = sorted(set(v[2] for v in RADAR_STOCKS.values()))
    with st.sidebar:
        st.divider()
        selected_sectors = st.multiselect(
            "Filtruj sektor",
            options=all_sectors,
            default=[],
            placeholder="Všechny sektory",
        )

    filtered_radar = {
        name: val for name, val in RADAR_STOCKS.items()
        if not selected_sectors or val[2] in selected_sectors
    }

    # ── Sektorový přehled – lišta nahoře ─────────────────────────────────────
    st.subheader("Výkon sektorů (kontext pro signály)")
    sector_cols = st.columns(min(len(sector_perf_raw), 5))
    for i, s in enumerate(sector_perf_raw[:5]):
        cp = s["chg_period"]
        color = "#22c55e" if cp >= 0 else "#ef4444"
        sector_cols[i].markdown(
            f'<div style="text-align:center;background:#1a1a2e;border-radius:8px;padding:8px 4px">'
            f'<div style="font-size:0.75rem;color:#888">{s["name"]}</div>'
            f'<div style="font-size:1.1rem;color:{color};font-weight:700">{cp:+.1f}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    if len(sector_perf_raw) > 5:
        sector_cols2 = st.columns(len(sector_perf_raw) - 5)
        for i, s in enumerate(sector_perf_raw[5:]):
            cp = s["chg_period"]
            color = "#22c55e" if cp >= 0 else "#ef4444"
            sector_cols2[i].markdown(
                f'<div style="text-align:center;background:#1a1a2e;border-radius:8px;padding:8px 4px">'
                f'<div style="font-size:0.75rem;color:#888">{s["name"]}</div>'
                f'<div style="font-size:1.1rem;color:{color};font-weight:700">{cp:+.1f}%</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Scan akcií ────────────────────────────────────────────────────────────
    with st.spinner(f"Skenuji {len(filtered_radar)} akcií..."):
        results = scan_stocks(filtered_radar, period)

    # Přidej sektorový kontext ke každému výsledku
    for r in results:
        r["sector_chg"] = sector_perf.get(r["sector"], None)

    strong = [r for r in results if r["action"] != "HOLD"]
    hold   = [r for r in results if r["action"] == "HOLD"]

    # ── Double confirmation – silný sektor + BUY signál ───────────────────────
    double_conf = [
        r for r in strong
        if r["action"] == "BUY"
        and r.get("sector_chg") is not None
        and r["sector_chg"] > 1.0
    ]

    if double_conf:
        st.subheader(f"Double confirmation – silný sektor + BUY signál ({len(double_conf)})")
        st.caption("Tyto akcie mají BUY signál A zároveň jejich sektor roste nad 1% — nejsilnější příležitosti.")
        for r in sorted(double_conf, key=lambda x: -(x["strength"] + (x["sector_chg"] or 0) / 20)):
            _render_radar_card(r, highlight=True)
        st.divider()

    # ── Ostatní silné signály ─────────────────────────────────────────────────
    other_strong = [r for r in strong if r not in double_conf]
    if other_strong:
        st.subheader(f"Ostatní signály ({len(other_strong)})")
        for r in sorted(other_strong, key=lambda x: -x["strength"]):
            _render_radar_card(r, highlight=False)
    elif not double_conf:
        st.info("Žádné silné signály. Trh je momentálně v klidném pásmu — čekej na příležitost.")

    # ── Přehled podle sektoru – co sledovat ──────────────────────────────────
    st.divider()
    st.subheader("Přehled podle sektoru")
    sectors_with_stocks = {}
    for r in sorted(hold + strong, key=lambda x: x["name"]):
        s = r["sector"]
        sectors_with_stocks.setdefault(s, []).append(r)

    # Seřaď sektory od nejsilnějšího výkonu
    def sector_sort_key(s):
        return -(sector_perf.get(s, 0))

    for sector_name in sorted(sectors_with_stocks.keys(), key=sector_sort_key):
        stocks_in_sector = sectors_with_stocks[sector_name]
        sp = sector_perf.get(sector_name)
        sp_str = f"{sp:+.1f}%" if sp is not None else "N/A"
        sp_color = "#22c55e" if (sp or 0) >= 0 else "#ef4444"
        buy_in  = sum(1 for r in stocks_in_sector if r["action"] == "BUY")
        sell_in = sum(1 for r in stocks_in_sector if r["action"] == "SELL")

        label_parts = []
        if buy_in:  label_parts.append(f"{buy_in} BUY")
        if sell_in: label_parts.append(f"{sell_in} SELL")
        signal_summary = " · ".join(label_parts) if label_parts else "vše HOLD"

        with st.expander(
            f"{sector_name}  —  ETF: {sp_str}  |  {signal_summary}  ({len(stocks_in_sector)} akcií)"
        ):
            for r in sorted(stocks_in_sector, key=lambda x: {"BUY": 0, "SELL": 1, "HOLD": 2}[x["action"]]):
                arrow = "▲" if r["chg_pct"] >= 0 else "▼"
                price_color = "#22c55e" if r["chg_pct"] >= 0 else "#ef4444"
                trend_color = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Smíšený": "#888"}[r["ema_trend"]]
                badge_css = {"BUY": "badge-buy", "SELL": "badge-sell", "HOLD": "badge-hold"}[r["action"]]
                badge_lbl = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[r["action"]]
                card_css  = {"BUY": "card-buy", "SELL": "card-sell", "HOLD": "card-hold"}[r["action"]]
                reasons = (r["buy_reasons"] if r["action"] == "BUY" else r["sell_reasons"])[:2]
                reasons_html = " · ".join(reasons) if reasons else ""
                st.markdown(
                    f'<div class="{card_css}" style="margin:3px 0;padding:10px">'
                    f'<span class="{badge_css}">{badge_lbl}</span> &nbsp;'
                    f'<strong>{r["name"]}</strong> <span style="color:#888;font-size:0.8rem">{r["ticker"]}</span>'
                    f' &nbsp;{r["price"]:.2f} {r["currency"]}'
                    f' <span style="color:{price_color}">{arrow}{r["chg_pct"]:+.1f}%</span>'
                    f' &nbsp;|&nbsp; RSI: <b>{r["rsi"]:.0f}</b>'
                    f' &nbsp;|&nbsp; Trend: <span style="color:{trend_color}">{r["ema_trend"]}</span>'
                    + (f'<br><small style="color:#aaa">{reasons_html}</small>' if reasons_html else "")
                    + '</div>',
                    unsafe_allow_html=True,
                )


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 4 – Makro & Sentiment
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Makro & Sentiment":
    st.title("Makro & Sentiment")
    st.caption("Globální tržní kontext – Fear & Greed, VIX, dluhopisy, komodity.")

    with st.expander("Co jsou tyto indikátory a proč jsou důležité?"):
        st.markdown("""
**Fear & Greed Index** (Strach a chamtivost, 0–100) – měří celkovou náladu na americkém trhu.
Historicky platí: *když ostatní se bojí, je čas kupovat; když jsou chamtiví, je čas prodávat.*
- 0–25 = Extreme Fear (extrémní strach) → trh v panice, akcie levné
- 26–45 = Fear (strach) → pesimismus, opatrný optimismus
- 46–55 = Neutral → nejasná nálada
- 56–75 = Greed (chamtivost) → optimismus, možné předražení
- 76–100 = Extreme Greed → euforie, vysoké riziko korekce

**VIX** (Index volatility, „index strachu") – jak moc trh očekává výkyvy v příštích 30 dnech.
- Pod 15 = klidný trh, nízká volatilita
- 15–25 = normální volatilita
- 25–35 = zvýšená nervozita
- Nad 35 = panika, velké výkyvy

**10Y Treasury** (výnos amerických státních dluhopisů, 10 let) – klíčová úroková sazba.
- Nad 5% = drahé peníze → akcie pod tlakem, investoři přesouvají peníze do dluhopisů
- Pod 3% = levné peníze → příznivé pro akcie

**Gold (Zlato)** – bezpečný přístav. Když zlato roste, investoři se bojí → negativní pro akcie.

**USD Index** – síla amerického dolaru. Silný dolar = slabší zisky amerických firem ze zahraničí.
        """)

    col_fg, col_macro = st.columns([1, 2])

    with col_fg:
        st.subheader("Fear & Greed Index")
        with st.spinner("Načítám F&G..."):
            fg = fetch_fear_greed()

        if fg.get("ok") and fg.get("score") is not None:
            score = fg["score"]
            label, color = fg_label(score)

            # Gauge chart
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score,
                title={"text": label, "font": {"size": 18}},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar":  {"color": color},
                    "steps": [
                        {"range": [0, 25],  "color": "#7f1d1d"},
                        {"range": [25, 45], "color": "#9a3412"},
                        {"range": [45, 55], "color": "#713f12"},
                        {"range": [55, 75], "color": "#365314"},
                        {"range": [75, 100],"color": "#14532d"},
                    ],
                    "threshold": {
                        "line": {"color": "white", "width": 3},
                        "thickness": 0.85,
                        "value": score,
                    },
                },
            ))
            fig_gauge.update_layout(
                height=240, template="plotly_dark",
                margin=dict(l=20, r=20, t=40, b=10),
            )
            st.plotly_chart(fig_gauge, use_container_width=True)

            m1, m2 = st.columns(2)
            if fg.get("prev_week"):
                diff_w = score - fg["prev_week"]
                m1.metric("Před týdnem", f"{fg['prev_week']:.0f}", f"{diff_w:+.1f}")
            if fg.get("prev_month"):
                diff_m = score - fg["prev_month"]
                m2.metric("Před měsícem", f"{fg['prev_month']:.0f}", f"{diff_m:+.1f}")

            # Interpretace
            if score <= 25:
                st.error("Extreme Fear – trh je v panice. Historicky dobrá příležitost k nákupu pro long-term investory.")
            elif score <= 45:
                st.warning("Fear – pesimismus převládá. Opatrný optimismus může být opodstatněný.")
            elif score <= 55:
                st.info("Neutral – trh neví kam. Čekej na jasný signál.")
            elif score <= 75:
                st.success("Greed – optimismus na trhu. Pozor na overvaluation.")
            else:
                st.error("Extreme Greed – euforie! Zvažuj profit-taking, trh může být přehřátý.")
        else:
            st.warning("Fear & Greed Index se nepodařilo načíst.")

    with col_macro:
        st.subheader("Makro indikátory")
        with st.spinner("Načítám makro data..."):
            macro = fetch_macro_tickers()

        if macro:
            for name, data in macro.items():
                price = data["price"]
                chg   = data["chg"]
                arrow = "▲" if chg >= 0 else "▼"
                color = "#22c55e" if chg >= 0 else "#ef4444"

                # Speciální interpretace VIX
                note = ""
                if name == "VIX":
                    if price < 15:
                        note = " – nízká volatilita, klidný trh"
                    elif price < 25:
                        note = " – normální volatilita"
                    elif price < 35:
                        note = " – zvýšená volatilita, nervozita"
                    else:
                        note = " – extrémní volatilita / panika"
                elif name == "10Y Treasury":
                    if price > 5.0:
                        note = " – výnosy vysoké, akcie pod tlakem"
                    elif price > 4.0:
                        note = " – výnosy zvýšené"
                    else:
                        note = " – výnosy nízké, příznivé pro akcie"

                st.markdown(
                    f'<div class="card-hold" style="margin:4px 0">'
                    f'<strong>{name}</strong> &nbsp; '
                    f'<span style="font-size:1.1rem">{price:.2f}</span> &nbsp; '
                    f'<span style="color:{color}">{arrow} {chg:+.1f}%</span>'
                    f'<span style="color:#888;font-size:0.82rem">{note}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # Interpretace kombinace VIX + F&G
            st.divider()
            st.subheader("Celkové vyhodnocení prostředí")
            vix_val = macro.get("VIX", {}).get("price", 20)
            fg_score = fg.get("score", 50) if fg.get("ok") else 50

            if vix_val < 20 and fg_score > 50:
                st.success("Příznivé prostředí pro akcie – nízká volatilita + optimismus trhu.")
            elif vix_val > 30 or fg_score < 30:
                st.error("Rizikové prostředí – vysoká volatilita nebo strach na trhu. Konzervativní přístup doporučen.")
            else:
                st.info("Smíšené prostředí – žádný jasný extrém. Řiď se individuálními signály akcií.")


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 5 – Earnings kalendář
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Earnings kalendář":
    st.title("Earnings kalendář")
    st.caption("Příští výsledky hospodaření pro tvoje portfolio.")
    with st.expander("Co jsou Earnings a proč jsou důležité?"):
        st.markdown("""
**Earnings** (výsledky hospodaření) = každé čtvrtletí firmy zveřejňují své skutečné tržby a zisky.
Trh reaguje velmi silně — cena může vyletět nebo propadnout o desítky procent během hodin.

**EPS** (Earnings Per Share) = zisk na akcii. Čím vyšší, tím lépe.

**Proč nekupovat 1–2 týdny před earnings:**
- Cena může být uměle nafouklá spekulacemi
- Po zveřejnění může cena prudce klesnout i při dobrých výsledcích (\"buy the rumor, sell the news\")
- Výsledky jsou v podstatě nepředvídatelné

**Strategie:** Pokud máš BUY signál, ale earnings jsou za méně než 14 dní — počkej na výsledky.
Po zveřejnění se situace vyjasní a signál bude spolehlivější.
        """)

    with st.spinner("Načítám earnings data..."):
        earnings = get_portfolio_earnings(PORTFOLIO)

    if not earnings:
        st.warning("Nepodařilo se načíst earnings data.")
    else:
        for e in earnings:
            ed = e.get("earnings_date")
            days = e.get("days_until")

            if ed is None:
                continue

            if days is not None and days < 0:
                # Proběhlé – šedé
                css = "card-hold"
                badge_html = '<span class="badge-hold">PROBĚHLO</span>'
                date_str = f"{ed} (před {abs(days)} dny)"
            elif days is not None and days <= 7:
                css = "card-sell"
                badge_html = '<span class="badge-sell">TENTO TÝDEN</span>'
                date_str = f"{ed} (za {days} dní)"
            elif days is not None and days <= 14:
                css = "card-radar"
                badge_html = f'<span style="background:#f59e0b;color:#000;padding:2px 8px;border-radius:4px;font-weight:700;font-size:0.8rem">ZA {days} DNÍ</span>'
                date_str = f"{ed}"
            else:
                css = "card-hold"
                badge_html = f'<span class="badge-hold">ZA {days} DNÍ</span>' if days else '<span class="badge-hold">---</span>'
                date_str = f"{ed}" if ed else "Neznámo"

            eps_html = ""
            if e.get("eps_estimate"):
                eps_html = f'&nbsp;|&nbsp; EPS odhad: <b>{e["eps_estimate"]:.2f}</b>'

            st.markdown(
                f'<div class="{css}">'
                f'{badge_html} &nbsp; '
                f'<strong>{e["name"]}</strong> '
                f'<span style="color:#888">{e["ticker"]}</span>'
                f'&nbsp;&nbsp;<span style="color:#aaa">{date_str}</span>'
                f'{eps_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.divider()
        st.info(
            "Strategie: Pokud máš BUY signál na akcii, ale earnings jsou za méně než 14 dní, "
            "zvažuj počkat na výsledky — výsledky mohou signál potvrdit nebo zvrátit."
        )


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 6 – Korelace portfolia
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Korelace portfolia":
    st.title("Korelace portfolia")
    st.caption("Jak moc se akcie pohybují společně — odhalí skrytou koncentraci rizika.")
    with st.expander("Co je korelace a proč na ní záleží?"):
        st.markdown("""
**Korelace** = číslo od -1 do +1, které říká, jak moc se dvě akcie pohybují společně.

| Hodnota | Meaning | Příklad |
|---|---|---|
| **+1.0** | Pohybují se identicky | NVDA a AMD — oba semiconductory |
| **+0.8** | Silná shoda | Většina tech akcií spolu |
| **0.0** | Nezávislé | Tech akcie vs. zlato |
| **-1.0** | Pohybují se opačně | Vzácné, hedgingové páry |

**Proč je to důležité?**
Pokud máš NVDA + AMD + TSM, všechny jsou v semiconductor sektoru a silně korelují.
Když sektor klesne (např. kvůli celním válkám s Čínou), klesnou všechny najednou.
Myslíš si, že máš 3 různé pozice, ale ve skutečnosti máš 1 velkou sázku na semiconductory.

**Barvy v heatmapě:**
- Tmavě červená = vysoká kladná korelace (riziko)
- Tmavě modrá = záporná korelace (dobrá diverzifikace)
- Střední = nízká korelace (dobré)
        """)

    with st.spinner("Načítám data pro korelační analýzu..."):
        closes = {}
        for name, (ticker, currency, sector) in PORTFOLIO.items():
            df = load_data(ticker, period)
            if df is not None and len(df) > 30:
                closes[name.split()[0]] = df["Close"]

    if len(closes) < 2:
        st.error("Nedostatek dat pro korelaci.")
    else:
        price_df = pd.DataFrame(closes).dropna()
        returns  = price_df.pct_change().dropna()
        corr     = returns.corr()

        # Heatmapa
        fig_corr = go.Figure(go.Heatmap(
            z=corr.values,
            x=corr.columns.tolist(),
            y=corr.index.tolist(),
            colorscale=[
                [0.0,  "#1d4ed8"],
                [0.5,  "#1e1e2e"],
                [1.0,  "#b91c1c"],
            ],
            zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in corr.values],
            texttemplate="%{text}",
            textfont={"size": 11},
        ))
        fig_corr.update_layout(
            template="plotly_dark",
            height=500,
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig_corr, use_container_width=True)

        # Varování na vysoké korelace
        st.subheader("Rizikové páry (korelace > 0.80)")
        high_corr = []
        cols = corr.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                v = corr.iloc[i, j]
                if v > 0.80:
                    high_corr.append((cols[i], cols[j], v))

        if high_corr:
            for a, b, v in sorted(high_corr, key=lambda x: -x[2]):
                st.warning(f"**{a}** ↔ **{b}**: korelace {v:.2f} – pohybují se velmi podobně, zdvojené riziko v sektoru.")
        else:
            st.success("Žádné extrémně korelované páry. Portfolio je dobře diverzifikované.")

        # Výkonnostní přehled (normalizovaná cena)
        st.subheader("Normalizovaná výkonnost (báze = 100)")
        normalized = (price_df / price_df.iloc[0] * 100)
        fig_norm = go.Figure()
        colors_list = ["#60a5fa","#34d399","#f59e0b","#f87171","#a78bfa",
                       "#fb923c","#4ade80","#38bdf8","#e879f9","#facc15","#94a3b8"]
        for idx, col in enumerate(normalized.columns):
            fig_norm.add_trace(go.Scatter(
                x=normalized.index, y=normalized[col],
                name=col,
                line=dict(width=1.8, color=colors_list[idx % len(colors_list)]),
            ))
        fig_norm.add_hline(y=100, line=dict(color="#666", dash="dot", width=1))
        fig_norm.update_layout(
            template="plotly_dark", height=380,
            margin=dict(l=0, r=0, t=20, b=0),
            legend=dict(orientation="h", y=-0.15),
        )
        st.plotly_chart(fig_norm, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 7 – Backtest signálů
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Backtest signálů":
    st.title("Backtest signálů")
    st.caption(
        "Jak by dopadly BUY/SELL signály tohoto systému na historických datech. "
        "Win rate = procento obchodů v zisku. Backtest negarantuje budoucí výsledky."
    )

    all_bt_stocks = {**{n: t for n, (t, c, s) in PORTFOLIO.items()},
                     **{n: t for n, (t, c, s) in RADAR_STOCKS.items()}}

    bt_choice = st.selectbox("Vyber akcii pro backtest", list(all_bt_stocks.keys()))
    bt_period = st.select_slider("Historické období", ["1y", "2y", "3y", "5y"], value="2y")
    bt_ticker = all_bt_stocks[bt_choice]

    if st.button("Spustit backtest", type="primary"):
        with st.spinner(f"Počítám backtest pro {bt_ticker} za {bt_period}... (může trvat 20–60s)"):
            result = run_backtest(bt_ticker, period=bt_period)

        if not result.get("ok"):
            st.error(f"Chyba: {result.get('error', 'Neznámá chyba')}")
        else:
            # Souhrnná tabulka
            st.subheader("Souhrnné výsledky")
            tbl = backtest_summary_table(result)
            if not tbl.empty:
                st.dataframe(tbl, hide_index=True, use_container_width=True)

            # Detailní grafy
            for action in ("BUY", "SELL"):
                data = result.get(action, {})
                if data.get("count", 0) == 0:
                    continue

                label = "BUY" if action == "BUY" else "SELL"
                color = "#22c55e" if action == "BUY" else "#ef4444"
                st.subheader(f"{label} signály – distribuce výnosů")

                trades = data.get("trades", [])
                for fd in [10, 20, 30]:
                    key = f"ret_{fd}d"
                    rets = [t[key] for t in trades if key in t]
                    if not rets:
                        continue

                    fig_hist = go.Figure()
                    fig_hist.add_trace(go.Histogram(
                        x=rets,
                        nbinsx=20,
                        marker_color=color,
                        opacity=0.8,
                        name=f"{fd}D výnosy",
                    ))
                    fig_hist.add_vline(x=0, line=dict(color="white", dash="dash"))
                    fig_hist.add_vline(
                        x=float(np.mean(rets)),
                        line=dict(color="#f59e0b", dash="dot"),
                        annotation_text=f"avg {np.mean(rets):+.1f}%",
                    )
                    wr = sum(1 for r in rets if r > 0) / len(rets) * 100
                    fig_hist.update_layout(
                        title=f"Horizon {fd} dní | Win rate: {wr:.0f}% | n={len(rets)}",
                        template="plotly_dark", height=220,
                        margin=dict(l=0, r=0, t=40, b=10),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)

            st.info(
                "Interpretace: Win rate > 55% a průměrný výnos > 0 naznačuje, "
                "že signály mají historicky prediktivní hodnotu. "
                "Pod 45% win rate je signální systém pro danou akcii méně spolehlivý."
            )
    else:
        st.info("Vyber akcii a klikni na 'Spustit backtest'.")


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 8 – Sektorový přehled
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Sektorový přehled":
    st.title("Sektorový přehled")
    st.caption("Výkonnost hlavních tržních sektorů. Pomáhá pochopit kontext – jde dolů jen tvoje akcie nebo celý sektor?")

    sector_period_map = {"1 týden": "5d", "1 měsíc": "1mo", "3 měsíce": "3mo", "6 měsíců": "6mo"}
    sp_label = st.selectbox("Období sektorů", list(sector_period_map.keys()), index=1)
    sp = sector_period_map[sp_label]

    with st.spinner("Načítám sektorová data..."):
        sectors = fetch_sectors(sp)

    if not sectors:
        st.error("Nepodařilo se načíst sektorová data.")
    else:
        # Sloupcový graf sektorů
        names   = [s["name"] for s in sectors]
        chg_p   = [s["chg_period"] for s in sectors]
        chg_d   = [s["chg_day"] for s in sectors]
        bar_colors = ["#22c55e" if v >= 0 else "#ef4444" for v in chg_p]

        fig_sec = go.Figure()
        fig_sec.add_trace(go.Bar(
            x=names, y=chg_p,
            marker_color=bar_colors,
            name=f"Za {sp_label}",
            text=[f"{v:+.1f}%" for v in chg_p],
            textposition="outside",
        ))
        fig_sec.add_trace(go.Scatter(
            x=names, y=chg_d,
            mode="markers",
            marker=dict(size=10, color=["#22c55e" if v >= 0 else "#ef4444" for v in chg_d],
                        symbol="diamond"),
            name="Dnešní změna",
        ))
        fig_sec.add_hline(y=0, line=dict(color="#666", width=1))
        fig_sec.update_layout(
            template="plotly_dark", height=380,
            margin=dict(l=0, r=0, t=20, b=0),
            legend=dict(orientation="h", y=1.1),
            yaxis_title="Výkonnost (%)",
        )
        st.plotly_chart(fig_sec, use_container_width=True)

        # Tabulka + komentáře
        st.subheader("Detail sektorů")
        for s in sectors:
            cp = s["chg_period"]
            cd = s["chg_day"]
            css = "card-buy" if cp > 2 else "card-sell" if cp < -2 else "card-hold"
            color_p = "#22c55e" if cp >= 0 else "#ef4444"
            color_d = "#22c55e" if cd >= 0 else "#ef4444"
            st.markdown(
                f'<div class="{css}" style="padding:10px">'
                f'<strong>{s["name"]}</strong> '
                f'<span style="color:#888;font-size:0.85rem">{s["symbol"]}</span>'
                f'&nbsp;&nbsp; {s["price"]:.2f} USD'
                f'&nbsp;|&nbsp; <span style="color:{color_p}">{sp_label}: {cp:+.1f}%</span>'
                f'&nbsp;|&nbsp; <span style="color:{color_d}">Dnes: {cd:+.1f}%</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Kontext pro tvoje portfolio
        st.divider()
        st.subheader("Jak to ovlivňuje tvoje portfolio")

        portfolio_sectors = {
            "Technologie": ["NVIDIA", "AMD", "Alphabet", "Microsoft", "Palo Alto", "Amazon", "Taiwan Semi"],
            "Obrana & Průmysl": ["SAAB", "Rheinmetall"],
        }
        sector_perf = {s["name"]: s["chg_period"] for s in sectors}

        for sector_name, stocks in portfolio_sectors.items():
            perf = sector_perf.get(sector_name)
            if perf is None:
                continue
            color = "#22c55e" if perf >= 0 else "#ef4444"
            stocks_str = ", ".join(stocks)
            st.markdown(
                f'**{sector_name}** ({sp_label}: <span style="color:{color}">{perf:+.1f}%</span>) '
                f'– ovlivňuje: {stocks_str}',
                unsafe_allow_html=True,
            )


# ── Patička ───────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"Aktualizováno: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}  |  "
    "Data: Yahoo Finance · Finviz · MarketWatch · CNN  |  "
    "Tento nástroj NENÍ finančním poradenstvím."
)
