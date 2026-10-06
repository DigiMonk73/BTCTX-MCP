# StartOS box test: v1.2.2

Test the released v1.2.2 package on your own StartOS server. You're
updating from 1.1.0 (1.2.0's and 1.2.1's changes come with it), and your
data stays in place. Delete this file once it's done and the result has
gone into `docs/CHANGELOG.md` or a fix. Issue: #30 (it moves to the
Community Beta build of 1.2.4:1).

**Already checked on a StartOS VM (2026-09-28/29):** the updates 1.1.0 →
1.2.2, 1.1.0 → 1.2.0 → 1.2.1 → 1.2.2 and 1.2.0 → 1.2.1, every stored
figure and the login identical, Show Credentials, Price Source & Privacy
(Off, Public, Public over Tor), past prices, reports, the AI connector
(`~/code/btctx-vm-lab/scenarios/`). What only your box can check is **My
Mempool on this server**, so that section matters most. Anything it finds
goes into 1.2.3.

## Before you start

- [ ] Make a StartOS backup that includes BitcoinTX. An update can't be
      undone except by restoring a backup.
- [ ] Note two or three figures to compare afterwards, e.g. Total BTC and
      Net Short-Term on the Dashboard.
- [ ] Download the package, signed with your key:
      <https://github.com/DigiMonk73/BTCTX-MCP/releases/download/v1.2.2/btctx.s9pk>
      (133 MB).

## Update

- [ ] In StartOS, click **Sideload** in the top bar and upload `btctx.s9pk`.
- [ ] Confirm the update (StartOS shows the 1.2.2 release notes). It
      updates in place.
- [ ] If StartOS asks you to run **Show Credentials**, run it and save the
      password. That only happens if your login was still `admin` /
      `password`.

## Price source: your own Mempool

**Owner, 2026-09-29: My Mempool tested with a fully synced node.**

- [ ] Run the **Price Source & Privacy** action (StartOS reminds you after
      the update) and choose **My Mempool on this server**. If you typed a
      mempool address into BitcoinTX in 1.1.0, this replaces it.
- [ ] If StartOS says Mempool must be installed or running, start it, then
      start BitcoinTX.
- [ ] Open the **Web UI** and log in.
- [ ] Dashboard: a current Bitcoin price and a block height show up.
- [ ] **Settings > Privacy & Network** shows your choice as read-only (it's
      set by the server).
- [ ] Past price: in the **Sats Converter** on the left, click **Date** and
      pick a day since you installed Mempool. A BTC price shows up. This is
      the same price history your tax figures use, and nothing is saved to
      your ledger. (Days before your Mempool's history show no price unless
      you turn on the fallback; that's expected.)
- [ ] BitcoinTX's **Logs** in StartOS: a line
      `Price history from your mempool server: N days`, and **no** line
      `BTC price history from public site …`.

## Your data

- [ ] Transactions are all there; the figures you noted match.
- [ ] **Settings > Ledger Review**: if it lists "Figures that Recalculate
      Ledger would change", read them, then run **Recalculate** (1.2.2's
      fixes can change a few cents or a fee's handling).
- [ ] **Reports**: Form 8949 / Schedule D for last year downloads and looks
      right.

## Optional

- [ ] Tor: with the Tor service installed, choose **Public price sites** and
      turn on **over Tor**. Prices still load, and the log names the public
      site. Then switch back to **My Mempool on this server**.
- [ ] AI assistant: run **Connect an AI Assistant**; the address and
      configuration show up.

## Tell Claude

- All good: "the box test passed".
- Anything off: what you did, what you expected, what happened, and a
  screenshot or the log lines. Fixes ship as 1.2.3.
