# Stock Advisor Dashboard – Revolut

Konzervativní dashboard pro sledování akcií dostupných na Revolut.

## Instalace

```bash
pip install -r requirements.txt
```

## Spuštění

```bash
streamlit run app.py
```

## Signálový systém

Dashboard je **konzervativní** – signál BUY/SELL se zobrazí pouze při **shodě alespoň 3 indikátorů**:

| Indikátor | BUY | SELL |
|-----------|-----|------|
| RSI | < 30 (oversold) | > 70 (overbought) |
| MACD | bullish crossover | bearish crossover |
| Bollinger Bands | cena pod dolním pásmem | cena nad horním pásmem |
| EMA 20/50/200 | bullish uspořádání | bearish uspořádání |
| Stochastic | K/D < 20 | K/D > 80 |

## Zdroje dat

- **Yahoo Finance** – historická data, ceny
- **Finviz** – zprávy pro daný ticker (scraping)
- **MarketWatch RSS** – obecné tržní zprávy

## Disclaimer

Tento nástroj je pouze informativní. Nejedná se o finanční poradenství.
