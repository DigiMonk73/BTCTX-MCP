"""
The Python suite split across machines (#814): the split (shards.py) puts
every test file in exactly one shard, the same way on every machine, and
CI's guard (scripts/check_test_shards.py) fails the run when a test is
dropped, run twice or collected differently, so nothing drops out unseen.
And ci.yml runs the split as the guard checks it.
"""

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.tests import shards

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_test_shards", ROOT / "scripts" / "check_test_shards.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

FILES = [f"backend/tests/test_{name}.py" for name in "abcdefghij"]
TIMED = {"backend/tests/test_a.py": 90.0, "backend/tests/test_b.py": 60.0, "backend/tests/test_c.py": 50.0,
         "backend/tests/test_d.py": 5.0, "backend/tests/test_e.py": 1.0}


def items_of(files: list[str], each: int = 3) -> list:
    return [SimpleNamespace(nodeid=f"{name}::test_{n}") for name in files for n in range(each)]


@pytest.mark.parametrize("count", [1, 2, 3, 4, 12])
def test_every_file_is_in_exactly_one_shard(count):
    planned = shards.plan(FILES, TIMED, count)
    assert len(planned) == count
    assert sorted(name for shard in planned for name in shard) == sorted(FILES)


def test_the_split_is_the_same_whatever_order_the_files_come_in():
    assert shards.plan(FILES, TIMED, 3) == shards.plan(list(reversed(FILES)), TIMED, 3)


def test_the_longest_files_go_first_each_into_the_lightest_shard():
    planned = shards.plan(FILES, TIMED, 3)
    assert [shard[0] for shard in planned] == ["backend/tests/test_a.py", "backend/tests/test_b.py",
                                               "backend/tests/test_c.py"]
    totals = [sum(TIMED.get(name, 0) for name in shard) for shard in planned]
    assert max(totals) - min(totals) <= max(TIMED.values())


def test_a_file_not_timed_yet_counts_as_the_average_one():
    """Five files have no time: each counts as the average, 41.2 s, so they
    spread over the shards rather than all landing in one."""
    planned = shards.plan(FILES, TIMED, 3)
    untimed = [name for name in FILES if name not in TIMED]
    assert all(any(name in untimed for name in shard) for shard in planned)


def test_with_no_times_at_all_the_files_share_out_evenly():
    planned = shards.plan(FILES, {}, 3)
    assert sorted(len(shard) for shard in planned) == [3, 3, 4]


def test_a_shard_runs_its_files_whole_in_the_collections_order():
    """The order the whole suite runs in, so a test that leaves something
    behind still runs after the tests it would upset (#814)."""
    items = items_of(FILES)
    seen = []
    for number in (1, 2, 3):
        kept, others = shards.select(items, number, 3, TIMED)
        assert len(kept) + len(others) == len(items)
        assert sorted({shards.file_of(item.nodeid) for item in kept}) == sorted(shards.plan(FILES, TIMED, 3)[number - 1])
        assert kept == [item for item in items if item in kept]
        seen += kept
    assert sorted(item.nodeid for item in seen) == sorted(item.nodeid for item in items)


@pytest.mark.parametrize("text", ["1", "0/3", "4/3", "a/3", "1/3/1", ""])
def test_a_shard_is_named_k_of_n(text):
    with pytest.raises(pytest.UsageError):
        shards.parse(text)
    assert shards.parse("3/3") == (3, 3)


@pytest.mark.parametrize("nodeid, collected", [
    ("backend/tests/test_printed_forms.py::test_x[seed-2024]@printed_forms",
     "backend/tests/test_printed_forms.py::test_x[seed-2024]"),
    ("backend/tests/test_x.py::test_y@printed_forms", "backend/tests/test_x.py::test_y"),
    ("backend/tests/test_x.py::test_y[a@b]", "backend/tests/test_x.py::test_y[a@b]"),
    ("backend/tests/test_x.py::test_y", "backend/tests/test_x.py::test_y"),
])
def test_a_ran_test_is_named_as_the_collection_names_it(nodeid, collected):
    assert shards.without_group(nodeid) == collected


def test_the_ran_list_adds_up_each_tests_seconds(tmp_path):
    ran = shards.RanList(str(tmp_path / "ran.json"))
    for when, seconds in (("setup", 1.0), ("call", 2.5), ("teardown", 0.25)):
        ran.pytest_runtest_logreport(SimpleNamespace(nodeid="backend/tests/test_a.py::test_0@g", when=when,
                                                     duration=seconds))
    ran.pytest_sessionfinish(SimpleNamespace(config=SimpleNamespace(workerinput={})))
    assert not (tmp_path / "ran.json").exists(), "a pytest-xdist worker leaves the writing to the controller"
    ran.pytest_sessionfinish(SimpleNamespace(config=SimpleNamespace()))
    assert json.loads((tmp_path / "ran.json").read_text()) == {"backend/tests/test_a.py::test_0": 3.75}


def shard_results(folder: Path, collected: list[str], ran: dict[int, list[str]], version: str = "3.11") -> None:
    """Each shard's artifact as CI leaves it: what it collected, what it ran."""
    for shard, nodeids in ran.items():
        path = folder / f"python-tests-py{version}-{shard}"
        path.mkdir()
        (path / "collected.txt").write_text("\n".join(collected) + f"\n\n{len(collected)} tests collected in 1.00s\n")
        (path / "ran.json").write_text(json.dumps({nodeid: 0.5 for nodeid in nodeids}))


ALL = [item.nodeid for item in items_of(FILES, 2)]


def split(nodeids: list[str]) -> dict[int, list[str]]:
    return {1: nodeids[:7], 2: nodeids[7:14], 3: nodeids[14:]}


def test_the_guard_passes_when_every_test_ran_once(tmp_path, capsys):
    shard_results(tmp_path, ALL, split(ALL))
    shard_results(tmp_path, ALL, split(ALL), version="3.13")
    out = tmp_path / "durations.json"
    assert guard.main([str(tmp_path), "--shards", "3", "--durations", str(out)]) == 0
    assert "py3.11: 20 tests collected, each run once by the 3 shards (7 + 7 + 6)" in capsys.readouterr().out
    assert json.loads(out.read_text()) == {name: 1.0 for name in FILES}


@pytest.mark.parametrize("ran, says", [
    ({1: ALL[:7], 2: ALL[7:14], 3: ALL[15:]}, "1 tests collected ran in no shard"),
    ({1: ALL[:8], 2: ALL[7:14], 3: ALL[14:]}, "1 tests ran in more than one shard"),
    ({1: ALL[:7], 2: ALL[7:14], 3: ALL[14:] + ["backend/tests/test_z.py::test_0"]},
     "1 tests ran that the collection doesn't have"),
    ({1: ALL[:7], 2: ALL[7:]}, "no results from shard 3 of 3"),
])
def test_the_guard_fails_on_a_test_dropped_run_twice_or_unknown_or_a_shard_missing(tmp_path, capsys, ran, says):
    shard_results(tmp_path, ALL, ran)
    out = tmp_path / "durations.json"
    assert guard.main([str(tmp_path), "--shards", "3", "--durations", str(out)]) == 1
    assert says in capsys.readouterr().out
    assert not out.exists(), "no timings from a run the guard failed"


def test_the_guard_fails_when_the_shards_collected_different_tests(tmp_path, capsys):
    shard_results(tmp_path, ALL, {1: ALL[:7], 2: ALL[7:14]})
    shard_results(tmp_path, ALL[:-1], {3: ALL[14:-1]})
    assert guard.main([str(tmp_path), "--shards", "3"]) == 1
    out = capsys.readouterr().out
    assert "shard 3 collected other tests than shard 1" in out and ALL[-1] in out


def test_the_guard_fails_with_no_results_at_all(tmp_path):
    assert guard.main([str(tmp_path), "--shards", "3"]) == 1


def test_the_timings_name_test_files():
    """The stored timings are each a file's seconds, as the guard writes them."""
    durations = shards.read_durations()
    assert durations, "test_durations.json is there"
    assert all(re.fullmatch(r"(backend|mcp_server)/tests/test_\w+\.py", name) for name in durations)
    assert all(seconds >= 0 for seconds in durations.values())


def ci_job(name: str) -> str:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    found = re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:\n|\Z)", text, re.M | re.S)
    assert found, name
    return found.group(1)


def test_ci_runs_the_split_the_guard_checks():
    """The python job's shards, the count each runs as and the guard's
    count agree, the guard is in "CI passed"'s needs, and the shards record
    what they ran beside a full collection of their own."""
    python, guard_job = ci_job("python"), ci_job("python-guard")
    shard_list = re.search(r"^\s+shard: \[(.*?)\]", python, re.M).group(1)
    count = len(shard_list.split(","))
    assert count >= 2
    assert f"--shard ${{{{ matrix.shard }}}}/{count}" in python
    assert "--ran-list" in python and "--collect-only -q" in python
    assert f"--shards {count}" in guard_job
    needs = re.search(r"^    needs: \[(.*?)\]", ci_job("ci-passed"), re.M).group(1)
    assert {"python", "python-guard"} <= {need.strip() for need in needs.split(",")}
