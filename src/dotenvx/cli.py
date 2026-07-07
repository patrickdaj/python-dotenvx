"""Typer CLI entrypoint for dotenvx.

Commands are added across milestones (see PLAN.md / SPEC.md §6). For now the
app exists with `--version` so the entrypoint is wired and testable.
"""

from __future__ import annotations

import typer

from dotenvx import __version__

app = typer.Typer(
    name="dotenvx",
    help="A better dotenv — run anywhere, multi-env, encrypted.",
    no_args_is_help=True,
    add_completion=False,
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


if __name__ == "__main__":
    app()
