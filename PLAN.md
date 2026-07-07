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
- [x] **M1 — Crypto spike**: generate Node-dotenvx golden fixtures; prove ECIES round-trip interop; resolve §3 ⚠️VERIFY markers. Chose **coincurve + cryptography**. `crypto.py` done; bidirectional interop verified (Node↔Python).
- [x] **M2 — Parser (plaintext)**: `KEY=VALUE`, comments, quotes, `export`, multiline.
- [x] **M3 — Interpolation**: `${VAR}`/`$VAR`, `:-`/`-`, `:+`/`+`, and `$(command)`
  substitution (not deferred — confirmed always-on in real dotenvx).
- [x] **M4 — Library API**: `parse()` / `config()` + precedence / `--overload` into `os.environ`.
- [x] **M5 — Encrypted `.env`**: `DOTENV_PUBLIC_KEY`, `encrypted:` values, `.env.keys` resolution wired into parse/config.
- [~] **M6 — CLI core**: `run`, `get` done; `set` not yet (see notes below).
- [ ] **M7 — CLI crypto**: `encrypt`, `decrypt`, `keypair`.
- [ ] **M8 — CLI utilities**: `ls`, `gitignore`, `precommit`, `prebuild`.
- [ ] **M9 — Compat & polish**: python-dotenv shim, docs, full-suite green.

## Decisions & notes

- **M0**: mypy's analysis target set to 3.10 (tool floor); runtime 3.9 support is
  preserved via `requires-python>=3.9` and the CI 3.9 matrix run. Build backend:
  hatchling. `dotenvx` console script → `dotenvx.cli:app`.
- **M1 (crypto — RESOLVED)**: reverse-engineered from dotenvx 2.1.5 /
  `@dotenvx/primitives` 1.7.1 and proven by round-tripping Node ciphertext.
  Scheme fully documented in SPEC §3: secp256k1 ECIES, uncompressed ephemeral
  key, HKDF-SHA256 over `eph_pub(65)‖shared_point(65)`, AES-256-GCM 16B nonce,
  blob = `eph(65)‖nonce(16)‖tag(16)‖ct` (tag BEFORE ct). Key finding: pyca
  `cryptography` alone is insufficient — full-point secp256k1 ECDH needs
  **`coincurve`**. Two proven dependency options (see DECISION below):
    - **B (recommended)**: `coincurve` + pyca `cryptography` (~15 LOC of glue,
      no pycryptodome). Proven byte-exact.
    - **A**: `eciespy` (`ecies`) — zero crypto code, pulls `coincurve` +
      `pycryptodome`. Proven byte-exact with its default config.
  **Decision: option B (coincurve + cryptography).** `crypto.py` implemented
  and covered 100%; interop proven both directions against the Node CLI (incl.
  emoji/unicode). Golden fixture at `tests/fixtures/node_interop/`.
- **M2/M3 (parsing + interpolation — RESOLVED, no decision needed)**: read
  `@dotenvx/primitives` `src/scan.js`/`src/expand.js`/`src/evaluate.js`/
  `src/parse.js` directly and confirmed every edge case by invoking the real
  module (`node -e "require('@dotenvx/primitives')..."`) — see SPEC.md §2/§4
  for the full resolved algorithm and confirmed vectors. Notable findings that
  corrected earlier assumptions: `\"` inside double-quoted values is **not**
  unescaped (stays literal, a long-standing `dotenv` quirk); `${VAR-x}` and
  `${VAR:-x}` behave identically (no unset-vs-empty distinction); command
  substitution `$(...)` runs **unconditionally by default** (not opt-in) with
  errors silently swallowed. `parser.py` ports `scan`/`expand`/`evaluate`
  faithfully (line-by-line comments cite the JS source); `resolve()` is the
  Python equivalent of `parseWithRing` (minus decryption, which M5 wires in).
  `_PLAIN` key semantics deliberately deferred to M5.
- **M4 (library API)**: `config()` supports repeated `path` (list) mirroring
  dotenvx's repeatable `-f`; multi-file precedence (first-file-wins by
  default, last-file-wins under `--overload`) verified against the real CLI
  (`dotenvx run -f a -f b`). `environ` param defaults to `os.environ` but is
  injectable for tests. `get()`/`set()` intentionally deferred — no
  half-built stubs; they land with the CLI commands that need them (M6).
- **M5 (encrypted `.env`)**: read dotenvx's `conventions/keynames.js` +
  `environment.js` + `resolvers/envs.js` + `helpers/cryptography/*` directly.
  `keys.py` ports `keynames()` (content-first: an existing
  `DOTENV_PUBLIC_KEY*` line in the file wins over the filename convention)
  and `find_private_key()` (checks `environ` first — this is what lets
  `.env.keys` be `chmod a-r` — else a colocated `.env.keys`, else an explicit
  `env_keys_path`). `resolve()` gained a `private_key` param (comma-separated
  candidates tried in order, matching `decryptKeyValue.js`); a value that
  can't be decrypted passes through as `encrypted:...` and command-sub/expand
  are skipped for it (matches the real `encryptedPrefixed` gate). `config()`
  now decrypts automatically and reports `could not decrypt X, Y` in `errors`
  for anything left encrypted. Verified end-to-end against the real M1 Node
  fixture (`tests/test_encrypted_config.py`), not just unit-level crypto.
  `_PLAIN` resolved as a pure naming convention (any key ending `_PLAIN` is
  skipped by `encrypt`/`set` — not implemented yet since those are M7).
- **M6 (CLI core, partial)**: read `cli/actions/run.js`, `get.js`, and
  `helpers/executeCommand.js` directly. `run`: `-- command` via Typer's
  `list[str] | None` argument + `ignore_unknown_options=True`; child process
  inherits the (already-mutated) `os.environ` implicitly — no explicit `env=`
  needed, since `config()` already injected into it, matching how dotenvx's
  own `execa` call is a same-process env inherit, not a distinct merge.
  Exit code propagates via `subprocess.run(...).returncode`. `get`: JSON
  output by default (matches real CLI), `--format shell/colon/eval`, single-
  key lookup prints `""` for a missing key (confirmed from `get.js`); uses a
  **snapshot** of `os.environ` (not the real one) so `${VAR}` expansion still
  sees real env vars without `get` leaving side effects. Verified both via
  pytest (`test_cli_run_get.py`, note: subprocess-inherited stdout needs
  `capfd`, not Typer's `CliRunner.result.stdout`, which only captures Python-
  level `sys.stdout`) and manually against real command execution.
  **`set` deferred** — it requires an "upsert" that mutates a `.env` file's
  raw text in place (add/update one `KEY=value` line while preserving
  comments/formatting elsewhere, generating a keypair + `.env.keys` entry on
  first encryption). That's a distinct chunk of work from `run`/`get`; will
  implement + gate it in the next pass alongside/before M7's `encrypt`/
  `decrypt` (which need the same upsert machinery).
- (log resolved ⚠️VERIFY answers and any dependency changes here as they land)
