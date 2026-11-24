"""
#964: a time typed in the transaction form is turned into a moment by
BitcoinTX's own timezone rules (the tzdata package), not the device's. The
form sends the time as typed and the device's zone (`typed_time`) beside the
moment the device worked out; the server works the moment out again and uses
its own. On a device whose rules predate a zone's change, the device's
moment is an hour off: British Columbia stays on summer time (UTC-7) from
1 November 2026, so 14:00 on 15 November is 21:00 UTC, where an older device
says 22:00. The owner's decision 4 on #972 (2026-11-14).
"""

from datetime import datetime

import pytest

from backend.schemas.transaction import TransactionCreate, TransactionUpdate

CLIENT = None


@pytest.fixture(autouse=True, scope="module")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


DEPOSIT = {"type": "Deposit", "from_account_id": 99, "to_account_id": 1, "amount": "100",
           "fee_amount": "0", "fee_currency": "USD", "source": "N/A"}
VANCOUVER = {"local": "2026-11-15T14:00", "zone": "America/Vancouver"}
OLD_DEVICE = "2026-11-15T22:00:00Z"  # 14:00 at UTC-8, as rules from before 2026 have it
RIGHT = "2026-11-15T21:00:00Z"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _saved(tx_id: int) -> str:
    return CLIENT.get(f"/api/transactions/{tx_id}").json()["timestamp"]


def test_an_out_of_date_devices_typed_time_is_saved_by_bitcointxs_rules():
    r = CLIENT.post("/api/transactions", json={**DEPOSIT, "timestamp": OLD_DEVICE, "typed_time": VANCOUVER})
    assert r.status_code == 200, r.text
    assert _utc(_saved(r.json()["id"])) == _utc(RIGHT)


def test_an_up_to_date_device_sees_no_change():
    r = CLIENT.post("/api/transactions", json={**DEPOSIT, "timestamp": RIGHT, "typed_time": VANCOUVER})
    assert _utc(_saved(r.json()["id"])) == _utc(RIGHT)


@pytest.mark.parametrize("local, moment", [
    ("2024-03-10T02:30", "2024-03-10T07:30:00Z"),  # the spring-forward gap: as a browser reads it
    ("2024-11-03T01:30", "2024-11-03T05:30:00Z"),  # the repeated hour: its first time, as a browser reads it
    ("2024-07-04T09:15:30", "2024-07-04T13:15:30Z"),  # seconds kept
])
def test_new_yorks_gap_and_repeated_hour_read_as_a_browser_reads_them(local, moment):
    created = TransactionCreate(**DEPOSIT, timestamp=moment, typed_time={"local": local, "zone": "America/New_York"})
    assert created.timestamp == _utc(moment)


def test_an_edit_reads_its_typed_time_too():
    tx_id = CLIENT.post("/api/transactions", json={**DEPOSIT, "timestamp": "2026-11-10T12:00:00Z"}).json()["id"]
    r = CLIENT.put(f"/api/transactions/{tx_id}", json={"timestamp": OLD_DEVICE, "typed_time": VANCOUVER})
    assert r.status_code == 200, r.text
    assert _utc(_saved(tx_id)) == _utc(RIGHT)


def test_an_edit_with_a_typed_time_alone_moves_to_it():
    update = TransactionUpdate(typed_time=VANCOUVER)
    assert update.timestamp == _utc(RIGHT)


def test_a_zone_the_package_doesnt_name_keeps_the_devices_moment():
    created = TransactionCreate(**DEPOSIT, timestamp=OLD_DEVICE, typed_time={**VANCOUVER, "zone": "Mars/Olympus"})
    assert created.timestamp == _utc(OLD_DEVICE)


def test_a_typed_time_is_never_stored():
    created = TransactionCreate(**DEPOSIT, timestamp=OLD_DEVICE, typed_time=VANCOUVER)
    assert "typed_time" not in created.model_dump()


@pytest.mark.parametrize("local", ["2026-11-15T14:00Z", "2026-11-15T14:00-08:00", "yesterday", "", "2026-11-15"])
def test_a_typed_time_that_isnt_a_wall_clock_time_is_refused(local):
    r = CLIENT.post("/api/transactions", json={**DEPOSIT, "timestamp": RIGHT, "typed_time": {**VANCOUVER, "local": local}})
    assert r.status_code == 422, r.text
    assert "typed_time" in r.text


def test_the_coins_moved_routes_take_it():
    """They share the Save's body (#706): the list and the save can't disagree."""
    r = CLIENT.post("/api/transactions/coins-moved", json={
        **DEPOSIT, "type": "Transfer", "from_account_id": 4, "to_account_id": 2, "amount": "0.1",
        "fee_currency": "BTC", "source": None, "timestamp": OLD_DEVICE, "typed_time": VANCOUVER})
    assert r.status_code != 422, r.text
