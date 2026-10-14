# Hourly BTC prices

The hourly price history BitcoinTX values with when a transaction has no
dollar amount of its own (an income or rebate deposit, a BTC network fee, a
spend without a price, a gift's, donation's or lost coins' value): **the price
of bitcoin when the transaction's hour began**, in UTC (issue #144), and
holdings at the hour a tax year ends. This folder is that history's record.

## What the prices are

- **Bitstamp's BTC/USD hourly opening price**: the first price of each UTC
  hour (`/api/v2/ohlc/btcusd/?step=3600`), two decimals. It's one
  exchange's price, not an index; BitcoinTX already used Bitstamp for its
  daily prices.
- **From 1 January 2013.** Before that, most hours had no trade; those
  years keep the day's 00:00 UTC price.
- **Every hour has a price.** Bitstamp has a candle for every hour since
  2013, even one without a trade (242 of them, 107 during its halt of 5–9
  January 2015): such an hour opens at the previous hour's close (241 of
  the 242). A year missing an hour is incomplete and isn't used.

## What's here, and why not the prices themselves

`MANIFEST.csv` holds one line per year: its first and last hour, how many
hours, and the **SHA-256 fingerprint** of that year's file:

```
year,first_hour,last_hour,hours,sha256
2024,2024-01-01T00:00Z,2024-12-31T23:00Z,8784,529f3e31…
```

A year's file, `YYYY.csv`, is plain text (UTF-8, `\n` line endings), one
row per hour from 1 January 00:00 UTC to the manifest's last hour:

```
hour_utc,usd
2024-03-10T14:00Z,69123.45
```

Bitstamp allows its data to be redistributed only under its data licence,
so the owner asked Bitstamp for permission (2026-10-12). Until it's given,
this repo holds **only the fingerprints**: each install downloads the same
years from Bitstamp into its data folder (`btc-prices/`, next to the
database), in the same fixed requests (1,000 hours from 1 January
00:00 UTC, then the next 1,000…, never anything about a ledger), and uses a
year only if its text gives the fingerprint here. That happens once public
price sites are the chosen source (with your own mempool server and its
fallback, only when a lookup needs an hour the server doesn't have), newest
year first, each request with the choice as it is then: through the proxy
(Tor) set then, and none once public sites aren't allowed. So every install
holds exactly the same prices, and anyone can check them. If permission
comes, the year files are added here and the fingerprints stay the same.

## Checking them

- `python scripts/price_history.py check-sources` downloads every year
  again and compares it with the manifest.
- A year's file, once the app has downloaded it: `shasum -a 256 2024.csv`
  gives its line's fingerprint.

## How it's kept up to date

- **Each release's bump pull request runs `make prices`**
  (`scripts/price_history.py refresh`). It adds the hours since the last
  refresh, and refuses, writing nothing, if an hour is missing, if Bitstamp
  changed a price already in the manifest, or if a new hour disagrees with
  a second exchange: Bitfinex's hourly open for every new hour, Kraken's for
  its latest 720 hours. The limits: no hour more than 2% apart, a median
  gap of 0.5% at most, and the hours must agree better as they are than
  shifted by an hour. Measured from 2023 to October 2026, Bitstamp and
  Bitfinex were 0.09% apart at the median and 1.12% at most (the USDC
  weekend of March 2023); Bitstamp and Kraken 0.05% at most. Failed
  requests are tried twice more.
- **If a real market event trips a limit** (both exchanges right, as in a
  stablecoin's crash), the hours are excused in a pull request, with the
  owner's OK: listed with the reason in `EXCUSED_HOURS` in
  `scripts/price_history.py`. They still count in the median and the shift
  test.
- **The release workflow** checks again before it builds anything: the
  manifest is well formed, its newest 30 days still give their fingerprint
  and pass the cross-check, and it ends at most 14 days before the release.
- **A monthly check** (`.github/workflows/price-history-watch.yml`)
  downloads every year and opens an issue if Bitstamp no longer gives one.
- **A closed year never changes.** A test pins each closed year's line
  (`backend/tests/test_price_files.py`); closing a year in January is a
  deliberate change in a pull request. If Bitstamp ever changes a past
  price, nothing here changes without the owner's OK.
- **Nothing promises updates.** If no release came, newer hours would come
  from the price source chosen in the app, or be typed in.

The IRS asks for value at the "date and time" of each transaction and
approves no price source or method; an hourly price approximates it, and a
value you type (from an exchange's record, for example) is always used
instead.
