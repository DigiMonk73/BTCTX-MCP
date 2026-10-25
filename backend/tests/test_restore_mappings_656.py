"""
What a restore does with the exchange import's saved mappings (#656). They
are the owner's tools, neither this install's own (the login, the AI key, the
price choice a restore keeps) nor the ledger's (nothing in it names one): a
restore loses none. This install's stay, the backup's are added unless one
here has the name, and no mapping id handed out here is handed out again.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.exchange_mappings import NO_MORE_IDS
from backend.tests.test_exchange_import_567_own import MAPPING, own
from backend.tests.test_restore_and_saves import _browser, _once_rebuilt
from backend.tests.test_restore_checks import (  # noqa: F401  (live: fixture)
    OWNER, REFERENCE_1X, _backup, _restore, _sealed, live,
)

URL = "/api/import/exchange/mappings"


def _save(client, name: str, **change) -> str:
    r = client.post(URL, json={**MAPPING, **change, "name": name})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _in_backup(last_id: int, mappings: dict[str, dict]) -> str:
    """The SQL that gives the backup's install these mappings (by id: their fields over MAPPING's)."""
    stored = json.dumps({"last_id": last_id, "mappings": {i: {**MAPPING, **m} for i, m in mappings.items()}})
    return f"INSERT INTO app_settings (key, value) VALUES ('import_mappings', '{stored}')"


def _restored(live, blob: bytes) -> TestClient:  # noqa: F811
    """Restore `blob`; a browser logged in afterwards (the restoring one logs in again)."""
    r = _restore(live.client, blob)
    assert r.status_code == 200, r.text
    browser = TestClient(app)
    assert browser.post("/api/login", json=OWNER).status_code == 200
    return browser


def _listed(client) -> list[tuple[str, str]]:
    return [(m["id"], m["name"]) for m in own(client)]


def test_a_mapping_saved_since_stays_beside_the_backups(live, tmp_path):  # noqa: F811
    assert _save(live.client, "Made here") == "own-1"
    blob, _ = _backup(tmp_path, _in_backup(7, {"own-7": {"name": "In the backup"}}))
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "Made here"), ("own-7", "In the backup")]
    assert _save(browser, "Next") == "own-8"


def test_the_backups_mapping_whose_name_is_taken_here_stays_behind(live, tmp_path):  # noqa: F811
    _save(live.client, "Kraken export", zone="America/Chicago")
    blob, _ = _backup(tmp_path, _in_backup(3, {"own-3": {"name": "KRAKEN export", "zone": "UTC"}}))
    browser = _restored(live, blob)
    assert [(m["id"], m["name"], m["mapping"]["zone"]) for m in own(browser)] == [
        ("own-1", "Kraken export", "America/Chicago")]


def test_after_a_restore_no_id_is_handed_out_twice(live, tmp_path):  # noqa: F811
    """T3's case on #656: a mapping saved after the backup was made isn't
    dropped, so its id is never given to the next one saved."""
    _save(live.client, "First")
    blob, _ = _backup(tmp_path, _in_backup(1, {"own-1": {"name": "First"}}))
    _save(live.client, "Second")
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "First"), ("own-2", "Second")]
    assert _save(browser, "Third") == "own-3"


def test_a_backups_mapping_whose_id_was_handed_out_here_takes_a_new_one(live, tmp_path):  # noqa: F811
    _save(live.client, "A")
    gone = _save(live.client, "B")
    assert live.client.delete(f"{URL}/{gone}").status_code == 204
    blob, _ = _backup(tmp_path, _in_backup(5, {"own-2": {"name": "From elsewhere"}, "own-5": {"name": "Latest"}}))
    browser = _restored(live, blob)
    # own-2 was B's here, so the backup's own-2 takes the next id after both last ids (5)
    assert _listed(browser) == [("own-1", "A"), ("own-6", "From elsewhere"), ("own-5", "Latest")]
    assert _save(browser, "Next") == "own-7"


def test_a_new_install_gets_the_backups_mappings_as_they_were(live, tmp_path):  # noqa: F811
    blob, _ = _backup(tmp_path, _in_backup(4, {"own-2": {"name": "X"}, "own-4": {"name": "Y"}}))
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-2", "X"), ("own-4", "Y")]
    assert _save(browser, "Z") == "own-5"


def test_a_1x_backup_keeps_this_installs_mappings(live):  # noqa: F811
    _save(live.client, "Made here")
    browser = _restored(live, _sealed(REFERENCE_1X.read_bytes()))
    assert _listed(browser) == [("own-1", "Made here")]
    assert _save(browser, "Next") == "own-2"


def test_a_backups_mapping_named_like_a_ready_made_one_comes_too(live, tmp_path):  # noqa: F811
    """Saved before a later version's ready-made mapping took its name: a restore loses none."""
    _save(live.client, "Made here")
    blob, _ = _backup(tmp_path, _in_backup(2, {"own-2": {"name": "Kraken"}}))
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "Made here"), ("own-2", "Kraken")]


def test_a_mapping_saved_while_the_restore_runs_is_kept(live, tmp_path, monkeypatch):  # noqa: F811
    """This install's mappings are read from the live database at the swap,
    as its other kept settings are."""
    blob, _ = _backup(tmp_path, _in_backup(1, {"own-1": {"name": "In the backup"}}))
    other = _browser()
    _once_rebuilt(monkeypatch, lambda: _save(other, "Meanwhile"))
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "Meanwhile"), ("own-2", "In the backup")]
    assert _save(browser, "Next") == "own-3"


# A backup's mappings row this version can't read (damaged, or a later one's shape) is none, never an error
@pytest.mark.parametrize("stored", [
    '{"mappings": [1, 2]}', '{"mappings": "own-1"}', '"text"', "not json",
    "[" * 100_000 + "]" * 100_000, '{"last_id": true, "mappings": {}}',
], ids=["a list", "a string", "text", "not json", "too deep", "a last id that isn't one"])
def test_a_backups_mappings_row_this_version_cant_read_is_none(live, tmp_path, stored):  # noqa: F811
    _save(live.client, "Made here")
    blob, _ = _backup(tmp_path, f"INSERT INTO app_settings (key, value) VALUES ('import_mappings', '{stored}')")
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "Made here")]
    assert _save(browser, "Next") == "own-2"


def test_a_backups_id_no_number_can_hold_takes_a_new_one(live, tmp_path):  # noqa: F811
    _save(live.client, "Made here")
    blob, _ = _backup(tmp_path, _in_backup(3, {"own-" + "9" * 5000: {"name": "Far off"}}))
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "Made here"), ("own-4", "Far off")]


# A row's last id that's missing or isn't one (damaged, or written by hand):
# the ids' own numbers count, so the next save never takes a mapping's id
@pytest.mark.parametrize("last_id", ["null", "true", '"2"', "0", "-5"])
def test_a_last_id_that_isnt_one_never_hands_an_id_out_twice(live, tmp_path, last_id):  # noqa: F811
    stored = json.dumps({"last_id": 0, "mappings": {"own-1": {**MAPPING, "name": "A"}, "own-2": {**MAPPING, "name": "B"}}})
    stored = stored.replace('"last_id": 0', f'"last_id": {last_id}')
    blob, _ = _backup(tmp_path, f"INSERT INTO app_settings (key, value) VALUES ('import_mappings', '{stored}')")
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "A"), ("own-2", "B")]
    assert _save(browser, "C") == "own-3"
    assert _listed(browser) == [("own-1", "A"), ("own-2", "B"), ("own-3", "C")]


def test_a_backups_last_id_no_number_can_hold_is_none(live, tmp_path):  # noqa: F811
    """JSON reads up to 4,300 digits; one more, the id after it, is past what int() writes."""
    _save(live.client, "Made here")
    stored = json.dumps({"last_id": 0, "mappings": {"own-1": {**MAPPING, "name": "X"}}})
    stored = stored.replace('"last_id": 0', '"last_id": ' + "9" * 4300)
    blob, _ = _backup(tmp_path, f"INSERT INTO app_settings (key, value) VALUES ('import_mappings', '{stored}')")
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "Made here"), ("own-2", "X")]
    assert _save(browser, "Next") == "own-3"


# The top of the ids an install reads back (a crafted backup's): a save past
# it would write an id read as none, then hand it out again over a mapping
TOP = "own-" + "9" * 18


def test_no_mapping_is_saved_past_the_top_id_and_none_is_overwritten(live, tmp_path):  # noqa: F811
    blob, _ = _backup(tmp_path, _in_backup(0, {TOP: {"name": "A"}}))
    browser = _restored(live, blob)
    r = browser.post(URL, json={**MAPPING, "name": "B"})
    assert (r.status_code, r.json()["detail"]) == (409, NO_MORE_IDS)
    assert _listed(browser) == [(TOP, "A")]
    assert browser.put(f"{URL}/{TOP}", json={**MAPPING, "name": "A, replaced"}).status_code == 200


def test_a_backups_mapping_that_would_need_an_id_past_the_top_stays_behind(live, tmp_path):  # noqa: F811
    _save(live.client, "Here")
    blob, _ = _backup(tmp_path, _in_backup(0, {TOP: {"name": "X"}, "own-1": {"name": "Y"}}))
    browser = _restored(live, blob)
    assert _listed(browser) == [("own-1", "Here"), (TOP, "X")]
    assert browser.post(URL, json={**MAPPING, "name": "Z"}).status_code == 409
    assert _listed(browser) == [("own-1", "Here"), (TOP, "X")]
