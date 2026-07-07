# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository — **how we
work here**. For **what we're building** (behavior, formats, crypto, CLI
semantics), see [`SPEC.md`](./SPEC.md).

## Project goal

`python-dotenvx` is a Python port of [dotenvx](https://dotenvx.com) — "a better
dotenv." The aim is **feature parity with the Node.js `dotenvx` library and
CLI**, delivered as an idiomatic, modern Python package.

Two surfaces, one behavior:

- **CLI** — `dotenvx run -- <cmd>`, `dotenvx encrypt`, etc. Drop-in compatible
  with the Node CLI's flags and file formats.
- **Library API** — `config()`, `parse()`, `get()`, `set()` for use from Python
  code; a superset-compatible replacement for `python-dotenv`.

The north star: a `.env` file encrypted by Node `dotenvx` must decrypt with
`python-dotenvx` and vice versa. **File formats and crypto must be
byte-for-byte interoperable.** The exact contract lives in `SPEC.md`; when in
doubt, defer to what Node `dotenvx` actually does — match its output, exit
codes, and error messages where practical.

## Tech stack (locked)

- **Python 3.9+** — support floor is 3.9; develop on the latest stable.
- **uv** — the single tool for the venv, dependencies, locking, and running
  commands. No pip, poetry, or hand-managed venvs.
- **Typer** — CLI framework (typed commands + generated help).
- **cryptography** (pyca) — secp256k1 / ECDH / AES-GCM primitives for the ECIES
  scheme. (If exact interop with Node's `eciesjs` proves awkward, revisit —
  but `cryptography` is the default.)
- **pytest** (+ `pytest-cov`) — all tests.
- **ruff** — linting and formatting (replaces black + flake8 + isort).
- **mypy** — static type checking; the codebase is fully type-annotated.

## Project layout (target)

```
src/dotenvx/          # `src` layout — import the installed package, not source
  __init__.py         # public API: config, parse, get, set
  cli.py              # Typer CLI entrypoint
  crypto.py           # ECIES encrypt/decrypt, keypair generation
  parser.py           # .env parsing + interpolation
  ...
tests/                # pytest, mirrors src/ structure
pyproject.toml        # single source of config (uv, ruff, mypy, pytest)
```

Import/CLI name is `dotenvx` (parity with Node); the PyPI distribution is
published as `python-dotenvx`.

## Development commands

```bash
uv sync                       # create/refresh the venv from the lockfile
uv run pytest                 # run the test suite
uv run pytest -k name         # run a subset
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy src               # type-check
uv run dotenvx --help         # exercise the CLI locally
uv add <pkg>                  # add a runtime dependency
uv add --dev <pkg>            # add a dev dependency
```

Prefer `uv run <tool>` over activating the venv so the environment is always
the locked one.

## Conventions & best practices

- **Everything through `pyproject.toml`** — deps, ruff, mypy, pytest config. No
  `setup.py`, `setup.cfg`, or standalone tool configs.
- **`src` layout** so tests run against the installed package, not the source
  tree.
- **Full type annotations**; mypy runs clean. No `Any` without a reason.
- **Tests first-class**: every command and crypto path covered. Include
  **cross-compatibility fixtures** — real `.env`/`.env.keys` pairs produced by
  Node dotenvx — to prove interop.
- **Small, pure functions** for parsing and crypto; keep I/O and process
  execution at the edges.
- **Never commit secrets.** `.env.keys` and plaintext `.env` files are
  gitignored. Test fixtures use throwaway keys only.
- **Meaningful commits**; keep the branch history clean.
- Match dotenvx's user-facing strings and exit codes where it aids drop-in use.

## Status

Greenfield. Repo is empty. The first task is scaffolding (`pyproject.toml`,
`src` layout, tooling, CI), then implementing features against the parity
checklist in `SPEC.md`. Update this file when *tooling/process* decisions
change; update `SPEC.md` when *behavior* is pinned down.
