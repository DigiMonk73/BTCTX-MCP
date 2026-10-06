"""
Restoring a backup file inside the app keeps the login in use, as it keeps
the AI key (owner decision 2026-09-28, after Grok Bot's StartOS test): the
restored database brought back the backup's username and password, so on
StartOS the password the package gave stopped working.
"""

from sqlalchemy import text

from backend.models.user import User
from backend.tests.conftest import default_login


def test_restoring_an_old_backup_keeps_the_login_in_use(auth_client, test_engine, monkeypatch):
    from backend.routers import backup

    old = User(username="old-owner", password_hash="")
    old.set_password("old-password-123")

    def restore_old_backup(password, path):  # the backup's database: another login
        with test_engine.begin() as conn:
            conn.execute(text("UPDATE users SET username = :u, password_hash = :h"),
                         {"u": old.username, "h": old.password_hash})

    monkeypatch.setattr(backup, "restore_backup", restore_old_backup)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert r.status_code == 200, r.text

    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT username FROM users")).scalar() == default_login()["username"]
    assert auth_client.post("/api/login", json={"username": "old-owner", "password": "old-password-123"}).status_code != 200
    assert auth_client.post("/api/login", json=default_login()).status_code == 200
    assert "current username and password" in r.json()["message"]


def _restore_a_backup_that_used_public_sites(auth_client, test_engine, monkeypatch):
    from backend.routers import backup

    def restore_old_backup(password, path):  # the backup's database: public sites, direct, prices stored
        with test_engine.begin() as conn:
            for key in ("price_source", "mempool_fallback", "mempool_url", "proxy_url", "live_data"):
                conn.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": key})
            conn.execute(text("INSERT INTO app_settings (key, value) VALUES ('price_source', 'public')"))
            conn.execute(text("INSERT OR REPLACE INTO btc_price_daily (day, usd, source) "
                              "VALUES ('2020-01-01', 7200, 'bitstamp')"))

    monkeypatch.setattr(backup, "restore_backup", restore_old_backup)
    r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
    assert r.status_code == 200, r.text
    assert auth_client.post("/api/login", json=default_login()).status_code == 200
    settings = auth_client.get("/api/settings/network").json()
    with test_engine.begin() as conn:
        conn.execute(text("DELETE FROM btc_price_daily WHERE day = '2020-01-01' AND usd = 7200"))
    return settings


def test_a_restore_keeps_the_price_settings_in_use(auth_client, test_engine, monkeypatch):
    """Privacy audit 2026-09-29 (1j), owner decision: a restore brought back
    the backup's price settings, so an install switched to Tor or Off since
    that backup asked the public sites directly again."""
    tor = {"price_source": "public", "mempool_url": None, "mempool_fallback": False,
           "proxy_url": "socks5h://127.0.0.1:9050"}
    assert auth_client.put("/api/settings/network", json=tor).status_code == 200
    after = _restore_a_backup_that_used_public_sites(auth_client, test_engine, monkeypatch)
    assert (after["price_source"], after["proxy_url"]) == ("public", "socks5h://127.0.0.1:9050")

    off = {**tor, "price_source": "off", "proxy_url": None}
    assert auth_client.put("/api/settings/network", json=off).status_code == 200
    assert _restore_a_backup_that_used_public_sites(auth_client, test_engine, monkeypatch)["price_source"] == "off"


def test_a_restore_before_any_price_choice_leaves_it_unchosen(auth_client, test_engine, monkeypatch):
    """Nothing chosen yet: the restored backup's choice, or its stored
    prices, don't choose public sites for the owner."""
    with test_engine.begin() as conn:
        conn.execute(text("DELETE FROM app_settings WHERE key IN "
                          "('price_source', 'mempool_fallback', 'mempool_url', 'proxy_url', 'live_data')"))
    assert _restore_a_backup_that_used_public_sites(auth_client, test_engine, monkeypatch)["price_source"] == "unset"
    auth_client.put("/api/settings/network", json={"price_source": "public", "mempool_url": None,
                                                    "mempool_fallback": False, "proxy_url": None})
