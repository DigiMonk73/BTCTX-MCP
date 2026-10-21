"""
The equivalence check's ledgers stay 1.x's (2.0 spec 5.15): its golden
ledger and random generator are frozen copies in scripts/, never the
backend tests' own (which the pin's side may lack, and 2.0 may change),
and the reference ledger reaches both sides without its "since": "2.0"
rows. scripts/seed_ledger.py strips "since" as it strips "why".
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

# The golden ledger and seeds 0-39 of the snapshot's random ledgers, worked
# out from v1.2.9's own LEDGER and draw_ledger (git archive v1.2.9) with the
# snapshot's SeededDraws. Never updated: a different digest means the frozen
# ledgers are no longer 1.x's.
DIGEST_1X = "37d6b981ee3003a0536f070539f4ec1fd0bb45cdd22daedc44dab25a115cfe0b"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass looks its module up there
    spec.loader.exec_module(module)
    return module


def ledgers_digest(golden: list, draw_ledger, seeded_draws) -> str:
    ledgers = [golden] + [draw_ledger(seeded_draws(seed), max_ops=25)[0] for seed in range(40)]
    return hashlib.sha256(json.dumps(ledgers, sort_keys=True).encode()).hexdigest()


def test_the_frozen_ledgers_are_1x_s():
    frozen = _script("equivalence_ledgers_1x")
    assert ledgers_digest(frozen.GOLDEN_LEDGER, frozen.draw_ledger, frozen.SeededDraws) == DIGEST_1X


def _ledger_file(tmp_path: Path) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"transactions": [
        {"type": "Buy", "amount": "1", "why": "a 1.x row"},
        {"type": "Sell", "amount": "0.5", "why": "a 2.0 row", "since": "2.0"},
    ]}))
    return path


def test_the_reference_ledger_reaches_1x_without_its_2_0_rows(tmp_path):
    frozen = _script("equivalence_ledgers_1x")
    assert frozen.reference_rows_1x(_ledger_file(tmp_path)) == [{"type": "Buy", "amount": "1"}]


def test_seed_ledger_strips_since_as_it_strips_why(tmp_path, monkeypatch):
    seed_ledger = _script("seed_ledger")
    monkeypatch.setattr(seed_ledger, "LEDGER", _ledger_file(tmp_path))
    assert seed_ledger.ledger_rows() == [{"type": "Buy", "amount": "1"}, {"type": "Sell", "amount": "0.5"}]


def test_the_snapshot_takes_the_frozen_ledgers():
    snapshot = (SCRIPTS / "equivalence_snapshot.py").read_text()
    assert "backend.tests.test_golden_years" not in snapshot
    assert "backend.tests.test_invariants_property" not in snapshot
    assert "from equivalence_ledgers_1x import" in snapshot
    # A change to the frozen ledgers' file retakes the release's snapshot
    assert '"equivalence_ledgers_1x.py"' in (SCRIPTS / "equivalence_check.py").read_text()
