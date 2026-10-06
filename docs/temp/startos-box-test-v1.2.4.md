# StartOS box test: 1.2.4:1 from Community Beta

Test Start9's build of package 1.2.4:1 on your own StartOS server, from the
Community Beta registry, before Start9 promotes it to everyone. It's the
BitcoinTX 1.2.4 app with Start9's review of the package: one **Set Login
Credentials** action instead of Show Credentials and Reset Login
Credentials. Your data stays in place. Delete this file once it's done and
the result has gone into `docs/CHANGELOG.md` or a fix. Issue: #30.

**Already checked on a StartOS VM:** with 1.2.2 (2026-09-28/29), the updates
from 1.1.0, every stored figure and the login identical, Price Source &
Privacy (Off, Public, Public over Tor), past prices, reports, the AI
connector (`~/code/btctx-vm-lab/scenarios/`); with 1.2.4:1 (2026-10-05,
Claude's own build of the same package), the update from 1.2.4:0 with every
figure and the login identical, and Set Login Credentials on an update and
a fresh install. Your box checked **My Mempool on
this server** with 1.2.2 (2026-09-29); it gets one quick look again below.

## Before you start

- [ ] Make a StartOS backup that includes BitcoinTX. An update can't be
      undone except by restoring a backup.
- [ ] Note two or three figures to compare afterwards, e.g. Total BTC and
      Net Short-Term on the Dashboard.
- [ ] Make sure you know your BitcoinTX login (you'll need it to log in
      after the update, unless StartOS asks you to set a new one).
- [ ] In StartOS, **Marketplace**: add the registry
      `https://community-beta-registry.start9.com` and switch to it.

## Update

- [ ] Find BitcoinTX in the Community Beta registry; it shows version
      1.2.4:1. Click **Update** (or **Install** if it's not on this server).
      StartOS shows the release notes, starting "Package revision 1".
- [ ] If StartOS refuses because the package is signed differently from
      the one you have (you sideloaded your own builds before), **don't
      uninstall** (that deletes your data): tell Claude.
- [ ] Tasks after the update:
  - No **Set Login Credentials** task: expected if StartOS keeps a
    password for you (Show Credentials used to show it). Your login stays
    as it was, even if you changed the password inside BitcoinTX since.
  - A critical **Set Login Credentials** task: expected only if StartOS
    keeps no password for you (Show Credentials showed only the username,
    because you set your password inside BitcoinTX on an old install). Stop
    BitcoinTX, run it, and save the new username (`admin`) and password
    somewhere safe: **they're shown only once**. Your old login stops
    working; your transactions stay.
- [ ] The old Show Credentials and Reset Login Credentials actions are
      gone; **Set Login Credentials** is listed under Actions.

## Your data

- [ ] Start BitcoinTX, open the **Web UI** and log in.
- [ ] Transactions are all there; the figures you noted match.
- [ ] **Settings > Ledger Review**: nothing new to fix (1.2.4 changes no tax
      figure). If it lists "Figures that Recalculate Ledger would change",
      tell Claude before running anything.
- [ ] **Reports**: Form 8949 / Schedule D for last year downloads and looks
      right.
- [ ] Dashboard: with **My Mempool on this server** still chosen, a current
      Bitcoin price and a block height show up.

## Set Login Credentials

Only if you want to try it now (it replaces your login):

- [ ] With BitcoinTX running, **Set Login Credentials** is greyed out: it
      runs only while stopped.
- [ ] Stop BitcoinTX and run it. It warns that it replaces your username
      and password, then shows `admin` and a new password once. Save it.
- [ ] Start BitcoinTX: the new password logs in, the old one doesn't, and
      the figures are unchanged.

## Optional

- [ ] Recalculate Ledger action: it says "Transactions recalculated: N".
- [ ] AI assistant: run **Connect an AI Assistant**; the address and
      configuration show up, and your AI app still connects.

## Tell Claude

- All good: "the box test passed". Claude then drafts the request asking
  Start9 to promote the build (#30).
- Anything off: what you did, what you expected, what happened, and a
  screenshot or the log lines.
