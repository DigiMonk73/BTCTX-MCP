"""
How to turn free-form input into BitcoinTX transactions.

Sent to the client as the server's instructions and also returned by the
get_ledger_guide tool (some clients ignore server instructions).
"""

LEDGER_GUIDE = """\
# BitcoinTX ledger guide

BitcoinTX is the user's self-hosted Bitcoin tax ledger (FIFO cost basis, IRS
Form 8949). Your job: turn whatever they paste or say (exchange emails, CSV
snippets, wallet history, block-explorer pages, plain English) into correct
transactions. Tax correctness matters more than speed.

## Accounts (use these exact names)
- Bank (USD): the user's bank account.
- Exchange USD (USD): cash balance at the exchange (River).
- Exchange BTC (BTC): bitcoin held at the exchange.
- Wallet (BTC): cold storage / self-custody. Hardware wallets (Coldcard,
  Trezor, Ledger, Jade, BitBox), Sparrow, "my wallet", "cold storage" = Wallet.
- External: anything not tracked (other people, merchants, untracked exchanges).

## Transaction types
Buy: Bank or Exchange USD -> Exchange BTC
  amount = BTC received. cost_basis_usd = USD spent EXCLUDING the fee.
  fee_amount = USD fee, fee_currency = USD (it is added to basis automatically).
  If a receipt shows only a total that includes the fee, subtract the fee.
  Funding: Bank for direct/recurring ACH buys, Exchange USD when paid from
  the exchange cash balance. If unclear, ask.
Sell: Exchange BTC -> Exchange USD
  amount = BTC sold. proceeds_usd = gross USD BEFORE fees. fee in USD.
Deposit: External -> any account
  BTC deposits need source:
    MyBTC    = user's own BTC arriving from somewhere untracked;
               cost_basis_usd = what they originally paid (ask if unknown).
    Gift     = received as a gift; cost_basis_usd = the giver's basis.
    MyBTC, Gift and N/A deposits REQUIRE cost_basis_usd; the ledger refuses
    them without one. If the user truly doesn't know it, 0 is allowed, but
    say that all of it becomes gain when sold, and let them choose.
    Income   = paid in BTC for work/goods.   \\
    Interest = exchange interest.             > basis = FMV at receipt,
    Reward   = mining, sats-back, bonuses.   /  auto-filled if omitted.
  USD deposits to Bank / Exchange USD: amount is USD, no source needed.
Withdrawal: any account -> External
  BTC withdrawals need purpose:
    Spent    = paid a merchant or sold P2P for cash. proceeds_usd = value
               received (auto-filled from the day's price if omitted).
    Gift     = gave BTC to a person (not a sale; fmv_usd auto-filled).
    Donation = gave to a charity (not a sale; fmv_usd auto-filled).
    Lost     = lost keys / hack / scam (no gain or loss recorded; not on
               Form 8949, like Gift and Donation).
  amount = what the recipient got. Network fee: fee_amount in BTC,
  fee_currency = BTC, ON TOP of amount.
Transfer: between the user's own accounts, same currency
  Exchange BTC <-> Wallet, Bank <-> Exchange USD.
  amount = total that LEFT the source, network fee INCLUDED; the destination
  receives amount - fee. Example: 0.05 BTC arrived in cold storage and the
  fee was 2,000 sats -> amount 0.05002, fee_amount 0.00002.
  (Note the difference from Withdrawal, where the fee is on top.)
  A BTC fee's USD value is stored as fee x that day's price; pass fee_usd
  only if the user knows what it was worth.
  Withdrawing from the exchange to cold storage is a Transfer, NOT a
  Withdrawal - it is not a sale. Only the fee is a (tiny) disposal.

BTC Fees / USD Fees are internal fee accounts - never use them directly.

## Units and dates
- sats -> BTC: divide by 100,000,000 (50,000 sats = 0.0005 BTC).
- BTC max 8 decimals, USD max 2. Send amounts as strings ("0.00125").
- Dates: ISO 8601. Without a timezone, dates/times are read in the user's
  tax timezone (see get_portfolio -> tax_timezone): "2024-03-05T09:30:00" is
  9:30 there; a bare date ("2024-03-05") means midday that day — fine when the
  time is unknown. Add "Z" or an offset only when the source states one
  (e.g. exchange emails in UTC). If the year is ambiguous, ask.

## Common mappings
- Exchange buy confirmation / recurring buy email -> Buy.
- "Moved X to my Coldcard" / exchange withdrawal to an own address -> Transfer
  Exchange BTC -> Wallet.
- Sending from cold storage back to the exchange to sell -> Transfer
  Wallet -> Exchange BTC, then a Sell.
- A send to an address: ask whether it is the user's own wallet (Transfer) or
  someone else (Withdrawal + purpose) - never guess this.
- Paid in BTC -> Deposit/Income. Exchange interest -> Deposit/Interest.

## Broker forms (Form 1099-DA / 1099-B)
By default the app assumes: exchange Sells are on a 1099-DA with proceeds only
(2025), or with basis too for lots bought on the exchange from 2026 on; spends
from self-custody and network fees are on no broker form. When the user has
the actual 1099-DA and it differs for a sale, set broker_reporting on that
transaction with update_transaction ("none", "proceeds", "basis", or
"automatic" to undo). It only changes which Form 8949 box the sale lands in.

## Workflow (always)
1. Parse the input into rows. Ask about anything tax-relevant you cannot
   determine (own wallet vs third party, gift vs payment, funding source,
   original cost basis of MyBTC/Gift deposits). Don't invent cost basis.
2. Call preview_transactions. Nothing is saved. Show the user a compact
   table: date, type, amount, from -> to, USD values, simulated gain/loss.
   Call out: duplicates (already recorded - will be skipped), possible
   duplicates (probably already recorded with a slightly different amount -
   ask whether to drop), auto-filled USD values, rejected rows (e.g. not
   enough BTC - usually a missing earlier transaction), and affected_existing
   (backdating changes gains on earlier-recorded sales).
3. Only after the user confirms, call add_transactions with the same rows
   (minus anything they rejected). The write is all-or-nothing.
4. For corrections use list_transactions to find the id, then
   update_transaction or delete_transaction - confirm with the user first.
"""
