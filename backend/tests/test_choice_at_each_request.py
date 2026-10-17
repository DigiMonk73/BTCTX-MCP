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

from backend.services import bitcoin, outbound

# The real functions, captured before the session fixture stubs them.
from backend.services.bitcoin import get_current_price as real_current_price
from backend.services.price_history import find_prices as real_find_prices

TOR = "socks5h://127.0.0.1:9050"
NODE = "http://umbrel.local:3006"
ONION = "http://mempoolabcdefghijklmnopqrstuvwxyz234567abcdefghijklmnop.onion"
PUBLIC_THROUGH_TOR = outbound.NetworkSettings(price_source="public", proxy_url=TOR)
NOBODY = outbound.NetworkSettings(price_source="off")


@pytest.fixture
def sent(monkeypatch):
    """Every request sent, as (host, proxy taken), each answered 503; `then`
    runs at the first request to a host, standing for a save landing while
    it's under way."""
    requests, then = [], {}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        requests.append((host, request.extensions.get(outbound.PROXY_TAG)))
        if host in then:
            then.pop(host)()
        return httpx.Response(503)

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(outbound, "_current", outbound.current())  # put back afterwards
    bitcoin._price_cache.update(settings=None)
    yield requests, then
    bitcoin._price_cache.update(settings=None)


def in_use(settings: outbound.NetworkSettings):
    """A save of `settings`: what load() leaves in memory."""
    def save():
        outbound._current = settings
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


@pytest.mark.parametrize("saved", [
    NOBODY,
    outbound.NetworkSettings(price_source="public"),  # public sites, no proxy
    outbound.NetworkSettings(price_source="public", proxy_url="socks5h://127.0.0.1:9150"),  # another Tor
], ids=["nobody", "no proxy", "another proxy"])
def test_a_public_sites_client_sends_nothing_the_settings_in_use_dont_allow(sent, saved):
    requests, _ = sent
    outbound._current = PUBLIC_THROUGH_TOR
    for client_for in (outbound.async_client, outbound.history_client):

        async def made_then_saved():
            async with client_for() as client:
                assert (await client.get("https://www.bitstamp.net/api/v2/ticker/btcusd/")).status_code == 503
                outbound._current = saved
                await client.get("https://api.kraken.com/0/public/Ticker?pair=XBTUSD")

        outbound._current = PUBLIC_THROUGH_TOR
        with pytest.raises(outbound.ChoiceChanged):
            asyncio.run(made_then_saved())
    assert requests == [("www.bitstamp.net", TOR)] * 2  # each client's request before the save, through Tor


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


def test_the_live_price_asked_while_nobody_is_saved_asks_no_more_sites(sent):
    """Kraken is asked through Tor; Nobody is saved meanwhile: Bitstamp
    isn't asked, and the answer says no price is asked (503), as it would
    after the save."""
    requests, then = sent
    outbound._current = PUBLIC_THROUGH_TOR
    then["api.kraken.com"] = in_use(NOBODY)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(real_current_price())
    assert refused.value.status_code == 503
    assert requests == [("api.kraken.com", TOR)]
