"""
Backtest signálového systému – jak dobře fungovaly BUY/SELL signály historicky.
"""
import pandas as pd
import numpy as np
import yfinance as yf
from indicators import generate_signals


def _rolling_signals(df: pd.DataFrame, min_history: int = 60) -> pd.DataFrame:
    """
    Pro každý den spočítá signál na základě dat dostupných do toho dne.
    Vrátí DataFrame s sloupci: date, action, close, buy_n, sell_n
    """
    records = []
    closes = df["Close"]
    n = len(df)

    for i in range(min_history, n):
        window = df.iloc[:i + 1]
        try:
            sig = generate_signals(window)
        except Exception:
            continue
        records.append({
            "date":   df.index[i],
            "action": sig["action"],
            "close":  float(closes.iloc[i]),
            "buy_n":  len(sig["buy_signals"]),
            "sell_n": len(sig["sell_signals"]),
            "strength": sig["strength"],
        })

    return pd.DataFrame(records)


def run_backtest(ticker: str, period: str = "2y", forward_days: list[int] = None) -> dict:
    """
    Spustí backtest pro jeden ticker.
    Vrátí statistiky výsledků BUY a SELL signálů.
    """
    if forward_days is None:
        forward_days = [10, 20, 30]

    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty or len(df) < 80:
        return {"ok": False, "error": "Nedostatek dat"}

    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    closes = df["Close"].values
    dates  = df.index

    signals_df = _rolling_signals(df)
    if signals_df.empty:
        return {"ok": False, "error": "Žádné signály"}

    results = {"ok": True, "ticker": ticker, "period": period}

    for action in ("BUY", "SELL"):
        action_signals = signals_df[signals_df["action"] == action].copy()
        if action_signals.empty:
            results[action] = {"count": 0}
            continue

        # Deduplikuj – beri první den každého signálového clusteru
        # (ignoruj po sobě jdoucí dny se stejným signálem)
        action_signals = action_signals.reset_index(drop=True)
        keep = [0]
        for idx in range(1, len(action_signals)):
            prev_date = action_signals.loc[keep[-1], "date"]
            curr_date = action_signals.loc[idx, "date"]
            if (curr_date - prev_date).days >= 5:
                keep.append(idx)
        action_signals = action_signals.loc[keep].reset_index(drop=True)

        stats = {"count": len(action_signals), "trades": []}

        for _, row in action_signals.iterrows():
            signal_date = row["date"]
            entry_price = row["close"]

            # Najdi forward returns
            future_idx = (dates > signal_date)
            future_closes = closes[future_idx]
            trade = {"date": signal_date.strftime("%Y-%m-%d"), "entry": entry_price}

            for fd in forward_days:
                if len(future_closes) >= fd:
                    exit_price = float(future_closes[fd - 1])
                    ret = (exit_price - entry_price) / entry_price * 100
                    if action == "SELL":
                        ret = -ret  # SELL = profitujeme z poklesu
                    trade[f"ret_{fd}d"] = round(ret, 2)

            stats["trades"].append(trade)

        # Souhrnné statistiky
        for fd in forward_days:
            key = f"ret_{fd}d"
            rets = [t[key] for t in stats["trades"] if key in t]
            if rets:
                wins = [r for r in rets if r > 0]
                stats[f"win_rate_{fd}d"]    = round(len(wins) / len(rets) * 100, 1)
                stats[f"avg_return_{fd}d"]  = round(float(np.mean(rets)), 2)
                stats[f"best_{fd}d"]        = round(float(max(rets)), 2)
                stats[f"worst_{fd}d"]       = round(float(min(rets)), 2)
                stats[f"median_{fd}d"]      = round(float(np.median(rets)), 2)

        results[action] = stats

    return results


def backtest_summary_table(result: dict) -> pd.DataFrame:
    """Přehledná tabulka výsledků backtestu."""
    rows = []
    for action in ("BUY", "SELL"):
        data = result.get(action, {})
        if data.get("count", 0) == 0:
            continue
        for fd in [10, 20, 30]:
            key = f"ret_{fd}d"
            if f"win_rate_{fd}d" not in data:
                continue
            rows.append({
                "Signál":         action,
                "Horizon":        f"{fd} dní",
                "Počet obchodů":  data["count"],
                "Win rate":       f"{data[f'win_rate_{fd}d']}%",
                "Průměrný výnos": f"{data[f'avg_return_{fd}d']:+.1f}%",
                "Medián":         f"{data[f'median_{fd}d']:+.1f}%",
                "Nejlepší":       f"{data[f'best_{fd}d']:+.1f}%",
                "Nejhorší":       f"{data[f'worst_{fd}d']:+.1f}%",
            })
    return pd.DataFrame(rows)
