"""M0 smoke tests: the package imports and the CLI entrypoint is wired."""

from __future__ import annotations

from typer.testing import CliRunner

import dotenvx
from dotenvx.cli import app

runner = CliRunner()


def test_package_exposes_version() -> None:
    assert isinstance(dotenvx.__version__, str)
    assert dotenvx.__version__


def test_cli_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert dotenvx.__version__ in result.stdout


def test_cli_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    # Typer's no_args_is_help prints usage and exits 2 (like a missing command)
    assert result.exit_code == 2
    assert "Usage" in result.stdout
