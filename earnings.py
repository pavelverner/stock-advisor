"""
Earnings kalendář – příští výsledky pro sledované akcie.
"""
import yfinance as yf
from datetime import date


def get_earnings(ticker: str) -> dict:
    """Vrátí datum příštích earnings a odhady EPS."""
    try:
        t = yf.Ticker(ticker)
        today = date.today()
        earnings_date = None

        # Metoda 1: earnings_dates DataFrame (yfinance 0.2.x)
        try:
            ed_df = t.earnings_dates
            if ed_df is not None and not ed_df.empty:
                # Index je DatetimeTZDtype – převeď na date
                future = [
                    idx.date() for idx in ed_df.index
                    if hasattr(idx, "date") and idx.date() >= today
                ]
                if future:
                    earnings_date = min(future)
        except Exception:
            pass

        # Metoda 2: calendar dict (starší yfinance)
        if earnings_date is None:
            try:
                cal = t.calendar
                if isinstance(cal, dict):
                    for key in ("Earnings Date", "earningsDate", "Earnings Call Date"):
                        val = cal.get(key)
                        if val is not None:
                            if isinstance(val, (list, tuple)) and len(val) > 0:
                                val = val[0]
                            if hasattr(val, "date"):
                                val = val.date()
                            elif hasattr(val, "to_pydatetime"):
                                val = val.to_pydatetime().date()
                            if isinstance(val, date):
                                earnings_date = val
                            break
            except Exception:
                pass

        if earnings_date is None:
            return {}

        days_until = (earnings_date - today).days
        result = {
            "earnings_date": earnings_date,
            "days_until":    days_until,
            "is_soon":       0 <= days_until <= 14,
            "is_past":       days_until < 0,
        }

        # EPS odhady
        try:
            info = t.info
            result["eps_estimate"]     = info.get("epsForward") or info.get("epsCurrentYear")
            result["revenue_estimate"] = info.get("revenueForward")
        except Exception:
            pass

        return result

    except Exception:
        return {}


def get_portfolio_earnings(portfolio: dict) -> list[dict]:
    """Vrátí earnings pro celé portfolio, seřazené podle blízkosti."""
    results = []
    for name, (ticker, currency, sector) in portfolio.items():
        try:
            data = get_earnings(ticker)
            if not data:
                continue
            entry = {"name": name, "ticker": ticker, "currency": currency}
            entry.update(data)
            results.append(entry)
        except Exception:
            pass

    def sort_key(x):
        d = x.get("days_until")
        if d is None:
            return 9999
        if d < 0:
            return 9999 + abs(d)
        return d

    return sorted(results, key=sort_key)
