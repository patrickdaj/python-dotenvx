# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## Project goal

`python-dotenvx` is a Python port of [dotenvx](https://dotenvx.com) — "a better
dotenv." The aim is **feature parity with the Node.js `dotenvx` library and
CLI**, delivered as an idiomatic, modern Python package.

Two surfaces, one behavior:

- **CLI** — `dotenvx run -- <cmd>`, `dotenvx encrypt`, etc. Cross-language,
  drop-in compatible with the Node CLI's flags and file formats.
- **Library API** — `config()`, `parse()`, `get()`, `set()` for use from Python
  code, a superset-compatible replacement for `python-dotenv`.

The north star: a `.env` file encrypted by Node `dotenvx` must decrypt with
`python-dotenvx` and vice versa. **File formats and crypto must be
byte-for-byte interoperable.**

## Feature parity checklist

Track against upstream dotenvx. Core scope:

### CLI commands
- `run` — inject env vars, then exec a command (`dotenvx run -- npm start`)
- `get` — read one or all decrypted values
- `set` — add/update a value, encrypting it in place
- `encrypt` / `decrypt` — convert `.env` between plaintext and encrypted form
- `keypair` — print the public/private keypair
- `ls` — list `.env*` files in the tree
- `gitignore` — append `.env` patterns to `.gitignore`
- `precommit` — install a git hook blocking plaintext `.env` commits
- `prebuild` — guard against `.env` files baked into Docker images

### Encryption model (must match upstream exactly)
- Elliptic-curve crypto over **secp256k1** (same curve as Bitcoin).
- **ECIES**: ephemeral keypair per encryption, ECDH shared secret, **AES-256-GCM**
  for the payload.
- `DOTENV_PUBLIC_KEY` lives in the `.env` file (safe to commit); encrypted
  values are prefixed `encrypted:`.
- `DOTENV_PRIVATE_KEY` lives in **`.env.keys`** (never committed). Multiple keys
  and `_PLAIN`-suffixed cleartext overrides are supported.
- Encrypted `.env` files are safe to commit; decryption requires only the
  private key.

### Loading & interpolation
- Multiple files via repeated `-f` flags; `--overload` controls precedence.
- Variable expansion: `${VAR}`, defaults `${VAR:-fallback}`, alternates
  `${VAR:+alt}`, and command substitution `${VAR:-$(cmd)}`.
- Convention loaders (`--convention`) for framework patterns (e.g. Next.js,
  dotenv-flow).
- Flags to mirror: `--verbose`, `--debug`, `--quiet`, `--log-level`, `--strict`,
  `--ignore`, `--overload`, `-fk` (custom `.env.keys` path).

When in doubt about behavior, **defer to what Node `dotenvx` actually does** —
match its output, exit codes, and error messages where practical.

## Tech stack

- **Python** — target 3.9+ (confirm floor before pinning); develop on latest.
- **uv** — the single tool for env, dependencies, locking, and running. No pip,
  poetry, or manual venvs.
- **pytest** — all tests. Coverage via `pytest-cov`.
- **ruff** — linting and formatting (replaces black + flake8 + isort).
- **mypy** — static type checking; the codebase is fully type-annotated.
- **click** or **typer** — CLI framework (decide before building; typer gives
  typed commands + good help output for free).
- **cryptography** (pyca) — secp256k1 / ECDH / AES-GCM primitives. Verify it
  exposes secp256k1; fall back to `coincurve`/`ecies` if needed for exact
  interop.

## Project layout (target)

```
src/dotenvx/          # `src` layout — import only the installed package
  __init__.py         # public API: config, parse, get, set
  cli.py              # CLI entrypoint
  crypto.py           # ECIES encrypt/decrypt, keypair generation
  parser.py           # .env parsing + interpolation
  ...
tests/                # pytest, mirrors src/ structure
pyproject.toml        # single source of config (uv, ruff, mypy, pytest)
```

Package name TBD — `dotenvx` for CLI/import parity with Node, published to PyPI
under a name to be decided (e.g. `python-dotenvx`).

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

Prefer `uv run <tool>` over activating the venv so the environment is always the
locked one.

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

Greenfield. Repo is empty — the first task is scaffolding (`pyproject.toml`, `src`
layout, tooling, CI), then implementing features against the parity checklist.
Update this file as decisions are locked in (Python floor, CLI framework, crypto
library).
