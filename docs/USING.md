# Using BitcoinTX

What BitcoinTX does and how you use it, the same wherever it runs. How to
install it, log in the first time and update it depends on where it runs,
so none of that is on this page: on StartOS, the service's Instructions tab
covers it; elsewhere, the [README](../README.md#install).

BitcoinTX is a self-hosted, single-user Bitcoin portfolio tracker and tax
report generator for your self-custody wallets, exchange accounts and
banks. It tracks BTC and USD balances with **double-entry accounting**,
keeps each wallet's and each exchange's own cost-basis lots, computes cost
basis (**Per-wallet FIFO**) and capital gains, and prints IRS **Form 8949** and
**Schedule D**, including the Form 1099-DA boxes that start with tax year
2025.

> [!IMPORTANT]
> Add each wallet, exchange and bank you use in Settings, under Wallets,
> exchanges and banks. From 2025, cost basis is figured wallet by wallet and
> account by account; unless you identify the coins you sell, first in,
> first out within each, by the date first acquired (Treas. Reg.
> §1.1012-1(j)). Cost basis is per-wallet FIFO: each wallet and exchange
> uses its own oldest coins first for a sale, spend or transfer. If you kept
> multiple wallets or exchanges together in BitcoinTX 1.x, years before you
> added them were figured together: ask a tax professional whether an
> earlier return needs a change.

On this page: [Wallets, exchanges and banks](#wallets-exchanges-and-banks) ·
[Dashboard](#dashboard) · [Transactions](#transactions) · [A change to an
earlier tax year](#a-change-to-an-earlier-tax-year) · [Lots, gains and the
holding period](#lots-gains-and-the-holding-period) · [Reports and tax
forms](#reports-and-tax-forms) · [Imports and the CSV
export](#imports-and-the-csv-export) · [Ledger Review and Recalculate
Ledger](#ledger-review-and-recalculate-ledger) · [Prices and
privacy](#prices-and-privacy) · [Backups and safety
copies](#backups-and-safety-copies) · [Settings](#settings)

## Wallets, exchanges and banks

A new BitcoinTX starts with a **Bank**, a **Wallet** and an **Exchange**
(its dollars, **Exchange USD**, and its bitcoin, **Exchange BTC**).
**External** is everything outside BitcoinTX: other people, merchants, an
account you don't track. BitcoinTX also keeps two accounts of its own,
**BTC Fees** and **USD Fees**, where it records the fees you pay: no
transaction names them, and they aren't listed in Settings.

- **A wallet** holds bitcoin you keep yourself. It is one set of keys:
  every address it makes is part of it. A backup of the same keys (a seed
  phrase, or another device with the same keys) isn't a second wallet.
- **An exchange** keeps its dollars and its bitcoin as two accounts,
  "*name* USD" and "*name* BTC".
- **A bank** holds dollars: it can pay for a buy, and move dollars to or
  from an exchange's USD account or another bank by a Transfer.

**Settings → Wallets, exchanges and banks** lists your accounts by kind,
under Wallets, Exchanges and Banks, each on a row with its name, its kind
and its balance (an exchange's dollars, then its bitcoin). The section's
line says how many of each you have, and how many are hidden. Click a row
to open it.

- **Add a wallet**, **Add an exchange** or **Add a bank**: type its name
  and click **Add**. Under the name, the form says what a wallet is, or
  what the exchange's two accounts will be called, and **Add an exchange**
  also asks "Does this exchange send you a Form 1099-DA?" (**Yes** unless
  you choose No; below). A new account starts
  empty: move coins into it with a Transfer dated when they really moved
  (BitcoinTX moves the oldest coins first, unless you choose others in a
  wallet: [Lots, gains and the holding
  period](#lots-gains-and-the-holding-period)). Adding a wallet or an exchange
  while another one of its kind has transactions shows a note: years
  before you added it were figured with the others together, as BitcoinTX
  1.x did. A Transfer dated in an earlier year can change that year's
  figures and later ones, and BitcoinTX shows which years before it saves.
- **A name** is 1 to 40 characters on one line (an exchange's 1 to 36, so
  that its accounts' names fit " USD" and " BTC"); spaces at its ends are
  dropped, and a run of spaces is kept as one. No two accounts may have the
  same name whatever the case, nor two exchanges. **Bank**, **Wallet**,
  **Exchange USD** and **Exchange BTC** always mean your first bank, wallet
  and exchange in files (CSV, River, BitcoinTX 1.x), so no other account
  can take those names, nor **BTC Fees**, **USD Fees** or **External**.
  Your first bank, wallet and exchange can take their first names back. A
  name uses letters, digits and punctuation the tax report can print: no
  emoji, and no letters outside Western European alphabets (accents, €
  and dashes are fine).
- **Rename**, in the open row: an exchange's two accounts are renamed with
  it ("Kraken" makes them "Kraken USD" and "Kraken BTC"). A name moves no
  figure. A CSV file names each account as it was named when the file was
  saved, and an import matches those names to your accounts as they're
  named then: a file saved before a rename names that account by its old
  name. In a file, Bank, Wallet, Exchange USD and Exchange BTC still mean
  your first bank, wallet and exchange, whatever they're called now.
- **Hide** an account you no longer use: its history stays, and the
  transaction form no longer offers it, except for a transaction already
  saved in it. An exchange's two accounts are hidden and shown together.
  Hidden accounts are listed under **Show hidden (n)** in their kind; open
  one and click **Show** to bring it back. What a hidden account holds
  still counts on the Dashboard, and a file or an AI assistant that names
  one still records into it, with a warning.
- **Delete** an account no transaction names. An account with transactions
  can be hidden, never deleted: its history stays on your tax forms. Your
  first bank, wallet and exchange can't be deleted either: hide one you
  don't use.
- **This exchange sends me a Form 1099-DA**, in each exchange's row: the
  answer you gave when adding the exchange (your first exchange's is on),
  which the switch changes later. An exchange in the US sends one for your
  sales from 2025; one
  outside the US usually doesn't. Turn it off for an exchange that sends
  none, and its sales go in the Form 8949 boxes for no broker form. It
  decides the Form 8949 box, not the gain. It moves the boxes of earlier
  years' sales too, so when it would change an earlier tax year, it asks
  first ([below](#a-change-to-an-earlier-tax-year)).

BitcoinTX never lets you pick which coins to sell. It doesn't allocate your
cost basis among your wallets as of January 1, 2025 (Rev. Proc. 2024-28),
nor record an allocation you made: its figures from 2025 on follow its own
history. Your 2024 Complete Tax Report lists each account's lots at the end
of 2024, for a tax professional to compare with yours.

## Dashboard

- **Portfolio Overview**: Bank (USD), Exchange (USD), Exchange (BTC) and
  Wallet (BTC), each the total of all your accounts of that kind (Exchange
  (USD) adds up every exchange's dollars, Exchange (BTC) every exchange's
  bitcoin). A line with more than one account, or with a hidden one still
  holding something, has a caret after its label: click the line to list
  its accounts under it, each with its amount ("Hidden" noted), and under
  each wallet's and each exchange's bitcoin, what it cost and, with a
  price, its unrealized gain or loss. Lines start
  closed, and the ones you open stay open in that browser. Then **Total
  BTC**, **Avg. Cost per BTC** and **Unrealized Gains/Losses** (what the
  bitcoin you hold would gain or lose at the current price, from its
  average cost).
- **Current Bitcoin Price**: the live price, where it came from and when,
  and the block height. Until you choose where prices come from, a card at
  the top of the Dashboard asks "Where should BitcoinTX get Bitcoin
  prices?" ([Prices and privacy](#prices-and-privacy)).
- **Realized Gains/Losses (FIFO)**: short-term and long-term gains, losses
  and their net, the total net capital gains, and this year's so far.
- **Income & Fees**: income, interest and rewards earned, and their total;
  gifts and rebates received, which aren't income; the fees you paid in
  dollars and in bitcoin, and their total in dollars.

The sidebar, on every page, holds the **Sats Converter** (dollars, bitcoin
and sats at a price: **Manual**, a price you type; **Auto**, the live
price; **Date**, the price BitcoinTX has stored for a date, at an hour on
your device's clock or for the whole day) and a calculator.

## Transactions

**Transactions** lists your transactions under their days, newest first.
Each row shows its type and its accounts as you named them (a Buy's or a
Sell's exchange by the exchange's name, a transfer as *from* → *to*), its
time, a deposit's source or a withdrawal's purpose ("Consolidation" for a
bitcoin account sent to itself), its fee, the gain of a sale or a spend,
and the amount in its account's currency (under a bitcoin deposit,
withdrawal, buy or sell, its value in dollars). **Edit** opens it in the
form. Above the list:

- **Add transaction** opens the form.
- The account filter, on **All accounts** at first, narrows the list to a
  kind (**All wallets**, **All exchanges**, **All banks**, once you have
  more than one of that kind) or to one account (an exchange's two
  accounts together; a hidden one is marked). A transfer shows under both
  of its accounts.
- **Sort by date** or **Last added**; under the list, **Items per page**.

In the form you choose the **Transaction Type**, the **Date & Time**, the
accounts and the amounts. Your accounts are listed by name, grouped by
kind once you have more than one of a kind. Where more than one account
fits (two wallets, say), the field starts blank and you choose one; where
exactly one fits, it's filled in. Hidden accounts aren't offered, except
the one a transaction you're editing already uses; an account that no
longer exists shows as "account N (missing)" until you choose another.
Editing a transaction keeps the accounts it was saved with. A page opened
before BitcoinTX was updated from 1.x to 2.0 can't save: it says
"BitcoinTX was updated: reload the page." Reload it, and save again.

There are five kinds. Every edit or deletion, and every entry dated
before your latest one, recalculates the whole ledger, so backdated
entries come out right.

- **Deposit**: from External into one of your accounts: dollars into a
  bank or an exchange's USD account, or bitcoin into a wallet or an
  exchange's BTC account. A bitcoin deposit's **Source** decides its cost
  basis:
  - **MyBTC** (your own bitcoin from somewhere BitcoinTX doesn't track) and
    **Gift** (the giver's cost) take the basis you enter. Their **Date
    originally acquired** (when you first got the coins; for a gift, when
    the giver did), if you give it, starts the holding period, sets their
    place in Per-wallet FIFO's order and is Form 8949's date acquired; left
    blank, the deposit's date is used.
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
- **Withdrawal**: money leaving one of your accounts to External. A bitcoin
  withdrawal's **Purpose (BTC only)** decides how it's taxed: **Spent** is a disposal
  at its proceeds (left blank, the value at the hour's price); **Gift**,
  **Donation** and **Lost** aren't sales, so their value (**FMV (USD)**;
  left blank, the value at the hour's price) is recorded but is never part
  of a gain. A bitcoin network fee is on top of the amount and is a
  disposal of its own (for a spend, it comes off the proceeds), valued in
  **Fee value (USD)**. A dollar withdrawal has no purpose: only bitcoin is
  spent, given, donated or lost.
- **Transfer**: a move between your own accounts, such as an exchange's
  BTC account to a wallet, or one wallet to another, in one currency.
  Choose the **From Account** and the **To Account**, and enter **Amount
  (From)**, what left, and **Amount (To)**, what arrived: the fee is the
  difference. A bitcoin transfer's fee is a disposal (its **Fee value
  (USD)** beside it); the destination keeps each lot's acquisition date and
  its share of the basis. A dollar transfer (between dollar accounts,
  such as a bank and an exchange's USD account) has its fee come out of the
  sending account. Between two of your bitcoin accounts, the form lists the
  coins that will move before you save, oldest first: each one's date
  acquired, amount and cost.
  - For a bitcoin account, **To Account** also offers the account itself:
    "*wallet*: consolidate / move within the same wallet" or "*exchange*:
    consolidate within the same exchange". A consolidation records only its
    network fee, a disposal (of that account's coins, by Per-wallet FIFO)
    at the fee's value; your coins, their dates and cost basis stay as they
    are.
  - Moving coins to another exchange is a Transfer into that exchange's BTC
    account (add the exchange in Settings first if it isn't listed): each
    exchange keeps its own lots.
- **Buy**: bitcoin into an exchange's BTC account. Choose the **Exchange**
  (with one exchange, it isn't asked), then **Paid from**: that exchange's
  dollars, or a bank (marked "(auto-buy)"). An exchange's dollars buy only
  on that exchange. Enter the dollars spent without the fee as **Amount
  USD**, the bitcoin as **Amount BTC** and the fee as **Fee (USD)**: the
  lot's cost basis is Amount USD and the fee together.
- **Sell**: bitcoin from an exchange's BTC account, the dollars into the
  same exchange's USD account. Choose the **Exchange**, then enter what the
  sale brought before the fee as **Gross Proceeds (USD)** and the fee as
  **Fee (USD)**: the sale's proceeds are the gross less the fee.

A Sell and a Spent withdrawal also have **Broker form (1099-DA /
1099-B)**: leave it on **Automatic** unless the form your broker sent says
otherwise ([Reports and tax forms](#reports-and-tax-forms)).

## A change to an earlier tax year

A save that would change the figures of a tax year before this one, which
you may already have filed, asks first. The figures are each sale's gain
and Form 8949 box, the dates a return or the report prints, income and
rebates, and the value or kind of a gift, a donation or lost coins. It
asks when you:

- add, edit or delete a transaction;
- save the **Tax Timezone** (a sale whose tax year moves is listed under
  both years);
- turn an exchange's **This exchange sends me a Form 1099-DA** off or on;
- import an exchange's file (one question for the whole file).

An AI assistant's add (one question for its batch), edits, deletes and
Recalculate Ledger ask too.

**Change an earlier tax year?** says which years and lists what changes,
under each tax year: each transaction's date (in your tax timezone, as
Ledger Review dates it), type and amount, and what moves. Under "These also change, from rules fixed since they were saved"
come the changes the save also applies. **Cancel** saves nothing. **Save
anyway (a copy is made first)**, for a delete **Delete anyway (a copy is
made first)**, keeps a copy of your ledger in BitcoinTX's data folder
first, then saves ([Backups and safety
copies](#backups-and-safety-copies)). If the ledger changes while the
question is open, nothing is saved, and the question shows what the save
changes now.

- Adding to an earlier year (catching up on one, say), you can tick
  **Don't ask again for adds to 2025 while this page is open** (it names
  the years asked about): later adds to those years save without asking
  until the page is reloaded. Edits and deletes always ask.
- A save dated in this tax year, or one that moves only dollars, saves at
  once.
- With your login, changes Recalculate Ledger alone would make (rules
  fixed since a transaction was saved) never ask: Recalculate Ledger is
  how you apply them. When a save asks anyway, they're listed apart. With
  an AI assistant's key, those in an earlier year ask too.
- On a ledger too large to check within 10 seconds, the question names
  every tax year from the transaction's date on, instead of exactly what
  changes.
- An AI assistant gets the same question back, with the years and the
  changes, and saves only once you say yes.

## Lots, gains and the holding period

Cost basis is per-wallet FIFO: each wallet and exchange uses its own
oldest coins first for a sale, spend or transfer. A transfer
between your accounts moves lots, each keeping its acquisition date and
its share of the cost. A sale is long-term only when it comes after the
first anniversary of its lot's acquisition date (the IRS's "more than one
year"), dates taken in your tax timezone. Inherited coins are long-term
whatever the dates.

The **Tax Timezone** (Settings → Account) decides which tax year a
late-night December 31 transaction lands in, the dates on Form 8949, and
when a lot turns long-term.

## Reports and tax forms

**Reports**: choose the **Tax year** and the **Report**:

- **Complete Tax Report** (PDF): a one-page summary, then every disposal
  of the year as on Form 8949, one line for each lot it used, with its box
  and the account it left (a network fee paid in bitcoin is a disposal
  too); **Sales by exchange**, each exchange's Sells of the year (whether
  it sends a Form 1099-DA, the boxes, the rows, proceeds, cost basis and
  gain, network fees left out), to set beside the Form 1099-DA each
  exchange sends; income, and rebates apart (they aren't income); gifts,
  donations and lost coins; the bitcoin held
  at the end of the year, by account and lot by lot; "Using these forms",
  for whoever files the return; and notes on how the figures are made.
- **IRS Reports (Form 8949, Schedule D, etc.)** (PDF): the filled,
  flattened IRS forms, one Form 8949 sheet for each box.
- **Transaction History**: every transaction of the year, as a **CSV
  spreadsheet** or a **PDF** (**Format**).

Which Form 8949 box a sale goes in:

- **Up to 2024:** C (short-term) or F (long-term), as on no Form 1099-B.
- **From 2025, an exchange's sales** are on its Form 1099-DA: H or K
  (proceeds, no basis). From 2026, a sale of coins bought on that same
  exchange (a Buy into the account sold from) on or after January 1, 2026,
  and never moved, is G or J (basis reported). Coins moved into an exchange
  arrive there as noncovered: their sale stays H or K.
- **An exchange whose switch is off**, a self-custody spend and a network
  fee: I or L (no broker form).
- **Broker form** on a Sell or a Spent withdrawal overrides these for that
  transaction, when the form your broker sent says something different
  (for a spend, its network fee follows it: set it when the 1099-DA lists
  the spend and its fee).

Each year's final IRS forms come in an update once the IRS publishes them;
until then, the IRS's draft of that year is a preview, marked DRAFT — DO
NOT FILE.

## Imports and the CSV export

- **An exchange's file** (Settings → Import from an exchange). Under
  **Exchange file**, choose the exchange's CSV export: River's,
  Coinbase's, Kraken's (its ledger), Strike's, Swan's (two files: "Swan:
  deposits and purchases" and "Swan: withdrawals") or Cash App's, read
  as each writes it (all but River's from the exchange's published format,
  not yet checked against a real export: check the preview against your
  file); a mapping you saved, under **Your mappings**; or **Another
  exchange: match its columns**. Matching columns, you say which of the
  file's columns holds the date, the kind of row, the bitcoin and dollar
  amounts and the fee; how the file writes its times, numbers and dates;
  which word is bitcoin's and which is a completed row's (other rows are
  left out); and what each kind of row is. **Save this mapping**, under a
  name, puts it in the list for next time; you can preview without saving.
  - With more than one exchange or wallet, choose the **Exchange** the file
    is from and the **Wallet for sends and receives**: no exchange's file
    says which of your wallets a send went to or a receive came from, and
    with more than one exchange none is chosen for you unless one is named
    as the file's exchange.
  - The preview adds to a ledger in use: it leaves out the rows already in
    it (the same kind, bitcoin amount and minute), lists under "Possible
    matches with your ledger" the ones that only look like one you
    recorded, or that you recorded at the same minute and amount in another
    exchange or wallet (as BitcoinTX 1.x had you record a second exchange's
    trades in its one exchange),
    and names every row it didn't read and why (another coin, dollars
    alone, a row not completed, a repeated row, a trade of bitcoin for
    another coin, which you add by hand). Tick or untick each row under
    **Import**, change its type, source or purpose, and for a buy the file
    doesn't say how it was paid for, choose in **From → To** between that
    exchange's dollars and a bank. A buy's cost and a sell's proceeds are
    recorded before the fee, with the fee apart, whichever way the exchange
    writes them.
  - Rows dated in earlier tax years are named in the preview, and the
    import asks first ([A change to an earlier tax
    year](#a-change-to-an-earlier-tax-year)).
- **Import Transactions (CSV)** (Settings → Data Management): BitcoinTX's
  own columns, into an empty ledger only. **Template** downloads the
  columns, **Instructions** a PDF explaining each; **Preview** checks the
  file before anything is saved. A file names each account as Settings
  does, in any case: Bank, Wallet, Exchange USD and Exchange BTC always
  mean your first ones, so a BitcoinTX 1.x file imports as it did; any
  other name must be one of your accounts' names now (the error lists
  them); a hidden account still imports, with a warning.
- **Export as CSV** (Settings → Backup & Restore): every transaction, in
  BitcoinTX's own columns, each account by its name now (unencrypted, and
  editable). It imports back into an empty ledger whose accounts have
  those names (after Delete All Transactions, say); to move a whole ledger,
  use the encrypted backup.
- **Optional AI entry**, off until you turn it on (Settings → Connect an
  AI Assistant): paste an exchange email or a wallet history into an AI
  assistant, or type "moved 0.05 BTC to my Coldcard yesterday, fee 2k
  sats". The assistant previews the rows (duplicate check, fair market
  value, resulting gains) and saves them once you confirm. It names your
  accounts as you named them, asks which one when more than one fits, and
  can't add an account: you add it in Settings. A name that isn't one of
  your accounts is refused before anything is sent (a renamed account's
  first name, with its new one). For Ledger Review and for a change that
  may ask about an earlier tax year, the connector waits up to 20 minutes
  for BitcoinTX's answer, time a large ledger on a slow server can need. An AI connector older than
  BitcoinTX 2.0 can't tell your wallets or exchanges apart, so once you
  have more than one wallet or more than one exchange (a hidden one
  counted), BitcoinTX refuses its changes until it's updated; it can still
  read the ledger. Setting it up: the [MCP server's
  guide](../mcp_server/README.md). Once connected, the AI's model reads
  your ledger; to keep it on your computer, use a local model
  ([how](../mcp_server/README.md#privacy-cloud-or-local-model)).

## Ledger Review and Recalculate Ledger

**Settings → Ledger Review** is a read-only list of saved entries worth a
second look, each check with its count, what to do, and **Show the …** to
list its transactions with their accounts. The section's line says how
many transactions it wants you to check. **Check again** reads the ledger
again; it is also read again on its own once another section saves
something it shows (the Tax Timezone, Recalculate Ledger, an exchange's
switch). The checks:

- transactions naming an account that doesn't exist (a BitcoinTX before
  0.9.2 saved these, or an account they named was deleted): edit each
  into one of your accounts, or delete it;
- transactions in an account made through BitcoinTX 1.x's old account API,
  which 2.0 counts by that account's currency: check each, and save it
  (even unchanged) to take it off the list;
- every figure a recalculation would change (old → new);
- values BitcoinTX priced at the day's price that the hour would change
  (below);
- Spent withdrawals saved with $0 proceeds, and Lost withdrawals still
  carrying a loss;
- bitcoin withdrawals whose purpose isn't Spent, Gift, Donation or Lost
  (each counts as Spent until you choose);
- bitcoin deposits (not income or a rebate) and buys with a $0 or blank
  cost basis;
- Inherited deposits without a date of death;
- income and rebate deposits, and gifts, donations and lost coins, with a
  $0 or blank value; and income and rebate values you typed, far from
  that hour's price.

After them come two reminders, not errors: MyBTC and Gift deposits without
a date originally acquired, counted from their deposit date until you add
one; and exchange sales your exchange's Form 1099-DA may show differently
(an exchange may count coins moved in as bought when they arrived, and sell
other coins first), to compare with that form.

**Values priced at the day's price that the hour would change**: a value
BitcoinTX filled in itself before it had hourly prices (or while they were
still downloading) used that day's price. They're listed by tax year, with
each year's totals. Tick the ones to change and click **Apply to the
ticked ones**, or **Apply to all of** a year: BitcoinTX asks, makes a copy
of the database, prices each at its hour and recalculates the ledger. A
value you typed is never listed. For a year you've already filed, leaving
it as filed is recommended: whether to amend is a question for a tax
professional.

**Settings → Account → Recalculate Ledger** rebuilds every lot and gain
from your transactions; the transactions themselves aren't changed. Open
Ledger Review first and recalculate when you agree with what it lists.

## Prices and privacy

BitcoinTX values a transaction at the price when its hour began, from its
own stored history; where no hour is known, the day's price is used. It
records one price per hour, so it won't always match a chart of one
exchange at another moment.

A fresh install contacts nothing until you choose where newer prices come
from (**Settings → Privacy & Network**, or the Dashboard's "Where should
BitcoinTX get Bitcoin prices?"): your own Mempool, public price sites, or
nobody. Where the server sets that choice (on StartOS, the **Price Source
& Privacy** action), Settings shows it read-only.

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

## Backups and safety copies

**Settings → Backup & Restore**:

- **Download Encrypted Backup** saves your whole ledger as an encrypted
  file, with a password of its own: at least 12 characters, typed twice.
  Keep it: without it the backup can't be opened (a backup made earlier
  with a shorter password still restores).
- **Restore from Backup** takes a backup file and its password. It takes
  the backup's data but keeps your current login, AI key and price
  settings, and you log in again afterwards. Your saved exchange-file
  mappings are kept, and the backup's are added beside them, unless you
  already have one with the same name. It takes a backup made by
  BitcoinTX 1.x or 2.0: a 1.x backup's ledger is brought up to 2.0 as it is
  restored, the way an update brings up a 1.x database. BitcoinTX 1.x
  refuses a backup made by 2.0, since it can't read 2.0's ledger.
- **Export as CSV**: [above](#imports-and-the-csv-export).

BitcoinTX also keeps unencrypted safety copies of its database in its data
folder, in `backups` next to the database. You never need them in normal
use; each is a way back from one kind of change:

- before each update that changes the database, and before each restore
  (the newest 5);
- of a BitcoinTX 1.x database, made when 2.0 first opens it, named
  `btctx-pre-2.0-from-…`: never deleted by BitcoinTX;
- before a save you confirmed with **Save anyway** or **Delete anyway**
  (the newest 5, and for a week the first of each day);
- before **Delete All Transactions** (the newest 5);
- before Ledger Review's prices at the hour are applied (the newest 5);
- an AI assistant's, before its first change in an hour, before each
  change it confirms to an earlier tax year, and when it asks for one (at
  most 11).

## Settings

Settings is a list of sections, each with a line saying what's inside or
how it stands. Click one to open it; one is open at a time, and the one
you left open opens again next time in that browser.

- **Account**: **Logout**; **Reset Username & Password**, which keeps your
  transactions (a new password is at least 12 characters, and any change
  needs your current password); the **Tax Timezone**; **Recalculate
  Ledger**.
- **Wallets, exchanges and banks**: [above](#wallets-exchanges-and-banks).
- **Ledger Review**: [above](#ledger-review-and-recalculate-ledger).
- **Privacy & Network**: where prices come from, and through what
  ([Prices and privacy](#prices-and-privacy)).
- **Connect an AI Assistant**, optional: **AI access** (off until you turn
  it on), the AI key, and the setup prompt to paste into your AI app; the
  [MCP server's guide](../mcp_server/README.md) has the rest.
- **Data Management**: **Delete All Transactions**, which says how many
  transactions would go and over which years, offers an encrypted backup
  first, deletes only once you type DELETE, and keeps a copy of the
  database before it does; **Import Transactions (CSV)**
  ([above](#imports-and-the-csv-export)).
- **Import from an exchange**: [above](#imports-and-the-csv-export).
- **Backup & Restore**: [above](#backups-and-safety-copies).
- **About BitcoinTX**: the notice above, "Important: add each wallet and
  exchange.", the disclaimer, your version with a link to the release
  notes, and where to report a problem (reports are public, so never
  include your own figures or addresses) or, privately, a security
  problem.

## Disclaimer

BitcoinTX is software, not tax, legal or financial advice. It works from the
records you enter: check its figures with a tax professional before you
file.
