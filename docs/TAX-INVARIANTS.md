# Tax invariants

The rules every tax figure keeps. Read them before changing anything
that can move a figure: `backend/services/` (the ledger, prices,
imports, reports), `backend/migrations/`, `testdata/`, `scripts/`'s
figures scripts. Each has regression tests: don't break them. The
data model they act on, the past-year warning included, is in
`docs/ARCHITECTURE.md` ("Data model"); how a change to them is
reviewed, in `AGENTS.md` ("Reviews": the figures rule).

Moved word for word from `AGENTS.md` on 2026-11-04 (#903); `AGENTS.md`
now keeps a map of where each part lives. Where the text below says
"this file", it means `AGENTS.md` and the files its map names, and a
section named in quotes ("Branches", "Reviews") is found through that
map.

## Tax invariants (each has regression tests; don't break them)

- **Withdrawal fee**: a BTC network fee on a withdrawal is on top of `amount`
  and is its own disposal (`lot_disposals.is_fee`, oldest BTC first) at
  `fee_usd`, taxable even for Gift/Donation/Lost. It's on no broker form
  unless the withdrawal is a spend (rows of its own: not Gift/Donation/Lost)
  whose own `broker_reporting` says otherwise: then its rows go in the
  boxes that override gives (`form_8949._fee_follows_override`, #549, the
  owner's rule; only the box moves, never the fee's value or gain). A
  gift-like withdrawal's fee, even with an override left from an edit, and
  a transfer's fee take none (#551).
  A Spent's fee (and that of a withdrawal `counts_as_spent`, under
  "Proceeds") is a cost of the spend (Treas. Reg. §1.1001-7(b)(2)(ii)(A),
  #157, all years): its proceeds are the gross for `amount` less `fee_usd`,
  so the spend and its fee together realize the gross (a fee worth more
  than the gross takes only the gross). The transaction's own
  proceeds/basis/gain are the amount's (fee disposals left out).
- **Transfer**: `amount` is what left the source *including* the BTC fee; the
  destination lot gets `amount − fee`, keeping the source lot's acquisition
  date and its share of basis ("Lot cost"). The fee is a disposal. A bitcoin account to itself
  (a wallet, or an exchange's BTC account: a consolidation; in a 1.x ledger
  also a move between wallets or exchanges it kept together, #159) needs a
  fee and records only it: no lot moves. A dollar transfer (a bank ↔ an
  exchange's USD account) is the other way round, like a
  withdrawal: `amount` is what arrived, its fee on top (`_plain_lines`,
  #477).
- **Lot cost** (#100): a lot's cost is claimed as a running total. A piece
  taken from it (a sale's, a spend's, a fee's, a transfer's moved part)
  costs what the lot's BTC taken so far costs with it, in cents, less
  without it (`transaction.piece_cost`), so a lot's pieces add up to its
  cost, and what's held carries the rest (`cost_left`: holdings, the
  dashboard). A disposal's proceeds and a fee's value are shared among its
  lots the same way (`running_share`, #297), so its rows add up to them
  exactly and none is below zero. An exact half cent of a share rounds up
  (`SHARE_ROUNDING`).
- **Proceeds**: the user's figure is anchored in `gross_proceeds_usd`; stored
  `proceeds_usd` is net of fees and is re-derived from gross on every recalc
  (never from the previous net, which would subtract the fee again). A
  Sell's gross of $0 is a $0 sale; only a blank one (a row saved before
  0.8.0) is worked out from its stored net, the USD fee added back (#471).
  A withdrawal with a blank gross made a Sell by an edit that sends no
  proceeds takes the gross a recalculation recovers for it
  (`_send_gross_of_an_old_withdrawal_sold`, #520): its proceeds aren't a net.
  Unpriced "Spent" withdrawals get FMV proceeds at the hour's price, marked
  (`proceeds_from_price`) like an income value: an edit of the amount or
  hour (or a blank sent) prices them again; a change of purpose or type,
  or a typed value (never the form's echo), makes them typed. A spend's
  proceeds and fee value share one price: one priced again while the other
  keeps the day's price takes the day's too (`_keeps_a_day_price`).
  A withdrawal that doesn't count as spent (a gift, donation or lost coins;
  a dollar withdrawal) has no proceeds (#457): the form sends them only with
  a Spent, and an edit keeps no value sent for one (`_apply_proceeds`; a
  create still keeps one, so a CSV round trip keeps a former spend's). An
  edit that sends none carries over no $0 a gift holds into a Spent or a
  Sell, nor anything a dollar withdrawal holds into a bitcoin one
  (`_drop_proceeds_it_never_had`): a Spent's are then priced as a new blank
  Spent's are (sharing its fee's price), a Sell needs them sent; a gift's
  above $0 (a former spend's) are kept, typed. The form opens an old row
  with no gross at the gross the server recovers, rounded as it rounds
  (`utils/withdrawalProceeds.ts`, #485).
  A BTC withdrawal whose purpose isn't Spent, Gift, Donation or Lost (only
  an old ledger holds one) counts as Spent (`transaction.counts_as_spent`,
  the owner's rule, #61): at its gross, or, saved before 0.8.0 with no
  gross, at its stored `proceeds_usd` (no fee offset to undo: only a
  Spent's had one), which is kept as its gross. With none above $0 stored
  (blank, or 1.2.8's 0, #329) it stays as it was: a $0 sale, its fee at its
  value, no gross recorded and never priced by a recalculation
  (`transaction.received_known`). Ledger Review lists them until the owner chooses.
- **Gift, Donation and Lost values** (#255): a blank `fmv_usd` on such a BTC
  withdrawal is filled at save from the hour's price and marked
  (`fmv_from_price`). An edit fills one it leaves blank, or a sale's $0 it
  makes a gift when it sends no value (the form shows that $0 blank), and
  prices a marked one again when the amount or hour changes
  (`_gift_priced_by_edit`), at the transaction's one price. A value sent,
  $0 included, is typed and kept (a marked one sent back unchanged stays
  marked); with no price it stays blank (never a 422: it's on no form
  BitcoinTX fills), and Ledger Review lists it (`gift_without_value`).
  Never part of a gain.
- **Dollar withdrawals** (#449): only bitcoin leaving is spent, given,
  donated or lost. A withdrawal from a bank or an exchange's USD account keeps no such
  purpose and no proceeds or FMV: the save drops them
  (`_drop_btc_withdrawal_fields`; other text stays, a label such as
  "Rent"), the import previews leave them out with a warning, and every
  figure and check (the tax report and its values from the price, the
  dashboard, Ledger Review and its hour check, `priced_values`, the AI's
  duplicate check) reads them only on a bitcoin account (`book.is_btc`), so
  one an older save left there counts for nothing. The Transactions list
  and the Transaction History report show what's stored. It has no cost basis,
  gain or holding period either (no lots): every save and recalculation
  clears any it holds, such as a bitcoin withdrawal's an edit made it from
  (`compute_sell_summary_from_disposals`, #487).
- **Income deposits** (source Income/Interest/Reward into a BTC account):
  basis = market value at receipt, which is also the reported income. A blank
  or 0 basis is filled from the hour's price on create/update
  (`_value_at_receipt`); no price → 422, never $0. A value from the price
  is marked (`cost_basis_from_price`) and priced again when an edit changes
  the account, amount, UTC hour or type, or moves it from a source not valued
  at receipt (Reward to Rebate keeps it; a type change makes it typed); a
  typed one is kept, and the form's echo of a priced value isn't a typed one
  (`_revalue_income_deposit`). Income (report, dashboard) counts only
  deposits into a bitcoin account (`AccountBook.is_btc`): a USD
  deposit is dollars, whatever value it carries.
- **Rebates** (source Rebate, #98: card sats-back, shopping cash-back): valued
  like income deposits (`constants.VALUED_AT_RECEIPT`: the same filling,
  marking and re-pricing), but never income: not in the report's or the
  dashboard's income, listed apart in the report (`rebates`) and on the
  dashboard (`rebates_received`, #129). Reward stays income (mining,
  staking, bonuses).
- **Inherited** (source Inherited, #154): basis = value on the date of death
  (IRC §1014), the deposit's required `acquired_at`, which also dates its lot;
  valued like income deposits but on that date (`VALUED_AT_RECEIPT`: typed, or
  that day's price, priced again when the date of death changes; the date is
  the one entered, stored as a date that no tax timezone change moves,
  `transaction.date_of_death`, #177, #185), never income. Every disposal of its
  coins is long-term (§1223(9)) with INHERITED in Form 8949 column (b):
  `bitcoin_lots.inherited`, kept through transfers. Ledger Review doesn't
  compare its value with the day's price (an estate's value can rightly
  differ).
- **River Sells**: River's Received Amount is net of River's fee, so
  `proceeds_usd` (gross) = Received + fee.
- **River sends**: River's Sent Amount is what the destination got, its
  network fee on top (River's record gives the total as Sent + Fee, #39),
  so a Transfer's `amount` is Sent + fee. A send tagged `Withdrawal` is an
  auto-withdrawal, to the address the owner set: a Transfer to the
  wallet chosen for the file (a guess, its side marked by `guessed`) like
  any other send (#397). A `Mining` payout is a Reward deposit (#399).
- **Import duplicates** (#253, the owner's rule): the AI connector's and the
  River import's check (`river_import.annotate_duplicates`; every
  exchange's file is read into River's rows and checked as River's, B5b)
  leaves out only
  a duplicate: the same kind (going the same way), BTC amount and minute as
  a transaction in the ledger (a date given alone: that day in the tax
  timezone). A row is only ever compared with transactions of its own
  currency, bitcoin with bitcoin and dollars with dollars, in every pass
  (`_compatible`, #581). The AI's rows
  also need the same type, accounts (from and to: a payout into Exchange
  BTC beside one recorded into Wallet isn't that payout, only similar,
  #522), source or purpose and a Buy's basis (`entry_import.ENTRY_RULE`);
  a River row nothing else, and River's own amount counts (`RIVER_RULE`),
  since its source, purpose, fee and type are the preview's or the
  owner's edits;
  of the accounts, a River row needs only to go the same way
  (`_compatible`: the same source account or the same destination).
  No row, River's or the AI's, is ever matched to a transaction naming on
  the same side another account of the same kind and currency (two
  wallets, two exchanges' BTC or USD accounts, two banks: the owner's
  rule, 2026-10-15, #350); but River's wallet is the file's guess
  (`guessed`), so a transaction typed into or from another wallet beside
  River's send or receive (its other side the row's own or External,
  never a move between two wallets) is only similar, marked Review,
  ticked (the owner's decision, 2026-10-16); and River never names a
  buy's funding bank (`unnamed_bank`), so another bank there still
  matches exactly, as in 1.x (the build lead's call, 2026-10-23, #251's
  decision 25). A River row the other passes leave new, of the same kind,
  bitcoin amount and minute as a transaction in another account of the
  same kind (another exchange's, another wallet; going the same way, never
  into the account the row's coins left nor out of the one they went into;
  on the guessed side only beside the row's own account, one like it or
  External), is only similar:
  Review, ticked, its note naming that account and where the row may
  already be (`_in_another_account`, the owner's decision, 2026-10-25,
  #707: 1.x's guide had a second exchange's trades recorded in the first);
  the AI's rows never are. With more than one exchange, the screen picks
  none for a file but the one shown that the file is named for
  (`riverChoices`), and asks again for each file; the API keeps 5.11's
  first exchange for a request that names none. The
  amount tests go in turn (the ledger amount, then River's), and within
  each a transaction of the row's own type first. The timed rows take
  their copies before the date-alone rows (`_timed_first`, #472), so a
  date-alone row is the one saved when it and a timed row share their only
  copy. The AI's rows are matched so the
  most find a copy: a row left without one takes a copy another row holds
  when that row can take another (`match_by_moving`, #411). The user can
  override a duplicate: the AI's row names the transaction the preview
  matched (`not_a_duplicate_of`), a River row is ticked. Each transaction
  an AI row names, when it's a duplicate of that row (else the name counts
  for nothing), is set aside for every row of the request, in any row
  order (#510), and the rows are matched to the rest: a named row that
  finds another copy is that copy, so a resent request doesn't save it
  twice (#378). A named row beside a row without a name that the named
  transaction is a duplicate of too is unclear, never guessed at (the
  owner's rule, #497; a row into or out of another account than that
  transaction never is): the preview marks each such row invalid, saying
  which rows and what to do, and an add refuses the request
  (`entry_import._unclear`) until the AI names each or sends the named
  one alone.
  At River's save, each row the preview found in the ledger, ticked or
  left unticked (`left_out`), comes with the transaction the preview
  matched (`matched_tx_id`), which is kept for it, so an edit can't move a
  match; the other rows are checked against the rest. The same
  amount within 48 hours with anything else different is only similar:
  flagged, never skipped by itself. So is a bitcoin move (a Transfer or
  Withdrawal; never a dollar row, #581) of a near amount, within 20 %
  (one typed by hand guesses its network fee); a River bitcoin move of
  only a near amount starts unticked.
- **Prices**: every valuation goes through `services/hourly_prices.price_at`
  (#144): the opening price of the moment's UTC hour (the tax timezone never
  changes the hour), else the UTC day's 00:00 price
  (`services/price_history.daily_price`, table `btc_price_daily`); the
  moment is recorded in `transactions.price_moment` ("hour" or "day"; none
  when every value is typed). A value priced before hourly prices stays at
  the day until an edit prices it again or the owner applies Ledger
  Review's check (#144); a recalculation never re-prices. Holdings at a
  tax year's start and end are valued at `price_at` of that bound (the
  hour the tax year ends, in the tax timezone), and the Complete Tax
  Report lists the year's priced values with the price each used.
  Nothing is asked until the owner picks a
  price source (`services/outbound.py`: off / public / own mempool,
  optional fallback),
  or the server sets it (`BTCTX_PRICE_SOURCE` and co.; StartOS's Price
  Source & Privacy action), which Settings then shows read-only. From
  1.2.8, prices stored while the server sets it never count as a choice
  (it stores `unset`), and a CLI command never makes one (#134). Each
  start of the app notes which of the server's settings it has (its
  choice, or only its Tor: `outbound.SERVER_SET_KEY`); a CLI command
  lacking them (StartOS, run by hand) asks no one and says so on stderr
  (#461).
  **No request may name the day**: the own mempool server is asked for its
  whole history (hourly 00:00 rows kept), public sites for the whole history
  in fixed blocks once, then only the latest days; the tests check the URLs.
  The same for the hourly prices (`services/hourly_prices.py`, #144): the
  year files in fixed 1,000-hour blocks from 1 January, every year, newest
  first (checked against `MANIFEST.csv`), and after them Bitstamp's fixed
  blocks from the hour after the files; never the hour asked. Those blocks
  are asked at most every 10 minutes. A replay on a scratch copy (the
  past-year question, the coins list, a report, Ledger Review's check)
  that prices a stored row's missing value (`transaction._price_for`; one
  the stored row held blank, never its write's: `OWN_VALUES`) at an hour
  its own ask brought leaves that hour in memory, and in those 10 minutes
  only such a value is given it (`hourly_prices._found_for_a_stored_value`, #824,
  #849): never kept in the ledger, where it would come before your
  Mempool's for other rows, and with the day's prices looked for as before,
  so every other lookup gives what it did.
  **A proxy (Tor) carries every request to a public site**, with one
  exception the owner opts into (#241): Bitstamp refuses Tor's exits, so
  the price card asks once "Download the price history once without
  Tor?" (only after Bitstamp refused through the proxy, never before). The
  answer (`app_settings` `history_without_tor`, with when and where) is
  the owner's: a login-only route (never the AI key), kept by a restore,
  changeable in Settings even while the server sets the choice. After a
  Yes, and only then, Bitstamp's fixed history blocks (the year files, the
  hours after them, the daily history) go directly
  (`outbound.history_client`); `FixedBlocksOnly` refuses anything else on
  that route, a `start` off those blocks' grid included. The live price, block height and latest days stay on Tor.
  A proxy set for the whole machine (`HTTPS_PROXY` and co., a Mac's
  system proxy) carries only requests made without a proxy of
  BitcoinTX's to addresses beyond the home network (the public sites):
  never one to this computer or the home network (your Mempool there:
  `outbound.this_computer_or_home`; the Mac app's checks:
  `desktop_ports.open_here`; the AI connector: its own copy of the rule),
  nor that direct route (#474).
  A lookup can outlast a save (#437): each request is checked just
  before it's sent against the settings in use then, and one they no
  longer allow (or not through that client's proxy) is refused unsent
  (`outbound.ChoiceChanged`).
  Stored days and hours never change. Never today's live price, never $0: no price is
  a 422. A value a save, an import or Ledger Review works out from a
  price (a deposit's value at receipt: income, rebate or inheritance; a
  gift's `fmv_usd`; a Spent's proceeds; a fee's `fee_usd`) rounds an
  exact half cent to the even cent (`Decimal.quantize`'s default; the
  owner's choice, #556), unlike a lot's share (half up, "Lot cost") and
  the report's holdings value at a tax year's bounds (half down).
  A BTC fee's USD value is stored in `transactions.fee_usd`
  at save (`fee_usd_manual` when typed) and recalculation only reads it.
  A save that has written never waits for a year's download (#421); an
  import and the AI's preview and add find their rows' prices before
  their first write (`transaction.find_prices_first`, #426); such an
  import waits for a year once and asks a source once per hour. No save
  sends a request while it holds SQLite's write lock, nor waits for
  another lookup's (your Mempool's history under way, #535): one about to
  go out or be waited for
  (`price_history.requests_held`) rolls the save back, the price is found
  with the lock free, and the save runs again
  (`hourly_prices.with_prices_found`, #426), so a new way to save or
  recalculate runs in it.
- **Holding period**: long-term only when disposed *after* the one-year
  anniversary (IRS "more than one year"), dates taken in the tax timezone.
  It runs from the lot's acquisition date: a My BTC or Gift deposit's date
  originally acquired (`acquired_at`, a plain date since #185: its lot is at
  noon of it in the tax timezone, never after the deposit) when given, else
  the deposit's date;
  FIFO (oldest acquisition first, per account) and 8949 column (b) follow it.
  Inherited coins are long-term whatever the dates (above).
- **Chosen coins** (2.0, #711; specific identification, Treas. Reg.
  §1.1012-1(j)(2)): a Transfer out of a wallet (not to itself) or a bitcoin
  Withdrawal from one may name the coins that leave, `chosen_coins`: each
  the Buy or Deposit that acquired them (`acquired_txn_id`) and the BTC
  from it, together exactly what leaves (a Transfer's amount; a
  Withdrawal's amount and BTC fee). The fee takes the oldest of the chosen
  coins first, then the amount the rest, as first in, first out does with
  all of a wallet's coins; each piece costs its running share (Lot cost).
  Every lot keeps the acquisition its coins came from
  (`bitcoin_lots.acquired_txn_id`), through transfers; a write with a
  choice while a lot lacks it (made before migration 0101) replays the
  ledger first. Nothing chosen: per-wallet FIFO. An exchange's coins and a
  consolidation take no choice. A choice survives every recalculation; a
  write that would leave a later choice short of its coins is refused,
  naming it (`chosen_coins.NotHeld`); an edit that changes what leaves
  must send the coins again, or `[]` (null works too: `SendAgain`, its
  422 naming the transaction in `X-BitcoinTX-Choose-Again`, which the AI
  connector answers as `saved: false`). `coins_chosen_at` is when the choice was saved, kept
  while it's sent back unchanged. The CSV carries a choice by its rows'
  ids, never their positions (`csv_choices.py`, #732); the tax report
  prints "Coins you chose", with the day each was saved, and Ledger Review
  lists those saved after their coins left (`coins_chosen_later`). The AI
  key sends a choice too (the owner's Q4: only coins the user says they
  chose at the time, its guide's rule, #733): its preview lists the coins a
  row leaving a wallet takes and holds (`HELD_HOOK`; none for a row whose
  wallet holds a lot that doesn't know its acquisition while nothing
  replays), and a write that replays for a choice
  (`chosen_coins.replays_first`) counts as replaying for its copy and the
  past-year question.
- **Tax timezone**: timestamps are stored in UTC. The tax timezone (Settings,
  `app_settings` table, fallback env `BTCTX_TIMEZONE`, default UTC) decides
  tax-year bounds, 8949 dates and the holding period. Helpers in
  `backend/services/tax_time.py`. Never slice a year with naive UTC dates.
  A login fills it from the browser only while none was chosen and the
  ledger is empty (`tax_time.fill_tax_timezone`, #334); with transactions,
  only the owner's change in Settings moves it. Only the bundled `tzdata`
  package's names are saved, the same on every machine (#407); a name saved
  before 1.2.9 is still read (`tax_time.readable_zone`; one this machine
  can't open counts as none chosen, logged once), and a restore keeps this
  install's own in place of a backup's that `tzdata` doesn't name.
  Times on screen are the device's clock (#260), except Ledger Review's
  and the past-year question's (the tax timezone, as `cli review` and the
  AI see them, labelled: #737) and a price's hour (UTC, labelled).
- **Form 8949 boxes** (`form_8949.py`): ≤2024 C/F; 2025+ exchange Sells H/K
  (1099-DA without basis); 2026+ Sells of lots bought on that exchange (a Buy
  into the account sold from) on/after 2026-01-01 and never moved G/J;
  self-custody spends and fees I/L, and so are the Sells of an exchange whose
  "This exchange sends me a Form 1099-DA" is off (`exchanges.sends_1099da`,
  2.0, #349). A
  Sell/Withdrawal's `broker_reporting` (none/proceeds/basis) overrides those
  rules for that transaction, a spend's fee disposals included (#549).
  One sheet per box, line 2 totals that sheet's rows, Schedule D line per
  box, column (f) blank. A broker's figures are never stored: where a Form
  1099-DA differs, the report's page says how to correct the form by hand
  (the owner's choice, #158).
