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
from trade_journal import add_trade, get_trades, get_performance, get_stats, delete_trade, import_from_csv, init_db

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
    [data-testid="stSegmentedControl"],
    [data-testid="stSegmentedControl"] > div,
    [data-testid="stSegmentedControl"] div[role="group"] {
        width: 100% !important;
        display: flex !important;
    }
    [data-testid="stSegmentedControl"] label,
    [data-testid="stSegmentedControl"] div[role="group"] > * {
        flex: 1 !important;
        text-align: center !important;
        justify-content: center !important;
    }
}

/* ── Tablet ── */
@media (max-width: 1024px) and (min-width: 769px) {
    .block-container { padding: 1rem 1.5rem 2rem !important; }
    .card-buy, .card-sell, .card-hold, .card-radar { font-size: 0.92rem !important; }
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

/* levý sloupec – badge + skóre */
.pf-left { grid-column:1; grid-row:1/3; display:flex; flex-direction:column; gap:6px; align-items:flex-start; min-width:80px; }

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
    .pf-card { grid-template-columns: 1fr auto; grid-template-rows: auto auto auto; gap:4px 8px; padding:10px 10px; }
    .pf-left  { grid-column:1; grid-row:1; flex-direction:row; flex-wrap:wrap; min-width:unset; }
    .pf-name  { grid-column:1; grid-row:2; font-size:0.95rem; }
    .pf-meta  { grid-column:1/3; grid-row:3; }
    .pf-price-block { grid-column:2; grid-row:1/3; }
    .pf-reasons { grid-column:1/3; }
    .pf-price { font-size:0.95rem; }
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
    # ── Technologie – Evropa ─────────────────────────────────────────────────
    "ASML":             ("ASML",  "USD", "Technologie"),
    "SAP":              ("SAP",   "USD", "Technologie"),
    "Infineon":         ("IFNNY", "USD", "Technologie"),
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
    # ── Utility (XLU) ────────────────────────────────────────────────────────
    "NextEra Energy":   ("NEE",   "USD", "Utility"),
    "Duke Energy":      ("DUK",   "USD", "Utility"),
    "Iberdrola":        ("IBDRY", "USD", "Utility"),
    "Enel":             ("ENLAY", "USD", "Utility"),
    # ── Materiály & Těžba (XLB) ──────────────────────────────────────────────
    "Freeport-McMoRan": ("FCX",   "USD", "Materiály"),
    "Newmont":          ("NEM",   "USD", "Materiály"),
    "BHP":              ("BHP",   "USD", "Materiály"),
    "Rio Tinto":        ("RIO",   "USD", "Materiály"),
    "Vale":             ("VALE",  "USD", "Materiály"),
    "Glencore":         ("GLEN.L","GBP", "Materiály"),
    "Anglo American":   ("AAL.L", "GBP", "Materiály"),
    # ── Komunikace & Média (XLC) ─────────────────────────────────────────────
    "Netflix":          ("NFLX",  "USD", "Komunikace"),
    "Walt Disney":      ("DIS",   "USD", "Komunikace"),
    "Spotify":          ("SPOT",  "USD", "Komunikace"),
    "T-Mobile":         ("TMUS",  "USD", "Komunikace"),
    "Comcast":          ("CMCSA", "USD", "Komunikace"),
    # ── Reality (XLRE) ───────────────────────────────────────────────────────
    "Prologis":         ("PLD",   "USD", "Reality"),
    "American Tower":   ("AMT",   "USD", "Reality"),
    "Equinix":          ("EQIX",  "USD", "Reality"),
}

# ── Sada tickerů v portfoliu (pro filtrování signálů v radaru) ────────────────
PORTFOLIO_TICKERS = {t for t, _, _ in PORTFOLIO.values()}

# ── Sidebar ───────────────────────────────────────────────────────────────────
refresh = False       # default; přepsáno tlačítkem v sidebaru
period  = "6mo"       # default; přepsáno selectboxem v sidebaru
detail_ticker   = list(PORTFOLIO.values())[0][0]
detail_currency = "USD"
show_ema = True
show_bb  = True
selected_sectors: list = []
investment_horizon = "Střednědobý (3–12 měs.)"

_pages = ["Přehled portfolia", "Detail akcie", "Příležitosti", "Deník obchodů"]

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
_pages = ["Přehled portfolia", "Detail akcie", "Příležitosti", "Deník obchodů"]
_page_icons = ["📊", "🔍", "🎯", "📓"]
st.markdown("""
<style>
.mob-nav { display:none }
@media (max-width: 768px) {
  .mob-nav {
    display: flex; position: sticky; top: 0; z-index: 999;
    background: #0f172a; border-bottom: 1px solid #1e293b;
    overflow-x: auto; gap: 0; padding: 0; margin: -1rem -1rem 1rem -1rem;
    -webkit-overflow-scrolling: touch; scrollbar-width: none;
  }
  .mob-nav::-webkit-scrollbar { display: none; }
  .mob-nav a {
    flex: 0 0 auto; padding: 10px 14px; font-size: 0.8rem;
    color: #94a3b8; text-decoration: none; white-space: nowrap;
    border-bottom: 2px solid transparent;
  }
  .mob-nav a.active { color: #22c55e; border-bottom-color: #22c55e; }
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
        all_sectors = sorted(set(v[2] for v in RADAR_STOCKS.values()))
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


@st.cache_data(ttl=1800)
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
    st.title("Portfolio přehled")
    st.caption(f"Aktualizováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    # Tržní kontext – gauge + VIX
    with st.spinner("Načítám tržní kontext..."):
        _fg = fetch_fear_greed()
        _macro_mini = fetch_macro_tickers()

    _fg_score = _fg.get("score") if _fg.get("ok") else None
    _vix      = _macro_mini.get("VIX", {}).get("price") if _macro_mini else None
    _vix_chg  = _macro_mini.get("VIX", {}).get("chg")   if _macro_mini else None
    _fg_label_str, _fg_color = fg_label(_fg_score) if _fg_score is not None else ("N/A", "#888")

    _ctx_left, _ctx_right = st.columns([1, 1])

    with _ctx_left:
        st.markdown("**Index strachu a chamtivosti**")
        if _fg_score is not None:
            _fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=_fg_score,
                title={"text": _fg_label_str, "font": {"size": 14}},
                number={"font": {"size": 36}},
                gauge={
                    "axis": {"range": [0, 100], "tickvals": [0, 25, 45, 55, 75, 100],
                             "ticktext": ["0", "25", "45", "55", "75", "100"]},
                    "bar": {"color": _fg_color, "thickness": 0.25},
                    "steps": [
                        {"range": [0,  25], "color": "#7f1d1d"},
                        {"range": [25, 45], "color": "#9a3412"},
                        {"range": [45, 55], "color": "#713f12"},
                        {"range": [55, 75], "color": "#365314"},
                        {"range": [75,100], "color": "#14532d"},
                    ],
                    "threshold": {"line": {"color": "white", "width": 3},
                                  "thickness": 0.85, "value": _fg_score},
                },
            ))
            _fig_gauge.update_layout(
                height=250, template="plotly_dark",
                margin=dict(l=10, r=10, t=30, b=5),
            )
            st.plotly_chart(_fig_gauge, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

            # Interpretace pod grafem
            if _fg_score <= 25:
                st.error("Extrémní strach – trh v panice. Historicky dobrá příležitost pro long-term nákup.")
            elif _fg_score <= 45:
                st.warning("Strach – pesimismus převládá. Opatrný optimismus může být opodstatněný.")
            elif _fg_score <= 55:
                st.info("Neutrální – trh neví kam. Čekej na jasný signál.")
            elif _fg_score <= 75:
                st.success("Chamtivost – optimismus na trhu. Pozor na předražení.")
            else:
                st.error("Extrémní chamtivost – euforie! Zvažuj profit-taking, trh může být přehřátý.")
        else:
            st.warning("Index strachu a chamtivosti se nepodařilo načíst.")

    _MACRO_DESC = {
        "VIX":          "index volatility – čím vyšší, tím větší nervozita trhu",
        "10Y Treasury": "výnos 10letých US dluhopisů – nad 5% tlačí akcie dolů",
        "Gold":         "zlato – roste, když jsou investoři v panice",
        "Oil (WTI)":    "cena ropy – ovlivňuje inflaci i energetické firmy",
        "USD Index":    "síla dolaru – silný dolar zhoršuje zisky US firem ze zahraničí",
        "S&P 500":      "hlavní US akciový index – celkový tep amerického trhu",
    }

    with _ctx_right:
        st.markdown("**Klíčové makro ukazatele**")
        if _macro_mini:
            for _name, _data in _macro_mini.items():
                _p   = _data["price"]
                _c   = _data["chg"]
                _arr = "▲" if _c >= 0 else "▼"
                _col = "#22c55e" if _c >= 0 else "#ef4444"
                _note = ""
                if _name == "VIX":
                    _note = "nízká volatilita" if _p < 15 else "zvýšená nervozita" if _p > 25 else "normální"
                elif _name == "10Y Treasury":
                    _note = "tlak na akcie" if _p > 5 else "příznivé" if _p < 3 else "zvýšené výnosy"
                _desc = _MACRO_DESC.get(_name, "")
                st.markdown(
                    f'<div class="card-hold" style="margin:3px 0;padding:8px 12px">'
                    f'<div style="display:flex;align-items:baseline;gap:6px;overflow:hidden">'
                    f'<span style="font-size:0.9rem;font-weight:700;white-space:nowrap">{_name}</span>'
                    f'<span style="color:#555;font-size:0.75rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_desc}</span>'
                    f'</div>'
                    f'<div style="display:flex;align-items:center;gap:10px;margin-top:2px">'
                    f'<span style="font-size:1.05rem;font-weight:600">{_p:.2f}</span>'
                    f'<span style="color:{_col};font-weight:600">{_arr} {_c:+.1f}%</span>'
                    + (f'<span style="color:#666;font-size:0.78rem">· {_note}</span>' if _note else "")
                    + '</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("Makro data se nepodařilo načíst.")

    st.divider()

    with st.expander("Jak číst tento přehled?"):
        st.markdown("""
- **KOUPIT** (zelená) = alespoň 3 technické indikátory najednou naznačují, že akcie je podhodnocená nebo se chystá růst
- **PRODAT** (červená) = alespoň 3 indikátory naznačují, že akcie je předražená nebo se chystá klesat
- **DRŽET** (šedá) = indikátory si protiřečí nebo nejsou dostatečně výrazné → nic nedělej
- **RSI** = číslo 0–100. Pod 30 je akcie „levná" (přeprodaná), nad 70 „drahá" (překoupená)
- **Trend** = Bullish znamená rostoucí trend, Bearish klesající, Smíšený = nejasný
- **Síla signálu** = kolik % z maximálního počtu indikátorů souhlasí (60%+ = silný signál)
        """)

    # Výběr horizontu pro portfolio overview
    _pf_hz_label = st.segmented_control(
        "Investiční horizont signálů",
        ["Krátkodobý", "Střednědobý", "Dlouhodobý"],
        default="Krátkodobý",
        key="pf_horizon",
    )
    _pf_period_map = {"Krátkodobý": "3mo", "Střednědobý": "1y", "Dlouhodobý": "2y"}
    _pf_period = _pf_period_map.get(_pf_hz_label or "Krátkodobý", "3mo")

    with st.spinner("Načítám data pro celé portfolio..."):
        results = scan_stocks(PORTFOLIO, _pf_period)

    if not results:
        st.error("Nepodařilo se načíst data. Zkontroluj připojení.")
        st.stop()

    # ── Souhrnná lišta ────────────────────────────────────────────────────────
    buy_count  = sum(1 for r in results if r["action"] == "BUY")
    sell_count = sum(1 for r in results if r["action"] == "SELL")
    hold_count = sum(1 for r in results if r["action"] == "HOLD")

    st.markdown(f"""
<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">
  <div style="flex:1;min-width:120px;background:#1e293b;border-radius:10px;padding:14px 18px;text-align:center">
    <div style="color:#94a3b8;font-size:0.75rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Sledované akcie</div>
    <div style="font-size:2rem;font-weight:800;color:#f1f5f9">{len(results)}</div>
  </div>
  <div style="flex:1;min-width:120px;background:#052e16;border:2px solid #22c55e;border-radius:10px;padding:14px 18px;text-align:center">
    <div style="color:#86efac;font-size:0.75rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Koupit</div>
    <div style="font-size:2rem;font-weight:800;color:#22c55e">{buy_count}</div>
  </div>
  <div style="flex:1;min-width:120px;background:#2d0a0a;border:2px solid #ef4444;border-radius:10px;padding:14px 18px;text-align:center">
    <div style="color:#fca5a5;font-size:0.75rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Prodat</div>
    <div style="font-size:2rem;font-weight:800;color:#ef4444">{sell_count}</div>
  </div>
  <div style="flex:1;min-width:120px;background:#1a1a2e;border:1px solid #444;border-radius:10px;padding:14px 18px;text-align:center">
    <div style="color:#94a3b8;font-size:0.75rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Držet</div>
    <div style="font-size:2rem;font-weight:800;color:#94a3b8">{hold_count}</div>
  </div>
</div>
""", unsafe_allow_html=True)
    st.divider()

    # ── Karty akcií – nejprve akce, pak hold ─────────────────────────────────
    def action_order(r):
        return {"BUY": 0, "SELL": 1, "HOLD": 2}[r["action"]]

    sorted_results = sorted(results, key=action_order)

    for r in sorted_results:
        action = r["action"]
        card_css = {"BUY": "pf-card pf-card-buy", "SELL": "pf-card pf-card-sell", "HOLD": "pf-card pf-card-hold"}[action]
        badge    = {"BUY": "badge-buy", "SELL": "badge-sell", "HOLD": "badge-hold"}[action]
        label    = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[action]
        arrow    = "▲" if r["chg_pct"] >= 0 else "▼"
        chg_color = "#22c55e" if r["chg_pct"] >= 0 else "#ef4444"
        trend_color = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Smíšený": "#888"}[r["ema_trend"]]
        rsi_color = "#22c55e" if r["rsi"] < 35 else "#ef4444" if r["rsi"] > 65 else "#94a3b8"

        score, score_label = _score_label(r["buy_n"], r["sell_n"], action)
        score_html = _score_bar_html(score)

        reasons = (r["buy_reasons"] if action == "BUY" else r["sell_reasons"] if action == "SELL" else [])[:3]
        reason_color = "#86efac" if action == "BUY" else "#fca5a5"
        reasons_html = ""
        if reasons:
            reasons_html = (
                f'<div class="pf-reasons">'
                + " &nbsp;·&nbsp; ".join(f'<span style="color:{reason_color}">{s}</span>' for s in reasons)
                + '</div>'
            )

        st.markdown(f"""
<a href="?page=1&ticker={r['ticker']}" target="_self" style="text-decoration:none;color:inherit;display:block">
<div class="{card_css}" style="cursor:pointer">
  <div class="pf-left">
    <span class="{badge}">{label}</span>
    <div style="margin-top:2px">{score_html}</div>
  </div>
  <div class="pf-name">
    {r['name']} <span style="color:#555;font-size:0.78rem;font-weight:400">{r['ticker']}</span>
  </div>
  <div class="pf-meta">
    <span class="pf-pill" style="color:{rsi_color}">RSI {r['rsi']:.0f}</span>
    <span class="pf-pill" style="color:{trend_color}">{r['ema_trend']}</span>
    <span class="pf-pill" style="color:#94a3b8">{r['sector']}</span>
  </div>
  <div class="pf-price-block">
    <div class="pf-price">{r['price']:.2f} <span style="font-size:0.75rem;color:#666">{r['currency']}</span></div>
    <div class="pf-change" style="color:{chg_color}">{arrow} {r['chg_pct']:+.1f}%</div>
  </div>
  {reasons_html}
</div>
</a>
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
    st.plotly_chart(fig_rsi, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

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
    st.plotly_chart(fig_chg, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

    st.divider()
    with st.expander("Top příležitosti z Radaru (rozbal)"):
        st.caption("Akcie mimo tvoje portfolio se silným signálem.")
        with st.spinner("Skenuji radar..."):
            _radar_results = scan_stocks(RADAR_STOCKS, period)
        _top = [r for r in _radar_results if r["action"] == "BUY" or (r["action"] == "SELL" and r["ticker"] in PORTFOLIO_TICKERS)]
        _top = sorted(_top, key=lambda x: -x["strength"])[:5]
        if _top:
            for r in _top:
                _render_radar_card(r)
        else:
            st.info("Žádné silné signály v radaru momentálně.")


# ═════════════════════════════════════════════════════════════════════════════
# STRANA 2 – Detail akcie
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Detail akcie":
    ticker   = detail_ticker
    currency = detail_currency

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

        # ── Multi-horizont souhrnná karta ────────────────────────────────────────
        _HINT_LABEL = {"koupit": "KOUPIT", "prodat": "PRODAT", "čekat": "ČEKAT", "sledovat": "SLEDOVAT"}
        _HINT_COLOR = {"koupit": "#22c55e", "prodat": "#ef4444", "čekat": "#f59e0b", "sledovat": "#60a5fa"}
        _ai_prov = _claude.get("provider", "AI") if _claude.get("ok") else ""

        def _horizon_badge(key: str, title: str, subtitle: str = "") -> str:
            """HTML badge pro jeden horizont v horním řádku."""
            h = _claude.get(key, {}) if _claude.get("ok") else {}
            hint = h.get("action_hint", "")
            conf = h.get("confidence", "")
            sig  = _mh.get(key)
            tech_action = (sig or {}).get("action", "HOLD") if not hint else ""
            # Fallback na tech signál pokud AI nedostupná
            if not hint:
                hint = {"BUY": "koupit", "SELL": "prodat", "HOLD": "čekat"}.get(tech_action, "čekat")
            clr = _HINT_COLOR.get(hint, "#94a3b8")
            lbl = _HINT_LABEL.get(hint, hint.upper())
            conf_html = f'<div style="color:#64748b;font-size:0.68rem;margin-top:2px">{conf}</div>' if conf else ""
            sub_html = f'<div style="color:#475569;font-size:0.62rem;line-height:1.2">{subtitle}</div>' if subtitle else ""
            return (
                f'<div style="background:{clr}18;border:2px solid {clr};border-radius:10px;'
                f'padding:10px 8px;text-align:center">'
                f'<div style="color:#94a3b8;font-size:0.68rem;line-height:1.3;margin-bottom:4px">'
                f'{title}{sub_html}</div>'
                f'<div style="color:{clr};font-size:1.15rem;font-weight:800">{lbl}</div>'
                f'{conf_html}</div>'
            )

        st.markdown(f"""
    <style>
    .horizon-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-bottom: 12px;
    }}
    </style>
    <div class="horizon-grid">
      {_horizon_badge("short",  "Krátkodobý", "< 3 měs.")}
      {_horizon_badge("medium", "Střednědobý", "6m – 2 roky")}
      {_horizon_badge("long",   "Dlouhodobý",  "3+ roky")}
    </div>
    """, unsafe_allow_html=True)

        # Přepínač detailu horizontu
        _sel_hz = st.segmented_control(
            "Detail horizontu",
            ["Krátkodobý", "Střednědobý", "Dlouhodobý"],
            default="Krátkodobý",
            key=f"hz_detail_{ticker}",
        )
        _hz_key = {"Krátkodobý": "short", "Střednědobý": "medium", "Dlouhodobý": "long"}.get(_sel_hz or "Krátkodobý", "short")
        _hz_sig = _mh.get(_hz_key) or signals  # fallback na 6mo signály

        _hz_data = _claude.get(_hz_key, {}) if _claude.get("ok") else {}
        _hz_summ = _hz_data.get("summary", "")
        _hz_hint = _hz_data.get("action_hint", "")
        _hz_conf = _hz_data.get("confidence", "")
        _hz_events = _hz_data.get("events", [])
        _hz_risks  = _hz_data.get("risk_factors", [])
        _hz_opp    = _hz_data.get("opportunity", "")

        # Technické hodnoty z vybraného horizontu
        _trend = ("Bullish" if _hz_sig["ema20"] > _hz_sig["ema50"] > _hz_sig["ema200"]
                  else "Bearish" if _hz_sig["ema20"] < _hz_sig["ema50"] < _hz_sig["ema200"]
                  else "Smíšený")
        _rsi   = _hz_sig["rsi"]
        _rsi_lbl = "Oversold" if _rsi < 30 else ("Overbought" if _rsi > 70 else "Neutrální")
        _rsi_c   = "#22c55e" if _rsi < 30 else ("#ef4444" if _rsi > 70 else "#94a3b8")
        _trend_c = "#22c55e" if _trend == "Bullish" else ("#ef4444" if _trend == "Bearish" else "#94a3b8")
        _macd_c  = "#22c55e" if _hz_sig["macd"] > _hz_sig["macd_signal"] else "#ef4444"
        _macd_lbl = "Bullish" if _hz_sig["macd"] > _hz_sig["macd_signal"] else "Bearish"
        _sent_c  = "#22c55e" if ai_sent["score"] > 0.15 else ("#ef4444" if ai_sent["score"] < -0.15 else "#94a3b8")
        _sent_lbl = {"positive": "Pozitivní", "negative": "Negativní", "neutral": "Neutrální"}.get(ai_sent.get("dominant","neutral"), "Neutrální")
        _hz_action = _hz_sig.get("action", "HOLD")
        _sig_c   = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#94a3b8"}[_hz_action]
        _sig_lbl = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[_hz_action]

        score, score_label = _score_label(
            len(_hz_sig.get("buy_signals", [])), len(_hz_sig.get("sell_signals", [])), _hz_action
        )
        score_html = _score_bar_html(score)

        _buy_html  = "".join(f'<div style="color:#22c55e;font-size:0.82rem;padding:2px 0">+ {s}</div>' for s in _hz_sig.get("buy_signals", [])) or '<div style="color:#555;font-size:0.82rem">Žádné</div>'
        _sell_html = "".join(f'<div style="color:#ef4444;font-size:0.82rem;padding:2px 0">− {s}</div>' for s in _hz_sig.get("sell_signals", [])) or '<div style="color:#555;font-size:0.82rem">Žádné</div>'
        _hint_c = _HINT_COLOR.get(_hz_hint, "#94a3b8")
        _ai_row = (f'<div style="color:#94a3b8;font-size:0.78rem;margin-top:4px">AI: '
                   f'<span style="color:{_hint_c};font-weight:600;text-transform:uppercase">{_hz_hint}</span>'
                   f' · jistota: {_hz_conf} · <span style="color:#60a5fa">{_ai_prov}</span></div>') if _hz_hint else ""

        st.markdown(f"""
    <style>
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin: 10px 0;
    }}
    @media (max-width: 640px) {{
      .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    .summary-cell {{
      background: #0f172a;
      border-radius: 8px;
      padding: 8px;
      text-align: center;
    }}
    .summary-label {{ color: #64748b; font-size: 0.72rem; }}
    .summary-value {{ font-size: 1.1rem; font-weight: 700; }}
    .summary-sub   {{ color: #64748b; font-size: 0.7rem; }}
    </style>
    <div style="background:#1e293b;border-radius:12px;padding:14px 16px;margin-bottom:12px">
      <!-- Signál + skóre -->
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
        <div style="background:{_sig_c}22;border:2px solid {_sig_c};border-radius:8px;
                    padding:5px 16px;font-size:1.2rem;font-weight:700;color:{_sig_c}">{_sig_lbl}</div>
        <div style="flex:1;min-width:120px">{score_html}
          <div style="color:#94a3b8;font-size:0.78rem;margin-top:2px">{score_label} · {len(_hz_sig.get('buy_signals',[]))} buy / {len(_hz_sig.get('sell_signals',[]))} sell</div>
          {_ai_row}
        </div>
      </div>
      <!-- Metriky 4×2 -->
      <div class="summary-grid">
        <div class="summary-cell">
          <div class="summary-label">RSI (14)</div>
          <div class="summary-value" style="color:{_rsi_c}">{_rsi:.1f}</div>
          <div class="summary-sub">{_rsi_lbl}</div>
        </div>
        <div class="summary-cell">
          <div class="summary-label">EMA Trend</div>
          <div class="summary-value" style="color:{_trend_c}">{_trend}</div>
          <div class="summary-sub">20/50/200</div>
        </div>
        <div class="summary-cell">
          <div class="summary-label">MACD</div>
          <div class="summary-value" style="color:{_macd_c}">{_macd_lbl}</div>
          <div class="summary-sub">{_hz_sig['macd']:.3f}</div>
        </div>
        <div class="summary-cell">
          <div class="summary-label">Sentiment</div>
          <div class="summary-value" style="color:{_sent_c}">{_sent_lbl}</div>
          <div class="summary-sub">{ai_sent['score']:+.2f}</div>
        </div>
      </div>
      <!-- AI shrnutí -->
      {f'<div style="border-top:1px solid #334155;padding-top:10px;margin-top:4px;color:#cbd5e1;font-size:0.85rem"><span style="color:#60a5fa;font-size:0.72rem;font-weight:600">{_ai_prov.upper()} · </span>{_hz_summ}</div>' if _hz_summ else ""}
      <!-- Signály detail -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;border-top:1px solid #334155;padding-top:10px">
        <div><div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">BUY signály</div>{_buy_html}</div>
        <div><div style="color:#64748b;font-size:0.72rem;margin-bottom:4px">SELL signály</div>{_sell_html}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # Indikátory
        st.subheader("Technické indikátory")

        rsi_v  = signals["rsi"]
        bb_pos = (price_now - signals["bb_lower"]) / max(signals["bb_upper"] - signals["bb_lower"], 0.01) * 100
        trend  = ("Bullish" if signals["ema20"] > signals["ema50"] > signals["ema200"]
                  else "Bearish" if signals["ema20"] < signals["ema50"] < signals["ema200"]
                  else "Smíšený")
        rsi_delta  = "Oversold – levná" if rsi_v < 30 else ("Overbought – drahá" if rsi_v > 70 else "Neutrální")
        bb_delta   = "Blízko dna" if bb_pos < 20 else ("Blízko vrcholu" if bb_pos > 80 else "Střed pásma")
        stoch_delta = "Oversold" if signals["stoch_k"] < 20 else ("Overbought" if signals["stoch_k"] > 80 else "Neutrální")
        rsi_color  = "#22c55e" if rsi_v < 30 else ("#ef4444" if rsi_v > 70 else "#94a3b8")
        bb_color   = "#22c55e" if bb_pos < 20 else ("#ef4444" if bb_pos > 80 else "#94a3b8")
        stoch_color = "#22c55e" if signals["stoch_k"] < 20 else ("#ef4444" if signals["stoch_k"] > 80 else "#94a3b8")
        trend_color = "#22c55e" if trend == "Bullish" else ("#ef4444" if trend == "Bearish" else "#94a3b8")
        macd_color  = "#22c55e" if signals["macd"] > signals["macd_signal"] else "#ef4444"

        st.markdown(f"""
    <div class="indicator-grid">
      <div class="indicator-card" title="RSI (Relative Strength Index) měří přeprodanost/překoupenost. Pod 30 = levná → BUY. Nad 70 = drahá → SELL.">
        <div class="indicator-label">RSI (14)</div>
        <div class="indicator-value" style="color:{rsi_color}">{rsi_v:.1f}</div>
        <div class="indicator-delta">{rsi_delta}</div>
      </div>
      <div class="indicator-card" title="MACD porovnává EMA 12 a EMA 26. Křížení signal linky nahoru = BUY, dolů = SELL.">
        <div class="indicator-label">MACD</div>
        <div class="indicator-value" style="color:{macd_color}">{signals['macd']:.3f}</div>
        <div class="indicator-delta">Signal: {signals['macd_signal']:.3f}</div>
      </div>
      <div class="indicator-card" title="Pozice ceny v Bollinger Bands. 0% = spodní pásmo (levná), 100% = horní pásmo (drahá).">
        <div class="indicator-label">Bollinger Bands</div>
        <div class="indicator-value" style="color:{bb_color}">{bb_pos:.0f}%</div>
        <div class="indicator-delta">{bb_delta}</div>
      </div>
      <div class="indicator-card" title="Stochastic porovnává cenu s cenovým rozsahem 14 dní. Pod 20 = přeprodaná, nad 80 = překoupená.">
        <div class="indicator-label">Stochastic K/D</div>
        <div class="indicator-value" style="color:{stoch_color}">{signals['stoch_k']:.0f} / {signals['stoch_d']:.0f}</div>
        <div class="indicator-delta">{stoch_delta}</div>
      </div>
      <div class="indicator-card" title="EMA trend: Bullish = EMA20 > EMA50 > EMA200. Bearish = opačně. Golden Cross = EMA20 překříží EMA50 nahoru.">
        <div class="indicator-label">Trend (EMA)</div>
        <div class="indicator-value" style="color:{trend_color}">{trend}</div>
        <div class="indicator-delta">EMA50: {signals['ema50']:.1f}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

        # Rozbalovací legenda pro méně zkušené uživatele
        with st.expander("Co znamenají tyto indikátory?"):
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
    | **AI Sentiment** | Tón zpráv (FinBERT model) | Převažují pozitivní zprávy | Převažují negativní zprávy |

    **Bullish** = rostoucí trend, **Bearish** = klesající trend, **Oversold** = přeprodaná (levná), **Overbought** = překoupená (drahá).

    > Žádný indikátor není 100% spolehlivý. Vždy kombinuj s vlastním úsudkem a zprávami.
            """)

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # Graf (skrytý by default)
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

        st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

        # Zprávy & AI Sentiment (skryté by default)
        with st.expander("Zprávy & AI Sentiment", expanded=False):
            if news:
                source_label = "FinBERT AI" if ai_sent.get("source") == "FinBERT" else "Klíčová slova"
                n1, n2, n3, n4 = st.columns(4)
                n1.metric("Pozitivní zprávy", ai_sent["positive"])
                n2.metric("Negativní zprávy", ai_sent["negative"])
                n3.metric("Neutrální",        ai_sent["neutral"])
                dom = ai_sent["dominant"]
                dom_label = {"positive": "Pozitivní", "negative": "Negativní", "neutral": "Neutrální"}[dom]
                n4.metric(
                    "AI Sentiment", dom_label,
                    f"Skóre: {ai_sent['score']:+.2f} ({source_label})",
                    help="Skóre -1 = velmi negativní, 0 = neutrální, +1 = velmi pozitivní."
                )
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
                _ev_html = "".join(
                    f'<div style="background:#0c2a4a;border-left:3px solid #60a5fa;border-radius:4px;'
                    f'padding:8px 12px;margin:4px 0;font-size:0.85rem;color:#cbd5e1">📌 {ev}</div>'
                    for ev in _hz_events
                )
                _ri_html = "".join(
                    f'<div style="background:#2a1a0a;border-left:3px solid #f59e0b;border-radius:4px;'
                    f'padding:8px 12px;margin:4px 0;font-size:0.85rem;color:#cbd5e1">⚠️ {ri}</div>'
                    for ri in _hz_risks
                )
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px">'
                    f'<div><div style="color:#94a3b8;font-size:0.75rem;font-weight:600;margin-bottom:4px">KLÍČOVÉ UDÁLOSTI</div>{_ev_html}</div>'
                    f'<div><div style="color:#94a3b8;font-size:0.75rem;font-weight:600;margin-bottom:4px">RIZIKOVÉ FAKTORY</div>{_ri_html}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
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
    tab_radar, tab_makro, tab_korelace = st.tabs([
        "Radar příležitostí",
        "Sektory & Makro",
        "Korelace portfolia",
    ])

    # ── Tab: Radar příležitostí ───────────────────────────────────────────────
    with tab_radar:
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

        # ── Načtení sektorové výkonnosti ─────────────────────────────────────
        with st.spinner("Načítám sektorová data..."):
            sector_perf_raw = fetch_sectors(period)
        sector_perf = {s["name"]: s["chg_period"] for s in sector_perf_raw}

        filtered_radar = {
            name: val for name, val in RADAR_STOCKS.items()
            if not selected_sectors or val[2] in selected_sectors
        }

        # ── Sektorový přehled – kompaktní flex grid ───────────────────────────
        st.subheader("Výkon sektorů (kontext pro signály)")
        sector_items = "".join(
            f'<div style="background:#1a1a2e;border-radius:8px;padding:6px 10px;'
            f'display:flex;justify-content:space-between;align-items:center;gap:8px;min-width:0">'
            f'<span style="font-size:0.78rem;color:#94a3b8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{s["name"]}</span>'
            f'<span style="font-size:0.9rem;font-weight:700;white-space:nowrap;color:{"#22c55e" if s["chg_period"] >= 0 else "#ef4444"}">'
            f'{s["chg_period"]:+.1f}%</span>'
            f'</div>'
            for s in sector_perf_raw
        )
        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:6px;margin-bottom:8px">'
            f'{sector_items}</div>',
            unsafe_allow_html=True,
        )

        st.divider()

        # ── Scan akcií ────────────────────────────────────────────────────────
        with st.spinner(f"Skenuji {len(filtered_radar)} akcií..."):
            results = scan_stocks(filtered_radar, period)

        # Přidej sektorový kontext ke každému výsledku
        for r in results:
            r["sector_chg"] = sector_perf.get(r["sector"], None)

        # SELL signály zobrazujeme jen pro akcie v portfoliu – pro ostatní nemají smysl
        strong = [
            r for r in results
            if r["action"] == "BUY"
            or (r["action"] == "SELL" and r["ticker"] in PORTFOLIO_TICKERS)
        ]
        hold   = [r for r in results if r not in strong]

        # ── Double confirmation – silný sektor + BUY signál ───────────────────
        double_conf = [
            r for r in strong
            if r["action"] == "BUY"
            and r.get("sector_chg") is not None
            and r["sector_chg"] > 1.0
        ]

        if double_conf:
            st.subheader(f"Double confirmation – silný sektor + BUY signál")
            st.caption("Tyto akcie mají BUY signál A zároveň jejich sektor roste nad 1% — nejsilnější příležitosti.")
            for r in sorted(double_conf, key=lambda x: -(x["strength"] + (x["sector_chg"] or 0) / 20)):
                _render_radar_card(r, highlight=True)
            st.divider()

        # ── Ostatní silné signály ─────────────────────────────────────────────
        other_strong = [r for r in strong if r not in double_conf]
        if other_strong:
            st.subheader("Ostatní signály")
            for r in sorted(other_strong, key=lambda x: -x["strength"]):
                _render_radar_card(r, highlight=False)
        elif not double_conf:
            st.info("Žádné silné signály. Trh je momentálně v klidném pásmu — čekej na příležitost.")

        # ── Přehled podle sektoru – co sledovat ──────────────────────────────
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
            sell_in = sum(1 for r in stocks_in_sector if r["action"] == "SELL" and r["ticker"] in PORTFOLIO_TICKERS)

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
                    # SELL skrýt pro akcie mimo portfolio
                    display_action = r["action"] if (r["action"] != "SELL" or r["ticker"] in PORTFOLIO_TICKERS) else "HOLD"
                    badge_css = {"BUY": "badge-buy", "SELL": "badge-sell", "HOLD": "badge-hold"}[display_action]
                    badge_lbl = {"BUY": "KOUPIT", "SELL": "PRODAT", "HOLD": "DRŽET"}[display_action]
                    card_css  = {"BUY": "card-buy", "SELL": "card-sell", "HOLD": "card-hold"}[display_action]
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

    # ── Tab: Sektory & Makro ──────────────────────────────────────────────────
    with tab_makro:
        # ── Sektorový přehled (původní strana 8) ─────────────────────────────
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
            st.plotly_chart(fig_sec, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

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
            sector_perf_tab = {s["name"]: s["chg_period"] for s in sectors}

            for sector_name, stocks in portfolio_sectors.items():
                perf = sector_perf_tab.get(sector_name)
                if perf is None:
                    continue
                color = "#22c55e" if perf >= 0 else "#ef4444"
                stocks_str = ", ".join(stocks)
                st.markdown(
                    f'**{sector_name}** ({sp_label}: <span style="color:{color}">{perf:+.1f}%</span>) '
                    f'– ovlivňuje: {stocks_str}',
                    unsafe_allow_html=True,
                )

        st.divider()

        # ── Makro & Sentiment (původní strana 4) ─────────────────────────────
        st.title("Makro & Sentiment")
        st.caption("Globální tržní kontext – Index strachu a chamtivosti, VIX, dluhopisy, komodity.")

        with st.expander("Co jsou tyto indikátory a proč jsou důležité?"):
            st.markdown("""
**Index strachu a chamtivosti** (0–100) – měří celkovou náladu na americkém trhu.
Historicky platí: *když ostatní se bojí, je čas kupovat; když jsou chamtiví, je čas prodávat.*
- 0–25 = Extrémní strach → trh v panice, akcie levné
- 26–45 = Strach → pesimismus, opatrný optimismus
- 46–55 = Neutrální → nejasná nálada
- 56–75 = Chamtivost → optimismus, možné předražení
- 76–100 = Extrémní chamtivost → euforie, vysoké riziko korekce

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
            st.subheader("Index strachu a chamtivosti")
            with st.spinner("Načítám data..."):
                fg = fetch_fear_greed()

            if fg.get("ok") and fg.get("score") is not None:
                score = fg["score"]
                label, color = fg_label(score)

                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=score,
                    title={"text": label, "font": {"size": 18}},
                    number={"font": {"size": 42}},
                    gauge={
                        "axis": {"range": [0, 100], "tickvals": [0, 25, 45, 55, 75, 100],
                                 "ticktext": ["0", "25", "45", "55", "75", "100"]},
                        "bar":  {"color": color, "thickness": 0.25},
                        "steps": [
                            {"range": [0,  25], "color": "#7f1d1d"},
                            {"range": [25, 45], "color": "#9a3412"},
                            {"range": [45, 55], "color": "#713f12"},
                            {"range": [55, 75], "color": "#365314"},
                            {"range": [75,100], "color": "#14532d"},
                        ],
                        "threshold": {"line": {"color": "white", "width": 3},
                                      "thickness": 0.85, "value": score},
                    },
                ))
                fig_gauge.update_layout(
                    height=260, template="plotly_dark",
                    margin=dict(l=20, r=20, t=50, b=10),
                )
                st.plotly_chart(fig_gauge, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})

                m1, m2 = st.columns(2)
                if fg.get("prev_week"):
                    diff_w = score - fg["prev_week"]
                    m1.metric("Před týdnem", f"{fg['prev_week']:.0f}", f"{diff_w:+.1f}")
                if fg.get("prev_month"):
                    diff_m = score - fg["prev_month"]
                    m2.metric("Před měsícem", f"{fg['prev_month']:.0f}", f"{diff_m:+.1f}")

                if score <= 25:
                    st.error("Extrémní strach – trh v panice. Historicky dobrá příležitost pro long-term investory.")
                elif score <= 45:
                    st.warning("Strach – pesimismus převládá. Opatrný optimismus může být opodstatněný.")
                elif score <= 55:
                    st.info("Neutrální – trh neví kam. Čekej na jasný signál.")
                elif score <= 75:
                    st.success("Chamtivost – optimismus na trhu. Pozor na předražení.")
                else:
                    st.error("Extrémní chamtivost – euforie! Zvažuj výběr zisku.")
            else:
                st.warning("Index strachu a chamtivosti se nepodařilo načíst.")

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
# STRANA 5 – Deník obchodů
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Deník obchodů":
    import json as _json
    st.title("Deník obchodů")
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
    if _using_pg:
        st.success("Úložiště: **PostgreSQL** (data přežijí restarty)", icon="🗄️")
    elif _using_sheets:
        st.success("Úložiště: **Google Sheets** (data přežijí restarty)", icon="📊")
    else:
        st.warning(
            "Úložiště: **lokální SQLite** — data se smažou při restartu Streamlit Cloud. "
            "Pro trvalé uložení nastav `DATABASE_URL` v Secrets (Supabase / Neon zdarma).",
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

        with st.form("trade_form"):
            action_j = st.radio(
                "Typ obchodu",
                ["🟢  Koupil jsem", "🔴  Prodal jsem"],
                horizontal=True,
                label_visibility="collapsed",
            )
            action_j = "BUY" if action_j.startswith("🟢") else "SELL"

            jc1, jc2 = st.columns(2)
            with jc1:
                price_j = st.number_input(
                    f"Cena za akcii ({j_currency})",
                    min_value=0.01,
                    value=round(_fetched_price, 2) if _fetched_price else 1.0,
                    step=0.01,
                    help="Předvyplněno automaticky — uprav pokud byla tvá reálná cena jiná.",
                )
            with jc2:
                shares_j = st.number_input(
                    "Počet akcií",
                    min_value=0.001,
                    value=1.0,
                    step=0.001,
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
                "✅  Uložit obchod",
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
            st.success(f"{lbl}: {shares_j:g} × {j_ticker} @ {price_j:.2f} {j_currency} = {total_preview:,.2f} {j_currency} ({trade_date_j.strftime('%d.%m.%Y')})")
            st.rerun()

        st.divider()
        st.subheader("Import / Export")
        col_imp, col_exp = st.columns(2)
        with col_imp:
            uploaded = st.file_uploader("Importuj zálohu (CSV)", type="csv", label_visibility="collapsed")
            if uploaded:
                try:
                    n = import_from_csv(uploaded.read())
                    st.success(f"Importováno {n} obchodů.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Chyba importu: {e}")
        with col_exp:
            df_exp = get_trades()
            if not df_exp.empty:
                csv_bytes = df_exp.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Stáhnout zálohu (CSV)",
                    data=csv_bytes,
                    file_name=f"trades_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # ── Tab 2: Historie ───────────────────────────────────────────────────────
    with tab_history:
        st.subheader("Historie obchodů")
        df_raw = get_trades()
        if df_raw.empty:
            st.info("Zatím žádné záznamy. Přidej první obchod v záložce 'Přidat obchod'.")
        else:
            with st.spinner("Načítám aktuální ceny..."):
                df_perf = get_performance(df_raw)

            for _, row in df_perf.iterrows():
                action_r = row["Akce"]
                pnl      = row["P&L %"]
                card_css = "card-buy" if action_r == "BUY" else "card-sell"
                badge_css= "badge-buy" if action_r == "BUY" else "badge-sell"
                badge_lbl= "KOUPENO"  if action_r == "BUY" else "PRODÁNO"

                pnl_html = ""
                if pnl is not None:
                    pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
                    pnl_abs   = row["P&L Kč/USD"]
                    pnl_html  = (
                        f' &nbsp;|&nbsp; P&L: '
                        f'<span style="color:{pnl_color};font-weight:700">'
                        f'{pnl:+.1f}% ({pnl_abs:+.0f})</span>'
                    )

                cur_html = f" → aktuálně {row['Aktuální']:.2f}" if row["Aktuální"] else ""
                note_html = f'<br><small style="color:#888">{row["Poznámka"]}</small>' if row["Poznámka"] else ""
                reasons_html = f'<br><small style="color:#aaa">{row["Důvody"]}</small>' if row["Důvody"] else ""

                c_left, c_del = st.columns([10, 1])
                with c_left:
                    st.markdown(
                        f'<div class="{card_css}" style="margin:4px 0">'
                        f'<span class="{badge_css}">{badge_lbl}</span> &nbsp;'
                        f'<strong>{row["Název"]}</strong> '
                        f'<span style="color:#888;font-size:0.82rem">{row["Ticker"]}</span>'
                        f' &nbsp; vstup: <b>{row["Vstup"]:.2f}</b> × {row["Počet"]:.3g}'
                        f' = <b>{row["Investováno"]:.0f}</b>'
                        f'{cur_html}{pnl_html}'
                        f'<br><small style="color:#666">{row["Datum"]}</small>'
                        f'{note_html}{reasons_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with c_del:
                    if st.button("🗑", key=f"del_{row['id']}", help="Smazat záznam"):
                        delete_trade(int(row["id"]))
                        st.rerun()

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
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Celkem obchodů",   stats.get("total_trades", 0))
                s2.metric("Otevřené pozice",  stats.get("open_positions", 0))
                win_rate = stats.get("win_rate", 0)
                s3.metric("Win rate", f"{win_rate:.0f}%",
                          "Nad 50% = signály fungují" if win_rate >= 50 else "Pod 50% = signály zatím netáhnou")
                total_pnl = stats.get("total_pnl_abs", 0)
                total_pct = stats.get("total_pnl_pct", 0)
                s4.metric("Celkový P&L",
                          f"{total_pnl:+.0f}",
                          f"{total_pct:+.1f}% z investovaného")

                st.divider()
                b1, b2, b3 = st.columns(3)
                b1.metric("Nejlepší obchod", f"{stats.get('best_trade', 0):+.1f}%")
                b2.metric("Nejhorší obchod", f"{stats.get('worst_trade', 0):+.1f}%")
                b3.metric("Průměrný P&L",    f"{stats.get('avg_pnl', 0):+.1f}%")

                # Graf P&L jednotlivých obchodů
                open_pos = df_perf_s[df_perf_s["Status"] == "Otevřená"].dropna(subset=["P&L %"])
                if not open_pos.empty:
                    st.divider()
                    st.subheader("P&L otevřených pozic")
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
