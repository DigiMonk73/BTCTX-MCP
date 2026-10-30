"""
The whole suite's own options (backend/tests and mcp_server/tests): CI runs
it split across machines (backend/tests/shards.py, #814). Kept here at the
root, which pytest always reads first, so `--shard 1/3` works with a space
as well as with "=".
"""

from backend.tests import shards


def pytest_addoption(parser):
    parser.addoption("--shard", metavar="K/N", help="run only shard K of N, as CI does (backend/tests/shards.py)")
    parser.addoption("--ran-list", metavar="PATH", help="write each test run and its seconds there, as JSON (CI's guard)")


def pytest_configure(config):
    if config.getoption("ran_list"):
        config.pluginmanager.register(shards.RanList(config.getoption("ran_list")), "ran-list")


def pytest_collection_modifyitems(config, items):
    if config.getoption("shard"):
        number, count = shards.parse(config.getoption("shard"))
        kept, others = shards.select(items, number, count, shards.read_durations())
        items[:] = kept
        config.hook.pytest_deselected(items=others)
