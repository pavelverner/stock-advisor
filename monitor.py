"""
Stock Monitor – běží na pozadí, sleduje signály a posílá Windows notifikace.

Spuštění:
    python monitor.py

Volitelné argumenty:
    --interval 15       kontrola každých 15 minut (výchozí)
    --threshold 2       min. počet signálů pro notifikaci (výchozí 3)
"""
import argparse
import json
import time
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf

# Přidej aktuální složku do PATH pro import vlastních modulů
sys.path.insert(0, str(Path(__file__).parent))
from indicators import generate_signals

# ── Notifikace (Windows) ──────────────────────────────────────────────────────
try:
    from plyer import notification as _plyer_notif
    NOTIF_BACKEND = "plyer"
except ImportError:
    _plyer_notif = None
    NOTIF_BACKEND = None

try:
    import ctypes
    _MB = ctypes.windll.user32.MessageBoxW  # noqa – jen test importu
    NOTIF_BACKEND = NOTIF_BACKEND or "msgbox"
except Exception:
    pass


def send_notification(title: str, message: str, urgent: bool = False):
    """Pošle Windows desktop notifikaci."""
    print(f"[{_now()}] NOTIFIKACE: {title} – {message}")

    if NOTIF_BACKEND == "plyer" and _plyer_notif:
        try:
            _plyer_notif.notify(
                title=title,
                message=message,
                app_name="Stock Advisor",
                timeout=10,
            )
            return
        except Exception as e:
            print(f"  plyer chyba: {e}")

    # Záloha: Windows Balloon Tip přes PowerShell
    try:
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.Visible = $true; "
            f"$n.ShowBalloonTip(8000, '{_esc(title)}', '{_esc(message)}', "
            "[System.Windows.Forms.ToolTipIcon]::Info); "
            "Start-Sleep -Seconds 9; "
            "$n.Dispose()"
        )
        os.system(f'powershell -WindowStyle Hidden -Command "{ps_script}"')
    except Exception as e:
        print(f"  PowerShell notifikace chyba: {e}")


def _esc(s: str) -> str:
    return s.replace("'", "`'").replace('"', '`"')


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── Sledované akcie ───────────────────────────────────────────────────────────
WATCH_LIST = {
    # Portfolio
    "NVIDIA":               "NVDA",
    "AMD":                  "AMD",
    "Alphabet":             "GOOGL",
    "Microsoft":            "MSFT",
    "Vanguard S&P500":      "VUSA.L",
    "iShares MSCI World":   "IWDA.AS",
    "Palo Alto":            "PANW",
    "Amazon":               "AMZN",
    "SAAB":                 "SAAB-B.ST",
    "Taiwan Semi":          "TSM",
    "Rheinmetall":          "RHM.DE",
    # Radar
    "Meta":                 "META",
    "Tesla":                "TSLA",
    "ASML":                 "ASML",
    "CrowdStrike":          "CRWD",
    "Palantir":             "PLTR",
}

STATE_FILE = Path(__file__).parent / ".monitor_state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_market_likely_open() -> bool:
    """
    Přibližná kontrola: US trh 15:30–22:00 CET (Mo–Fri),
    evropské trhy 9:00–17:30 CET. Stačí být v jednom z oken.
    """
    now = datetime.now()
    if now.weekday() >= 5:  # sobota, neděle
        return False
    h = now.hour + now.minute / 60
    # Evropa 9:00–17:30, USA 15:30–22:00
    return (9.0 <= h <= 17.5) or (15.5 <= h <= 22.0)


def check_signals(threshold: int) -> list[dict]:
    """Načte data a vrátí aktuální signály."""
    results = []
    for name, ticker in WATCH_LIST.items():
        try:
            df = yf.download(ticker, period="3mo", auto_adjust=True, progress=False)
            if df.empty or len(df) < 30:
                continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            sig = generate_signals(df)
            price = float(df["Close"].iloc[-1])
            prev  = float(df["Close"].iloc[-2])
            chg   = (price - prev) / prev * 100
            results.append({
                "name":    name,
                "ticker":  ticker,
                "price":   price,
                "chg":     chg,
                "action":  sig["action"],
                "strength": sig["strength"],
                "buy_n":   len(sig["buy_signals"]),
                "sell_n":  len(sig["sell_signals"]),
                "buy_reasons":  sig["buy_signals"],
                "sell_reasons": sig["sell_signals"],
            })
        except Exception as e:
            print(f"  Chyba {ticker}: {e}")
    return results


def run_monitor(interval_min: int, threshold: int):
    print(f"Stock Monitor spuštěn – kontrola každých {interval_min} min | min. signálů: {threshold}")
    print(f"Sledované akcie: {', '.join(WATCH_LIST.keys())}")
    print("Ctrl+C pro zastavení.\n")

    send_notification(
        "Stock Monitor spuštěn",
        f"Sleduje {len(WATCH_LIST)} akcií, kontrola každých {interval_min} min."
    )

    state = load_state()

    while True:
        ts = _now()
        print(f"[{ts}] Kontrola signálů...")

        results = check_signals(threshold)
        new_state = {}
        alerts = []

        for r in results:
            ticker = r["ticker"]
            action = r["action"]
            prev_action = state.get(ticker, {}).get("action", "HOLD")
            new_state[ticker] = {"action": action, "price": r["price"], "ts": ts}

            # Upozorni jen pokud:
            # 1. Signál se změnil na BUY nebo SELL
            # 2. NEBO signál je BUY/SELL a je silný (strength >= 0.6)
            changed   = (action != prev_action) and action != "HOLD"
            strong    = action != "HOLD" and r["strength"] >= 0.6
            first_run = ticker not in state

            if (changed or strong) and not first_run:
                alerts.append(r)
            elif first_run and action != "HOLD":
                alerts.append(r)

            # Log do konzole
            arrow  = "▲" if r["chg"] >= 0 else "▼"
            marker = f"  *** {action} ***" if action != "HOLD" else ""
            print(
                f"  {r['name']:20s}  {r['price']:8.2f}  {arrow}{r['chg']:+.1f}%"
                f"  RSI:{r.get('rsi', 0) if 'rsi' in r else '?':>5}  {action}{marker}"
            )

        save_state(new_state)

        # Pošli notifikace
        for r in alerts:
            action = r["action"]
            emoji  = {"BUY": "BUY", "SELL": "SELL"}[action]
            reasons = r["buy_reasons"] if action == "BUY" else r["sell_reasons"]
            reason_str = reasons[0] if reasons else ""
            title   = f"{emoji}: {r['name']} ({r['ticker']})"
            message = (
                f"Cena: {r['price']:.2f}  {r['chg']:+.1f}%\n"
                f"Signálů: {r['buy_n'] if action=='BUY' else r['sell_n']}\n"
                f"{reason_str}"
            )
            send_notification(title, message)
            time.sleep(1)  # mezera mezi notifikacemi

        if not alerts:
            print(f"  -> Žádné nové signály.\n")
        else:
            print(f"  -> {len(alerts)} alert(ů) odesláno.\n")

        # Čekej na příští kontrolu
        print(f"[{_now()}] Příští kontrola za {interval_min} min (Ctrl+C = stop)\n")
        time.sleep(interval_min * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock Monitor – real-time notifikace")
    parser.add_argument("--interval", type=int, default=15,
                        help="Interval kontroly v minutách (výchozí: 15)")
    parser.add_argument("--threshold", type=int, default=3,
                        help="Min. počet signálů pro alert (výchozí: 3)")
    args = parser.parse_args()

    try:
        run_monitor(args.interval, args.threshold)
    except KeyboardInterrupt:
        print("\nMonitor zastaven.")
