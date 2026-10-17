"""
A price lookup can outlast a save of Settings -> Privacy & network: it may
wait for the owner's Mempool for up to a minute and a half. Each request is
sent only as the settings in use when it's sent allow (#437): never to a
public site once they aren't allowed, never through another proxy than the
one in use (none, around Tor), never to a Mempool address no longer chosen,
and never an .onion's name to the system's resolver. A request the choice
no longer allows is refused before it's sent (outbound.ChoiceChanged).
"""

import asyncio
from datetime import date

import httpx
import pytest
from fastapi import HTTPException

from backend.services import bitcoin, outbound, price_history, price_status

# The real functions, captured before the session fixture stubs them.
from backend.services.bitcoin import get_current_price as real_current_price
from backend.services.price_history import find_prices as real_find_prices

TOR = "socks5h://127.0.0.1:9050"
NODE = "http://umbrel.local:3006"
ONION = "http://mempoolabcdefghijklmnopqrstuvwxyz234567abcdefghijklmnop.onion"
PUBLIC_THROUGH_TOR = outbound.NetworkSettings(price_source="public", proxy_url=TOR)
PUBLIC_NO_PROXY = outbound.NetworkSettings(price_source="public")
NOBODY = outbound.NetworkSettings(price_source="off")
MEMPOOL_NO_BACKUP = outbound.NetworkSettings(price_source="mempool", mempool_url=NODE)
TRY_AGAIN = "The price settings changed while BitcoinTX was asking: try again."


@pytest.fixture
def sent(monkeypatch):
    """Every request sent, as (host, proxy taken), each answered 503; `then`
    runs at the first request to a host, standing for a save landing while
    it's under way (the answer it gives, if any, is that request's)."""
    requests, then = [], {}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        requests.append((host, request.extensions.get(outbound.PROXY_TAG)))
        answer = then.pop(host)() if host in then else None
        return answer or httpx.Response(503)

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(outbound, "_current", outbound.current())  # put back afterwards
    bitcoin._price_cache.update(settings=None)
    yield requests, then
    bitcoin._price_cache.update(settings=None)


def in_use(settings: outbound.NetworkSettings, answer: httpx.Response | None = None):
    """A save of `settings`: what load() leaves in memory."""
    def save():
        outbound._current = settings
        return answer
    return save


async def _get(client_for, url: str) -> int:
    async with client_for() as client:
        return (await client.get(url)).status_code


def test_a_save_while_the_mempool_is_awaited_leaves_no_public_site_asked(sent):
    """The issue's probe: a price lookup with the Mempool and public sites
    as its backup, through Tor; Nobody, with no proxy, is saved while the
    Mempool is awaited. Bitstamp was asked directly."""
    requests, then = sent
    outbound._current = outbound.NetworkSettings(
        price_source="mempool", mempool_url=NODE, mempool_fallback=True, proxy_url=TOR)
    then["umbrel.local"] = in_use(NOBODY)
    asyncio.run(real_find_prices(date(2024, 1, 10), full=True))
    assert requests == [("umbrel.local", None)]  # the Mempool, on the home network, and nothing after


@pytest.mark.parametrize("made, saved", [
    (PUBLIC_THROUGH_TOR, NOBODY),
    (PUBLIC_THROUGH_TOR, PUBLIC_NO_PROXY),
    (PUBLIC_THROUGH_TOR, outbound.NetworkSettings(price_source="public", proxy_url="socks5h://127.0.0.1:9150")),
    # Tor set: a client made without a proxy never goes around it
    (PUBLIC_NO_PROXY, PUBLIC_THROUGH_TOR),
], ids=["nobody", "no proxy", "another proxy", "tor set"])
def test_a_public_sites_client_sends_nothing_the_settings_in_use_dont_allow(sent, made, saved):
    requests, _ = sent
    for client_for in (outbound.async_client, outbound.history_client):

        async def made_then_saved():
            async with client_for() as client:
                assert (await client.get("https://www.bitstamp.net/api/v2/ticker/btcusd/")).status_code == 503
                outbound._current = saved
                await client.get("https://api.kraken.com/0/public/Ticker?pair=XBTUSD")

        outbound._current = made
        with pytest.raises(outbound.ChoiceChanged):
            asyncio.run(made_then_saved())
    assert requests == [("www.bitstamp.net", made.proxy_url)] * 2  # each client's request before the save


def test_a_public_sites_client_goes_on_while_the_choice_holds(sent):
    """A save that keeps public sites through the same proxy (another
    choice's record, say) stops nothing."""
    requests, _ = sent
    outbound._current = PUBLIC_THROUGH_TOR
    assert asyncio.run(_get(outbound.async_client, "https://api.kraken.com/")) == 503
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=NODE,
                                                 mempool_fallback=True, proxy_url=TOR)
    assert asyncio.run(_get(outbound.async_client, "https://api.kraken.com/")) == 503
    assert requests == [("api.kraken.com", TOR)] * 2


def test_an_own_mempools_client_never_sends_an_onion_name_around_tor(sent):
    """A client made for an .onion Mempool through Tor; then a Mempool on the
    home network, with no proxy, is saved: the .onion isn't asked (directly,
    the system's resolver would see its name), nor any address but the
    chosen Mempool's."""
    requests, _ = sent
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=ONION, proxy_url=TOR)

    async def made_then_saved():
        async with outbound.own_node_client() as client:
            with pytest.raises(outbound.ChoiceChanged):
                await client.get("https://api.kraken.com/")  # not the chosen Mempool
            assert (await client.get(ONION + "/api/v1/prices")).status_code == 503
            outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=NODE)
            with pytest.raises(outbound.ChoiceChanged):
                await client.get(ONION + "/api/v1/prices")

    asyncio.run(made_then_saved())
    assert requests == [(httpx.URL(ONION).host, TOR)]


@pytest.mark.parametrize("saved, answer", [
    (NOBODY, (503, "You chose Nobody for prices, so none is asked.")),  # as it would be after the save
    (PUBLIC_NO_PROXY, (502, TRY_AGAIN)),
    # Not "Your Mempool didn't answer": it wasn't asked
    (MEMPOOL_NO_BACKUP, (502, TRY_AGAIN)),
], ids=["nobody", "no proxy", "mempool, no backup"])
def test_the_live_price_asked_while_a_choice_is_saved_asks_no_more_sites(sent, saved, answer):
    """Kraken is asked through Tor; another choice is saved meanwhile:
    Bitstamp isn't asked, and the status line reports no failure."""
    requests, then = sent
    outbound._current = PUBLIC_THROUGH_TOR
    then["api.kraken.com"] = in_use(saved)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(real_current_price())
    assert (refused.value.status_code, refused.value.detail.split(" To change")[0]) == answer
    assert requests == [("api.kraken.com", TOR)]
    assert price_status.status()["last_problem"] is None


def test_the_live_price_from_a_mempool_no_longer_chosen_isnt_asked(sent, monkeypatch):
    """A save of another Mempool address lands as the live price's client
    for the old one is made: the old one isn't asked, and the status line
    doesn't say a Mempool failed."""
    requests, _ = sent
    outbound._current = MEMPOOL_NO_BACKUP
    real_client = outbound.own_node_client

    def made_then_saved(timeout=None):
        client = real_client(timeout)
        outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url="http://umbrel.local:3007")
        return client

    monkeypatch.setattr(outbound, "own_node_client", made_then_saved)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(real_current_price())
    assert (refused.value.status_code, refused.value.detail) == (502, TRY_AGAIN)
    assert requests == []
    status = price_status.status()
    assert (status["last_problem"], status["last_mempool_problem"]) == (None, None)


@pytest.mark.parametrize("made, saved", [
    (outbound.NetworkSettings(price_source="mempool", mempool_url=ONION, proxy_url=TOR),
     outbound.NetworkSettings(price_source="mempool", mempool_url=ONION, proxy_url="socks5h://127.0.0.1:9150")),
    # The home server's root the owner trusted (#188), then forgot
    (outbound.NetworkSettings(price_source="mempool", mempool_url=NODE, mempool_root="the root trusted"),
     MEMPOOL_NO_BACKUP),
], ids=["another proxy", "root forgotten"])
def test_an_own_mempools_client_stops_when_its_proxy_or_trusted_root_changes(sent, made, saved):
    requests, _ = sent

    async def made_then_saved():
        async with outbound.own_node_client() as client:
            assert (await client.get(made.mempool_url + "/api/v1/prices")).status_code == 503
            outbound._current = saved
            with pytest.raises(outbound.ChoiceChanged):
                await client.get(made.mempool_url + "/api/v1/prices")

    outbound._current = made
    asyncio.run(made_then_saved())
    assert requests == [(httpx.URL(made.mempool_url).host, made.proxy_url)]


def test_the_mempools_history_a_save_stopped_is_asked_again_at_once(sent, monkeypatch):
    """The trusted root forgotten as the Mempool's history is about to be
    asked (#188): it isn't asked with the old root, and the next lookup asks
    the same Mempool at once, not RETRY_SECONDS later."""
    requests, _ = sent
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=NODE, mempool_root="a root")
    real_client = outbound.own_node_client

    def made_then_saved(timeout=None):
        client = real_client(timeout)
        outbound._current = MEMPOOL_NO_BACKUP
        return client

    monkeypatch.setattr(outbound, "own_node_client", made_then_saved)
    assert asyncio.run(price_history.own_node_rows()) == ([], False)
    assert requests == []
    monkeypatch.setattr(outbound, "own_node_client", real_client)
    asyncio.run(price_history.own_node_rows())
    assert requests == [("umbrel.local", None)]


def test_the_live_price_whose_mempool_a_save_cleared_says_try_again(sent, monkeypatch):
    """Public sites saved (no Mempool now) just before the live price's
    client for the Mempool is made: nothing sent, "try again", and no
    Mempool problem on the status line (the third re-check of #443)."""
    requests, _ = sent
    outbound._current = MEMPOOL_NO_BACKUP
    real_client = outbound.own_node_client

    def saved_then_made(timeout=None):
        outbound._current = PUBLIC_NO_PROXY
        return real_client(timeout)

    monkeypatch.setattr(outbound, "own_node_client", saved_then_made)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(real_current_price())
    assert (refused.value.status_code, refused.value.detail) == (502, TRY_AGAIN)
    assert requests == []
    assert price_status.status()["last_mempool_problem"] is None


def test_a_mempool_address_saved_before_odd_hosts_were_refused_is_never_asked(sent):
    """An address whose host httpx keeps as typed ("….onion\\"), saved
    before _clean_url refused it, is read as stored: never asked, its name
    never to the resolver, with Tor set or not (the review of #443)."""
    requests, _ = sent
    outbound._current = outbound.NetworkSettings(price_source="mempool", mempool_url=ONION + "\\", proxy_url=TOR)
    with pytest.raises(RuntimeError, match="save it again"):
        asyncio.run(_get(outbound.own_node_client, ONION + "\\/api/v1/prices"))
    assert requests == []


@pytest.mark.parametrize("full", [True, False], ids=["whole history", "latest days"])
def test_a_history_download_a_save_stopped_is_asked_again_as_the_new_choice_says(sent, full):
    """Tor is set while the daily history comes in through no proxy (its
    first block, or Bitstamp's latest days, answered): the rest isn't asked
    around Tor, and the next lookup asks again at once, through it, not
    RETRY_SECONDS later (a save is no failure)."""
    requests, then = sent
    outbound._current = PUBLIC_NO_PROXY
    then["www.bitstamp.net"] = in_use(PUBLIC_THROUGH_TOR, httpx.Response(200, json={"data": {"ohlc": []}}))
    assert asyncio.run(price_history.public_history(full)) == ({}, False)
    assert requests == [("www.bitstamp.net", None)]  # the second block, or Kraken, not asked
    asyncio.run(price_history.public_history(full))
    assert requests[1] == ("www.bitstamp.net", TOR)
