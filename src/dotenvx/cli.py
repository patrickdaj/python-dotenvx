"""Typer CLI entrypoint for dotenvx.

Commands are added across milestones (see PLAN.md / SPEC.md §6).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import typer

import dotenvx
from dotenvx import __version__, ext, transforms

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


_ENV_KEYS_FILE_OPTION = typer.Option(
    None,
    "-fk",
    "--env-keys-file",
    help="Custom .env.keys path (default: colocated .env.keys).",
)


@app.command(name="set")
def set_command(
    key: str = typer.Argument(..., help="Variable name."),  # noqa: B008
    value: str = typer.Argument(..., help="Value to set."),  # noqa: B008
    env_file: list[str] = _ENV_FILE_OPTION,
    plain: bool = typer.Option(
        False, "--plain", help="Store the value in plaintext (no encryption)."
    ),
    env_keys_file: str | None = _ENV_KEYS_FILE_OPTION,
) -> None:
    """Add/update KEY=VALUE in .env file(s), encrypting by default (SPEC.md §6)."""
    changed_files = []
    for path in env_file:
        result = dotenvx.set(
            key, value, path=path, encrypt=not plain, env_keys_path=env_keys_file
        )
        if result.changed:
            changed_files.append(path)

    verb = "set" if plain else "encrypted"
    if changed_files:
        typer.echo(f"dotenvx: {verb} {key} ({', '.join(changed_files)})")
    else:
        typer.echo(f"dotenvx: no change ({', '.join(env_file)})")


@app.command(name="encrypt")
def encrypt_command(
    env_file: list[str] = _ENV_FILE_OPTION,
    env_keys_file: str | None = _ENV_KEYS_FILE_OPTION,
) -> None:
    """Encrypt every plaintext value in .env file(s) in place (SPEC.md §6)."""
    changed_files = []
    for path in env_file:
        result = transforms.encrypt_file(path, env_keys_path=env_keys_file)
        if result.changed:
            changed_files.append(path)

    if changed_files:
        typer.echo(f"dotenvx: encrypted ({', '.join(changed_files)})")
    else:
        typer.echo(f"dotenvx: no change ({', '.join(env_file)})")


@app.command(name="decrypt")
def decrypt_command(
    env_file: list[str] = _ENV_FILE_OPTION,
    env_keys_file: str | None = _ENV_KEYS_FILE_OPTION,
) -> None:
    """Decrypt every ``encrypted:`` value in .env file(s) in place (SPEC.md §6)."""
    changed_files = []
    for path in env_file:
        result = transforms.decrypt_file(path, env_keys_path=env_keys_file)
        if result.changed:
            changed_files.append(path)

    if changed_files:
        typer.echo(f"dotenvx: decrypted ({', '.join(changed_files)})")
    else:
        typer.echo(f"dotenvx: no change ({', '.join(env_file)})")


@app.command(name="keypair")
def keypair_command(
    key: str | None = typer.Argument(  # noqa: B008
        None, help="A specific key name (e.g. DOTENV_PRIVATE_KEY); omit for all."
    ),
    env_file: list[str] = _ENV_FILE_OPTION,
    env_keys_file: str | None = _ENV_KEYS_FILE_OPTION,
    format_: str = typer.Option(
        "json", "--format", help="Output format: json|shell|colon."
    ),
    pretty_print: bool = typer.Option(
        False, "--pretty-print", "--pp", help="Pretty-print JSON output."
    ),
) -> None:
    """Print the public/private keypair for .env file(s) (SPEC.md §6)."""
    out: dict[str, str | None] = {}
    for path in env_file:
        kp = transforms.get_keypair(path, env_keys_path=env_keys_file)
        out[kp.public_key_name] = kp.public_key
        out[kp.private_key_name] = kp.private_key

    if key is not None:
        typer.echo(out.get(key) or "")
    elif format_ == "shell":
        typer.echo(" ".join(f"{k}={v or ''}" for k, v in out.items()))
    elif format_ == "colon":
        typer.echo(" ".join(f"{k}:{v or ''}" for k, v in out.items()))
    else:
        typer.echo(json.dumps(out, indent=2 if pretty_print else None))


@app.command(name="ls")
def ls_command(
    directory: str = typer.Argument(".", help="Directory to list .env files from."),  # noqa: B008
    env_file: list[str] = typer.Option(  # noqa: B008
        [".env*"], "-f", "--env-file", help="Pattern(s) to include."
    ),
    exclude_env_file: list[str] = typer.Option(  # noqa: B008
        [], "-ef", "--exclude-env-file", help="Pattern(s) to exclude."
    ),
) -> None:
    """Print all .env files found under DIRECTORY (SPEC.md §6)."""
    for filepath in ext.ls(
        directory, env_file=env_file, exclude_env_file=exclude_env_file
    ):
        typer.echo(filepath)


@app.command(name="gitignore")
def gitignore_command(
    pattern: list[str] = typer.Option(  # noqa: B008
        [".env*"], "--pattern", help="Pattern(s) to ignore."
    ),
) -> None:
    """Append PATTERN(s) to .gitignore (and .dockerignore/.npmignore/.vercelignore)."""
    result = ext.gitignore(pattern)
    if result.changed_files:
        typer.echo(f"dotenvx: ignored {pattern} ({', '.join(result.changed_files)})")
    for filename in result.unchanged_files:
        typer.echo(f"dotenvx: no change ({filename})")


@app.command(name="precommit")
def precommit_command(
    directory: str = typer.Argument(  # noqa: B008
        ".", help="Directory to prevent committing .env files from."
    ),
    install: bool = typer.Option(
        False, "-i", "--install", help="Install to .git/hooks/pre-commit."
    ),
) -> None:
    """Prevent committing plaintext .env files (SPEC.md §6)."""
    if install:
        typer.echo(f"dotenvx: {ext.install_precommit_hook(Path(directory) / '.git')}")
        return

    result = ext.precommit_check(directory)
    for warning in result.warnings:
        typer.echo(f"dotenvx: warning: {warning}", err=True)
    typer.echo(f"dotenvx: {result.message}")
    if not result.ok:
        raise typer.Exit(1)


@app.command(name="prebuild")
def prebuild_command(
    directory: str = typer.Argument(".", help="Directory to check."),  # noqa: B008
) -> None:
    """Prevent plaintext .env files from being baked into a Docker image."""
    result = ext.prebuild_check(directory)
    for warning in result.warnings:
        typer.echo(f"dotenvx: warning: {warning}", err=True)
    typer.echo(f"dotenvx: {result.message}")
    if not result.ok:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
