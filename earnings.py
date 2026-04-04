"""
Earnings kalendář – příští výsledky pro sledované akcie.
"""
import yfinance as yf
from datetime import datetime, date, timedelta


def get_earnings(ticker: str) -> dict:
    """Vrátí datum příštích earnings a odhady EPS."""
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        # calendar může být dict nebo DataFrame
        if cal is None:
            return {}
        if hasattr(cal, "to_dict"):
            cal = cal.to_dict()

        result = {}
        # Yahoo vrací různé formáty – zkusíme oba
        earnings_date = None
        if isinstance(cal, dict):
            for key in ("Earnings Date", "earningsDate", "Earnings Call Date"):
                val = cal.get(key)
                if val is not None:
                    if isinstance(val, (list, tuple)) and len(val) > 0:
                        earnings_date = val[0]
                    else:
                        earnings_date = val
                    break

        if earnings_date is None:
            # Zkus přes info
            info = t.fast_info
            ed = getattr(info, "earnings_date", None)
            if ed:
                earnings_date = ed

        if earnings_date is not None:
            if hasattr(earnings_date, "date"):
                earnings_date = earnings_date.date()
            elif hasattr(earnings_date, "to_pydatetime"):
                earnings_date = earnings_date.to_pydatetime().date()
            result["earnings_date"] = earnings_date

            today = date.today()
            if isinstance(earnings_date, date):
                days_until = (earnings_date - today).days
                result["days_until"] = days_until
                result["is_soon"] = 0 <= days_until <= 14
                result["is_past"] = days_until < 0

        # EPS odhady
        try:
            info = t.info
            result["eps_estimate"] = info.get("epsForward") or info.get("epsCurrentYear")
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
            entry = {
                "name":     name,
                "ticker":   ticker,
                "currency": currency,
            }
            entry.update(data)
            results.append(entry)
        except Exception:
            pass

    # Seřaď: nejbližší earnings první, bez data na konec
    def sort_key(x):
        d = x.get("days_until")
        if d is None:
            return 9999
        if d < 0:
            return 9999 + abs(d)
        return d

    return sorted(results, key=sort_key)
