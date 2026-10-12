"""
The hourly price history's year files and their manifest (#144, PR 1):
the format and fingerprints (backend/services/price_files.py) and the
script that keeps the manifest (scripts/price_history.py): a refresh that
refuses a gap, a changed past price, a price another exchange disagrees
with or an hour off, writing nothing; the monthly source check; the
release check. Every exchange is faked: no test touches the network.
"""

import importlib.util
import random
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from backend.services import price_files as pf

HOUR = pf.HOUR
D = Decimal

# Every closed year's fingerprint. A year is added here by hand, in the
# pull request that closes it (`make prices` in January), and a line never
# changes: past prices must not move unnoticed.
PINNED = {
    2013: "031289ceed324f1abb97608cf13648e2ae37fbc87dc0e11ed1dc5ef475360bba",
    2014: "72383a1ecbcd4ee4a50c5b51b7dd71115bd7a2e61a4fa69588c2959b45413cec",
    2015: "20d7ddb3e4fa851b9c12c8ca8adfc1a78d34360f2686536306035ab38dde7635",
    2016: "5ebba5cca8f6dffe9cad1b788253dd3e00be6a1d3d7e7816529a58fda2490eec",
    2017: "aca3090824a4155b56b00a7c635c2435ee74e8337910823ee1adad45ffab00f9",
    2018: "f38d82bfa746065cb5caaf4b986e1715a1ce2da3cb2b31414e2eda13f4d0dcf4",
    2019: "9f7241e1669927f3e44edecf770b798ec0e851d40b62dbf75cf6101904c01d46",
    2020: "79155839cbd75a9e768f0fcdbf1809c5bdde2e3cdf3862a4d312a2cef48b9058",
    2021: "34f3f895228c59f513151debf0673b053e1e79f517b9322990321cce0454d805",
    2022: "5e2635598b47c7ee98659a580ce389739d081263c0a6181a9775f0263da43780",
    2023: "4e53395d873e0eb577dc1ae5c90c86b4e2a19568f01fb752e3308b6ced5c0ac2",
    2024: "529f3e3109b4f8c818aeb6db32bf39b75def6d6b18dab3c6b6df5c42fc1c2b40",
    2025: "ba2caea590da986fadd971d4065acf7a49000c4c608ce1046c27e2ec3e8f739d",
}


def _script():
    spec = importlib.util.spec_from_file_location(
        "price_history_script", Path(__file__).resolve().parents[2] / "scripts" / "price_history.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _script()


def at(text: str) -> int:
    return pf.from_label(text)


# ---------------------------------------------------------------------------
# The manifest in the repo
# ---------------------------------------------------------------------------
def test_the_manifest_is_well_formed_and_every_closed_year_is_pinned():
    assert script.main(["verify"]) == 0
    lines = pf.read_manifest()
    assert lines[0].year == pf.FIRST_YEAR == 2013
    closed = {line.year: line.sha256 for line in lines if line.is_closed()}
    assert closed == PINNED, "a closed year changed, or a newly closed one isn't pinned above yet"
    assert not lines[-1].is_closed() or lines[-1].year in PINNED


# ---------------------------------------------------------------------------
# The year file
# ---------------------------------------------------------------------------
def test_a_year_file_is_one_row_per_hour_with_two_decimals():
    first = pf.year_start(2024)
    prices = {first: D("42283"), first + HOUR: D("42199.5"), first + 2 * HOUR: D("42010.07")}
    text = pf.year_text(prices, 2024, first + 2 * HOUR)
    assert text == ("hour_utc,usd\n2024-01-01T00:00Z,42283.00\n"
                    "2024-01-01T01:00Z,42199.50\n2024-01-01T02:00Z,42010.07\n")
    assert pf.prefix(text, 2) == "hour_utc,usd\n2024-01-01T00:00Z,42283.00\n2024-01-01T01:00Z,42199.50\n"
    line = pf.line_for(2024, text)
    assert (line.first_hour, line.last_hour, line.hours) == (first, first + 2 * HOUR, 3)
    assert line.sha256 == pf.fingerprint(text) and len(line.sha256) == 64
    assert pf.parse_year_text(text) == {h: D(pf.usd(p)) for h, p in prices.items()}
    assert pf.usd(D("1E+5")) == "100000.00"


def test_a_year_with_a_missing_hour_is_incomplete():
    first = pf.year_start(2024)
    with pytest.raises(pf.IncompleteYear, match="2024-01-01T01:00Z"):
        pf.year_text({first: D(1), first + 2 * HOUR: D(1)}, 2024, first + 2 * HOUR)


def test_a_year_is_asked_in_the_same_fixed_blocks_on_every_install():
    """No request depends on a ledger: 1,000 hours from 1 January 00:00 UTC, then the next 1,000."""
    starts = pf.block_starts(2024, pf.year_end(2024))
    assert starts[0] == pf.year_start(2024) and len(starts) == 9
    assert all(b - a == 1000 * HOUR for a, b in zip(starts, starts[1:]))
    world = Exchanges(market(2024, 2025), now=pf.year_start(2025))
    prices = pf_download(world, 2024, pf.year_end(2024))
    assert len(prices) == 8784
    assert [dict(httpx.URL(u).params) for u in world.requests] == [
        {"step": "3600", "limit": "1000", "start": str(s)} for s in starts]


def pf_download(world, year, last):
    import asyncio

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world.handler)) as client:
            return await pf.download_year(client, year, last)
    return asyncio.run(go())


# ---------------------------------------------------------------------------
# The script against fake exchanges
# ---------------------------------------------------------------------------
def market(first_year: int, last_year: int, seed: int = 7) -> dict[int, Decimal]:
    """A market that moves like Bitcoin's (about 0.4% an hour), every hour of the years."""
    rng, price, out = random.Random(seed), 60000.0, {}
    for h in range(pf.year_start(first_year), pf.year_start(last_year + 1), HOUR):
        out[h] = D(f"{price:.2f}")
        price *= 1 + rng.gauss(0, 0.004)
    return out


class Exchanges:
    """Bitstamp, Bitfinex (within 0.05% of it) and Kraken, faked; every request recorded."""

    def __init__(self, prices: dict[int, Decimal], now: float = 0):
        self.bitstamp = dict(prices)
        rng = random.Random(1)
        self.bitfinex = {h: D(f"{float(p) * (1 + rng.gauss(0, 0.0005)):.2f}") for h, p in prices.items()}
        self.kraken = dict(prices)
        self.now, self.down, self.requests = now, set(), []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        host, params = request.url.host, request.url.params
        if host in self.down:
            return httpx.Response(503)
        current = int(self.now) // HOUR * HOUR
        if host == "www.bitstamp.net":
            start = int(params["start"])
            rows = [{"timestamp": str(h), "open": str(self.bitstamp[h])}
                    for h in range(start, min(start + 1000 * HOUR, current + HOUR), HOUR) if h in self.bitstamp]
            return httpx.Response(200, json={"data": {"pair": "BTC/USD", "ohlc": rows}})
        if host == "api-pub.bitfinex.com":
            lo, hi = int(params["start"]) // 1000, int(params["end"]) // 1000
            rows = [[h * 1000, float(self.bitfinex[h]), 0, 0, 0, 1] for h in range(lo, hi + HOUR, HOUR)
                    if h in self.bitfinex]
            return httpx.Response(200, json=rows)
        if host == "api.kraken.com":
            rows = [[h, str(self.kraken[h]), "0", "0", "0", "0", "0", 1]
                    for h in range(current - 719 * HOUR, current + HOUR, HOUR) if h in self.kraken]
            return httpx.Response(200, json={"error": [], "result": {"XXBTZUSD": rows, "last": current}})
        return httpx.Response(404)


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A history from 2025 (as if it were the first year), a fresh manifest file, no pauses."""
    monkeypatch.setattr(pf, "FIRST_YEAR", 2025)
    monkeypatch.setattr(script, "PAUSE", {"bitstamp": 0, "bitfinex": 0})
    w = Exchanges(market(2025, 2026))
    w.manifest = tmp_path / "MANIFEST.csv"
    return w


def run(world, *args, now: str) -> int:
    world.now = at(now) + 1800  # half past the hour
    world.requests.clear()
    return script.main([*args, "--manifest", str(world.manifest)],
                       transport=httpx.MockTransport(world.handler), now=world.now)


def test_refresh_adds_the_new_hours_and_keeps_the_rest(world):
    assert run(world, "refresh", now="2026-02-01T00:00Z") == 0
    first = pf.read_manifest(world.manifest)
    assert [(y.year, y.hours) for y in first] == [(2025, 8760), (2026, 744)]
    assert run(world, "refresh", now="2026-03-15T00:00Z") == 0
    second = pf.read_manifest(world.manifest)
    assert second[0] == first[0]
    assert second[1].last_hour == at("2026-03-14T23:00Z") and second[1].hours == 744 + 672 + 14 * 24
    hosts = {httpx.URL(u).host for u in world.requests}
    assert hosts == {"www.bitstamp.net", "api-pub.bitfinex.com", "api.kraken.com"}
    assert run(world, "refresh", now="2026-03-15T00:00Z") == 0  # up to date: asks nothing
    assert world.requests == []


def test_refresh_in_january_closes_the_old_year(world):
    assert run(world, "refresh", now="2025-12-01T00:00Z") == 0
    assert run(world, "refresh", now="2026-01-10T00:00Z") == 0
    lines = pf.read_manifest(world.manifest)
    assert [(y.year, y.hours, y.is_closed()) for y in lines] == [(2025, 8760, True), (2026, 9 * 24, False)]


def one_hour_off(w):
    w.bitstamp[at("2026-03-01T12:00Z")] *= D("1.025")


def a_missing_hour(w):
    del w.bitstamp[at("2026-03-01T12:00Z")]


def a_changed_past_price(w):
    w.bitstamp[at("2026-01-15T12:00Z")] += D("0.01")


def every_new_hour_an_hour_late(w):
    true = market(2025, 2026)
    for h in range(at("2026-02-01T00:00Z"), at("2026-03-15T00:00Z"), HOUR):
        w.bitstamp[h] = true[h - HOUR]


def bitfinex_down(w):
    w.down.add("api-pub.bitfinex.com")


def kraken_down(w):
    w.down.add("api.kraken.com")


def bitfinex_half_a_percent_higher(w):
    w.bitfinex = {h: p * D("1.006") for h, p in w.bitfinex.items()}


@pytest.mark.parametrize("break_it, says", [
    (one_hour_off, "more than 2% from Bitfinex, the first 2026-03-01T12:00Z"),
    (a_missing_hour, "1 hours missing, the first 2026-03-01T12:00Z"),
    (a_changed_past_price, "2026: Bitstamp's prices for the hours already in the manifest changed"),
    (every_new_hour_an_hour_late, "agree better with Bitfinex's shifted by an hour"),
    (bitfinex_down, "Bitfinex didn't answer"),
    (kraken_down, "Kraken didn't answer"),
    (bitfinex_half_a_percent_higher, "the median gap to Bitfinex"),
])
def test_refresh_refuses_and_writes_nothing(world, capsys, break_it, says):
    assert run(world, "refresh", now="2026-02-01T00:00Z") == 0
    before = world.manifest.read_bytes()
    break_it(world)
    capsys.readouterr()
    assert run(world, "refresh", now="2026-03-15T00:00Z") == 1
    assert says in capsys.readouterr().err
    assert world.manifest.read_bytes() == before


def test_check_sources_names_a_year_bitstamp_changed(world, tmp_path, capsys):
    assert run(world, "refresh", now="2026-03-15T00:00Z") == 0
    assert run(world, "check-sources", now="2026-04-01T00:00Z") == 0
    world.bitstamp[at("2025-06-01T00:00Z")] += D("1")
    report = tmp_path / "report.md"
    assert run(world, "check-sources", "--report", str(report), now="2026-04-01T00:00Z") == 1
    assert "2025: Bitstamp's prices no longer give the manifest's fingerprint" in report.read_text()
    assert "2026" not in capsys.readouterr().err


def test_the_release_check_refuses_a_stale_history(world, capsys):
    assert run(world, "refresh", now="2026-03-15T00:00Z") == 0
    commit = str(at("2026-03-20T00:00Z"))
    assert run(world, "release-check", "--commit-time", commit, now="2026-03-21T00:00Z") == 0
    late = str(at("2026-03-30T00:00Z"))
    assert run(world, "release-check", "--commit-time", late, now="2026-03-31T00:00Z") == 1
    assert "run `make prices`" in capsys.readouterr().err
    # a package-only revision ships the history it had
    assert run(world, "release-check", "--no-age-check", now="2026-03-31T00:00Z") == 0
    world.bitstamp[at("2026-03-10T00:00Z")] += D("1")
    assert run(world, "release-check", "--no-age-check", now="2026-03-31T00:00Z") == 1


def test_verify_catches_a_bad_line_and_a_year_file_that_doesnt_match(world, capsys):
    assert run(world, "refresh", now="2026-03-15T00:00Z") == 0
    (world.manifest.parent / "2025.csv").write_text("hour_utc,usd\n", encoding="utf-8")
    assert run(world, "verify", now="2026-03-15T00:00Z") == 1
    assert "2025.csv doesn't give its fingerprint" in capsys.readouterr().err
    (world.manifest.parent / "2025.csv").unlink()
    world.manifest.write_text(world.manifest.read_text().replace(",8760,", ",8759,"), encoding="utf-8")
    assert run(world, "verify", now="2026-03-15T00:00Z") == 1
    assert "2025: hours doesn't match" in capsys.readouterr().err
