"""
A Sell edited through proceeds_usd is checked with the proceeds it sends
(#458). The edit stores proceeds_usd as the Sell's new gross, but the check
saw the stored gross: {"proceeds_usd": null} saved a $0 sale (its whole
basis a loss), and proceeds below a USD fee were kept, the net clamped to $0.
A create, and proceeds below the fee sent as gross_proceeds_usd (the form's),
were refused; {"gross_proceeds_usd": null} was saved, its gross made up
again from the stored net and the fee, and proceeds_usd beside a blank
gross was saved as the net, the fee added on top.
"""

import pytest

BANK, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 3, 4, 99
NO_PROCEEDS = "A sell needs its proceeds"
FEE_OVER = "The sell's fee is more than its proceeds."


@pytest.fixture(autouse=True)
def bought(auth_client):
    """1 BTC bought for $30,000 on the exchange, the issue's ledger."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    for body in (
        dict(type="Deposit", timestamp="2024-02-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2024-03-01T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="1", cost_basis_usd="30000", fee_amount="0", fee_currency="USD"),
    ):
        assert auth_client.post("/api/transactions", json=body).status_code == 200
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def sell(client, amount: str, gross: str, fee: str) -> dict:
    r = client.post("/api/transactions", json=dict(
        type="Sell", timestamp="2024-04-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
        amount=amount, gross_proceeds_usd=gross, fee_amount=fee, fee_currency="USD"))
    assert r.status_code == 200, r.text
    return r.json()


def spend(client, gross: str) -> dict:
    r = client.post("/api/transactions", json=dict(
        type="Withdrawal", timestamp="2024-04-01T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXTERNAL,
        amount="0.1", fee_amount="0", fee_currency="BTC", purpose="Spent", proceeds_usd=gross))
    assert r.status_code == 200, r.text
    return r.json()


def refused(r, text: str) -> None:
    assert r.status_code == 422, (r.status_code, r.text)
    assert text in r.text, r.text


def unchanged(client, before: dict) -> None:
    after = client.get(f"/api/transactions/{before['id']}").json()
    for key in ("type", "gross_proceeds_usd", "proceeds_usd", "fee_amount", "realized_gain_usd"):
        assert after[key] == before[key], (key, after[key], before[key])


def test_blank_proceeds_on_a_sell_are_refused(auth_client):
    """{"proceeds_usd": null} was saved: gross blank, proceeds $0, gain -$15,000."""
    before = sell(auth_client, "0.5", "35000", "7.72")
    assert before["realized_gain_usd"] == "19992.28"
    refused(auth_client.put(f"/api/transactions/{before['id']}", json={"proceeds_usd": None}), NO_PROCEEDS)
    unchanged(auth_client, before)


@pytest.mark.parametrize("proceeds", ["5", "0"])
def test_proceeds_below_a_sells_fee_are_refused(auth_client, proceeds):
    """{"proceeds_usd": "5"} on a Sell with a $10 fee was saved, its net clamped to $0."""
    before = sell(auth_client, "0.1", "500", "10")
    refused(auth_client.put(f"/api/transactions/{before['id']}", json={"proceeds_usd": proceeds}), FEE_OVER)
    unchanged(auth_client, before)


def test_the_same_edit_as_gross_proceeds_is_refused_too(auth_client):
    """A blank gross was saved: the stored net, $490, stood in for it, and
    the gross was made up again from it (with a new $20 fee, $510)."""
    before = sell(auth_client, "0.1", "500", "10")
    refused(auth_client.put(f"/api/transactions/{before['id']}", json={"gross_proceeds_usd": "5"}), FEE_OVER)
    for blank in ({"gross_proceeds_usd": None}, {"gross_proceeds_usd": None, "fee_amount": "20"}):
        refused(auth_client.put(f"/api/transactions/{before['id']}", json=blank), NO_PROCEEDS)
    unchanged(auth_client, before)


@pytest.mark.parametrize("change, text", [
    ({"proceeds_usd": None}, NO_PROCEEDS),
    ({"proceeds_usd": "5", "fee_amount": "10", "fee_currency": "USD"}, FEE_OVER),
])
def test_a_spend_changed_into_a_sell_is_checked_with_the_proceeds_sent(auth_client, change, text):
    """A type change keeps a spend's gross for the Sell: the check saw that
    $500, the save stored the proceeds sent."""
    before = spend(auth_client, "500")
    r = auth_client.put(f"/api/transactions/{before['id']}", json={
        "type": "Sell", "from_account_id": EXCH_BTC, "to_account_id": EXCH_USD, **change})
    refused(r, text)
    unchanged(auth_client, before)


def test_proceeds_sent_on_a_sell_still_become_its_gross(auth_client):
    """A valid proceeds edit saves as before: the new gross, net of the fee."""
    before = sell(auth_client, "0.1", "500", "10")
    r = auth_client.put(f"/api/transactions/{before['id']}", json={"proceeds_usd": "600"})
    assert r.status_code == 200, r.text
    assert (r.json()["gross_proceeds_usd"], r.json()["proceeds_usd"]) == ("600.00", "590.00")
    assert r.json()["realized_gain_usd"] == "-2410.00"  # 590 less 0.1 of the $30,000 buy


@pytest.mark.parametrize("body, gross, net", [
    ({"gross_proceeds_usd": "700"}, "700.00", "690.00"),
    ({"proceeds_usd": "800", "gross_proceeds_usd": "800"}, "800.00", "790.00"),
])
def test_the_forms_and_the_connectors_edits_save_as_before(auth_client, body, gross, net):
    """The form sends gross_proceeds_usd; the AI connector sends proceeds_usd
    with the same value as gross_proceeds_usd (_complete_for_server_rules)."""
    before = sell(auth_client, "0.1", "500", "10")
    r = auth_client.put(f"/api/transactions/{before['id']}", json=body)
    assert r.status_code == 200, r.text
    assert (r.json()["gross_proceeds_usd"], r.json()["proceeds_usd"]) == (gross, net)


def test_proceeds_beside_a_blank_gross_are_the_gross_as_on_a_create(auth_client):
    """{"gross_proceeds_usd": null, "proceeds_usd": "15"} was saved with $15
    as the net and $25 as the gross; a create of the same takes $15 as the
    gross, $5 net of the $10 fee."""
    body = {"gross_proceeds_usd": None, "proceeds_usd": "15"}
    created = auth_client.post("/api/transactions", json=dict(
        type="Sell", timestamp="2024-04-02T12:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
        amount="0.1", fee_amount="10", fee_currency="USD", **body)).json()
    edited = auth_client.put(f"/api/transactions/{sell(auth_client, '0.1', '500', '10')['id']}", json=body)
    assert edited.status_code == 200, edited.text
    for tx in (created, edited.json()):
        assert (tx["gross_proceeds_usd"], tx["proceeds_usd"]) == ("15.00", "5.00")


def test_a_spend_changed_into_a_sell_with_proceeds_sent_saves_them(auth_client):
    """The proceeds sent are the Sell's gross, net of its new USD fee."""
    before = spend(auth_client, "500")
    r = auth_client.put(f"/api/transactions/{before['id']}", json={
        "type": "Sell", "from_account_id": EXCH_BTC, "to_account_id": EXCH_USD,
        "proceeds_usd": "450", "fee_amount": "10", "fee_currency": "USD"})
    assert r.status_code == 200, r.text
    assert (r.json()["gross_proceeds_usd"], r.json()["proceeds_usd"]) == ("450.00", "440.00")
