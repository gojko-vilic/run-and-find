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

Amazon pages are priced with the delivery location set to Austria (override with
`AMAZON_SHIP_TO=<country code>`). A listing Amazon will not deliver there is
reported as out of stock, so only add ASINs that ship to Austria — usually a
specific size/colour child ASIN rather than the parent listing.

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

### 3. Sizes

Shoes are tracked only in the wearer's sizes, set in the `sizes` block of
`products.yaml` (cm, US and per-brand EU labels). A store offering every size
but those counts as out of stock, so no price drop there is reported, and the
wanted size reappearing is what triggers "back in stock". Store pages are read
for their size lists (Sportvision, Run'n'more, Intersport); an Amazon shoe url
must itself be the child ASIN of a wanted size — the checker names the right
ASINs when it is not. Products without a `gender` (a watch) are not filtered.

### 4. Run manually to test

Go to **Actions → Check Prices → Run workflow**.

## Project structure

```
├── .github/workflows/check_prices.yml   # daily schedule + manual trigger
├── scrapers/
│   ├── base.py        # abstract scraper interface
│   ├── serbian.py     # .rs sites
│   ├── austrian.py    # .at sites
│   ├── amazon.py      # amazon.*
│   ├── trebapatike.py # trebapatike.rs price aggregator (all Serbian shoe stores)
│   └── sizes.py       # wanted sizes + per-store size lists
├── data/
│   └── last_prices.json   # auto-managed, committed by workflow
├── products.yaml          # edit this to add/remove tracked products
├── checker.py             # main script invoked by workflow
└── requirements.txt
```
