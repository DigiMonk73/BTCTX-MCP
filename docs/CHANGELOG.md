# Changelog

All notable changes to BitcoinTX are documented in this file.

## [Unreleased]

### Added
- **Through Tor, the price history can be downloaded once without Tor,
  if you agree** (#241, the owner's decision of 2026-10-16). Through Tor,
  Bitstamp refuses BitcoinTX's requests (a 403 or a "Loading" page), so
  since 1.2.8 an install using Tor got no hourly history and no past
  prices, and the card only told you to turn Tor off. Now, once Bitstamp
  has refused through Tor, the Dashboard (and the price card in Settings
  → Privacy & network) asks once: "Download the price history once
  without Tor? It's the same download for every install, and names none of
  your dates; Bitstamp would see this server's address." **Yes** lets only
  Bitstamp's fixed history blocks go directly: the hourly history from
  2013, the newer hours after it when a value needs one, and the daily
  history. The live price, the block height and everything else stay on
  Tor. **No** keeps everything on Tor, as before. The answer is recorded
  (when, and where), kept by an in-app restore, and changeable in Settings,
  also on StartOS when its Price Source & Privacy action sets Tor (its Use
  Tor text says so). Nothing goes around Tor before a Yes, and a Tor that
  isn't running never brings the question. The privacy audit
  (`docs/PRIVACY_AUDIT.md`) lists what Bitstamp then sees.
- **Tax notes in the Complete Tax Report, the AI's guide and the form**
  (#160, #114; no figure is computed differently). Each was checked
  against the IRS's own text (its digital asset FAQ, the instructions for
  Forms 1040, 709, 8283, 8949 and 1099-DA, CCA 202511015, Pub. 525):
  - Gifts, donations and lost coins (section 4) list each one's **cost
    basis and term** (Long, Short, or Both, split in a note), from the
    lots it used. Below them, only for the kinds the year has: a
    donation's deduction rules (the value for coins held more than a year,
    the lower of value and basis for the rest), Form 8283 over $500 and a
    qualified appraisal over $5,000 (an exchange's price isn't one); a gift
    tax return (Form 709) when gifts to one person other than your spouse
    pass the year's annual exclusion ($19,000 in 2025 and 2026); a theft
    or scam loss in an investment possibly deductible on Form 4684, up to
    the coins' basis.
  - The Summary answers **Form 1040's digital asset question**: Yes for a
    year with bitcoin sold, spent, paid as a fee, given away or donated, or
    received as income, a reward, interest or a rebate.
  - Income (section 3): pay for work as an independent contractor goes on
    Schedule C and is self-employment income (Schedule SE).
  - Notes (section 7), in a year with a broker's form: the IRS hasn't said
    which time zone sets your dates, and a broker may date a sale in
    another (UTC), so near midnight its date can differ.
  - "Using these forms", for a year without BitcoinTX's IRS forms (#114):
    -0- in column (g), and the exchange's name before "see attached
    statement" in its boxes (Form 8949 instructions, Exception 2).
  - The form's Rebate hint and the AI's guide: sats-back for buying money
    orders or other cash equivalents is income (Reward), not a rebate. The
    guide carries the other notes too.
  The Summary and "Using these forms" still take one page each wherever
  they did.
- **A way to support BitcoinTX:** the README's "Support BitcoinTX" gives its
  Lightning address (digimonk73@strike.me), and GitHub's Sponsor button
  (`.github/FUNDING.yml`) opens the tipping page. Nothing in the app changes.
- **Grok's review pass** (`docs/GROK-REVIEW.md`). The finder's manual:
  a release pass and one monthly area, with Claude checking each finding;
  `AGENTS.md` points to it ("Who does what", "Reviews").
- **StartOS: the store's donation link** (#249): the package's
  `donationUrl` is BitcoinTX's Lightning tipping page. It reaches StartOS
  with the next package release.

### Changed
- **The README says what comes after 1.2.9** (#369, #251; "Versions", also
  `docs/ROADMAP.md` and `SECURITY.md`). 1.2.9 is planned as the stable
  version, with maintenance updates and small improvements after it, until
  2.0 replaces it;
  2.0, with several wallets, exchanges and banks, is planned to be tested as
  a beta on GitHub pre-releases before it comes to Start9's Community Beta.
  No dates are promised.
- **The River import's preview fits a 1440-wide window** (#259). At 1440 ×
  900 its table was 1,500 px wide in a 776 px card, so the amounts, cost
  basis, proceeds and fees were off to the right and the table had to be
  scrolled sideways. While a preview is open, Settings now widens (up to
  1,240 px, the Dashboard's width), and the table is narrower: the time under the date, a
  withdrawal's purpose or a deposit's source under its type, and the
  account it goes to under the one it comes from (a Buy's Bank / Exchange
  USD choice included). Every column now shows in a 1440-wide window; in a
  narrower one (the Mac app opens at 1280) and on a phone the table still
  scrolls sideways, less than before.
- **Times on screen are this device's clock** (#260, the owner's choice).
  With a tax timezone other than the computer's, the screen showed times in
  two zones: the Transactions list and the form in the computer's, but the
  price card ("From public price sites (Kraken) · 4:45 pm"), Settings'
  "Last price" and "You chose this … at" in the tax timezone, and the
  sidebar's Date + hour picked the hour in the tax timezone. Now these
  times, and the sidebar's hour, follow the device you look from (on
  StartOS, your phone's or laptop's clock, not the server's). The tax
  timezone keeps deciding what it's for: the tax year, Form 8949's dates
  and the report. Two kinds of time stay as they were, each labelled:
  Ledger Review's dates are in the tax timezone, as `cli review` and the
  AI connector see the same items, and a price's hour ("From the price: …
  at 14:00 UTC") is named in UTC wherever it's shown.
- **Delete All and Create account ask before they wipe the ledger, and
  keep a copy first** (#256). Settings → Data Management → **Delete** used
  the browser's one-click confirm, and **Create account** on an install
  with transactions deleted them all after a similar confirm, shown even on
  an empty install and before the setup code was checked. Neither kept a
  copy. Now:
  - a dialog says what goes ("This deletes 118 transactions, 2023–2026"),
    offers **Download a backup first** (the encrypted backup, which
    Restore brings back; on Create account, how to get one after logging
    in), and deletes only once you type `DELETE`;
  - before anything is deleted, BitcoinTX keeps a copy of the database in
    its data folder (`backups/btctx-before-delete-all-….db`, unencrypted,
    the newest 5, apart from the copies made before updates), for help in
    putting it back; no copy, nothing deleted;
  - Create account checks the setup code or current password first, and
    asks only when there are transactions to delete;
  - the server refuses either delete without the typed `DELETE`
    (`confirm=DELETE`; otherwise 409 says what would go). The AI key still
    can't delete everything.
- **A gift's, donation's or lost coins' value left blank is filled from
  the price** (#255). In the transaction form, a Withdrawal with purpose
  Gift, Donation or Lost saved with its FMV (USD) blank kept no value
  unless you pressed Refresh, and the tax report listed it as "not given";
  the AI connector filled a gift's or donation's but not lost coins'. Now,
  as for an income value or a spend's proceeds, a blank one is filled when
  it's saved, from the BTC price when that hour began (that day's where
  there's no hourly price), shown as "From the price", priced again when
  you change its amount or time, and listed with the report's other values
  from a price. The FMV box's **Refresh** button is gone: like an income
  value, a blank one is filled when you save. A value you type, $0
  included, is kept. With the price source Nobody (or no price found) it
  stays blank. **Ledger Review** gets a check, "Gifts, donations and lost
  coins with a $0 or blank value", that also finds the ones earlier
  versions saved blank: saving one again fills it (a $0 one: clear its
  FMV first). A gift, donation or loss is not a sale, so no gain changes;
  nothing already saved changes either. The CSV file gains an `fmv_typed`
  column, so a re-import keeps where the value came from. This adds a
  database column (migration 0011, `fmv_from_price`).

- **The Mac app says when it has no AI key, and how to get one** (#238).
  If the app can't write its AI key file when it starts, it runs with no
  key until **Reset key** (or the next start). Settings › Connect an AI
  Assistant now says "No AI key yet: press Reset key." instead of only
  describing the key file. And the AI connector, finding no key file, or
  one whose app is gone, adds "or, if it's open, press Reset key in its
  Settings (Connect an AI Assistant)" to "Open the BitcoinTX app and try
  again": an open app that couldn't write its key has no file on its first
  start, and leaves the earlier run's file after that.
  `mcp_server/AI_SETUP.md`'s troubleshooting says the same.
- **The sidebar's price says where it came from and when** (part of
  #208). Under the Sats Converter's Auto price, a short line names its
  source and time as the Dashboard does: "Kraken · 2:04 pm", "Kraken,
  through Tor · 2:04 pm" or "Your Mempool · 2:04 pm" (pointing at it shows
  the Dashboard's words). It's one line however narrow the window, so the
  calculator below doesn't move when you switch modes. Right after a new
  price choice is saved, the sidebar shows "…" until the new price comes,
  and an answer for the old choice still on its way is dropped (#327: it
  could replace the new one). Clicking the mode already in use (Auto,
  Manual or Date) no longer clears it: Auto chosen again showed "…" until
  its next poll, two minutes later (#328).
- **The sidebar asks "Is Tor running?" when Tor doesn't answer** (part of
  #208 and #241). When public price sites are asked through Tor and none
  could be reached through it, the sidebar now says "Is Tor running?"
  beside **Type a price**, as the Dashboard and the price card do. When a
  site answered with a refusal, as Bitstamp does Tor's exits (#241), it
  doesn't ask, since Tor is running; the price card has said what to do
  then since 1.2.8 (#240).
- **A blank value's hint says where its price comes from** (part of
  #208). In the transaction form, the hint under a value BitcoinTX fills
  from the price when left blank (an income or rebate deposit's value, a
  spend's proceeds, a gift's, donation's or lost coins' value, a BTC fee's
  value) now ends with where that price comes from, as BitcoinTX looks it
  up:
  - with the hourly history downloaded: "Hourly prices from 2013 to Oct
    12, 2026 are stored in BitcoinTX; newer ones come from public price
    sites" (or "your Mempool, else public price sites" with its backup, or
    "your Mempool where it has them; otherwise type it" without);
  - before that: "It comes from public price sites" (or your Mempool with
    its backup). Your Mempool alone has prices only from when it began
    recording, so the hint says to type an older hour's value. Through
    Tor, where Bitstamp refuses BitcoinTX's requests (#241), it says an
    older hour may need typing;
  - with Nobody it says to type it; before a source is chosen or
    confirmed, where to do that; and on StartOS with Mempool chosen but
    not installed, that it isn't installed yet.

  An inheritance's value (the date of death's price) says the same where
  none would be found, Tor included.
- **"Recommended" beside "Chosen" when StartOS set your Mempool** (part of
  #208). On StartOS, with **My Mempool on this server** chosen in the Price
  Source & Privacy action and Mempool installed, Settings › Privacy &
  network marks it "✓ Chosen" and "Recommended", as the action does. The Mac app and Docker never mark
  one: finding a Mempool would mean asking your network before you choose.
- **The AI connector says which price a value it filled came from**
  (#208). When BitcoinTX fills a value from the BTC price (an income or
  rebate value, an inheritance's value at its date of death, a spend's
  proceeds, a gift's, donation's or lost coins' value, a BTC fee's value),
  `preview_transactions` (each row's `simulated.from_price`),
  `add_transactions` (each created row's `from_price`),
  `list_transactions` and `update_transaction` (`from_price`) now say
  which values and that price: the hour it began (or the day, where
  there's no hourly price, and for an inheritance its date of death) in
  UTC, where it came from and USD per BTC. The values are named as the
  transactions API names them (a spend's `gross_proceeds_usd`, before its
  fee), and the preview now also gives them (`gross_proceeds_usd`,
  `fmv_usd`, a BTC fee's `fee_usd`). The transactions API lists them too
  (`values_from_price`). The AI guide asks the AI to tell you, e.g. "cost
  basis $5,008.30: 0.1 BTC at $50,083.00, the price at 14:00 UTC on
  2024-03-01 (Bitstamp)". Only `get_btc_price` and the tax report said it
  before. The AI key reaches no new route.
- **The server runs Python 3.13** (the Docker image and the StartOS
  package, #425; the owner's choice for 1.2.9, 2026-10-17). It ran Python
  3.11, which gets security fixes until October 2027; 3.13 gets them until
  October 2029, so the stable 1.2.9 keeps a supported runtime longer. The
  Mac app already ran 3.13 (#284), and the automatic tests already ran on
  it. The packages and their versions are the same. Checked before the
  change: everything the app produces (figures, IRS forms, reports, CSV
  files, API answers, error messages) for the reference and random test
  ledgers, with the same code inside the 3.11 image and the 3.13 image,
  showed no difference; and on a StartOS test server, Start9's 1.2.8:0
  updated to a 3.13 build kept every stored figure, with the IRS forms and
  CSV files byte for byte the same. CI's checks of the image (the smoke
  test, the click-through tests, the dependency audit) and the release
  jobs run 3.13 too; running from source still works on 3.10 and later.
  Nothing to do.

### Fixed
- **Two different price-setting saves at the same moment: the later one is
  the one in use** (#435). Saving Settings → Privacy & network from two
  tabs or browsers at the same moment, with different choices, could leave
  BitcoinTX using a mix of the two that neither tab chose, and it could be
  less private than both: public price sites through Tor in one tab and
  Nobody in the other could leave public sites allowed with no proxy, so a
  price lookup could go to a public site without Tor. The database held the
  later save; the mix lasted until the next save, a restore or a restart.
  Every version from 0.9.2; and from 1.2.2, a restore started while a save
  was being made could keep a mix of the two in the restored database. Now
  the price settings are read in one go, and read back into memory one
  reading at a time, so the last save is the one in use (this release's
  answer about the price history without Tor included) and a restore keeps
  one save's settings. Only your own two saves within a moment of each
  other could cause it (these settings are login only, never the AI key),
  and on StartOS with Tor from its Price Source & Privacy action the proxy
  couldn't drop out. Nothing to do.
- **Two saves of a setting at the same moment both work** (#398). Saving
  a setting for the first time (the price choice in Settings → Privacy &
  network, the answer about the price history without Tor, the AI access
  switch, an AI key, the tax timezone) from two tabs or browsers at once
  failed one of them with a server error (a 500; the server's log said
  "UNIQUE constraint failed"); nothing was lost or wrong, and trying again
  worked. Now each setting is
  written in one step (`models/app_setting.save_setting`), so both saves
  land and the later one's value is kept, as when a setting already saved
  is changed in two tabs: of two AI keys made at once, the later one works.
- **No save asks for a price while it holds the database's lock** (#426).
  A recalculation that prices an old transaction's missing value (from
  Recalculate Ledger, in the app or StartOS's action, an edit, a delete, a
  transaction or an import dated before others, a change of the tax
  timezone, or Ledger Review's pricing at the hour), a Spent's proceeds
  left blank (priced once its row is written), or a price an import's
  first look missed, was asked for from the price sites or your own
  Mempool while BitcoinTX held the database's lock, so a save of yours
  made meanwhile failed after 5 seconds. Now such a save stops before
  asking, lets go of the lock, finds the price, and starts again. No
  figure changes: each value gets the price it got before, and one that
  can't be priced is refused as before (a 422 naming the transaction,
  never $0).
- **A save of several rows no longer holds your other saves up while it
  looks for prices** (#421; #426 in part). An import, or the AI
  connector's preview or add, prices its later rows (a BTC fee, an income
  value, a gift's value) after the earlier ones are written, holding the
  database's lock from then on. While BitcoinTX was still downloading a
  year of hourly prices (a fresh install, or after a failed download, with
  public price sites allowed) it waited up to 30 seconds for that year
  there, and a price not stored yet was asked for from the price sites or
  your own Mempool there, so a save of yours made meanwhile failed after 5
  seconds. Now an import or the AI's preview or add finds its rows'
  prices before it writes anything, waiting for a year's download once,
  and a save that has started writing never waits for the download. A row
  that can't be priced at its hour while the year is still downloading
  takes the day's price, marked so, which Ledger Review's check of values
  priced at the day can price at its hour later; once the download is
  done, prices are as before. The rest of #426: the entry above.
- **A withdrawal short of bitcoin says "withdraw"** (#415). Its refusal
  read "Not enough BTC to withdrawal 0.70000000 BTC", the type's name in
  place of the verb; it now reads "Not enough BTC to withdraw …", in the
  app, the AI connector and the command line. A sale's ("to sell") was
  right already. The wording only: no figure changes.
- **A River auto-withdrawal is imported as a move to your wallet, and a
  River mining payout as income** (tax figures, #397, #399). River's
  activity file tags bitcoin sent by an auto-withdrawal `Withdrawal`: River
  sending your balance to the address you set, normally your own wallet. The
  River import read the tag as bitcoin that had left your hands, and
  suggested each such row as a Withdrawal with purpose Spent. Kept as
  suggested, a move to your own wallet counted as a sale on Form 8949 (a
  gain or loss that didn't happen), and the coins were missing from your
  Wallet's balance, so a later sale from it took the wrong lots. A row
  tagged `Mining` (a River mining payout) was skipped with a warning, so its
  income was left out unless you added it by hand. Every version from 0.7.0
  (the River import) to 1.2.8. Now an auto-withdrawal is suggested like any
  other send from River, a Transfer from Exchange BTC to Wallet with River's
  network fee (you can still make it a Withdrawal in the preview), and a
  mining payout as a deposit into Exchange BTC with source Reward: income,
  valued at the hour it arrived. Importing a file again finds an
  auto-withdrawal you saved as a spend, so it isn't added twice. River's
  network fee on a send is on top of its Sent Amount, as the import already
  read it: River's record of a send gives its total as Sent plus Fee (#39).
  **Affected:** only ledgers with River files holding auto-withdrawals kept
  as suggested, or mining payouts.
  **What to do:** in Transactions, look for withdrawals from Exchange BTC to
  External with purpose Spent on the days of River's auto-withdrawals. If
  the bitcoin went to your own wallet, delete each one, then import that
  River file again: it suggests them as Transfers to Wallet, and a mining
  payout the import skipped as a Reward deposit. Rows already in your ledger
  are left out. A row marked Review, which only looks like one of yours, is
  ticked when its amount is the same: untick any you entered yourself, such
  as a mining payout you added by hand. If you filed a return from
  BitcoinTX's figures, such a sale, or income left out, would be in that
  year.
- **The password forms count characters as the server does** (#405).
  Create account, Settings' password change and the Mac app's "Choose your
  username and password" counted an emoji as two characters, so a password
  of 6 emoji passed the form, then the server refused it with the
  12-character rule. They now count the way the server does. The server's
  rule itself is unchanged.
- **A gift, donation or lost coins saved in the form is no longer a $0 sale
  when it's made a Spent later** (tax figures, #457). Saving one in the
  edit form, even unchanged, stored a hidden $0 as its proceeds. Made a
  Spent afterwards through the AI connector or the API without proceeds
  (the connector's `update_transaction` sends only the purpose), it kept
  that $0: a sale at $0, its whole cost basis a loss on Form 8949, where
  the same gift never saved in the form was priced at the hour. Changed
  into a Sell the same way, it was saved as a $0 sale instead of being
  refused. A dollar withdrawal saved in the form held the same $0, and
  moved to a bitcoin account as a Spent it was a $0 sale too. Every version
  from 0.8.0 to 1.2.8. Now the form sends proceeds only with a Spent, and
  an edit keeps none sent for any other withdrawal. One made a Spent with
  no proceeds given is valued from the BTC price, as a new Spent left blank
  is, unless it holds proceeds above $0 from when it was a spend, which are
  kept as typed. A Sell made of one needs its proceeds.
  **Affected:** only a gift, donation, lost coins or dollar withdrawal
  changed afterwards into a Spent or a Sell through the AI connector or the
  API (in the form, the change showed Proceeds 0 and its warning).
  **What to do:** open Ledger Review: it lists such a spend under "Spent
  withdrawals saved with $0 proceeds". If it was really a sale, open it and
  clear Proceeds (it's valued from the BTC price) or type what you
  received. A $0 Sell isn't listed there: look in Transactions for a Sell
  showing no proceeds. If you filed a return from BitcoinTX's figures, such
  a sale would be in that year.
- **An old Spent withdrawal opens in the edit form with what it received**
  (tax figures, #485). A spend saved before 0.8.0, when BitcoinTX didn't
  yet keep a withdrawal's proceeds before fees, opened in the form with
  Proceeds 0 and its warning, so a save, even unchanged, made it a $0 sale.
  The form now shows the proceeds BitcoinTX recovers for it, as a
  recalculation does: what was stored, with the fee deduction those
  versions made undone. An old withdrawal of a purpose BitcoinTX doesn't
  list shows what it recorded as received. Every version from 0.8.0 to
  1.2.8.
  **Affected:** only a ledger from before 0.8.0 with no recalculation since
  (any edit or deletion, an add dated before the latest transaction, or
  Recalculate Ledger fills those proceeds in for good).
  **What to do:** only if you saved such a spend in the form: Ledger Review
  lists it under "Spent withdrawals saved with $0 proceeds"; open it and
  type what you received.
- **An old gift, donation or lost coins saved with spaces in its purpose is
  no longer a sale** (tax figures, #342). Before 0.9.2 BitcoinTX saved a
  withdrawal's purpose and a deposit's source as typed (and a source it
  didn't list yet, such as `" rebate "` or `" inherited "`, until 1.1.0),
  so an old ledger can hold `" gift "` or `" Income "`. The screens read
  those as Gift and Income, but the figures didn't:
  - a bitcoin withdrawal of `" gift "`, `" donation "` or `" lost "`
    counted as a sale on Form 8949 (at $0 when nothing was recorded as
    received, so its whole basis showed as a loss), and was missing from
    the tax report's gifts;
  - a deposit of `" Income "`, `" Interest "` or `" Reward "` was left out
    of the income totals, `" rebate "` out of the rebates, and an
    `" inherited "` one was missed by Ledger Review's checks of Inherited
    deposits (it was already long-term).

  Every version through 1.2.8. Now each counts as its listed spelling,
  everywhere, and the tax report prints that spelling. An old `" spent "`
  works differently: versions through 1.2.8 didn't count it as Spent, so
  it counts as the entry on purposes BitcoinTX doesn't know (#61, below)
  describes, and the change shows in Ledger Review's "Figures that
  Recalculate Ledger would change". With nothing recorded as received,
  Ledger Review also lists it among withdrawals whose purpose it doesn't
  know. **Affected:** only
  ledgers started before 0.9.2 (or 1.1.0, for those two sources) that hold
  such a row; Gift, `"GIFT"` and blank always counted the same on the
  screens and in the figures.
  **What to do:** Ledger Review's "figures a recalculation would change"
  shows what moves. Then Recalculate Ledger (any edit or delete does it
  too). If you filed a return from BitcoinTX's figures, a gift, donation or
  loss listed there as a sale, or income left out, would be in that year.
- **A tax timezone name that isn't a zone is refused, not a server error**
  (#384). Saving a tax timezone named like a folder of zones (`America`),
  with a name hundreds of characters long, or with a part named like a
  module of the zone package (`America/__init__/x`) answered "Internal
  Server Error" instead of "Unknown timezone". Nothing was saved either way. Settings
  offers only real zones and the login page sends the browser's, so only
  a hand-made request could send one. **Affected:** every version since
  0.8.0 (Settings' save), and this version's login fill. Nothing to do.
- **A tax timezone name only one computer knew no longer breaks the
  reports after a restore** (#407). BitcoinTX saved any timezone name the
  computer's own zone files opened, and that differs between computers: on
  a Mac `america/chicago` (in any case), `utc` and `posixrules`; in the
  Docker image and on StartOS `localtime` and `posixrules`. Restored on
  another computer, such a name made the tax forms, the reports and the
  gains page fail with a server error (a 500) until a timezone was saved in
  Settings again; nothing was lost. Only a hand-made request could save
  one: Settings and the login page send names from the browser's own list.
  Now BitcoinTX takes only the names of the timezone package it ships with
  (`tzdata`), the same list on every computer. A restore whose backup holds
  another name keeps this install's tax timezone (none chosen: UTC or
  `BTCTX_TIMEZONE`, as before) and says so, waiting for you to read it
  before the login page: check the timezone in Settings → Account, then run
  Recalculate Ledger there, so the restored ledger is worked out in it. An
  install that already holds such a name keeps working with the same
  figures: a case variant is read as its proper name (`America/Chicago`),
  another name as before where the computer opens it, and one it can't open
  (from a restore) counts as none chosen, where every report failed (the
  server's log says so once). The upgrade to 1.2.9 (migration 0012)
  reads it the same way, so such a name never stops the upgrade.
  The AI connector says plainly that its computer doesn't know the tax
  timezone, where some names failed with a raw error. The trade-off: a
  timezone newer than the shipped `tzdata` is refused until an update
  brings it.
- **A login no longer changes the tax timezone of a ledger with
  transactions** (tax figures, #334). While no tax timezone had ever been
  chosen (Settings showed UTC, and no `BTCTX_TIMEZONE`), every login saved
  the browser's timezone as the tax timezone and recalculated the ledger,
  without a word. A browser that reports UTC, such as Tor Browser, left it
  alone. So a Docker or StartOS ledger entered so far only from such a
  browser (or a restored backup that carried no timezone) switched at its
  first login from an ordinary browser. The tax timezone decides the dates
  that count for tax, so in years already filed a sale near midnight or
  near its one-year anniversary could move to another tax year or term, an
  income or rebate deposit near New Year's Eve to another year, and Form
  8949's printed dates and the year-end holdings could shift. Every version
  from 0.8.0 to 1.2.8. Now a login fills the timezone only while the ledger
  has no transactions, as on a fresh install or the Mac app's first login,
  and a page left open from before the update can't set it either. With
  transactions, only you change it, in Settings, which says what that does
  and, while none was chosen, suggests this computer's timezone in one
  line (saving the one shown, UTC included, ends the suggestion).
  **What to do:** check Settings › Tax Timezone. If the timezone shown is
  where you file, today's report is the right one; if a return you filed
  differs from it, ask your tax preparer whether to amend it. If it isn't
  where you file, choose the right one there (saving recalculates).
- **StartOS: a dismissed Recalculate Ledger task no longer comes back at
  every server restart** (#365). After an update that asks for Recalculate
  Ledger (1.2.8:0 does), StartOS raised the task again each time the server
  started, until its action ran: dismissing it, or recalculating in
  BitcoinTX's own Settings, never settled it. Every package version since
  the task came in (0.9.0); nothing in the ledger was ever wrong. Now it asks
  once per such update, as 1.2.8 meant to, and again after restoring a backup
  on which the recalculation is still due: the task stays until the action
  runs or you dismiss it. If you dismissed it on 1.2.8 without running the
  action, it comes back once, at the next update. Its text now says to run
  the Recalculate Ledger action in StartOS once, after Ledger Review. It
  reaches StartOS with the next package release.
- **A transaction naming an account that doesn't exist is named when it
  stops a save** (#337). Before 0.9.2, BitcoinTX saved a transaction
  naming any account number, even one with no account; and deleting an
  account left the transactions naming it with none. A transfer, deposit or
  withdrawal between one of your accounts and such a missing one stops
  every replay of the ledger, so every save that recalculates (an edit, a
  delete, an entry dated before the latest), Recalculate Ledger and Ledger
  Review's check failed with "Ledger not balanced for BTC" or "would lack
  BTC", naming neither the transaction nor the account; Settings ›
  Recalculate Ledger only said it failed. Now:
  - the message names both, with the date ("Transaction 970 (a Transfer of
    2024-02-01) names account 999, which doesn't exist…"), and Settings ›
    Recalculate Ledger shows it;
  - **Ledger Review** has a check, "Transactions naming an account that
    doesn't exist", listing every such transaction (and it shows a move of
    dollars in dollars, not "500.00000000 BTC");
  - an account that transactions name can't be deleted ("Not deleted: 1
    transaction names Old wallet…").

  **What to do:** edit each into one of your accounts, or delete it, one
  at a time. With more than one that stops saves, each edit or delete of
  one was refused too, naming another, so none could be fixed in the app
  (#368). Now an edit or a delete of such a transaction goes on past the
  others, replaying them as BitcoinTX replays one that doesn't stop saves;
  they still stop every other save, by name, until they're fixed. If that
  leaves a later transaction short of BTC, the refusal names the others it
  went past: fix the one that's why first. Until the last is fixed, the figures
  (Form 8949, the dashboard) can be off: fix them all before relying on a
  report. No figure changes for a ledger without them: it replays as
  before, and only the message differs.
- **Text that isn't text is refused, not a server error** (#313). A JSON
  string can hold a lone surrogate (`"\ud800"`): JSON allows it, but it
  isn't a character and can't be saved. Sent in a transaction's purpose, an
  AI entry or the tax timezone, it gave a server error (500), with nothing
  saved. Now every JSON request holding one is refused, once its login is
  checked and before its route runs, with a 422 naming the field, whether
  the JSON is in UTF-8, UTF-16 or UTF-32. The login and the account routes keep their own answer
  (#210). A backup's password, which a form's charset can turn into such
  text, is refused the same way when you download or restore a backup. A
  request whose body isn't UTF-8 text, sent without a JSON type, also gave
  a 500 instead of its 422. No form in the app and no AI connector tool
  sends such text.
- **A save made while Ledger Review checks the ledger no longer fails**
  (#335). Ledger Review (also `cli review` and the AI connector's
  `review_ledger`) works out what Recalculate Ledger would change by
  running it and undoing it. It ran on the live database, holding its
  write lock for the whole replay, so a transaction saved meanwhile, yours
  or the AI's, waited and after 5 seconds failed with "database is locked".
  On a ledger of a few thousand transactions the replay takes longer than
  that. It now runs on a copy of the database in memory, as the tax
  report's year-end holdings already do: saves go through, and the check
  finds the same changes. Nothing was ever half-saved: the save was
  refused whole. Also in Ledger Review: when its check of what Recalculate
  Ledger would change fails on something unexpected, it says so in plain
  words (BitcoinTX's log has the details) instead of showing an error's
  technical text, and `cli review` shows that line too. A transaction
  deleted while the check runs, or while you apply the hour's prices, is
  left out instead of causing a server error.
- **A price lookup under way when you change the price settings follows
  your new choice** (#437). A lookup of a past price asked your own
  Mempool first, waiting for it up to a minute and a half when it was slow
  or down, and then asked the public sites if your choice allowed them
  when the lookup started, through the proxy set by the end of that wait.
  So if you saved a choice without public sites and without a proxy
  meanwhile (Nobody, or your Mempool with no backup and no proxy), it
  still asked a public site, and directly, not through Tor: something
  neither choice allowed. The live price, the block height, a download of
  several blocks and a request to your own Mempool could do the same
  within a much shorter moment (an .onion Mempool's name could then go to
  this server's resolver). During the Mempool's wait: every version from
  1.1.0; within a moment: every version from 0.9.2. Now each request is
  sent only as the settings in use at that moment allow: never to a public
  site once they aren't allowed, never through another proxy than the one
  in use, and never to a Mempool address no longer chosen; a request they
  don't allow is refused before it's sent, and the daily history, the
  latest days and your Mempool's history are asked again at the next
  lookup, as the new choice says. Only your own change of these settings
  while a lookup was under way could cause it (they're login only, never
  the AI key), and no figure is affected. Nothing to do.
- **After you change your Mempool's address, its prices are the new
  Mempool's** (#473). BitcoinTX keeps your own Mempool's answer for 10
  minutes, so the day and hour lookups share it. If you changed the
  address while a lookup was still waiting for the old Mempool, and another
  lookup asked the new one before the old one answered, the old one's late
  answer was kept as the new one's: for the rest of those 10 minutes, every
  value priced from your Mempool had the old server's prices, and so did
  the days and hours stored then (a day lookup stores every day of the
  answer not stored yet). In 1.2.8 (the kept answer came with the hourly
  prices, #144), for a price of any tax year. Now an answer is kept only
  while it's the last one asked: the old Mempool's late answer is used, and
  stored, only by the lookup that asked for it before the change, as the
  answer to any request sent before a save is (#437). Two Mempools' prices
  usually agree closely, so a figure was wrong only where the old one's
  were off. Only your own change of that address could cause it (login
  only, never the AI key), and nothing was sent to an address no longer in
  use. Nothing to do, unless you changed your Mempool's address in 1.2.8
  because its prices looked wrong. Then a stored price can still be the
  old Mempool's (a stored price never changes): check the values priced
  from your Mempool since that change (the Complete Tax Report lists the
  price each used and where it came from) and type the right value into
  any that differ.
- **An .onion Mempool address however its dots are typed is reached
  through Tor** (found by the review of #443). Typed with a dot at its end
  (`http://….onion.`, the same address) or with a full stop that web
  addresses take for a dot (`。`, `．`), it wasn't taken for an .onion: it
  was asked directly, even with Tor set, so its name went to this
  server's resolver; and it could be saved without Tor. Now it's an
  .onion like any other, in Settings and on the server: it needs Tor, and
  goes through it. An address whose host has a character no host name has
  (a backslash, a `%`), which went around Tor the same way, is now refused
  when saved (or, set by the server, makes its price settings invalid),
  and one saved before is never asked until you correct it. Nothing to
  do, unless you typed your Mempool's address with such a dot without
  Tor: Settings now offers Tor for it when you next save, and BitcoinTX
  asks that Mempool nothing until then.
- **A save made while Ledger Review looks up a price no longer fails**
  (#364). When one of Ledger Review's checks needed a BTC price not stored
  yet (with a price source chosen), it stored the price in the review's own
  database transaction and held the write lock until the review ended: a
  transaction saved meanwhile, yours or the AI's, waited and after 5
  seconds failed with "database is locked". The AI connector's preview and
  add, and the River import's preview, looked their prices up the same
  way. A price found is now stored at once, in a short transaction of its
  own (within a save that has already written something, such as an
  import's later rows, it goes with that save), so saves go through. What
  Ledger Review shows doesn't change, and a stored price still never
  changes. Nothing was ever half-saved: the save was refused whole.
- **An edit made while the hour's prices are applied keeps its own value**
  (tax figures, #387). Ledger Review's "apply the hour's prices" worked
  out each new value from the transaction as its check had found it, made
  the backup copy, then wrote that value. A transaction edited in those
  few seconds (its amount or its time changed) got the value worked out for
  its old amount or hour: for example $4,000 for 0.2 BTC that the hour's
  $40,000 values at $8,000. The apply now takes the database's write lock
  right after the copy, so an edit made from then on waits until it's done,
  and works each value out again from the transaction as it is then. While
  another save holds the lock too long, nothing is applied, and it says
  so. **Affected:** 1.2.8, only a transaction edited while the apply ran
  (by you in another window, or by the AI); not seen in real use. **What
  to do:** nothing, unless you edited a transaction while applying the
  hour's prices: then open it and, if its value doesn't match its amount,
  clear the value to price it again at its hour.
- **A transaction you told the AI is another one no longer depends on the
  rows' order** (tax figures, #497, #510). Two cases in the AI connector's
  duplicate check:
  - **A row named as another transaction** (`not_a_duplicate_of`) **beside
    an identical row without a name.** The same request can be a first
    send naming a new payout, or a send of two payouts already recorded.
    The check decided by the rows' order: one order saved an extra payout
    (income) or purchase, the other saved none. Now it never guesses (the
    owner's rule): the preview marks those rows unclear, saying which rows
    and what to do. The AI's add refuses them until the AI names each row
    or sends the named one in a request of its own.
  - **Identical rows, each named as the transaction its preview matched.**
    They were all saved in the preview's order and all left out in another,
    so payouts went missing. Now every transaction a row names is set
    aside for all the rows, so a name means the same in any order.

  **Affected:** no release: telling the AI a duplicate is another
  transaction is new in this version (#253). Nothing to do.
- **A different transaction of the same amount is no longer skipped as
  already recorded** (#253). The AI connector (`add_transactions`) and the
  River import treated a new transaction as already in the ledger when one
  of the same kind and BTC amount was recorded within 48 hours, whatever
  its source or value, and skipped it: two Interest payouts of the same
  amount a day apart, or an Inherited deposit beside an Interest deposit of
  the same amount and time. The skipped one's income and cost basis were
  missing from every report. Every version since 0.7.0 (the River import)
  and 0.8.0 (the AI connector, which reused its check); verified in 1.2.8.
  Now (the owner's rule):
  - **A duplicate** is the same kind, BTC amount and minute as a recorded
    transaction. The AI connector also compares the source or purpose, and
    a Buy's price, and a date given alone matches that day. A duplicate is
    left out by default, and you can override it: tick it in the River
    preview, or tell the AI it's another transaction.
  - **A similar row,** the same amount within 48 hours with anything else
    different, is never skipped by itself. It's shown with the match and
    what differs, and saved unless you remove it; in the River preview it
    starts ticked (it used to start unticked). A River bitcoin move (a send
    or a receive) whose amount is only near one you typed by hand (within
    20 %) still starts unticked, as before: it's most likely that move,
    typed with a rounded amount.
  - A River row compares nothing else, and its amount is River's: its
    source, purpose, fee and type are the preview's or your own edits, so
    a re-import of a row you changed isn't recorded twice.
  - Also fixed at the River import's save: a row the preview showed as New
    beside an identical one already in the ledger was skipped all the same.
    The import now keeps each match the preview made, ticked or not, and
    whatever you edited, so it saves exactly the rows you tick.

  **What to do:** if you added transactions through the AI connector or
  imported River files, check that payouts of the same amount within two
  days of each other (interest, rewards, sats-back) are all in your
  ledger, against River's statement or your own records. Previewing a
  River file again shows a payout the old check skipped as New or Review.
  Any tax year with such imports can be affected.
- **A payout given to the AI as a date alone beside a timed copy of it
  is the one saved, at noon** (tax figures, #472). When a request held the same
  payout twice, once as a date alone and once with a time after noon, and
  the ledger had it once, at that time, the duplicate check gave the
  recorded payout to the date-alone row and saved the timed row: a second
  payout at the recorded one's exact minute, valued (when its value came
  from the price) at that hour's price instead of noon's. Now the timed
  rows are matched before the date-alone rows: the timed row is the
  recorded one, and the date-alone row is saved, at noon. For a request
  with no row named as another transaction, how many rows are saved
  doesn't change. **Affected:** no release: matching a date alone is new
  in this version (#253). Nothing to do.
- **A payout given to the AI as a date alone no longer takes a timed one's
  place** (tax figures, #411). The AI connector's duplicate check gave each
  row, in time order, the nearest recorded transaction it matched, and a
  row given as a date alone matches the whole day, so it could take the
  copy that was a timed row's only match. Sent again (a retry), the timed
  row was saved twice; on a first send it was shown as a possible
  duplicate and saved unless you removed it: an extra payout (income) or
  purchase. Now the rows are matched so that each finds a copy when the
  ledger holds one for each. **Affected:** no release: matching a date
  alone is new in this version (#253). Nothing to do.
- **The same rows sent twice at once are saved once** (tax figures,
  #454). An add through the AI connector checked the ledger for its rows
  and then saved them, as two steps, so a second request with the same
  rows that checked before the first had saved found nothing and saved
  them again. That happens when the connector gives up waiting (after
  120 s, while BitcoinTX looks up prices, through Tor especially) and the
  AI sends the add again, as the ledger guide says is safe; BitcoinTX
  finished the first request all the same. It happens too when an AI app
  sends two adds at once, or a River or CSV file is imported in two
  browser tabs at once. The check and the save now hold the database's
  lock together: the second request waits for the first, then finds its
  rows and leaves them out (the CSV import says the ledger isn't empty);
  one kept waiting past 5 s is refused as busy, nothing saved, to be sent
  again. The prices are still found before, with the lock free.
  **Affected:** every release (the AI connector's add since 0.8.0, the
  River import since 0.7.0, the CSV import before them), any tax year.
  **What to do:** if the AI connector ever told you an add failed or timed
  out, an AI app sent the same add twice, or you imported a River file in
  two tabs, look in Transactions for a transaction recorded twice (the
  same type, amount and time, next to each other) and delete the extra
  copy. A CSV file imported in two tabs at once saved every row twice:
  delete the second copy of each row, or Delete All, import the file once
  and add again anything you entered after it.
- **A transaction you told the AI is another one is saved once, even if
  the request is sent again** (tax figures, #378). When you told the AI
  that a duplicate was another transaction, a second send of the same
  request (a retry after a timeout, say) could save extra copies: with two
  or three identical rows marked that way, one after an identical row that
  wasn't, or one beside the same payout given as a date alone. Now the AI
  names the transaction the row isn't (the one the preview matched,
  `not_a_duplicate_of`, as River's import already keeps its matches), so a
  request sent again finds the copies the first one saved. **Affected:**
  no release: telling the AI a duplicate is another transaction is new in
  this version (#253). Nothing to do.
- **A sale edited through the API is checked with the proceeds it sends**
  (tax figures, #458). An edit of a Sell sent to BitcoinTX's API
  (`PUT /api/transactions/{id}`) with its proceeds as `proceeds_usd` was
  checked against the sale's old proceeds (before 0.9.2, not checked at
  all), then saved with the new ones: blank proceeds (`null`) saved a $0
  sale, its whole cost basis a loss on Form 8949, and proceeds below the
  sale's USD fee were kept, its net proceeds $0. Blank proceeds sent as
  `gross_proceeds_usd` were saved too, the proceeds made up again from the
  old net and the fee; and `proceeds_usd` sent beside a blank
  `gross_proceeds_usd` was saved as the net, the fee added on top, so the
  sale's proceeds on Form 8949 were too high by the fee. Creating such a
  sale is refused, and now so is the edit, with the same message ("A sell
  needs its proceeds", "The sell's fee is more than its proceeds."); and
  proceeds sent beside a blank gross are the gross, as when the sale is
  created. **Affected:** every release to 1.2.8, any tax year, but
  only edits a script or another program sent to the API: the app's form
  and the AI connector never sent one. **What to do:** if a program of
  yours edits sales through the API, compare each sale's proceeds on the
  Transactions page with your exchange's record (Ledger Review doesn't
  list a sale with $0 proceeds) and correct any that differ.
- **Cost basis is claimed to the cent** (#100). When a lot of bitcoin was
  sold, spent, paid out as network fees or moved in pieces, each piece's
  cost basis was its share of the lot's cost rounded to the cent on its
  own, and an exact half cent was rounded down. So a lot's pieces could add
  up to a few cents more or less than what it cost (up to half a cent a
  piece; most with many tiny disposals, such as network fees of a few
  hundred satoshis), and gains could be off by those cents either way. Every release from 0.8.0 (the
  oldest tagged) to 1.2.8. Now a lot's cost is claimed as a running total:
  each piece costs what the lot's bitcoin taken so far costs with it, less
  without it, so a lot's pieces always add up to exactly what it cost, and
  what's still held carries the rest. An exact half cent rounds up, as the
  IRS rounds to whole dollars, both for a piece's cost and when a sale's or
  spend's proceeds, or a fee's value, are shared among lots. On the
  reference test ledger, cost basis rises and gains fall by 1 to 2 cents a
  year (2024–2026, long-term); no proceeds and no year-end holdings total
  changes.

  **What to do:** nothing urgent; the difference is cents. A ledger saved
  by an earlier version keeps its figures until it's recalculated: run
  Recalculate Ledger (Settings) to bring them up to date; Ledger Review
  lists the transactions it would change first. Any tax year with a lot
  sold, spent or moved in pieces can be affected, by a few cents either
  way.
- **A Buy is never saved without its cost basis** (#459). The transactions
  API saved a Buy sent without a cost basis (every release from 0.8.0, the
  oldest tagged, to 1.2.8). So did an edit that made a transfer, a dollar
  deposit or a dollar withdrawal a Buy without giving one (the same
  releases), or a sale or a bitcoin withdrawal (from 1.2.2, when a type
  change began to drop the old type's figures; before, the Buy kept the
  cost basis stored on the sale or withdrawal). A dollar deposit made a
  Buy that way kept its own cost basis as the Buy's: $0 on one entered
  with the form before 0.9.2. The AI connector's `update_transaction` can send that
  edit when it isn't given the cost. The Buy's bitcoin then cost $0: selling
  or spending it later counted the whole proceeds as gain, and the
  year-end holdings' cost and the dashboard's average cost were low by the
  missing amount. The form, the CSV and River imports and the AI
  connector's add never saved one without it. Now such a save is refused,
  saying the Buy needs its cost basis; a basis of 0 you type is still
  kept. Ledger Review lists every Buy with a $0 or blank cost basis ("Buys
  with a $0 or blank cost basis"). An edit of an old Buy with a blank
  basis, through the API or the AI connector, asks for it; the form shows
  its Amount USD as 0 until you enter what it cost.

  **What to do:** open Ledger Review (Settings). For each Buy it lists,
  edit it and enter what the bitcoin cost in USD, before the fee (Amount
  USD); the save recalculates the ledger. Any tax year in which coins from
  such a Buy were sold or spent can be affected, its gain too high by the
  missing basis. A ledger entered only with the form or the imports has
  none.
- **A dollar deposit moved into Wallet or Exchange BTC asks for the
  bitcoin's cost** (#517). An edit that moved a dollar deposit into Wallet
  or Exchange BTC (making it a deposit of bitcoin) kept the cost basis
  stored on the dollar deposit as the cost of that bitcoin, without
  asking: $0 on a dollar deposit entered with the form before 0.9.2, or
  whatever figure a program or a CSV file gave it. (A dollar deposit made
  a Buy instead: the entry above.) Selling those coins later then counted
  the whole proceeds as gain (or a gain off by the difference), and an
  income deposit moved that way reported that figure as its income
  instead of the coins' value. Every release from 0.8.0 (the oldest
  tagged) to 1.2.8, through the API and the AI connector. Now such an
  edit asks for the coins' cost (a My BTC, Gift or N/A deposit), or values
  an income, interest, reward or rebate deposit at that hour's price (an
  inherited one at the price on its date of death, which the edit must
  give), unless it gives one. The form isn't changed: there the Cost Basis
  field shows the figure the deposit had (a blank one as 0), and saving
  keeps what it shows (a 0 on an income, rebate or inherited deposit is
  valued at the price).

  **What to do:** Ledger Review lists a bitcoin deposit with a $0 cost
  basis ("BTC deposits (not income or a rebate) with a $0 or blank cost
  basis"): edit it and enter what the coins cost. An income or rebate
  deposit moved that way with another figure is listed under "Income and
  rebate values you typed, far from that hour's price". Others with
  another figure aren't listed: if you moved a dollar deposit into Wallet
  or Exchange BTC, or made one a Buy, through the AI connector or another
  program, check its cost basis. Any tax year in which those coins were
  sold or spent can be affected, and for an income deposit the year it
  was received.
- **No proceeds row below zero** (#297). When a sale, a spend or a network
  fee took bitcoin from several lots, each lot's share of the proceeds (or
  of the fee's value) was rounded to the cent on its own, and the last lot
  took what was left. The rounded shares could add up to more than the
  whole, so the last row's proceeds came out negative: six 1-satoshi lots
  sold together for $0.03 gave five rows of $0.01 and one of −$0.02. With
  ordinary lots it could happen too, rarely: when a sale reached only a few
  satoshis into its last lot. From 0.9.2 to 1.2.8 for a
  network fee's rows, and from 1.2.2 to 1.2.8 for a sale's or spend's
  proceeds. Now the shares are a running total, like a lot's cost above:
  no row is below zero.

  A disposal's total never changes. Its rows can each move by a cent, and
  its last row by a few cents (at most half a cent for each lot it took
  from). Where its lots fall on both sides of the one-year mark, or in two
  Form 8949 boxes, the Schedule D lines of those terms or boxes (short- and
  long-term, or two boxes' lines such as 1b and 2) can move by those cents,
  one up and one down. On the reference
  test ledger, two rows of one 2026 spend swap a cent, and no Schedule D
  line moves.

  **What to do:** as above, Recalculate Ledger (Settings).
- **A sale edited down to $0 proceeds is a $0 sale** (tax figures, #471).
  Setting a Sell's Gross Proceeds (USD) to 0 in an edit was saved without
  an error but didn't take: the sale kept its old proceeds and gain, and
  its gross came back as the old proceeds ($5,000 with a $10 USD fee,
  edited to $0 and no fee, came back as $4,990). BitcoinTX read a gross of
  $0 as "none recorded", the case of a sale saved before 0.8.0, and took
  the proceeds stored with the sale instead. The same sale created at $0
  was right: a $0 sale, its whole cost a loss. Now a gross of $0 is a $0
  sale however it's saved (an edit, or a request that also sends
  `proceeds_usd`); only a sale saved before 0.8.0, with no gross, is still
  worked out from its stored proceeds.
  **Affected:** 0.8.0 to 1.2.8, for the tax year of any sale edited to $0
  that way: its proceeds and gain on Form 8949, Schedule D, the Complete
  Tax Report and the dashboard, and the Exchange USD balance. **What to
  do:** if you once set a sale's Gross Proceeds to 0 and it came back with
  its old figure, open it and set it to 0 again. Ledger Review and
  Recalculate Ledger can't find such a sale: the old figure is what was
  stored.
- **Ledger Review sees a cent moved between a transaction's rows** (#296).
  Its check of the figures Recalculate Ledger would change compared each
  transaction's totals only. A recalculation that moved a cent between two
  rows of one sale (between a short-term and a long-term lot's row, or two
  rows of one term), or in the cost a transfer carried to its new lot, left
  them the same, so Review said there was nothing to review while Schedule
  D's lines, the form's rows or the coins' cost would change. It now also
  compares each transaction's short- and long-term gains where its rows
  are, or would be, of both terms, and the lots it made and their cost; and
  it lists one whose rows, or lots, alone would be split differently.
  Since 0.9.2 (when the check came in).
- **An old bitcoin withdrawal of unknown purpose counts as Spent, and Ledger
  Review lists it** (tax figures, #61). Since 0.9.2 a bitcoin withdrawal's
  purpose must be Spent, Gift, Donation or Lost, but a ledger started before
  then can hold one with another purpose (such as "Expenses") or none. Such
  a withdrawal counted as a sale: from 0.9.2, one saved before 0.8.0 (which
  kept its proceeds in an older field) that no recalculation under
  0.8.0–0.9.1 had given a recorded gross counted at $0, so its whole cost
  basis showed as a loss on Form 8949; and from 1.2.8, when a Spent's
  network fee became a cost of the spend (#157), its fee wasn't taken off
  its proceeds as a Spent's is. Ledger Review didn't point them out. Now it
  counts as Spent (the owner's rule: a withdrawal is spent, given, donated
  or lost, and an expense paid in bitcoin is a spend, whose deduction, if
  any, goes on other forms): at the proceeds saved with it, with its fee a
  cost of the spend, as for any Spent. One with no amount saved stays as it
  was, a sale at $0, until you enter what it received. Ledger Review lists
  each one, saying what it counts as, so you can confirm Spent or choose
  Gift, Donation or Lost. **Affected:** ledgers started before 0.9.2 with
  such a withdrawal, in the tax year it falls in: its proceeds rise from $0
  to the amount saved (a row saved before 0.8.0 with no recorded gross), or
  fall by its fee's value (one with a bitcoin network fee), and its gain
  with them. **What to do:** open Ledger Review before saving anything:
  "Figures that Recalculate Ledger would change" lists each withdrawal whose
  figures move, and "BTC withdrawals whose purpose isn't Spent, Gift,
  Donation or Lost" lists the withdrawals. Edit each to choose its purpose:
  as Spent, enter what you got for it if none is recorded; a gift, a
  donation and lost coins have no gain. Then Recalculate Ledger (any save
  does it too). One listed as "none recorded": see the next entry.
- **An old sale opens in the edit form with its gross proceeds** (tax
  figures, #476). A Sell saved before 0.8.0 (an imported one, say) may hold
  only its proceeds net of its dollar fee, with no gross. Until a
  recalculation filled the gross in, the edit form showed such a sale's
  Gross Proceeds (USD) as $0, in every release up to 1.2.8: saved unchanged,
  it was refused when it had a fee, and typing the proceeds the transaction
  list shows for it (the net) took the fee off a second time, lowering its
  proceeds and gain by the fee. It now opens with the net plus the dollar
  fee, the gross BitcoinTX itself works out for it at a recalculation, so
  saving it unchanged changes nothing. **Affected:** ledgers started before
  0.8.0 with a Sell that has a dollar fee, edited in the form with the net
  typed as its gross before any recalculation (any edit or deletion, an
  entry dated before the latest, or Recalculate Ledger) had filled the gross
  in; the tax year of that sale. **What to do:** nothing for most ledgers.
  If you edited such an old sale that way, open it: if Gross Proceeds (USD)
  is less than what the sale really brought before the fee, enter that and
  save.
- **A recalculation keeps what an old withdrawal of unknown purpose
  received** (tax figures, #329). A bitcoin withdrawal saved before 0.8.0
  kept what was received in an older field. When its purpose isn't Spent,
  Gift, Donation or Lost (the entry above), BitcoinTX counted it as a sale
  at $0, and up to 1.2.7 a recalculation left that amount alone. 1.2.8 wrote
  $0 over it on every recalculation (Recalculate Ledger, which its update
  asked for on StartOS, an edit or a delete, an entry dated before the
  latest, applying hourly prices), erasing the only record of it. The
  reported figures didn't change, the sale was already at $0, but the amount
  needed to correct it was gone. It is kept again, and counts as that
  withdrawal's proceeds (the entry above). **Affected:** ledgers started
  before 0.8.0 holding such a withdrawal that no recalculation under
  0.8.0–0.9.1 had given a recorded gross, from their first recalculation
  under 1.2.8. **What to do:** in Ledger Review, a withdrawal under "BTC
  withdrawals whose purpose isn't Spent, Gift, Donation or Lost" listed as
  "none recorded" may have lost its amount. The copy of your database
  BitcoinTX made before updating to 1.2.8
  (`backups/btctx-before-schema-0010-….db` in its data folder) still holds
  it, as `proceeds_usd` in the `transactions` table, which any SQLite viewer
  shows. On StartOS that folder, `/data/backups/`, is reached only over SSH
  or in a StartOS backup. Look it up there, then edit the withdrawal: choose
  its purpose and, as Spent, enter it as its proceeds. Don't restore that
  copy over your ledger: everything entered since would be lost.
- **Texts no longer say adding a transaction recalculates the ledger**
  (#172). Ledger Review's note on the figures Recalculate Ledger would
  change, and 1.2.8's release note on spend fees (#157), said adding any
  transaction recalculates everything too. Only one dated before the latest
  does: one dated after the others adds only its own figures, so an older
  row kept its old figures. Editing or deleting any transaction, or
  Recalculate Ledger, applies the newest rules to every row, as both now
  say.
- **A dollar transfer's Amount (To) counts** (#447). On a dollar transfer
  (Bank → Exchange, or Exchange USD → Bank) the form asked for Amount
  (From), Amount (To) and Fee (USD) but saved only Amount (From) and the
  fee: whatever Amount (To) said was dropped, the receiving account was
  credited all of Amount (From), and the fee came out of the sending
  account on top. So "$1,000 sent, $990 arrived, a $10 fee" showed Bank
  $1,010 lower and Exchange (USD) $1,000 higher, both wrong by the fee.
  Now a dollar transfer works as a bitcoin one does: you type what left
  (Amount (From)) and what arrived (Amount (To)); Fee (USD) is filled in
  as the difference and can't be typed. Amount (To) above Amount (From) is
  refused in words (on a bitcoin transfer too, which saved it with no fee
  and credited Amount (From)), and so is a dollar amount past the cent. It
  is saved as dollar transfers always were (the amount that arrived, the
  fee on top), so nothing stored changes, and one saved before opens with
  Amount (From) as its amount plus its fee. Every release with this form
  (1.2.8 and earlier). No tax figure was affected: dollar balances don't
  enter gains, basis or income. **To check:** compare the Dashboard's Bank
  (USD) and Exchange (USD) balances with your bank's and the exchange's.
  If they differ, open each dollar transfer, with or without a fee (one
  saved with a lower Amount (To) and no fee lost the difference too), and
  set Amount (From) to what left the account and Amount (To) to what
  arrived; the balances follow when you save.
- **A fee in dollars is in cents** (#298). A fee's decimals were checked
  as bitcoin's (up to 8 places) whatever its currency, so a Buy's fee of
  $0.005 was accepted and then lost from the lot's cost when stored in
  cents ($1.00 plus $0.005 was a $1.00 lot; $0.006 made it a cent more).
  Now a fee in dollars, typed or filled in for its type, can have at most
  2 decimal places ("A USD fee can have at most 2 decimal places."), in the
  form, the API, the CSV preview, the AI connector's import and River's. A
  bitcoin fee keeps its 8. Every release from 0.8.0; a fee typed with more
  than 2 decimals was needed.
- **A value the server refuses field by field is said in words** (#448).
  When the server refused a value field by field (FastAPI's 422, a list),
  two screens didn't put that list into words. The River import's preview
  crashed to "Something went wrong" on Import, losing every edit made in
  it, when a cell held a value such as `1,200` in a Cost Basis; the
  transaction form said "Failed to create transaction: [object Object]"
  (or "update") for an amount such as `12345678901`. Both now show the
  server's reason ("Input should be a valid decimal", "Amount is too
  large."), and River's preview stays as it was, so the cell can be
  corrected and imported. Nothing was saved in either case: no figure
  changed. Every release from 0.8.0.
- **The River import's preview says what its fees and tags are** (#269).
  The Fee column wrote a dollar fee as "1.50" and a bitcoin fee as
  "0.00000200", with no unit, and an Interest payout showed only as
  "Deposit". It now writes "$1.50" and "0.00000200 BTC", as the other
  columns do, and a deposit River tagged shows its source under its type
  ("Deposit" over "Interest"). Display only: the import always read them
  right.
- **The River and AI imports' duplicate check is fast again** (#379). This
  version's duplicate rule (#253) checks each row in up to seven passes,
  and each pass looked through the whole ledger for every row: a River
  file of 2,000 rows against 2,000 transactions took about 13 seconds, and
  the AI connector's 500 rows against 10,000 about 8. Each row's
  transactions within two days are now found once, by time: about a tenth
  of a second for either. The answers are the same. **Affected:** no
  release: the rule is new in this version. Nothing to do.
- **A number written with a decimal comma is refused, not read as another
  number** (#452). The CSV import and the River import dropped every comma
  in a number, to allow a thousands separator ("1,000.50"), so a decimal
  comma was dropped too, with no error and no warning: "0,5" BTC was saved
  as 5 BTC, "1234,56" dollars as $123,456 and "0,01" as 1. Where a point
  separated thousands, as the same spreadsheets write them, "21.000,00"
  dollars was saved as $21. Now a comma counts only as a thousands
  separator, between groups of three digits before the point (1,000 or
  12,345.67). Any other comma is refused, naming its column, in the
  preview and at Import: "A comma is read only as a thousands separator
  (1,000.50): write decimals with a point (0.5, not 0,5)." A number with an
  underscore ("0_5", which was read as 5) is refused too. **Affected:**
  every release with the CSV or River import, 1.2.8 included, any tax
  year, but only a file that wrote an amount, cost basis, proceeds, fee or
  value with a comma as its decimal point (a spreadsheet set to a language
  that writes one can save a CSV so, with the number in quotes). A file
  with points, as BitcoinTX's template, its own export and River's files
  have, was read right.
  **What to do:** if you imported a file that wrote decimals with a comma,
  look in Transactions for amounts and values ten or more times too large,
  or about a thousand times too small where a point separated thousands
  (21.000,00), and edit each to the right figure (an edit recalculates the
  ledger).
- **The CSV import's Preview says when a row needs a price BitcoinTX can't
  get** (#125). Preview called a row valid that Import then refused for want
  of a BTC price: a BTC fee without `fee_usd`, an income, rebate or
  inherited deposit without its basis, or a Spent without its proceeds,
  when no price for that day was stored and none could be asked for (no
  price source chosen, or Nobody, or a day before any price or after
  today). Preview now
  lists such a row as an error naming the value to fill. A price BitcoinTX
  may still ask for is left to the import, as before. Nothing was ever saved
  wrong: the import refused the whole file and said why. **Affected:** every
  version since 1.1.0 (where nothing is asked for prices until a source is
  chosen, nor with Nobody), and every version for a day before any price or
  after today. Nothing to do.
- **The CSV import refuses a row with more fields than the header**
  (#453). A comma outside quotes starts a new field, so an amount written
  `20,000.00` without quotes is two fields, `20` and `000.00`, and so is a
  note with a comma in it, or a doubled comma. Every column after it moved
  one place, and the import read the row so, with no error and no
  warning: a My BTC deposit with a $20,000.00 cost basis was saved with a
  basis of $20.00, no source and "MyBTC" as its purpose, and its sale
  later showed about $19,980 too much gain; an income deposit could lose
  its source and not count as income. Preview and Import now refuse a row
  left with more fields than the header, naming it: "This row has more
  fields than the header: a stray comma, or an amount written with a
  comma (write 1000.00, not 1,000.00)?", as the River import does. A row
  ending in one comma too many is refused too, since it can't be told
  from a shifted one: remove the comma. A value in quotes (`"20,000.00"`)
  is one field and reads as before, and so does a row with fewer fields
  than the header (its last cells blank). So a shifted row written
  without its last empty cells still can't be caught: write every column,
  as the template and the export do. **Affected:** every version with the
  CSV import, 1.2.8 included, and any tax year with a transaction
  imported from a file with one comma too many outside quotes in a row (a
  row whose shift put a value in a column that can't take it was refused,
  with a confusing error such as "Invalid fee currency '1'"). **What to
  do:** if a file you imported had one (an amount like `1,000.00`, a
  doubled comma, or a comma in a note, without quotes), compare its
  transactions with the file (cost basis, proceeds, fee, source, purpose,
  notes and the later columns) and edit any that differ: the edit
  recalculates the ledger.
- **The CSV import's preview shows dollars as dollars** (#254). Settings →
  Import Transactions (CSV) → Preview wrote "BTC" after every amount, so a
  $50,000 deposit to Bank read "50000.00000000 BTC", and named the
  accounts "Exchange Usd" and "Exchange Btc". It now shows a cash row's
  amount in dollars ($50,000.00), a bitcoin row's in BTC, and the
  accounts as the CSV file writes them (Exchange USD, Exchange BTC). Only
  the preview was wrong: the import always read the amounts right.
- **The Mac app's Python is chosen and tested** (#284). Its build took the
  newest Python on the build machine: GitHub's macOS runner has 3.13, so
  the 1.2.8 Mac app bundled Python 3.13.15, which no test job ran, and a
  newer runner would have changed it without anyone choosing that. Now the
  macOS build and release jobs set up Python 3.13 and hand it to the build
  (`BTCTX_BUILD_PYTHON`), and the automatic tests run on 3.13 too, beside
  3.10 and 3.11 (and Docker and StartOS now run 3.13, #425). The owner chose 3.13,
  what 1.2.8 shipped and was tested on, over 3.11, which GitHub offers for
  the Mac only as a release from April 2024. A build on your own Mac still
  takes the newest it finds, unless you name one.
- **A dollar withdrawal is never listed as a gift of bitcoin** (tax
  figures, #449). In the transaction form, a withdrawal's Purpose, FMV and
  Proceeds show only for a bitcoin account, but a value chosen there stayed
  in the form when the Account was then changed to Bank or Exchange USD,
  and was saved with the dollar withdrawal. The Complete Tax Report then
  listed it under "4. Gifts, donations and lost coins" as bitcoin given
  away (its dollars shown as BTC, its typed value in the section's total),
  a leftover Spent with proceeds was counted in the dashboard's spent
  total, and Ledger Review could list a leftover Lost or $0 Spent. In
  1.2.8, a Spent whose proceeds came from the price, edited into a dollar
  withdrawal, was even priced again at the BTC price times its dollar
  amount: the dashboard counted that as spent, the report's table of
  values from the price listed it, and Ledger Review offered to price it
  at the hour. A deposit's Source was kept the same way (shown in the list
  only). Now the form sends a purpose, value or source only for a bitcoin
  account; BitcoinTX keeps no Spent, Gift, Donation or Lost and no value on
  a dollar withdrawal whoever sends one (a label of its own, such as
  "Rent", stays), and the CSV import's and the AI connector's previews say
  so; and the report, the dashboard, Ledger Review and the AI connector's
  duplicate check read them only on bitcoin leaving. Form 8949, Schedule D
  and the gains were never affected: a dollar withdrawal has no lots.
  **Affected:** every version (the priced case 1.2.8), for any tax year
  with a dollar withdrawal saved this way. **What to do:** nothing: such a
  row is left out of the figures from this version. Its old purpose still
  shows in the Transactions list, and its purpose and proceeds in the
  Transaction History report, until you open the withdrawal and save it.
- **No gain line for a gift, a donation or lost coins** (#257). The
  Transactions list showed one under these withdrawals ("Gain $0.00 ·
  +0.00% · Long-term"), as if they were sales with a holding period. They
  aren't sales: the tax report already gives them no gain or loss of their
  own. Now only a Sell and a Spent withdrawal show a gain line. Display
  only: no figure changes.
- **The Mac app in a browser says where its setup code is** (#258). Opened
  in a browser at its own address (`http://127.0.0.1:8765`), the Mac app's
  login page explained the first-run setup code for Docker ("docker logs",
  "/data"), and so did Create account and Settings, even in the app's own
  window. They now say it is in `setup-code.txt` in BitcoinTX's data folder
  (`~/Library/Application Support/BitcoinTX`) wherever the server is the
  Mac app: the public `/api/users/setup-status` now says so (`desktop`).
  Wording only.
- **The IRS forms no longer fill the log with pypdf warnings** (#124).
  Each time BitcoinTX read an IRS form's text (to check a draft form's year
  and pages, as when the next year's preview is offered), pypdf logged a
  warning for each font that fontTools wasn't installed, with the font's
  whole width table: on the StartOS test server, 183 lines of about 2 KB
  after making one ledger's forms, burying real errors. The forms were
  always right. That one warning is now left out; pypdf's others still
  show. No new dependency.
- **Nothing saved while Delete All runs is lost** (#276). Delete All (and
  Create account on an install with transactions) copied the database,
  then deleted every transaction: a transaction saved in between, by the AI
  connector at that very moment, was in neither. And on an empty ledger,
  which needs no typed `DELETE`, one saved just after that check was
  deleted without it (kept only in the copy). The check, the copy and the
  delete now hold the database's write lock together, so such a save waits
  until the delete is done and is kept. If another save holds the lock too
  long (more than 5 seconds), nothing is copied or deleted, and the message
  says to try again. Not seen in use: the gaps were a few milliseconds.
- **Delete All deletes only what its dialog showed** (#377). A transaction
  saved while the dialog was open (by the AI connector, say) was deleted
  too, and Settings then said "Deleted" with the count the dialog had
  shown. The confirmation now carries what the dialog showed, the number
  of transactions and their tax years: if the ledger changed meanwhile,
  nothing is deleted, and the dialog shows what would go now and asks you
  to type `DELETE` again. The same at Create account on an install with
  transactions. (A change that keeps both, one transaction swapped for
  another within those years, still goes ahead; the copy made first keeps
  it.) **Affected:** no release: the dialog is new in this version (#256).
  Nothing to do.
- **The newest database copies are the ones kept** (#308). BitcoinTX keeps
  the newest few copies of each kind in its data folder's `backups/` (before
  an update or a restore, before Delete All, before Ledger Review's hourly
  prices, and the AI's), sorted by the time their files were written. Copies
  made within one tick of the filesystem's clock share that time, and then
  their names decided, which sort the wrong way (`…Z-2.db` before `…Z.db`):
  the oldest of them could be kept and the newest deleted, and the next copy
  could take a deleted copy's name. They now sort by the second and number
  in their names too, and a new copy never takes a deleted one's name.
  Copies made seconds apart, as in use, were always right; no figure is
  involved.
- **A bitcoin withdrawal moved to a dollar account no longer shows a
  gain** (#487). A withdrawal edited from Wallet or Exchange BTC to Bank or
  Exchange USD kept the cost basis, gain and holding period it had as a
  bitcoin withdrawal, even after Recalculate Ledger. The Transactions list
  showed a gain line under it, the Transaction History report (PDF and
  CSV) showed the gain and called the row a "CapitalGainsTransaction", and
  the AI connector's list of transactions returned it. A dollar withdrawal
  disposes of no bitcoin, so it now has none, from the edit on. Form 8949,
  Schedule D, the Complete Tax Report's gains and the dashboard were always
  right: they count the bitcoin that left, which the edit gave back.
  **Affected:** every release from 0.8.0 to 1.2.8, the Transaction History
  of such a withdrawal's tax year. **What to do:** nothing for the tax
  forms. Ledger Review lists such a row among the figures Recalculate
  Ledger would change, and Recalculate Ledger clears them.
- **An old withdrawal made a sale keeps its proceeds before the fee** (tax
  figures, #520). A withdrawal saved before 0.8.0, when BitcoinTX didn't
  yet keep proceeds before fees, changed into a Sell with a dollar fee
  through the API (the AI connector, say: the edit form sends the sale's
  gross itself), before any recalculation had filled its proceeds in, was
  saved with proceeds too high by the fee:
  $700 received, with a $10 fee, came out as $710 gross and $700 net,
  instead of $700 and $690. The check read the $700 as the sale's gross,
  but the save read it as an old sale's net and added the fee on top. Now
  the sale's gross is what the withdrawal received, as a recalculation
  recovers it and the edit form shows it (#485), and the fee comes off it.
  **Affected:** every release from 0.8.0 to 1.2.8, only for a ledger from
  before 0.8.0 with no recalculation since (any edit or deletion, an add
  dated before the latest transaction, or Recalculate Ledger fills those
  proceeds in for good), and only for such a withdrawal changed into a Sell
  with a dollar fee: that sale's proceeds and gain, on Form 8949, Schedule
  D, the Complete Tax Report and the dashboard, and the Exchange USD
  balance, by the fee. **What to do:** if you changed such an old
  withdrawal into a sale, open it: if its Gross Proceeds (USD) is more than
  the sale brought before the fee, enter what it brought and save.
- **Edit reads a purpose saved in another case** (#273). A withdrawal an
  older version saved as "spent" (or "gift", "donation", "lost") opened in
  Edit with **Purpose** blank, and **Update transaction** did nothing until
  a purpose was picked again, without saying why. The form now reads the
  saved purpose ignoring case, as the server always has, so it shows Spent
  and saves as before. A deposit's source was already read this way. The
  Transactions list and Ledger Review show the listed spelling too ("Spent",
  not "spent"). Display only: nothing stored changes, and no figure moves.
- **BTC Fees and USD Fees can't be renamed or deleted** (#289). The
  account API (`/api/accounts`, login only: no screen and no AI connector
  tool changes accounts) protected Bank, Wallet, Exchange USD and Exchange
  BTC, but not the two fee accounts. A renamed BTC Fees made the next
  bitcoin fee create a second "BTC Fees", and BitcoinTX then failed to
  start (it puts the fixed names back, and two accounts can't share one);
  a deleted fee account took its ledger lines with it. All six fixed
  accounts now refuse a new name, a new currency and a delete, and no other
  account can take their names. No figure moves: the lots don't read the
  fee accounts.
- **The CSV preview refuses the fee accounts, dollar amounts past the cent
  and transfers across currencies** (#266). Settings → Import Transactions
  (CSV) → **Preview** called these rows valid, and **Import** then refused
  them, the whole file with them: a row naming the ledger's own BTC Fees
  or USD Fees account (a withdrawal from BTC Fees wasn't even asked for its
  purpose), a dollar amount with more than 2 decimal places, and a
  transfer between a dollar account and a bitcoin account. Preview now
  refuses each of them with the reason, as the import does; so do the AI
  connector's entry check and the River import, which share the row check.
  Nothing wrong was ever saved: the import is all or nothing.
- **The CSV preview refuses every row the save's own checks of a row would**
  (#285). After #266, Preview still called some rows valid that **Import**
  then refused, the whole file with them: a sell's fee over its proceeds, a bitcoin
  transfer's fee over its amount, a deposit's or withdrawal's fee in the
  other currency (also a dollar deposit's fee with no currency, which the
  import takes as bitcoin), more than 21,000,000 BTC, a date before 2009 or
  more than a day ahead (one in the next day is still only a warning), and
  a purpose or source over 64 characters. Preview now refuses each with
  the save's own words, through the save's own checks, so the two can't
  drift apart; the AI connector's entry check and the River import, which
  share the row check, refuse them there too. (A row the ledger has too
  little bitcoin for is still found only at Import.) Also, the CSV guide's
  troubleshooting table said a deposit goes only to Wallet or Exchange
  BTC; Bank and Exchange USD take deposits too. And in the River import, a
  dollar transfer with a fee and no fee currency was saved with the fee
  added to its amount ($101 for $100), and a fee currency written with a
  space (" BTC") was left out of a bitcoin transfer's amount; both now save
  as the CSV import does.
- **A CSV export imports as it was** (#230). The export puts a `'` in
  front of text a spreadsheet could run as a formula (a purpose such as
  `-5% fee`, `=…`, `+…`, `@…`, or one that only looks like it, such as
  `－10`), and importing that file kept the `'`: `-5% fee` came back as
  `'-5% fee`. The import now drops that one `'` again, in the columns the
  export writes that way; a `'` before any other text stays. A purpose
  saved with its own `'` before such text (`'-5% fee`) is exported with
  another, so it comes back with its own (#380). In a CSV file you write
  yourself, `'-5% fee` reads as the export's and loses its `'`, and spaces
  at either end of a cell are trimmed, as before. Text only, no figure.
  Every version since 1.1.0 (the look-alikes since 1.2.8).
- **The AI's guide and the CSV guide say how a dollar transfer's fee is
  entered** (#477). Both said a transfer's amount is what left the
  account, its fee included, which is true of bitcoin only: for dollars
  (Bank ↔ Exchange USD) BitcoinTX takes the amount as what arrived and
  the fee on top, as for a withdrawal. So "$1,000 sent, $990 arrived, a
  $10 fee", entered as the guides said (amount 1,000, fee 10), lowered
  the Bank by $1,010 and raised Exchange (USD) by $1,000, both wrong by
  the fee. They now say amount 990, fee 10, with that example (the AI
  connector's field descriptions too, and the CSV guide has an example
  row of it). Dollar balances only, no tax figure; a dollar transfer with
  no fee was right either way. The AI's guide since 0.8.0, the CSV guide
  since 0.9.2. To check: open each dollar transfer with a fee that the AI
  or a CSV file entered; if Amount (From) is more than really left the
  account, set Amount (From) to what left and Amount (To) to what
  arrived (#447), and save.
- **The CSV guide says what the import takes** (#304). Its rules table said
  a deposit goes only to Wallet or Exchange BTC, and a withdrawal comes
  only from them, while its own troubleshooting table and the import take
  Bank and Exchange USD too; its type and column tables said the same.
  They now say dollars or bitcoin: a deposit's cost basis and a
  withdrawal's purpose (Spent, Gift, Donation or Lost) are needed only with
  bitcoin, and a dollar withdrawal's purpose is any text, or none. Its
  Deposit and Withdrawal example rows had a comma too few, so they didn't
  import as printed; they do now. And its tables' longer rows no longer
  run off the page.
- **A date originally acquired, or a date of death, stays the date you
  entered** (tax figures, #185). These dates were stored as noon of that day
  in the tax timezone, and used as that moment's date in whatever the tax
  timezone was later. After the tax timezone changed by about 12 hours or
  more (UTC+14 to UTC, or UTC to UTC+12, for example), the form, the holding
  period, Form 8949 column (b) and an inheritance priced again used the day
  before or after, with no save needed, and saving the deposit kept it.
  Smaller changes could move a date stored with a time of day: one the CSV
  import, the AI connector or the API took with a time, and a date that was
  the deposit's own day for a deposit made before noon. A day can move a
  holding period across the one-year line (long-term or short-term), change
  which coins are sold first, and price an inheritance on the wrong day.
  Every version since 1.2.6 (the date originally acquired) and 1.2.8 (the
  date of death). Now the date itself is stored: `acquired_at` is a date,
  `YYYY-MM-DD`, in the API, the CSV export and the AI connector, and no
  timezone change moves it. A date given with a time stands for its date in
  the tax timezone. The deposit's coins count from noon of that date in the
  tax timezone, never after the deposit, as before for a date entered alone.
  An edit that keeps the date is saved even if a timezone change has since
  put the deposit on the day before it; its coins then count from the
  deposit itself, so the CSV export leaves such a My BTC or Gift date blank,
  which means the same (Ledger Review's reminder then lists the deposit). An
  Inherited date of death is exported as it is, and the import refuses it;
  importing under the old tax timezone, then changing it back, keeps every
  figure. From this version on, the app's page is checked with the server
  every time it loads, so a browser can't keep showing an older version's
  form.

  The upgrade (migration 0012) stores each date as the form showed it, which
  is the date the reports used. Which timezone a date was entered in isn't
  known, so a date an earlier timezone change moved keeps the moved day. For
  a date given with a time, or entered before a timezone change, the coins
  now count from noon of that day instead of that time. That moves no date
  and no holding period, but where two lots in one account fall on the same
  day, it can change which one a later sale takes first, and so its gain.
  Ledger Review now compares lots by their dates, so a lot that only moves
  within its day isn't listed by itself.

  **What to do:** right after upgrading, reload BitcoinTX's page (the Mac
  app does it by itself). A browser can keep showing 1.2.8's page for a
  while, which shows these dates a day early in a tax timezone behind UTC
  (the Americas) and saves that day with any edit of the deposit: if an edit
  form shows a date originally acquired or of death a day early, don't save;
  reload the page. Then open Ledger Review before saving anything. If
  "Figures that Recalculate Ledger would change" lists a sale, its gain
  moves because of the order above; Recalculate Ledger applies it (so does
  any save). If you changed the tax timezone by many hours after entering a
  My BTC, Gift or Inherited deposit's date, check those dates against your
  records and correct any that moved. Most ledgers need nothing.
- **Input that can never be valid gets a refusal, not a server error**
  (#210, #218, #211). These requests were answered "Internal Server
  Error" (500) instead of saying what was wrong. Nothing was saved, and
  only the logged-in owner (or the AI key, for the AI connector's entries)
  could send most of them. Every version up to 1.2.8. Now:
  - a password or username that isn't text (a lone surrogate, `"\ud800"`,
    which JSON can carry but no keyboard types) is a wrong one at login or
    as the current password (401 or 403, counted like any other), and a
    new password or username like it is refused with a 422 that says so
    (#210);
  - a JSON number too large for a computer's numbers (`1e999`, read as
    infinity), or `NaN`, gets a 422 that names the field and leaves the
    value out (#218);
  - a date at the very edge of the calendar, such as 9999-12-31 23:59:59 in
    a US tax timezone or `0001-01-01T00:00:00+05:00`, is refused as "out of
    range", naming the field (the date or the date originally acquired), in
    the CSV import, the AI connector's entries and the API; a Complete Tax
    Report or transaction history for a year before 2009 or after 2100 is
    a 422 naming the year, as Form 8949 already refused one; and a CSV or
    River file with a field over 131,072 characters gets "The file can't
    be read as CSV" (#211).
- **A few sats are written out, never as 5E-8** (#101). The transactions
  API, and so the AI connector's `list_transactions`, gave an amount or a
  fee under 0.000001 BTC in exponent form (`"5E-8"` for 5 sats), and no fee
  as `"0E-8"`; so did `preview_transactions`' balances afterwards,
  `add_transactions`' list of what it created and `get_portfolio`'s BTC
  balances (`1e-08`). An AI reading it could misread it. These now always
  come with their eight places (`"0.00000005"`, `"0.00000000"`), as the
  CSV export, Form 8949 and Ledger Review write them. The edit form showed
  such an amount or fee as `5e-8` too, and so did a transfer's fee worked
  out from its amounts; they now show `0.00000005`. Nothing stored or
  computed changes.
- **The AI connector's `btctx_mcp.__version__` is its real version**
  (#133). It said 0.1.0 whatever the release; it now reads the installed
  package's version (`unknown` when the connector isn't installed).
  Nothing used it: the connector's version notice already read the
  package's version.

### Security
- **BitcoinTX no longer runs as root in its container** (#202), in Docker
  and on StartOS, which runs the same image. It runs as its own user,
  `btctx` (uid and gid 10001), keeping one right: to open port 80. A flaw
  in BitcoinTX or a library it uses can then change only BitcoinTX's own
  files, never the rest of the container. Nothing to do on StartOS or with
  the README's Docker command: at a start the image, or StartOS's package,
  first gives `/data` to that user, so a volume an earlier version made
  (every file root's) keeps working, and so does a StartOS backup made
  before. With Docker:
  - Run a maintenance command as that user:
    `docker exec -u btctx <container> python -m backend.cli …`. Run as
    root, a file it creates stays root's until the next start.
  - A host folder mounted at `/data` is given to uid 10001 at a start when
    anything in it isn't that user's. With `DATABASE_FILE` set elsewhere,
    its folder must be a volume or a mounted folder itself, which is then
    handed over; a subfolder of one isn't: give it to uid 10001 yourself.
  - With capabilities dropped (`--cap-drop ALL`), keep CHOWN, DAC_OVERRIDE,
    SETUID, SETGID and NET_BIND_SERVICE.
  - Started with `--user`, the image runs as that user and leaves `/data`
    as it is: it must then be that user's.
  - A `/data` that can't be given to uid 10001 (a read-only mount, network
    storage that refuses it, a missing capability) stops the start, with a
    message saying so.

  Checked on every pull request: an update from the published 1.2.8 image
  on a volume with a ledger, its setup code and a backup copy
  (`scripts/docker_update_check.sh`); and on the StartOS test VM.
- **Hardening from the 1.2.8 and 1.2.9 security reviews** (#204). None of
  these could be used against an install; each closes a gap before it
  could matter:
  - **A login with a username that doesn't exist takes as long as one
    with a wrong password.** Only an existing username's password was
    checked (about 0.2 s, against 1 ms), so the time an answer took said
    whether that name exists. Now an unknown one is checked against a
    stand-in all the same.
  - **The AI key goes by the route a request reached**, not by its web
    address read a second time, where a `%3F` in the address cut that
    reading short. No route outside the key's list could be reached that
    way (checked); now none can by any address.
  - **A `SECRET_KEY` set in the environment needs at least 32
    characters**, like the key file's. A shorter one is ignored, with a
    warning in the log, and the key file next to the database is used
    instead (everyone logs in again once). Docker, StartOS and the Mac app
    set none, so nothing changes for them.
  - **Trust this server says where to check the fingerprint.** The
    certificate authority's name it shows is what the server says about
    itself; the card now asks you to check that the SHA-256 fingerprint
    is that server's own before you trust it (on a StartOS server, the
    Root CA in its About this server: System > General Settings, or the
    menu at the top right).
  - **A new encrypted backup needs a password of at least 12 characters**,
    the login passwords' rule. Before, any password made one, a single
    letter included. The file holds the whole ledger and the login's
    hashed password; its encryption slows guessing, but a short password
    still falls to someone who has the file. A backup made earlier with a
    shorter password still restores. Settings' Backup & Restore and the
    Delete All dialog's backup say so under the password boxes.
  - **Backups, the CSV export, the reports and the ledger's other data
    stay out of the browser's cache** (`Cache-Control: no-store` on every
    answer from BitcoinTX's API): a downloaded ledger no longer lingers in
    the browser's own files after you've saved it.
  - **A CSV or River file is read only as far as the 5 MB limit** (and one
    byte, to tell it's over) before it's refused, not whole.
  - **An import that fails for an unexpected reason says so in plain
    words**: "Import failed: something unexpected stopped it, and no
    transactions were saved. BitcoinTX's log says what." It used to repeat
    the error's own text, which could hold a database query, a server path
    or a transaction's date. The log names the kind of error; the details
    are in its debug level. When the database was busy saving something
    else, the import says so, to try again. The AI preview no longer
    passes such an error's text on to the AI either.
  - **The AI preview reads the price history files before its dry run**,
    so the time it holds the database's lock, while your own saves wait,
    no longer includes reading them to say which price filled each value.
- **The AI connector's Recalculate Ledger, and its import of an entry dated
  before your latest entry, come after a copy of the database** (#336, #414,
  the owner's choices). Before the AI key's first edit or deletion in an
  hour, BitcoinTX keeps a copy of the database
  (`backups/…-ai-before-changing-…db`). A recalculation asked for with the
  key (`recalculate_ledger`) made none, nor did an import
  (`add_transactions`) holding an entry dated before your latest entry,
  which recalculates the whole ledger too; either can change stored figures
  (a rule fix an update brings, which Ledger Review lists first). Both now
  count as a change: the hour's first one comes after that copy, kept as
  long as the others, and with no copy nothing is recalculated or added. An
  import of later entries only, and your own Recalculate Ledger or imports
  (Settings, or StartOS's action), are unchanged.
- **The IRS forms and a restore that fail unexpectedly say so in plain
  words** (#422), as the imports now do: never the error's own text, which
  could hold a database query, a server path or a transaction's date; the
  log names the kind of error. A backup the restore can't read past its
  password check is called damaged, as other unreadable files are.
- **Every error nobody expected says so in plain words, and the log keeps
  its text out** (#430). An error no part of BitcoinTX handled answered a
  bare "Internal Server Error" while the server logged its whole trace,
  which can hold a database query with a transaction's date; it now
  answers "Something unexpected went wrong. BitcoinTX's log says what.",
  and the log names only the kind of error (the details are in its debug
  level). The same for Ledger Review's check of what Recalculate Ledger
  would change, the steps BitcoinTX takes as it starts, the refresh after
  a restore and a report's year-end price; and changing the tax timezone
  no longer shows a recalculation error's own text.

### StartOS package
- **Restoring a StartOS backup, as StartOS does it** (#323). The package's
  README said a backup made on an older version is migrated forward when
  it's restored, and its README and instructions said to go back by
  restoring a backup. StartOS keeps the installed package in each backup,
  so a restore brings back the version the backup was made with (the next
  update migrates it, and only then runs that update's steps), and it
  restores a service only while it isn't installed. The README now says
  what a restore brings back, and the instructions say how to go back:
  uninstall BitcoinTX, which deletes its data (its `backups/` copies too),
  then restore a backup made before the update; anything entered after
  that backup is lost.
- **Price Source & Privacy says where each Mempool goes** (#246). In
  testing, **My Mempool on this server** was read as "my Mempool, wherever
  it is", and no box for an address appeared, since that choice means the
  Mempool service installed on this StartOS server. Its label now says so
  ("installed here, recommended", or "install Mempool here first"), and
  **Decide in BitcoinTX instead** says "also for a Mempool on another
  machine", whose address you type in the app. The action's description
  and its message after a Mempool choice say the same, in all five
  languages. The instructions (in English) also say which of another
  server's addresses to use: the one on your home network (often
  192.168.x.x), not a 10.59.x.x address, which belongs to a VPN.
- **The package checked against Start9's current guide** (#372; Start9's
  published guide at `698a56c`, everything since `5c7e52e`, the last check).
  The package's `LICENSE` is now an exact copy of BitcoinTX's
  (`project-structure.md`: upstream's license text alone; it had a Markdown
  heading). The instructions describe the AI connector's version and the
  Recalculate Ledger task as they work, without "after each update" steps,
  which Start9 keeps for release notes (`versions.md`,
  `writing-instructions.md`). `UPDATING.md` gains Start9's rules for the
  version and its notes (a version counts as released once the community
  registry serves it, and the notes cover everything since the one it last
  served) and for bumping the SDK (`npm install` until the lockfile stops
  changing; `npm update` doesn't move a git dependency), and says Start9
  packs with the newest start-cli. The release tests add a reinstall after
  the uninstall (`publishing.md`), and `test_startos_conformance.py` checks
  the license, how Start9's release workflow reads the id and version, the
  instructions' wording, and one exact SDK. Everything else already
  conformed; nothing the package does changes.
- **A package fix while a version is only on Community Beta** (#376, the
  owner's rule): Start9 keeps the version number until the community
  registry serves it, so `UPDATING.md` now ships such a fix inside a small
  app release (a new version with a real app fix, the package back at `:0`)
  instead of a package revision.
- **The instructions' Documentation link names a page with only what
  applies on StartOS** (#467). Start9's support indexer crawls the links
  under the instructions' `## Documentation`, and Start9's guide
  (`writing-instructions.md`, "Choosing documentation URLs") says to leave
  out install guides for a deployment the package doesn't use, or support
  learns steps that break a StartOS install. The link was the whole README,
  with the Mac app's, Docker's and source's install, first login and
  upgrade steps. It now names a new page, `docs/USING.md`: what BitcoinTX
  does, the same wherever it runs (the accounts, the five kinds of
  transaction, lots, reports and tax forms, imports, Ledger Review, prices,
  backups, one wallet and one exchange), made from the README's "Features"
  and "One wallet, one exchange". The README keeps its text and points to
  the page; the MCP server's page stays linked.
  `test_startos_docs_link_467.py` checks that each link is a page of this
  repository and that the page about the app has no other install's steps.

### Development
- **During big work the lead runs every merge** (AGENTS.md, "Big work",
  "Pull requests" and "Branches"; `docs/HOW-CHANGES-FLOW.md`; the owner's
  rule, 2026-10-17). Sessions report a pull request "ready" instead of
  turning on auto-merge; the lead merges from one queue on the umbrella
  issue, each branch brought up to date with `develop` and re-tested
  first; `develop` requires that since 2026-10-17. #413 had merged on
  checks run before #416 changed the sentence its test expected, which
  broke `develop` until #417.
- **A bug found during big work gets its own session** (AGENTS.md, "Big
  work"; `docs/HOW-CHANGES-FLOW.md`; the owner's rule, 2026-10-16). Once
  it's filed, the lead adds a session for it to the umbrella issue and
  starts it, and the release waits for it, unless the owner leaves it for
  later; a bug in an open pull request and a security problem are handled
  as before. The 1.2.9 release's session A2 (#383) is the first, for bugs
  session B's security review (#371) found.
- **Every session of big work starts from `develop`** (AGENTS.md, "Big
  work"; `docs/HOW-CHANGES-FLOW.md`). A session given a working folder of
  its own gets `develop` as that folder's base (after `make sync-check`),
  and each kickoff prompt says to bring the folder up to `origin/develop`
  first with `git merge --ff-only`: otherwise the folder may be cut from
  `main`, which lacks everything not yet released.
  The 1.2.9 release's sessions A, B and C (#369) started from `main` on
  2026-10-16 and moved to `develop` themselves.
- **The stale `.devcontainer` is gone** (#431). Its Python 3.11
  environment with old, unhashed pins (some with known advisories, some for
  packages the app dropped long ago) and its Node 18 image matched nothing
  BitcoinTX runs, and nothing documented or used it: opened in VS Code or
  Codespaces, it built an environment unlike the image, the locks and CI.
  A development setup follows `docs/MAINTENANCE.md` and `docs/TESTING.md`,
  from the hashed locks.
- **Two old scripts are gone** (#44). `scripts/release-docker.sh` pushed
  an image to a Docker Hub repository no longer used, with `:latest`; the
  images come from `.github/workflows/image.yml`
  (`ghcr.io/digimonk73/btctx-mcp`). `scripts/backup-db.sh` copied a
  database by hand, which Settings → Backup & Restore and BitcoinTX's own
  copies before each upgrade cover; `mcp_server/README.md` no longer
  points to it.
- **The price card's "confirm once" click-through tests wait for the
  price lookups that Confirm starts** (#444). "Confirm once: My own
  Mempool" read the requests sent to the outside once, right after the
  card went, and expected one to the Mempool; the price lookups that
  Confirm starts run after the save's answer, so on a slow runner they
  came later and the test saw none (WebKit, in #441's CI). It now reads
  once the Dashboard shows the price and the block height they gave; the
  tests that choose Nobody read once the Dashboard says "You chose Nobody:
  no live price.", so none can pass by reading too early either.
  Test-only.
- **The WebKit click-through check no longer fails now and then on a
  page load** (#231). In Playwright's WebKit, the reload or `goto` that
  followed a price choice saved over the API sometimes failed with
  "WebKit encountered an internal error" (the sidebar matrix's reload, the
  price card's status checks; the Dashboard's and the converter's "prices
  off" tests had the same pattern), and the required check failed until it
  ran again. Those tests now save the choice with `choosePriceSource()`, which
  tells the open page as the price card does after its own save: the page
  asks again in place, with no page load. Real Safari, Chrome and the Mac
  app were never at fault (#149).
- **One helper takes SQLite's write lock** (#402): `database.take_write_lock`,
  with `database.is_busy` (moved from `csv_import`) the one check of
  "database is locked". Delete All, the hourly prices' apply and a login's
  timezone fill each took it with a copy of the same lines; each keeps its
  own answer to a busy database (Delete All's 503 and log line, the
  apply's 503, the fill's False) and the step where it takes the lock,
  which `test_write_lock.py` checks. Nothing BitcoinTX does changes.
- **The certificate test no longer fails 1 run in 256** (#299).
  `test_a_changed_certificate_isnt_trusted` made a "changed" fingerprint by
  writing `AB` over the first byte; when the test server's new certificate
  already began with `AB`, nothing changed, the app rightly trusted it, and
  the required Python check failed. It now changes the first byte whatever
  it is. And `scripts/equivalence_check.py` no longer reports the
  `open_sessions` setting, whose login session hashes are new on every run,
  as a difference in every ledger.
- **Node 24, ESLint 10 and eslint-plugin-react-hooks 7** (#425; the
  owner's choice for 1.2.9, 2026-10-17). Node builds the web pages (the
  Docker image's first stage, CI, the release) and gets security fixes on
  its 24 line until April 2028 (22: April 2027). The StartOS jobs, pinned
  to Node 22.23.2 because 22.23.3 couldn't build `diskusage` (#32), take
  Node 24, which builds it. ESLint 10 and react-hooks 7 check the code;
  nothing they install ships (the web pages' 40 packages are unchanged).
  react-hooks 7 adds the React Compiler's checks: they stay on, except
  the one that flags the screens setting state from an effect (to load
  their data, or to reset or derive state when something changes: nine
  places), which `frontend/eslint.config.js` turns off, saying why, until
  2.0's screens. Of the two other spots they found, the transaction form's
  `handleSubmit` (a false alarm) says so where it is, and the Dashboard's
  Tor state, declared after the effect that sets it, moved up a few lines:
  nothing it does changes.
  The configuration now uses ESLint's own `defineConfig` (typescript-eslint
  deprecated `tseslint.config`).
- **ReportLab 4.5.1** (#425; the owner's choice for 1.2.9, 2026-10-17, if
  no PDF moved). It draws the Complete Tax Report and the transaction
  history PDF, and had stayed on 4.4 since 4.5 might change their output.
  The before-and-after comparison (`scripts/equivalence_check.py`'s
  snapshot with 4.4.10, then 4.5.1, the same code, in the Docker image on
  Python 3.11 and on 3.13) found every PDF byte for byte the same: the
  IRS forms and every year's Complete Tax Report and transaction history
  of the reference, golden and 40 random test ledgers, and the CSV
  instructions. The parts 4.5 changed most (its own form fields, CSS
  colours) aren't used. No other package moves.
- **Test and build tools:** ruff 0.17.0, uv 0.13.0 and hypothesis 6.168.5
  (#293, which takes #224 except hypothesis 6.169: it needs Python 3.11,
  and CI still tests 3.10; deferred in #294). Nothing that ships changes;
  uv 0.13 rebuilds the locks unchanged.
- **The Ledger Review click-through test no longer hangs now and then**
  (#275, which #189 also was). The test fakes a failed apply with a
  Playwright route used once. As that route expires, Playwright turns its
  request interception off, and the review's reload, which the browser
  paused in that moment, was never continued: it never left the browser,
  the panel stayed on "Checking..." until the test timed out, and the
  required Chromium check failed now and then. The test now keeps one
  route for the whole test, refusing the first apply and passing the rest
  through, and a lint rule refuses a `times` route or an unroute in the
  click-through tests. BitcoinTX itself was never at fault: the server was
  never asked.
- **Test files run under pytest only** (#272). Six test files had a runner
  of their own, and five failed when run that way: two were old scripts
  for a server at `127.0.0.1:8000` with no pytest test in them (removed:
  `test_backdated_fifo.py` and `test_user_patch.py`, whose scenarios other
  tests cover), one ran `pytest` from the PATH, and two lacked conftest.py's
  setup (stubbed prices, temp folders), so they also wrote `setup-code.txt`
  into `backend/`. The runners are gone; a test checks no test file gets
  one back. `pre_commit_tests.py`, which CI runs as a script, keeps its
  own and no longer runs the two removed scripts. `.gitignore` now ignores
  `setup-code.txt` and `*.orig` (a comment after the pattern made it match
  nothing).

## [v1.2.8] - 2026-10-13 - Prices at the hour, one price choice, inherited bitcoin and consolidation fees, a security review's fixes

### Added
- **Check a download** (#203). Each release now has `SHA256SUMS`, the
  SHA-256 of the macOS `.dmg` and `.zip` and of `btctx.s9pk`, and GitHub
  keeps a signed build provenance attestation of each, made by the release
  workflow. With the file and `SHA256SUMS` in one folder,
  `shasum -a 256 -c --ignore-missing SHA256SUMS` should say OK; with the
  GitHub CLI, `gh attestation verify <file> -R DigiMonk73/BTCTX-MCP` also
  checks that GitHub built it from this repository (README, "Install").
- **Trust this server: your own Mempool at a home server's https address**
  (#188, follow-up to #178). A StartOS server's home-network address (and
  other home servers') has a certificate from that server's own authority,
  which BitcoinTX couldn't use. When that's why your Mempool can't be used,
  the price card now offers **Trust this server**: it shows the server, its
  root certificate's name and SHA-256 fingerprint, and "Only do this on your
  own home network." Once trusted, BitcoinTX checks that Mempool against
  that root alone, for that address only; never for public price sites.
  Offered only for home-network addresses (`.local`, `.lan`, a one-word
  name, 10.x, 172.16–31.x, 192.168.x), never a public internet name.
  **Forget this server's certificate** undoes it, and so does changing the
  Mempool's address. An in-app restore keeps this install's choice, like
  the price source. Login only, never the AI key.
- **A consolidation's network fee can be recorded** (tax figures, #159).
  When you consolidate the coins (UTXOs) in your wallet, or move bitcoin
  between two of your wallets that BitcoinTX counts as one, the network
  fee is a disposal of the coins that paid it (IRS digital-asset FAQ, Q81
  and Q97), but there was nowhere to record it: a transfer to the same
  account was refused. Now the Transfer form's To Account offers **Wallet:
  consolidate / move within the same wallet** (and, from the exchange,
  **Exchange: move between exchanges BitcoinTX counts as one**). Enter what
  left (fee included) and what arrived, as for any transfer. Only the fee
  is recorded: a disposal of your oldest coins at the fee's value, on Form
  8949 in box I or L (C or F before 2025), never broker-reported. Your
  coins, their dates and cost basis stay as they are. The CSV import and
  export, the AI connector and its guide take it too; the list shows it as
  a Consolidation (Between exchanges for the exchange). No existing figure
  changes: only entries you add create new fee rows. If you left a past
  consolidation's fee out, you can add it now: it is checked against what
  the wallet held on its date. After a move between two exchanges, a sale
  at the one the coins moved to usually shows no basis on its 1099-DA: set
  that sale's Broker form to Proceeds only, as the form's hint says.
- **Inherited bitcoin can be recorded** (tax figures, #154). A deposit's
  Source now has **Inherited**, which follows the rules for property
  inherited from someone who died, different from a gift's:
  - its cost basis is its value on the **date of death** (IRC §1014),
    which the deposit must have (the form's **Date of death**; `acquired_at`
    in a CSV or the AI connector). Leave the value blank to use that day's
    BTC price (the date as entered, in any tax timezone, #177), or type
    it: the value on the estate's alternate valuation date if it chose
    one; and if the estate's Form 8971, Schedule A, gives
    a value marked as having increased the estate tax, your basis can't be
    more (IRC §1014(f));
  - every sale or spend of these coins is **long-term** however soon it
    comes (IRC §1223(9)), with **INHERITED** in Form 8949's column (b), as
    the form's instructions ask. The rule follows the coins when you move
    them between the wallet and the exchange;
  - it isn't income. The form explains the rules where Inherited is
    chosen, and the Complete Tax Report adds a note in a year with such a
    sale.

  Before, the choice was My BTC or Gift, and either could print wrong
  figures: a sale within a year of the death came out short-term, or a
  Gift's basis was the person's own cost. **What to do:** if you recorded
  inherited bitcoin that way, edit the deposit: Source **Inherited**, the
  date of death (the edit must give it), and its value that day. A
  deposit saved before 1.1.0 (when the source was free text) as
  "inherited" follows these rules too from the next recalculation; Ledger
  Review lists any without a date of death, which an edit then asks for.
  The update adds one column to the database's lots (rebuilt at every
  recalculation), after its usual backup copy.

- **The hourly price lookup and its verified download** (#144, the second
  of five pull requests; nothing is valued at the hour yet). With public
  price sites chosen, BitcoinTX downloads Bitstamp's hourly prices from
  2013 once, in the background, into `btc-prices/` next to the database
  (about 3 MB): every year in the same fixed requests on every install,
  newest first, through Tor when it's set, and keeps a year only if it
  gives the fingerprint the release ships. With your own mempool server
  and its fallback, it's downloaded when you save that choice. Hours after
  the history come from the server's hourly record (only the hours it
  recorded live) or from Bitstamp, and
  are kept (a new table, `btc_price_hourly`; nothing else in the database
  changes). No request names a transaction's hour.

### Fixed
- **CSV files keep every transaction on its own row** (#151). A line
  break in a stored text stays inside its cell in the transaction history
  CSV, and the CSV export's price moment can't start a spreadsheet formula.
  A purpose or source typed as text must be one line (no line break, tab
  or other control character), and a fee currency must be USD or BTC,
  through the API and every import; a row that already holds such text
  keeps it through an edit that leaves it alone. A text cell that only
  looks plain (spaces or a full-width sign before `=`) gets a `'` in front
  too.
- **Before the AI key's first change in an hour, BitcoinTX keeps a copy of
  the database** (#151). An edit or a deletion with the AI key (the
  connector's `update_transaction` and `delete_transaction`) first makes a
  copy in the `backups` folder with the AI's other copies
  (`…-ai-before-changing-…db`); if it can't be made, the change is
  refused. Of the AI copies BitcoinTX now keeps the newest 3 and, for a
  week, the oldest and the first copy of each day made before the AI
  changed anything that day (UTC days; at most 11 copies), so copies made
  afterwards never replace the ledger from before the AI's changes. Your
  own edits and deletions make no copy.
- **The AI connector's imports are kept short** (#151). With the AI key,
  `preview_transactions` and `add_transactions` take at most 500 rows a
  call, and fewer rows dated before your latest entry, since each of those
  recalculates the whole ledger: the error says how many to send. A long
  one kept BitcoinTX busy, so a save of yours meanwhile (turning AI access
  off too) could fail with "database is locked"; now one takes about 1 s
  on a recent computer and your save waits for it. Your own CSV and River imports are
  unchanged.
- **Every request is limited to 5 MB** (#151). BitcoinTX refuses a larger
  request before reading it, the login and Create account pages included.
  A file keeps its own limit: a backup to restore up to 1 GiB, a CSV or
  River file up to 5 MB. That larger allowance is only for a session still
  open; anyone else, a copy of a cookie after its logout or a password
  change included, gets 5 MB.
- **Every price request ends in bounded time and size** (#151). A request
  to a price source (your own Mempool or a public price site) had a time
  limit for each wait but none for the whole request, and no limit on the
  answer's size, so a source answering very slowly could hold the live
  price, or a save needing a past price, for as long as it kept answering.
  Now each request has a limit for the whole of it (30 seconds; 90 for your
  Mempool's whole price history and Bitstamp's hourly prices), and an
  answer over 16 MB is refused. Either counts as the source not answering,
  as before: the backup, "no price", or a retry later. A past-price lookup
  now really ends at its 3-minute limit.
- **A browser that logged in before isn't kept waiting by others' failed
  logins** (#151). After repeated wrong passwords BitcoinTX makes the next
  tries wait. Behind StartOS's proxy, or a proxy in front of Docker, every
  browser has the proxy's address, so anyone's wrong passwords made the
  owner wait too, even with the right one. Now a browser that has logged in
  (or set the password) gets a cookie that marks it as known (`btc_device`,
  for a year; Secure over HTTPS): its tries are counted on their own, so
  others' failures, from one address or many, no longer stop it. Its own
  wrong passwords still slow it as before, and a browser without the cookie
  is counted by its address as before. Logging out keeps the cookie; a new
  password (in Settings or with StartOS's Set Login Credentials) makes
  earlier ones count as none until that browser logs in again.
- **A value too large to store is refused everywhere** (#151). The API
  refused most amounts and USD values with more digits than the database
  holds (not one the database rounds up, or a tiny exponent, saved as 0),
  and the CSV, River and JSON imports (the AI connector's) refused none:
  such a value was saved, and then the transaction list, the average cost
  and the tax report showed an error for the whole ledger. Every path now
  refuses it with a message naming the field (an amount or BTC value: at
  most 10 digits before the decimal point; a USD value: 16, as the database
  stores it), and the AI connector does before it asks BitcoinTX anything.
  An amount in a River file that isn't a number is now that row's error (a
  fee was read as no fee). Values within the limits are saved as before,
  and the transaction list shows every stored value as it is, including a
  sale's basis the ledger sums past the limits.
- **The Mac app asks for your own username and password while it still
  has the default login** (#151). Its default login (`admin` / `password`)
  now needs the one-time setup code too, as on Docker, and the app's window
  fills it in: the first screen is **Choose your username and password**
  (12 or more characters, typed twice), and your transactions are kept. The
  code is in `setup-code.txt` in the app's data folder (owner-only) and is
  never written to its log; from a browser, `admin` / `password` works only
  with the code typed in.
- **A price a site gives under one cent, or as no number, is never kept**
  (#206, #198, tax figures). A day's price from a public site or your own
  Mempool was checked above zero before it was rounded to the cent, so an
  answer of $0.004 was stored as $0.00, and a value left blank that day
  (an income deposit's value at receipt, an unpriced spend's proceeds, a
  BTC fee's value) was saved at $0.00. The hours after the hourly price
  files (not in a release yet) kept 0, below 0 and no number too. Now such
  a day or hour has no price: a value from it takes the day's price, or
  asks you to type one, never $0, and one odd price no longer costs the
  site's other days or hours. **Affected:** 0.9.2 to 1.2.7, only if a
  price site (Bitstamp, Kraken, Coinbase before #161) or your own Mempool
  ever answered such a price; none is known. **What to do:** nothing,
  unless you ever saw a value "from the price" at $0.00: a day already
  stored at $0.00 stays, so type that value.
- **Logging out ends the session, for every copy of its cookie** (#151). Each login now opens
  a session of its own on the server. Logging out ends it at once, for any
  copy of that browser's cookie too; before, a copy kept working until 14
  days after the login. (If the database is busy at that moment, the browser
  is logged out all the same, the log says the session couldn't be ended,
  and a copy works until it expires.) Your other browsers stay logged in. A password
  change (Settings, or StartOS's Set Login Credentials) or an account reset
  still logs every other browser out, and an in-app restore keeps the
  sessions that were open (when the backup's account has the same id;
  otherwise every browser logs in again) and the browser that restored
  logs in again. **After this update, everyone logs in once
  more.** The unused `GET /api/users/protected` is gone.
- **The Mac app gives the AI connector a new key each time it starts**
  (#151). The key in `mcp.json` stayed the same across restarts; now each
  start writes a new one, and a key from an earlier run stops working. The
  AI connector reads the file again when its key is refused (every
  released connector does), so an AI app left open carries on with nothing
  to set up again. The connector also counts only a BitcoinTX run by your
  own Mac account. If the key's file can't be written, a reset keeps the
  key from before, so the connector carries on; a start then has no key
  (the log says so) until **Reset key** in Settings or the next start, never
  an earlier run's.
- **A restore brings back a backup's data, and keeps this install's login,
  AI key and price settings, or restores nothing** (#201, #151). An in-app
  restore now builds a new database with BitcoinTX's own migrations, as a
  fresh install does, and copies into it only the rows of BitcoinTX's own
  tables and columns from the backup (upgraded first); anything else in the
  backup's database stays behind, and a backup holding database objects
  BitcoinTX doesn't make, more than one login, or rows that don't fit is
  refused. Your current login, AI key and its switch, and price settings are
  written into the new database and checked before it replaces your ledger.
  If any step fails, the restore stops: your ledger and settings stay as
  they were, no temporary file is left, and the page says why in plain words
  (a wrong password, a damaged file) instead of "Failed to restore backup."
  One restore runs at a time. Before, an error while keeping those settings
  was only logged, and the backup's settings could stay in use.
- **A wrong setup code or an over-long password gets the usual answer, not
  a server error** (#200, #205). A setup code typed with some letters
  outside A–Z and 0–9 (À, for example) made the login, Create account and
  Settings' password change answer with a server error (500), and so did a
  password over 72 bytes there. Neither can ever be right, so nothing was
  exposed; now they're refused like any wrong code or password, and count
  toward the wait after repeated failures. A new password over 72 bytes is
  refused with "at most 72 characters (fewer with accented letters or
  symbols)"; before, Create account with such a password deleted the
  transactions (as it warns it will) and then failed, keeping the old
  login.
- **The Mac app answers only at 127.0.0.1 or localhost** (#151). A request
  addressed to any other name is refused, and the app's server no longer
  takes a client's address from an `X-Forwarded-For` header. Nothing changes
  in the app's own window or for the AI connector, which use 127.0.0.1.
- **An https Mempool whose certificate isn't trusted now says so** (#178).
  A Mempool address with a private certificate (StartOS's home-network
  address for Mempool, for example) can't be used, and BitcoinTX said
  nothing: with *Fall back to public price sites* on, the public sites
  answered silently while Settings still said your node did. The status
  line now names the reason, and says when the public sites answered
  instead. Use the Mempool's http:// or .onion address, or on StartOS
  *My Mempool on this server*.
- **A spend's network fee no longer counts twice in its gain** (tax
  figures, #157). When bitcoin was spent (a Withdrawal, purpose Spent) with
  a BTC network fee, the spend's proceeds were the full value received, and
  the fee was also its own small disposal at its value: the gain came out
  too high by the fee's value. The fee paid to make a spend is a cost of
  it (Treas. Reg. §1.1001-7(b)(2)(ii)(A) and its Example 4, a fee paid out of
  the coins sent; the IRS digital-asset FAQ, Q63), so it now comes off the spend's proceeds, as a
  Sell's fee always has; the fee's own row stays (Q97). Example: 0.08 BTC
  spent for $8,800 with an $8.80 fee now has proceeds of $8,791.20, and
  with the fee's row the spend realizes $8,800, not $8,808.80. Applied to
  every year (the owner's decision: before 2025 no rule is written for
  bitcoin, and the general rule that a sale's costs reduce what it brought
  points the same way). Gifts, donations, losses and transfers are
  unchanged: their fee is a disposal, not a cost of a sale.
  **Affected:** versions 0.9.2 to 1.2.7, spends that paid a BTC fee, every
  tax year; each overstated the gain by its fee's value (usually a few
  dollars), so reports showed slightly more tax, never less. **What to
  do:** after updating, Ledger Review lists each spend whose figures
  change, old and new; then run Recalculate Ledger (Settings), or edit or
  delete any transaction, which recalculates too. Returns already filed
  overstated the gain by these fees; whether to amend over a few dollars is
  for you or your tax professional to decide.
- **The AI connector lists a Sell's or spend's gross proceeds** (#157):
  `list_transactions` shows `gross_proceeds_usd`, what was entered (or the
  value from the BTC price), beside `proceeds_usd`, which is after the fee, and the
  guide tells the AI to edit with the gross. Copying the listed after-fee
  value into an edit took the fee off a second time. Update the connector
  (`btctx-mcp`) with this release.
- **An edit can no longer save a negative fee value.** A new transaction
  and a CSV import refused one, but an edit with the AI connector's edit
  tool or the API took it (the form wasn't affected). Such a row now
  refuses other edits until its fee value is set again.
- **Switching StartOS's Price Source & Privacy to "Decide in BitcoinTX
  instead" (called "Choose in BitcoinTX" before this release) no longer
  picks public price sites for you** (privacy, #134). While the action
  sets the source (My Mempool, Public price sites or Nobody), no choice is
  made in the app, but prices get stored. After a switch to **Decide in
  BitcoinTX instead**, BitcoinTX took those stored prices for an install
  from before 1.1.0 (when public sites were on by default), saved
  **Public price sites** as your choice and asked them for prices, without showing its
  price question. A command run without the server's settings saved the
  same choice, ready for a later switch: the package's **Set Login
  Credentials** (Reset Login Credentials before 1.2.4:1), or
  `python -m backend.cli` run by hand in the service.
  - Affected: StartOS (and Docker installs that set `BTCTX_PRICE_SOURCE`),
    1.2.0 to 1.2.7, only installs that stored prices while the server set
    the source and had no choice made in the app.
  - Now BitcoinTX records "not chosen yet" while the server sets the
    source, so after a switch it asks you, whatever the action was set to;
    and a command never makes a price choice. Installs from before 1.1.0
    keep what they did, except one that never changed its price settings
    and first starts 1.2.8 with the source set by the server: it asks once.
  - What could have been sent: requests from the server's address to
    public sites for Bitcoin's price (CoinGecko, Kraken, Bitstamp or
    Coinbase) and the block height (Blockchain.info, Blockstream or
    mempool.space). Never dates, amounts or anything from the ledger. The
    action's Use Tor didn't apply after the switch (the package passed its
    proxy only while the action set the source), so only a proxy set in
    BitcoinTX's own Settings hid the address (on Docker, also a standard
    proxy variable such as `HTTPS_PROXY`). Every request the app can make is listed in
    `docs/PRIVACY_AUDIT.md`.
  - What to do: confirm or change the choice when BitcoinTX asks once
    after the update (next entry), or check Settings › Privacy & Network.
  - What this fix alone couldn't cover (an install whose first start is
    already without the server's source, and a Public choice this bug
    already saved, which looks like your own) is covered by the next
    entry: after this update, BitcoinTX asks once to confirm a price
    choice saved before it, and asks nobody until you do (#145).

### Changed
- **After this update, BitcoinTX asks once to confirm where it gets
  prices** (#145, the owner's request; privacy), unless StartOS or the
  server sets them. A price choice saved before this release has no record
  of when or how it was made, so BitcoinTX can't tell your own *Public*
  choice from one the #134 bug saved by itself. The Dashboard shows
  "Please confirm where BitcoinTX gets prices", with your current choice
  selected: press **Confirm**, or pick another. Until then nothing is asked
  of anyone (not even your own Mempool); prices BitcoinTX already has still
  work. From now on each choice records when it was made and where (the
  first-run question or Settings), which Settings shows; the record is kept
  through an in-app restore. A choice StartOS sets is never asked here; if
  you switch StartOS's action to *Decide in BitcoinTX instead*, a choice
  in the app without a record is asked then (closing #155's last gap).
- **Public price sites: Coinbase and CoinGecko are no longer asked**
  (#161, the owner's decision). Coinbase's market data terms keep its data
  for personal or research use and say it "may not be used to build an
  application intended for use by end users"; CoinGecko's ask for a credit
  and discourage storing its data. Past prices now come from Bitstamp's
  whole daily history (if that download fails, it's tried again later),
  then the latest days from Bitstamp, else Kraken; the live price from
  Kraken, else Bitstamp; a live price of 0, below 0 or not a number (a
  mempool server answers -1 until it has one) is skipped instead of shown.
  Prices already stored don't change. Settings, the
  READMEs and StartOS's Price Source & Privacy action list the sites asked.
- **Values BitcoinTX fills in from the BTC price now use the price when the
  transaction's hour began** (#144, tax figures; the third of five pull
  requests). That's an income or rebate deposit's value left blank, a
  Spent withdrawal's proceeds left blank, a BTC network fee's value, and
  what the AI connector's and River imports fill in. IRS rules value bitcoin
  at the date and time of each transaction (Treas. Reg. §1.1001-7(b)(3));
  the day's midnight (UTC) price used so far could be hours from it (on
  2025–2026 prices, about 1% off on average, the hour about 0.24%). The
  price is Bitstamp's opening price for the UTC hour (the hourly history
  above) or, for later hours, your mempool server's hourly record or
  Bitstamp's latest hours; where there's none (before 2013, or no source
  answering), that day's 00:00 UTC price as before. An inheritance's value
  (#154) stays at its date of death's day price: a date has no hour. Each
  transaction now records which moment its priced values came from
  (`price_moment`: hour or day), and a Spent's proceeds from the price are
  marked like an income value's, so an edit of its amount or hour prices
  them again.
  - **Nothing already saved changes.** Values priced before this release
    stay at the day's price, marked "day". An edit that changes what a
    priced value depends on (its amount, account, type, or now its hour
    rather than its day) prices it again, at the hour; on a spend whose
    other priced value (its proceeds, or its network fee's value) keeps the
    day's price, at the day, so a transaction's values share one price
    (Ledger Review offers both at the hour). A recalculation never
    re-prices anything. A value you typed is never touched.
  - An entry dated today whose hour hasn't begun (a date alone means noon
    in the tax timezone) takes that day's price, marked "day"; a later
    day has no price, as before.
  - The CSV export carries the marks (two new columns, `proceeds_typed`
    and `price_moment`); an older file imports as before, its priced
    values counted as priced at the day.
- **The form and the AI connector say "the price when that hour began"**
  (#144). The form's hints for a blank income value, Spent proceeds and a
  fee's value say so, a stored fee value says which price it came from,
  and a gift's, donation's or lost bitcoin's **Refresh** fills its value at that hour's
  price (it asked for the day's). The price API takes a time
  (`/api/bitcoin/price/history?at=…`, answering which price it used), and
  the AI connector's `get_btc_price` takes a transaction's time and gives
  the price BitcoinTX values it at; its guide says the same. Update the
  connector (`btctx-mcp`) with this release.
- **Ledger Review offers the hour's price for values priced at the day**
  (#144, tax figures; the fourth of five pull requests). Its new check,
  "Values priced at the day's price that the hour would change", lists, by
  tax year, each transaction whose values BitcoinTX filled in at the day's
  price (income or rebate values, Spent proceeds, network fee values) and
  what its hour's price would make them; changes under $1.00 aren't listed
  one by one but are in each year's totals. Nothing changes until you tick
  some and apply them, or apply a whole year (Settings, or `python -m
  backend.cli review --apply-hourly-prices YEAR`): a backup copy of the
  database first (in `backups/`, its newest 5 kept apart from the update's
  copies), then the values at the hour (the day's price where
  there's no hourly price), marked so, and a recalculation. For a year
  you've filed, leaving it as filed is recommended; whether to amend is a
  question for a tax professional. Typed values and inheritances (valued
  at the date of death's day) are never listed. It replaces "Transfer fees
  valued far from that day's price" and its **Fix these** (`review
  --fix-fee-prices`): such a fee is in this check, at its hour's price
  (listed when it changes by $1.00 or more). The
  check of income and rebate values now covers only the ones you typed,
  compared with that hour's price.
- **The Complete Tax Report states how values are priced, and values
  holdings at the hour the tax year ends** (#144, tax figures; the last of
  five pull requests).
  - Its Notes say how a blank value is filled in: Bitstamp's hourly
    opening price, downloaded by BitcoinTX and checked against published
    fingerprints, or your own Mempool server's record; that day's price
    where there's none; an inheritance at its date of death's. They also
    say that the IRS measures value at the date and time of each
    transaction (Treas. Reg. §1.1001-7(b)(3)) and approves no price source
    or method, and that a value from your own records is better evidence.
  - A new table, **Values from the BTC price**, lists each of the year's
    values BitcoinTX filled in (income, rebate and inherited values, Spent
    proceeds, network fee values) and the price each used: when its hour
    began, that day's 00:00 UTC price, or the date of death's. Every other
    such value was entered. (A gift's or donation's value isn't tracked
    this way; the report says so.)
  - **Holdings at the start and end of a tax year** are valued at the
    price when it began and ended (midnight in the tax timezone: the
    hour's price, else that day's), so one year's end and the next one's
    start agree. Before, the year-end value used December 31's 00:00 UTC
    price, hours before the year ended (29 hours in New York, 15 in
    Tokyo). Holdings values are for information (no
    IRS form takes them); a report made before the year ends leaves them
    unpriced, as before.
  - With a donation, the gifts section says a deduction over $5,000 needs
    a qualified appraisal (IRS digital asset FAQ, Q78).
- **The live price says where it came from and when** (#145, the price
  source redesign): `GET /api/bitcoin/price` adds `source` (`mempool`,
  `kraken` or `bitstamp`) and `at`, so the screens can say when your
  Mempool's backup answered instead. The price messages use the new words:
  "Nobody" for the choice once called Off, "not chosen yet", "your
  Mempool" and "the backup (public price sites)", and they say where to
  change a choice the server sets (StartOS's Price Source & Privacy action
  once the package passes the new `BTCTX_HOST=startos`;
  `GET /api/settings/network` adds `host` and `invalid`). Invalid server
  settings say so instead of "Price lookups are off".
- **The tax report and the AI connector say where each price came from**
  (#145). The Complete Tax Report's list of values filled in from the BTC
  price names the source of each price ("When its hour began (2025-03-01
  14:00 UTC), Bitstamp", or "your Mempool"); no figure changes. The AI
  connector's `get_btc_price` and `get_portfolio` give the price's
  `source` ("mempool" for your own Mempool, otherwise the public site), and
  when there's no live price, `get_portfolio` gives BitcoinTX's reason
  (`btc_price_unavailable`). Its guide explains the price choices (your
  Mempool, public price sites, Nobody), that only you change them (in
  Settings, or where the server sets them: StartOS's Price Source & Privacy
  action), and that it asks you for a value BitcoinTX has no price for.
- **Where prices show, in the redesign's words** (#145). The Dashboard's
  Current Bitcoin Price says where the price came from and when ("From
  your Mempool · 2:02 pm", "From public price sites (Kraken)"), or why
  there's none and what to do: "Offline" (you chose Nobody), "Not chosen
  yet" or "Confirm your choice" (with a link to the card), "No answer" (the
  reason, and a link to change the source). The sidebar converter says
  "offline", "not chosen yet" or "no answer" instead of "Prices off" and
  "No price", with **Type a price** (Manual) or a link to the card, and its
  Date mode gains an hour, in your tax timezone, looked up in BitcoinTX's
  own history. When you edit a transaction, a value BitcoinTX filled in
  says which price it came from ("From the price: $50,083.00 at 14:00 UTC,
  Mar 1, 2024 · Bitstamp"), and one you typed says "Typed". The API gives
  each transaction's `price_used` and each past price's `source`; neither
  asks anything.
- **The price card says where the hourly history is** (#145): before a
  choice, that it's downloaded once from Bitstamp when you choose public
  price sites (or your Mempool with its backup), each year checked against
  a fingerprint that comes with BitcoinTX; then its progress, year by year;
  then "downloaded and checked", from when it works offline whatever you
  choose. With *Nobody*, or your Mempool alone, the card says what that
  means for older values. And a server can lend its Tor to a choice made
  in the app (new `BTCTX_TOR_PROXY_URL`; StartOS's *Use Tor* with *Decide
  in BitcoinTX instead*): Settings shows "Through Tor: Tor on this server", locked on.
- **One price card, the same everywhere** (#145): where BitcoinTX gets
  Bitcoin prices is now one card with three choices, *My own Mempool* (with
  *If it can't answer, ask public price sites*), *Public price sites*
  (Bitstamp and Kraken, optionally *Through Tor*) and *Nobody*. It's the
  first-run question, now on the Dashboard only, and Settings › Privacy &
  network, read-only when StartOS or the server sets it. Choosing no
  longer reloads the page. A status line says where newer prices come
  from now and when the last one arrived, or why there's none (new
  `GET /api/bitcoin/price/status`, login only, which asks nothing itself).

### Documentation
- **The README and the AI connector's README in the redesign's words** (#145):
  who BitcoinTX asks for newer prices (your Mempool, public price sites,
  Nobody), prices at the hour from the one-time, fingerprint-checked
  Bitstamp download, and that one price per hour won't always match a chart
  of one exchange at another moment.
- **The README's screenshots are 1.2.7's** (#141), the same as the landing
  page's: the Dashboard's Rebates line, a rebate in Transactions, and the
  setup prompt asking for btctx-mcp==1.2.7. They were from 1.2.2.

### Known limitations
- **Through Tor, Bitstamp refuses BitcoinTX's requests** (#241; found in
  the 1.2.8 release tests, PRC-3b: 403 or its "Loading" challenge). With
  public price sites (or your Mempool's public backup) through Tor, the
  hourly history and every past price from Bitstamp fail; only the live
  price works (Kraken). It fails safe: no direct request, never $0. Choose
  public price sites without Tor to download them (a checked hourly history
  stays, whatever you choose later), use your own Mempool for newer values,
  or type them. The price card now says so when Bitstamp refuses through
  Tor, instead of asking whether Tor is running, and so do the Through Tor
  box and StartOS's Use Tor. A fix is planned for 1.2.9.

### StartOS package
- **Price Source & Privacy, in the redesign's words** (#145). The action asks
  who BitcoinTX asks for newer prices: **My Mempool on this server**
  ("recommended: installed" once Mempool is), **Public price sites**,
  **Nobody** or **Decide in BitcoinTX instead**, with **Use Tor** and **If
  Mempool can't answer, ask public price sites**. A new install doesn't
  start until a choice is made (any of the four, Nobody included: Start9's
  "critical" task, as for the login). After an update or a restore of an
  install that was never asked and has no choice made in the action, an
  "important" task asks once, without stopping the service. **Use Tor**
  with *Decide in BitcoinTX instead* now lends StartOS's Tor to the app's
  own choice. The package passes
  `BTCTX_HOST=startos`, so the app's messages name this action. Texts in
  five languages; the README and instructions say the same.
- **Start9's 1.2.7:1, taken back** (`scripts/start9-pull.sh`): start-sdk
  3.0.6, whose fix stops every process of the previous run when BitcoinTX
  is restarted while still starting, and the action-result fields it
  requires (`launchable: false`). Start9 published it on 2026-10-12.
- **Package 1.2.8:0.** Release notes in five languages: what to do after
  updating (Ledger Review, then Recalculate Ledger; confirm the price
  choice; log in again; update the AI connector), the spend fee fix
  (#157), what #134 could have sent and who could be affected, and what's
  new. The update raises **Recalculate Ledger** once, an important task
  that doesn't stop the service (the owner's choice, 2026-10-13), so
  #157's corrected figures reach existing transactions; its text now says
  to open Ledger Review first.

### Development
- **CI runs once per change** (owner, 2026-10-13): on each pull request (which tests the branch merged with its base) and each push to `develop` or `main`, no longer again for the same commit's branch push. Each pull request's merge waits for one run instead of two, and a fluke in the second can't block it. The macOS app build now runs on pull requests too (not a required check). A flaky WebKit reload in the price matrix is #231.
- **Two privacy tests see more** (the stable candidate's privacy audit,
  #151). The test that every site public prices may contact is named in
  Settings, and is never Coinbase or CoinGecko, read only the three price
  modules: it now reads every backend module (the IRS's draft forms, the
  one admin's command, from `draft_forms.py` only), and no string may name
  either site at all. And a new test checks the screens call only the API
  they were served from: the Mac app's window has no browser policy to stop
  a request to another site, so the screens' code may name no other site
  but links, an example address and SVG's namespace, each only in the file
  that names it today.
- **Big work runs as a main session and numbered sessions** (AGENTS.md,
  "Big work"; `docs/HOW-CHANGES-FLOW.md`). The owner's standard since the
  stable release (#143): one session plans with the owner. The plan goes
  on GitHub: an umbrella issue, an issue per session with its checklist,
  and a kickoff prompt on each. Each session works through its checklist
  and records its decisions on its issue. Small changes stay in one
  session. The main session keeps a handoff for itself on the umbrella
  issue, current after every change, so a new one can take over. The plan
  lists each session's footprint, its shared hot spots, any reserved
  migration numbers and the merge order, so conflicts are few and
  expected.
- **The hourly price history's record and tools** (#144, the first of five
  pull requests; nothing in the app uses them yet).
  `backend/assets/btc_prices/MANIFEST.csv` holds, for each year from 2013,
  the SHA-256 fingerprint of a plain-text file of Bitstamp's hourly opening
  prices (one row per UTC hour), so every install that downloads them will
  hold exactly the same prices. `make prices` (`scripts/price_history.py
  refresh`, in each release's bump pull request) adds the new hours and
  refuses, writing nothing, on a missing hour, a changed past price, or a
  disagreement with Bitfinex or Kraken (no hour over 2% apart, a median gap
  of 0.5% at most, and the hours must line up better than shifted by an
  hour: limits measured on 2023–2026). The release workflow checks it
  again, and a monthly workflow opens an issue if Bitstamp stops giving a
  year's fingerprint or stops answering. Closed years are pinned by
  a test. The folder's README explains it all in plain words.
- **The reference ledger's figures, checked by a second calculation**
  (#150). `scripts/independent_figures.py` recomputes every Form 8949 row,
  Schedule D line, box total, gains summary, income and rebate figure, gift
  and year-end lot of the reference test ledger from the rules (FIFO per
  account, fees, transfers, dates originally acquired, the holding period,
  the boxes), importing nothing of the app, and a test fails on any
  difference from the app's saved figures. For 2023 to 2026 there is none,
  to the cent; the printed 2024 and 2025 forms carry the same figures. Three
  rounding conventions are shared with the app on purpose (the script says
  which). With the usual half-up rounding instead of the app's half-down,
  the exact half-cent ties #100 covers move a cent: 2024 one row, 2025
  four, 2026 two (one by a cent of proceeds), and one year-end lot a year.
- **The sidebar's converter and calculator, tested under every price
  source** (#147). A new click-through file, `e2e/sidebar-matrix.e2e.ts`,
  uses Auto, Date and Manual and the calculator in each state the app has:
  not chosen yet (then picked in the first-run question), off, public
  sites, public sites through Tor (running and stopped), the own mempool
  server (answering and down), with the public backup (the mempool server
  answering and down), and set by the server (StartOS); the Mac app's mode
  repeats the first-run question and off. Auto shows the live price or a
  plain message, never $0.00; Date that day's price (each past day has its
  own, so a lookup of the wrong day shows) or a plain message; Manual works
  from a typed price throughout; the calculator carries on across mode
  switches and stays put. The prices come from a fake internet
  (`fake_internet` in `scripts/smoke_test.py`, the `fakeInternet` fixture
  option) instead of stubbed functions, so the app's own choice of source,
  backup and proxy runs (a request it never makes gets no price), and each
  test checks what the server sent out: nothing before a choice or while
  off, only to the chosen source (every public request through Tor when
  it's set), and nothing naming the day, in any form from the day before to
  the day after; the browser asks nobody but BitcoinTX, from its first
  request. Chromium (Chicago and Tokyo) and WebKit.
- **A Mac test build calls itself "BitcoinTX Test"** (#142) in its window
  title and its messages ("BitcoinTX Test is already open", a busy port),
  whenever it runs on a throwaway data folder (`desktop/run-test-build.sh`).
  During the 1.2.7 release tests the owner saw the test copy's "already
  open" message, took it for their own app's, and quit the real one: now
  its window and messages can't be taken for the installed app's (the menu
  bar and the Dock still say BitcoinTX: they come from the bundle).
- **One reference test ledger, and its figures can't move unnoticed**
  (#139, closes #122). The full test ledger was rebuilt from code in
  `scripts/seed_ledger.py` each time, and had no Rebate source and no date
  originally acquired. It is now one data file,
  `testdata/reference_ledger.json` (111 transactions, 2023 to 2026): every
  kind of transaction each year (from the app's own lists, so a new kind
  fails the test until the ledger has one), every account route, every
  broker-reporting choice, every Form 8949 box, a rebate each year
  (the 2025 "Purchase rebate in BTC" entered as Reward is a Rebate now, as
  #98 tells users), and My BTC and Gift deposits with a date originally
  acquired that FIFO sells first. `seed_ledger.py`, the printed-forms
  tests and the before-and-after check (`scripts/equivalence_check.py`,
  whose inputs also try Rebate and `acquired_at` now) load it.
  `testdata/reference_figures.json` holds every figure it gives (each
  year's Form 8949 rows and Schedule D, the complete tax report's data, the
  dashboard), and `test_seed_ledger.py` fails, naming where, if one moves;
  `make reference-figures` accepts a meant change, which the pull request
  then shows. The release tests keep each release's database of it in the
  test lab and check the next release against it (AGENT-TESTS REF-2/3;
  `scripts/reference_figures.py --db … --compare`).
- **The README's and landing page's pictures, from one command, in the
  release tests** (#139). `make site-shots` (`frontend/e2e/shots/site.ts`)
  takes the four pictures from the checkout's app at the site's size, with
  fixed test prices and a small saved portfolio
  (`testdata/showcase_ledger.json`), into `docs/images/`, so git shows which
  changed; the agent release tests run it (REF-1), and the release's
  landing-page step puts the changed ones in the README and on btctx-site
  together (the landing page shown to the owner first).

## [v1.2.7] - 2026-10-11 - Rebates on the dashboard, a clearer Ledger Review reminder

### Added
- **Rebates on the dashboard** (#129). The Income & Fees card showed
  income, interest, rewards and gifts, but rebates (card sats-back,
  shopping cash-back, new in 1.2.6) nowhere. They now have their own line,
  Rebates (received), in USD and BTC, under Gifts (received): like gifts,
  not added to income or gains. The sidebar calculator's keys are a little
  taller (42 to 49 px), so it still ends level with the cards.

### Changed
- **Ledger Review: the missing "date originally acquired" is a reminder,
  not an error** (#128). After the 1.2.6 upgrade it listed every older My
  BTC and Gift deposit, each with the same two sentences, under
  "Transactions to check", so it read like a long list of errors and could
  bury the checks that do point at a wrong figure. These rows aren't
  errors: a blank date counts from the deposit, so no sale is long-term too
  early (though a date can also change which coins are sold first).
  It now comes after the checks as "Reminder: My BTC and Gift deposits
  counted from their deposit date", isn't counted in the review's total,
  and explains once, in plain words: change the Source if they are really
  income, interest, rewards or rebates, and check the cost basis (no date
  needed; before 1.2.6 there was no Rebate source, so card sats-back may
  have been saved as My BTC); the two dates and which one each kind of
  coins uses, with the gift rule BitcoinTX doesn't apply (#104); what a
  blank date means, and that a date can change a year's gain either way;
  enter only a date you can back up. In Settings the list is
  folded behind **Show**. `cli review` and the AI connector's
  `review_ledger` carry the same explanation (`kind: "reminder"`, a
  separate `reminders` count).
- **Timezone rules: tzdata 2026.5** (upstream 2026e, #67). Manitoba moves to
  permanent UTC−5 on 2026-10-31; this matters only with the tax timezone
  America/Winnipeg, for dates after that. No figure moved in the
  before-and-after comparison.

### StartOS package
- **Package 1.2.7:0.** Release notes in five languages. They keep 1.2.6's,
  which StartOS users updating from 1.2.5:0 haven't seen, marked "From 1.2.6".

### Development

- Dependencies: `lucide-react` 1.52.0 (#66; the icons BitcoinTX uses draw
  the same) and `hypothesis` 6.168.4 (#73, tests only).
- **The pre-push gate finds a Python with the dev tools.** It took the
  first interpreter that existed, `desktop/.venv` first, so after a Mac
  build (whose venv has no ruff), or in a worktree with no `.venv`, the
  push failed at ruff until `BTCTX_PYTHON` was set. It now takes the first
  with ruff and pytest: this checkout's `.venv`, the main checkout's, then
  `desktop/.venv` and `python3`, and says so plainly if there is none.

## [v1.2.6] - 2026-10-10 - Accurate income and holding periods, rebates, cleaner IRS forms, one wallet stated plainly

### Added
- **A "Using these forms" page in the Complete Tax Report** (#79), for
  whoever files the return, often a tax preparer handed the PDF. It says
  what BitcoinTX fills on Form 8949 (every Bitcoin disposal, a page or more
  per box) and on Schedule D (lines 1b to 3 and 8b to 10), and what it
  leaves blank on purpose, and why: lines 1a and 8a (every sale is on Form
  8949), the loss carryovers (lines 6 and 14), other sources (lines 4, 5,
  11 to 13), the lines that combine everything (7, 15, 16, 21 and Part III)
  and the opportunity fund question. For a year BitcoinTX has no forms for,
  it says how to fill them from the report (Form 8949 instructions,
  Exception 2); for a year of drafts, to file on the final forms. It gives the
  Bitcoin-only figures for lines 7, 15 and 16 ("if bitcoin is the only
  capital asset and there's no carryover"), with line 21's rule for a net
  loss ($3,000, or $1,500 married filing separately). It also says to write
  the name and SSN on every Form 8949 page and print single-sided, the
  one-wallet-one-exchange assumption, that the gift
  rule of IRC §1015 isn't applied (#104), and that BitcoinTX is not tax
  advice. A report made before December 31 says, on its cover and on this
  page, that the year isn't over yet.
- **Updating the AI connector, as a clear step** (part of #97). The
  connector is pinned in your AI app's settings (`uvx btctx-mcp==X.Y.Z`) on
  purpose: nothing new runs on its own, and PyPI sees you once per version.
  After updating BitcoinTX, change that one number to the new version and
  restart the AI app: no new key, nothing to set up again. The README's
  Upgrading steps now say so, the connector's README (the PyPI page) has an
  "Updating" section with where to change it in Claude Desktop, Claude Code,
  Cursor, Grok Build and LM Studio, and Settings → Connect an AI Assistant
  shows the version to set. The README also names StartOS's **Set Login
  Credentials** action, which replaced Reset Login Credentials in 1.2.4:1.
- **One disclaimer, and the one-wallet limit you can't miss.**
  - The README gains a "Disclaimer" section: "BitcoinTX is software, not
    tax, legal or financial advice. It works from the records you enter:
    check its figures with a tax professional before you file." It also
    carries the MIT License's "as is, without warranty". The landing page
    uses the same words; the app, the StartOS listing and the AI connector
    follow in this release.
  - "One wallet, one exchange" opens with GitHub's "Important" box, as the
    landing page does with an amber box. Since 2025, IRS rules require cost
    basis to be figured wallet by wallet and account by account, so with
    several wallets or exchange accounts BitcoinTX's gains can differ from
    what the rules give. The StartOS instructions say the same.
  - In the app (part of #97): Settings → About BitcoinTX opens with that
    notice in an amber "Important" box, followed by the disclaimer; the
    Reports page carries the disclaimer under Export; and choosing the
    Bitcoin Wallet in a transaction shows one short line, "One self-custody
    wallet: see Settings → About." The IRS Reports choice now reads "for you
    and your preparer to check before filing" instead of "ready to file".
  - In the PDFs: the footer of both reports asks you to check them with "a
    tax professional" (it said "your tax advisor"), and the Transaction
    History ends with the disclaimer instead of "please consult your
    accountant".
  - In the AI connector: its README (the PyPI page) gains a "Disclaimer"
    section, and when you ask your AI a tax question beyond what the ledger
    shows, its guide has it say that BitcoinTX's figures aren't tax advice
    and suggest your tax preparer for filing decisions.
- **Who BitcoinTX is for, said plainly.** The README ("One wallet, one
  exchange") and the StartOS instructions ("Limitations") now say that
  BitcoinTX tracks one self-custody Wallet and one Exchange on purpose. Since
  2025, IRS rules require cost basis to be figured wallet by wallet, so
  anyone with several wallets or exchanges should keep separate records for
  each, or ask their tax preparer. Several wallets and exchanges is an idea
  for 2.0 (#86, on the roadmap).
- **The AI connector says so too.** When you tell your AI assistant about a
  second wallet or a second exchange, its guide has it say once that
  BitcoinTX pools it with the first, and why that matters for taxes since
  2025, and records it in Wallet or the Exchange accounts, never as a
  withdrawal to External (#92).
- **About BitcoinTX, at the bottom of Settings.** It shows the version a bug
  report asks for, with the release notes, and where to report a problem: a
  public report, the open bugs already known, and a private report for a
  security problem. The links only open GitHub when clicked; BitcoinTX sends
  nothing. The unused footer, which said "All rights reserved" although
  BitcoinTX is MIT-licensed, is gone.

### Fixed
- **A Gift deposit's basis hint asks for the giver's basis** (#115). The
  transaction form told every BTC deposit that isn't income "What this BTC
  cost you"; for a gift, the cost basis is the giver's (IRC §1015), as the
  AI guide and the Complete Tax Report say. It now reads "The giver's cost
  basis: what they paid for these coins (type 0 if unknown)", and Ledger
  Review's advice for a deposit without a basis says the same. What to do:
  Ledger Review lists Gift deposits saved with a $0 or blank basis; enter
  the giver's basis where you know it.
- **Bitcoin back for spending was counted as income** (tax figures, #98).
  A rewards card's sats-back or shopping cash-back entered as a Reward
  deposit (the AI connector's guide even suggested it) was counted as
  income. Such bitcoin is generally treated like a rebate on the purchase
  price, not income (by analogy with Rev. Rul. 76-96; the IRS has no ruling
  on bitcoin back for spending); its value when received is its cost basis.
  - Affected: every version up to 1.2.5, any tax year, only deposits of
    that kind entered as Reward.
  - Now there is a deposit source **Rebate**: valued like income (left
    blank, it's that day's price times the amount, its cost basis), but
    never counted as income on the report, the dashboard or the Transaction
    History; the Complete Tax Report lists rebates in a table of their own,
    and its "Using these forms" page says they aren't income.
    Reward stays income (mining, staking, sign-up and referral bonuses),
    and the transaction form says which is which. The CSV import and
    export, the AI connector and Ledger Review's value checks take Rebate.
    Nothing changes by itself after the update.
  - What to do: open each card or shopping reward entered as Reward and
    change its source to Rebate (its value stays the same; its income goes
    away). Keep mining, staking and bonuses as Reward. Ask your tax
    professional if unsure.
- **Form 8949 prints tiny BTC amounts in full.** An amount under 0.000001
  BTC (100 satoshis), such as a small network fee, printed in column (a) as
  "5E-8 BTC" instead of "0.00000005 BTC". Ledger Review and the River
  import's "likely the same event" note showed such amounts the same way.
  All now print eight decimals. The figures were right; only the
  description was hard to read. Closes #74.
- **Losses print in parentheses on Form 8949 and Schedule D.** The IRS
  instructions ask for negative amounts in parentheses, "(9.74)"; the forms
  printed "-9.74" in column (h), on line 2 and on Schedule D's lines, while
  the Complete Tax Report already said they used parentheses. The figures
  are the same. Closes #75.
- **Ledger Review lists income deposits with a $0 or blank value** (#77).
  Such a deposit reports no income, which the income rules forbid, yet it
  slipped past both of Ledger Review's basis checks. A new item, "Income
  and rebate deposits with a $0 or blank value" (rebates since #98), lists
  them with their value at that day's price, so they can be fixed (clear
  its Cost Basis (USD) to use the day's price, or type the right one).
- **No more blank pages in the IRS forms PDF.** Each Form 8949 sheet
  printed both of its pages, so a short-term sheet was followed by an empty
  Part II (28 blank pages in a 58-page 2026 draft), and a long-term-only
  sheet by an empty Part I. Only the Part a sheet uses is printed now, as
  the instructions allow ("complete and file either Part I or II");
  Schedule D keeps both pages. Closes #78.
- **Editing an income deposit could leave the wrong income** (tax figures,
  #76, #110). An Income, Interest or Reward deposit into Wallet or Exchange BTC is
  valued at that day's price when its value is left blank (by you, a CSV,
  the River import or the AI connector), and that value is both its cost
  basis and the income on the tax report. An edit could keep the wrong
  figure (an old value can be too high or too low, and $0 understates the
  income; either way the later gain is off by the same amount in the other
  direction. The third overstates the income):
  - **the old value**, after changing the deposit's amount or date (from
    the form, the AI connector or the API);
  - **$0**, after moving a deposit from Bank to Wallet or Exchange BTC with
    the AI connector's edit tool or the API (the form wasn't affected).
  - **income counted on a USD deposit**: an Income, Interest or Reward
    deposit into Bank or Exchange USD that carried a value (one moved there
    from Wallet or Exchange BTC by the AI connector or the API, or created
    with a value through the API, the AI connector or a CSV import) was
    counted as income on the report and the dashboard (a Gift's in the
    dashboard's gifts), its dollar amount shown as BTC.
  - Affected: versions up to 1.2.5, any tax year, only income deposits
    edited or entered that way.
  - Now a value from the day's price is marked as such, and is priced again
    when you change the deposit's account, amount, date or source (a change
    between Income, Interest, Reward and Rebate, which value it the same
    way, keeps it); a value
    you typed stays as you typed it; and income on the report and the
    dashboard counts only deposits into Wallet or Exchange BTC, whatever
    value a USD deposit carries (a partial edit that moves one to a USD
    account also clears its value). Apart from that, the update changes no
    figure: it marks an existing value only where it is exactly that day's
    price times the amount (migration 0006; a typed value that happens to
    equal it is marked too, and is then priced the same way), and the mark
    only decides what the next edit does. The CSV export and import carry it
    (`cost_basis_typed`), as the AI connector's import and the River import
    do.
  - What to do: after updating, run Ledger Review (Settings), and fix each
    income deposit it lists with a $0 or blank value, or a value far from
    that day's price: clear the value to use the day's price, or type the
    right one. Dollar interest from a bank or an exchange recorded as an
    Income, Interest or Reward deposit into Bank or Exchange USD no longer
    shows as income in BitcoinTX: it isn't bitcoin; report it from the
    bank's or exchange's own tax form (such as Form 1099-INT or 1099-MISC).
- **Coins you already owned, or received as a gift, keep their holding
  period** (tax figures, #91). A My BTC or Gift deposit into Wallet or
  Exchange BTC has a new optional field, **Date originally acquired**: when
  you first bought the coins, or, for a gift, when the giver did (IRC
  §1223(2)). BitcoinTX counted the holding period from the deposit, so a
  sale within a year of it was reported **short-term**, with the deposit's
  date in Form 8949 column (b), even for coins held for years.
  - Affected: every version up to 1.2.5, every tax year with such a sale.
  - With the date, the holding period and column (b) use it, and
    first-in-first-out treats those coins as acquired then (the oldest in
    the account are sold first). A transfer keeps it. The form, the CSV
    export and import (`acquired_at`), and the AI connector take it; its
    guide asks for it. The update changes nothing until you fill one in
    (migration 0007 adds an empty column).
  - What to do: open Ledger Review (Settings). Its new check lists My BTC
    and Gift deposits without an original date; enter the date for each one
    you know, then download your forms again. A date can change the term
    and basis of sales in years already filed (those coins are then sold
    first): ask your tax professional whether to amend.
  - Not covered: the gift rule for coins worth less on the day of the gift
    than the giver paid (IRC §1015), which needs the day's value (#104).
- **The CSV template imports as it is on a new install.** Four of its
  sample rows had a BTC fee without its dollar value (`fee_usd`), so before
  a price source was chosen, or with prices off, the import stopped at "No
  BTC price is stored" and saved nothing. Each fee now has its value. The
  template also gains a Rebate row, and its Gift row, like the CSV guide,
  says a gift's cost basis is the giver's.

### StartOS package
- **Connect an AI Assistant's Claude Code command works in every folder**
  (#116). It lacked `--scope user`, so Claude Code (whose default scope is
  the current folder) saved BitcoinTX's connector for the folder it was run
  in only; Settings → Connect an AI Assistant and the setup guide already
  gave `--scope user`. Set up with the old command? Move the `bitcointx`
  entry in `~/.claude.json` from your folder's `projects` entry to the
  top-level `mcpServers` (it keeps your key and certificate path). To use
  the new command instead, first remove the old entry with
  `claude mcp remove bitcointx -s local` in that folder, then put your key
  and certificate path into the new one.
- **The store listing says who BitcoinTX is for, and the instructions say
  it isn't tax advice.** The short description is now "Bitcoin tax tracker
  for one wallet and one exchange, optional AI-assisted entry", and the long
  one opens with the one-wallet limit (since 2025, IRS rules figure cost
  basis wallet by wallet and account by account) and ends with the
  disclaimer, in all five languages (Start9's `manifest.md`: short about 80
  characters, the one-wallet limit first so a clipped tile still shows it;
  long under 2,000). The
  instructions (Start9's `writing-instructions.md`) carry the disclaimer
  next to Reports, where it can be acted on, and a line on updating the AI
  connector after each BitcoinTX update; the one-wallet Limitations line
  stays as it was.
- **Start9's move to start-sdk 3.0.3, taken back (still package 1.2.5:0).**
  Start9 moved their fork to the new SDK
  (Start9-Community/BTCTX-StartOS#3) and asked that our 1.2.5:0 be built on
  it, keeping its version, since 1.2.4:1 never reached their main registry.
  The package now needs StartOS 0.4.0.2 or later. Connect an AI Assistant
  shows the root certificate and the Claude Desktop configuration with
  their line breaks, and offers the certificate as a download; Price
  Source & Privacy explains each choice on its own line. Mempool and Tor
  are declared the SDK 3 way (`sdk.Dependency.optional`), still optional
  and needed only by the price source that uses them. The package's file
  models keep keys they don't model. The 1.2.5:0 release notes gained
  those two sentences in every language. Closes #27.

### Development
- **A Mac app build can be tested without touching a real ledger.**
  `desktop/run-test-build.sh` runs a build on its own data folder (log
  included) and port 8766, the same on every launch. It uses only a folder
  that is empty or its own, never the installed app's however it is
  spelled; underneath, `BTCTX_DESKTOP_DATA_DIR` moves the app's data folder
  (`desktop/desktop_paths.py`). The Mac docs and the agent release tests'
  Track C no longer say to `open` a build, which would open the installed
  app's ledger. A test run that finds itself already open
  doesn't bring "BitcoinTX" forward by name, which could start the
  installed app.
- **The before-and-after check hides the report's time again.** Since 1.2.5
  the Complete Tax Report prints when it was made on a "GENERATED" line,
  which `scripts/equivalence_check.py` didn't mask, so every comparison
  showed a difference there (found in the review of #96). Needed for the
  1.2.6 tax-figure fixes.
- **The printed forms are read back by the tests (#80, first part).** A QA
  pass of a 2026 draft found defects only the printed PDF showed. The new
  `test_printed_forms.py` reads each value of the flattened Form 8949 and
  Schedule D where it is drawn, for the full test ledger and the golden one,
  and checks every row is printed once in its box with its figures, each
  row and page adds up, Schedule D's lines are their boxes' sheets, and the
  Complete Tax Report's box table shows the same figures.
- **Feature requests and the mirror's issues, in the process.**
  - A feature request gets a thank-you and no promise. The owner decides:
    the roadmap, "not planned" with a reason, or open.
  - The mirror DigiMonk73/BTCTX-StartOS has its Issues off, with a
    description pointing here. Its three unanswered issues from January
    were moved here and answered: #85 and #87 closed as fixed, #86 open
    as an idea.
- **Start9's rules win for everything Start9 governs, now written down.**
  That's the StartOS package, the mirror, which pages Start9's support
  indexes, and everything sent to their fork. The app, its Docker image
  and the Mac app keep our own rules. AGENTS.md "Start9" asks that the
  guide be checked first and the page each decision follows be named.
- **A final docs check before each release.** Merging doesn't update the
  docs by itself, so before `main` moves to a release a fresh Claude reads
  every doc against what the release ships: the READMEs, the StartOS
  instructions, store descriptions, actions and release notes, the AI
  connector's guide, `docs/`, the app's on-screen text and the CHANGELOG.
  Anything stale is fixed first (AGENTS.md "Releasing", step 1;
  `docs/HOW-CHANGES-FLOW.md` section 2).
- **How bugs and security problems are handled, in public files.**
  - `SECURITY.md`: report security problems privately (GitHub's private
    vulnerability reporting, now on). The fix ships first, then a public
    advisory.
  - `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.
  - Bug report and feature request forms. The bug form asks whether a
    tax figure is affected, and has a no-personal-data check.
  - The README gains "Reporting problems", with the open bugs as the
    known-issues list.
  - The `tax-figures`, `security` and `unconfirmed` labels. A user's
    report starts `unconfirmed` and becomes `bug` once reproduced.
  - AGENTS.md and `docs/HOW-CHANGES-FLOW.md` write the process down:
    - every confirmed bug, found by anyone, is a public issue;
    - a security fix goes out before its advisory;
    - a `tax-figures` fix tells users in the release notes what was wrong,
      which tax years it touched, and what to do.
- **The StartOS package builds with the SDK's own tools.** start-sdk 3
  brings TypeScript, Prettier and the bundler, so `startos/package.json`
  lost its `check` and `build` scripts: CI, the pre-push hook and the docs
  run `make javascript/index.js` (type check, lint, format check, bundle)
  and start-cli 2.3.0, which packs only with Docker 28.1 or later: the CI
  pack job and the release install a current Docker
  (`docker/setup-docker-action`, as Start9's own builds do).
  `startos/TODO.md` is gone, as in Start9's template: the package's to-dos
  are issues labelled `start9`. Closes #28.
- **The landing page is a release step.** `AGENTS.md` and
  `docs/HOW-CHANGES-FLOW.md` name DigiMonk73/btctx-site: its download links
  follow the latest release by themselves, its text and screenshots are
  checked and updated by hand at each release.
- **Stale docs found before 1.2.6** (Grok's review of the docs, each
  claim checked first):
  - `docs/AGENT-TESTS.md` expected a dashboard row "Interest and Rewards",
    which the app doesn't have (it shows Interest and Rewards separately),
    and had no checks for 1.2.6's additions. New: AUTH-4b (Settings >
    About), GLD-6c (a Rebate deposit, which isn't income, and the
    one-wallet hint), and the report's "Using these forms" section in
    RPT-5.
  - `scripts/backup-db.sh` had one old machine's paths built in. It now
    takes the database as its argument (or `DATABASE_FILE`) and keeps its
    copies in `daily-backups/` beside it.
  - A dead link to Start9's review in `docs/HOW-CHANGES-FLOW.md`, and the
    finished 1.2.4 box-test checklist in `docs/temp/`, removed.
- **The final docs check before 1.2.6.**
  - The README's StartOS install now names Start9's Community Beta
    registry, with sideloading as the other way (#84).
  - The CSV template's fix and new rows (under Fixed).
  - The Complete Tax Report's Notes now say "check it with a tax
    professional before you file", like the rest of the report.
  - The AI connector's tool descriptions and guide match 1.2.6.
  - For maintainers: wording fixes in AGENTS.md and `docs/`.

## [v1.2.5] - 2026-10-06 - A preview of the 2026 forms, a professional Complete Tax Report, Start9's review of the StartOS package

### Added
- **A preview of the 2026 tax forms.** The IRS's final 2026 Form 8949 and
  Schedule D usually come out in December or January; until then Reports
  offers 2026 as "2026 – IRS draft (preview, not for filing)", filled from
  the IRS's draft forms, which say "DRAFT — DO NOT FILE" on every page,
  with a warning not to file them. On January 1, 2027 the preview stops by
  itself, so nobody files a draft from a version they never updated: the
  final forms come in an update, which replaces it. Reports now also says,
  for a year without forms yet, that they come in an update (#53).
- **A full test ledger on any server, and 2026's forms from the IRS
  drafts, for testing only.** `scripts/seed_ledger.py` loads 103
  transactions (2023 to 2026) into a running BitcoinTX over its API: every
  year has every kind of transaction, and every report has entries in each
  part, every Form 8949 box of 2024 (A–F), 2025 and 2026 (G–L) included, in
  any tax timezone.
  Every USD value a price lookup would fill is given, so it loads with the
  price source Off. It refuses a ledger that has
  transactions and the Mac app's address. On a test install,
  `python -m backend.cli install-draft-forms` puts the IRS's draft 2026
  Form 8949 and Schedule D in the data folder; Reports then offers 2026,
  labelled as the IRS draft, and prints them with the IRS's
  "DRAFT — DO NOT FILE" on every page. The drafts are checked like a final
  form (year, marking, every field the app writes), and are ignored once a
  version has that year's final forms. The StartOS test lab's `vmtest seed` uses both, so
  every report can be clicked through on the VM without the owner's real
  ledger (#51).

### Changed
- **A professional Complete Tax Report.** Redesigned from the ground up,
  with the same figures:
  - a cover with the year's key figures (net capital gain, income, bitcoin
    held and its value at year end), how the report was made (FIFO per
    account, tax timezone, prices, when it was generated) and contents
    with page numbers;
  - a one-page summary: gains and losses by term, each Form 8949 box with
    its Schedule D line and totals (the same as the IRS forms BitcoinTX
    fills), income by source, and holdings on January 1 and December 31;
  - the detail, each table with a totals row and its heading repeated on
    every page it runs onto: every disposal (with its kind, Form 8949 box
    and term, in the IRS column order: proceeds, cost basis, gain), income,
    gifts, donations and lost coins, and the holdings at year end by
    account and lot by lot (they listed every lot as a "balance" before,
    with the same price note on each row);
  - losses in parentheses as on the IRS forms, a running header and "Page X
    of Y" on every page, and the notes at the end.
  Fixed on the way: the number of disposals sat in the Short Term column
  though it counted both; two column headings overlapped; and a table that
  ran onto another page lost its heading there.
- **The Transaction History PDF fits the page.** Its table was wider than
  the page (columns were cut off). It is now landscape, in the same look,
  with dates in the tax timezone, each type with its source or purpose
  ("Withdrawal (Spent)"), amounts and fees with their currency, and page
  numbers. Reports now offers it: with Transaction History selected,
  Format is CSV spreadsheet (as before) or PDF; before, the PDF could only
  be had through the API. The CSV is unchanged.

### Fixed
- **The Complete Tax Report no longer has an "Expenses" section.** It
  listed withdrawals with the purpose "Expenses", which the app's forms
  never offered (a BTC withdrawal is Spent, Gift, Donation or Lost), so it
  almost always said "No transactions". Rows that reached it: a BTC
  "Expenses" row from an old ledger, and a cash withdrawal sent by API or
  CSV with that purpose, which it showed as BTC.
  Spending is in the capital gains section, as before, and so is a BTC
  "Expenses" row an old ledger still has. No figure changes (#58).
- **The Mac app no longer carries the test files.** It bundled all of
  `backend/`, its tests and test ledgers included (harmless, never used);
  now it leaves out `backend/tests/` and what a dev run leaves in the
  build's checkout (a database, its backups, the session key, the setup
  code). Docker and StartOS never had the tests; their build now also
  ignores those dev files. Release builds start from a clean checkout and
  were never affected.
- **On a phone, the transaction panel can be closed.** Up to 460 px wide the
  Add or Edit Transaction panel covers the whole page, so there was nothing
  outside it to tap and no Escape key: Save was the only button, and the
  phone's Back button left the page and dropped what was typed without
  asking. A close button (✕) in the panel's header now closes it, on every
  screen, like a click outside: at once when nothing was changed, else after
  "Discard changes?". Found by the full test run of 1.2.4.

### StartOS package
- **Package 1.2.5:0.** Release notes in five languages; 1.2.4:1's
  one-time cleanup of the retired Show Credentials task moved to its own
  version file, so installs from before it still get it.
- **Start9's review, taken back (package 1.2.4:1, on Community Beta).**
  Start9 reviewed the package on their fork
  (Start9-Community/BTCTX-StartOS#1) and merged it on 2026-10-05; `startos/`
  now has it as they wrote it. One **Set Login Credentials** action
  replaces Show Credentials and Reset Login Credentials: it makes a new
  random password and shows it once, at install (a critical task; install
  no longer creates the database) and whenever the owner has lost it, only
  while the service is stopped. A login StartOS already made stays; an
  older install whose password was set in the app gets the critical task,
  and running it replaces that login. The update clears any leftover Show
  Credentials task. The package repository is now Start9's fork; their
  workflows and template updates came too. Our docs, comments, the agent
  release tests and the box test name the new action (#29).

### Development
- **The Start9 check survives squash merges.** `scripts/start9-pull.sh
  --apply` records the Start9 commit it took in `scripts/start9-taken`
  (committed with the take-back); the release's check then counts only
  what Start9 changed since. Before, it looked for the take-back commit in
  the history, which GitHub's squash merge of #48 removed: the 1.2.5
  release would have stopped at its first step. Set to Start9's 8c030d8,
  the review #48 took.
- **How changes flow, on one page.** `docs/HOW-CHANGES-FLOW.md` maps the
  whole path in plain steps: an everyday change, a release, sending it to
  Start9, taking Start9's own changes back, and keeping this computer and
  GitHub the same. Written for the owner and every AI session; `AGENTS.md`
  points to it.
- **An issue for each yearly IRS forms step.** The weekly IRS forms watch
  now runs all year and opens an issue (label `claude`) when the IRS
  publishes the next year's draft forms or revises them (ship them as the
  preview) and when it publishes the final forms (add them, in a release).
  Before, it only ran November to March and only failed, with an email, for
  the final forms (`scripts/irs_new_year.py --due`).
- **One command says whether everything is on GitHub.** `make sync-check`
  (`scripts/sync-check.sh`) fetches, brings local `main` and `develop` down
  when they're only behind, and lists anything that exists only on this
  computer: work not committed in any working folder, branches with
  commits GitHub doesn't have (a merged pull request counts as on GitHub),
  stashes. It ends with IN SYNC or NOT IN SYNC. `--tidy` also deletes the
  local branches already on GitHub. Every session runs it at its start and
  end, and ends its last message to the owner with "Git: in sync" or what
  is only here (owner's request).
- **The mirror sync builds on Start9's fork.**
  `scripts/sync-startos-mirror.sh` first fast-forwards the mirror's `main`
  to Start9's fork (or, if the two have diverged, records it as merged,
  keeping `startos/`), so each pull request to Start9 shows only our
  changes, not theirs undone. It runs `start9-pull.sh --check` first, also
  for a docs-only sync by hand, and stops if `startos/` lacks theirs.
  The check (also the release's first step) now accepts their changes
  taken in a commit since our last sync and edited afterwards; before, our
  edits to two lines Start9 had rewritten would have stopped the next
  release (the release's mirror step now fetches the whole history for
  it). It also passes when Start9's branch is already in the mirror's
  history: what differs then is ours, waiting for them to merge. And it
  now stops, instead of warning, when Start9 changed their fork while a
  pull request of ours is open there: theirs can't be told from ours then,
  and a sync could record their commits without their content.
  `startos/`'s `UPDATING.md`, `TODO.md` and `AGENTS.md` now say that `develop` takes pull requests and that to-dos
  are issues (#29).
- **What to do when a dependency update breaks something.**
  `docs/MAINTENANCE.md` now says that an update to the app's or the Mac
  app's Python packages or to the GitHub Actions merges only after the Mac
  build has passed (it isn't
  one of the required checks), that updates which could move a tax figure
  get the before-and-after comparison, how a breaking update is fixed or
  skipped (an `ignore` rule, a "Deferred upgrades" row and an issue), and
  how a skipped one is taken later.
- **Comments tidied where the linters don't look.** The `Dockerfile`,
  `Makefile` and `scripts/backup-db.sh` lost their banners and the comments
  that only restated the next line; the ones left say why. No change in
  behaviour.
- **Everything we name to build with is pinned exactly.** The Docker base
  images are pinned by digest and the GitHub Actions by commit (a tag can be
  moved later; the publishing step for the AI connector followed a branch),
  the Mac app's build tools and `anyio` by version; Dependabot now also
  proposes updates for `desktop/` and the base images (the Dockerfile lost
  its indentation, which hid its `FROM` lines from Dependabot). The packages
  those pull in themselves aren't locked yet (#37). The AI connector
  keeps version ranges, now capped below the next major version of `httpx`
  and `pydantic`. The rules are in `docs/MAINTENANCE.md`, "Updating a
  dependency".
- **Every Python package that ships is locked, with its hash.** Each shipped
  requirements file is now a `requirements.in` (what we name, pinned) with a
  lock beside it, `requirements.txt`, made by `make lock` (`uv pip
  compile`): every package, the indirect ones too (32 of them were pinned
  nowhere and resolved at build time), at a fixed version with its hashes,
  for Linux (both chip types), macOS and Python 3.10 and up. The Docker
  image installs its lock with `--require-hashes` and ready-built wheels
  only; the Mac app installs the backend's and `desktop/`'s locks the same
  way, and builds its one source-only package with the locked setuptools;
  the connector's PyPI build uses a lock of `build` and setuptools
  (`.github/release-tools/`) and no longer fetches them unpinned. The Mac
  build no longer upgrades `pip` or installs `wheel`, and CI's container
  smoke test installs the lock rather than an unpinned `httpx`. Dependabot
  keeps the locks current (`uv` entries); the dependency audit now covers
  all three locks, on Linux and macOS. `test_pinning.py` checks that each
  lock has every hash and matches its pins, and that whatever ships installs
  with `--require-hashes`. The indirect packages are refreshed once a month
  (`make lock LOCK_ARGS=--upgrade`), when the first Monday's weekly check
  reports newer versions (#37).
- **The pre-push check can't break the repository any more.** Run from a
  worktree, git hands the hook `GIT_DIR`; the tests that build throwaway
  repositories inherited it, and their `git init` set `core.bare = true` in
  the shared `.git/config`, so git refused to work in every checkout until
  it was set back. The hook now unsets those variables first (git's advice
  for hooks), and a test keeps that line there.
- **The weekly StartOS check also watches start-cli.** Besides a newer
  `@start9labs/start-sdk` on npm, `startos-sdk-check.yml` opens an issue
  when Start9 releases a newer start-cli (the tool that packs `btctx.s9pk`)
  than CI's `START_CLI_VERSION`. Each issue links the release notes and
  says to look at Start9's fork first, since Start9 may send the bump
  there themselves.
- **One rules file and one to-do list for every AI.** The rules moved
  from `CLAUDE.md` to `AGENTS.md`, the file other AI tools read too
  (`CLAUDE.md` now only points to it, which a test checks); it now says who
  does what (the owner decides, Claude Code develops, Grok brainstorms) and where each kind of information lives. To-dos are GitHub
  issues, labelled `claude`, `owner`, `ask-grok` or `start9` (the workflows
  label theirs), instead of `docs/temp/TODO.md`: its open items went to
  #29–#32 (checking that `start9-pull.sh --fork` finds Start9's fork was
  done), the roadmap's two specific to-dos to #38 and #39, and
  `test_todo_lists.py` keeps a to-do file from coming back.
- **Every change arrives by reviewed pull request.** `develop` takes changes
  only by pull request (GitHub rulesets now protect `main` and `develop`),
  from `.github/pull_request_template.md`. Each one is reviewed by a fresh
  Claude agent before it merges, as thoroughly as the change needs. Claude
  merges once the required checks pass and nothing is open, except a change
  in tax figures or what the app computes, the database, the StartOS
  package or anything that reaches Start9, and releases, which wait for the
  owner. The pre-push hook now fast-forwards `main` only to GitHub's
  `develop`, and `scripts/start9-pull.sh --apply` runs on a branch for a
  pull request.
- **Sessions start and end at one pinned issue.** #41, "Where we are", says
  what's in flight and what's next; each session reads it first and rewrites
  it last (`AGENTS.md`, "Starting a session"). Reviewed pull requests now
  merge through GitHub's auto-merge once the required checks pass, and a
  branch behind `develop` is updated by merging `develop` in, not rebasing.
- **`AGENTS.md` says what's at stake and how Start9 works.** Two new
  sections: the owner's real tax records and ledger, other people's
  installs, privacy; and Start9's fork, Community Beta, promotion, and their
  own changes coming back.

## [v1.2.4] - 2026-09-30 - Fixes from testing 1.2.3: zero fees kept, phone header, Escape; the unused lock removed

Small fixes found by the 1.2.3 test walk on StartOS, with no change to any
tax figure: checked on every test ledger and, before release, on the owner's
own ledger upgraded from 1.2.3 (every row, form, gain and CSV row the same).
The database moves to schema 0005 once (a copy is kept in `backups/` first).

### Removed
- **The unused transaction lock.** Nothing in the app could lock a row (no
  button, API field or import set it), yet a locked row would have refused
  edits and deletes with "not found" while recalculation still changed its
  figures. It is gone rather than finished: database schema 0005 drops the
  column (the usual copy of the database goes to `backups/` first), API
  answers no longer carry `is_locked`, and editing or deleting a missing
  transaction says "Transaction not found." No figure changes (checked on
  every test ledger). As with any schema change, an older BitcoinTX then
  refuses the database; the backup copy is the way back.

### Fixed
- **Escape closes the transaction panel**, like a click outside it: at
  once when nothing was changed, else after "Discard changes?". With that
  question showing, Escape answers Go back and keeps your changes. The panel
  learns of a change at once, so Escape or a click outside right after one
  still asks. Found by the 1.2.3 VM walk.
- **On a phone, every tab in the header fits on screen.** At 375 px the
  header needed 407 px, so Logout was cut off at the edge ("Logo") and only
  reachable by scrolling the header sideways. Up to 480 px wide the tabs are
  now a little smaller and spread across the width; they fit from 340 px
  (narrower screens still scroll). Found by the 1.2.3 VM walk.
- **A CSV export re-imported gives back its zero fees.** The import dropped
  a fee of 0, so rows saved with "0 USD" or "0 BTC" came back with no fee
  and no fee currency. Every figure was already the same (a zero fee and no
  fee count alike), but a CSV backup now restores exactly what was saved. A
  blank fee in a file still means no fee. Found by the 1.2.3 VM walk.

### Development
- **CI and the release build pin Node 22.23.2 for the StartOS package.**
  GitHub's runners moved to Node 22.23.3, whose headers fail to build
  `diskusage`, a native module that Start9's `mempool-startos` dependency
  pulls in; the release's package build would have failed the same way.
- **The web app's error-message helper moved** from `hooks/useApiCall.ts`
  (it held no hooks) into `utils/apiError.ts`, beside the other one; its
  tests moved unchanged.
- **The stress tests fail on a refused save** instead of carrying on
  without the row, except where a random ledger may ask for more than is on
  hand, and their random amounts and dates are the same on every run. The
  backdating test now checks that its ten backdates were saved.
- **The CSV export prints numbers from their exact value**, not through a
  float. Nothing an export writes changes (checked on every test ledger):
  a value is already rounded to its column's decimals when it is read, so
  the float could only lose digits past about 16, far beyond real amounts.
- **A release's title names its StartOS package version**, for example
  "v1.2.3 · StartOS package 1.2.3:0", and so does its StartOS download line:
  the number StartOS and the mirror's releases show (the app version plus
  the package's own revision). The tag stays `vX.Y.Z`, which the Mac app,
  the Docker image and the AI connector share. v1.2.3's release was
  retitled to match.

## [v1.2.3] - 2026-09-29 - Code cleanup: the same app, easier to maintain

A maintenance release with no new features. The code behind the app was
reorganized (long functions divided into named steps, the web app's big
components split, filler comments and unused code removed) with one rule:
nothing it produces may change. Every figure, database row, Form 8949 field,
report PDF (byte for byte), CSV, import preview, API answer, AI tool output
and error message was compared with 1.2.2-1's on the golden ledger, the
seed ledger, 40 random ledgers in three timezones and about 2,200 bad
inputs; every page and form was recorded before and after. The only
differences are the two fixes below. Recalculation is about 7% faster.

### Fixed
- **A CSV row with an unknown `fee_usd_typed` value** (anything but yes, no
  or blank) crashed the import preview with a server error; it is now a row
  error, "Must be yes, no or blank." Found by the new equivalence check's
  bad inputs.
- **Ledger Review's fee check no longer hides errors.** Looking for
  transfers whose fee value is off the day's price, it passed over a
  transfer on *any* error while getting that day's price, so a broken
  database or a bug looked like "nothing to fix". It now passes over only
  a day with no price; anything else is reported as an error.

### Development
- **Code cleanup, no change in behaviour**:
  the standards are written down in `docs/CODE_STYLE.md`, and `CLAUDE.md`
  points to them. `scripts/equivalence_check.py` compares everything the
  app produces (database rows, API answers, Form 8949 field values, report
  PDFs byte for byte, CSV files, import previews, MCP tool outputs, the
  error message of each of about 2,200 bad inputs) with v1.2.2-1's, and
  times recalculation (`docs/TESTING.md`).
- **Every Transaction column is in the CSV export or on a list saying why
  not** (`test_csv_export_columns.py`), so a new column can't be left out of
  the export unnoticed, as three were before 1.2.1.
- **Comments and docstrings** say what each module is for and why the code
  does what it does: no file-path headers, banner dividers, history notes
  or narration. The Transaction model's column descriptions no longer call
  its main fields "legacy". Two pieces of dead code went: `main.py`'s empty
  `__main__` block and an unused `services.user.delete_user`.
- **Modern type hints** (`list[str]`, `dict`, `X | None`) in the app code,
  and ruff's `UP` rules keep it that way (tests and migrations excepted).
- **The complete tax report** is built one section at a time
  (`complete_tax_report.py`, from one 510-line function), with the paragraph
  styles and grid tables it shares with the transaction history in
  `reports/pdf_layout.py`. Its PDFs are byte-identical.
- **The transaction history and the Form 8949 field mapping** are divided
  the same way: the history's columns and widths are one table, its PDF
  uses the shared layout; a Form 8949 page's checkbox, row fields and line 2
  totals are named steps. Same PDFs, CSVs and field values.
- **The CSV import guide's script** keeps its tables as data and builds
  one section per method (`backend/scripts/generate_csv_instructions_pdf.py`,
  from one 395-line function); the PDF it writes is byte-identical, and the
  committed one is unchanged.
- **The CSV import** checks a row one field at a time (`csv_import.py`:
  `_validate_row` was 276 lines), with the account rules per type as a
  table and each type's own rules in their own function; the template's
  sample rows are data. Two branches that could never run are gone.
  Checked on 40,728 generated rows: the same errors, warnings, previews and
  transactions.
- **The River import** reads each kind of River row in its own step, finds
  duplicates in an exact and a rough pass, and the import endpoint checks,
  stubs and saves rows in named steps. Same proposals, warnings, matches and
  imports (3,000 random files and 3,000 random ledgers compared).
- **The dashboard's gains** (`get_gains_and_losses`, 179 lines) add up
  realized gains, proceeds, income by source, fees and this year's gain in
  one step each. Same figures on every ledger compared, including ones with
  sales this year.
- **Ledger Review, the CSV export, the AI entry dry run, the public price
  download, the IRS form filler, the adoption of a pre-migration database
  and the AI connector's request and `update_transaction`** are divided
  into named steps too; the connector's tools, their schemas and outputs
  are unchanged.
- **The ledger engine** (`transaction.py`) reads as its steps: create and
  edit (check, complete, insert or apply, recalculate), the ledger lines per
  kind of transaction, FIFO disposal and transfer lot moves, the input checks
  in their fixed order and each type's account rules as a table. Two unused
  functions are gone. Same lines, lots, disposals, figures and messages on
  every ledger and bad input compared; recalculation no slower.
- **The transaction form** (`TransactionForm.tsx`, 1,049 lines) keeps the
  form's state, saving and deleting; each transaction type's fields, the
  shared account and fee fields, the autofill and the save request are their
  own files in `components/transactionForm/`. Every form variant renders the
  same labels, roles and HTML (`e2e/ui-snapshot.e2e.ts`).
- **The Settings page** (799 lines) is its sections: Account, Data
  Management (with the CSV import's preview) and Backup & Restore are their
  own components, next to the ones it already had; the page keeps the one
  action at a time and the message line they share. Same page, labels and
  messages.
- **The River import panel** (486 lines) keeps the upload and the import;
  the preview, one row and its editable cells are their own components, and
  the row logic (the accounts a new type implies, the import request) is in
  `utils/riverImport.ts` with a unit test. The two import previews share
  one date format and one "server's reason, else…" message helper. Same
  preview after every edit a row allows (recorded before and after).
- **The Dashboard** (470 lines) fetches its figures and lays out four
  cards, each its own component; the account totals and the gain/loss
  colour are in `utils/dashboard.ts` with a unit test. Same cards, figures
  and HTML.
- **The rest of the frontend over the limit**: the transaction form's
  mapping to and from the API is one small step per transaction type (the
  same results on 40,000 random forms and transactions, compared), the
  Transactions page's sorting, paging and day groups are in
  `utils/transactionList.ts`, Privacy & network's "anything changed?" is
  one tested function, and the error message for a failed request is read
  in two steps (the same message for 20,000 random failures).
- **Frontend comments and unused code**, as in the backend: no file-path
  headers, banner dividers, history notes ("NEW", "ADDED", "legacy") or
  comments that repeat the code. Gone because nothing used them: three hook
  files and four API hooks (`src/hooks/` keeps the error message),
  `formatTimestamp`, two types, and five dashboard fields the server has
  never sent. The built app is byte-identical but for those five fields.
- **Lint limits each function's size**, so the long functions can't grow
  back: Python (ruff: complexity 10, 12 branches, 50 statements, 6 returns;
  tests and migrations exempt) and the frontend (ESLint: complexity 15 per
  function, 400 lines per file; tests exempt).
- **The StartOS mirror stays current between releases**: a docs-only change
  to `startos/` goes to DigiMonk73/BTCTX-StartOS right away (`CLAUDE.md`),
  since Start9's build there ignores those files. Anything else waits for a
  release.
- Roadmap: the AI connector will follow the app's version, chosen over
  `uvx btctx-mcp@latest`.

## [v1.2.2-1] - 2026-09-29 - StartOS package: BitcoinTX's own logo as its icon

Package-only update; BitcoinTX itself is unchanged.

### StartOS package
- **The icon is BitcoinTX's own logo**, the gold coin the app, the landing
  page and the screenshots show, as a 39 KB WebP (`startos/icon.webp`, under
  Start9's 40 KiB limit). It replaces the simplified vector copy drawn for
  the size limit (decision of 2026-09-23); Start9's guide asks for the real
  asset rather than a redrawn one. The release notes still carry 1.2.2's
  for anyone updating from 1.2.1 or earlier.

### Documentation
- **Screenshots of 1.2.2** in the README and on the landing page (same demo
  ledger): the whole taller calculator, 2025 picked in Reports, and the
  AI setup prompt with today's `uvx btctx-mcp==1.2.2` instead of 1.1.0's.

### Development
- **To-dos are checkboxes.** Specific to-dos live in `docs/temp/TODO.md`,
  the StartOS package's in `startos/TODO.md` (Start9's standard file, so it
  reaches the repository Start9 forks), and what's next in `docs/ROADMAP.md`.
  Every item is `- [ ]`, ticked when done and cleared at the release that
  ships it; a finished plan is deleted and its roadmap box ticked.
  `test_todo_lists.py` checks the format. The 1.2.2 privacy audit is now
  `docs/PRIVACY_AUDIT.md`; the finished stabilization plan is gone.
- **The StartOS package always keeps Start9's packaging rules**, checked by
  `test_startos_conformance.py`: the standard layout, the README's fixed
  headings (each opening with a sentence) and no version numbers,
  documentation links Start9's indexer can parse, and `TODO.md` as Start9's
  worklist (`# TODO`, an item removed when done rather than ticked). Fixed
  on the way: the Quick Reference section now opens with a sentence, and
  `instructions.md` links whole files without `#anchors` and drops the
  package's own README, which isn't upstream documentation.
- **After Start9 forks the package, releases reach them only by pull
  request, and the release makes sure it isn't forgotten.** The release
  workflow's first job runs `scripts/start9-pull.sh --check` and stops before
  publishing anything if Start9 changed their fork and `startos/` doesn't
  have it yet (the mirror sync would undo it). After the mirror push it
  opens an issue, "Send vX.Y.Z to Start9", with a link that opens the pull
  request ready to create, unless one of ours is still open there (it then
  carries the new release). The script finds the fork itself (`--fork`),
  since Start9 renames forks and may use another branch; tests cover it
  with local repositories.

## [v1.2.2] - 2026-09-29 - Stability: tax-figure fixes from a bug hunt, privacy audit, no new features

Stabilization after 1.2.1: no new features. Found by testing the published
1.2.1 on a StartOS VM, a bug hunt of the tax engine, the imports and the AI
connector, and a privacy audit (2026-09-29). Each fix has a test that
failed before it.

### Changed
- **The sidebar calculator is a little taller** (owner's request): its keys
  are slightly longer, so it ends level with the Dashboard's Realized
  Gains/Losses card. The Sats Converter's price area is now the same height
  in Manual, Auto and Date, so the calculator no longer moves when you
  switch; in Date mode the day's price sits beside "Select date".

### Fixes to tax figures
- **Changing a transaction's type no longer keeps the old type's fields.**
  A Gift changed into a Sell stayed a "gift" and was missing from Form 8949
  and Schedule D; a withdrawal changed into an Income deposit reported the
  old lots' cost basis as the income instead of that day's value. (Only the
  AI connector or the API can change a type; the form locks it.)
- **A fee entered without its currency now counts.** Adding a fee on its
  own (e.g. by the AI connector) left a Sell's proceeds and a Buy's cost
  basis without it, and took a withdrawal's BTC fee from the balance with
  no disposal or value. The fee now gets its type's currency (USD for Buy
  and Sell, else the account's) and is saved with it; entries already saved
  that way are fixed by the next recalculation (which needs that day's
  price, or the fee's value typed in, for a BTC fee).
- **Pay the AI adds as an Income deposit into Bank or Exchange USD is no
  longer valued at the BTC price** ($5,000 became $250 million of income);
  likewise a Spent or Gift withdrawal from a USD account. Only BTC accounts
  are valued at the day's BTC price.
- **Dates given to the AI connector are read as when adding.** Changing a
  transaction's date read it as UTC, so in the US a sale moved to Jan 1
  landed on Dec 31, in the previous tax year; a date alone is now midday in
  your tax timezone. A time ending in " UTC" is read as UTC (it was read in
  the tax timezone), and finding transactions by date uses days in your tax
  timezone.
- **A second Buy of the same amount at another price can be saved through
  the AI.** A Buy of the same BTC amount within 48 hours was taken for a
  duplicate even at a different price, skipped, and could never be saved.
  It's now a possible duplicate the AI asks you about; only the very same
  buy (same amount and price) is skipped.
- **Export CSV then Import CSV keeps the order of same-time entries.** The
  import put them in a fixed type order (moves before sales), which could
  change which coins a sale used and its gain; rows at the same time now go
  in the file's order (the export's is the ledger's). A hand-made file that
  lists a sale before the same-time buy paying for it is refused, and the
  message says to list the buy first.
- **Form 8949 line 2 "Totals" is filled.** Each page now shows the totals of
  its own rows in (d), (e) and (h), which add up to the Schedule D line; it
  was left blank on the locked PDF, so it couldn't be typed in either.
- **A sale drawn from several lots no longer loses cents.** Each lot's share
  of the proceeds was rounded on its own ($100.00 over three lots showed as
  $99.99 on Form 8949); the last share now takes the remainder.
- **A withdrawal of 1 satoshi more than you hold is refused**, like a
  transfer or sale. It was accepted and left the balance at -1 sat.
- **A time with fractions of a second no longer lands in the wrong year.**
  A sale entered (through the API or the AI connector) half a second after
  midnight on Jan 1 counted in the year before; times are now saved in
  whole seconds.
- **A Spent withdrawal changed into a Gift, Donation or Lost no longer keeps
  its proceeds**, which the complete tax report printed in its Gifts
  section. (The network fee is still its own taxable disposal.)

### Other fixes
- **The Sats Converter no longer shows "BTC Price: $0.00" without a price.**
  With prices off it says "Prices off", after an error or for a day with no
  stored price "No price", and the USD field empties instead of keeping an
  old figure (BTC and sats still convert).
- **My Mempool not answering is an error, not "Prices off".** With your
  Mempool chosen but missing or not answering (and the fallback off), the
  Dashboard said "Prices off"; it now says "Error", and hovering it shows
  why (e.g. install and start Mempool).
- **Clearer messages when no price is stored.** A transfer's missing fee
  value names the form's **Fee value (USD)** field (and `fee_usd` for
  imports), and a new Spent withdrawal without proceeds is no longer told
  to "edit that transaction".
- **The complete tax report says where its prices come from.** It claimed
  "the average market value at the time of disposal"; it now says values
  are the ones entered, a blank one comes from that day's stored daily
  price, and dates are in the tax timezone (named).
- **An import no longer freezes the whole app while it works.** A CSV,
  River or AI-assistant import (or its preview) held up every other
  request, StartOS's health check included, for as long as it ran (10
  seconds in one test); that work now runs beside them.
- **The CSV import reads Excel's "CSV UTF-8" files.** Their invisible
  byte-order mark made the import say "Missing required columns: date".
- **A River file row with one comma too many is that row's error.** A
  trailing comma or an amount written 1,000.00 made the River import fail
  with a server error.
- **A River Sell whose Fee Currency is blank is no longer a fee short.** A
  blank fee currency on a River Buy or Sell counts as USD, as River charges
  it, so the sale lands at River's Received Amount.
- **When BitcoinTX's address redirects** (e.g. `http://` to `https://`), the
  AI connector says so and which address to set in `BTCTX_URL`, instead of
  an unclear error or a blank price. It still never follows a redirect, so
  the AI key only goes to that address.
- **Keyboard focus shows in the Mac app on older macOS.** On Safari before
  15.4 (macOS 10.15 to 12.2) no focus ring was drawn at all; the browser's
  own ring now stays there, and newer versions keep the gold one.

### Privacy (`docs/PRIVACY_AUDIT.md`)
- The AI connector no longer writes request addresses to the AI app's log
  files; past-price lookups named your transaction dates there.
- An `.onion` mempool address needs the proxy: it's refused without one (it
  was looked up through the normal DNS, which then saw the name).
- An encrypted backup no longer passes through a plain copy in the system's
  temp folder, and a restore's decrypted file is owner-only from the moment
  it's written.
- Making reports no longer logs how many transactions, disposals and lots
  each year has (now only at the DEBUG log level).
- The Docker instructions start BitcoinTX reachable from your computer
  only (`-p 127.0.0.1:8080:80`), with a note to put it behind HTTPS for
  other devices; the old command sent your password and ledger unencrypted
  across your network. The AI connector warns once in its log when it talks
  to another machine over plain `http://` (owner decision).
- The encrypted backup's password is typed in a hidden field, twice: it
  was a plain pop-up that showed it and asked once, so a typo made a backup
  no one could open (owner decision).
- Deleted transactions are erased from the database file (SQLite's secure
  delete), instead of staying readable in it and its copies until it was
  compacted.
- Settings > Backup & Restore says BitcoinTX keeps a few unencrypted safety
  copies of its database in its data folder.
- Responses no longer name the web server ("server: uvicorn"), and the
  Docker image's data folder is owner-only (it was writable by everyone).
- The READMEs say that `uvx` downloads the AI connector from PyPI once,
  which sees your IP address and the version.
- Settings (and StartOS's Price Source & Privacy action and instructions)
  name every public site BitcoinTX may contact (mempool.space and Coinbase
  were missing) and say the sites see your IP address and when BitcoinTX is
  open, never your transaction dates (owner decision).
- Fewer requests to public price sites: the live price asks Kraken first
  and CoinGecko only if Kraken fails (CoinGecko refuses VPN and Tor users,
  so each refresh used to contact both), and the block height is kept for a
  minute like the price instead of being asked on every Dashboard visit
  (owner decision).
- Restoring a backup in the app keeps the price settings in use, as it
  keeps your login and AI key: a backup from before a switch to Tor or Off
  brought back direct lookups of the public sites (owner decision).

## [v1.2.1] - 2026-09-28 - Fixes from testing 1.2.0: prices stay off until you choose, restore keeps your login, reports say why

### Fixes
- **Adding transactions before choosing a price source no longer turns
  public price sites on.** Since 1.1.0, an install with transactions but no
  price choice yet was taken for one from before 1.1.0 (when public sites
  were on by default), so its next restart, e.g. an update, switched it to
  **Public price sites** and asked them for prices, although you never
  chose that. Now only an install that stored past prices before 1.1.0
  keeps public sites; any other stays unasked until you choose. If you
  added entries before answering the price question and BitcoinTX has
  restarted since, check **Settings → Privacy & Network** (on StartOS, the
  Price Source & Privacy action decides instead). Found testing the 1.2.0
  package on a StartOS VM.
- **The complete tax report works with price lookups off.** It looked up
  the Jan 1 BTC price even when nothing was held then, and a missing price
  failed the whole report; a missing Dec 31 price valued the holdings at
  $0. Holdings with no price for that day now read "not priced", and the
  rest of the report is unchanged.
- **The complete tax report's Beginning of Year Holdings were wrong**
  whenever BTC had moved or been sold in earlier years: lots were counted
  twice (in the checklist's ledger, 1.8797 BTC on Jan 1, 2024 instead of
  the 0.9898 held on Dec 31, 2023). They are now taken the same way as the
  year-end holdings, so Jan 1 always matches the previous Dec 31. Only this
  section of that report was affected: IRS forms and gains were right.
- **Export CSV now imports back to the same ledger.** The export had no
  column for a BTC fee's USD value, a gift's fair market value or the
  Broker form override (all added after the export was written), so a
  re-import priced every BTC fee again at that day's price, changing gains,
  lost Broker form choices and failed outright with price lookups off. The
  export, the import and the template now share one list of columns, with
  three new optional ones at the end: `fee_usd`, `fmv_usd` and
  `broker_reporting`. Older CSV files import as before. A CSV import a row
  can't be saved from (e.g. a BTC fee with no price to value it) now says
  why instead of answering with a server error. The CSV import guide
  describes the new columns and no longer calls a BTC deposit's basis
  optional.
- Deleting a transaction that later ones depend on (a buy whose BTC a later
  sell or transfer spends) is refused and changes nothing. Before, it showed
  an error but deleted the row anyway, and every later save then failed
  until the row was entered again. The message now says why: "Not deleted:
  later transactions depend on this one. …".
- Restoring a backup made before 0.9.2 with the wrong password now always
  says "Wrong password?". About 1 time in 256 it said the file wasn't a
  BitcoinTX backup instead (the live database was never touched either way).

- **The log is readable again.** Every health check (StartOS asks every 30
  seconds) logged two database lines, half of a running install's log. It
  now logs nothing.

- Loading the dashboard asked for the live price twice (the dashboard and
  the sidebar converter at the same moment). Requests at the same moment
  now share one.

- The dashboard's **BTC Cost Basis** is now labeled **Avg. Cost per BTC**:
  it always was the average cost of one bitcoin you hold, not your total
  cost.

- The login page shows **Create account** only on a fresh install that
  still has the default login. Once the account is set up, that page
  resets it (deleting every transaction, after asking for the current
  password), which the link didn't say; Settings still has Reset
  Username & Password.

- **A report that can't be made now says why.** Reports showed only "Failed
  to generate the report" and dropped the reason. They now show it, and
  when an old withdrawal's network fee (or a Spent withdrawal's proceeds)
  has no USD value and no price is available, the message names that
  transaction, e.g. "Withdrawal of 0.01 BTC on 2024-06-01: its network fee
  has no USD value (edit that transaction to enter it)".

- **Restoring a backup file in the app keeps your current login.** It
  brought back the backup's username and password, so a password changed
  since stopped working, and on StartOS Show Credentials showed one that
  no longer logged in. Like the AI key, the login in use now stays; the
  ledger and settings come from the backup. StartOS's own backups were
  never affected (they restore the login and the ledger together).

- With prices off, the dashboard's Unrealized Gains/Losses said
  "Loading..." forever; it now says "Prices off" (or "No price" when a
  lookup failed).

- When public price sites go through a proxy that's down (e.g. Tor
  stopped), the error says so and asks whether Tor is running, instead of
  only "No public site answered".

- Deleting a transaction asks "Are you sure?" once, not twice.

- **Export CSV** has a fourth new optional column, `fee_usd_typed`: whether
  a BTC fee's USD value was typed (yes) or that day's price (no). A
  re-import marked every fee value as typed, so editing such a
  transaction's date later kept the old value instead of pricing it
  again. Files without the column import as before.

- A missing file (the browser's `/favicon.ico`, an outdated script after an
  update) is a 404 instead of the app's page.

- **Sats Converter:** a price you type in Manual mode is no longer replaced
  by the starting price arriving late (on a slow server it could land after
  you had typed yours).

### Development
- `docs/AGENT-TESTS.md`: the release tests an AI agent runs on a StartOS VM
  before each release (install, actions, the update from the last release,
  backups, price sources, TLS, the MCP connector, the Mac app), against a
  14-transaction ledger whose every figure is known, with its known issues.
- Dependabot opens weekly pull requests against `develop`, grouped per
  directory (Python in `backend/`, `mcp_server/` and the dev tools, npm in
  `frontend/` and `startos/`, GitHub Actions). It leaves the StartOS SDK and its service
  packages, `@playwright/test` and the deferred upgrades alone
  (`docs/MAINTENANCE.md`, "Dependabot").
- First updates taken: uvicorn 0.54.0; vitest 5.0.2,
  eslint-plugin-react-refresh 0.5.7, globals 17 (frontend); prettier, ncc and
  the Node types (StartOS package build); GitHub Actions on their current
  majors (Node 24).
- The release job downloads its two artifacts by name, so a Docker build
  record can't get mixed in.
- `make preview` runs the checked-out code in a browser on a throwaway
  database with offline test prices; `make docker-smoke` builds the Docker
  image locally and runs CI's container checks on it (`docs/TESTING.md`).

## [v1.2.0] - 2026-09-28 - StartOS: your own Mempool and Tor in one action, translated package; connector on PyPI

### StartOS: your own Mempool and Tor, chosen in one action
- **New action: Price Source & Privacy.** Choose **My Mempool on this
  server**, **Public price sites** (optionally **over Tor**), **Off**, or
  **Choose in BitcoinTX**. A fresh install asks right after Show
  Credentials; updating installs get an optional reminder. What you choose
  there shows read-only in the app (Settings → Privacy & Network).
- **Your Mempool on the same server now just works.** BitcoinTX reaches it
  inside StartOS, so there's no address to copy, no https certificate that
  fails, and no LAN address that can change. This replaces the 1.1.0 advice
  to turn on the fallback for `.local`/https addresses (which, with the
  fallback off, meant no prices at all). Mempool and Tor are optional
  dependencies, only while you use them.
- **Tor for public sites:** with the Tor service installed, requests to
  public price sites go through it, so they never see your IP address. If
  Tor stops, those requests fail rather than go out directly.
- **Old default logins retired.** An install from before generated passwords
  that still had admin/password gets a generated password at this update,
  and StartOS asks you to copy it (Show Credentials) before starting.
- **Translated:** every action, task and message of the package in Spanish,
  German, Polish and French (the app itself stays English, US tax forms).
- The package follows Start9's conventions for the community registry: its
  mirror (DigiMonk73/BTCTX-StartOS) runs Start9's standard build and release
  workflows, and changes Start9 makes to their fork come back with
  `scripts/start9-pull.sh`.

### Price settings the server can set
- `BTCTX_PRICE_SOURCE`, `BTCTX_MEMPOOL_URL`, `BTCTX_MEMPOOL_FALLBACK` and
  `BTCTX_PROXY_URL` (Docker too): when set, they replace Settings →
  Privacy & Network, which shows them read-only; your stored settings come
  back once they're removed. An invalid value turns lookups off. See
  docs/STARTOS_COMPATIBILITY.md.
- The log now says where each download of past prices came from ("Price
  history from your mempool server: N days", "… from public site bitstamp"),
  so you can check no public site was asked.

### Fixes
- **Recalculate Ledger (StartOS action, `python -m backend.cli`) can look up
  a missing day's price.** The maintenance commands never read the price
  settings, so they behaved as if no source was chosen.

### AI connector on PyPI
- The connector is published to PyPI as
  [`btctx-mcp`](https://pypi.org/project/btctx-mcp/) with every release, by
  trusted publishing (no token is stored anywhere). The setup prompt,
  configurations, StartOS action and docs now install it with
  `uvx btctx-mcp==X.Y.Z`, still pinned to your BitcoinTX version; nothing
  needs `git` on your computer any more. Versions before 1.2.0 stay
  installable from GitHub (`uvx --from "git+…@vX.Y.Z#subdirectory=mcp_server" btctx-mcp`).

## [v1.1.0] - 2026-09-27 - Privacy: choose your price source, no dates in lookups; security tightening

### Privacy: you choose where prices come from, and no lookup reveals a date
- **Nothing is contacted until you choose.** A fresh install asks, right
  after the first login, where Bitcoin prices come from: **My mempool
  server**, **Public price sites**, or **Off** (Settings → Privacy &
  Network). Before that the dashboard says "Prices off". Installs from
  before 1.1.0 keep what they did.
- **Your own mempool server** now also gives past prices (its hourly record
  at 00:00 UTC), and it's used *only*: the public sites are asked when it
  can't answer only if you turn on **Fall back to public price sites**. A
  mempool server on your network is reached directly, not through the proxy
  (an .onion still is).
- **Past prices never reveal your dates.** Before, a missing day started a
  ~1,000-day download that began exactly 500 days before it, so the site
  could work out the date, and the Coinbase backup never covered the day,
  so BitcoinTX often asked for the day by name. Now the public sites send
  the whole daily history once, in the same requests for every install, and
  after that only "the latest days". The single-day lookups (CoinGecko,
  Kraken, CoinDesk) are gone. Days before 2011-08-18 (Bitstamp's first) have
  no public price: type the value in.
- The live price is asked at most once a minute however many tabs are open,
  and the sidebar converter doesn't ask while its tab is hidden.
- **Correction:** the 1.0.3 README, StartOS docs and website said that
  download kept lookups from pointing at your dates; it didn't, as above.
- **StartOS:** a mempool address starting with `https` (the `.local` ones)
  doesn't answer BitcoinTX yet (it can't check StartOS's own certificate);
  1.0.3 then quietly used the public sites. Turn on **Fall back to public
  price sites** with such an address for now; a direct connection inside
  StartOS comes next.

### Security
- **PDF reports can't be made to fetch anything.** Text stored in a
  transaction (for example from an imported file or an AI) could make the
  server contact any web address while drawing a report, skipping the
  proxy. Report text is now escaped and the PDF library may fetch nothing
  remote. A deposit's source must be one of the listed values. The IRS forms
  (filled by a different tool) are unchanged.
- **Docker/source first run: a setup code.** Until you set your own login,
  logging in with admin/password or claiming the account needs a one-time
  code from the log (`docker logs`) or `/data/setup-code.txt`, so nobody
  else on the network can claim it first. An older install that still uses
  admin/password: the login page asks for the code; log in, then change the
  password in Settings (your transactions are untouched).
- **Login protection:** repeated wrong passwords make everyone wait longer
  (1 s up to 5 min); new passwords need at least 12 characters (existing
  ones still work); changing the password needs the current one.
- **Requests from other sites are refused:** a page on another site (or
  another app on the same server) can't make your browser restore a backup
  or import a file. Cross-origin requests (CORS) are off unless configured.
- A restore refuses files over 1 GiB and unreasonable key-strength settings;
  two old example session keys from the project's history are refused; an
  empty session key file is replaced.
- CSV exports can't start a spreadsheet formula; Docker and StartOS keep no
  access log (request paths can hold dates), and transaction dates left the
  normal log.

### AI connector
- The setup texts pin the connector to your BitcoinTX version (`@vX.Y.Z`)
  instead of following `main`: your AI app runs exactly that code and
  fetches nothing new at each start. After an update, every tool reply says
  which version to set. (PyPI will come once publishing is set up.)

## [v1.0.3] - 2026-09-27 - Security: AI keys for every edition

### AI keys instead of passwords
- **The AI connector no longer uses your password.** On Docker and StartOS,
  **Settings → Connect an AI Assistant** now has the **Let AI assistants use
  BitcoinTX** switch (off by default) and **Create AI key**: a key shown
  once, which you paste into your AI app's settings. **New key** replaces
  it, **Revoke** deletes it. BitcoinTX stores only a hash of it. The Mac app
  keeps its automatic key file.
- **The key can do only what the AI tools need:** read the ledger, add,
  change or delete single entries, recalculate, and make a backup copy. It
  can't log in, change the username or password, restore or download a
  backup, export or import files, delete everything, apply Ledger Review
  fixes, open reports or change settings: those answer 403 (an allow-list,
  so anything added later is closed to the key too).
- **New AI tool `backup_ledger`:** a copy of the database in BitcoinTX's
  `backups` folder on your server before a big change (the newest 3 are
  kept, apart from the pre-upgrade copies; one a minute).
- **A restore keeps the current AI key and switch**, so an old backup can't
  bring back a key you revoked.
- **The connector refuses a password.** While `BTCTX_PASSWORD` is in its
  settings, every tool says how to switch to a key and sends nothing.
- **Breaking:** the undocumented `API_KEY` setting (`X-API-Key` header) is
  gone; use an AI key.
- The StartOS **Connect an AI Assistant** action no longer shows your login;
  its configuration has a `YOUR_BITCOINTX_AI_KEY` placeholder.

### AI connector updates itself
- The setup prompt, configs and docs install the connector from this repo's
  `main` branch, which now holds released code only: uvx checks it each time
  the AI app starts, so you never edit a version again. Pinning `@vX.Y.Z`
  still works.
- The connector has the app's version number, and when the two differ every
  tool reply starts with a line saying so and what to do (restart the AI
  app, or update BitcoinTX).

**If you use an AI assistant with BitcoinTX on Docker or StartOS:** your AI
app's settings file held your BitcoinTX password in plain text. After
upgrading: (1) in BitcoinTX, Settings → Connect an AI Assistant, turn on AI
access and create an AI key; (2) in your AI app's settings, replace
`BTCTX_PASSWORD` (and `BTCTX_USERNAME`) with `BTCTX_AI_KEY` set to that key,
and delete the password; (3) change your BitcoinTX password (Settings →
Reset Username & Password), or on StartOS run **Reset Login Credentials**,
because the old one sat in that file. Mac app users: nothing to do.

### Documentation
- The MCP README no longer says a local model means "nothing leaves your
  computer": what the AI reads stays there, but BitcoinTX still looks up
  prices unless Live data is off. It also says a preview can look up prices.
- **Correction:** v0.9.2 said past-day price requests "no longer name
  individual transaction dates", and the README said lookups "don't reveal
  your transaction dates". A missing day is filled by one download of about
  1,000 days, but if that download fails BitcoinTX asks CoinGecko, Kraken or
  CoinDesk for the single day, which names it. The README now says so; Live
  data off sends no request at all.
- The StartOS listing says BitcoinTX sends your ledger nowhere (instead of
  "your ledger stays on your server", which a cloud AI would contradict), in
  all five languages. The README and StartOS docs list every outside service
  (single-day fallback and block-height sources included).
- `docs/startos-research/btctx-requirements.md` (it described v0.8.0) moved to
  `docs/archive/`.

### Development
- Work now happens on `develop`; `main` holds released code only and moves
  by fast-forwarding to `develop` (`CLAUDE.md`, "Branches"). The pre-push
  hook refuses a push to `main` of anything not already on `develop`, and
  any delete, rewind or force-push of `main`; the release workflow refuses a
  release commit that isn't on `main`.

## [v1.0.2-1] - 2026-09-27 - StartOS package: translated listing, ready for the Start9 Community Registry

Package-only update; BitcoinTX itself is unchanged.

- The StartOS store listing and release notes are also in Spanish, German,
  Polish and French. The app stays in English and produces US (IRS) tax
  forms, which the listing says.
- The listing's website link points to the BitcoinTX site.
- The package README names no versions (Start9's rule): old upgrade paths
  are described by what changed.

## [v1.0.2] - 2026-09-26 - AI privacy: cloud or local model, Mac AI access off by default

### AI assistant privacy
- **Settings → Connect an AI Assistant** now opens with a warning: the AI's
  model reads what BitcoinTX hands it (transactions, balances, gains) and
  whatever you paste, and with a cloud AI (Claude, Grok…) that goes to the
  provider. It points to local-model apps (LM Studio, Goose with Ollama).
- The AI setup guide tells the AI to say this before it installs anything;
  the MCP README has a "Privacy: cloud or local model" section with LM Studio
  and Goose setup; the README and the StartOS instructions carry the warning.
- **Mac app: AI assistant access is now off by default**, including on
  installs upgraded from 0.9.2–1.0.1 that never touched the switch. If you
  use an AI with the Mac app, turn on **Settings → Connect an AI Assistant →
  Let AI assistants use BitcoinTX** once; until then the AI gets "AI
  assistant access is turned off". A line under the switch says what it
  allows. The docs say AI entry is optional, what the switch
  does, and that Docker/StartOS have no switch (the server logs in with the
  password).
- StartOS: the MCP API address, the Connect an AI Assistant action and the
  package description say the same, and name LM Studio. Text only; AI access
  on StartOS still works by username and password, as before.

### Documentation
- Install from the release downloads (macOS `.dmg`, `btctx.s9pk`, the
  `ghcr.io/digimonk73/btctx-mcp` image) instead of building; README features
  now include Ledger Review, stored price history and Privacy & Network; the
  upgrade steps use Ledger Review; price and outbound-request sources updated.
- The AI's ledger guide: income with no price available is refused (ask the
  user), a withdrawal's BTC fee is taxable even for Gift, Donation and Lost,
  River's Received is net of its fee, and when to use `review_ledger`.
- Mac app docs: the port-busy dialog replaces the old random-port fallback,
  the MCP server needs no settings, Gatekeeper steps for macOS 15.
- Developer docs: test counts and what `make check` covers, `make e2e`, the
  weekly workflows, new modules in `CLAUDE.md`, missing pinned packages,
  network-fee disposals on withdrawals in the IRS docs, frozen StartOS ids.
  The finished hardening/redesign and StartOS package plans moved to
  `docs/archive/`; the roadmap lists only open work.

### Releases
- The release workflow now also publishes each version's `btctx.s9pk` as a
  release on the StartOS mirror (DigiMonk73/BTCTX-StartOS), marked Latest,
  so the mirror's releases page stays current with no work in that repo
  (`scripts/mirror-startos-release.sh`).
- The mirror's only branch is now `main` (was `master`, plus four stale
  branches); the sync script and the mirror's CI follow it.

## [v1.0.1] - 2026-09-26 - Settings layout fix

### Fixes
- **Settings** (windows wider than 900 px): "Your own mempool server" and
  "Proxy for outside requests" squeezed their label and help into a column
  one word wide, with the field drawn on top; the Reset Username & Password
  fields (and, slightly, the Tax Timezone drop-down) sat above their row.
  Rows with text fields now show the label and help first and the fields
  below, up to 440 px wide; Tax Timezone keeps its drop-down on the right,
  level with its title. A click-through test checks every Settings row at
  desktop, tablet and phone widths. (Layout only: no figures change.)

## [v1.0.0] - 2026-09-26 - Look and feel: the polish, ready for everyday use

### Look and feel
Same app, same layout, calmer. No tax figure changes; no Recalculate Ledger
needed.
- **Numbers** have thousands separators and a real minus sign ($80,000.00,
  −$1,373.21); gains and losses carry a sign. Dashboard labels lose their
  trailing colons.
- **Transactions** is one list: an icon for each type, the type and account
  over a grey line with the time, source and fee, the gain written out
  ("Gain +$7,000.00 · +350.00% · Long-term"), and the BTC that moved on the
  right with its dollar value under it.
- **Reports**: Tax year is a drop-down, from your first transaction's year to
  this year. Years without IRS forms in this version can't be picked for the
  IRS Reports (the Complete Tax Report and Transaction History work for any
  year). New `GET /api/reports/years`.
- **One set of buttons** everywhere: a gold primary (one per section), grey
  secondary, quiet text, and red-text destructive. Settings no longer shows
  eight gold buttons side by side.
- **One input style** with a gold focus ring, labels above, no spinner arrows
  on number fields; file pickers, checkboxes and the Manual/Auto/Date switch
  match.
- **Nothing moves on hover.** Cards and buttons no longer lift, the report
  choices no longer grow, the transaction panel and toasts fade instead of
  sliding; Reduce Motion is honored.
- **Colors** checked for WCAG AA contrast: gains and losses in the list were
  4.0:1 and 2.7:1 and are now 8.4:1 and 6.4:1; field borders went from 1.75:1
  to 3.2:1.
- **Small windows**: at the Mac app's 800 × 600 the sidebar keeps the Sats
  Converter and a whole calculator (it used to cut the calculator in half);
  on a phone the sidebar hides and the pages stack.
- Icons from Lucide (ISC license, `lucide-react` 1.48.0), bundled with the
  app. The stylesheets went from about 3,900 lines to 1,300: shared tokens in
  `styles/theme.css`, shared buttons, inputs and cards in
  `styles/components.css`, and page files that only lay them out.

## [v0.9.2] - 2026-09-26 - Hardening: price history, withdrawal fees, Ledger review, privacy settings

### Before you upgrade: what changes existing figures
Upgrading changes no stored figure. Two fixes change figures **the next time
the ledger is recalculated**, which is Recalculate Ledger (Settings) *or any
add, edit or delete*:
- **Lost** withdrawals: their loss becomes $0 (like a gift).
- **Withdrawals with a BTC network fee**: the fee becomes its own small
  disposal at its value; a spend's proceeds no longer have the fee taken out.
Back up first, then open **Settings → Ledger review**: "Figures that
Recalculate Ledger would change" lists each affected transaction, old -> new,
without changing anything (`python -m backend.cli review` prints the same).
Transfer fees that look priced at the live price are fixed only when you
press **Fix these**. New entries only: a BTC deposit that isn't income needs
a basis (0 allowed); blank Spent proceeds are valued at the day's price.

### Added
- **Ledger review** (Settings, `GET /api/review`, `python -m backend.cli
  review`, and the AI assistant tool `review_ledger`): a read-only list of
  saved transactions worth a second look after this upgrade: Spent
  withdrawals saved with $0 proceeds, Lost withdrawals still carrying a loss,
  and BTC deposits (not income) with a $0 or blank cost basis. Each row says
  what looks odd and what would change. It changes nothing.
- **Local BTC price history.** Every past-day valuation (income, spends,
  gifts, network fees, the form's price Refresh, import autofill) reads one
  stored daily price. A missing day is filled by one download of about
  1,000 days around it (Bitstamp, then Coinbase, then Kraken), so requests no
  longer name individual transaction dates, and stored days work offline.
- **Fee value (USD)** on transfers and BTC withdrawals: a BTC network fee's
  dollar value is stored when you save it (fee x that day's price), or you can
  type it; a typed value is kept. Also `fee_usd` in the API and the AI tools.

### Fixes
- **The Mac app could come up on a random port after a quick relaunch**, and
  then AI assistants couldn't reach it (they look on 127.0.0.1:8765). The
  check that decided "port busy" failed while the previous run's connections
  were still closing (TIME_WAIT), and one failed check meant a random port for
  the whole session, silently. The app now binds 8765 itself the way the
  server does, retries for up to 10 seconds, and never switches ports on its
  own: if another program really holds the port, a dialog offers Retry, Use
  Another Port (this session, with a banner saying AI assistants can't
  connect) or Quit. Opening the app twice brings the running copy forward. The
  app now keeps a log at `~/Library/Logs/BitcoinTX/BitcoinTX.log`.
- **A "Spent" withdrawal entered with blank proceeds was saved at $0**, a
  loss of its whole cost basis, instead of its value at that day's BTC price
  (the rule for spends without proceeds, which imports already followed): the
  form sent 0 for a blank. Blank now means "not given" everywhere in the form:
  Spent proceeds, a gift's FMV and an income deposit's basis start blank and
  are filled from that day's price; a 0 you type stays 0. New entries only.
  Spends saved before with $0 can't be told apart from a real $0:
  the new Ledger review lists them (read-only) so you can check.
- **A BTC deposit that isn't income now needs its cost basis.** A MyBTC,
  Gift or N/A deposit left blank was saved with a $0 basis, so all of it
  became gain when sold (the CSV import only warned). The form, the API and
  the CSV, River and AI imports now ask for it; type 0 if it's really
  unknown. Income, Interest and Reward deposits are still valued at the day's
  price. New entries only; the Ledger review lists existing ones with a $0 or
  blank basis.
- **"Lost" withdrawals no longer count as a capital loss.** They recorded a
  loss of their cost basis, which the dashboard and the tax report's summary
  included, although Form 8949 leaves Lost out. They are now treated like a
  Gift: no gain, no loss. **Run Recalculate Ledger** (Settings) to update
  Lost withdrawals saved before; the Ledger review lists them.
- The transfer form showed the network fee's USD value at a made-up
  $30,000 price; the estimate is gone. The sats converter rounded BTC to 5
  decimals (1,000 sats); it now shows every satoshi.
- **Backup download and restore didn't check for a login.** Their router is
  meant to be login-only, but both endpoints skipped the check, so a client
  with the optional `API_KEY` could download or replace the whole database.
  Both now need a login.
- **Stricter input, clear messages.** The API, CSV and AI imports now refuse
  what the ledger would record wrongly: amounts of 0 or less, negative fees,
  basis or proceeds, more decimals than a satoshi (or a cent for USD accounts,
  exponent notation included), amounts too large to store (one used to be
  saved and then break the transaction list), unknown accounts, dates before
  3 January 2009 or in the future, a BTC withdrawal without a purpose (it got
  $0 proceeds: a loss of its whole basis on Form 8949), a Sell without
  proceeds, a fee in the wrong currency. A malformed optional number in an
  import is now an error instead of being dropped. An edit is checked as the
  whole transaction.
- **Form 8949 left out "Gift"/"Donation"/"Lost" only when capitalized exactly
  that way**; a "gift" entered through the API or an import printed on the
  form with its basis. Purposes are now stored in one spelling and matched in
  any case.
- **The complete tax report's capital-gains summary could disagree with Form
  8949 and Schedule D**: it totaled whole transactions by their first lot's
  holding period (a sale across short- and long-term lots went all to one
  side), left out transfer fees and counted the basis of gifts. It is now
  built from the same disposals as the forms. The forms themselves were right.
- **CSV import dates**: a date without a timezone was read as UTC, so
  "2024-01-01" landed on 31 December 2023 in a US tax timezone. Dates now
  follow the tax timezone (Settings), and a date alone means noon that day.
  A USD transfer's fee can be imported (it used to insist on BTC). The CSV
  instructions PDF said to include fees in a Buy's basis and gave the Sell
  proceeds after fees; both are before the fee (the fee column is applied
  once).
- **The Mac app refused today's price in the evening** in the Americas (it
  compared a UTC date with the local date): an income deposit left blank got
  an error and FMV Refresh failed.
- **Security**: deleting every transaction, the debug routes and the tax
  timezone setting are login-only (the optional `API_KEY` reached them).
  Changing the password or resetting the account now ends every other
  session (you'll be asked to log in once after upgrading). Empty usernames
  and passwords are refused. The API docs pages are off unless DEBUG is set.
- **A past value could be priced at today's price, or another day's.** When
  the day's price lookup failed, a transfer's network fee (on every
  recalculation) and a Spent withdrawal without proceeds used the live price,
  silently, so old gains could change and saving failed offline. And for
  dates more than about two years back, the lookup could return a price from
  about two years later (the Kraken fallback took the first day it returned).
  Now only the exact day's price is used; if there is none, BitcoinTX says so
  and asks for the value, never $0 or today's price. A fee's dollar value is
  stored with the transaction, so recalculating never prices it again.
  **Existing figures don't change on upgrade**: stored fee values are kept.
  The Ledger review lists transfer fees more than 5% off that day's price
  (probably priced live), with a **Fix these** button (or
  `python -m backend.cli review --fix-fee-prices`) that changes only those and
  recalculates, and income deposits more than 5% off, for you to check.
- **A withdrawal's network fee is now its own disposal**, as a transfer's
  always was (it's a small sale of BTC at its value). A spend's proceeds are
  what you received for the BTC spent; before, the fee was taken out of them
  (a $1,000 spend with a fee reported $990.10). A gift's, donation's or lost
  withdrawal's network fee now shows on Form 8949 too. **This changes
  existing figures once the ledger is recalculated** (Recalculate Ledger, or
  any add, edit or delete). Settings → Ledger review lists every transaction
  whose figures would change, old -> new, before you do.
- **Double-clicking Save added the transaction twice.** It now saves once.
- River import checked against a real River export: a Buy's Sent Amount is
  the subtotal with River's fee on top (basis = Sent + Fee), and timestamps
  are UTC, both as BitcoinTX reads them. Whether a send's Sent Amount
  includes the network fee is still being checked (v0.9.3).
- The River import warns when a row's Fee Currency isn't what BitcoinTX
  reads it as. The tax report shows a gift's value as "not given" instead of
  $0 when none was entered.

### Privacy
- **Fonts ship with the app.** The page loaded Inter and Outfit from Google
  Fonts, which told Google every time BitcoinTX opened. Nothing the page
  loads comes from anywhere but BitcoinTX now, and in a browser a
  Content-Security-Policy enforces it.
- Responses now carry no-referrer, nosniff and no-framing headers, and the
  session cookie is marked Secure when BitcoinTX is reached over HTTPS
  (StartOS).
- The database file and downloaded backups are readable by their owner only.
- **Backups are stronger**: 600,000 PBKDF2 iterations (was 100,000) and an
  integrity check, so a wrong password or a damaged file is reported clearly.
  Backups made by earlier versions still restore. A backup made by 0.9.2
  can't be restored by 0.9.1 or earlier.
- A log message no longer includes a fee amount.
- **Settings → Privacy & network.** Turn live data off (BitcoinTX then asks
  no public service for anything: no live price or block height, and past
  prices come only from those already stored), use your own mempool server
  for the live price and block height, and send every outside request
  through a proxy such as Tor (`socks5h://127.0.0.1:9050`). Public services
  stay the default.

### AI assistant (MCP)
- **The Mac app no longer needs your password in an AI app's settings.** It
  writes `~/Library/Application Support/BitcoinTX/mcp.json` (readable only by
  you) with its address and an AI assistant key, and the MCP server reads it
  by itself. Setup is one line with nothing secret in it (Settings → Connect an
  AI Assistant). The key works only from this computer and never for backup,
  restore, imports or deleting everything. Settings can turn AI access off or
  reset the key; the MCP server picks up a new key by itself. StartOS and
  Docker keep the username/password setup.
- **If you set up the MCP server with your password before:** remove the
  `BTCTX_URL`, `BTCTX_USERNAME` and `BTCTX_PASSWORD` lines from its
  configuration (for Grok Build, `~/.grok/config.toml`), or remove the server
  and add it again with the new one-line command. Check that a read such as
  `get_portfolio` works, then change your BitcoinTX password, since the old
  one sat in a plain-text file.
- `mcp_server/AI_SETUP.md` now tells the AI where the StartOS certificate
  comes from (the **Connect an AI Assistant** action's Root CA certificate,
  saved as `btctx-root-ca.crt`) and which password StartOS uses. The Settings
  prompt on a StartOS address already said "the guide explains"; it didn't.

### Tests
- Playwright click-through tests of every UI flow (`make e2e`; CI runs them in
  Chromium in Chicago and Tokyo time, and in WebKit). Form controls got proper
  labels for this (accessibility only).
- Property tests (Hypothesis): random valid ledgers keep the tax invariants.
  Golden years: three tax years worked out by hand, with exact Form 8949 rows
  and Schedule D lines. See `docs/TESTING.md`.

## [v0.9.1] - 2026-09-25 - Connect an AI Assistant in Settings, River sell fee, edit time, income basis

### Fixes
- **River import double-counted the fee on Sells.** River's Received Amount is
  what landed after River's fee (receipt: subtotal − fee = received), but it
  was stored as the gross, so the fee was subtracted a second time: proceeds
  and the Exchange USD balance came out short by the fee. Proceeds are now
  Received + fee. Sells imported before this fix keep the old figure; correct
  them by setting the proceeds to Received + fee.
- **Editing a transaction shifted its time by the UTC offset** (5 hours in
  CDT): the edit form showed the UTC time as local time and saved it back as
  local. It also dropped the seconds. A new transaction's default time had the
  same mix-up. The form now shows and saves local time, seconds included.
- **Income deposits entered without a cost basis were saved at $0**, which
  left them out of the income on the tax report and overstated the gain when
  the BTC was later sold. A Deposit with source Income, Interest or Reward
  into a BTC account, entered by hand or by CSV with a blank or 0 basis, is
  now valued at that day's BTC price, as River import and the MCP server
  already did; it isn't saved when no price is available. Editing such a
  deposit saved at $0 values it.
- The MCP `get_btc_price` tool says which moment its daily price is (00:00
  UTC) and to pass a transaction's UTC date.

### Distribution
- Releases signed with the `DEV_KEY` secret no longer fail to pack the s9pk
  when the secret ends with a newline or carries trailing spaces: the key is
  rewritten in the strict PEM form start-cli requires.

### AI assistant (MCP)
- **Settings → Connect an AI Assistant**: a setup prompt to paste into your AI
  app, with this server's address and your username filled in and the MCP
  server pinned to this release, plus a ready-made Claude Desktop config and
  `claude mcp add` command. Works for the macOS app, Docker and StartOS. The
  password is never shown or put in the prompt: the AI writes a placeholder
  you replace in the configuration file.
- `mcp_server/AI_SETUP.md`: setup instructions written for an AI assistant
  (Claude Code, Claude Desktop, Grok Build, other MCP clients), which the
  prompt points to.

## [v0.9.0] - 2026-09-23 - StartOS package in this repo, health check, maintenance CLI

### StartOS package
- The StartOS package now lives in this repository (`startos/`, start-sdk
  2.0.9) and is mirrored to DigiMonk73/BTCTX-StartOS. Installs of the old
  package (0.3.x through 0.8.0:1) update in place.
- New actions: **Connect an AI Assistant** (MCP address, login, the StartOS
  root CA, a ready-to-paste Claude Desktop config and `claude mcp add`
  command) and **Recalculate Ledger**. Updating from before 0.8.0 raises a
  Recalculate Ledger task.
- New **MCP API** interface (`…/api`), which the MCP server accepts as
  `BTCTX_URL`.
- Fresh installs prompt for Show Credentials before the first start.
- The database upgrade runs as its own startup step; the health check uses
  `/api/health`.
- The generated login moved from the app's volume to a separate package
  volume; both are backed up.
- Downgrades are refused (an older app can't open a migrated database).
- New vector icon.

### Distribution
- One release workflow (`release/vX.Y.Z` branch) produces the GHCR image, the
  macOS app as an unsigned `.dmg` plus the `.zip`, and `btctx.s9pk`, all on one
  GitHub release; the s9pk is signed with the `DEV_KEY` secret when it exists
  and `startos/` is mirrored to BTCTX-StartOS when `MIRROR_TOKEN` exists
  (`scripts/sync-startos-mirror.sh` by hand otherwise).
- CI checks the package and packs an x86_64 s9pk from every commit's image;
  a weekly job opens an issue when a newer start-sdk is on npm.

### Added
- `GET /api/health` (no login): 200 when the database answers at the current
  schema, 503 otherwise, with the app version. Used by the StartOS package and
  the CI container checks.
- `python -m backend.cli` maintenance commands: `migrate` (schema upgrade +
  defaults), `set-password [--username NAME] [--password-stdin]` (through the
  app's own hashing; the password never goes on the command line) and
  `recalculate` (rebuild the ledger). The StartOS package uses them instead of
  editing SQLite directly.
- Frontend unit tests (Vitest) for the transaction form's mapping to and
  from the API, run by the pre-push hook and CI. The mapping moved to
  `frontend/src/utils/transactionForm.ts`.

### Changed
- Logging defaults to INFO instead of DEBUG; set `LOG_LEVEL` (DEBUG, INFO,
  WARNING, ERROR) to change it.
- Only the newest 5 automatic database copies (taken before a schema upgrade
  or a restore) are kept in `<data dir>/backups/`; older ones are deleted.
- The app version (`VERSION`) ships inside the Docker image and the macOS app.
- The complete tax report no longer rebuilds the ledger inside the request
  to take its start- and end-of-year snapshots (33 writes for a small ledger,
  holding the database write lock, then discarded). The snapshots replay on
  an in-memory copy of the database; the report writes nothing.

## [v0.8.0] - 2026-09-23 - MCP server, schema migrations, tax fixes

### Distribution
- Multi-arch (amd64 + arm64) Docker image published to
  `ghcr.io/digimonk73/btctx-mcp` on every push to main; `:v0.8.0` is fixed.
  The StartOS package (DigiMonk73/BTCTX-StartOS v0.8.0:0) runs this image.
- Tax year 2026: the IRS draft Form 8949 and Schedule D were checked against
  the app (`scripts/irs_new_year.py --draft`, run weekly in CI): identical
  field layout to 2025, every field the app fills exists, box order matches.

### Added — MCP server (AI-assisted entry)
- **`mcp_server/`**: an MCP server (`btctx-mcp`) that lets an AI assistant
  (Claude Desktop, Claude Code, any MCP client) add transactions from pasted
  text or plain English: exchange emails, wallet history, explorer pages. Tools:
  guide, preview, add, list, update, delete (single), portfolio, BTC price.
  Runs locally over stdio and logs in to BitcoinTX with the user's credentials.
  See `mcp_server/README.md`.
- **JSON entry import API** (session-auth only):
  `POST /api/import/entries/preview` and `POST /api/import/entries/execute`.
  - Preview validates with the CSV importer's rules, dedups against the ledger
    with the River engine (exact → skipped, near-match → flagged), auto-fills
    FMV-derived USD values (Income/Interest/Reward basis, Spent proceeds,
    Gift/Donation FMV), then **dry-runs the real create path and rolls it
    back**: returns simulated realized gain/holding period per row, rejected
    rows (e.g. not enough BTC), balances afterward, and existing sales whose
    gains change due to backdating.
  - Execute is atomic with the same exact-duplicate guard and returns the
    created transaction ids.
- **`POST /api/transactions/recalculate`** (and MCP tool `recalculate_ledger`):
  rebuild all lots, disposals and gains from the transactions. **Run once after
  upgrading** so the fixes below reach existing data.
- New tests: `test_entry_import.py` (20), `test_transfer_fees.py` (5),
  `test_disposal_proceeds.py` (11), and 10 MCP end-to-end tests
  (`mcp_server/tests/`).

### IRS forms: yearly update tooling
- `scripts/irs_new_year.py YYYY`: downloads the final forms, rejects drafts and
  wrong-year PDFs, verifies field names and box order, diffs against the prior
  year, installs, and runs the template tests.
- A new year folder fails tests until its config is explicitly verified
  (`verified_years`), so it can't silently inherit last year's layout.
- `IRS forms watch` workflow checks irs.gov weekly Nov–Mar for new final forms.

### macOS desktop app
- Listens on a fixed local port, `http://127.0.0.1:8765` (override with
  `BTCTX_DESKTOP_PORT`; falls back to a random port if taken), so the MCP
  server can connect. Still bound to localhost only.
- PyInstaller spec lists the River/entry import modules; bundle version 0.8.0.

### Security (account takeover — upgrade recommended)
- **`/api/users` had no authentication.** Anyone who could reach the app
  could list users, change the password, or delete the account. Changing or
  deleting now requires being logged in as that user. First-run setup and
  re-registration use `POST /api/users/reset-account`, which the server allows
  only while the login is still the shipped `admin`/`password`, or with the
  current password (previously the "override password" was checked only in
  the browser). `GET /api/users/setup-status` is the only public user route.
- **Forgeable login cookies.** Without a `SECRET_KEY` env var (the Docker and
  StartOS default) sessions were signed with `default_secret_key`, published
  in this repo, so anyone could mint a valid login cookie. The macOS app used
  another published key. Now a random key is generated per install and stored
  next to the database (`.btctx_secret_key`, mode 600); an explicit
  `SECRET_KEY` still wins unless it is one of the published values.
  Existing users are logged out once after upgrading.

### Security / dependencies
- fastapi 0.141.1, starlette 1.7.0, pydantic 2.13.5, uvicorn 0.53.0 (starlette CVEs)
- cryptography 50.0.1, pypdf 6.19.0, sqlalchemy 2.0.54, python-dotenv 1.2.3
- axios 1.20.0 (high-severity advisories), react-hook-form, react-router-dom,
  eslint/typescript-eslint patch updates; `npm audit` clean
- Docker frontend build stage: node:18 (EOL) → node:22
- **Python 3.9 is no longer supported** (3.10+; Docker uses 3.11)

### Added — tax timezone
- **Settings → Tax Timezone** (auto-set from your browser on first login;
  `BTCTX_TIMEZONE` env var as a fallback). Tax years, Form 8949 dates,
  holding-period anniversaries, the reports and year-to-date totals now use
  it — a 10 pm Dec 31 sale in New York is no longer counted in the next
  year. Timestamps are still stored in UTC. Changing it recalculates.
- AI/MCP entries without a timezone are read in the tax timezone (a bare date
  means midday that day).

### Fixed — tax report placeholders
- The complete tax report valued year-end BTC at a hardcoded demo price
  ($94,153.13) and reported a hardcoded $4,000 profit in its asset summary.
  It now uses the real Dec 31 price and the year's actual gains/losses, and
  year-end holdings exclude activity after Dec 31.
- The complete tax report dropped transactions in the last second of the year.

### Changed — no more pdftk (Java)
- IRS forms are now filled and flattened in pure Python (pypdf). pdftk is no
  longer needed on macOS (`brew install pdftk-java` step gone), in Docker
  (image drops the Java runtime) or in CI. Output compared page-by-page with
  pdftk: Schedule D pixel-identical, Form 8949 identical except sub-pixel
  text placement in the description column.
- A field name missing from an IRS template now raises an error instead of
  being silently dropped (which produced blank forms).

### Changed — Form 1099-DA boxes (IRS broker reporting, 2025+)
- Exchange (River) sells are now reported in **Box H/K** for 2025 (on a
  1099-DA, basis not reported) and in **Box G/J** from 2026 for lots bought on
  the exchange on/after 2026-01-01 (covered, basis reported). Self-custody
  spends and network fees stay in **I/L**. Each box gets its own Form 8949
  page, and Schedule D now fills lines 1b, 2, 3, 8b, 9 and 10 as applicable
  (previously only 3 and 10).

### Fixed
- **Holding period off by one day.** Anything held 365+ days was long-term,
  so a sale on the one-year anniversary (or on day 365 in a leap year) got the
  long-term rate. IRS rule: long-term only when held MORE than one year —
  disposed after the anniversary date. Two old tests asserted the wrong
  answer and were corrected. Run the recalculation once to update existing
  sales.
- **IRS Form 8949 boxes.** No Part checkbox was ever checked (the IRS requires
  one), and the box letter was written into column (f) "Code(s)", which is for
  adjustment codes. For 2025 the app also used Box C/F, which the 2025 form
  reserves for non-digital assets. Now exactly one box is checked per Part —
  C/F for 2024, **I/L** (digital assets not on a 1099) for 2025+ — and column
  (f) is blank. Verified by filling the real IRS templates and reading every
  field back (`test_irs_templates.py`, runs for every bundled year).
- **BTC Transfer fees counted two ways.** The ledger treated a Transfer's
  `amount` as what left the source (fee included, as the UI's "amount sent"
  field does), but cost-basis lots took `amount + fee` from the source. Lots
  and balances drifted apart by every transfer fee, and sending a whole
  balance failed with "Not enough BTC". Lots now use the ledger/UI convention;
  a fee larger than the amount is rejected with a clear message. River
  imports (whose amounts exclude the fee) are converted at execute and in
  dedup, so re-imports still match. Dashboard balances do not change.
- **Proceeds shrank on every recalculation.** Stored `proceeds_usd` is the
  net value, but Sells from CSV/River/API (no `gross_proceeds_usd`) and every
  Spent withdrawal with a BTC fee re-derived net from that already-net value,
  losing the fee again on each backdated insert, edit or delete. The user's
  gross is now always recorded on create and on proceeds edits, and rows
  saved by older versions recover their gross on the next recalculation, so
  they stop shrinking. (Losses that already happened can't be undone
  automatically — compare old Sells/Spends against exchange records.)
- **River/CSV "Spent" withdrawals without proceeds became fake losses.** They
  were saved with $0 proceeds, realizing the full cost basis as a capital
  loss. They are now valued at the day's BTC price (as the CSV importer's
  warning always claimed), fetched once and stored. Existing rows are
  repaired on the next recalculation. An explicit $0 entered in the form is
  still respected.
- The transaction edit form now loads a withdrawal's gross proceeds, so
  re-saving an edit no longer nets the fee again.
- **Docker data could be lost on update.** The image never set
  `DATABASE_FILE`, so a plain `docker run -v …:/data` kept the database inside
  the container. The image now defaults to `/data/btctx.db`; CI checks the
  database and session key land on the volume. (StartOS was unaffected: its
  wrapper sets the same path.)
- **Form 1099-DA covered-lot cutoff** compared the acquisition time in UTC, so
  a lot bought on the evening of Dec 31, 2025 in the US counted as covered
  (Box G/J) while its printed acquisition date said 12/31/2025. It now uses
  the tax-timezone date.
- **Filled IRS forms were ~5 MB per Form 8949 sheet.** Flattening left the old
  field appearance streams in the file. Output is now ~0.3 MB per sheet and
  renders pixel-identically.
- `.env.example`'s placeholder `SECRET_KEY` was a publicly known value that
  would have been used as-is; it is now rejected like the other public
  defaults, and the example leaves the key unset (auto-generated).

### Added — per-transaction Form 1099-DA override
- A Sell or Spent withdrawal can record what the broker actually reported
  ("Broker form" in the transaction form; `broker_reporting` in the API and
  the MCP `update_transaction` tool): not on a broker form, proceeds only, or
  proceeds and basis. That picks the Form 8949 box for that sale (2025+:
  I/L, H/K, G/J; 2024 and earlier: C/F, B/E, A/D) instead of the default
  rules. Left on Automatic, nothing changes.
- The first real schema migration (0003): existing databases gain the column
  automatically on upgrade.

### Added — schema migrations
- The database schema is now managed by **Alembic migrations**
  (`backend/migrations/`), run automatically at every start. Before this, new
  tables were created on startup but new columns and indexes never reached
  existing databases.
- **Existing databases are adopted automatically**: checked against the v0.7.0
  schema, repaired where that's safe (databases from before Jan 2026 get the
  foreign-key indexes they never received), then upgraded. Verified against a
  database written by the real v0.7.0 code, in tests and in the Docker image.
- **Automatic backup** to a `backups/` folder next to the database before any
  schema change (or restore). Upgrades run in a single transaction: a failure
  leaves the database exactly as it was.
- A database from a newer BitcoinTX is refused with a clear message instead of
  being opened by older code.
- **Restoring an older backup now upgrades it** before it replaces the live
  database. Restores are validated first (wrong password, not a database, or
  from a newer version leave the live data untouched), swapped in atomically,
  and the database being replaced is kept in `backups/`. Encrypted backups are
  now taken with SQLite's backup API (consistent even while the app writes).

### Added
- **Settings → Recalculate Ledger** button (same as the MCP
  `recalculate_ledger` tool) for applying calculation fixes after an upgrade.

### Housekeeping
- Removed legacy scripts that drove a live server (one sent `delete_all` to
  port 8000), superseded IRS field-dump tools, `scripts/pre-commit.sh`,
  `baseline-pdfs/`, `clean_env.py` and the legacy Makefile targets. Finished
  design plans moved to `docs/archive/`.
- Lint: ruff enforces all Pyflakes rules and ESLint runs with zero warnings.
- Tests: two test files used soft assertions that logged failures without
  failing (108 checks); they now fail properly, which exposed one wrong
  holding-period expectation (fixed). Several tests that asserted nothing now
  check what their names claim.
- pytest moved out of `backend/requirements.txt` (it was installed in the
  Docker image) into `requirements-dev.txt`, upgraded to 9.1.1; the dependency
  audit now covers both files with no exceptions.
- Docs rewritten for the current code: README, CLAUDE.md, IRS form
  generation and yearly update, macOS app, StartOS, maintenance, testing.

---

## [v0.7.0] - 2026-06-10 - River CSV Import

### Added — River CSV Import
- **Import from River** (Settings page): upload a River bitcoin-activity CSV
  (river.com → Taxes & Documents) and merge it into a live ledger — unlike the
  onboarding CSV import, no empty-database requirement.
  - Adapter maps every River row pattern: Buy, Sell, Interest/Income (BTC
    interest on the River cash balance), tagged Withdrawals, and untagged
    on-chain sends/receives (default to cold-storage Transfers, flippable to
    Withdrawal/Deposit per row).
  - **Dedup engine**: rows already in the ledger are matched (exact BTC amount,
    compatible type, ±48h) and skipped; near-matches (transfers within ±20%)
    are flagged for review and excluded by default. Re-importing overlapping
    date ranges is safe and idempotent.
  - Buy funding source (Bank vs Exchange USD) defaults from a file-recurrence
    heuristic and is always a one-click toggle in the preview — by design the
    user is the final classifier on every import.
  - Interest/Income deposits get fair-market-value cost basis auto-filled from
    the historical BTC price (3-source failover), marked "est." and editable.
  - Atomic execute: all-or-nothing with server-side re-validation and a
    double-submit guard.
  - New endpoints `POST /api/import/river/preview` and
    `POST /api/import/river/execute` (session-auth only).
- 20 new tests (`backend/tests/test_river_import.py`, synthetic fixtures);
  suite now **184 tests**. Verified against a real 1,197-row River export
  (100% row coverage) and a live import reconciled to River's balance to the
  exact satoshi and cent.
- New runbook `docs/IRS_ANNUAL_FORM_UPDATE.md` for adding each year's IRS form
  templates (official IRS URL patterns, MD5 verification, field-diff procedure,
  per-year config and test checklist). `docs/IRS_FORM_GENERATION.md`'s stale
  update section now points to it.

---

## [v0.6.0] - 2026-06-10 - 2026 Modernization

### 2026 Modernization (June 2026)

#### Security / Dependencies (conservative pass: React 18 + Vite 6 retained)
- **Backend**: fastapi 0.115.8→0.121.3, starlette pinned 0.49.3 (CVE-2025-62727 HIGH StaticFiles Range-header DoS, CVE-2025-54121), python-multipart 0.0.20→0.0.32 (CVE-2026-42561 HIGH + 2), cryptography 44.0.2→46.0.7 (CVE-2026-26007 HIGH), pypdf 5.4.0→6.13.1 (~20 DoS CVEs; 5.x line unmaintained), reportlab 4.4.7→4.4.10 (4.5.x deliberately skipped — PDF output drift risk), uvicorn 0.49.0, sqlalchemy 2.0.50, requests ==2.34.2, python-dotenv 1.2.2, pytest 8.4.2; pydantic deliberately held at 2.12.5. Deferred majors documented in MAINTENANCE.md "Deferred Updates".
- **Frontend**: vite 6.4.3 (4 dev-server CVEs), axios 1.17.0 (CVE-2026-25639), react-router-dom 7.17.0 (SPA open-redirect/XSS), typescript 5.9.3, eslint 9.39.4; removed obsolete @types/react-router-dom; `npm audit` now reports 0 vulnerabilities.
- **Desktop**: pyinstaller >=6.20.0, pywebview >=6.2.1 (rebuild + save_file bridge check due at next .app build).

#### Fixed
- **2025 Form 8949 row capacity**: the 2025 IRS template holds 11 rows per page (2024: 14); the hardcoded 14-row chunking would have silently dropped rows 12-14 on 2025 filings (pdftk ignores unknown fields). Row capacity is now part of the year-specific field config.
- **Form 8949 multi-page handling**: overflow pages were numbered continuously (f1_, f2_, f3_...), but templates only define Page1 (Part I/short-term) and Page2 (Part II/long-term) fields — a second short-term chunk landed in the long-term table and later chunks vanished. Short/long chunks are now paired onto shared template-copy sheets, matching the paper form.
- Bundled 2025 templates verified MD5-identical to the final irs.gov releases (no draft markers).
- **Desktop app launch failure** (broken since 2026-02-14, exposed by the first .app build since January): the launcher's backend-readiness probe polled `/api/accounts/` expecting HTTP 200, but router-level auth (added Feb 2026) returns 401 — the probe spun for 30s and the app exited before ever creating a window (Dock dot, no UI). Probe now polls the unauthenticated SPA root.

#### Changed (behavior-preserving backend quality pass)
- Dead code removed (unused `fill_8949_multi_page`, legacy `AccountType` enum, duplicate `get_db`, debug prints, no-op `group_id` write); duplication consolidated (CSV upload validation, debug serializers, deposit aggregation, Schedule D field mapping); N+1 queries fixed in the transaction-history report (was 4 Account queries per row) and account balances; root-logger `basicConfig` calls replaced with module loggers.

#### UI Polish (existing dark theme, CSS-only)
- Design tokens: easing curves, letter-spacing, layered shadows, missing `--color-text-dim` defined; tabular numerals on all financial figures; gold active-nav underline; dashboard card hover lift; transaction date-heading hairlines; side-panel slide-in animation; `prefers-reduced-motion` support; theme-matched scrollbars; login.css duplicated rule blocks removed; stale pre-rebrand colors tokenized. Browser-verified at 1440/800/768/480px; layout, breakpoints, and 44px touch targets unchanged.

#### Testing
- New `backend/tests/test_2025_forms.py` (6 tests) incl. an 11-row capacity regression test; suite now **164 tests** (was 158).
- New PDF baseline gate `baseline-pdfs/regen_and_diff.sh`: regenerates all three reports against a frozen seed dataset and text-diffs them against committed baselines (run after every modernization phase; output verified equivalent throughout — a documented price-provider variant baseline covers live BTC-price variance in transfer-fee valuations).

### Test Isolation & Backups (February 2026)
- Test suite isolated from the production database (FastAPI TestClient + temp SQLite via dependency override; no running backend needed for most tests)
- Daily encrypted-safe SQLite backup script `scripts/backup-db.sh` (cron 3 AM, 60-day retention)

### Added
- **PDF Content Verification Test Suite**: `backend/tests/test_pdf_content.py` with 23 new tests
  - Uses `pypdf` to extract and verify actual PDF content, not just file generation
  - Complete Tax Report tests: year, sections, capital gains, ending balance, income, long/short-term
  - IRS Form tests: Schedule D present, Form 8949, proceeds, tax year, long-term section, page count
  - Transaction History tests: CSV headers, transaction data, types, PDF content
  - Edge case tests: empty year, large amounts ($7.5M), small BTC precision (0.00012345), same-day sales
  - Data accuracy tests: gain calculation, FIFO cost basis tracking, income totals
  - Total pytest tests: **158** (was 135)

### Fixed
- **test_seed_data_integrity.py**: Made tests self-contained with fixture that creates test data if database is empty
- **Disposal test logic**: Fixed to correctly skip USD transfers (only BTC transfers require lot disposals)

---

## [v0.5.5] - 2025-01-17 - Transaction Edit Fix

### Fixed
- **Transaction editing in macOS desktop app**: Fixed bug where editing transactions would fail with "Not enough BTC" error
  - Root cause: Backend's `update_transaction_record()` had flawed lot logic when backdating transactions
  - The partial re-lot (`recalculate_subsequent_transactions`) ran before full scorched earth, using stale lot balances
  - Fix: Simplified update flow to use only full scorched earth (`recalculate_all_transactions`)
  - This also fixes potential edge cases in Docker/web deployments with specific transaction histories

### Improved
- **PUT response validation**: Edit form now validates backend response before showing success
- **Realized gain display on edit**: Edit transactions now show realized gain in success toast (matching create behavior)

### Technical Notes
- **Files Modified:** `backend/services/transaction.py`, `frontend/src/components/TransactionForm.tsx`
- **Documentation:** `docs/archive/edit-tx-bug-mac.md` - Full investigation and fix details
- **Tests:** All 135 pytest tests pass, 17/17 pre-commit tests pass

---

## [v0.5.4] - 2025-01-16 - Buy from Bank Feature

> **Rollback Tags:** If issues arise, rollback to `pre-bank-buy` (develop) or `pre-bank-buy-master` (master)

### Added
- **Buy from Bank**: Buy transactions can now originate from Bank account (auto-buy support)
  - New "From Account" dropdown in Buy form: Exchange USD (default) or Bank (auto-buy)
  - CSV import accepts `Bank` as source for Buy transactions
  - FIFO cost basis tracking works correctly - lots land in Exchange BTC pool regardless of USD source
  - Backend validation relaxed to allow `from_account = Bank (1) OR Exchange USD (3)`
  - 5 new tests in `TestBuyFromBank` class covering basic flow, FIFO order, CSV import, backward compatibility
  - Documentation: `docs/archive/BUY_FROM_BANK_FEATURE.md`

### Technical Notes
- **Risk Level:** LOW - FIFO logic uses `to_account_id` (unchanged), not `from_account_id`
- **Backward Compatible:** Existing Buy transactions and CSVs continue to work unchanged
- **Files Modified:** `transaction.py`, `csv_import.py`, `TransactionForm.tsx`, `global.d.ts`, `test_stress_and_forms.py`

---

## [v0.5.3] - 2025-01-17 - Comprehensive Test Suite & Desktop Fixes

### Added
- **Comprehensive Test Suite**: `backend/tests/test_stress_and_forms.py` with 46 new pytest tests
  - Volume/stress testing (250+ transactions, backdating cascades, multi-year)
  - Edge cases: holding period boundaries (364/365/366 days), satoshi precision, $100M amounts
  - Account-specific FIFO verification (Exchange vs Wallet isolation)
  - All deposit sources tested: MyBTC, Gift, Income, Interest, Reward
  - All withdrawal purposes tested: Spent, Gift, Donation, Lost (with correct tax treatment)
  - IRS Form 8949 validation: multi-page (15/30 disposals), non-taxable exclusions
  - Schedule D totals verification
  - Total pytest tests: 131 (was 84)
- **macOS Desktop App**: Native macOS application using PyInstaller + pywebview
  - Self-contained `.app` bundle (~61MB) with embedded FastAPI backend
  - Data persists in `~/Library/Application Support/BitcoinTX/btctx.db`
  - Automated build script: `desktop/build-mac.sh`
  - PyInstaller spec with all hidden imports configured
  - Dynamic port allocation for backend server
  - Dark mode support, resizable window (1280x800 default, 800x600 min)
  - pdftk detection with user warning dialog if missing
  - Files added: `desktop/entrypoint.py`, `desktop/BitcoinTX.spec`, `desktop/build-mac.sh`, `desktop/requirements.txt`, `desktop/README.md`
  - Documentation: `docs/MACOS_DESKTOP_APP.md`
- **Mobile Responsiveness Overhaul**: Comprehensive mobile-friendly UI updates
  - Transaction panel: responsive width, fixed overlay positioning on mobile
  - Login page: fluid width for small screens
  - Navigation: CSS grid layout for mobile (3-column at 768px, 2-column at 480px)
  - Touch targets: minimum 44px for all interactive elements
  - Transaction list: mobile labels via CSS `::before` pseudo-elements
  - Added `:active` states for touch feedback across all interactive elements
  - Files modified: `transactionPanel.css`, `login.css`, `transactions.css`, `app.css`, `converter.css`, `reports.css`, `dashboard.css`, `settings.css`, `theme.css`, `transactionForm.css`
- **Frontend Design System Refactor**: Major code quality and architecture improvements
  - Custom hooks: `useAccounts`, `useApiCall`, `useBtcPrice` for reusable logic
  - Toast notification system with `ToastContext` for user feedback
  - Error boundaries (`ErrorBoundary.tsx`) for graceful error handling
  - Centralized theme system (`theme.css`) with CSS variables
  - Barrel exports via `hooks/index.ts`
- **CSV Export**: Export all transactions as a CSV file matching the import template format
  - Creates clean roundtrip: Export → Edit → Re-import
  - File naming: `btctx_transactions_YYYY-MM-DD.csv`
  - New endpoint: `GET /api/backup/csv`
- **CSV Import Instructions PDF**: Downloadable PDF guide for CSV import feature
  - New endpoint: `GET /api/import/instructions`
- **Pre-Commit Test Suite**: 17 tests for catching regressions
  - Run with: `./scripts/pre-commit.sh` or `python backend/tests/pre_commit_tests.py`

### Changed
- **Sidebar brand layout**: Changed from horizontal to vertical stack (logo above title)
- **Logout button**: Removed lock emoji, simplified to text-only
- **Logout link color**: Changed from dark red (#811922) to brighter red (#cf4655) to fix font rendering issue on macOS dark backgrounds
- **Pydantic V1 → V2 Migration**: Updated all deprecated Pydantic patterns
  - Replaced `@validator` with `@field_validator` + `@classmethod`
  - Replaced `class Config` with `model_config = ConfigDict(...)`
  - Replaced `orm_mode` with `from_attributes`
  - Replaced `.from_orm()` with `.model_validate()`
  - Replaced `.dict()` with `.model_dump()`
  - Eliminates all Pydantic deprecation warnings
  - Documentation: `docs/archive/PYDANTIC_MIGRATION.md`

### Fixed
- **pdftk path resolution for macOS desktop**: Added centralized `pdftk_path.py` module
  - PyInstaller bundles don't inherit system PATH, breaking pdftk detection
  - New module checks known Homebrew locations (`/opt/homebrew/bin/pdftk`, `/usr/local/bin/pdftk`)
  - Caches resolved path for performance
  - Updated `pdf_utils.py`, `pdftk_filler.py`, `reports.py` to use new module
- **Reports page desktop downloads**: Reports now download correctly in macOS desktop app
  - Updated `Reports.tsx` to use desktop-aware download utility
  - Added PyWebView API TypeScript types to `global.d.ts`
- **macOS desktop app downloads**: Settings page downloads (backup, CSV export, templates) now work correctly in the desktop app
  - Added `desktopDownload.ts` utility that detects pywebview environment
  - Uses native file save dialog via `window.pywebview.api.save_file()` when running in desktop app
  - Falls back to standard browser download for web/Docker deployment
  - File: `frontend/src/utils/desktopDownload.ts`
- **Lint errors fixed**: Removed unused variables in `useBtcPrice.ts` and `Settings.tsx`
- **Form 8949 non-taxable exclusion**: Gift, Donation, and Lost disposals now correctly excluded
- **Proceeds degradation fix**: Fixed bug where `proceeds_usd` could degrade during recalculation
- **None-to-Decimal conversion**: Fixed TypeError in report generation after Pydantic V2 migration
  - `.model_dump()` includes keys with `None` values, breaking `Decimal(tx_data.get("key", default))`
  - Changed to `Decimal(tx_data.get("key") or default)` pattern in `transaction.py`
- **FIFO lot disposal now account-specific**: Fixed bug where selling/withdrawing BTC would consume lots from all accounts globally instead of only from the source account. This ensures correct cost basis tracking when BTC is held across multiple accounts.
- **SPA routing in Docker**: Fixed browser refresh returning 404 on client-side routes
  - Added custom exception handler to serve `index.html` for non-API 404s
  - React Router now handles `/dashboard`, `/transactions`, `/settings`, etc. on page refresh
  - API routes still return proper JSON errors
  - File: `backend/main.py`

### Files Added
- `backend/tests/test_stress_and_forms.py` - Comprehensive stress testing and IRS form validation (46 tests)
- `backend/services/reports/pdftk_path.py` - Centralized pdftk path resolution for macOS desktop compatibility
- `frontend/src/utils/desktopDownload.ts` - Desktop app file download utility with pywebview integration
- `frontend/src/hooks/useAccounts.ts` - Account fetching and caching hook
- `frontend/src/hooks/useApiCall.ts` - Generic API call hook with loading/error states
- `frontend/src/hooks/useBtcPrice.ts` - BTC price fetching hook
- `frontend/src/hooks/index.ts` - Barrel exports for hooks
- `frontend/src/components/ErrorBoundary.tsx` - React error boundary component
- `frontend/src/components/Toast.tsx` - Toast notification component
- `frontend/src/components/ToastContainer.tsx` - Toast container component
- `frontend/src/contexts/ToastContext.tsx` - Toast context provider
- `frontend/src/styles/theme.css` - Centralized CSS variables and theming
- `frontend/src/styles/toast.css` - Toast notification styles
- `frontend/src/styles/errorBoundary.css` - Error boundary styles
- `backend/tests/pre_commit_tests.py` - Pre-commit test suite
- `scripts/pre-commit.sh` - Shell script wrapper for pre-commit tests

---

## [v0.5.0] - 2025-01-14 - Backend Refactoring & Test Suite

### Major Backend Refactoring

#### Code Modernization
- **Removed passlib dependency**: Direct bcrypt usage for password hashing
  - `User.set_password()` and `User.verify_password()` now use bcrypt directly
  - Added 72-byte password limit validation (bcrypt requirement)
  - Eliminates passlib deprecation warnings
- **Replaced deprecated `Query.get()`**: Updated to `Session.get()` pattern
  - 10 occurrences in `transaction.py`
  - 1 occurrence in `debug.py`
  - 1 occurrence in `test_seed_data_integrity.py`
- **Replaced `@app.on_event` deprecation**: Migrated to FastAPI lifespan context manager
- **Removed duplicate import**: Fixed `from_orm` duplicate in `form_8949.py`

#### Performance Improvements
- **Added `joinedload` eager loading**: Optimized `compute_sell_summary_from_disposals()`
  - Prevents N+1 queries when loading `LotDisposal.lot` relationships
- **Added database indexes on foreign keys**:
  - `LedgerEntry.transaction_id`, `LedgerEntry.account_id`
  - `BitcoinLot.created_txn_id`
  - `LotDisposal.lot_id`, `LotDisposal.transaction_id`

#### Code Organization
- **Created `backend/constants.py`**: Centralized account ID constants
  - `ACCOUNT_BANK`, `ACCOUNT_WALLET`, `ACCOUNT_EXCHANGE_USD`, `ACCOUNT_EXCHANGE_BTC`
  - `ACCOUNT_BTC_FEES`, `ACCOUNT_USD_FEES`, `ACCOUNT_EXTERNAL`
  - Replaced magic numbers throughout codebase
- **Deleted dead files**:
  - `backend/create_account_db.py` (unused)
  - `backend/create_db.py` (replaced with inline command)
- **Updated Makefile**: `create-db` target now uses inline Python command

### CSV Import/Export Fixes
- **Fixed CSV export `proceeds_usd`**: Now falls back to `proceeds_usd` when `gross_proceeds_usd` is None
- **Relaxed CSV import validation**: Now matches transaction service rules
  - Deposit: External → any internal account (BTC or USD)
  - Withdrawal: any internal account → External
  - Transfer: between internal accounts of same currency

### Testing

#### Comprehensive Test Suite (`backend/tests/test_everything.py`)
78 automated tests covering:
- Database seeding with 65 test transactions
- All API endpoints (accounts, transactions, calculations, debug)
- All report generation (Complete Tax Report, IRS Forms, Transaction History)
- CSV export/import roundtrip verification
- FIFO integrity (lots, disposals, account balance matching)
- Gains/losses calculations and income tracking
- All transaction types, withdrawal purposes, deposit sources
- Holding period verification (short-term vs long-term)

Run with: `python3 backend/tests/test_everything.py`

#### Authentication Test Suite (`backend/tests/test_password_migration.py`)
Comprehensive auth tests:
- Password hashing and verification
- 72-byte bcrypt limit enforcement
- Unicode and special character passwords
- Login/logout endpoint tests
- Session persistence tests
- Protected endpoint authentication
- Backward compatibility with existing hashes

Run with: `pytest backend/tests/test_password_migration.py -v`

#### Updated Seed Data (`backend/tests/transaction_seed_data.json`)
- 65 transactions across 2023-2025
- All 5 deposit sources: MyBTC, Gift, Income, Interest, Reward
- All 4 withdrawal purposes: Spent, Gift, Donation, Lost
- Short-term and long-term gains coverage
- USD and BTC deposits to various accounts

### Dependency Updates

| Package | Old Version | New Version |
|---------|-------------|-------------|
| pydantic | 2.10.6 | 2.12.5 |
| uvicorn | 0.34.0 | 0.40.0 |
| sqlalchemy | 2.0.37 | 2.0.45 |
| httpx | 0.24.1 | 0.28.1 |
| requests | 2.28.1 | 2.32.0 |
| python-multipart | 0.0.6 | 0.0.20 |
| python-dateutil | 2.8.2 | 2.9.0 |
| itsdangerous | 2.1.2 | 2.2.0 |
| reportlab | 3.6.12 | 4.4.7 |
| pytest | 8.1.1 | 8.3.5 |

### Removed Dependencies
- `passlib` - replaced with direct bcrypt
- `typer` - unused
- `python-jose` - unused
- `pandas` - unused
- `weasyprint` - unused
- `pdfkit` - unused
- `jinja2` - unused (beyond FastAPI's built-in)
- `pycryptodome` - unused

### Files Added
- `backend/constants.py` - Centralized account ID constants
- `backend/tests/test_everything.py` - Comprehensive test suite (78 tests)
- `backend/tests/test_password_migration.py` - Authentication tests

### Files Modified
- `backend/models/user.py` - Direct bcrypt, 72-byte limit
- `backend/models/transaction.py` - FK indexes
- `backend/database.py` - Direct bcrypt for default user
- `backend/main.py` - Lifespan context manager
- `backend/services/transaction.py` - Query.get(), joinedload, constants
- `backend/routers/backup.py` - proceeds_usd fallback, constants
- `backend/routers/debug.py` - Query.get()
- `backend/services/csv_import.py` - Relaxed validation, constants
- `backend/services/reports/form_8949.py` - Removed duplicate import
- `backend/tests/register_default_user.py` - Direct bcrypt
- `backend/requirements.txt` - Updated all versions
- `Makefile` - Updated create-db target

### Files Deleted
- `backend/create_account_db.py`
- `backend/create_db.py`

---

## [v0.4.0] - 2025-01-12

### Added
- **CSV Template Import**: Bulk transaction import from CSV files
  - Download CSV template with exact column structure
  - Preview parsed transactions before importing
  - Full validation with error/warning display
  - Atomic import (all-or-nothing) with rollback on failure
  - Requires empty database (Phase 1 - no merge complexity)

### Endpoints
- `GET /api/import/template` - Download blank CSV template
- `GET /api/import/status` - Check if database is empty
- `POST /api/import/preview` - Parse and preview CSV (no DB writes)
- `POST /api/import/execute` - Execute atomic import

### Files Added
- `backend/schemas/csv_import.py` - Pydantic request/response models
- `backend/services/csv_import.py` - Parsing, validation, and import logic
- `backend/routers/csv_import.py` - API endpoints

### Fixed
- **Atomic imports**: Added `auto_commit` parameter to `create_transaction_record()`
  - Bulk imports now use `auto_commit=False` to defer commit until all succeed
  - Prevents partial imports on validation failures
- **Async event loop conflict**: Fixed `get_btc_price()` during CSV import
  - Used `ThreadPoolExecutor` to run async price fetches in separate threads
  - Fixes "Cannot run the event loop while another loop is running" error

---

## [v0.3.2] - 2025-01-10

### Fixed
- **Backup restore redirect**: Fixed "Not Found" error after successful backup restore
  - After restoring a backup, the session cookie still referenced the old user_id
  - Backend now clears session after restore (`request.session.clear()`)
  - Frontend redirects to `/login` instead of reloading the page
  - Users now see success message and are redirected to login properly

---

## [v0.3.1] - 2025-01-10

### Fixed
- **Backup/restore in Docker/StartOS**: Fixed `backup.py` to use `DATABASE_FILE` environment variable
  - Previously used hardcoded path `backend/bitcoin_tracker.db` which didn't match Docker's `/data/btctx.db`
  - Backup and restore now work correctly in containerized environments
- **Backup file cleanup race condition**: Fixed temp file deletion before streaming complete
  - Now uses FastAPI `BackgroundTasks` to delete temp file after response completes

### Documentation
- **StartOS container architecture**: Comprehensive documentation in `docs/STARTOS_COMPATIBILITY.md`
  - Two-repository architecture explanation
  - Volume mounts and data persistence
  - DATABASE_FILE environment variable
  - Common mistakes to avoid

---

## [v0.3.0] - 2025 IRS Form Support

### Added
- **Multi-year IRS form support**: Users can now generate IRS reports for both 2024 and 2025 tax years
- Year-based template folder structure (`backend/assets/irs_templates/2024/`, `2025/`)
- `get_template_path(year, form_name)` - Dynamic template path selection
- `get_supported_years()` - Returns list of available tax years
- `get_8949_field_config(year)` - Year-specific Form 8949 field naming
- `get_schedule_d_field_config(year)` - Year-specific Schedule D field naming
- 2025 IRS Form 8949 and Schedule D templates
- Comprehensive test dataset (40 transactions spanning 2023-2025)

### Fixed
- **Schedule D field mapping**: Changed from Line 1b/8b to Line 3/10 for self-tracked crypto
  - Self-custody Bitcoin uses Box C (short-term) and Box F (long-term) - not reported on 1099
  - Line 3 for short-term totals from Box C, Line 10 for long-term totals from Box F
- **Complete Tax Report generation**: Fixed Transfer lot restoration in `_partial_relot_strictly_after()`
  - Transfer transactions now properly restore source lot balances during year-boundary recalculations
  - Uses LIFO to reverse FIFO consumption when rebuilding transactions

### Changed
- `map_8949_rows_to_field_data()` now accepts `year` parameter for correct field naming
- `map_schedule_d_fields()` now accepts `year` parameter
- `fill_8949_multi_page()` now accepts `year` parameter
- `_verify_templates_exist()` now validates year-specific template availability
- IRS reports endpoint returns helpful error for unsupported years

### Technical Details
- 2024 Form 8949: `Table_Line1`, fields `f1_3` (not zero-padded)
- 2025 Form 8949: `Table_Line1_Part1`/`Part2`, fields `f1_03` (zero-padded for row 1)
- Schedule D Line 3 (Row3): Short-term from Box C/I (self-tracked, no 1099)
- Schedule D Line 10 (Row10): Long-term from Box F/L (self-tracked, no 1099)

---

## [v0.2.0-beta] - StartOS Packaging Complete

### Added
- `docs/` directory for project documentation
- `CLAUDE.md` - AI assistant context file (root directory for auto-detection)
- `docs/CHANGELOG.md` - This file
- `docs/ROADMAP.md` - Future goals and planned features
- `docs/STARTOS_COMPATIBILITY.md` - Docker requirements for StartOS packaging

### Changed
- Updated `README.md` with current Docker instructions and accurate tech stack

---

## [2025-01-10] - Docker Compatibility & Cleanup

### Fixed
- **PDF generation paths**: Changed relative paths to absolute paths in `backend/routers/reports.py`
  - IRS Form 8949 and Schedule D templates now load correctly regardless of working directory
  - Added `_verify_pdftk_installed()` and `_verify_templates_exist()` pre-flight checks

- **BTC price fetching in Docker**: Fixed `get_btc_price()` in `backend/services/transaction.py`
  - Previously made HTTP calls to `localhost:8000` which failed in Docker (port 80)
  - Now calls bitcoin service functions directly via import

- **Python 3.9 compatibility**: Added `from __future__ import annotations` to:
  - `backend/schemas/transaction.py`
  - `backend/services/user.py`
  - Fixes `TypeError: unsupported operand type(s) for |` for union type syntax

### Changed
- Cleaned up 63 stale branches across repositories
- Established `master`/`develop` branch workflow

### Infrastructure
- Docker image published to `b1ackswan/btctx:latest`
- All repositories synced

---

## [Pre-2025] - Initial Development

### Features
- Double-entry accounting system for BTC transactions
- FIFO cost basis tracking with BitcoinLot/LotDisposal models
- IRS Form 8949 and Schedule D PDF generation
- Dashboard with holdings, balances, and gains
- Transaction entry form (Deposit, Withdraw, Transfer, Buy, Sell)
- Historical BTC price fetching (CoinGecko, Kraken, CoinDesk)
- Session-based authentication
- CSV/PDF transaction history export
