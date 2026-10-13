"""Edge inputs to the first-run setup code and to password checks must be refused, not crash.

- A setup code with non-ASCII letters or digits is compared with hmac, which raises TypeError
  for non-ASCII text. Such a code can never match, so it is treated as wrong.
- bcrypt reads at most 72 bytes and raises ValueError for more. A longer password never
  matches, so verify_password returns False.
"""

import bcrypt

from backend.models.user import User
from backend.services import first_run


def test_a_setup_code_with_non_ascii_letters_is_just_wrong(monkeypatch, tmp_path):
    monkeypatch.setattr(first_run, "_read_code", lambda: "ABCD-EFGH-JKMN")
    assert first_run.check_code("ÀÀÀÀ-ÀÀÀÀ-ÀÀÀÀ") is False


def test_the_matching_setup_code_still_passes(monkeypatch):
    monkeypatch.setattr(first_run, "_read_code", lambda: "ABCD-EFGH-JKMN")
    assert first_run.check_code("abcd-efgh-jkmn") is True


def test_a_password_longer_than_72_bytes_does_not_match_or_raise():
    user = User(username="u", password_hash=bcrypt.hashpw(b"correct horse", bcrypt.gensalt()).decode())
    assert user.verify_password("x" * 73) is False


def test_a_correct_password_still_verifies():
    user = User(username="u", password_hash=bcrypt.hashpw(b"correct horse", bcrypt.gensalt()).decode())
    assert user.verify_password("correct horse") is True
