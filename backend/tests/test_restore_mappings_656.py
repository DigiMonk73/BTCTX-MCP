"""
What a restore does with the exchange import's saved mappings (#656). They
are the owner's tools, neither this install's own (the login, the AI key, the
price choice a restore keeps) nor the ledger's (nothing in it names one): a
restore loses none. This install's stay, the backup's are added unless one
here (or a ready-made one) has the name, and no mapping id handed out here is
handed out again.
"""

import json

from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.test_exchange_import_567_own import MAPPING, own
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
    blob, _ = _backup(tmp_path, _in_backup(3, {"own-3": {"name": "KRAKEN export", "zone": "UTC"},
                                               "own-2": {"name": "Kraken"}}))  # a ready-made one's name
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
