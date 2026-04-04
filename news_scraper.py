import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

NEGATIVE_WORDS = [
    "падение", "снижение",
    "crash", "fall", "drop", "decline", "loss", "bankrupt", "fraud",
    "warning", "risk", "recession", "layoff", "cut", "downgrade",
    "sell", "short", "bear", "weak", "miss", "disappoint",
    "pokles", "ztráta", "propad", "krize", "varování", "snížení",
    "bankrot", "podvod", "riziko",
]

POSITIVE_WORDS = [
    "growth", "rise", "gain", "profit", "beat", "upgrade",
    "buy", "bull", "strong", "surge", "record", "rally",
    "positive", "bullish", "outperform", "expand",
    "růst", "zisk", "nárůst", "rekord", "posílení", "zlepšení",
]


def _parse_entry_date(entry) -> str:
    for field in ("published_parsed", "updated_parsed"):
        val = getattr(entry, field, None)
        if val:
            try:
                dt = datetime(*val[:6], tzinfo=timezone.utc)
                return dt.strftime("%d.%m. %H:%M")
            except Exception:
                pass
    return ""


def _sentiment(text: str) -> str:
    text_lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def fetch_rss(url: str, max_items: int = 8) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            # Odstranit HTML tagy ze summary
            summary = re.sub(r"<[^>]+>", "", summary)[:300]
            date = _parse_entry_date(entry)
            items.append({
                "title": title,
                "link": link,
                "summary": summary,
                "date": date,
                "sentiment": _sentiment(title + " " + summary),
                "source": feed.feed.get("title", url),
            })
        return items
    except Exception:
        return []


def fetch_finviz_news(ticker: str, max_items: int = 10) -> list[dict]:
    """Scraping zpráv z Finviz pro daný ticker."""
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"id": "news-table"})
        if not table:
            return []
        items = []
        current_date = ""
        for row in table.find_all("tr")[:max_items * 2]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            date_cell = cells[0].text.strip()
            # Finviz: datum je buď "Apr-01-26" nebo jen čas "09:30AM"
            if re.match(r"\w{3}-\d{2}-\d{2}", date_cell):
                parts = date_cell.split()
                current_date = parts[0] if parts else ""
                time_str = parts[1] if len(parts) > 1 else ""
            else:
                time_str = date_cell

            a_tag = cells[1].find("a")
            if not a_tag:
                continue
            title = a_tag.text.strip()
            link = a_tag.get("href", "")
            source_span = cells[1].find("span")
            source = source_span.text.strip() if source_span else "Finviz"
            items.append({
                "title": title,
                "link": link,
                "summary": "",
                "date": f"{current_date} {time_str}".strip(),
                "sentiment": _sentiment(title),
                "source": source,
            })
            if len(items) >= max_items:
                break
        return items
    except Exception:
        return []


def fetch_seeking_alpha_rss(ticker: str, max_items: int = 5) -> list[dict]:
    url = f"https://seekingalpha.com/api/sa/combined/{ticker}.xml"
    return fetch_rss(url, max_items)


def fetch_yahoo_rss(ticker: str, max_items: int = 8) -> list[dict]:
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    return fetch_rss(url, max_items)


def fetch_marketwatch_rss(max_items: int = 6) -> list[dict]:
    url = "https://feeds.marketwatch.com/marketwatch/topstories/"
    return fetch_rss(url, max_items)


def get_all_news(ticker: str) -> list[dict]:
    """Agreguje zprávy z více zdrojů, deduplikuje a třídí."""
    all_items: list[dict] = []

    # Yahoo Finance RSS
    all_items.extend(fetch_yahoo_rss(ticker, max_items=8))

    # Finviz scraping
    all_items.extend(fetch_finviz_news(ticker, max_items=10))

    # MarketWatch obecné tržní zprávy
    all_items.extend(fetch_marketwatch_rss(max_items=5))

    # Deduplikace podle titulku
    seen_titles = set()
    unique = []
    for item in all_items:
        key = item["title"].lower()[:60]
        if key not in seen_titles and item["title"]:
            seen_titles.add(key)
            unique.append(item)

    return unique


def news_sentiment_summary(news: list[dict]) -> dict:
    """Souhrnný sentiment ze všech zpráv."""
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for item in news:
        counts[item.get("sentiment", "neutral")] += 1
    total = sum(counts.values()) or 1
    dominant = max(counts, key=counts.get)
    return {
        "positive": counts["positive"],
        "negative": counts["negative"],
        "neutral": counts["neutral"],
        "dominant": dominant,
        "score": (counts["positive"] - counts["negative"]) / total,
    }
