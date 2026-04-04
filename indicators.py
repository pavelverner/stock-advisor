import pandas as pd
import numpy as np


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def compute_emas(series: pd.Series):
    ema20 = series.ewm(span=20, adjust=False).mean()
    ema50 = series.ewm(span=50, adjust=False).mean()
    ema200 = series.ewm(span=200, adjust=False).mean()
    return ema20, ema50, ema200


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def compute_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3):
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def generate_signals(df: pd.DataFrame) -> dict:
    """
    Conservative signal generation — vyžaduje shodu více indikátorů.
    Vrací: signal ('BUY' | 'SELL' | 'HOLD'), score, důvody
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    rsi = compute_rsi(close).iloc[-1]
    macd_line, signal_line, histogram = compute_macd(close)
    macd_val = macd_line.iloc[-1]
    signal_val = signal_line.iloc[-1]
    hist_now = histogram.iloc[-1]
    hist_prev = histogram.iloc[-2] if len(histogram) > 1 else 0

    upper_bb, mid_bb, lower_bb = compute_bollinger(close)
    price = close.iloc[-1]
    bb_upper = upper_bb.iloc[-1]
    bb_lower = lower_bb.iloc[-1]
    bb_mid = mid_bb.iloc[-1]

    ema20, ema50, ema200 = compute_emas(close)
    ema20_val = ema20.iloc[-1]
    ema50_val = ema50.iloc[-1]
    ema200_val = ema200.iloc[-1]

    k, d = compute_stochastic(high, low, close)
    stoch_k = k.iloc[-1]
    stoch_d = d.iloc[-1]

    # Předchozí hodnoty pro detekci crossoverů
    ema20_prev = ema20.iloc[-2] if len(ema20) > 1 else ema20_val
    ema50_prev = ema50.iloc[-2] if len(ema50) > 1 else ema50_val
    macd_prev = macd_line.iloc[-2] if len(macd_line) > 1 else macd_val
    signal_prev = signal_line.iloc[-2] if len(signal_line) > 1 else signal_val

    buy_signals = []
    sell_signals = []

    # --- RSI ---
    if rsi < 30:
        buy_signals.append(f"RSI oversold ({rsi:.1f} < 30)")
    elif rsi < 40:
        buy_signals.append(f"RSI blízko oversold ({rsi:.1f})")
    if rsi > 70:
        sell_signals.append(f"RSI overbought ({rsi:.1f} > 70)")
    elif rsi > 60:
        sell_signals.append(f"RSI blízko overbought ({rsi:.1f})")

    # --- MACD crossover ---
    if macd_prev < signal_prev and macd_val > signal_val:
        buy_signals.append("MACD bullish crossover")
    if macd_prev > signal_prev and macd_val < signal_val:
        sell_signals.append("MACD bearish crossover")

    # --- MACD histogram momentum ---
    if hist_now > 0 and hist_now > hist_prev and hist_prev <= 0:
        buy_signals.append("MACD histogram přechod do kladných hodnot")
    if hist_now < 0 and hist_now < hist_prev and hist_prev >= 0:
        sell_signals.append("MACD histogram přechod do záporných hodnot")

    # --- Bollinger Bands ---
    if price < bb_lower:
        buy_signals.append(f"Cena pod dolním BB pásmem")
    elif price < bb_lower * 1.02:
        buy_signals.append(f"Cena blízko dolního BB pásma")
    if price > bb_upper:
        sell_signals.append(f"Cena nad horním BB pásmem")
    elif price > bb_upper * 0.98:
        sell_signals.append(f"Cena blízko horního BB pásma")

    # --- EMA trend ---
    if ema20_val > ema50_val > ema200_val:
        buy_signals.append("EMA uspořádání: bullish trend (20>50>200)")
    if ema20_val < ema50_val < ema200_val:
        sell_signals.append("EMA uspořádání: bearish trend (20<50<200)")

    # EMA 20/50 crossover
    if ema20_prev < ema50_prev and ema20_val > ema50_val:
        buy_signals.append("EMA 20 překřížila EMA 50 (golden cross)")
    if ema20_prev > ema50_prev and ema20_val < ema50_val:
        sell_signals.append("EMA 20 překřížila EMA 50 dolů (death cross)")

    # --- Stochastic ---
    if stoch_k < 20 and stoch_d < 20:
        buy_signals.append(f"Stochastic oversold (K={stoch_k:.1f}, D={stoch_d:.1f})")
    if stoch_k > 80 and stoch_d > 80:
        sell_signals.append(f"Stochastic overbought (K={stoch_k:.1f}, D={stoch_d:.1f})")

    # --- Skóre a výsledný signál ---
    buy_score = len(buy_signals)
    sell_score = len(sell_signals)

    # Konzervativní práh: min. 3 signály pro akci
    THRESHOLD = 3

    if buy_score >= THRESHOLD and buy_score > sell_score:
        action = "BUY"
        strength = min(buy_score / 5, 1.0)
    elif sell_score >= THRESHOLD and sell_score > buy_score:
        action = "SELL"
        strength = min(sell_score / 5, 1.0)
    else:
        action = "HOLD"
        strength = 0.0

    return {
        "action": action,
        "strength": strength,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "rsi": rsi,
        "macd": macd_val,
        "macd_signal": signal_val,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
        "ema20": ema20_val,
        "ema50": ema50_val,
        "ema200": ema200_val,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
    }
