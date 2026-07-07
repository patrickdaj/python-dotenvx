"""M6: `dotenvx run` and `dotenvx get` (SPEC.md §6)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from dotenvx.cli import app

runner = CliRunner()


def test_get_prints_all_as_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=hello\nB=${A} world\n")

    result = runner.invoke(app, ["get"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"A": "hello", "B": "hello world"}


def test_get_prints_single_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=hello\n")

    result = runner.invoke(app, ["get", "A"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"


def test_get_missing_key_prints_empty_line(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=hello\n")

    result = runner.invoke(app, ["get", "NOPE"])

    assert result.exit_code == 0
    assert result.stdout == "\n"


def test_get_does_not_mutate_real_os_environ(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOTENVX_GET_LEAK_TEST", raising=False)
    (tmp_path / ".env").write_text("DOTENVX_GET_LEAK_TEST=1\n")

    runner.invoke(app, ["get"])

    import os

    assert "DOTENVX_GET_LEAK_TEST" not in os.environ


def test_get_missing_file_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["get"])

    assert result.exit_code == 1
    assert "missing file" in result.stderr


def test_get_shell_format(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\nB=2\n")

    result = runner.invoke(app, ["get", "--format", "shell"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "A=1 B=2"


def test_run_injects_env_and_executes_command(
    tmp_path: Path, monkeypatch, capfd
) -> None:
    # The child inherits the real stdout fd (like dotenvx's stdio: 'inherit'),
    # which CliRunner's sys.stdout capture doesn't see — use capfd instead.
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=hello\nB=${A} world\n")
    monkeypatch.delenv("A", raising=False)

    result = runner.invoke(
        app,
        [
            "run",
            "--",
            sys.executable,
            "-c",
            "import os; print(os.environ['A'], '|', os.environ['B'])",
        ],
    )

    assert result.exit_code == 0
    assert "hello | hello world" in capfd.readouterr().out


def test_run_propagates_exit_code(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\n")

    result = runner.invoke(
        app, ["run", "--", sys.executable, "-c", "import sys; sys.exit(7)"]
    )

    assert result.exit_code == 7


def test_run_without_command_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\n")

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert "missing command" in result.stderr


def test_run_unknown_command_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\n")

    result = runner.invoke(app, ["run", "--", "dotenvx-nonexistent-binary-xyz"])

    assert result.exit_code == 1
    assert "Unknown command" in result.stderr


def test_run_overload_flag(tmp_path: Path, monkeypatch, capfd) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=from_file\n")
    monkeypatch.setenv("A", "from_environ")

    result = runner.invoke(
        app,
        [
            "run",
            "--overload",
            "--",
            sys.executable,
            "-c",
            "import os; print(os.environ['A'])",
        ],
    )

    assert result.exit_code == 0
    assert "from_file" in capfd.readouterr().out
