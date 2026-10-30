#!/usr/bin/env python3
"""
CI's guard on the Python suite split across machines (#814): for each
Python version, every test collected ran, in exactly one shard.

Each shard's job leaves a folder `python-tests-py<version>-<shard>` (its
artifact) holding:
- collected.txt: `pytest --collect-only -q` of the whole suite, a run of
  its own without --shard, so a fault in the split can't hide a test from it;
- ran.json: every test the shard ran and its seconds (`--ran-list`).

It fails when a shard's folder is missing, a version's shards collected
different tests, a test ran in two shards, or a test collected ran in none.
With --durations it then writes each test file's seconds (the versions'
average), ready to replace backend/tests/test_durations.json.

    python scripts/check_test_shards.py FOLDER --shards 3 [--durations OUT]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ARTIFACT = re.compile(r"python-tests-py(?P<version>\d+\.\d+)-(?P<shard>\d+)$")
# How many test ids a failure lists before saying how many more
SHOWN = 20


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    found = read_shards(Path(args.folder))
    if not found:
        print(f"No shard results in {args.folder}")
        return 1
    problems = [problem for version in sorted(found) for problem in check_version(version, found[version], args.shards)]
    for problem in problems:
        print(problem)
    if problems:
        return 1
    if args.durations:
        Path(args.durations).write_text(json.dumps(file_seconds(found), indent=1, sort_keys=True) + "\n")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", help="the folder the shards' artifacts were downloaded into")
    parser.add_argument("--shards", type=int, required=True, help="how many shards each version ran as")
    parser.add_argument("--durations", help="write each test file's seconds there, as JSON")
    return parser.parse_args(argv)


def read_shards(folder: Path) -> dict[str, dict[int, tuple[list[str], dict[str, float]]]]:
    """version -> shard -> (the tests it collected, the tests it ran and their seconds)."""
    found: dict[str, dict[int, tuple[list[str], dict[str, float]]]] = defaultdict(dict)
    for path in sorted(folder.iterdir()):
        name = ARTIFACT.match(path.name)
        if name:
            collected = collected_ids((path / "collected.txt").read_text())
            ran = json.loads((path / "ran.json").read_text())
            found[name["version"]][int(name["shard"])] = (collected, ran)
    return dict(found)


def collected_ids(text: str) -> list[str]:
    """The test ids `pytest --collect-only -q` printed, one a line, up to the
    blank line before its summary."""
    return text.split("\n\n", 1)[0].splitlines()


def check_version(version: str, shards: dict[int, tuple[list[str], dict[str, float]]], count: int) -> list[str]:
    absent = sorted(set(range(1, count + 1)) - set(shards))
    if absent:
        return [f"py{version}: no results from shard {', '.join(map(str, absent))} of {count}"]
    collected = set(shards[1][0])
    problems = [f"py{version}: shard {shard} collected other tests than shard 1:{listed(sorted(set(other) ^ collected))}"
                for shard, (other, _ran) in sorted(shards.items()) if set(other) != collected]
    runs = Counter(nodeid for _collected, ran in shards.values() for nodeid in ran)
    for nodeids, says in (
        (sorted(nodeid for nodeid, times in runs.items() if times > 1), "ran in more than one shard"),
        (sorted(collected - set(runs)), "collected ran in no shard"),
        (sorted(set(runs) - collected), "ran that the collection doesn't have"),
    ):
        if nodeids:
            problems.append(f"py{version}: {len(nodeids)} tests {says}:{listed(nodeids)}")
    if not problems:
        each = " + ".join(f"{len(shards[shard][1]):,}" for shard in sorted(shards))
        print(f"py{version}: {len(collected):,} tests collected, each run once by the {count} shards ({each})")
    return problems


def listed(nodeids: list[str]) -> str:
    more = f"\n  … and {len(nodeids) - SHOWN} more" if len(nodeids) > SHOWN else ""
    return "".join(f"\n  {nodeid}" for nodeid in nodeids[:SHOWN]) + more


def file_seconds(found: dict[str, dict[int, tuple[list[str], dict[str, float]]]]) -> dict[str, float]:
    """Each test file's seconds, the versions' average."""
    totals: dict[str, float] = defaultdict(float)
    for shards in found.values():
        for _collected, ran in shards.values():
            for nodeid, seconds in ran.items():
                totals[nodeid.split("::", 1)[0]] += seconds / len(found)
    return {name: round(seconds, 1) for name, seconds in totals.items()}


if __name__ == "__main__":
    sys.exit(main())
