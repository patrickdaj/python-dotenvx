"""Typer CLI entrypoint for dotenvx.

Commands are added across milestones (see PLAN.md / SPEC.md §6).
"""

from __future__ import annotations

import json
import os
import subprocess

import typer

import dotenvx
from dotenvx import __version__

app = typer.Typer(
    name="dotenvx",
    help="A better dotenv — run anywhere, multi-env, encrypted.",
    no_args_is_help=True,
    add_completion=False,
)

_ENV_FILE_OPTION = typer.Option(
    [".env"],
    "-f",
    "--env-file",
    help="Path to a .env file; repeat to load multiple, in order.",
)
_OVERLOAD_OPTION = typer.Option(
    False,
    "--overload",
    help="Later sources / process env is overridden by files (default: first wins).",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the dotenvx version and exit.",
    ),
) -> None:
    """dotenvx — secure, cross-language environment variable management."""


def _report_errors(errors: list[str]) -> None:
    for error in errors:
        typer.echo(f"dotenvx: {error}", err=True)


@app.command(context_settings={"ignore_unknown_options": True})
def run(
    command: list[str] | None = typer.Argument(  # noqa: B008
        None, help="Command to execute, e.g. `-- npm start`."
    ),
    env_file: list[str] = _ENV_FILE_OPTION,
    overload: bool = _OVERLOAD_OPTION,
) -> None:
    """Inject env vars from .env file(s), then execute COMMAND."""
    if not command:
        typer.echo(
            "missing command after [dotenvx run --]. try [dotenvx run -- yourcommand]",
            err=True,
        )
        raise typer.Exit(1)

    result = dotenvx.config(env_file, overload=overload)
    _report_errors(result.errors)

    try:
        completed = subprocess.run(command)  # noqa: S603 - executing the user's own command
    except FileNotFoundError:
        typer.echo(f"Unknown command: {command[0]}", err=True)
        raise typer.Exit(1) from None

    raise typer.Exit(completed.returncode)


@app.command(name="get")
def get_command(
    key: str | None = typer.Argument(None, help="Variable name; omit to print all."),  # noqa: B008
    env_file: list[str] = _ENV_FILE_OPTION,
    overload: bool = _OVERLOAD_OPTION,
    format_: str = typer.Option(
        "json",
        "--format",
        help="Output format for all-vars mode: json|shell|colon|eval.",
    ),
    pretty_print: bool = typer.Option(
        False, "--pretty-print", "--pp", help="Pretty-print JSON output."
    ),
) -> None:
    """Print one decrypted value, or all values (SPEC.md §6)."""
    # A snapshot, not the real os.environ: ${VAR} expansion can see real
    # process env vars, but `get` never leaves lasting environment changes.
    result = dotenvx.config(env_file, overload=overload, environ=dict(os.environ))
    _report_errors(result.errors)

    if key is not None:
        typer.echo(result.parsed.get(key, ""))
    elif format_ == "eval":
        typer.echo("\n".join(f"{k}={json.dumps(v)}" for k, v in result.parsed.items()))
    elif format_ == "shell":
        typer.echo(" ".join(f"{k}={v}" for k, v in result.parsed.items()))
    elif format_ == "colon":
        typer.echo(" ".join(f"{k}:{v}" for k, v in result.parsed.items()))
    else:
        typer.echo(json.dumps(result.parsed, indent=2 if pretty_print else None))

    if result.errors:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
