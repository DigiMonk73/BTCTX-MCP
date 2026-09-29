# Next release: 1.2.1

Decided with the owner on 2026-09-28. A fix release: everything in the
CHANGELOG's Unreleased section (the price-source privacy fix, restore
keeping the login, clearer report and Tor errors, the CSV fee flag, the
dashboard label, dependency updates). Delete this file once 1.2.1 is out.

## Waits for

- [ ] **The owner's box test of 1.2.0** (`startos-box-test-v1.2.0.md`),
      mainly **My Mempool on this server**, which the VM can't test. Anything
      it finds is fixed in 1.2.1.

## Steps (CLAUDE.md "Releasing", startos/UPDATING.md)

- [ ] If Start9 has forked the mirror by then: `scripts/start9-pull.sh`,
      then `--apply` on `develop`.
- [ ] Bump to 1.2.1 everywhere `test_versions_agree.py` checks. The package
      version: 1.2.0:0's `up` does real work, so move `current.ts` to
      `v1.2.0_0.ts` first; release notes in all five languages.
- [ ] CHANGELOG: Unreleased → `## [v1.2.1] - <date> - <summary>`.
- [ ] Push `develop`, wait for CI.
- [ ] **VM proof** (owner's choice): build an **aarch64** `btctx.s9pk` from
      that commit on the Mac (the CI artifact is x86_64 only), then in
      `~/code/btctx-vm-lab`: `./vm.sh reset --yes`, run
      `scenarios/update-1.1.0-to-1.2.0.md` with 1.2.1 as the update, plus an
      update 1.2.0 → 1.2.1. Must pass: **no public price request after the
      update while the price question is unanswered** (afd23ea); an in-app
      restore keeps the login; the Tor-stopped message names Tor.
- [ ] Fast-forward `main`, push `release/v1.2.1`, delete the branch after.
      (The Dependabot dev-tools fix reaches `main` with it.)
- [ ] Website (btctx-site): the 1.2.1 notes.
- [ ] If Start9 has forked: PR from the mirror's `main` to their fork.

## Not part of this release

- Emailing Start9 (submissions@start9.com, the mirror DigiMonk73/BTCTX-StartOS)
  to submit the package: the owner decides when (no plan yet, 2026-09-28).
