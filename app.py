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
    generate_signals_with_news,
)
from news_scraper import get_all_news, news_sentiment_summary
try:
    from macro import fetch_fear_greed, fetch_macro_tickers, fetch_sectors, fg_label
except Exception as _macro_err:
    raise ImportError(f"Nelze importovat macro.py: {type(_macro_err).__name__}: {_macro_err}") from _macro_err
from earnings import get_portfolio_earnings, get_earnings
from backtest import run_backtest, backtest_summary_table
from ai_sentiment import enrich_news_with_ai, news_ai_summary, sentiment_to_signal
from claude_analysis import analyze_stock_with_claude, get_peer_comparison
from trade_journal import add_trade, get_trades, get_performance, get_stats, delete_trade, update_trade, import_from_csv, init_db

# ── Konfigurace stránky ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Advisor",
    page_icon="📈",
    layout="wide",
)

# ── Google login ─────────────────────────────────────────────────────────────
_ALLOWED_EMAIL = "seusdt@gmail.com"


if not st.user.is_logged_in:
    st.markdown("""
    <style>
    .login-wrap { display:flex; flex-direction:column; align-items:center;
                  justify-content:center; min-height:70vh; gap:24px; }
    .login-title { font-size:2rem; font-weight:700; color:#f1f5f9; }
    .login-sub   { color:#94a3b8; font-size:1rem; }
    </style>
    <div class="login-wrap">
      <div style="font-size:3rem">📈</div>
      <div class="login-title">Stock Advisor</div>
      <div class="login-sub">Přihlas se pro přístup k portfoliu a analýzám</div>
    </div>
    """, unsafe_allow_html=True)
    st.login("google")
    st.stop()

if st.user.email != _ALLOWED_EMAIL:
    st.logout()
    st.error("Přístup zamítnut.")
    st.stop()

# ── PWA meta tagy (ikona při přidání na plochu telefonu) ─────────────────────
st.markdown("""
<link rel="manifest" href="/app/static/manifest.json">
<link rel="apple-touch-icon" href="/app/static/icon.svg">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Stock Advisor">
<meta name="theme-color" content="#0f172a">
""", unsafe_allow_html=True)

# ── Styly ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Skryj Streamlit branding a systémové prvky ── */
#MainMenu, footer, header                            { display: none !important; height: 0 !important; }
[data-testid="stToolbar"]                            { display: none !important; height: 0 !important; }
[data-testid="stDecoration"]                         { display: none !important; height: 0 !important; }
[data-testid="stStatusWidget"]                       { display: none !important; height: 0 !important; }
[data-testid="stHeader"]                             { display: none !important; height: 0 !important; min-height: 0 !important; }
.stDeployButton                                      { display: none !important; }
[data-testid="baseButton-headerNoPadding"]           { display: none !important; }
.viewerBadge_container__1QSob                        { display: none !important; }
#stDecoration                                        { display: none !important; }
/* Footer odkazy na Streamlit */
[data-testid="stFooter"]                             { display: none !important; }
.st-emotion-cache-164nlkn                            { display: none !important; }
a[href*="streamlit.io"]                              { display: none !important; }
a[href*="share.streamlit.io"]                        { display: none !important; }
a[href*="github.com"][target]                        { display: none !important; }
/* Odstraň veškerý horní padding */
.stMainBlockContainer, [data-testid="stMain"] > div  { padding-top: 0 !important; }
[data-testid="stAppViewBlockContainer"]              { padding-top: 0 !important; }
section[data-testid="stSidebar"] ~ div               { padding-top: 0 !important; }
.main .block-container                               { padding-top: 0 !important; }
/* Zmenši globální mezery mezi sekcemi */
h3 { margin-top: 0.3rem !important; margin-bottom: 0.1rem !important; }
hr { margin: 4px 0 !important; }
[data-testid="stVerticalBlock"] > div { gap: 0.35rem !important; }

/* Zmenši mezery mezi expandery */
[data-testid="stExpander"] { margin-bottom: 0 !important; margin-top: 0 !important; }
[data-testid="stExpander"] + [data-testid="stExpander"] { border-top: none !important; }
div:has(> [data-testid="stExpander"]) { gap: 2px !important; }
/* Wrappery kolem expanderů */
[data-testid="stVerticalBlock"] > div:has([data-testid="stExpander"]) {
  margin-top: 0 !important; margin-bottom: 0 !important; padding: 0 !important;
}
.st-emotion-cache-1wrcr25, .st-emotion-cache-keje5e,
.st-emotion-cache-1gulkj5, .element-container:has([data-testid="stExpander"]) {
  margin: 0 !important; padding-top: 0 !important; padding-bottom: 0 !important;
}

/* Plynulý přechod při překliknutí stránek */
[data-testid="stMainBlockContainer"] {
  animation: fadeIn 0.25s ease-in-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
/* Plotly toolbar skryj všude */
.modebar                                             { display: none !important; }
/* Zamez zachycení scrollu grafem na mobilu – grafy nepřebírají dotyk */
@media (max-width: 768px) {
  .js-plotly-plot, .js-plotly-plot .plotly, .plotly-graph-div {
    touch-action: pan-y !important;
    pointer-events: none !important;
  }
}

/* ── Expander – menší rozestupy ── */
/* Streamlit flex gap je ~1rem; negativní margin na obou stranách ho redukuje */
div[data-testid="element-container"]:has(details),
div[data-testid="stElementContainer"]:has(details) {
    margin-top: -10px !important;
    margin-bottom: -10px !important;
}
details { margin: 0 !important; padding-bottom: 0 !important; }

/* ── Základní karty ── */
.signal-buy  { background:#0d6e2f; color:#fff; padding:10px 20px; border-radius:8px;
               font-size:1.8rem; font-weight:700; text-align:center; }
.signal-sell { background:#8b0000; color:#fff; padding:10px 20px; border-radius:8px;
               font-size:1.8rem; font-weight:700; text-align:center; }
.signal-hold { background:#2a2a3a; color:#ccc; padding:10px 20px; border-radius:8px;
               font-size:1.8rem; font-weight:700; text-align:center; }
.card-buy    { background:#0a2e18; border:2px solid #22c55e; border-radius:10px;
               padding:14px; margin:6px 0; line-height:1.6;
               overflow-x:hidden; overflow-wrap:anywhere; word-break:break-word; }
.card-sell   { background:#2e0a0a; border:2px solid #ef4444; border-radius:10px;
               padding:14px; margin:6px 0; line-height:1.6;
               overflow-x:hidden; overflow-wrap:anywhere; word-break:break-word; }
.card-hold   { background:#1a1a2e; border:1px solid #444; border-radius:10px;
               padding:14px; margin:6px 0; line-height:1.6;
               overflow-x:hidden; overflow-wrap:anywhere; word-break:break-word; }
.card-radar  { background:#1a1a0a; border:2px solid #f59e0b; border-radius:10px;
               padding:14px; margin:6px 0; line-height:1.6;
               overflow-x:hidden; overflow-wrap:anywhere; word-break:break-word; }
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
    /* Minimální horní padding – nav lišta je sticky, obsah hned pod ní */
    .block-container { padding: 0 0.6rem 2rem !important; }
    .stMainBlockContainer, [data-testid="stMain"] > div { padding-top: 0 !important; }
    [data-testid="stAppViewBlockContainer"] { padding-top: 0 !important; }

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

    /* Segmented control – celá šířka na mobilu */
    /* calc(100vw - 1.2rem) = viewport minus padding block-containeru */
    [data-testid="stSegmentedControl"] {
        width: calc(100vw - 1.2rem) !important;
        max-width: 100% !important;
        display: block !important;
        box-sizing: border-box !important;
    }
    [data-testid="stSegmentedControl"] > div {
        width: 100% !important;
        display: block !important;
        box-sizing: border-box !important;
    }
    [data-testid="stSegmentedControl"] div[role="group"] {
        width: 100% !important;
        display: flex !important;
        box-sizing: border-box !important;
    }
    [data-testid="stSegmentedControl"] div[role="group"] > * {
        flex: 1 !important;
        text-align: center !important;
        justify-content: center !important;
        min-width: 0 !important;
        overflow: hidden !important;
    }

}


/* ── Tablet ── */
@media (max-width: 1024px) and (min-width: 769px) {
    .block-container { padding: 1rem 1.5rem 2rem !important; }
    .card-buy, .card-sell, .card-hold, .card-radar { font-size: 0.92rem !important; }
}

/* ── Desktop – ohraničení šířky obsahu ── */
@media (min-width: 769px) {
    .block-container {
        max-width: 1080px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    /* Stat boxy v Deníku – větší čísla */
    .stats-grid6 .stat-box-val { font-size: 1.35rem !important; }
}

/* ── Portfolio karta – nový layout ── */
.pf-card {
    border-radius: 10px;
    padding: 12px 14px;
    margin: 6px 0;
    display: grid;
    grid-template-columns: auto 1fr auto;
    grid-template-rows: auto auto;
    gap: 2px 12px;
    align-items: center;
}
.pf-card-buy  { background:#0a2e18; border:2px solid #22c55e; }
.pf-card-sell { background:#2e0a0a; border:2px solid #ef4444; }
.pf-card-hold { background:#1a1a2e; border:1px solid #444; }

/* levý sloupec – badge + skóre inline */
.pf-left { grid-column:1; grid-row:1/3; display:flex; flex-direction:row; gap:5px; align-items:center; white-space:nowrap; }

/* střed – název + ticker */
.pf-name  { grid-column:2; grid-row:1; font-size:1.0rem; font-weight:700; color:#f1f5f9; text-align:left; }
.pf-meta  { grid-column:2; grid-row:2; font-size:0.78rem; color:#94a3b8; display:flex; flex-wrap:wrap; gap:6px; align-items:center; text-align:left; }

/* pravý sloupec – cena + změna */
.pf-price-block { grid-column:3; grid-row:1/3; text-align:right; }
.pf-price   { font-size:1.05rem; font-weight:700; color:#f1f5f9; white-space:nowrap; }
.pf-change  { font-size:0.88rem; font-weight:600; white-space:nowrap; }

/* signálové důvody */
.pf-reasons { grid-column:1/4; grid-row:3; font-size:0.77rem; margin-top:4px; line-height:1.6; }

/* stat pill */
.pf-pill { background:#ffffff14; border-radius:4px; padding:1px 6px; font-size:0.75rem; white-space:nowrap; }

@media (max-width: 768px) {
    .pf-card { grid-template-columns: 1fr auto; grid-template-rows: auto auto auto auto; gap:4px 8px; padding:10px 10px; }
    .pf-left  { grid-column:1; grid-row:1; }
    .pf-name  { grid-column:1; grid-row:2; font-size:0.95rem; }
    .pf-meta  { grid-column:1/3; grid-row:3; }
    .pf-price-block { grid-column:2; grid-row:1/3; }
    .pf-reasons { grid-column:1/3; grid-row:4; }
    .pf-price { font-size:0.95rem; }
    /* Columns zůstanou vodorovně i na mobilu */
    [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 4px !important; }
    [data-testid="stHorizontalBlock"] > [data-testid="column"] { min-width: 0 !important; flex: 1 !important; }
}

/* ── Responsivní grid pro peer comparison ── */
.peer-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 8px;
    margin-top: 8px;
}
.peer-card {
    text-align: center;
    padding: 8px 4px;
    border-radius: 6px;
    background: #1a1a2e;
}
.peer-card.peer-main {
    background: #1e3a5f;
    border: 1px solid #3b82f6;
}
.peer-ticker  { font-weight: bold; font-size: 0.9rem; }
.peer-chg-pos { color: #22c55e; font-size: 1.05rem; font-weight: 600; }
.peer-chg-neg { color: #ef4444; font-size: 1.05rem; font-weight: 600; }
.peer-price   { color: #666; font-size: 0.78rem; margin-top: 2px; }

/* ── Responsivní grid pro indikátory (5 sloupců → 2+3 na mobilu) ── */
.indicator-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
    margin: 8px 0 12px;
}
.indicator-card {
    background: #1a1a2e;
    border-radius: 8px;
    padding: 10px 12px;
    text-align: center;
}
.indicator-label { color: #94a3b8; font-size: 0.75rem; margin-bottom: 4px; }
.indicator-value { font-size: 1.15rem; font-weight: 700; color: #e2e8f0; }
.indicator-delta { font-size: 0.75rem; color: #94a3b8; margin-top: 2px; }

/* ── Claude AI sekce ── */
.claude-summary {
    background: #1e293b;
    border-left: 4px solid #60a5fa;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 12px;
    line-height: 1.6;
}
.claude-label {
    color: #94a3b8;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
}
.claude-hint {
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 12px 16px;
    margin-top: 8px;
}

@media (max-width: 768px) {
    /* Indikátory: 2 + 3 */
    .indicator-grid { grid-template-columns: repeat(2, 1fr) !important; }
    .indicator-value { font-size: 1rem !important; }

    /* Peer karty – minimálně 2 na řádek */
    .peer-grid { grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)) !important; }
    .peer-ticker { font-size: 0.82rem !important; }

    /* Claude sekce */
    .claude-summary { padding: 10px 12px !important; font-size: 0.88rem !important; }
    .claude-hint    { padding: 10px 12px !important; font-size: 0.88rem !important; }
}

@media (max-width: 1024px) and (min-width: 769px) {
    /* Tablet: indikátory 3+2 */
    .indicator-grid { grid-template-columns: repeat(3, 1fr) !important; }
    /* Peer min 90px */
    .peer-grid { grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)) !important; }
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
    "Intel":                    ("INTC",    "USD", "tech"),
    "Oracle":                   ("ORCL",    "USD", "tech"),
    "Baidu":                    ("BIDU",    "USD", "tech"),
    "Virgin Galactic":          ("SPCE",    "USD", "tech"),
    "Parker Hannifin":          ("PH",      "USD", "defense"),
    "NIO":                      ("NIO",     "USD", "tech"),
}

# ── Radar – akcie rozdělené podle sektoru (mapování na sektorové ETF z macro.py)
# Sektor musí odpovídat klíčům v SECTOR_ETFS v macro.py
RADAR_STOCKS = {
    # ── Technologie – USA (XLK) ───────────────────────────────────────────────
    "Meta":             ("META",  "USD", "Technologie"),
    "Tesla":            ("TSLA",  "USD", "Technologie"),
    "CrowdStrike":      ("CRWD",  "USD", "Technologie"),
    "Palantir":         ("PLTR",  "USD", "Technologie"),
    "Broadcom":         ("AVGO",  "USD", "Technologie"),
    "ServiceNow":       ("NOW",   "USD", "Technologie"),
    "Apple":            ("AAPL",  "USD", "Technologie"),
    "Oracle":           ("ORCL",  "USD", "Technologie"),
    "Salesforce":       ("CRM",   "USD", "Technologie"),
    "Snowflake":        ("SNOW",  "USD", "Technologie"),
    "Cloudflare":       ("NET",   "USD", "Technologie"),
    "Datadog":          ("DDOG",  "USD", "Technologie"),
    "MongoDB":          ("MDB",   "USD", "Technologie"),
    "Shopify":          ("SHOP",  "USD", "Technologie"),
    "Intuit":           ("INTU",  "USD", "Technologie"),
    "Qualcomm":         ("QCOM",  "USD", "Technologie"),
    "Texas Instruments":("TXN",   "USD", "Technologie"),
    "Micron":           ("MU",    "USD", "Technologie"),
    "Applied Materials":("AMAT",  "USD", "Technologie"),
    "Lam Research":     ("LRCX",  "USD", "Technologie"),
    "KLA Corp":         ("KLAC",  "USD", "Technologie"),
    "Fortinet":         ("FTNT",  "USD", "Technologie"),
    "Zscaler":          ("ZS",    "USD", "Technologie"),
    "Okta":             ("OKTA",  "USD", "Technologie"),
    "Workday":          ("WDAY",  "USD", "Technologie"),
    "Autodesk":         ("ADSK",  "USD", "Technologie"),
    "Uber":             ("UBER",  "USD", "Technologie"),
    "Airbnb":           ("ABNB",  "USD", "Technologie"),
    "Block":            ("SQ",    "USD", "Technologie"),
    "Coinbase":         ("COIN",  "USD", "Technologie"),
    "Roblox":           ("RBLX",  "USD", "Technologie"),
    "Twilio":           ("TWLO",  "USD", "Technologie"),
    "HubSpot":          ("HUBS",  "USD", "Technologie"),
    "Confluent":        ("CFLT",  "USD", "Technologie"),
    "HashiCorp":        ("HCP",   "USD", "Technologie"),
    # ── Technologie – Evropa & Asie ─────────────────────────────────────────
    "ASML":             ("ASML",  "USD", "Technologie"),
    "SAP":              ("SAP",   "USD", "Technologie"),
    "Infineon":         ("IFNNY", "USD", "Technologie"),
    "Nokia":            ("NOK",   "USD", "Technologie"),
    "Ericsson":         ("ERIC",  "USD", "Technologie"),
    "STMicroelectronics":("STM",  "USD", "Technologie"),
    "Capgemini":        ("CAP.PA","EUR", "Technologie"),
    "Dassault Systèmes":("DSY.PA","EUR", "Technologie"),
    # ── Obrana & Průmysl (ITA) ───────────────────────────────────────────────
    "BAE Systems":      ("BA.L",  "GBP", "Obrana & Průmysl"),
    "Airbus":           ("AIR.PA","EUR", "Obrana & Průmysl"),
    "Lockheed Martin":  ("LMT",   "USD", "Obrana & Průmysl"),
    "RTX":              ("RTX",   "USD", "Obrana & Průmysl"),
    "Northrop Grumman": ("NOC",   "USD", "Obrana & Průmysl"),
    "Leonardo":         ("LDO.MI","EUR", "Obrana & Průmysl"),
    "Caterpillar":      ("CAT",   "USD", "Obrana & Průmysl"),
    "Siemens":          ("SIEGY", "USD", "Obrana & Průmysl"),
    "Rolls-Royce":      ("RR.L",  "GBP", "Obrana & Průmysl"),
    "General Dynamics": ("GD",    "USD", "Obrana & Průmysl"),
    "Boeing":           ("BA",    "USD", "Obrana & Průmysl"),
    "Honeywell":        ("HON",   "USD", "Obrana & Průmysl"),
    "Thales":           ("HO.PA", "EUR", "Obrana & Průmysl"),
    "General Electric": ("GE",    "USD", "Obrana & Průmysl"),
    "Deere & Company":  ("DE",    "USD", "Obrana & Průmysl"),
    "3M":               ("MMM",   "USD", "Obrana & Průmysl"),
    "Emerson Electric": ("EMR",   "USD", "Obrana & Průmysl"),
    "Parker Hannifin":  ("PH",    "USD", "Obrana & Průmysl"),
    # ── Zdravotnictví (XLV) ──────────────────────────────────────────────────
    "Eli Lilly":        ("LLY",   "USD", "Zdravotnictví"),
    "Novo Nordisk":     ("NVO",   "USD", "Zdravotnictví"),
    "Johnson & Johnson":("JNJ",   "USD", "Zdravotnictví"),
    "AbbVie":           ("ABBV",  "USD", "Zdravotnictví"),
    "UnitedHealth":     ("UNH",   "USD", "Zdravotnictví"),
    "AstraZeneca":      ("AZN",   "USD", "Zdravotnictví"),
    "Roche":            ("RHHBY", "USD", "Zdravotnictví"),
    "Pfizer":           ("PFE",   "USD", "Zdravotnictví"),
    "Merck":            ("MRK",   "USD", "Zdravotnictví"),
    "Intuitive Surgical":("ISRG", "USD", "Zdravotnictví"),
    "Bristol-Myers":    ("BMY",   "USD", "Zdravotnictví"),
    "Thermo Fisher":    ("TMO",   "USD", "Zdravotnictví"),
    "Danaher":          ("DHR",   "USD", "Zdravotnictví"),
    "Medtronic":        ("MDT",   "USD", "Zdravotnictví"),
    "Regeneron":        ("REGN",  "USD", "Zdravotnictví"),
    "Moderna":          ("MRNA",  "USD", "Zdravotnictví"),
    "Vertex Pharma":    ("VRTX",  "USD", "Zdravotnictví"),
    "Boston Scientific":("BSX",   "USD", "Zdravotnictví"),
    "Biogen":           ("BIIB",  "USD", "Zdravotnictví"),
    "Gilead Sciences":  ("GILD",  "USD", "Zdravotnictví"),
    # ── Energie (XLE) ────────────────────────────────────────────────────────
    "ExxonMobil":       ("XOM",   "USD", "Energie"),
    "Chevron":          ("CVX",   "USD", "Energie"),
    "Shell":            ("SHEL",  "USD", "Energie"),
    "BP":               ("BP",    "USD", "Energie"),
    "Equinor":          ("EQNR",  "USD", "Energie"),
    "Schlumberger":     ("SLB",   "USD", "Energie"),
    "Occidental":       ("OXY",   "USD", "Energie"),
    "TotalEnergies":    ("TTE",   "USD", "Energie"),
    "Enbridge":         ("ENB",   "USD", "Energie"),
    "ConocoPhillips":   ("COP",   "USD", "Energie"),
    "EOG Resources":    ("EOG",   "USD", "Energie"),
    "Marathon Petroleum":("MPC",  "USD", "Energie"),
    "Williams Cos.":    ("WMB",   "USD", "Energie"),
    "Kinder Morgan":    ("KMI",   "USD", "Energie"),
    "Pioneer Natural":  ("PXD",   "USD", "Energie"),
    # ── Finance (XLF) ────────────────────────────────────────────────────────
    "JPMorgan Chase":   ("JPM",   "USD", "Finance"),
    "Goldman Sachs":    ("GS",    "USD", "Finance"),
    "Visa":             ("V",     "USD", "Finance"),
    "Mastercard":       ("MA",    "USD", "Finance"),
    "Berkshire Hath.":  ("BRK-B", "USD", "Finance"),
    "BlackRock":        ("BLK",   "USD", "Finance"),
    "HSBC":             ("HSBC",  "USD", "Finance"),
    "UBS":              ("UBS",   "USD", "Finance"),
    "PayPal":           ("PYPL",  "USD", "Finance"),
    "Deutsche Bank":    ("DB",    "USD", "Finance"),
    "Morgan Stanley":   ("MS",    "USD", "Finance"),
    "Bank of America":  ("BAC",   "USD", "Finance"),
    "Citigroup":        ("C",     "USD", "Finance"),
    "Wells Fargo":      ("WFC",   "USD", "Finance"),
    "American Express": ("AXP",   "USD", "Finance"),
    "Charles Schwab":   ("SCHW",  "USD", "Finance"),
    "CME Group":        ("CME",   "USD", "Finance"),
    "Intercont. Exchange":("ICE", "USD", "Finance"),
    # ── Spotřeba & Luxus (XLY) ───────────────────────────────────────────────
    "Costco":           ("COST",  "USD", "Spotřeba"),
    "McDonald's":       ("MCD",   "USD", "Spotřeba"),
    "Nike":             ("NKE",   "USD", "Spotřeba"),
    "LVMH":             ("MC.PA", "EUR", "Spotřeba"),
    "L'Oréal":          ("OR.PA", "EUR", "Spotřeba"),
    "Hermès":           ("RMS.PA","EUR", "Spotřeba"),
    "Inditex":          ("ITX.MC","EUR", "Spotřeba"),
    "Nestlé":           ("NESN.SW","CHF","Spotřeba"),
    "Alibaba":          ("BABA",  "USD", "Spotřeba"),
    "Toyota":           ("TM",    "USD", "Spotřeba"),
    "Procter & Gamble": ("PG",    "USD", "Spotřeba"),
    "Starbucks":        ("SBUX",  "USD", "Spotřeba"),
    "Home Depot":       ("HD",    "USD", "Spotřeba"),
    "Lowe's":           ("LOW",   "USD", "Spotřeba"),
    "Ferrari":          ("RACE",  "USD", "Spotřeba"),
    "Volkswagen":       ("VOW3.DE","EUR","Spotřeba"),
    "BMW":              ("BMW.DE","EUR", "Spotřeba"),
    "Unilever":         ("UL",    "USD", "Spotřeba"),
    "Kering":           ("KER.PA","EUR", "Spotřeba"),
    "Richemont":        ("CFR.SW","CHF", "Spotřeba"),
    # ── Utility (XLU) ────────────────────────────────────────────────────────
    "NextEra Energy":   ("NEE",   "USD", "Utility"),
    "Duke Energy":      ("DUK",   "USD", "Utility"),
    "Iberdrola":        ("IBDRY", "USD", "Utility"),
    "Enel":             ("ENLAY", "USD", "Utility"),
    "American El. Power":("AEP",  "USD", "Utility"),
    "Southern Company": ("SO",    "USD", "Utility"),
    "Dominion Energy":  ("D",     "USD", "Utility"),
    "Sempra":           ("SRE",   "USD", "Utility"),
    # ── Materiály & Těžba (XLB) ──────────────────────────────────────────────
    "Freeport-McMoRan": ("FCX",   "USD", "Materiály"),
    "Newmont":          ("NEM",   "USD", "Materiály"),
    "BHP":              ("BHP",   "USD", "Materiály"),
    "Rio Tinto":        ("RIO",   "USD", "Materiály"),
    "Vale":             ("VALE",  "USD", "Materiály"),
    "Glencore":         ("GLEN.L","GBP", "Materiály"),
    "Anglo American":   ("AAL.L", "GBP", "Materiály"),
    "Linde":            ("LIN",   "USD", "Materiály"),
    "Air Products":     ("APD",   "USD", "Materiály"),
    "Barrick Gold":     ("GOLD",  "USD", "Materiály"),
    "Albemarle":        ("ALB",   "USD", "Materiály"),
    "Nucor":            ("NUE",   "USD", "Materiály"),
    # ── Komunikace & Média (XLC) ─────────────────────────────────────────────
    "Netflix":          ("NFLX",  "USD", "Komunikace"),
    "Walt Disney":      ("DIS",   "USD", "Komunikace"),
    "Spotify":          ("SPOT",  "USD", "Komunikace"),
    "T-Mobile":         ("TMUS",  "USD", "Komunikace"),
    "Comcast":          ("CMCSA", "USD", "Komunikace"),
    "AT&T":             ("T",     "USD", "Komunikace"),
    "Verizon":          ("VZ",    "USD", "Komunikace"),
    "Warner Bros.":     ("WBD",   "USD", "Komunikace"),
    "Pinterest":        ("PINS",  "USD", "Komunikace"),
    "Snap":             ("SNAP",  "USD", "Komunikace"),
    "Deutsche Telekom": ("DTEGY", "USD", "Komunikace"),
    # ── Reality (XLRE) ───────────────────────────────────────────────────────
    "Prologis":         ("PLD",   "USD", "Reality"),
    "American Tower":   ("AMT",   "USD", "Reality"),
    "Equinix":          ("EQIX",  "USD", "Reality"),
    "Simon Property":   ("SPG",   "USD", "Reality"),
    "Crown Castle":     ("CCI",   "USD", "Reality"),
    "Digital Realty":   ("DLR",   "USD", "Reality"),
    "SBA Comm.":        ("SBAC",  "USD", "Reality"),
    "Welltower":        ("WELL",  "USD", "Reality"),
    # ── Asie & Rozvíjející se trhy ────────────────────────────────────────────
    "Tencent":          ("TCEHY", "USD", "Asie & EM"),
    "JD.com":           ("JD",    "USD", "Asie & EM"),
    "NIO":              ("NIO",   "USD", "Asie & EM"),
    "Sea Limited":      ("SE",    "USD", "Asie & EM"),
    "Grab Holdings":    ("GRAB",  "USD", "Asie & EM"),
    "Infosys":          ("INFY",  "USD", "Asie & EM"),
    "Wipro":            ("WIT",   "USD", "Asie & EM"),
    "BYD":              ("BYDDY", "USD", "Asie & EM"),
    "LG Energy Solution":("LGES.KS","KRW","Asie & EM"),
    "Samsung SDI":      ("006400.KS","KRW","Asie & EM"),
}

# ── Sada tickerů v portfoliu (pro filtrování signálů v radaru) ────────────────
PORTFOLIO_TICKERS = {t for t, _, _ in PORTFOLIO.values()}

# ── Radar zahrnuje i portfolio (bez ETF, bez duplicit) ───────────────────────
_PF_SECTOR_MAP = {"tech": "Technologie", "defense": "Obrana & Průmysl", "etf": None}
_RADAR_TICKERS = {t for t, _, _ in RADAR_STOCKS.values()}
_PORTFOLIO_EXTRA = {
    name: (ticker, currency, _PF_SECTOR_MAP[sector])
    for name, (ticker, currency, sector) in PORTFOLIO.items()
    if _PF_SECTOR_MAP.get(sector) is not None
    and ticker not in _RADAR_TICKERS
}
RADAR_STOCKS_FULL = {**RADAR_STOCKS, **_PORTFOLIO_EXTRA}

# ── Sidebar ───────────────────────────────────────────────────────────────────
refresh = False       # default; přepsáno tlačítkem v sidebaru
period  = "6mo"       # default; přepsáno selectboxem v sidebaru
detail_ticker   = list(PORTFOLIO.values())[0][0]
detail_currency = "USD"
show_ema = True
show_bb  = True
selected_sectors: list = []
investment_horizon = "Střednědobý (3–12 měs.)"

_pages = ["Přehled portfolia", "Detail akcie", "Příležitosti", "Deník"]

# Mobilní navigace – query param přepíše session state před renderem radia
_qp        = st.query_params.get("page",   None)
_qp_ticker = st.query_params.get("ticker", None)
if _qp is not None:
    try:
        _qi = int(_qp)
        if 0 <= _qi < len(_pages):
            st.session_state["nav_page"] = _pages[_qi]
    except ValueError:
        pass
if _qp_ticker:
    # Najdi název akcie z tickeru a nastav rovnou do session_state selectboxu
    _all_combined = {**PORTFOLIO, **RADAR_STOCKS}
    for _n, (_t, _c, _s) in _all_combined.items():
        if _t == _qp_ticker:
            st.session_state["stock_select"] = _n
            break
    st.session_state["nav_page"] = "Detail akcie"
if _qp is not None or _qp_ticker:
    st.query_params.clear()
    st.rerun()

with st.sidebar:
    st.title("Stock Advisor")
    page = st.radio(
        "Zobrazení",
        _pages,
        key="nav_page",
    )
    st.divider()
    # Přihlášený uživatel
    _user = st.user
    if _user.is_logged_in:
        st.caption(f"👤 {_user.name or _user.email}")
        if st.button("Odhlásit se", use_container_width=True):
            st.logout()

# ── Mobilní navigace (zobrazí se jen na malých obrazovkách) ──────────────────
_pages = ["Přehled portfolia", "Detail akcie", "Příležitosti", "Deník"]
_page_icons = ["📊", "🔍", "🎯", "📓"]
st.markdown("""
<style>
.mob-nav { display:none }
@media (max-width: 768px) {
  .mob-nav {
    display: flex; position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
    background: #0f172a; border-bottom: 1px solid #1e293b;
    overflow-x: auto; gap: 0; padding: 0;
    -webkit-overflow-scrolling: touch; scrollbar-width: none;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
  }
  .mob-nav::-webkit-scrollbar { display: none; }
  .mob-nav a {
    flex: 1 1 0; padding: 10px 6px; font-size: 0.78rem;
    color: #94a3b8; text-decoration: none; white-space: nowrap;
    border-bottom: 2px solid transparent; text-align: center;
  }
  .mob-nav a.active { color: #22c55e; border-bottom-color: #22c55e; }
  /* Obsah posuň dolů, aby nebyl skrytý za fixním menu (~44px výška) */
  .block-container { padding-top: 52px !important; }
  [data-testid="stAppViewBlockContainer"] { padding-top: 0 !important; }
}
</style>
""", unsafe_allow_html=True)
_mob_links = "".join(
    f'<a href="?page={i}" target="_self" '
    f'class="{"active" if _pages[i] == page else ""}">{_page_icons[i]} {_pages[i]}</a>'
    for i in range(len(_pages))
)
st.markdown(f'<div class="mob-nav">{_mob_links}</div>', unsafe_allow_html=True)

# Výchozí období pro grafy (pevné – horizonty se načítají interně)
period = "6mo"

with st.sidebar:
    if page == "Detail akcie":
        all_stocks = dict(PORTFOLIO)
        all_stocks.update(RADAR_STOCKS)
        all_stocks["Vlastní ticker..."] = ("CUSTOM", "", "")
        _stock_names = list(all_stocks.keys())
        stock_choice = st.selectbox("Akcie", _stock_names, key="stock_select")
        if stock_choice == "Vlastní ticker...":
            custom = st.text_input("Ticker (např. AAPL)").upper().strip()
            detail_ticker = custom or "AAPL"
            detail_currency = "USD"
        else:
            detail_ticker, detail_currency, _ = all_stocks[stock_choice]

        show_ema = st.checkbox("EMA (20/50/200)", value=True)
        show_bb  = st.checkbox("Bollinger Bands", value=True)

    if page == "Příležitosti":
        all_sectors = sorted(set(v[2] for v in RADAR_STOCKS_FULL.values()))
        selected_sectors = st.multiselect(
            "Filtruj sektor",
            options=all_sectors,
            default=[],
            placeholder="Všechny sektory",
        )

    refresh = st.button("Obnovit data", use_container_width=True)
    st.divider()
    st.caption("**Disclaimer:** Pouze informativní nástroj. Nejedná se o finanční poradenství.")

# ── Cache funkce ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_usdczk() -> float:
    try:
        df = yf.download("USDCZK=X", period="5d", auto_adjust=True, progress=False)
        if df.empty:
            return 23.0
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return float(df["Close"].iloc[-1])
    except Exception:
        return 23.0


@st.cache_data(ttl=900)
def load_data(ticker: str, period: str):
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.dropna(subset=["Close"])
    return df if not df.empty else None


@st.cache_data(ttl=1800)
def load_news(ticker: str):
    return get_all_news(ticker)


@st.cache_data(ttl=3600)
def scan_stocks(stock_dict: dict, period: str) -> list[dict]:
    """Načte data a signály pro všechny akcie ve slovníku."""
    results = []
    for name, (ticker, currency, sector) in stock_dict.items():
        df = load_data(ticker, period)
        if df is None or len(df) < 30:
            continue
        try:
            sig = generate_signals(df)
        except Exception:
            continue
        try:
            price = float(df["Close"].squeeze().iloc[-1])
            prev  = float(df["Close"].squeeze().iloc[-2])
        except Exception:
            continue
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
            "ema200":     sig["ema200"],
            "ema_trend":  (
                "Bullish" if sig["ema20"] > sig["ema50"] > sig["ema200"]
                else "Bearish" if sig["ema20"] < sig["ema50"] < sig["ema200"]
                else "Smíšený"
            ),
        })
    return results


@st.cache_data(ttl=900)
def cached_multi_horizon(ticker: str) -> dict:
    """Generuje technické signály pro 3 investiční horizonty."""
    from indicators import generate_signals
    result = {}
    for key, p in [("short", "3mo"), ("medium", "1y"), ("long", "2y")]:
        df = load_data(ticker, p)
        if df is not None and len(df) >= 30:
            try:
                result[key] = generate_signals(df)
            except Exception:
                result[key] = None
        else:
            result[key] = None
    return result


@st.cache_data(ttl=1800, show_spinner=False)
def cached_claude_analysis(ticker: str, short_json: str, medium_json: str, long_json: str, news_json: str, sentiment_json: str) -> dict:
    import json
    return analyze_stock_with_claude(
        ticker,
        short_signals=json.loads(short_json),
        medium_signals=json.loads(medium_json),
        long_signals=json.loads(long_json),
        news=json.loads(news_json),
        ai_sentiment=json.loads(sentiment_json),
    )


@st.cache_data(ttl=3600)
def cached_peer_comparison(ticker: str, period: str) -> dict:
    return get_peer_comparison(ticker, period)


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
        width = int(clamped / 10 * 56)
        bar = f'<div style="display:inline-block;background:{color};width:{width}px;height:8px;border-radius:4px;vertical-align:middle"></div>'
        num = f'<span style="color:{color};font-weight:700;font-size:1rem">+{clamped}</span>'
    elif clamped < 0:
        color = "#ef4444"
        width = int(abs(clamped) / 10 * 56)
        bar = f'<div style="display:inline-block;background:{color};width:{width}px;height:8px;border-radius:4px;vertical-align:middle"></div>'
        num = f'<span style="color:{color};font-weight:700;font-size:1rem">{clamped}</span>'
    else:
        color = "#888"
        bar = f'<div style="display:inline-block;background:{color};width:4px;height:8px;border-radius:4px;vertical-align:middle"></div>'
        num = f'<span style="color:{color};font-weight:700;font-size:1rem">0</span>'
    return f'{num} /10 &nbsp;{bar}'


def _opportunity_score(r: dict) -> float:
    """
    Složené skóre příležitosti 0–100 pro BUY signály.
    Kombinuje: sílu signálu, výkonnost sektoru, RSI pozici, EMA trend.
    """
    # Síla signálu (0–40 bodů)
    sig = min(40, r.get("strength", 0) * 8)
    # Výkonnost sektoru (0–25 bodů)
    sc  = r.get("sector_chg") or 0
    sec = max(0, min(25, sc * 2.5))
    # RSI pozice – nejlepší entry 30–50 (0–20 bodů)
    rsi = r.get("rsi", 50)
    if 30 <= rsi <= 50:
        rsi_score = 20
    elif rsi < 30:
        rsi_score = 15   # přeprodaný = ok, ale možná další pokles
    elif rsi <= 65:
        rsi_score = max(0, 20 - (rsi - 50))
    else:
        rsi_score = 0    # překoupený = horší entry
    # EMA trend (0–15 bodů)
    ema_score = {"Bullish": 15, "Smíšený": 7, "Bearish": 0}.get(r.get("ema_trend", "Smíšený"), 0)
    return sig + sec + rsi_score + ema_score


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
    reasons_html = " · ".join(
        f'<span style="color:#{"86efac" if action == "BUY" else "fca5a5"}">{s}</span>'
        for s in reasons
    )
    score, score_label = _score_label(r["buy_n"], r["sell_n"], action)
    score_html = _score_bar_html(score)
    sp = r.get("sector_chg")
    sp_str = (f'<span style="color:{"#22c55e" if (sp or 0) >= 0 else "#ef4444"}">'
              f'Sektor: {sp:+.1f}%</span>' if sp is not None else "")

    # 3 horizonty z existujících dat (bez extra downloadu)
    # Krátkodobý: existing action
    _s_c = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#94a3b8"}[action]
    _s_lbl = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "ČEKAT"}[action]
    # Střednědobý: EMA alignment
    _med_trend = r["ema_trend"]
    _med_c = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Smíšený": "#f59e0b"}[_med_trend]
    _med_lbl = {"Bullish": "↑ Bullish", "Bearish": "↓ Bearish", "Smíšený": "→ Smíšený"}[_med_trend]
    # Dlouhodobý: cena vs EMA200
    _ema200 = r.get("ema200", 0)
    _price  = r.get("price", 0)
    _long_bull = _price > _ema200 > 0
    _long_c   = "#22c55e" if _long_bull else "#ef4444"
    _long_lbl = "↑ Nad EMA200" if _long_bull else "↓ Pod EMA200"

    def _hz_badge(lbl, clr, title, subtitle):
        return (f'<div style="background:{clr}18;border:1px solid {clr};border-radius:6px;'
                f'padding:4px 6px;text-align:center">'
                f'<div style="color:#64748b;font-size:0.6rem;line-height:1.3">{title}'
                f'<div style="color:#475569;font-size:0.55rem">{subtitle}</div></div>'
                f'<div style="color:{clr};font-size:0.72rem;font-weight:700">{lbl}</div>'
                f'</div>')

    hz_row = (
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-bottom:6px">'
        f'{_hz_badge(_s_lbl,    _s_c,   "Krátkodobý", "< 3 měs.")}'
        f'{_hz_badge(_med_lbl,  _med_c, "Střednědobý", "6m – 2r")}'
        f'{_hz_badge(_long_lbl, _long_c,"Dlouhodobý",  "3+ roky")}'
        f'</div>'
    )

    st.markdown(
        f'<a href="?page=1&ticker={r["ticker"]}" target="_self" style="text-decoration:none;color:inherit;display:block">'
        f'<div class="{css}" style="cursor:pointer">'
        f'{hz_row}'
        f'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px">'
        f'{score_html} <span style="color:#aaa;font-size:0.8rem">{score_label}</span>'
        f'</div>'
        f'<div style="margin-top:2px">'
        f'<strong style="font-size:1.05rem;margin-right:6px">{r["name"]}</strong>'
        f'<span style="color:#888;font-size:0.82rem">{r["ticker"]} · {r["sector"]}</span>'
        f'</div>'
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:2px 10px;margin-top:2px;font-size:0.85rem">'
        f'<span>{r["price"]:.2f} <span style="color:#94a3b8">{r["currency"]}</span></span>'
        f'<span style="color:{color};font-weight:600">{arrow}{r["chg_pct"]:+.1f}%</span>'
        f'<span style="color:#aaa">RSI <b>{r["rsi"]:.0f}</b></span>'
        + (f'<span>{sp_str}</span>' if sp_str else "")
        + f'</div>'
        + (f'<div style="margin-top:3px;font-size:0.8rem;line-height:1.5">{reasons_html}</div>' if reasons_html else "")
        + f'</div></a>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 1 – Přehled portfolia
# ═════════════════════════════════════════════════════════════════════════════
if page == "Přehled portfolia":
    # CSS platí jen na této stránce – jiné stránky tento blok nevygenerují
    st.markdown("""
<style>
/* Filtr řada – zrušit mezery mezi sloupci, aby se vešly na mobil */
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) {
    gap: 4px !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"] {
    padding: 0 !important;
    min-width: 0 !important;
    flex: 1 1 0 !important;
}
/* Základ všech filtrových tlačítek */
[data-testid="stButton"] button {
    background: #1e293b !important;
    border: 1.5px solid #334155 !important;
    border-radius: 8px !important;
    padding: 6px 2px !important;
    text-align: center !important;
    height: auto !important;
    min-height: 58px !important;
    display: block !important;
    white-space: pre-line !important;
    box-shadow: none !important;
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
    overflow: hidden !important;
    line-height: 1 !important;
}
[data-testid="stButton"] button p {
    white-space: pre-line !important;
    font-size: 0.62rem !important;
    color: #94a3b8 !important;
    margin: 0 !important;
    line-height: 1.6 !important;
    text-align: center !important;
    overflow: hidden !important;
    word-break: break-word !important;
}
[data-testid="stButton"] button p::first-line {
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    color: #f1f5f9 !important;
}
/* Aktivní – modrý */
[data-testid="stButton"] button[kind="primary"] {
    border: 2px solid #3b82f6 !important;
    background: #1a2a3f !important;
}
/* KOUPIT – 2. sloupec → zelená */
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(2) [data-testid="stButton"] button {
    background: #051a0d !important; border-color: #166534 !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(2) [data-testid="stButton"] button p { color: #22c55e !important; }
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(2) [data-testid="stButton"] button[kind="primary"] { background: #0a2e18 !important; border-color: #22c55e !important; }
/* PRODAT – 3. sloupec → červená */
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(3) [data-testid="stButton"] button {
    background: #1a0505 !important; border-color: #7f1d1d !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(3) [data-testid="stButton"] button p { color: #ef4444 !important; }
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(3) [data-testid="stButton"] button[kind="primary"] { background: #2e0a0a !important; border-color: #ef4444 !important; }
/* DRŽET – 4. sloupec → šedá */
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(4) [data-testid="stButton"] button {
    background: #1c1c1c !important; border-color: #4b5563 !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(4) [data-testid="stButton"] button p { color: #9ca3af !important; }
[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > [data-testid="stColumn"]:nth-child(4) [data-testid="stButton"] button[kind="primary"] { background: #374151 !important; border-color: #9ca3af !important; }
</style>
""", unsafe_allow_html=True)

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
        results = scan_stocks(PORTFOLIO, "3mo")

    if not results:
        st.error("Nepodařilo se načíst data. Zkontroluj připojení.")
        st.stop()

    # ── Souhrnná lišta + filtr ────────────────────────────────────────────────
    buy_count  = sum(1 for r in results if r["action"] == "BUY")
    sell_count = sum(1 for r in results if r["action"] == "SELL")
    hold_count = sum(1 for r in results if r["action"] == "HOLD")

    if "pf_filter" not in st.session_state:
        st.session_state["pf_filter"] = "ALL"
    _pf_filter = st.session_state["pf_filter"]

    # Filtr – 4 sloupce v jednom řádku (VŠE | KOUPIT | PRODAT | DRŽET)
    _fc = st.columns(4)
    with _fc[0]:
        if st.button(f"{len(results)}\nVŠE", key="pff_all", use_container_width=True,
                     type="primary" if _pf_filter == "ALL" else "secondary"):
            st.session_state["pf_filter"] = "ALL"; st.rerun()
    with _fc[1]:
        if st.button(f"{buy_count}\nKOUPIT", key="pff_buy", use_container_width=True,
                     type="primary" if _pf_filter == "BUY" else "secondary"):
            st.session_state["pf_filter"] = "BUY"; st.rerun()
    with _fc[2]:
        if st.button(f"{sell_count}\nPRODAT", key="pff_sell", use_container_width=True,
                     type="primary" if _pf_filter == "SELL" else "secondary"):
            st.session_state["pf_filter"] = "SELL"; st.rerun()
    with _fc[3]:
        if st.button(f"{hold_count}\nDRŽET", key="pff_hold", use_container_width=True,
                     type="primary" if _pf_filter == "HOLD" else "secondary"):
            st.session_state["pf_filter"] = "HOLD"; st.rerun()

    # ── Summary bar ──────────────────────────────────────────────────────────
    _up_today  = sum(1 for r in results if r["chg_pct"] >= 0)
    _dn_today  = len(results) - _up_today
    _best_r    = max(results, key=lambda x: x["chg_pct"])
    _worst_r   = min(results, key=lambda x: x["chg_pct"])
    _best_c    = "#22c55e"
    _worst_c   = "#ef4444"
    st.markdown(
        '<div style="background:#1e293b;border-radius:10px;padding:10px 14px;margin:8px 0 12px;'
        'display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:0.82rem">'
        f'<span style="color:#22c55e;font-weight:600">▲ {_up_today}</span>'
        f'<span style="color:#64748b"> · </span>'
        f'<span style="color:#ef4444;font-weight:600">▼ {_dn_today}</span>'
        f'<span style="color:#334155;margin:0 4px">|</span>'
        f'<span style="white-space:nowrap"><span style="color:#64748b">Nejlepší: </span><span style="color:{_best_c};font-weight:600">{_best_r["ticker"]} {_best_r["chg_pct"]:+.1f}%</span></span>'
        f'<span style="color:#334155;margin:0 4px">|</span>'
        f'<span style="white-space:nowrap"><span style="color:#64748b">Nejhorší: </span><span style="color:{_worst_c};font-weight:600">{_worst_r["ticker"]} {_worst_r["chg_pct"]:+.1f}%</span></span>'
        '</div>',
        unsafe_allow_html=True
    )

    # ── P&L z Deníku pro otevřené pozice ─────────────────────────────────────
    try:
        _denik_raw  = get_trades()
        _denik_perf = get_performance(_denik_raw) if not _denik_raw.empty else pd.DataFrame()
        _open_pf    = _denik_perf[_denik_perf["Status"] == "Otevřená"] if not _denik_perf.empty else pd.DataFrame()
        _pnl_map    = {
            row["Ticker"]: {"pct": row["P&L %"], "abs": row["P&L Kč/USD"]}
            for _, row in _open_pf.iterrows()
            if pd.notna(row.get("P&L %"))
        }
    except Exception:
        _pnl_map = {}

    # ── Karty akcií ───────────────────────────────────────────────────────────
    _pf_ua = st.context.headers.get("User-Agent", "")
    _pf_mobile = any(k in _pf_ua for k in ("Mobile", "Android", "iPhone", "iPad"))

    def action_order(r):
        return {"BUY": 0, "SELL": 1, "HOLD": 2}[r["action"]]

    sorted_results = sorted(results, key=action_order)
    if _pf_filter != "ALL":
        sorted_results = [r for r in sorted_results if r["action"] == _pf_filter]

    _ACT_LBL = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}
    _ACT_CLR = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#94a3b8"}

    def _pf_hz_badge(sig, title, subtitle):
        if sig is None:
            return (f'<div style="background:#1e293b;border:1px solid #334155;border-radius:6px;'
                    f'padding:4px 6px;text-align:center">'
                    f'<div style="color:#475569;font-size:0.6rem">{title}<div style="font-size:0.55rem">{subtitle}</div></div>'
                    f'<div style="color:#475569;font-size:0.72rem">N/A</div></div>')
        act = sig.get("action", "HOLD")
        lbl = _ACT_LBL.get(act, act)
        clr = _ACT_CLR.get(act, "#94a3b8")
        return (f'<div style="background:{clr}18;border:1px solid {clr};border-radius:6px;'
                f'padding:4px 6px;text-align:center">'
                f'<div style="color:#64748b;font-size:0.6rem;line-height:1.3">{title}'
                f'<div style="color:#475569;font-size:0.55rem">{subtitle}</div></div>'
                f'<div style="color:{clr};font-size:0.72rem;font-weight:700">{lbl}</div>'
                f'</div>')

    def _render_pf_card(r):
        action      = r["action"]
        card_css    = {"BUY": "pf-card pf-card-buy", "SELL": "pf-card pf-card-sell", "HOLD": "pf-card pf-card-hold"}[action]
        act_color   = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#94a3b8"}[action]
        act_label   = {"BUY": "KOUPIT",  "SELL": "PRODAT",  "HOLD": "DRŽET"}[action]
        arrow       = "▲" if r["chg_pct"] >= 0 else "▼"
        chg_color   = "#22c55e" if r["chg_pct"] >= 0 else "#ef4444"
        trend_color = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Smíšený": "#888"}[r["ema_trend"]]
        rsi_color   = "#22c55e" if r["rsi"] < 35 else "#ef4444" if r["rsi"] > 65 else "#94a3b8"
        score, score_label = _score_label(r["buy_n"], r["sell_n"], action)
        score_color = "#22c55e" if score > 0 else "#ef4444" if score < 0 else "#888"
        reasons     = (r["buy_reasons"] if action == "BUY" else r["sell_reasons"] if action == "SELL" else [])[:3]

        _pnl_card = _pnl_map.get(r["ticker"])
        _pnl_metric = ""
        if _pnl_card:
            _pc   = "#22c55e" if _pnl_card["pct"] >= 0 else "#ef4444"
            _pabs = _pnl_card["abs"] * get_usdczk() if pd.notna(_pnl_card["abs"]) else 0
            _pnl_metric = (
                f'<div style="background:#0f172a;border-radius:8px;padding:8px;text-align:center">'
                f'<div style="color:#64748b;font-size:0.65rem;margin-bottom:2px">P&L</div>'
                f'<div style="color:{_pc};font-size:0.88rem;font-weight:700">{_pnl_card["pct"]:+.1f}%</div>'
                f'<div style="color:{_pc};font-size:0.68rem">{_pabs:+.0f} Kč</div>'
                f'</div>'
            )
        _reasons_block = ""
        if reasons:
            _reasons_block = (
                f'<div style="border-top:1px solid #1e293b;padding-top:8px;margin-top:8px">'
                + "".join(
                    f'<div style="color:{"#86efac" if action=="BUY" else "#fca5a5"};font-size:0.78rem;padding:1px 0">· {s}</div>'
                    for s in reasons
                )
                + '</div>'
            )
        _mh = cached_multi_horizon(r["ticker"])
        hz_row = (
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:10px">'
            f'{_pf_hz_badge(_mh.get("short"),  "Krátkodobý", "< 3 měs.")}'
            f'{_pf_hz_badge(_mh.get("medium"), "Střednědobý", "6m – 2r")}'
            f'{_pf_hz_badge(_mh.get("long"),   "Dlouhodobý",  "3+ roky")}'
            f'</div>'
        )
        st.markdown(
            f'<a href="?page=1&ticker={r["ticker"]}" target="_self" style="text-decoration:none;color:inherit;display:block">'
            f'<div class="{card_css}" style="cursor:pointer;display:block">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
            f'<div style="background:{act_color}22;border:1.5px solid {act_color};border-radius:6px;'
            f'padding:3px 10px;font-size:0.8rem;font-weight:700;color:{act_color};white-space:nowrap">{act_label}</div>'
            f'<div style="flex:1;min-width:0;overflow:hidden">'
            f'<div style="font-size:0.95rem;font-weight:700;color:#f1f5f9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
            f'{r["name"]} <span style="color:#555;font-size:0.75rem;font-weight:400">{r["ticker"]}</span></div>'
            f'<div style="color:{score_color};font-size:0.72rem">{score}/10 · {score_label}</div>'
            f'</div>'
            f'<div style="text-align:right;white-space:nowrap;flex-shrink:0">'
            f'<div style="font-size:1.0rem;font-weight:700">{r["price"]:.2f} <span style="font-size:0.72rem;color:#555">{r["currency"]}</span></div>'
            f'<div style="color:{chg_color};font-size:0.8rem">{arrow} {r["chg_pct"]:+.1f}%</div>'
            f'</div></div>'
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr{" 1fr" if _pnl_metric else ""};gap:6px;margin-bottom:2px">'
            f'<div style="background:#0f172a;border-radius:8px;padding:8px;text-align:center">'
            f'<div style="color:#64748b;font-size:0.65rem;margin-bottom:2px">RSI</div>'
            f'<div style="color:{rsi_color};font-size:0.88rem;font-weight:700">{r["rsi"]:.0f}</div>'
            f'</div>'
            f'<div style="background:#0f172a;border-radius:8px;padding:8px;text-align:center">'
            f'<div style="color:#64748b;font-size:0.65rem;margin-bottom:2px">Trend</div>'
            f'<div style="color:{trend_color};font-size:0.88rem;font-weight:700">{r["ema_trend"]}</div>'
            f'</div>'
            f'<div style="background:#0f172a;border-radius:8px;padding:8px;text-align:center">'
            f'<div style="color:#64748b;font-size:0.65rem;margin-bottom:2px">Sektor</div>'
            f'<div style="color:#94a3b8;font-size:0.72rem;font-weight:600">{r["sector"].split()[0]}</div>'
            f'</div>'
            f'{_pnl_metric}'
            f'</div>'
            f'{_reasons_block}{hz_row}'
            f'</div></a>',
            unsafe_allow_html=True
        )

    if _pf_mobile:
        for r in sorted_results:
            _render_pf_card(r)
    else:
        for i in range(0, len(sorted_results), 2):
            _cols = st.columns(2)
            with _cols[0]:
                _render_pf_card(sorted_results[i])
            with _cols[1]:
                if i + 1 < len(sorted_results):
                    _render_pf_card(sorted_results[i + 1])

    with st.expander("Grafy portfolia (RSI + denní změna)", expanded=False):
        rsi_names  = [r["name"].split()[0] for r in results]
        rsi_values = [r["rsi"] for r in results]
        rsi_colors = ["#22c55e" if v < 35 else "#ef4444" if v > 65 else "#60a5fa" for v in rsi_values]
        fig_rsi = go.Figure(go.Bar(x=rsi_names, y=rsi_values, marker_color=rsi_colors,
                                   text=[f"{v:.0f}" for v in rsi_values], textposition="outside"))
        fig_rsi.add_hline(y=70, line=dict(color="#ef4444", dash="dash"), annotation_text="Overbought 70")
        fig_rsi.add_hline(y=30, line=dict(color="#22c55e", dash="dash"), annotation_text="Oversold 30")
        fig_rsi.update_layout(template="plotly_dark", height=250, margin=dict(l=0,r=0,t=10,b=0),
                               yaxis=dict(range=[0,100]), showlegend=False)
        st.caption("RSI portfolia")
        st.plotly_chart(fig_rsi, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

        chg_names  = [r["name"].split()[0] for r in results]
        chg_values = [r["chg_pct"] for r in results]
        chg_colors = ["#22c55e" if v >= 0 else "#ef4444" for v in chg_values]
        fig_chg = go.Figure(go.Bar(x=chg_names, y=chg_values, marker_color=chg_colors,
                                   text=[f"{v:+.1f}%" for v in chg_values], textposition="outside"))
        fig_chg.add_hline(y=0, line=dict(color="#666", width=1))
        fig_chg.update_layout(template="plotly_dark", height=230, margin=dict(l=0,r=0,t=10,b=0), showlegend=False)
        st.caption("Denní změna (%)")
        st.plotly_chart(fig_chg, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

    # ── Tržní kontext – kompaktní karta + expander ───────────────────────────
    with st.spinner("Načítám tržní kontext..."):
        _fg = fetch_fear_greed()
        _macro_mini = fetch_macro_tickers()

    _fg_score      = _fg.get("score")      if _fg.get("ok") else None
    _fg_prev_week  = _fg.get("prev_week")  if _fg.get("ok") else None
    _fg_prev_month = _fg.get("prev_month") if _fg.get("ok") else None
    _fg_label_str, _fg_color = fg_label(_fg_score) if _fg_score is not None else ("N/A", "#888")
    _fg_pct_bar = int(_fg_score) if _fg_score is not None else 50

    # Kompaktní F&G karta
    def _fg_mini_item(label, val):
        if val is None:
            return ""
        delta = _fg_score - val
        clr = "#22c55e" if delta >= 0 else "#ef4444"
        arr = "▲" if delta >= 0 else "▼"
        return (f'<div style="text-align:center">'
                f'<div style="color:#64748b;font-size:0.68rem">{label}</div>'
                f'<div style="font-size:1rem;font-weight:700">{val:.0f}</div>'
                f'<div style="color:{clr};font-size:0.72rem">{arr} {delta:+.1f}</div>'
                f'</div>')

    _fg_interp = {"Extrémní strach": "Historicky dobrý čas na nákup.",
                  "Strach": "Pesimismus převládá — opatrný optimismus.",
                  "Neutrální": "Trh neví kam — čekej na signál.",
                  "Chamtivost": "Optimismus — pozor na předražení.",
                  "Extrémní chamtivost": "Euforie — zvaž profit-taking."}.get(_fg_label_str, "")

    st.markdown(
        '<div style="background:#1e293b;border-radius:12px;padding:14px 16px;margin:8px 0">'
        '<div style="color:#64748b;font-size:0.7rem;font-weight:600;margin-bottom:10px;letter-spacing:.05em">TRŽNÍ KONTEXT</div>'
        '<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">'
        '<div style="flex:1;min-width:140px">'
        '<div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">Index strachu &amp; chamtivosti</div>'
        f'<div style="font-size:1.15rem;font-weight:700;color:{_fg_color}">{_fg_label_str}</div>'
        f'<div style="position:relative;height:6px;background:#334155;border-radius:3px;margin:6px 0;max-width:160px">'
        f'<div style="position:absolute;left:{_fg_pct_bar}%;top:50%;transform:translate(-50%,-50%);'
        f'width:10px;height:10px;border-radius:50%;background:{_fg_color}"></div></div>'
        f'<div style="color:#64748b;font-size:0.72rem">{_fg_pct_bar} / 100'
        + (f' · {_fg_interp}' if _fg_interp else '') + '</div>'
        '</div>'
        f'<div style="display:flex;gap:20px">'
        f'{_fg_mini_item("Před týdnem", _fg_prev_week)}'
        f'{_fg_mini_item("Před měsícem", _fg_prev_month)}'
        f'</div>'
        '</div></div>',
        unsafe_allow_html=True
    )

    _MACRO_DESC = {
        "VIX":          "index volatility – čím vyšší, tím větší nervozita trhu",
        "10Y Treasury": "výnos 10letých US dluhopisů – nad 5% tlačí akcie dolů",
        "Gold":         "zlato – roste, když jsou investoři v panice",
        "Oil (WTI)":    "cena ropy – ovlivňuje inflaci i energetické firmy",
        "USD Index":    "síla dolaru – silný dolar zhoršuje zisky US firem ze zahraničí",
        "S&P 500":      "hlavní US akciový index – celkový tep amerického trhu",
    }
    _MACRO_ZONES = {
        "VIX":          [(12,"Klid","#22c55e"),(20,"Normální","#94a3b8"),(30,"Nervozita","#f59e0b"),(999,"Panika","#ef4444")],
        "10Y Treasury": [(2,"Velmi nízké","#94a3b8"),(4,"Normální","#22c55e"),(5,"Zvýšené","#f59e0b"),(999,"Tlak na akcie","#ef4444")],
        "Oil (WTI)":    [(60,"Nízká","#22c55e"),(80,"Normální","#94a3b8"),(100,"Vyšší","#f59e0b"),(999,"Inflační tlak","#ef4444")],
        "USD Index":    [(95,"Slabý $","#f59e0b"),(103,"Normální","#94a3b8"),(108,"Silný $","#f59e0b"),(999,"Velmi silný $","#ef4444")],
        "Gold":         [(1800,"Nízké","#94a3b8"),(2200,"Normální","#94a3b8"),(2800,"Zvýšené","#f59e0b"),(999999,"Krizová poptávka","#ef4444")],
    }
    def _macro_zone(name, val):
        for threshold, label, color in _MACRO_ZONES.get(name, []):
            if val <= threshold:
                return label, color
        return "", "#94a3b8"

    def _macro_bar(name, val):
        ranges = {"VIX":(8,50),"10Y Treasury":(0.5,6),"Oil (WTI)":(30,130),"USD Index":(85,115),"Gold":(1200,3200)}
        if name not in ranges:
            return ""
        lo, hi = ranges[name]
        if val is None or (isinstance(val, float) and (val != val)):
            return ""
        pct = max(0, min(100, int((val - lo) / (hi - lo) * 100))) if hi != lo else 0
        _, zcolor = _macro_zone(name, val)
        return (f'<div style="background:#1e293b;border-radius:3px;height:5px;width:100%;margin-top:4px;position:relative">'
                f'<div style="position:absolute;left:33%;top:0;bottom:0;width:1px;background:#334155"></div>'
                f'<div style="position:absolute;left:66%;top:0;bottom:0;width:1px;background:#334155"></div>'
                f'<div style="background:{zcolor};border-radius:3px;height:5px;width:{pct}%"></div>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;font-size:0.6rem;color:#334155;margin-top:1px">'
                f'<span>{lo}</span><span>normální rozsah</span><span>{hi}</span></div>')

    with st.expander("Klíčové makro ukazatele", expanded=False):
        if _macro_mini:
            for _name, _data in _macro_mini.items():
                _p   = _data["price"]
                _c   = _data["chg"]
                _arr = "▲" if _c >= 0 else "▼"
                _col = "#22c55e" if _c >= 0 else "#ef4444"
                _desc = _MACRO_DESC.get(_name, "")
                _zone_lbl, _zone_col = _macro_zone(_name, _p)
                _bar_html = _macro_bar(_name, _p)
                _zone_badge = (f'<span style="background:{_zone_col}22;color:{_zone_col};border:1px solid {_zone_col}55;'
                               f'border-radius:4px;padding:1px 6px;font-size:0.7rem;font-weight:600;white-space:nowrap">'
                               f'{_zone_lbl}</span>') if _zone_lbl else ""
                st.markdown(
                    f'<div class="card-hold" style="margin:3px 0;padding:8px 12px">'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;gap:6px">'
                    f'<span style="font-size:0.9rem;font-weight:700;white-space:nowrap">{_name}</span>'
                    f'{_zone_badge}'
                    f'</div>'
                    f'<div style="color:#555;font-size:0.72rem;margin:2px 0 3px">{_desc}</div>'
                    f'<div style="display:flex;align-items:center;gap:10px">'
                    f'<span style="font-size:1.05rem;font-weight:600">{_p:.2f}</span>'
                    f'<span style="color:{_col};font-weight:600;font-size:0.85rem">{_arr} {_c:+.1f}%</span>'
                    f'</div>'
                    f'{_bar_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("Makro data se nepodařilo načíst.")


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 2 – Detail akcie
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Detail akcie":
    ticker   = detail_ticker
    currency = detail_currency

    # ── Výběr akcie přímo na stránce ─────────────────────────────────────────
    _all_stocks_det = dict(PORTFOLIO)
    _all_stocks_det.update(RADAR_STOCKS)
    _all_stocks_det["Vlastní ticker..."] = ("CUSTOM", "", "")
    _stock_names_det = list(_all_stocks_det.keys())
    _cur_idx = 0
    for _i, _n in enumerate(_stock_names_det):
        if _all_stocks_det[_n][0] == ticker:
            _cur_idx = _i
            break
    _chosen = st.selectbox("Vyber akcii", _stock_names_det, index=_cur_idx, key="detail_stock_inline")
    if _chosen == "Vlastní ticker...":
        _custom_inline = st.text_input("Ticker (např. AAPL)", key="detail_custom_inline").upper().strip()
        ticker   = _custom_inline or ticker
        currency = "USD"
    else:
        ticker, currency, _ = _all_stocks_det[_chosen]

    _det_tabs = st.tabs(["📊 Analýza", "📈 Backtest"])
    with _det_tabs[0]:

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

        _chg_c = "#22c55e" if chg >= 0 else "#ef4444"
        _chg_arr = "▲" if chg >= 0 else "▼"
        _vol_c = "#f59e0b" if vol_ratio > 2 else "#94a3b8"
        st.markdown(f"""
    <style>
    .price-grid {{ display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px }}
    @media (max-width:640px) {{ .price-grid {{ grid-template-columns:repeat(2,1fr) }} }}
    </style>
    <div class="price-grid">
      <div style="background:#1e293b;border-radius:10px;padding:10px 12px">
        <div style="color:#64748b;font-size:0.72rem">Cena</div>
        <div style="font-size:1.15rem;font-weight:700">{price_now:.2f} <span style="font-size:0.8rem;color:#94a3b8">{currency}</span></div>
        <div style="color:{_chg_c};font-size:0.8rem">{_chg_arr} {chg:+.2f} ({chg_pct:+.1f}%)</div>
      </div>
      <div style="background:#1e293b;border-radius:10px;padding:10px 12px">
        <div style="color:#64748b;font-size:0.72rem">52W Max</div>
        <div style="font-size:1.15rem;font-weight:700">{high_52w:.2f}</div>
        <div style="color:#64748b;font-size:0.8rem">{((price_now/high_52w-1)*100):+.1f}% od maxima</div>
      </div>
      <div style="background:#1e293b;border-radius:10px;padding:10px 12px">
        <div style="color:#64748b;font-size:0.72rem">52W Min</div>
        <div style="font-size:1.15rem;font-weight:700">{low_52w:.2f}</div>
        <div style="color:#64748b;font-size:0.8rem">{((price_now/low_52w-1)*100):+.1f}% od minima</div>
      </div>
      <div style="background:#1e293b;border-radius:10px;padding:10px 12px">
        <div style="color:#64748b;font-size:0.72rem">Objem</div>
        <div style="font-size:1.15rem;font-weight:700;color:{_vol_c}">{vol_ratio:.1f}×</div>
        <div style="color:#64748b;font-size:0.8rem">průměr 20 dní</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # Načti zprávy, AI sentiment a signály
        with st.spinner("Načítám analýzu..."):
            news_raw = load_news(ticker)
            news     = enrich_news_with_ai(news_raw) if news_raw else []
            ai_sent  = news_ai_summary(news) if news else {"score": 0, "source": "N/A",
                                                            "positive": 0, "negative": 0, "neutral": 0}

        signals = generate_signals_with_news(df, ai_sent)
        action  = signals["action"]

        # Načti signály pro 3 horizonty + AI analýzu
        import json as _json
        with st.spinner("Načítám multi-horizont analýzu..."):
            _mh = cached_multi_horizon(ticker)

        def _sig_to_json(s: dict | None) -> str:
            if not s:
                return _json.dumps({})
            return _json.dumps(
                {k: (float(v) if isinstance(v, (int, float)) else v)
                 for k, v in s.items() if not isinstance(v, (list, dict))} |
                {"buy_signals": s.get("buy_signals", []),
                 "sell_signals": s.get("sell_signals", [])}
            )

        with st.spinner("Volám AI analýzu..."):
            _claude = cached_claude_analysis(
                ticker,
                _sig_to_json(_mh.get("short")),
                _sig_to_json(_mh.get("medium")),
                _sig_to_json(_mh.get("long")),
                _json.dumps([{"title": n.get("title",""), "summary": n.get("summary","")} for n in news[:10]]),
                _json.dumps({k: (float(v) if isinstance(v, float) else v) for k, v in ai_sent.items()}),
            )

        # ── Konstanty pro AI hint ────────────────────────────────────
        _HINT_LABEL = {"koupit": "KOUPIT", "prodat": "PRODAT", "čekat": "ČEKAT", "sledovat": "SLEDOVAT"}
        _HINT_COLOR = {"koupit": "#22c55e", "prodat": "#ef4444", "čekat": "#f59e0b", "sledovat": "#60a5fa"}
        _ai_prov = _claude.get("provider", "AI") if _claude.get("ok") else ""

        # ── Hero card: hlavní signál (krátkodobý + AI) ───────────────
        _hero_sig   = _mh.get("short") or signals
        _hero_act   = _hero_sig.get("action", "HOLD")
        _hero_sc    = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#94a3b8"}[_hero_act]
        _hero_lbl   = {"BUY": "KOUPIT",  "SELL": "PRODAT",  "HOLD": "DRŽET"}[_hero_act]
        _hero_cd    = _claude.get("short", {}) if _claude.get("ok") else {}
        _hero_summ  = _hero_cd.get("summary", "")
        _hero_hint  = _hero_cd.get("action_hint", "")
        _hero_conf  = _hero_cd.get("confidence", "")
        _hero_hc    = _HINT_COLOR.get(_hero_hint, "#94a3b8")
        _hero_score, _hero_slbl = _score_label(
            len(_hero_sig.get("buy_signals", [])), len(_hero_sig.get("sell_signals", [])), _hero_act
        )
        _hero_bar   = _score_bar_html(_hero_score)
        _sent_c     = "#22c55e" if ai_sent["score"] > 0.15 else ("#ef4444" if ai_sent["score"] < -0.15 else "#94a3b8")
        _sent_lbl   = {"positive": "Pozitivní", "negative": "Negativní", "neutral": "Neutrální"}.get(ai_sent.get("dominant", "neutral"), "Neutrální")
        _hero_b = len(_hero_sig.get("buy_signals", []))
        _hero_s = len(_hero_sig.get("sell_signals", []))
        _sent_pct = int((ai_sent["score"] + 1) / 2 * 100)
        _hero_sent_html = (
            f'<div style="display:flex;align-items:center;gap:6px;margin-top:1px">'
            f'<span style="color:#64748b;font-size:0.72rem">Sentiment:</span>'
            f'<span style="color:{_sent_c};font-size:0.75rem;font-weight:600">{_sent_lbl}</span>'
            f'<span style="color:#64748b;font-size:0.65rem">&#8722;1</span>'
            f'<div style="position:relative;width:52px;height:4px;background:#334155;border-radius:2px;flex-shrink:0">'
            f'<div style="position:absolute;left:{_sent_pct}%;top:50%;transform:translate(-50%,-50%);'
            f'width:8px;height:8px;border-radius:50%;background:{_sent_c};border:1px solid #1e293b"></div>'
            f'</div>'
            f'<span style="color:#64748b;font-size:0.65rem">+1</span>'
            f'<span style="color:{_sent_c};font-size:0.72rem">{ai_sent["score"]:+.2f}</span>'
            f'</div>'
        )
        _hero_summ_html = (
            f'<div style="color:#cbd5e1;font-size:0.87rem;line-height:1.5;'
            f'margin-top:10px;border-top:1px solid #334155;padding-top:10px">{_hero_summ}</div>'
        ) if _hero_summ else ""

        st.markdown(
            '<div style="background:#1e293b;border-radius:12px;padding:16px;margin-bottom:12px">'
            '<div style="display:flex;align-items:center;gap:14px">'
            f'<div style="background:{_hero_sc}22;border:2px solid {_hero_sc};border-radius:10px;'
            f'padding:10px 18px;font-size:1.4rem;font-weight:800;color:{_hero_sc};white-space:nowrap;flex-shrink:0">{_hero_lbl}</div>'
            '<div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:4px">'
            f'<div style="color:#94a3b8;font-size:0.72rem;white-space:nowrap">{_hero_bar} &nbsp; {_hero_slbl}</div>'
            f'<div style="color:#64748b;font-size:0.78rem">{_hero_b} buy / {_hero_s} sell</div>'
            + (f'<div style="color:#94a3b8;font-size:0.78rem"><span style="color:{_hero_hc};font-weight:700;text-transform:uppercase">{_hero_hint}</span>'
               + (f' · jistota: {_hero_conf}' if _hero_conf else '') + '</div>' if _hero_hint else '')
            + _hero_sent_html
            + '</div></div>'
            f'{_hero_summ_html}'
            '</div>',
            unsafe_allow_html=True
        )

        # ── Porovnávací tabulka 3 horizontů ─────────────────────────
        def _hz_col(hk):
            sig = _mh.get(hk) or signals
            cd  = _claude.get(hk, {}) if _claude.get("ok") else {}
            act = sig.get("action", "HOLD")
            sc  = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#94a3b8"}[act]
            sl  = {"BUY": "KOUPIT",  "SELL": "PRODAT",  "HOLD": "DRŽET"}[act]
            rsi = sig["rsi"]
            rc  = "#22c55e" if rsi < 30 else ("#ef4444" if rsi > 70 else "#94a3b8")
            tr  = ("Bullish" if sig["ema20"] > sig["ema50"] > sig["ema200"]
                   else "Bearish" if sig["ema20"] < sig["ema50"] < sig["ema200"]
                   else "Smíšený")
            tc  = "#22c55e" if tr == "Bullish" else ("#ef4444" if tr == "Bearish" else "#94a3b8")
            ml  = "Bullish" if sig["macd"] > sig["macd_signal"] else "Bearish"
            mc  = "#22c55e" if sig["macd"] > sig["macd_signal"] else "#ef4444"
            _, slbl = _score_label(len(sig.get("buy_signals", [])), len(sig.get("sell_signals", [])), act)
            hint  = cd.get("action_hint", "")
            hc    = _HINT_COLOR.get(hint, "#94a3b8")
            b_cnt = len(sig.get("buy_signals",  []))
            s_cnt = len(sig.get("sell_signals", []))
            hint_div = f'<div style="font-size:0.7rem;color:{hc};text-transform:uppercase;font-weight:600">{hint}</div>' if hint else ""
            return (
f'<div style="background:#0f172a;border-radius:10px;padding:12px 10px;text-align:center">'
f'<div style="background:{sc}22;border:1px solid {sc};border-radius:6px;padding:4px 0;font-size:0.88rem;font-weight:700;color:{sc};margin-bottom:10px">{sl}</div>'
f'<div style="font-size:0.68rem;color:#64748b;margin-bottom:1px">RSI</div>'
f'<div style="font-size:0.95rem;font-weight:700;color:{rc};margin-bottom:8px">{rsi:.1f}</div>'
f'<div style="font-size:0.68rem;color:#64748b;margin-bottom:1px">Trend</div>'
f'<div style="font-size:0.9rem;font-weight:600;color:{tc};margin-bottom:8px">{tr}</div>'
f'<div style="font-size:0.68rem;color:#64748b;margin-bottom:1px">MACD</div>'
f'<div style="font-size:0.9rem;font-weight:600;color:{mc};margin-bottom:8px">{ml}</div>'
f'<div style="font-size:0.68rem;color:#64748b;margin-bottom:1px">Signály</div>'
f'<div style="font-size:0.8rem;color:#94a3b8;margin-bottom:6px"><span style="color:#22c55e">{b_cnt}&#8593;</span> / <span style="color:#ef4444">{s_cnt}&#8595;</span></div>'
f'{hint_div}'
f'</div>'
            )

        _col_s = _hz_col("short")
        _col_m = _hz_col("medium")
        _col_l = _hz_col("long")

        st.markdown(f"""
<div style="background:#1e293b;border-radius:12px;padding:14px 16px;margin-bottom:12px">
  <div style="color:#64748b;font-size:0.7rem;font-weight:600;margin-bottom:10px;letter-spacing:.05em">POROVNÁNÍ HORIZONTŮ</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
    <div>
      <div style="color:#94a3b8;font-size:0.75rem;font-weight:600;margin-bottom:6px;text-align:center">Krátkodobý <span style="color:#64748b;font-weight:400">&lt; 3 měs.</span></div>
      {_col_s}
    </div>
    <div>
      <div style="color:#94a3b8;font-size:0.75rem;font-weight:600;margin-bottom:6px;text-align:center">Střednědobý <span style="color:#64748b;font-weight:400">6m – 2r</span></div>
      {_col_m}
    </div>
    <div>
      <div style="color:#94a3b8;font-size:0.75rem;font-weight:600;margin-bottom:6px;text-align:center">Dlouhodobý <span style="color:#64748b;font-weight:400">3+ roky</span></div>
      {_col_l}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

        # ── Default AI analýza (krátkodobý) ─────────────────────────
        _def_cd   = _claude.get("short", {}) if _claude.get("ok") else {}
        _def_summ = _def_cd.get("summary", "")
        _def_hint = _def_cd.get("action_hint", "")
        _def_conf = _def_cd.get("confidence", "")
        if _def_summ:
            _dh_c = _HINT_COLOR.get(_def_hint, "#94a3b8")
            st.markdown(f"""
<div style="background:#1e293b;border-radius:12px;padding:14px 16px;margin-bottom:12px">
  <div style="color:#64748b;font-size:0.7rem;font-weight:600;margin-bottom:6px;letter-spacing:.05em">AI ANALÝZA · KRÁTKODOBÝ · <span style="color:#60a5fa">{_ai_prov}</span></div>
  <div style="color:#cbd5e1;font-size:0.87rem;line-height:1.5">{_def_summ}</div>
  {f'<div style="color:#94a3b8;font-size:0.78rem;margin-top:8px">Doporučení: <span style="color:{_dh_c};font-weight:600;text-transform:uppercase">{_def_hint}</span> · jistota: {_def_conf}</div>' if _def_hint else ""}
</div>
""", unsafe_allow_html=True)

        # ── Stacked detaily pro každý horizont ──────────────────────
        for _hk, _hname, _hsub, _expanded in [
            ("short",  "Krátkodobý",  "< 3 měs.",  True),
            ("medium", "Střednědobý", "6m – 2 roky", False),
            ("long",   "Dlouhodobý",  "3+ roky",   False),
        ]:
            _hz_sig    = _mh.get(_hk) or signals
            _hz_data   = _claude.get(_hk, {}) if _claude.get("ok") else {}
            _hz_summ   = _hz_data.get("summary", "")
            _hz_hint   = _hz_data.get("action_hint", "")
            _hz_conf   = _hz_data.get("confidence", "")
            _hz_events = _hz_data.get("events", [])
            _hz_risks  = _hz_data.get("risk_factors", [])
            _hz_opp    = _hz_data.get("opportunity", "")

            _hz_action = _hz_sig.get("action", "HOLD")
            _sig_c  = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#94a3b8"}[_hz_action]
            _sig_lbl = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[_hz_action]
            _hint_c = _HINT_COLOR.get(_hz_hint, "#94a3b8")

            score, score_label = _score_label(
                len(_hz_sig.get("buy_signals", [])), len(_hz_sig.get("sell_signals", [])), _hz_action
            )
            score_html = _score_bar_html(score)
            _ai_row = (f'<div style="color:#94a3b8;font-size:0.78rem;margin-top:4px">AI: '
                       f'<span style="color:{_hint_c};font-weight:600;text-transform:uppercase">{_hz_hint}</span>'
                       f' · jistota: {_hz_conf} · <span style="color:#60a5fa">{_ai_prov}</span></div>') if _hz_hint else ""

            _buy_html  = "".join(f'<div style="color:#22c55e;font-size:0.82rem;padding:2px 0">+ {s}</div>' for s in _hz_sig.get("buy_signals",  [])) or '<div style="color:#555;font-size:0.82rem">Žádné</div>'
            _sell_html = "".join(f'<div style="color:#ef4444;font-size:0.82rem;padding:2px 0">− {s}</div>' for s in _hz_sig.get("sell_signals", [])) or '<div style="color:#555;font-size:0.82rem">Žádné</div>'

            _events_html = "".join(f'<div style="color:#f59e0b;font-size:0.82rem;padding:2px 0">▸ {e}</div>' for e in _hz_events) if _hz_events else ""
            _risks_html  = "".join(f'<div style="color:#ef4444;font-size:0.82rem;padding:2px 0">⚠ {r}</div>'   for r in _hz_risks)  if _hz_risks  else ""
            _opp_html    = f'<div style="color:#22c55e;font-size:0.82rem;margin-top:4px">💡 {_hz_opp}</div>'   if _hz_opp else ""

            _er_block = ""
            if _hz_events or _hz_risks or _hz_opp:
                _er_block = f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;border-top:1px solid #334155;padding-top:10px">
  <div><div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">Klíčové události</div>{_events_html or '<div style="color:#555;font-size:0.82rem">–</div>'}</div>
  <div><div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">Rizika</div>{_risks_html or '<div style="color:#555;font-size:0.82rem">–</div>'}</div>
</div>{_opp_html}"""

            with st.expander(f"{_hname} · {_hsub}", expanded=_expanded):
                st.markdown(f"""
<div style="background:#1e293b;border-radius:12px;padding:14px 16px">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
    <div style="background:{_sig_c}22;border:2px solid {_sig_c};border-radius:8px;
                padding:5px 16px;font-size:1.2rem;font-weight:700;color:{_sig_c}">{_sig_lbl}</div>
    <div style="flex:1;min-width:120px">{score_html}
      <div style="color:#94a3b8;font-size:0.78rem;margin-top:2px">{score_label} · {len(_hz_sig.get('buy_signals',[]))} buy / {len(_hz_sig.get('sell_signals',[]))} sell</div>
      {_ai_row}
    </div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;border-top:1px solid #334155;padding-top:10px">
    <div><div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">BUY signály</div>{_buy_html}</div>
    <div><div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">SELL signály</div>{_sell_html}</div>
  </div>
  {f'<div style="color:#cbd5e1;font-size:0.85rem;border-top:1px solid #334155;padding-top:10px;margin-top:10px">{_hz_summ}</div>' if _hz_summ and _hk != "short" else ""}
  {_er_block}
</div>
""", unsafe_allow_html=True)

        # Graf & technické indikátory
        with st.expander("Graf & technická analýza", expanded=False):
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
                legend=dict(orientation="h", yanchor="top", y=-0.05, x=0),
                margin=dict(l=0, r=0, t=40, b=0),
            )
            fig.update_yaxes(range=[0, 100], row=2, col=1)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

            # Technické indikátory pod grafem
            rsi_v  = signals["rsi"]
            bb_pos = (price_now - signals["bb_lower"]) / max(signals["bb_upper"] - signals["bb_lower"], 0.01) * 100
            _ind_trend  = ("Bullish" if signals["ema20"] > signals["ema50"] > signals["ema200"]
                           else "Bearish" if signals["ema20"] < signals["ema50"] < signals["ema200"]
                           else "Smíšený")
            rsi_delta   = "Oversold – levná" if rsi_v < 30 else ("Overbought – drahá" if rsi_v > 70 else "Neutrální")
            bb_delta    = "Blízko dna" if bb_pos < 20 else ("Blízko vrcholu" if bb_pos > 80 else "Střed pásma")
            stoch_delta = "Oversold" if signals["stoch_k"] < 20 else ("Overbought" if signals["stoch_k"] > 80 else "Neutrální")
            rsi_color   = "#22c55e" if rsi_v < 30 else ("#ef4444" if rsi_v > 70 else "#94a3b8")
            bb_color    = "#22c55e" if bb_pos < 20 else ("#ef4444" if bb_pos > 80 else "#94a3b8")
            stoch_color = "#22c55e" if signals["stoch_k"] < 20 else ("#ef4444" if signals["stoch_k"] > 80 else "#94a3b8")
            trend_color = "#22c55e" if _ind_trend == "Bullish" else ("#ef4444" if _ind_trend == "Bearish" else "#94a3b8")
            macd_color  = "#22c55e" if signals["macd"] > signals["macd_signal"] else "#ef4444"

            st.markdown(f"""
<div class="indicator-grid">
<div class="indicator-card" title="RSI měří přeprodanost. Pod 30 = levná, nad 70 = drahá."><div class="indicator-label">RSI (14)</div><div class="indicator-value" style="color:{rsi_color}">{rsi_v:.1f}</div><div class="indicator-delta">{rsi_delta}</div></div>
<div class="indicator-card" title="MACD: křížení signal linky nahoru = BUY, dolů = SELL."><div class="indicator-label">MACD</div><div class="indicator-value" style="color:{macd_color}">{signals['macd']:.3f}</div><div class="indicator-delta">Signal: {signals['macd_signal']:.3f}</div></div>
<div class="indicator-card" title="Pozice ceny v Bollinger Bands. 0% = dno, 100% = vrchol."><div class="indicator-label">Bollinger Bands</div><div class="indicator-value" style="color:{bb_color}">{bb_pos:.0f}%</div><div class="indicator-delta">{bb_delta}</div></div>
<div class="indicator-card" title="Stochastic: pod 20 = přeprodaná, nad 80 = překoupená."><div class="indicator-label">Stochastic K/D</div><div class="indicator-value" style="color:{stoch_color}">{signals['stoch_k']:.0f} / {signals['stoch_d']:.0f}</div><div class="indicator-delta">{stoch_delta}</div></div>
<div class="indicator-card" title="EMA trend: Bullish = EMA20 > EMA50 > EMA200."><div class="indicator-label">Trend (EMA)</div><div class="indicator-value" style="color:{trend_color}">{_ind_trend}</div><div class="indicator-delta">EMA50: {signals['ema50']:.1f}</div></div>
</div>
""", unsafe_allow_html=True)

            with st.expander("Co znamenají tyto indikátory?"):
                st.markdown("""
**Jak systém funguje:** Sleduje 5 indikátorů najednou. Signál KOUPIT nebo PRODAT se zobrazí teprve
když **alespoň 3 indikátory souhlasí** — proto je konzervativní a nevydává falešné alarmy.

| Indikátor | Co měří | Kdy říká KOUPIT | Kdy říká PRODAT |
|---|---|---|---|
| **RSI** | Síla trendu, přeprodanost | Pod 30 (levná) | Nad 70 (drahá) |
| **MACD** | Momentum trendu | Křížení nahoru | Křížení dolů |
| **Bollinger Bands** | Pozice vůči průměru | Cena pod spodním pásmem | Cena nad horním pásmem |
| **Stochastic** | Přeprodanost za 14 dní | K/D pod 20 | K/D nad 80 |
| **EMA trend** | Směr krátkodobého vs. dlouhodobého trendu | 20 > 50 > 200 | 20 < 50 < 200 |

> Žádný indikátor není 100% spolehlivý. Vždy kombinuj s vlastním úsudkem a zprávami.
                """)

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # Zprávy & AI Sentiment (skryté by default)
        with st.expander("Zprávy & AI Sentiment", expanded=False):
            if news:
                source_label = "FinBERT AI" if ai_sent.get("source") == "FinBERT" else "Klíčová slova"
                dom = ai_sent["dominant"]
                dom_label = {"positive": "Pozitivní", "negative": "Negativní", "neutral": "Neutrální"}[dom]
                dom_color = "#22c55e" if dom == "positive" else "#ef4444" if dom == "negative" else "#94a3b8"
                score_str = f"{ai_sent['score']:+.2f}"
                st.markdown(f"""
<style>
.sent-grid {{ display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px }}
@media (max-width:640px) {{ .sent-grid {{ grid-template-columns:repeat(2,1fr) }} }}
</style>
<div class="sent-grid">
  <div style="background:#1e293b;border-radius:10px;padding:10px 12px">
    <div style="color:#64748b;font-size:0.72rem">Pozitivní zprávy</div>
    <div style="font-size:1.15rem;font-weight:700;color:#22c55e">{ai_sent["positive"]}</div>
  </div>
  <div style="background:#1e293b;border-radius:10px;padding:10px 12px">
    <div style="color:#64748b;font-size:0.72rem">Negativní zprávy</div>
    <div style="font-size:1.15rem;font-weight:700;color:#ef4444">{ai_sent["negative"]}</div>
  </div>
  <div style="background:#1e293b;border-radius:10px;padding:10px 12px">
    <div style="color:#64748b;font-size:0.72rem">Neutrální</div>
    <div style="font-size:1.15rem;font-weight:700;color:#94a3b8">{ai_sent["neutral"]}</div>
  </div>
  <div style="background:#1e293b;border-radius:10px;padding:10px 12px">
    <div style="color:#64748b;font-size:0.72rem">AI Sentiment · {source_label}</div>
    <div style="font-size:1.15rem;font-weight:700;color:{dom_color}">{dom_label}</div>
    <div style="font-size:0.78rem;color:#64748b;margin-top:2px">Skóre: {score_str}</div>
  </div>
</div>""", unsafe_allow_html=True)
                score_val = ai_sent["score"]
                bar_pct   = int((score_val + 1) / 2 * 100)
                bar_color = "#22c55e" if score_val > 0.15 else "#ef4444" if score_val < -0.15 else "#888"
                st.markdown(
                    f'<div style="background:#1a1a2e;border-radius:8px;padding:10px;margin:8px 0">'
                    f'<div style="font-size:0.8rem;color:#888;margin-bottom:4px">Sentiment spektrum &nbsp;·&nbsp; {source_label}</div>'
                    f'<div style="background:#333;border-radius:4px;height:10px;width:100%">'
                    f'<div style="background:{bar_color};border-radius:4px;height:10px;width:{bar_pct}%"></div>'
                    f'</div>'
                    f'<div style="display:flex;justify-content:space-between;font-size:0.75rem;color:#666;margin-top:2px">'
                    f'<span>Velmi negativní</span><span>Neutrální</span><span>Velmi pozitivní</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
                st.markdown("---")
                for item in news[:15]:
                    s    = item.get("sentiment", "neutral")
                    conf = item.get("sentiment_score", 0)
                    src  = item.get("sentiment_source", "")
                    css  = {"positive": "news-pos", "negative": "news-neg", "neutral": "news-neu"}[s]
                    ico  = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}[s]
                    sd   = f"{item['source']} · {item['date']}" if item["date"] else item["source"]
                    smr  = f"<br><small style='color:#aaa'>{item['summary']}</small>" if item["summary"] else ""
                    conf_html = (f'<span style="color:#666;font-size:0.75rem"> [{src} {conf:.0%}]</span>') if conf else ""
                    st.markdown(
                        f'<div class="{css}">{ico} <a href="{item["link"]}" target="_blank" style="color:inherit">'
                        f'<strong>{item["title"]}</strong></a>{conf_html}'
                        f'<br><small style="color:#888">{sd}</small>{smr}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Zprávy se nepodařilo načíst.")

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # ── AI analýza – události a rizika pro vybraný horizont ──────────────────
        if _claude.get("ok"):
            if _hz_events or _hz_risks:
                # Interleave: každý řádek = jeden event + jeden risk (zarovnané vedle sebe)
                _max_rows = max(len(_hz_events), len(_hz_risks))
                _rows_html = ""
                for _i in range(_max_rows):
                    _ev = _hz_events[_i] if _i < len(_hz_events) else None
                    _ri = _hz_risks[_i]  if _i < len(_hz_risks)  else None
                    _rows_html += (
                        (f'<div style="background:#0c2a4a;border-left:3px solid #60a5fa;border-radius:4px;'
                         f'padding:8px 12px;font-size:0.85rem;color:#cbd5e1">📌 {_ev}</div>'
                         if _ev else '<div></div>')
                        +
                        (f'<div style="background:#2a1a0a;border-left:3px solid #f59e0b;border-radius:4px;'
                         f'padding:8px 12px;font-size:0.85rem;color:#cbd5e1">⚠️ {_ri}</div>'
                         if _ri else '<div></div>')
                    )
                st.markdown(f"""
<style>
.ev-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 12px; margin-top:8px; }}
</style>
<div class="ev-grid">
  <div style="color:#94a3b8;font-size:0.75rem;font-weight:600;padding-bottom:2px;text-transform:uppercase;letter-spacing:.05em">📌 Klíčové události</div>
  <div style="color:#94a3b8;font-size:0.75rem;font-weight:600;padding-bottom:2px;text-transform:uppercase;letter-spacing:.05em">⚠️ Rizikové faktory</div>
  {_rows_html}
</div>""", unsafe_allow_html=True)
            if _hz_opp:
                hint_color = _HINT_COLOR.get(_hz_hint, "#888")
                st.markdown(
                    f'<div style="background:#0f172a;border:1px solid #334155;border-radius:6px;'
                    f'padding:12px 16px;margin-top:4px">'
                    f'<span style="color:{hint_color};font-weight:bold;text-transform:uppercase">{_hz_hint}</span>'
                    f'<span style="color:#94a3b8;font-size:0.8rem"> · jistota: {_hz_conf}</span><br>'
                    f'<span style="color:#cbd5e1">{_hz_opp}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        elif not _claude.get("ok") and _claude.get("error"):
            st.warning(f"AI analýza nedostupná: {_claude.get('error')}")

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # ── Earnings ─────────────────────────────────────────────────────────────
        _earn = get_earnings(ticker)
        if _earn:
            _ed   = _earn.get("earnings_date")
            _days = _earn.get("days_until")
            _soon = _earn.get("is_soon", False)
            _past = _earn.get("is_past", False)
            if _ed and not _past:
                _earn_color = "#f59e0b" if _soon else "#60a5fa"
                _earn_label = f"za {_days} dní" if _days is not None else ""
                _eps_str = ""
                if _earn.get("eps_estimate"):
                    _eps_str = f" · EPS odhad: {_earn['eps_estimate']:.2f}"
                st.markdown(
                    f'<div style="background:#1a1a2e;border:1px solid {_earn_color};border-radius:8px;'
                    f'padding:10px 16px;margin-bottom:8px;display:flex;gap:12px;align-items:center">'
                    f'<span style="font-size:1.4rem">📅</span>'
                    f'<div><div style="color:{_earn_color};font-weight:700">Earnings: {_ed.strftime("%d.%m.%Y")} {_earn_label}</div>'
                    f'<div style="color:#94a3b8;font-size:0.82rem">Výsledky hospodaření{_eps_str}'
                    + (" · <b>Blíží se!</b>" if _soon else "") +
                    f'</div></div></div>',
                    unsafe_allow_html=True,
                )

        # ── Srovnání s konkurencí ────────────────────────────────────────────────
        st.subheader("Srovnání s konkurencí")
        st.caption(f"Výkonnost {ticker} vs. podobné firmy ve stejném období.")

        with st.spinner("Načítám data konkurentů..."):
            _peers = cached_peer_comparison(ticker, period)

        if _peers.get("ok"):
            ranked = _peers["ranked"]
            results = _peers["results"]
            main_rank = _peers["main_rank"]
            total = _peers["total"]

            st.caption(f"Pořadí {ticker}: **{main_rank}. z {total}** za vybrané období")

            # Normalizovaný výkonnostní graf
            pfig = go.Figure()
            for t, data in results.items():
                is_main = data["is_main"]
                pfig.add_trace(go.Scatter(
                    x=data["dates"],
                    y=data["normalized"],
                    name=t,
                    line=dict(width=3 if is_main else 1.5,
                              color="#60a5fa" if is_main else None),
                ))
            pfig.update_layout(
                height=340, template="plotly_dark",
                title="Normalizovaná výkonnost (báze = 100)",
                margin=dict(l=0, r=0, t=40, b=60),
                legend=dict(orientation="h", yanchor="top", y=-0.15, x=0),
            )
            st.plotly_chart(pfig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

            # Tabulka se změnami – responsivní CSS grid
            peer_rows = sorted(results.items(), key=lambda x: -x[1]["chg_pct"])
            cards_html = '<div class="peer-grid">'
            for t, d in peer_rows:
                chg = d["chg_pct"]
                chg_cls = "peer-chg-pos" if chg >= 0 else "peer-chg-neg"
                main_cls = " peer-main" if d["is_main"] else ""
                cards_html += (
                    f'<div class="peer-card{main_cls}">'
                    f'<div class="peer-ticker">{t}</div>'
                    f'<div class="{chg_cls}">{chg:+.1f}%</div>'
                    f'<div class="peer-price">{d["price"]:.2f}</div>'
                    f'</div>'
                )
            cards_html += '</div>'
            st.markdown(cards_html, unsafe_allow_html=True)
        else:
            st.info(_peers.get("error", "Peer data nejsou dostupná pro tento ticker."))


    with _det_tabs[1]:
        st.subheader("Backtest signálů")
        st.caption(
            "Jak by dopadly BUY/SELL signály tohoto systému na historických datech. "
            "Win rate = procento obchodů v zisku. Backtest negarantuje budoucí výsledky."
        )

        all_bt_stocks = {**{n: t for n, (t, c, s) in PORTFOLIO.items()},
                         **{n: t for n, (t, c, s) in RADAR_STOCKS.items()}}
        _bt_default_name = next(
            (n for n, t in all_bt_stocks.items() if t == ticker),
            list(all_bt_stocks.keys())[0]
        )
        bt_choice = st.selectbox(
            "Vyber akcii pro backtest",
            list(all_bt_stocks.keys()),
            index=list(all_bt_stocks.keys()).index(_bt_default_name),
            key="bt_selectbox",
        )
        bt_period = st.select_slider("Historické období", ["1y", "2y", "3y", "5y"], value="2y")
        bt_ticker = all_bt_stocks[bt_choice]

        if st.button("Spustit backtest", type="primary", key="bt_run_btn"):
            with st.spinner(f"Počítám backtest pro {bt_ticker} za {bt_period}... (může trvat 20–60s)"):
                result = run_backtest(bt_ticker, period=bt_period)

            if not result.get("ok"):
                st.error(f"Chyba: {result.get('error', 'Neznámá chyba')}")
            else:
                st.subheader("Souhrnné výsledky")
                tbl = backtest_summary_table(result)
                if not tbl.empty:
                    st.dataframe(tbl, hide_index=True, use_container_width=True)

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
                        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

                st.info(
                    "Interpretace: Win rate > 55% a průměrný výnos > 0 naznačuje, "
                    "že signály mají historicky prediktivní hodnotu. "
                    "Pod 45% win rate je signální systém pro danou akcii méně spolehlivý."
                )
        else:
            st.info("Klikni na 'Spustit backtest' pro zahájení analýzy.")


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 3 – Radar & Trh
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Příležitosti":
    tab_radar, tab_korelace = st.tabs(["Radar příležitostí", "Korelace portfolia"])

    # ── Tab: Radar příležitostí ───────────────────────────────────────────────
    with tab_radar:
        st.title("Příležitosti")

        # Horizontový filtr
        _radar_hz = st.segmented_control(
            "Horizont radaru",
            ["Krátkodobý", "Střednědobý", "Dlouhodobý"],
            default="Střednědobý",
            key="radar_hz",
            label_visibility="collapsed",
        )
        _radar_period_map = {"Krátkodobý": "3mo", "Střednědobý": "6mo", "Dlouhodobý": "2y"}
        _radar_period = _radar_period_map.get(_radar_hz or "Střednědobý", "6mo")

        # ── Data ─────────────────────────────────────────────────────────────
        with st.spinner("Načítám data..."):
            sector_perf_raw = fetch_sectors(_radar_period)
            _fg_opp = fetch_fear_greed()
        sector_perf = {s["name"]: s["chg_period"] for s in sector_perf_raw}

        with st.spinner(f"Skenuji {len(RADAR_STOCKS_FULL)} akcií..."):
            all_radar_results = scan_stocks(RADAR_STOCKS_FULL, _radar_period)
        for r in all_radar_results:
            r["sector_chg"] = sector_perf.get(r["sector"], None)

        results = [r for r in all_radar_results if not selected_sectors or r["sector"] in selected_sectors]

        # ── SEKCE 1: Kontext trhu ─────────────────────────────────────────────
        _fg_score = _fg_opp.get("score") if _fg_opp.get("ok") else None
        _fg_lbl, _fg_clr = fg_label(_fg_score)
        _fg_pct  = int((_fg_score or 50))
        _sectors_green = sum(1 for s in sector_perf_raw if s["chg_period"] >= 0)
        _sectors_red   = len(sector_perf_raw) - _sectors_green
        _top_sectors   = sorted(sector_perf_raw, key=lambda x: -x["chg_period"])
        _top3_html = "".join(
            f'<span style="color:{"#22c55e" if s["chg_period"]>=0 else "#ef4444"};font-size:0.78rem;white-space:nowrap">'
            f'{s["name"].split()[0]} {s["chg_period"]:+.1f}%</span>'
            for s in _top_sectors[:3]
        )
        _bot3_html = "".join(
            f'<span style="color:#ef4444;font-size:0.78rem;white-space:nowrap">'
            f'{s["name"].split()[0]} {s["chg_period"]:+.1f}%</span>'
            for s in _top_sectors[-3:]
        )

        _top3_str = " · ".join(s["name"].split()[0] + f' {s["chg_period"]:+.1f}%' for s in _top_sectors[:3])
        _bot3_str = " · ".join(s["name"].split()[0] + f' {s["chg_period"]:+.1f}%' for s in _top_sectors[-3:])
        _fg_score_str = str(int(_fg_score)) if _fg_score is not None else "–"

        st.markdown(
            '<div style="background:#1e293b;border-radius:12px;padding:14px 16px;margin-bottom:12px">'
            '<div style="color:#64748b;font-size:0.7rem;font-weight:600;margin-bottom:10px;letter-spacing:.05em">KONTEXT TRHU</div>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
            '<div>'
            '<div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">Index strachu &amp; chamtivosti</div>'
            f'<div style="font-size:1.1rem;font-weight:700;color:{_fg_clr}">{_fg_lbl}</div>'
            f'<div style="position:relative;height:6px;background:#334155;border-radius:3px;margin:6px 0;max-width:140px">'
            f'<div style="position:absolute;left:{_fg_pct}%;top:50%;transform:translate(-50%,-50%);width:10px;height:10px;border-radius:50%;background:{_fg_clr}"></div>'
            '</div>'
            f'<div style="color:#64748b;font-size:0.72rem">{_fg_score_str} / 100</div>'
            '</div>'
            '<div>'
            f'<div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">Sektory ({_sectors_green} zelených / {_sectors_red} červených)</div>'
            f'<div style="color:#22c55e;font-size:0.72rem;margin-bottom:3px">Nejsilnější: {_top3_str}</div>'
            f'<div style="color:#ef4444;font-size:0.72rem">Nejslabší: {_bot3_str}</div>'
            '</div>'
            '</div></div>',
            unsafe_allow_html=True
        )

        # ── SEKCE 2: Top příležitosti ─────────────────────────────────────────
        _buy_all = [r for r in results if r["action"] == "BUY"]
        _double  = [r for r in _buy_all if (r.get("sector_chg") or 0) > 1.0]
        _other   = [r for r in _buy_all if r not in _double]
        _top5    = sorted(_double, key=lambda x: -_opportunity_score(x))[:5] or sorted(_other, key=lambda x: -_opportunity_score(x))[:5]
        _all_buy_sorted = sorted(_double, key=lambda x: -_opportunity_score(x)) + sorted(_other, key=lambda x: -_opportunity_score(x))

        st.markdown('<div style="color:#64748b;font-size:0.7rem;font-weight:600;margin:16px 0 8px;letter-spacing:.05em">TOP PŘÍLEŽITOSTI</div>', unsafe_allow_html=True)
        _opp_ua = st.context.headers.get("User-Agent", "")
        _opp_mobile = any(k in _opp_ua for k in ("Mobile", "Android", "iPhone", "iPad"))
        if _top5:
            if _opp_mobile:
                for _r in _top5:
                    _render_radar_card(_r, highlight=_r in _double)
            else:
                for _oi in range(0, len(_top5), 2):
                    _ocols = st.columns(2)
                    with _ocols[0]:
                        _render_radar_card(_top5[_oi], highlight=_top5[_oi] in _double)
                    with _ocols[1]:
                        if _oi + 1 < len(_top5):
                            _render_radar_card(_top5[_oi + 1], highlight=_top5[_oi + 1] in _double)
        else:
            st.info("Žádné BUY signály. Trh je v klidném pásmu — čekej na příležitost.")

        # ── SEKCE 3: Sledovat portfolio ───────────────────────────────────────
        _sell_port  = [r for r in results if r["action"] == "SELL" and r["ticker"] in PORTFOLIO_TICKERS]
        _watch_port = [r for r in results if r["action"] == "HOLD" and r["ticker"] in PORTFOLIO_TICKERS and r.get("rsi", 50) > 65]
        _near_buy   = [r for r in results if r["action"] == "HOLD" and r.get("rsi", 50) < 38 and r["ticker"] not in PORTFOLIO_TICKERS]

        if _sell_port or _watch_port or _near_buy:
            st.markdown('<div style="color:#64748b;font-size:0.7rem;font-weight:600;margin:16px 0 8px;letter-spacing:.05em">SLEDOVAT</div>', unsafe_allow_html=True)

            for _r in _sell_port:
                _render_radar_card(_r, highlight=False)

            for _r in _watch_port:
                _sc = "#ef4444"
                st.markdown(
                    f'<div style="background:#1e293b;border-left:3px solid {_sc};border-radius:8px;padding:10px 14px;margin:4px 0">'
                    f'<div style="display:flex;align-items:center;gap:8px">'
                    f'<span style="background:#ef444422;border:1px solid #ef4444;border-radius:5px;padding:2px 8px;font-size:0.75rem;font-weight:700;color:#ef4444">PŘEKOUPENO</span>'
                    f'<strong>{_r["name"]}</strong><span style="color:#64748b;font-size:0.8rem">{_r["ticker"]}</span>'
                    f'</div>'
                    f'<div style="color:#94a3b8;font-size:0.78rem;margin-top:4px">RSI {_r["rsi"]:.0f} · {_r["ema_trend"]} · {_r["price"]:.2f} {_r["currency"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            for _r in _near_buy[:3]:
                _wc = "#f59e0b"
                st.markdown(
                    f'<div style="background:#1e293b;border-left:3px solid {_wc};border-radius:8px;padding:10px 14px;margin:4px 0">'
                    f'<div style="display:flex;align-items:center;gap:8px">'
                    f'<span style="background:#f59e0b22;border:1px solid #f59e0b;border-radius:5px;padding:2px 8px;font-size:0.75rem;font-weight:700;color:#f59e0b">BLÍZKO BUY</span>'
                    f'<strong>{_r["name"]}</strong><span style="color:#64748b;font-size:0.8rem">{_r["ticker"]}</span>'
                    f'</div>'
                    f'<div style="color:#94a3b8;font-size:0.78rem;margin-top:4px">RSI {_r["rsi"]:.0f} · {_r["ema_trend"]} · sektor {_r.get("sector_chg", 0):+.1f}%</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # ── SEKCE 4: Celý radar (schovaný) ───────────────────────────────────
        with st.expander(f"Celý radar podle sektoru ({len(results)} akcií)", expanded=False):
            sectors_with_stocks: dict = {}
            for _r in sorted(results, key=lambda x: x["name"]):
                sectors_with_stocks.setdefault(_r["sector"], []).append(_r)
            for _sn in sorted(sectors_with_stocks, key=lambda s: -(sector_perf.get(s, 0))):
                _ss = sectors_with_stocks[_sn]
                _sp = sector_perf.get(_sn)
                _sp_str = f"{_sp:+.1f}%" if _sp is not None else "N/A"
                _bi = sum(1 for _r in _ss if _r["action"] == "BUY")
                _si = sum(1 for _r in _ss if _r["action"] == "SELL" and _r["ticker"] in PORTFOLIO_TICKERS)
                _sig = " · ".join(filter(None, [f"{_bi} BUY" if _bi else "", f"{_si} SELL" if _si else ""])) or "vše HOLD"
                with st.expander(f"{_sn}  {_sp_str}  ·  {_sig}  ({len(_ss)})"):
                    for _r in sorted(_ss, key=lambda x: {"BUY": 0, "SELL": 1, "HOLD": 2}[x["action"]]):
                        _arr = "▲" if _r["chg_pct"] >= 0 else "▼"
                        _pc  = "#22c55e" if _r["chg_pct"] >= 0 else "#ef4444"
                        _tc  = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Smíšený": "#888"}[_r["ema_trend"]]
                        _da  = _r["action"] if (_r["action"] != "SELL" or _r["ticker"] in PORTFOLIO_TICKERS) else "HOLD"
                        _bc  = {"BUY": "badge-buy", "SELL": "badge-sell", "HOLD": "badge-hold"}[_da]
                        _bl  = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[_da]
                        _cc  = {"BUY": "card-buy", "SELL": "card-sell", "HOLD": "card-hold"}[_da]
                        _rs  = (_r["buy_reasons"] if _r["action"] == "BUY" else _r["sell_reasons"])[:2]
                        _rh  = " · ".join(_rs) if _rs else ""
                        st.markdown(
                            f'<div class="{_cc}" style="margin:3px 0;padding:10px">'
                            f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px">'
                            f'<span class="{_bc}" style="white-space:nowrap">{_bl}</span>'
                            f'<strong style="white-space:nowrap">{_r["name"]}</strong>'
                            f'<span style="color:#888;font-size:0.8rem">{_r["ticker"]}</span>'
                            f'</div>'
                            f'<div style="font-size:0.8rem;color:#94a3b8;margin-top:4px">'
                            f'<span style="color:{_pc}">{_r["price"]:.2f} {_r["currency"]} {_arr}{_r["chg_pct"]:+.1f}%</span>'
                            f' · RSI <b>{_r["rsi"]:.0f}</b>'
                            f' · <span style="color:{_tc}">{_r["ema_trend"]}</span>'
                            f'</div>'
                            + (f'<div style="margin-top:3px"><small style="color:#aaa">{_rh}</small></div>' if _rh else "")
                            + '</div>',
                            unsafe_allow_html=True,
                        )

    # ── Tab: Korelace portfolia ───────────────────────────────────────────────
    with tab_korelace:
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
            _corr_ua = st.context.headers.get("User-Agent", "")
            _corr_mobile = any(k in _corr_ua for k in ("Mobile", "Android", "iPhone", "iPad"))
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
                text=[[f"{v:.1f}" for v in row] for row in corr.values],
                texttemplate="" if _corr_mobile else "%{text}",
                textfont={"size": 9},
            ))
            fig_corr.update_layout(
                template="plotly_dark",
                height=350 if _corr_mobile else 500,
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(fig_corr, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

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
            st.plotly_chart(fig_norm, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "staticPlot": True})


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 5 – Deník
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Deník":
    import json as _json
    st.title("Deník")
    st.caption("Zaznamenávej nákupy a prodeje na základě doporučení portálu. Sleduj, kolik ti signály vydělaly nebo vzaly.")

    init_db()

    # ── Upozornění na perzistenci ─────────────────────────────────────────────
    try:
        _using_sheets = bool(st.secrets.get("GSHEETS_URL", ""))
    except Exception:
        _using_sheets = bool(os.environ.get("GSHEETS_URL", ""))
    try:
        _using_pg = bool(st.secrets.get("DATABASE_URL", ""))
    except Exception:
        _using_pg = bool(os.environ.get("DATABASE_URL", ""))
    if not _using_pg and not _using_sheets:
        st.warning(
            "Úložiště: **lokální SQLite** — data se smažou při restartu. "
            "Pro trvalé uložení nastav `DATABASE_URL` v Secrets.",
            icon="⚠️",
        )

    tab_add, tab_history, tab_stats = st.tabs(["Přidat obchod", "Historie", "Výkonnost"])

    # ── Tab 1: Přidat obchod ──────────────────────────────────────────────────
    with tab_add:
        st.subheader("Zaznamenat obchod")

        all_portfolio = {n: (t, c) for n, (t, c, s) in PORTFOLIO.items()}
        all_radar_j   = {n: (t, c) for n, (t, c, s) in RADAR_STOCKS.items()}
        all_stocks_j  = {**all_portfolio, **all_radar_j}

        # Výběr akcie mimo formulář – abychom mohli načíst live cenu
        stock_options = list(all_portfolio.keys()) + ["─── Radar ───"] + list(all_radar_j.keys())
        stock_choice_j = st.selectbox("Vyber akcii", stock_options,
                                      help="Portfolio + radar akcie. Cena se načte automaticky.")

        # Ignoruj oddělovač
        if stock_choice_j.startswith("───"):
            st.stop()

        j_ticker, j_currency = all_stocks_j[stock_choice_j]

        # Datum obchodu – mimo formulář, aby změna triggernula reload ceny
        from datetime import date as _date, timedelta as _td
        trade_date_j = st.date_input(
            "Datum obchodu",
            value=_date.today(),
            max_value=_date.today(),
            help="Dnes = aktuální cena. Historické datum = závěrečná cena z burzy pro daný den.",
        )

        # Načti cenu pro zvolené datum
        _today = _date.today()
        _is_today = (trade_date_j == _today)

        with st.spinner(f"Načítám cenu {j_ticker}..."):
            try:
                if _is_today:
                    _df_j = yf.download(j_ticker, period="5d", auto_adjust=True, progress=False)
                    _df_j.columns = [c[0] if isinstance(c, tuple) else c for c in _df_j.columns]
                    _fetched_price = float(_df_j["Close"].iloc[-1]) if not _df_j.empty else 0.0
                    _price_label = "aktuální tržní cena"
                else:
                    _start = trade_date_j.strftime("%Y-%m-%d")
                    _end   = (trade_date_j + _td(days=5)).strftime("%Y-%m-%d")
                    _df_j  = yf.download(j_ticker, start=_start, end=_end, auto_adjust=True, progress=False)
                    _df_j.columns = [c[0] if isinstance(c, tuple) else c for c in _df_j.columns]
                    if not _df_j.empty:
                        # Nejbližší obchodní den od zvoleného data
                        _fetched_price = float(_df_j["Close"].iloc[0])
                        _actual_day    = _df_j.index[0]
                        _price_label   = f"závěrečná cena {_actual_day.strftime('%d.%m.%Y')}"
                    else:
                        _fetched_price = 0.0
                        _price_label   = "cena nenalezena"
            except Exception:
                _fetched_price = 0.0
                _price_label   = "chyba načítání"

        if _fetched_price:
            st.caption(f"Načteno: **{_fetched_price:.2f} {j_currency}** ({_price_label})")

        st.markdown("<style>"
                    "[data-testid='stForm'] [data-testid='stRadio'] label:first-of-type input:checked + div{background:#22c55e !important;border-color:#22c55e !important;}"
                    "[data-testid='stForm'] [data-testid='stRadio'] label:last-of-type input:checked + div{background:#ef4444 !important;border-color:#ef4444 !important;}"
                    "</style>", unsafe_allow_html=True)
        with st.form("trade_form"):
            action_j = st.radio(
                "Typ obchodu",
                ["↑  Koupil jsem", "↓  Prodal jsem"],
                horizontal=True,
                label_visibility="collapsed",
            )
            action_j = "BUY" if action_j.startswith("↑") else "SELL"

            price_j = st.number_input(
                f"Cena ({j_currency})",
                min_value=0.01,
                value=round(_fetched_price, 2) if _fetched_price else 1.0,
                step=0.01,
                key=f"price_j_{j_ticker}_{trade_date_j}",
                help="Předvyplněno automaticky — uprav pokud byla tvá reálná cena jiná.",
            )
            shares_j = st.number_input(
                "Počet akcií",
                min_value=0.0001,
                value=1.0,
                step=0.1,
                format="%g",
                key=f"shares_j_{j_ticker}",
            )

            # Živý náhled celkové hodnoty
            total_preview = price_j * shares_j
            st.markdown(
                f'<div style="background:#1e293b;border-radius:6px;padding:10px 14px;'
                f'margin:4px 0 8px;display:flex;justify-content:space-between;align-items:center">'
                f'<span style="color:#94a3b8;font-size:0.85rem">{stock_choice_j} · {j_ticker}</span>'
                f'<span style="font-size:1.1rem;font-weight:700;color:#f1f5f9">'
                f'{total_preview:,.2f} {j_currency}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            submitted = st.form_submit_button(
                "Uložit obchod",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            add_trade(
                ticker=j_ticker,
                name=stock_choice_j,
                action=action_j,
                price=price_j,
                shares=shares_j,
                date=trade_date_j.strftime("%Y-%m-%d %H:%M"),
            )
            lbl = "Koupeno" if action_j == "BUY" else "Prodáno"
            st.toast(f"{lbl}: {shares_j:g} × {j_ticker} @ {price_j:.2f} {j_currency}", icon="✅")
            _portfolio_tickers = {t for _, (t, _, _) in PORTFOLIO.items()}
            if action_j == "BUY" and j_ticker not in _portfolio_tickers:
                st.session_state["notify_add_portfolio"] = j_ticker
            st.rerun()

        if st.session_state.get("notify_add_portfolio"):
            _nticker = st.session_state["notify_add_portfolio"]
            st.warning(
                f"**{_nticker}** není ve tvém portfoliu — nezobrazí se v Přehledu portfolia. "
                f"Přidej ji do souboru `app.py` do sekce `PORTFOLIO`.",
                icon="⚠️",
            )
            if st.button("Rozumím", key="dismiss_portfolio_notify"):
                del st.session_state["notify_add_portfolio"]
                st.rerun()

        # Náhled posledních záznamů přímo v záložce Přidat
        _recent = get_trades()
        if not _recent.empty:
            st.divider()
            st.caption("Poslední záznamy")
            for _, _r in _recent.head(3).iterrows():
                _a = _r["action"]
                _clr = "#22c55e" if _a == "BUY" else "#ef4444"
                _lbl = "KOUPENO" if _a == "BUY" else "PRODÁNO"
                st.markdown(
                    f'<div style="background:#1e293b;border-left:3px solid {_clr};border-radius:6px;'
                    f'padding:8px 12px;margin:4px 0;font-size:0.82rem">'
                    f'<span style="color:{_clr};font-weight:700">{_lbl}</span> '
                    f'<strong>{_r["name"]}</strong> · {float(_r["shares"]):.3g} ks @ {float(_r["price"]):.2f}'
                    f'<span style="color:#64748b;font-size:0.72rem;float:right">{str(_r["date"])[:10]}</span></div>',
                    unsafe_allow_html=True,
                )

        st.divider()
        st.subheader("Import / Export")
        st.markdown("<style>"
                    "[data-testid='stDownloadButton'] button,"
                    "[data-testid='stFileUploader'] button{"
                    "  width:100% !important;height:38px !important;"
                    "  font-size:0.875rem !important;font-family:inherit !important;"
                    "  padding:0 !important;justify-content:center !important;}"
                    "[data-testid='stFileUploader'] > label{display:none !important;}"
                    "[data-testid='stFileUploaderDropzone']{border:none !important;background:transparent !important;padding:0 !important;margin:0 !important;}"
                    "[data-testid='stFileUploaderDropzoneInstructions']{display:none !important;}"
                    "[data-testid='stFileUploader'] section{padding:0 !important;margin:0 !important;}"
                    "[data-testid='stFileUploader'] button p{display:none !important;}"
                    "[data-testid='stFileUploader'] button::after{content:'Nahrát';font-size:0.875rem;font-family:inherit;}"
                    "</style>", unsafe_allow_html=True)
        _ie_dl, _ie_ul = st.columns(2)
        with _ie_dl:
            df_exp = get_trades()
            if not df_exp.empty:
                csv_bytes = df_exp.to_csv(index=False).encode("utf-8")
                st.markdown('<p style="font-size:0.85rem;margin-bottom:6px;color:#94a3b8">Záloha dat (CSV)</p>', unsafe_allow_html=True)
                st.download_button(
                    "Stáhnout",
                    data=csv_bytes,
                    file_name=f"trades_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
        with _ie_ul:
            st.markdown('<p style="font-size:0.85rem;margin-bottom:6px;color:#94a3b8">Obnovit ze zálohy (CSV)</p>', unsafe_allow_html=True)
            uploaded = st.file_uploader("Nahrát zálohu", type="csv", label_visibility="collapsed")
            if uploaded:
                try:
                    n = import_from_csv(uploaded.read())
                    st.success(f"Importováno {n} obchodů.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Chyba importu: {e}")

    # ── Tab 2: Historie ───────────────────────────────────────────────────────
    with tab_history:
        st.markdown("<style>"
                    "[data-testid='stHorizontalBlock']{gap:4px !important;}"
                    "[data-testid='stHorizontalBlock'] [data-testid='stColumn']{padding:0 2px !important;min-width:0 !important;}"
                    "[data-testid='stHorizontalBlock'] button{padding:4px 4px !important;font-size:0.76rem !important;min-height:0 !important;width:100% !important;}"
                    "</style>", unsafe_allow_html=True)
        st.subheader("Historie obchodů")
        df_raw = get_trades()
        if df_raw.empty:
            st.info("Zatím žádné záznamy. Přidej první obchod v záložce 'Přidat obchod'.")
        else:
            with st.spinner("Načítám aktuální ceny..."):
                df_perf = get_performance(df_raw)

            for _, row in df_perf.iterrows():
                action_r  = row["Akce"]
                clr       = "#22c55e" if action_r == "BUY" else "#ef4444"
                badge_lbl = "KOUPENO" if action_r == "BUY" else "PRODÁNO"

                # Pro SELL: zobraz realizovaný zisk (prodej vs. nákup), ne pohyb od prodeje
                pnl     = row["P&L %"]
                pnl_abs = row["P&L Kč/USD"]

                pnl_html = ""
                if pd.notna(pnl):
                    pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
                    pnl_czk   = pnl_abs * get_usdczk() if pd.notna(pnl_abs) else 0
                    pnl_html  = (f'<div style="color:{pnl_color};font-weight:700;font-size:0.85rem">'
                                 f'P&L: {pnl:+.1f}% ({pnl_czk:+.0f} Kč)</div>')

                cur_html  = (f'<div style="color:#94a3b8;font-size:0.78rem">Aktuálně: {row["Aktuální"]:.2f}</div>'
                             if row["Aktuální"] else "")
                note_html = (f'<div style="color:#888;font-size:0.75rem">{row["Poznámka"]}</div>'
                             if row["Poznámka"] else "")

                st.markdown(
                    f'<div style="background:#1e293b;border-left:3px solid {clr};border-radius:8px;'
                    f'padding:10px 12px;margin:4px 0 2px;word-break:break-word;overflow-wrap:break-word">'
                    f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">'
                    f'<span style="background:{clr}22;color:{clr};border:1px solid {clr};border-radius:4px;'
                    f'padding:1px 6px;font-size:0.7rem;font-weight:700">{badge_lbl}</span>'
                    f'<strong style="font-size:0.9rem">{row["Název"]}</strong>'
                    f'<span style="color:#64748b;font-size:0.78rem">{row["Ticker"]}</span>'
                    f'<span style="color:#64748b;font-size:0.72rem;margin-left:auto">{row["Datum"]}</span>'
                    f'</div>'
                    f'<div style="color:#94a3b8;font-size:0.82rem">Vstup: <b style="color:#f1f5f9">{row["Vstup"]:.2f}</b>'
                    f' × {row["Počet"]:.3g} = <b style="color:#f1f5f9">{row["Investováno"]:.0f}</b></div>'
                    f'{cur_html}{pnl_html}{note_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("<div style='margin-top:2px'></div>", unsafe_allow_html=True)
                _btn_col1, _btn_col2 = st.columns([1, 1])
                with _btn_col1:
                    if st.button("✏️ Upravit", key=f"edit_toggle_{row['id']}", use_container_width=True, help="Upravit záznam"):
                        st.session_state[f"edit_open_{row['id']}"] = not st.session_state.get(f"edit_open_{row['id']}", False)
                with _btn_col2:
                    if st.button("🗑️ Smazat", key=f"del_{row['id']}", use_container_width=True, help="Smazat záznam"):
                        delete_trade(int(row["id"]))
                        st.rerun()
                if st.session_state.get(f"edit_open_{row['id']}", False):
                    with st.form(key=f"edit_form_{row['id']}"):
                        _ep = st.number_input("Cena", value=float(row["Vstup"]), step=0.01, format="%.2f")
                        _es = st.number_input("Počet akcií", value=float(row["Počet"]), min_value=0.0001, step=0.1, format="%g")
                        _en = st.text_input("Poznámka", value=str(row["Poznámka"]))
                        if st.form_submit_button("Uložit", type="primary", use_container_width=True):
                            update_trade(int(row["id"]), _ep, _es, _en)
                            st.session_state[f"edit_open_{row['id']}"] = False
                            st.toast("Záznam upraven", icon="✅")
                            st.rerun()
                st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

    # ── Tab 3: Výkonnost ──────────────────────────────────────────────────────
    with tab_stats:
        st.subheader("Výkonnost doporučení")
        df_raw_s = get_trades()
        if df_raw_s.empty:
            st.info("Zatím žádné záznamy.")
        else:
            with st.spinner("Počítám výkonnost..."):
                df_perf_s = get_performance(df_raw_s)
                stats     = get_stats(df_perf_s)

            if stats:
                _fx        = get_usdczk()
                win_rate   = stats.get("win_rate", 0)
                total_pnl  = stats.get("total_pnl_abs", 0) * _fx
                total_pct  = stats.get("total_pnl_pct", 0)
                real_pnl   = stats.get("realized_pnl_abs", 0) * _fx
                pnl_clr    = "#22c55e" if total_pnl >= 0 else "#ef4444"
                real_clr   = "#22c55e" if real_pnl >= 0 else "#ef4444"
                wr_clr     = "#22c55e" if win_rate >= 50 else "#ef4444"
                best        = stats.get("best_trade", 0)
                best_ticker = stats.get("best_ticker", "")
                worst       = stats.get("worst_trade", 0)
                worst_ticker= stats.get("worst_ticker", "")
                avg         = stats.get("avg_pnl", 0)
                avg_label   = ("Daří se skvěle" if avg >= 10 else
                               "Daří se dobře"  if avg >= 3  else
                               "Průměrně"       if avg >= 0  else
                               "Mírná ztráta"   if avg >= -5 else
                               "Nedaří se")

                def _stat_box(label, value, sub="", clr="#f1f5f9"):
                    sub_html = f'<div style="color:#64748b;font-size:0.68rem;margin-top:2px">{sub}</div>' if sub else ""
                    return (f'<div style="background:#1e293b;border:1px solid #334155;border-radius:10px;'
                            f'padding:12px 8px;text-align:center">'
                            f'<div style="color:#94a3b8;font-size:0.68rem;margin-bottom:4px">{label}</div>'
                            f'<div style="color:{clr};font-size:1.2rem;font-weight:700">{value}</div>'
                            f'{sub_html}</div>')

                st.markdown(f"""<style>
.stats-grid6 {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:8px; align-items:stretch; }}
.stats-grid6 > div {{ min-height:80px; display:flex; flex-direction:column; justify-content:center; }}
@media(max-width:640px) {{
  .stats-grid6 {{ grid-template-columns:repeat(2,1fr); }}
}}
</style>
<div class="stats-grid6">
  {_stat_box("Celkem obchodů", stats.get("total_trades", 0), f"Nákupy: {stats.get('buy_count',0)} · Prodeje: {stats.get('sell_count',0)}")}
  {_stat_box("Win rate", f"{win_rate:.0f}%", "≥50% = funguje", wr_clr)}
  {_stat_box("Celkový P&L", f"{total_pnl:+.0f} Kč", f"{total_pct:+.1f}% investovaného", pnl_clr)}
  {_stat_box("Nejlepší obchod", f"{best:+.1f}%", best_ticker, "#22c55e" if best>=0 else "#ef4444")}
  {_stat_box("Nejhorší obchod", f"{worst:+.1f}%", worst_ticker, "#22c55e" if worst>=0 else "#ef4444")}
  {_stat_box("Průměrný P&L",   f"{avg:+.1f}%",   avg_label,   "#22c55e" if avg>=0   else "#ef4444")}
</div>
""", unsafe_allow_html=True)

                # Graf P&L jednotlivých obchodů
                open_pos = df_perf_s[df_perf_s["Status"] == "Otevřená"].dropna(subset=["P&L %"])
                if not open_pos.empty:
                    st.divider()
                    st.subheader("P&L nakoupených akcií")
                    colors = ["#22c55e" if v >= 0 else "#ef4444" for v in open_pos["P&L %"]]
                    fig_pnl = go.Figure(go.Bar(
                        x=open_pos["Ticker"],
                        y=open_pos["P&L %"],
                        marker_color=colors,
                        text=[f"{v:+.1f}%" for v in open_pos["P&L %"]],
                        textposition="outside",
                        customdata=open_pos[["Název", "Vstup", "Aktuální", "Investováno"]].values,
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br>"
                            "Vstup: %{customdata[1]:.2f}<br>"
                            "Aktuálně: %{customdata[2]:.2f}<br>"
                            "Investováno: %{customdata[3]:.0f}<br>"
                            "P&L: %{y:+.1f}%<extra></extra>"
                        ),
                    ))
                    fig_pnl.add_hline(y=0, line=dict(color="#666", width=1))
                    fig_pnl.update_layout(
                        template="plotly_dark", height=300,
                        margin=dict(l=0, r=0, t=20, b=0),
                        showlegend=False,
                        yaxis_title="P&L (%)",
                    )
                    st.plotly_chart(fig_pnl, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})


# ── Patička ───────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"Aktualizováno: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}  |  "
    "Data: Yahoo Finance · Finviz · MarketWatch · CNN  |  "
    "Tento nástroj NENÍ finančním poradenstvím."
)
