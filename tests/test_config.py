"""M4: library API — parse()/config() (SPEC.md §5, §7).

Multi-file precedence is pinned to the real dotenvx CLI's behavior, confirmed
via `dotenvx run -f a -f b`: earlier files win unless --overload, in which
case later files win (see PLAN.md M4 notes).
"""

from __future__ import annotations

from pathlib import Path

import dotenvx
from dotenvx import config, parse


def test_parse_does_not_touch_os_environ(monkeypatch) -> None:
    monkeypatch.delenv("PARSE_SHOULD_NOT_LEAK", raising=False)
    parse("PARSE_SHOULD_NOT_LEAK=1\n")
    import os

    assert "PARSE_SHOULD_NOT_LEAK" not in os.environ


def test_parse_uses_given_process_env_for_expansion() -> None:
    result = parse('A="${BASE}/x"\n', process_env={"BASE": "/root"})
    assert result == {"A": "/root/x"}


def test_config_single_file_injects_into_given_environ(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nB=2\n")
    environ: dict[str, str] = {}

    result = config(env_file, environ=environ)

    assert environ == {"A": "1", "B": "2"}
    assert result.parsed == {"A": "1", "B": "2"}
    assert result.injected == {"A": "1", "B": "2"}
    assert result.existed == {}
    assert result.errors == []


def test_config_does_not_overwrite_existing_by_default(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=from_file\n")
    environ = {"A": "from_environ"}

    result = config(env_file, environ=environ)

    assert environ == {"A": "from_environ"}
    assert result.parsed == {"A": "from_environ"}
    assert result.existed == {"A": "from_environ"}
    assert result.injected == {}


def test_config_overload_overwrites_existing(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=from_file\n")
    environ = {"A": "from_environ"}

    result = config(env_file, overload=True, environ=environ)

    assert environ == {"A": "from_file"}
    assert result.injected == {"A": "from_file"}


def test_config_multi_file_first_wins_by_default(tmp_path: Path) -> None:
    one = tmp_path / ".env.one"
    one.write_text("A=from_env1\nB=only_in_1\n")
    two = tmp_path / ".env.two"
    two.write_text("A=from_env2\nC=only_in_2\n")
    environ: dict[str, str] = {}

    result = config([one, two], environ=environ)

    assert environ == {"A": "from_env1", "B": "only_in_1", "C": "only_in_2"}
    assert result.parsed == environ


def test_config_multi_file_reversed_order_flips_winner(tmp_path: Path) -> None:
    one = tmp_path / ".env.one"
    one.write_text("A=from_env1\n")
    two = tmp_path / ".env.two"
    two.write_text("A=from_env2\n")
    environ: dict[str, str] = {}

    config([two, one], environ=environ)

    assert environ == {"A": "from_env2"}


def test_config_multi_file_overload_last_wins(tmp_path: Path) -> None:
    one = tmp_path / ".env.one"
    one.write_text("A=from_env1\n")
    two = tmp_path / ".env.two"
    two.write_text("A=from_env2\n")
    environ: dict[str, str] = {}

    config([one, two], overload=True, environ=environ)

    assert environ == {"A": "from_env2"}


def test_config_missing_file_records_error_and_continues(tmp_path: Path) -> None:
    missing = tmp_path / ".env.missing"
    environ: dict[str, str] = {}

    result = config(missing, environ=environ)

    assert result.errors == [f"missing file ({missing})"]
    assert result.parsed == {}
    assert environ == {}


def test_config_defaults_to_os_environ(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DOTENVX_M4_TEST=hello\n")
    monkeypatch.delenv("DOTENVX_M4_TEST", raising=False)

    dotenvx.config()

    import os

    assert os.environ["DOTENVX_M4_TEST"] == "hello"
