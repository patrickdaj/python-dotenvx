"""Shared pytest fixtures.

``dotenvx.config()``/``dotenvx run`` default to mutating the real
``os.environ`` in place (by design — that's how ``run`` injects vars for a
child process, matching dotenvx). ``monkeypatch.setenv``/``delenv`` only
auto-revert changes made *through monkeypatch itself*, so a test that lets
production code write to ``os.environ`` directly can leak variables into
every test that runs after it. Snapshot/restore ``os.environ`` around every
test to make that isolation automatic, regardless of which code path wrote
to it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolate_os_environ() -> Iterator[None]:
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)
