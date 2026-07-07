# PLAN.md — build tracker

Durable, committed progress tracker for the incremental build. The environment
is ephemeral, so this file (not memory) is how the loop resumes across sessions.
See [`SPEC.md`](./SPEC.md) for behavior and [`CLAUDE.md`](./CLAUDE.md) for
tooling.

## Loop contract (per milestone)

1. Write failing tests first (from the relevant SPEC section) → red
2. Implement the minimum to pass
3. `uv run pytest` green
4. Gate: `uv run ruff check .` + `uv run ruff format --check .` + `uv run mypy src` all clean
5. Commit the slice, tick it off here
6. Advance

No milestone advances until steps 3 + 4 are green.

## Milestones

- [x] **M0 — Scaffold**: `pyproject.toml` (uv, Typer, cryptography, pytest, pytest-cov, ruff, mypy), `src/dotenvx/` skeleton, CI, `dotenvx --version` + one passing test.
- [ ] **M1 — Crypto spike**: generate Node-dotenvx golden fixtures; prove ECIES round-trip interop; resolve §3 ⚠️VERIFY markers; confirm/replace `cryptography`.
- [ ] **M2 — Parser (plaintext)**: `KEY=VALUE`, comments, quotes, `export`, multiline.
- [ ] **M3 — Interpolation**: `${VAR}`, `${VAR:-default}`, `${VAR:+alt}` (command substitution deferred).
- [ ] **M4 — Library API**: `parse()` / `config()` + precedence / `--overload` into `os.environ`.
- [ ] **M5 — Encrypted `.env`**: `DOTENV_PUBLIC_KEY`, `encrypted:` values, `.env.keys` resolution wired into parse/config.
- [ ] **M6 — CLI core**: `run`, `get`, `set`.
- [ ] **M7 — CLI crypto**: `encrypt`, `decrypt`, `keypair`.
- [ ] **M8 — CLI utilities**: `ls`, `gitignore`, `precommit`, `prebuild`.
- [ ] **M9 — Compat & polish**: python-dotenv shim, docs, full-suite green.

## Decisions & notes

- **M0**: mypy's analysis target set to 3.10 (tool floor); runtime 3.9 support is
  preserved via `requires-python>=3.9` and the CI 3.9 matrix run. Build backend:
  hatchling. `dotenvx` console script → `dotenvx.cli:app`.
- (log resolved ⚠️VERIFY answers and any dependency changes here as they land)
