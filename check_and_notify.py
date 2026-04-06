"""
Stock Advisor – GitHub Actions monitoring skript.

Spouští se každou hodinu přes GitHub Actions (viz .github/workflows/monitor.yml).
Zkontroluje signály pro portfolio + radar, pošle HTML email pokud najde BUY/SELL.

Vyžaduje GitHub Secrets:
  EMAIL_FROM     – odesílací Gmail adresa
  EMAIL_PASSWORD – Gmail App Password (ne běžné heslo!)
  EMAIL_TO       – příjemce (může být stejná adresa)
"""
import os
import sys
import smtplib
import yfinance as yf
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from indicators import generate_signals

# ── Sledované akcie ───────────────────────────────────────────────────────────
PORTFOLIO = {
    "NVIDIA":              "NVDA",
    "AMD":                 "AMD",
    "Alphabet":            "GOOGL",
    "Microsoft":           "MSFT",
    "Vanguard S&P500":     "VUSA.L",
    "iShares MSCI World":  "IWDA.AS",
    "Palo Alto":           "PANW",
    "Amazon":              "AMZN",
    "SAAB":                "SAAB-B.ST",
    "Taiwan Semi":         "TSM",
    "Rheinmetall":         "RHM.DE",
}

RADAR = {
    "Meta":        "META",
    "Tesla":       "TSLA",
    "ASML":        "ASML",
    "CrowdStrike": "CRWD",
    "Palantir":    "PLTR",
    "Apple":       "AAPL",
    "Broadcom":    "AVGO",
    "Lockheed":    "LMT",
    "Eli Lilly":   "LLY",
    "JPMorgan":    "JPM",
}

# ── Kontrola signálů ──────────────────────────────────────────────────────────

def check_signals(watch: dict, label: str) -> list[dict]:
    results = []
    for name, ticker in watch.items():
        try:
            df = yf.download(ticker, period="3mo", auto_adjust=True, progress=False)
            if df.empty or len(df) < 30:
                continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            sig   = generate_signals(df)
            price = float(df["Close"].iloc[-1])
            prev  = float(df["Close"].iloc[-2])
            chg   = (price - prev) / prev * 100
            results.append({
                "name":         name,
                "ticker":       ticker,
                "group":        label,
                "price":        price,
                "chg":          chg,
                "action":       sig["action"],
                "strength":     sig["strength"],
                "buy_n":        len(sig["buy_signals"]),
                "sell_n":       len(sig["sell_signals"]),
                "buy_reasons":  sig["buy_signals"],
                "sell_reasons": sig["sell_signals"],
                "rsi":          float(sig["rsi"]),
            })
        except Exception as e:
            print(f"  Chyba {ticker}: {e}")
    return results


# ── HTML email ────────────────────────────────────────────────────────────────

def _signal_rows(items: list[dict], action: str) -> str:
    color  = "#d1fae5" if action == "BUY"  else "#fee2e2"
    border = "#22c55e" if action == "BUY"  else "#ef4444"
    label  = "KOUPIT"  if action == "BUY"  else "PRODAT"
    rows   = ""
    for r in items:
        reasons = r["buy_reasons"] if action == "BUY" else r["sell_reasons"]
        reasons_str = " · ".join(reasons[:3]) if reasons else "—"
        chg_col = "#16a34a" if r["chg"] >= 0 else "#dc2626"
        rows += f"""
        <tr style="border-left:4px solid {border};background:{color}">
          <td style="padding:8px 12px;font-weight:700">{r['name']}<br>
              <span style="font-size:11px;color:#666">{r['ticker']} · {r['group']}</span></td>
          <td style="padding:8px;text-align:center;font-weight:700">{label}</td>
          <td style="padding:8px;text-align:right">{r['price']:.2f}</td>
          <td style="padding:8px;text-align:right;color:{chg_col}">{r['chg']:+.1f}%</td>
          <td style="padding:8px;text-align:center">{r['rsi']:.0f}</td>
          <td style="padding:8px;font-size:12px;color:#555">{reasons_str}</td>
        </tr>"""
    return rows


def build_html(buy_signals: list[dict], sell_signals: list[dict], hold_notable: list[dict]) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    total = len(buy_signals) + len(sell_signals)

    header_color = "#16a34a" if len(buy_signals) > len(sell_signals) else \
                   "#dc2626" if len(sell_signals) > len(buy_signals) else "#475569"

    buy_rows  = _signal_rows(buy_signals,  "BUY")
    sell_rows = _signal_rows(sell_signals, "SELL")

    table_rows = buy_rows + sell_rows

    hold_html = ""
    if hold_notable:
        hold_items = "".join(
            f'<li style="margin:3px 0"><b>{r["name"]}</b> ({r["ticker"]}) – '
            f'RSI {r["rsi"]:.0f}, '
            f'BUY signálů: {r["buy_n"]}, SELL signálů: {r["sell_n"]}</li>'
            for r in hold_notable[:5]
        )
        hold_html = f"""
        <h3 style="color:#475569;margin-top:24px">Sleduj – blízko signálu (HOLD)</h3>
        <ul style="font-size:13px;line-height:1.8">{hold_items}</ul>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:16px;background:#f8fafc">

<div style="background:{header_color};color:white;border-radius:8px;padding:16px 20px;margin-bottom:16px">
  <h2 style="margin:0">📈 Stock Advisor – {total} signál{'y' if 1 < total < 5 else ('ů' if total >= 5 else '')}</h2>
  <p style="margin:4px 0 0;opacity:0.9;font-size:14px">{now} · {len(buy_signals)} KOUPIT · {len(sell_signals)} PRODAT</p>
</div>

<table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">
  <thead>
    <tr style="background:#1e293b;color:white;font-size:13px">
      <th style="padding:10px 12px;text-align:left">Akcie</th>
      <th style="padding:10px;text-align:center">Signál</th>
      <th style="padding:10px;text-align:right">Cena</th>
      <th style="padding:10px;text-align:right">Změna</th>
      <th style="padding:10px;text-align:center">RSI</th>
      <th style="padding:10px;text-align:left">Důvody</th>
    </tr>
  </thead>
  <tbody>{table_rows}</tbody>
</table>

{hold_html}

<p style="font-size:11px;color:#94a3b8;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:12px">
  Tento email byl vygenerován automaticky nástrojem Stock Advisor.<br>
  <b>Upozornění:</b> Jedná se pouze o technickou analýzu, nikoliv o finanční poradenství.
</p>
</body></html>"""


# ── Odeslání emailu ───────────────────────────────────────────────────────────

def send_email(subject: str, html: str):
    from_addr = os.environ.get("EMAIL_FROM", "")
    password  = os.environ.get("EMAIL_PASSWORD", "")
    to_addr   = os.environ.get("EMAIL_TO", "")

    if not all([from_addr, password, to_addr]):
        print("ERROR: Chybí EMAIL_FROM, EMAIL_PASSWORD nebo EMAIL_TO v environment.")
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(from_addr, password)
        s.send_message(msg)
    print(f"Email odeslán na {to_addr}")


# ── Hlavní logika ─────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().strftime('%H:%M')}] Kontroluji signály...")

    all_results = (
        check_signals(PORTFOLIO, "Portfolio") +
        check_signals(RADAR,     "Radar")
    )

    buy_signals  = [r for r in all_results if r["action"] == "BUY"]
    sell_signals = [r for r in all_results if r["action"] == "SELL"]

    # HOLD akcie blízko signálu (2 signály z jedné strany)
    hold_notable = [
        r for r in all_results
        if r["action"] == "HOLD" and (r["buy_n"] >= 2 or r["sell_n"] >= 2)
    ]
    hold_notable.sort(key=lambda x: -max(x["buy_n"], x["sell_n"]))

    total_signals = len(buy_signals) + len(sell_signals)
    print(f"  BUY: {len(buy_signals)}, SELL: {len(sell_signals)}, HOLD blízko: {len(hold_notable)}")

    # Seřaď podle síly
    buy_signals.sort(key=lambda x: -x["strength"])
    sell_signals.sort(key=lambda x: -x["strength"])

    if total_signals == 0 and not os.environ.get("FORCE_SEND"):
        print("Žádné signály – email se neposílá.")
        return

    subject = (
        f"[Stock Advisor] {len(buy_signals)}x KOUPIT · {len(sell_signals)}x PRODAT"
        f" – {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    html = build_html(buy_signals, sell_signals, hold_notable)
    send_email(subject, html)


if __name__ == "__main__":
    main()
