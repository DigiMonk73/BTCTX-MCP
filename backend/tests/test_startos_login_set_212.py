"""
#212: the StartOS package's store.json kept the password Set Login Credentials
generated, in plain text, though the package only ever asked whether a login
was set. Start9's recipe-web-ui.md ("Authentication") says to persist only the
hash, which the app keeps in its own database; so the store keeps `loginSet`,
and 1.2.9:0's migration turns a stored password into it and deletes it
(`forgetStoredPassword` in utils.ts). The VM checks the update itself.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "startos" / "startos"
STORE = (PKG / "fileModels" / "store.json.ts").read_text()
ACTION = (PKG / "actions" / "setCredentials.ts").read_text()
WATCH = (PKG / "init" / "watchCredentials.ts").read_text()
UTILS = (PKG / "utils.ts").read_text()

# The 1.2.8:0 release, the last whose store could hold the password.
LAST_WITH_PASSWORD = (1, 2, 8, 0)


def package_version(text: str) -> tuple[int, ...]:
    version = re.findall(r"version: '(\d+)\.(\d+)\.(\d+):(\d+)'", text)
    assert len(version) == 1
    return tuple(int(n) for n in version[0])


def migration_up(text: str) -> str:
    """A version file's `up` body, without its comment lines."""
    body = text.split("migrations: {")[1].split("up: async ({ effects }) => {")[1].split("down:")[0]
    return "\n".join(line for line in body.splitlines() if not line.strip().startswith("//"))


def test_the_store_keeps_only_whether_a_login_was_set():
    assert "const shape = z.looseObject({" in STORE
    assert "  loginSet: z.boolean().optional().catch(undefined),\n" in STORE


def test_set_login_credentials_stores_the_flag_and_shows_the_password_once():
    assert "adminPassword" not in ACTION
    assert "await storeJson.merge(effects, { loginSet: true })" in ACTION
    # The app gets the login first, so the flag never says one is set that isn't
    assert ACTION.index("await setAppCredentials(effects, password)") < ACTION.index("loginSet: true")
    # Its warning before replacing a login reads the flag
    assert "warning: (await storeJson.read((s) => !!s.loginSet).const(effects))" in ACTION
    # The password is still returned to the user, masked and copyable
    shown = ACTION.split("name: i18n('Password'),")[1]
    assert "value: password," in shown and "masked: true," in shown


def test_the_set_a_login_task_reads_the_flag():
    assert "adminPassword" not in WATCH
    assert "storeJson.read((s) => !s.loginSet).const(effects)" in WATCH
    assert "createOwnTask(effects, setCredentials, 'critical'" in WATCH


def test_no_package_code_reads_or_writes_a_stored_password():
    """Only the store's model, the 0.9.0:0 migration (which moves an older
    install's password into the store on the way up, before 1.2.9:0 deletes
    it), the legacy file's own model and, in utils.ts, the helper name it."""
    allowed = {
        "fileModels/store.json.ts",
        "fileModels/legacyWrapperStore.ts",
        "versions/v0.9.0_0.ts",
        "utils.ts",
    }
    naming = {
        str(path.relative_to(PKG))
        for path in PKG.rglob("*.ts")
        if "adminPassword" in path.read_text()
    }
    assert naming <= allowed, naming - allowed
    helper = UTILS.split("export async function forgetStoredPassword(")[1].split("\n}\n")[0]
    assert UTILS.count("adminPassword") == helper.count("adminPassword")


def test_the_helper_turns_a_stored_password_into_the_flag():
    body = UTILS.split("export async function forgetStoredPassword(effects: T.Effects) {")[1]
    body = body.split("\n}\n")[0]
    assert "const hadPassword = await storeJson.read((s) => !!s.adminPassword).once()" in body
    # store.json is a z.looseObject: a key goes only when merged as undefined
    # (Start9's file-models.md, "Unknown Key Preservation")
    assert "adminPassword: undefined," in body
    assert "...(hadPassword ? { loginSet: true } : {})," in body
    # Nothing else is written, so every other key (and one the model doesn't
    # name) is kept
    assert body.count("storeJson.merge(") == 1


def test_the_release_after_1_2_8_drops_the_stored_password():
    """1.2.9:0's migration (D1, #373) calls the helper: without it, an update
    would raise the critical "Create your BitcoinTX login" task on every
    install whose store held the password, and keep the password."""
    current = (PKG / "versions" / "current.ts").read_text()
    if package_version(current) <= LAST_WITH_PASSWORD:
        return
    callers = [
        path.name
        for path in (PKG / "versions").glob("*.ts")
        if path.name != "index.ts"
        and package_version(path.read_text()) > LAST_WITH_PASSWORD
        and "await forgetStoredPassword(effects)" in migration_up(path.read_text())
    ]
    assert callers, "a version after 1.2.8:0 must call forgetStoredPassword in its up"
