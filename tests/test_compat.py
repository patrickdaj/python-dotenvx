"""M9: python-dotenv compatibility shim (SPEC.md §7).

Lets code written against `python-dotenv` migrate with a single import-line
change. Simplification (documented in `__init__.py`): `find_dotenv()` always
searches from the cwd, unlike python-dotenv's caller-file-based default.
"""

from __future__ import annotations

from pathlib import Path

import dotenvx


def test_find_dotenv_locates_file_in_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\n")

    assert dotenvx.find_dotenv() == str(tmp_path / ".env")


def test_find_dotenv_searches_upward(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("A=1\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert dotenvx.find_dotenv() == str(tmp_path / ".env")


def test_find_dotenv_not_found_returns_empty_string(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert dotenvx.find_dotenv() == ""


def test_find_dotenv_raises_if_requested(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    try:
        dotenvx.find_dotenv(raise_error_if_not_found=True)
        raise AssertionError("expected OSError")
    except OSError:
        pass


def test_load_dotenv_loads_into_os_environ(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOTENVX_COMPAT_TEST", raising=False)
    (tmp_path / ".env").write_text("DOTENVX_COMPAT_TEST=hello\n")

    result = dotenvx.load_dotenv()

    import os

    assert result is True
    assert os.environ["DOTENVX_COMPAT_TEST"] == "hello"


def test_load_dotenv_returns_false_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert dotenvx.load_dotenv() is False


def test_load_dotenv_accepts_and_ignores_unknown_kwargs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\n")

    assert dotenvx.load_dotenv(verbose=True, interpolate=True, encoding="utf-8") is True


def test_load_dotenv_override_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("A", "from_environ")
    (tmp_path / ".env").write_text("A=from_file\n")

    dotenvx.load_dotenv(override=True)

    import os

    assert os.environ["A"] == "from_file"


def test_dotenv_values_parses_without_touching_os_environ(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOTENVX_VALUES_TEST", raising=False)
    (tmp_path / ".env").write_text("DOTENVX_VALUES_TEST=hello\n")

    values = dotenvx.dotenv_values()

    import os

    assert values == {"DOTENVX_VALUES_TEST": "hello"}
    assert "DOTENVX_VALUES_TEST" not in os.environ


def test_dotenv_values_missing_file_returns_empty_dict(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert dotenvx.dotenv_values() == {}


def test_dotenv_values_explicit_path(tmp_path: Path) -> None:
    custom = tmp_path / "custom.env"
    custom.write_text("A=1\n")

    assert dotenvx.dotenv_values(custom) == {"A": "1"}
