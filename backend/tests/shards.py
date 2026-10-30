"""
The Python suite split across machines (#814): CI runs it as shards, each
a share of the test files (`pytest --shard 2/3`), so a run takes about a
third of the time.

A file is never split between shards, so its module fixtures are set up in
one shard only (test_printed_forms.py's takes a minute). The files are
shared out by how long each took on CI (test_durations.json), the longest
first into the shard with the least so far, so the shards end together; a
file not timed yet counts as the average one. A shard runs its tests in the
collection's order, as the whole suite does: a test that leaves something
behind (a logger's level, a database override) still runs after the tests
it would upset.

Every test still runs, in exactly one shard: CI's guard
(scripts/check_test_shards.py) compares what the shards ran (`--ran-list`)
with a full collection.
"""

import json
from pathlib import Path

import pytest

DURATIONS = Path(__file__).with_name("test_durations.json")


def parse(text: str) -> tuple[int, int]:
    """"2/3": shard 2 of 3, counted from 1."""
    try:
        number, count = (int(part) for part in text.split("/"))
    except ValueError:
        raise pytest.UsageError(f"--shard takes K/N, such as 1/3, not {text!r}") from None
    if not 1 <= number <= count:
        raise pytest.UsageError(f"--shard {text}: K must be from 1 to N")
    return number, count


def plan(files: list[str], durations: dict[str, float], count: int) -> list[list[str]]:
    """The test files of each shard, each file in one, longest first."""
    average = sum(durations.values()) / len(durations) if durations else 1.0
    weight = {name: durations.get(name, average) for name in files}
    shards: list[list[str]] = [[] for _ in range(count)]
    totals = [0.0] * count
    for name in sorted(weight, key=lambda name: (-weight[name], name)):
        lightest = totals.index(min(totals))
        shards[lightest].append(name)
        totals[lightest] += weight[name]
    return shards


def select(items: list, number: int, count: int, durations: dict[str, float]) -> tuple[list, list]:
    """Shard `number`'s tests, in the collection's order, and the others."""
    files = list(dict.fromkeys(file_of(item.nodeid) for item in items))
    mine = set(plan(files, durations, count)[number - 1])
    return [item for item in items if file_of(item.nodeid) in mine], \
        [item for item in items if file_of(item.nodeid) not in mine]


def read_durations() -> dict[str, float]:
    """Each test file's seconds on CI (scripts/check_test_shards.py writes them)."""
    return json.loads(DURATIONS.read_text()) if DURATIONS.exists() else {}


def file_of(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def without_group(nodeid: str) -> str:
    """A test's id as the collection has it: pytest-xdist's loadgroup adds
    "@group" to the id of a test marked xdist_group (the same rule as its
    own, so a parameter holding an "@" stays)."""
    at = nodeid.rfind("@")
    return nodeid[:at] if at > nodeid.rfind("]") else nodeid


class RanList:
    """Every test this run ran and its seconds (setup, call and teardown),
    written as JSON when the run ends: CI's guard reads each shard's."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.seconds: dict[str, float] = {}

    def pytest_runtest_logreport(self, report) -> None:
        nodeid = without_group(report.nodeid)
        self.seconds[nodeid] = self.seconds.get(nodeid, 0.0) + report.duration

    def pytest_sessionfinish(self, session) -> None:
        # Under pytest-xdist each worker's reports also reach the controller,
        # which writes the list for them all
        if not hasattr(session.config, "workerinput"):
            rounded = {nodeid: round(seconds, 3) for nodeid, seconds in sorted(self.seconds.items())}
            self.path.write_text(json.dumps(rounded, indent=1) + "\n")
