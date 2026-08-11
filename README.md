# python-searcher

Daily price tracker that monitors products on Serbian, Amazon, and Austrian sites and sends a **Telegram notification** whenever a price drops.

Runs entirely on **GitHub Actions** — no server, no domain, no cost.

## How it works

1. You add product URLs to `products.yaml` (edit directly in GitHub browser)
2. A GitHub Actions workflow runs every day at 8am UTC
3. Each URL is scraped for its current price
4. If the price dropped since the last check, a Telegram message is sent
5. Updated prices are committed back to the repo automatically

## Supported sites

| Region  | Sites                                          |
| ------- | ---------------------------------------------- |
| Serbia  | Gigatron, Tehnomanija, Shoppster               |
| Austria | MediaMarkt.at, Geizhals.at                     |
| Amazon  | amazon.com, amazon.de, amazon.co.uk, amazon.at |

## Setup

### 1. Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret      | Value                                                                 |
| ----------- | --------------------------------------------------------------------- |
| `BOT_TOKEN` | Your Telegram bot token (from [@BotFather](https://t.me/BotFather))   |
| `CHAT_ID`   | Your Telegram chat ID (from [@userinfobot](https://t.me/userinfobot)) |

### 2. Add products to track

Edit `products.yaml` in the GitHub browser:

```yaml
products:
  - url: https://www.gigatron.rs/some-product
    name: Sony WH-1000XM5
  - url: https://www.amazon.de/dp/XXXXXXX
    name: Kindle Paperwhite
```

### 3. Run manually to test

Go to **Actions → Check Prices → Run workflow**.

## Project structure

```
├── .github/workflows/check_prices.yml   # daily schedule + manual trigger
├── scrapers/
│   ├── base.py        # abstract scraper interface
│   ├── serbian.py     # .rs sites
│   ├── austrian.py    # .at sites
│   └── amazon.py      # amazon.*
├── data/
│   └── last_prices.json   # auto-managed, committed by workflow
├── products.yaml          # edit this to add/remove tracked products
├── checker.py             # main script invoked by workflow
└── requirements.txt
```
