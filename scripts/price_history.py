#!/usr/bin/env python3
"""
Keep the hourly BTC price history's manifest (backend/assets/btc_prices/,
#144): one line per year from 2013, with the SHA-256 of that year's file of
Bitstamp's hourly opening prices. The app downloads the same years from
Bitstamp and uses one only if it gives this fingerprint.

    python scripts/price_history.py refresh          # make prices: add the hours since the last refresh
    python scripts/price_history.py verify           # offline: the manifest is well formed
    python scripts/price_history.py check-sources    # online: Bitstamp still gives every fingerprint
    python scripts/price_history.py release-check --commit-time UNIX [--no-age-check]

refresh downloads the open year again (and a new one in January), in the
same fixed blocks the app asks for. It refuses, writing nothing, when:
  - an hour is missing;
  - the hours already in the manifest no longer give their fingerprint
    (Bitstamp changed a past price);
  - a new hour from 2023 on doesn't agree with a second exchange: Bitfinex's
    hourly open for every new hour, Kraken's for its latest 720 hours (the
    limits are under "Cross-check" below).
check-sources downloads every year again (the monthly watch,
.github/workflows/price-history-watch.yml). release-check is the release
workflow's: the manifest is well formed, the newest 30 days still give
their fingerprint and pass the cross-check, and the history ends at most
14 days before the release commit (not for a package-only revision).
A request that fails (a timeout, 429 or 5xx) is tried twice more.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from backend.services import price_files as pf  # noqa: E402

BITFINEX_URL = "https://api-pub.bitfinex.com/v2/candles/trade:1h:tBTCUSD/hist"
KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"
BITFINEX_BLOCK = 10000  # hours per request

# Cross-check, measured on 2023-01 to 2026-10 (#144, session 6):
# Bitstamp vs Bitfinex, every hour: median gap 0.09%, worst 30-day median
# 0.26%, largest 1.12% (the USDC weekend, 12 March 2023); vs Kraken, the
# latest 720 hours: largest 0.05%. A price an hour off (the commonest
# mistake) moves the median gap less than the market does, so the gaps must
# also scatter less as they are than shifted by an hour. The scatter is
# taken around the median gap, so a steady premium at one exchange doesn't
# count: every two-week window since 2023 passes by 54% at least (every
# 30-day one by 62%).
CROSS_CHECK_FROM = pf.year_start(2023)  # Bitfinex traded at a premium before (5% in 2017)
MAX_GAP = Decimal("0.02")  # any one hour
MAX_MEDIAN = Decimal("0.005")
MIN_COVER = 0.95  # of our hours the other exchange must have
SHIFT_TEST_HOURS = 336  # hours compared before the shift test means something
NEWEST_HOURS = 720  # release-check: the newest 30 days
MAX_AGE_DAYS = 14
# Hours where both exchanges were right and still more than MAX_GAP apart (a
# real market event): label -> why. Added only in a pull request, with the
# owner's OK; the hour still counts in the median and the shift test.
EXCUSED_HOURS: dict[str, str] = {}
PAUSE = {"bitstamp": 0.2, "bitfinex": 2.5}  # seconds between requests (tests: 0)
RETRY_WAITS = (2.0, 10.0)  # before the second and third try (tests: 0)
TRANSIENT = {429, 500, 502, 503, 504}
ONLINE_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError)  # no answer, or not the answer expected


class PatientClient(httpx.AsyncClient):
    """A client that tries a request again after a timeout, a 429 or a 5xx."""

    async def get(self, url, **kwargs):
        for wait in (*RETRY_WAITS, None):
            try:
                resp = await super().get(url, **kwargs)
                if resp.status_code not in TRANSIENT or wait is None:
                    return resp
            except httpx.TransportError:
                if wait is None:
                    raise
            await asyncio.sleep(wait)


def _pause(site: str):
    async def wait():
        await asyncio.sleep(PAUSE[site])
    return wait


# Second sources
async def bitfinex_hours(client, first: int, last: int) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    start = first
    while start <= last:
        if out:
            await _pause("bitfinex")()
        end = min(start + (BITFINEX_BLOCK - 1) * pf.HOUR, last)
        resp = await client.get(BITFINEX_URL, params={
            "start": start * 1000, "end": end * 1000, "limit": BITFINEX_BLOCK, "sort": 1})
        resp.raise_for_status()
        out.update({int(row[0]) // 1000: Decimal(str(row[1])) for row in resp.json()})  # [ms, open, …]
        start = end + pf.HOUR
    return out


async def kraken_hours(client) -> dict[int, Decimal]:
    resp = await client.get(KRAKEN_URL, params={"pair": "XBTUSD", "interval": 60})
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError(str(data.get("error") if isinstance(data, dict) else data)[:200])
    pair = next((k for k in data["result"] if k != "last"), None)
    if pair is None:
        raise ValueError("Kraken's answer has no pair")
    return {int(row[0]): Decimal(str(row[1])) for row in data["result"][pair]}  # [time, open, …]


def compare(ours: dict[int, Decimal], theirs: dict[int, Decimal], name: str) -> list[str]:
    """What's wrong with our hours against another exchange's (empty: they agree)."""
    common = sorted(h for h in ours if h in theirs)
    if len(common) < MIN_COVER * len(ours):
        return [f"{name} has only {len(common)} of the {len(ours)} hours to compare"]
    gap = {h: abs(theirs[h] - ours[h]) / ours[h] for h in common}
    problems = []
    far = [h for h in common if gap[h] > MAX_GAP and pf.label(h) not in EXCUSED_HOURS]
    if far:
        h = far[0]
        problems.append(f"{len(far)} hours more than {MAX_GAP:.0%} from {name}, the first "
                        f"{pf.label(h)}: Bitstamp {ours[h]}, {name} {theirs[h]}")
    median = statistics.median(gap.values())
    if median > MAX_MEDIAN:
        problems.append(f"the median gap to {name} is {median:.3%}, over {MAX_MEDIAN:.1%}")
    if len(common) >= SHIFT_TEST_HOURS and _off_by_an_hour(ours, theirs, common):
        problems.append(f"Bitstamp's hours agree better with {name}'s shifted by an hour: a time is off")
    print(f"  {name}: {len(common)} hours, median gap {median:.3%}, largest {max(gap.values()):.3%}")
    return problems


def _scatter(ours, theirs, common, shift: int) -> Decimal | None:
    """How far the gaps stray from their median, with our hours shifted by `shift`."""
    gaps = [theirs[h] / ours[h + shift] - 1 for h in common if h + shift in ours]
    if not gaps:
        return None
    middle = statistics.median(gaps)
    return statistics.median(abs(g - middle) for g in gaps)


def _off_by_an_hour(ours, theirs, common) -> bool:
    aligned = _scatter(ours, theirs, common, 0)
    shifted = [_scatter(ours, theirs, common, s) for s in (pf.HOUR, -pf.HOUR)]
    return any(s is not None and s <= aligned for s in shifted)


async def cross_check(client, ours: dict[int, Decimal]) -> list[str]:
    """Our new hours (from 2023 on) against Bitfinex, and Kraken's latest 720."""
    if not ours:
        return []
    problems = []
    try:
        problems += compare(ours, await bitfinex_hours(client, min(ours), max(ours)), "Bitfinex")
    except ONLINE_ERRORS as exc:
        problems.append(f"Bitfinex didn't answer: {exc}")
    try:
        kraken = await kraken_hours(client)
    except ONLINE_ERRORS as exc:
        return problems + [f"Kraken didn't answer: {exc}"]
    window = {h: p for h, p in ours.items() if kraken and min(kraken) <= h <= max(kraken)}
    if window:
        problems += compare(window, kraken, "Kraken")
    return problems


# Commands
async def _year(client, year: int, last_hour: int) -> tuple[str, dict[int, Decimal]]:
    prices = await pf.download_year(client, year, last_hour, _pause("bitstamp"))
    return pf.year_text(prices, year, last_hour), prices


async def refresh(client, path: Path, now: float) -> int:
    lines = pf.read_manifest(path)
    if lines and (problems := pf.manifest_problems(lines, now)):
        return fail(problems)
    target = pf.last_complete_hour(now)
    old = lines[-1] if lines else None
    if old and old.last_hour >= target:
        print(f"Up to date: the history ends {pf.label(old.last_hour)}.")
        return 0
    try:
        new_lines, new_hours = await _new_lines(client, old, target)
    except (ChangedPast, *ONLINE_ERRORS) as exc:
        return fail([str(exc)])
    checked = {h: p for h, p in new_hours.items() if h >= CROSS_CHECK_FROM}
    print(f"New hours: {len(new_hours)}, to {pf.label(target)}; cross-checking {len(checked)}:")
    if problems := await cross_check(client, checked):
        return fail(problems)
    path.write_text(pf.manifest_text(lines[:-1] + new_lines), encoding="utf-8")
    for line in new_lines:
        print(f"  {line.year}: {line.hours} hours to {pf.label(line.last_hour)}, sha256 {line.sha256}")
    return 0


class ChangedPast(Exception):
    """Bitstamp's prices for hours already in the manifest changed."""


async def _new_lines(client, old: pf.YearLine | None, target: int):
    """The open year's line (and newer years') rebuilt to `target`, and the hours they add."""
    new_lines, new_hours = [], {}
    for year in range(old.year if old else pf.FIRST_YEAR, pf.year_of(target) + 1):
        last = min(pf.year_end(year), target)
        text, prices = await _year(client, year, last)
        since = pf.year_start(year)
        if old and old.year == year:
            if pf.fingerprint(pf.prefix(text, old.hours)) != old.sha256:
                raise ChangedPast(f"{year}: Bitstamp's prices for the hours already in the manifest "
                                  "changed (they no longer give its fingerprint)")
            since = old.last_hour + pf.HOUR
        new_hours.update({h: p for h, p in prices.items() if h >= since})
        new_lines.append(pf.line_for(year, text))
    return new_lines, new_hours


def verify(path: Path, now: float) -> int:
    lines = pf.read_manifest(path)
    problems = pf.manifest_problems(lines, now)
    for line in lines:  # the year files themselves, where the app ships them
        file = path.parent / f"{line.year}.csv"
        if file.exists() and pf.fingerprint(file.read_bytes().decode("utf-8")) != line.sha256:
            problems.append(f"{file.name} doesn't give its fingerprint")
    if problems:
        return fail(problems)
    print(f"The manifest is well formed: {lines[0].year}–{lines[-1].year}, to {pf.label(lines[-1].last_hour)}.")
    return 0


async def check_sources(client, path: Path, now: float, report: Path | None) -> int:
    lines = pf.read_manifest(path)
    if problems := pf.manifest_problems(lines, now):
        return fail(problems)
    changed, unanswered = [], []
    for line in lines:
        try:
            text, _ = await _year(client, line.year, line.last_hour)
        except httpx.HTTPError as exc:
            unanswered.append(_why(line.year, exc))
            continue
        except ONLINE_ERRORS as exc:  # an hour missing, or an answer of another shape
            changed.append(_why(line.year, exc))
            continue
        if pf.fingerprint(text) != line.sha256:
            changed.append(f"{line.year}: Bitstamp's prices no longer give the manifest's fingerprint")
    if report and (changed or unanswered):
        report.write_text(_watch_report(changed, unanswered), encoding="utf-8")
    if changed or unanswered:
        return fail(changed + unanswered)
    print("Bitstamp still gives every year's fingerprint.")
    return 0


def _watch_report(changed: list[str], unanswered: list[str]) -> str:
    """The watch issue: its title on the first line, then its body."""
    if changed:
        title = "Price history: Bitstamp's hourly prices no longer match the manifest"
        what = ("Installs whose download fails a year's check value that year at the day's price "
                "instead. Find out what changed (Bitstamp's API, a missing hour, a corrected past "
                "price), then decide "
                "in a pull request: never change a closed year's line without the owner's OK "
                "(backend/assets/btc_prices/README.md).")
    else:
        title = "Price history: the monthly check couldn't reach Bitstamp"
        what = ("Nothing is known to have changed. If the next run (or a run by hand: Actions → Price "
                "history watch → Run workflow) passes, close this; if Bitstamp keeps failing, installs "
                "can't download the history either.")
    items = "\n".join(f"- {p}" for p in changed + unanswered)
    return (f"{title}\n\nThe monthly check of the hourly price history (`scripts/price_history.py "
            f"check-sources`) found:\n\n{items}\n\n{what}\n\n— the price history watch\n")


async def release_check(client, path: Path, now: float, commit_time: float | None) -> int:
    lines = pf.read_manifest(path)
    if problems := pf.manifest_problems(lines, now):
        return fail(problems)
    last = lines[-1].last_hour
    if commit_time is not None and commit_time - last > MAX_AGE_DAYS * 86400:
        return fail([f"the history ends {pf.label(last)}, more than {MAX_AGE_DAYS} days before the release "
                     "commit: run `make prices` in a pull request into develop"])
    newest = set(range(last - (NEWEST_HOURS - 1) * pf.HOUR, last + pf.HOUR, pf.HOUR))
    years = {pf.year_of(h) for h in newest}
    prices: dict[int, Decimal] = {}
    for line in (y for y in lines if y.year in years):
        try:
            text, got = await _year(client, line.year, line.last_hour)
        except ONLINE_ERRORS as exc:
            return fail([_why(line.year, exc)])
        if pf.fingerprint(text) != line.sha256:
            return fail([f"{line.year}: Bitstamp's prices no longer give the manifest's fingerprint"])
        prices.update(got)
    print(f"The newest {len(newest)} hours give their fingerprint; cross-checking:")
    if problems := await cross_check(client, {h: prices[h] for h in newest if h >= CROSS_CHECK_FROM}):
        return fail(problems)
    return 0


def _why(year: int, exc: Exception) -> str:
    """A year's problem, named once (an IncompleteYear's message already names it)."""
    return str(exc) if isinstance(exc, pf.IncompleteYear) else f"{year}: {exc}"


def fail(problems: list[str]) -> int:
    print("✗ Price history: failed (nothing written).", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None, transport=None, now: float | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["refresh", "verify", "check-sources", "release-check"])
    parser.add_argument("--manifest", type=Path, default=pf.MANIFEST)
    parser.add_argument("--report", type=Path, help="check-sources: write the issue (title, body) here on a failure")
    parser.add_argument("--commit-time", type=float, help="release-check: the release commit's Unix time")
    parser.add_argument("--no-age-check", action="store_true", help="release-check: a package-only revision")
    args = parser.parse_args(argv)
    now = time.time() if now is None else now
    if args.command == "verify":
        return verify(args.manifest, now)
    return asyncio.run(_online(args, transport, now))


async def _online(args, transport, now: float) -> int:
    async with PatientClient(transport=transport, timeout=30.0) as client:
        if args.command == "refresh":
            return await refresh(client, args.manifest, now)
        if args.command == "check-sources":
            return await check_sources(client, args.manifest, now, args.report)
        commit_time = None if args.no_age_check else (args.commit_time or now)
        return await release_check(client, args.manifest, now, commit_time)


if __name__ == "__main__":
    sys.exit(main())
