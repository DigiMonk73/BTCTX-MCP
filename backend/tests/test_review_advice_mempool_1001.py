"""
#1001: #966 made Ledger Review's advice for a value left blank or $0 say to
type it when BitcoinTX asks no one for prices. The Edit form says so in two
more cases, with your own Mempool chosen and no backup: Mempool not
installed on this server yet (asked of no one), and an hour before your
Mempool began recording (it has no price for it). The review said "clear it
to use that hour's price" in both; it now says what the form says.
"""

import pytest

from backend.services import outbound, review

ADVISED = ("income_without_value", "gift_without_value", "zero_proceeds_spend")
MEMPOOL = "http://mempool.local"


def _actions(monkeypatch, **settings) -> dict[str, str]:
    monkeypatch.setattr(outbound, "current", lambda: outbound.NetworkSettings(**settings))
    return {key: review.advice(key) for key in ADVISED}


def test_your_mempool_not_installed_without_its_backup_says_to_type_the_value(monkeypatch):
    for key, action in _actions(monkeypatch, price_source="mempool").items():
        assert "only if BitcoinTX already has that hour's price" in action, (key, action)
        assert action.endswith("since Mempool isn't installed on this server yet."), (key, action)
        assert "to use that hour's price" not in action, (key, action)


def test_your_mempool_alone_says_an_older_hour_is_typed(monkeypatch):
    """Clearing uses your Mempool's price where it has one; for an hour
    before it began recording, the form's own words."""
    for key, action in _actions(monkeypatch, price_source="mempool", mempool_url=MEMPOOL).items():
        assert action == f"{review.CHECKS[key][1]} {review.MEMPOOL_ALONE}", (key, action)
    assert review.MEMPOOL_ALONE == ("Your Mempool has prices only from when it began recording: for an older hour,"
                                    " unless BitcoinTX already has its price, type the value.")


@pytest.mark.parametrize("url", [MEMPOOL, None])
def test_your_mempool_with_its_backup_keeps_the_advice(monkeypatch, url):
    """With its backup, public sites give the hours your Mempool hasn't, or
    all of them until it's installed."""
    for key, action in _actions(monkeypatch, price_source="mempool", mempool_url=url, mempool_fallback=True).items():
        assert action == review.CHECKS[key][1], (key, action)


def test_a_command_without_the_servers_settings_keeps_the_advice(monkeypatch):
    """`cli review` without the server's settings (#461) can't tell what the
    app asks: CHECKS' own advice, as under #966."""
    for settings in ({"mempool_url": MEMPOOL}, {}):
        actions = _actions(monkeypatch, price_source="mempool", server_settings_missing="BTCTX_PRICE_SOURCE",
                           **settings)
        assert actions == {key: review.CHECKS[key][1] for key in ADVISED}


def test_another_checks_advice_is_its_own(monkeypatch):
    monkeypatch.setattr(outbound, "current", lambda: outbound.NetworkSettings(price_source="mempool"))
    assert review.advice("income_value_off") == review.CHECKS["income_value_off"][1]
