"""
AI sentiment analýza finančních zpráv pomocí FinBERT.
FinBERT je BERT model specificky trénovaný na finančních textech
(Reuters, Bloomberg, Financial PhraseBank).

Používá HuggingFace Inference API – zdarma, bez stahování modelu.
Volitelně: vlastní HF token pro vyšší rate limit (zdarma na huggingface.co).
"""
import os
import time
import requests
from pathlib import Path

HF_API_URL = "https://api-inference.huggingface.co/models/ProsusAI/finbert"
HF_TOKEN   = os.environ.get("HF_TOKEN", "")  # volitelné, pro vyšší rate limit

# Fallback – jednoduchý keyword sentiment pokud API selže
POSITIVE_WORDS = [
    "beat", "surge", "growth", "profit", "rally", "upgrade", "outperform",
    "record", "bullish", "strong", "expand", "rise", "gain", "buy",
]
NEGATIVE_WORDS = [
    "miss", "crash", "loss", "decline", "downgrade", "warning", "weak",
    "bearish", "cut", "layoff", "bankrupt", "fraud", "risk", "fall", "drop",
]


def _keyword_sentiment(text: str) -> dict:
    t = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if pos > neg:
        return {"label": "positive", "score": 0.6 + min(pos * 0.05, 0.3)}
    if neg > pos:
        return {"label": "negative", "score": 0.6 + min(neg * 0.05, 0.3)}
    return {"label": "neutral", "score": 0.5}


def analyze_headlines(headlines: list[str], batch_size: int = 8) -> list[dict]:
    """
    Analyzuje seznam titulků pomocí FinBERT.
    Vrátí list slovníků: {"label": "positive"|"negative"|"neutral", "score": 0-1}
    """
    if not headlines:
        return []

    headers = {"Content-Type": "application/json"}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    results = []

    # Zpracuj po dávkách
    for i in range(0, len(headlines), batch_size):
        batch = headlines[i : i + batch_size]
        # Zkrať texty na max 512 znaků (limit modelu)
        batch = [h[:512] for h in batch]

        try:
            resp = requests.post(
                HF_API_URL,
                headers=headers,
                json={"inputs": batch},
                timeout=15,
            )

            if resp.status_code == 503:
                # Model se načítá – počkej a zkus znovu
                time.sleep(10)
                resp = requests.post(
                    HF_API_URL, headers=headers,
                    json={"inputs": batch}, timeout=20,
                )

            if resp.status_code == 200:
                data = resp.json()
                # HF vrací list listů: [[{label, score}, ...], ...]
                for item_results in data:
                    if isinstance(item_results, list):
                        # Vezmi label s nejvyšším skóre
                        best = max(item_results, key=lambda x: x["score"])
                        results.append({
                            "label": best["label"].lower(),
                            "score": round(best["score"], 3),
                        })
                    else:
                        results.append({"label": "neutral", "score": 0.5})
            else:
                # API error – použij keyword fallback pro tuto dávku
                for h in batch:
                    results.append(_keyword_sentiment(h))

        except Exception:
            # Síťová chyba – fallback
            for h in batch:
                results.append(_keyword_sentiment(h))

        # Krátká pauza mezi dávkami (rate limit)
        if i + batch_size < len(headlines):
            time.sleep(0.5)

    return results


def enrich_news_with_ai(news: list[dict]) -> list[dict]:
    """
    Přidá AI sentiment ke každé zprávě.
    Pole 'sentiment' nahradí výsledkem FinBERT,
    přidá 'sentiment_score' a 'sentiment_source'.
    """
    if not news:
        return news

    headlines = [item.get("title", "") + " " + item.get("summary", "")[:200]
                 for item in news]
    sentiments = analyze_headlines(headlines)

    for item, sent in zip(news, sentiments):
        item["sentiment"]        = sent["label"]
        item["sentiment_score"]  = sent["score"]
        item["sentiment_source"] = "FinBERT"

    return news


def news_ai_summary(news: list[dict]) -> dict:
    """
    Souhrnné skóre ze zpráv obohacených AI sentimentem.
    Váží skóre jistotou modelu (čím jistější, tím větší váha).
    """
    pos_score = 0.0
    neg_score = 0.0
    counts    = {"positive": 0, "negative": 0, "neutral": 0}

    for item in news:
        label = item.get("sentiment", "neutral")
        conf  = item.get("sentiment_score", 0.5)
        counts[label] = counts.get(label, 0) + 1

        if label == "positive":
            pos_score += conf
        elif label == "negative":
            neg_score += conf

    total = sum(counts.values()) or 1
    net   = (pos_score - neg_score) / total  # -1 až +1

    if net > 0.15:
        dominant = "positive"
    elif net < -0.15:
        dominant = "negative"
    else:
        dominant = "neutral"

    return {
        "positive":  counts["positive"],
        "negative":  counts["negative"],
        "neutral":   counts["neutral"],
        "dominant":  dominant,
        "score":     round(net, 3),   # -1 (velmi negativní) až +1 (velmi pozitivní)
        "source":    "FinBERT" if any(i.get("sentiment_source") == "FinBERT" for i in news)
                     else "keywords",
    }


def sentiment_to_signal(summary: dict, threshold: float = 0.20) -> str:
    """
    Převede AI sentiment na signál pro integraci do technické analýzy.
    threshold: minimální net skóre pro signál (výchozí 0.20)
    """
    score = summary.get("score", 0)
    if score >= threshold:
        return "BUY"
    if score <= -threshold:
        return "SELL"
    return "HOLD"
