# Using BitcoinTX

What BitcoinTX does and how you use it, the same wherever it runs. How to
install it, log in the first time and update it depends on where it runs,
so none of that is on this page: on StartOS, the service's Instructions tab
covers it; elsewhere, the [README](../README.md#install).

BitcoinTX is a self-hosted, single-user Bitcoin portfolio tracker and tax
report generator. It tracks BTC and USD balances with **double-entry
accounting**, computes FIFO cost basis and capital gains per account, and
prints IRS **Form 8949** and **Schedule D**, including the Form 1099-DA
boxes that start with tax year 2025.

> [!IMPORTANT]
> Add each wallet, exchange and bank you use in Settings, under Wallets,
> exchanges and banks. From 2025, cost basis is figured wallet by wallet and
> account by account; unless you identify the coins you sell, first in,
> first out within each, by the date first acquired (Treas. Reg.
> §1.1012-1(j)). BitcoinTX keeps each wallet's and each exchange's own lots
> and always sells them first in, first out. If you kept multiple wallets or
> exchanges together in BitcoinTX 1.x, years before you added them were
> figured together: ask a tax professional whether an earlier return needs
> a change.

## Wallets, exchanges and banks

A new BitcoinTX starts with a **Bank**, a **Wallet** and an **Exchange**
(its dollars, **Exchange USD**, and its bitcoin, **Exchange BTC**). **External** is everything outside BitcoinTX: other people,
merchants, an account you don't track.

**Settings → Wallets, exchanges and banks** lists your accounts by kind,
each with its balance:

- **Add a wallet**, **Add an exchange** or **Add a bank**: a name. A wallet
  is one set of keys: every address it makes is part of it, and a backup of
  the same keys isn't a second wallet. An exchange keeps its dollars and its
  bitcoin as two accounts, "*name* USD" and "*name* BTC". A new account
  starts empty: move coins into it with a Transfer dated when they really
  moved (BitcoinTX moves the oldest coins first).
- **Rename** an account (an exchange's two accounts are renamed together),
  **Hide** one you no longer use (its history stays; Show brings it back),
  or **Delete** one no transaction names. Your first bank, wallet and
  exchange can't be deleted.
- Each exchange's **This exchange sends me a Form 1099-DA** switch, on by
  default: turn it off for an exchange that sends none (usually one outside
  the US), and its sales go in the Form 8949 boxes for no broker form.

The **Dashboard** shows your banks, exchanges and wallets on three cards; a
card with more than one wallet, exchange or bank opens to list them.

BitcoinTX never lets you pick which coins to sell. It doesn't allocate your
cost basis among your wallets as of January 1, 2025 (Rev. Proc. 2024-28),
nor record an allocation you made: its figures from 2025 on follow its own
history. Your 2024 Complete Tax Report lists each account's lots at the end
of 2024, for a tax professional to compare with yours.

## Transactions

There are five kinds. Every edit or deletion, and every entry dated
before your latest one, recalculates the whole ledger, so backdated
entries come out right.

- **Deposit**: dollars into a bank or an exchange's USD account, or
  bitcoin into a wallet or an exchange's BTC account. A bitcoin deposit's
  **Source** decides its cost basis:
  - **MyBTC** (your own bitcoin from somewhere BitcoinTX doesn't track) and
    **Gift** (the giver's cost) take the basis you enter. Their **Date
    originally acquired** (when you first got the coins; for a gift, when
    the giver did), if you give it, starts the holding period, sets their
    place in FIFO and is Form 8949's date acquired; left blank, the
    deposit's date is used.
  - **N/A** (no particular source) takes the basis you enter; its
    holding period starts on the deposit's date.
  - **Income**, **Interest** and **Reward** (mining, staking, a sign-up or
    referral bonus) are income: their basis is their value when received
    (left blank, the price at that hour), and that value is the income on
    the reports.
  - **Rebate** (bitcoin back for spending, such as a rewards card's
    sats-back) is valued the same way but isn't income: the reports list it
    apart. Sats-back for buying money orders or other cash equivalents is
    income: use Reward.
  - **Inherited**: the **Date of death** is required, and the basis is the
    value on it (or on the estate's alternate valuation date, if it chose
    one; left blank, the date of death's price). Any sale of those coins is
    long-term.
- **Withdrawal**: money leaving to External. A bitcoin withdrawal's
  **Purpose** decides how it's taxed: **Spent** is a disposal at its
  proceeds (left blank, the value at the hour's price); **Gift**,
  **Donation** and **Lost** aren't sales, so their value (left blank, the
  value at the hour's price) is recorded but is never part of a gain. A bitcoin network fee is on top of the amount and
  is a disposal of its own (for a spend, it comes off the proceeds).
- **Transfer**: a move between your own accounts, such as an exchange's
  BTC account to a wallet, or one wallet to another. A bitcoin transfer's
  amount is what left, network fee included; the destination gets the rest
  and keeps each lot's acquisition date and its share of the basis, and
  the fee is a disposal. A consolidation (a wallet, or an exchange's BTC
  account, to itself) records only its network fee. A dollar transfer (between a bank and an exchange's USD
  account) is kept the other way round, like a withdrawal: its amount is
  what arrived, and its fee comes out of the sending account on top.
- **Buy**: dollars from a bank or an exchange's USD account for bitcoin
  into an exchange's BTC account (an exchange's dollars buy only on that
  exchange).
  Enter the dollars spent without the fee as **Amount USD** and the fee as
  **Fee (USD)**: the lot's cost basis is the two together.
- **Sell**: bitcoin from an exchange's BTC account for dollars into the
  same exchange's USD account. Enter
  what the sale brought before the fee as **Gross Proceeds (USD)** and the
  fee as **Fee (USD)**: the sale's proceeds are the gross less the fee.

A save that would change the figures of an earlier tax year, one you may
already have filed (an add dated in it, an edit, a delete, a change of the
Tax Timezone or of an exchange's 1099-DA switch, an import), says which
years and what changes, and asks first: **Save anyway** (for a delete,
**Delete anyway**) makes a copy of your ledger, then saves.

## Lots, gains and the holding period

Each wallet and each exchange's BTC account keeps its own FIFO lots:
whatever leaves an account takes its oldest coins first. A sale is long-term only when it comes after the first
anniversary of its lot's acquisition date (the IRS's "more than one year"),
dates taken in your tax timezone.

The **Tax Timezone** (Settings → Account) decides which tax year a late-night
December 31 transaction lands in, the dates on Form 8949, and when a lot
turns long-term.

## Reports and tax forms

**Reports** gives Form 8949 and Schedule D (filled, flattened PDFs), a
complete tax report, and transaction history (PDF or CSV). For 2025 and
later, each exchange's sales go into the Form 1099-DA boxes its own form
uses (with its switch off, the boxes for no broker form), and the complete
tax report adds up each exchange's sales to set beside its 1099-DA; when
your broker's 1099-DA (or
1099-B) says something different for a sale, set **Broker form** on that
transaction and the right Form 8949 box follows (for a spend, its network
fee's box too: set it when the 1099-DA lists the spend and its fee). Each
year's final IRS forms come in an update once the IRS publishes them; until
then, the IRS's draft of that year is a preview, marked DRAFT — DO NOT FILE.

## Imports

- **River**: the CSV export from River. The preview leaves out rows already
  in your ledger.
- **Generic CSV**: into an empty ledger only.
- **AI entry**: paste an exchange email or a wallet history into an AI
  assistant, or type "moved 0.05 BTC to my Coldcard yesterday, fee 2k
  sats". The assistant previews the rows (duplicate check, fair market
  value, resulting gains) and saves them once you confirm. Setting it up:
  the [MCP server's guide](../mcp_server/README.md). Once connected, the
  AI's model reads your ledger; to keep it on your computer, use a local
  model ([how](../mcp_server/README.md#privacy-cloud-or-local-model)).

## Ledger Review and Recalculate Ledger

**Settings → Ledger Review** is a read-only list of saved entries worth a
second look, such as income and rebate deposits with a $0 or blank value,
Inherited deposits without a date of death, transactions naming an account
that doesn't exist or one made through BitcoinTX 1.x's old account API, and
every figure a recalculation would change (old → new). After them come two
reminders, not errors: MyBTC and Gift deposits without a date originally
acquired, counted from their deposit date until you add one; and exchange
sales your exchange's Form 1099-DA may show differently (an exchange may
count coins moved in as bought when they arrived), to compare with that
form.

**Settings → Account → Recalculate Ledger** rebuilds every lot and gain from your
transactions; the transactions themselves aren't changed. Open Ledger
Review first and recalculate when you agree with what it lists.

## Prices and privacy

BitcoinTX values a transaction at the price when its hour began, from its
own stored history; where no hour is known, the day's price is used. It
records one price per hour, so it won't always match a chart of one
exchange at another moment.

A fresh install contacts nothing until you choose where newer prices come
from (**Settings → Privacy & Network**): your own Mempool, public price
sites, or nobody. Where the server sets that choice (on StartOS, the
**Price Source & Privacy** action), Settings shows it read-only.

- **Your own Mempool**: the live price, block height and newer prices come
  from it, and no public site is contacted unless you tick **If it can't
  answer, ask public price sites**. It has hourly prices only from when it
  began recording. A home server's https address works too: when
  BitcoinTX can't trust its certificate, the card offers **Trust this
  server**, for that address only.
- **Public price sites**: the hourly history (2013 on) comes in one
  download from Bitstamp, the same for every install and checked against
  fingerprints that come with BitcoinTX. After that, only the newest hours
  come, in fixed blocks, so no request ever names one of your dates. A VPN
  or Tor hides your IP address from the sites. Through Tor, Bitstamp
  currently refuses BitcoinTX's requests for the price history, so the
  Dashboard asks once whether to download it without Tor: only Bitstamp's
  history downloads would show Bitstamp your address; the live price stays
  on Tor. You can change the answer in Settings. With No, use your own
  Mempool for newer values, or type them.
- **Nobody**: fully offline. Prices BitcoinTX already has still work; you
  type newer values yourself.

## Backups

**Settings → Backup & Restore** downloads an encrypted backup of your
ledger and restores one. A restore takes the backup's data but keeps your
current login, AI key and price settings.

## Disclaimer

BitcoinTX is software, not tax, legal or financial advice. It works from the
records you enter: check its figures with a tax professional before you
file.
