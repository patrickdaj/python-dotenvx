"""M5: encrypted ``.env`` wired end-to-end through ``config()`` (SPEC.md §3.4, §5).

Uses the real Node-dotenvx-produced golden fixture from M1
(``tests/fixtures/node_interop/``) to prove ``config()`` decrypts on load,
not just ``crypto.decrypt()`` in isolation.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from dotenvx import config

FIXTURES = Path(__file__).parent / "fixtures" / "node_interop"
EXPECTED: dict[str, str] = json.loads((FIXTURES / "expected.json").read_text())


def test_config_decrypts_node_fixture_via_colocated_env_keys() -> None:
    environ: dict[str, str] = {}

    result = config(FIXTURES / ".env", environ=environ)

    for key, value in EXPECTED.items():
        assert environ[key] == value
        assert result.parsed[key] == value
    assert result.errors == []


def test_config_without_private_key_reports_unresolved(tmp_path: Path) -> None:
    # Copy just the encrypted .env, no .env.keys alongside it.
    shutil.copy(FIXTURES / ".env", tmp_path / ".env")
    environ: dict[str, str] = {}

    result = config(tmp_path / ".env", environ=environ)

    assert "could not decrypt" in result.errors[0]
    assert environ["HELLO"].startswith("encrypted:")
    assert result.parsed["HELLO"].startswith("encrypted:")


def test_config_uses_private_key_already_in_environ_over_env_keys_file(
    tmp_path: Path,
) -> None:
    shutil.copy(FIXTURES / ".env", tmp_path / ".env")
    private_key = [
        line.split("=", 1)[1].strip().strip('"')
        for line in (FIXTURES / ".env.keys").read_text().splitlines()
        if line.startswith("DOTENV_PRIVATE_KEY=")
    ][0]
    environ = {"DOTENV_PRIVATE_KEY": private_key}

    result = config(tmp_path / ".env", environ=environ)

    assert result.parsed["HELLO"] == EXPECTED["HELLO"]


def test_config_explicit_env_keys_path(tmp_path: Path) -> None:
    shutil.copy(FIXTURES / ".env", tmp_path / "app.env")
    keys_path = tmp_path / "secrets" / ".env.keys"
    keys_path.parent.mkdir()
    shutil.copy(FIXTURES / ".env.keys", keys_path)
    environ: dict[str, str] = {}

    result = config(tmp_path / "app.env", environ=environ, env_keys_path=keys_path)

    assert result.parsed["HELLO"] == EXPECTED["HELLO"]
