# SPEC.md

The behavior contract for `python-dotenvx` — **what** we build. Process,
tooling, and conventions live in [`CLAUDE.md`](./CLAUDE.md).

This is a living document. Wherever a detail must match Node `dotenvx`
byte-for-byte and hasn't yet been confirmed against the upstream source, it is
marked **⚠️ VERIFY** — resolve these by reading upstream / round-tripping real
files before relying on them. Upstream reference:
<https://github.com/dotenvx/dotenvx>.

---

## 1. Scope & compatibility

### Goals
- Full parity with the Node `dotenvx` **CLI** (commands, flags, exit codes).
- A Python **library API** that is a superset-compatible replacement for
  `python-dotenv` (`load_dotenv`-style), plus dotenvx's `config`/`parse`/
  `get`/`set`.
- **Cryptographic interop**: files encrypted by Node dotenvx decrypt in Python
  and vice versa; keypairs are interchangeable.

### Non-goals (v1)
- **Armor** and other premium/hosted features (off-device keys, team sharing,
  audit) — out of scope.
- 100% identical log formatting/coloring — we match *semantics* (what is
  printed, exit codes), not necessarily every escape code.
- Reimplementing `.env.vault` (legacy) — **⚠️ VERIFY** whether any parity target
  still needs it; default is to skip unless required.

---

## 2. File formats

### 2.1 `.env` (plaintext or encrypted)

A line-oriented file of `KEY=VALUE` pairs. Parsing rules to match dotenv/dotenvx:

- Blank lines and lines beginning with `#` are ignored.
- `KEY=VALUE`; whitespace around `=` and around the value is trimmed (unless
  quoted).
- Values may be unquoted, single-quoted, or double-quoted.
  - **Double quotes**: support escape sequences (`\n`, `\t`, `\"`, …) and
    variable expansion (see §4).
  - **Single quotes**: literal; no expansion, no escapes.
  - **Unquoted**: trailing inline `# comment` is stripped; expansion applies.
- Multiline values via quoted strings spanning lines. **⚠️ VERIFY** exact
  multiline rules against dotenvx (it extends dotenv here).
- `export KEY=VALUE` — leading `export ` is accepted and ignored. **⚠️ VERIFY**.

An **encrypted** `.env` additionally contains:
- A `DOTENV_PUBLIC_KEY[_<ENV>]=<hex>` line (see §3).
- Values that are ciphertext strings prefixed `encrypted:` (see §3.3).
- Optionally `_PLAIN`-suffixed keys holding cleartext overrides. **⚠️ VERIFY**
  exact semantics of the `_PLAIN` suffix.

### 2.2 `.env.keys`

Holds **private** keys, never committed. Format:

```
DOTENV_PRIVATE_KEY[_<ENV>]=<hex-private-key>
```

- One entry per environment (`DOTENV_PRIVATE_KEY`, `DOTENV_PRIVATE_KEY_PRODUCTION`,
  …). The `_<ENV>` suffix is derived from the `.env.<env>` filename.
- May be `chmod a-r` and still work when the value is already in the process
  env. **⚠️ VERIFY** resolution order (file vs. `os.environ`).
- Multiple private keys may be supplied (comma-separated / repeated) for
  monorepos. **⚠️ VERIFY** the exact multi-key input format and the `-fk` flag.

### 2.3 Environment naming

`.env` → default; `.env.production` → `PRODUCTION`; `.env.ci` → `CI`. The
uppercased env name is the suffix on `DOTENV_PUBLIC_KEY_*` / `DOTENV_PRIVATE_KEY_*`.
**⚠️ VERIFY** the exact filename→suffix transform (case, dots, hyphens).

---

## 3. Cryptography (ECIES)

The single most interop-critical section. Everything here must match Node
dotenvx exactly.

### 3.1 Curve & keys
- Curve: **secp256k1**.
- Private key: 32-byte scalar, encoded as lowercase hex. **⚠️ VERIFY** length/
  encoding (with or without prefix).
- Public key: **compressed** SEC1 point (33 bytes), lowercase hex. **⚠️ VERIFY**
  compressed vs. uncompressed.

### 3.2 Scheme
ECIES, matching the `eciesjs` defaults Node dotenvx uses:
- Generate an ephemeral secp256k1 keypair per encryption.
- ECDH between the ephemeral private key and the recipient public key →
  shared secret.
- **KDF** derives a symmetric key from the shared secret. **⚠️ VERIFY** the KDF
  (HKDF-SHA256?), salt/info parameters, and whether the ephemeral public key is
  hashed in.
- **Symmetric cipher**: **AES-256-GCM**. **⚠️ VERIFY** nonce length (12 vs 16),
  tag length (16), and AAD (likely none).
- **Wire layout** of the encrypted blob: `ephemeral_pubkey || nonce || tag ||
  ciphertext` (order/segmentation) — **⚠️ VERIFY** exact concatenation order.

> These must be pinned by reading `eciesjs` + dotenvx and confirmed with a
> round-trip test against real Node-produced ciphertext. Do not ship crypto on
> assumptions.

### 3.3 Encrypted value encoding
- Each encrypted value in `.env` is the string `encrypted:` + base64 of the
  blob from §3.2. **⚠️ VERIFY** the base64 variant (standard vs. url-safe) and
  the exact prefix.

### 3.4 Decryption resolution
For a given key:
1. If a `_PLAIN` override / plaintext value is present, use it. **⚠️ VERIFY**.
2. Else if the value is `encrypted:…`, find the matching
   `DOTENV_PRIVATE_KEY[_<ENV>]` and decrypt.
3. Missing private key → error unless `--ignore`/non-strict suppresses it.
   **⚠️ VERIFY** default behavior.

---

## 4. Interpolation / expansion

Applied to unquoted and double-quoted values (not single-quoted):

- `${VAR}` / `$VAR` — substitute from already-parsed vars, then process env.
  **⚠️ VERIFY** precedence (file vs. process env) and whether `$VAR` (braceless)
  is supported.
- `${VAR:-default}` — use `default` if `VAR` is unset **or empty**.
- `${VAR-default}` — use `default` if `VAR` is **unset** only. **⚠️ VERIFY**
  support.
- `${VAR:+alt}` — use `alt` if `VAR` is set (and non-empty).
- **Command substitution**: `$(command)` (and inside defaults, e.g.
  `${VAR:-$(whoami)}`) is executed via the shell and replaced with stdout.
  **⚠️ VERIFY** whether this is on by default, opt-in, and how errors are
  handled. Security note: document that command substitution runs shell
  commands from the `.env` file.
- Escaping: `\$` produces a literal `$`. **⚠️ VERIFY**.

---

## 5. Loading & precedence

- Default file is `.env` in the cwd.
- `-f <path>` may be repeated; multiple files load in order.
- **Precedence**: by default an already-set variable is **not** overwritten
  (first-wins / existing `os.environ` wins). `--overload` (a.k.a. `--override`)
  makes later sources win. **⚠️ VERIFY** exact default and flag names.
- `--convention <name>` applies a framework loading pattern (e.g. `nextjs`,
  `flow`) that expands to a specific ordered set of files. **⚠️ VERIFY** the
  supported conventions and their file orders.
- `-fk <path>` / custom `.env.keys` location for keys. **⚠️ VERIFY**.

---

## 6. CLI reference

Invocation: `dotenvx <command> [flags]`. Each command below lists intended
behavior; flags and exit codes marked **⚠️ VERIFY** must be confirmed against
`dotenvx <command> --help` upstream.

### Global flags
`--verbose`, `--debug`, `--quiet`, `--log-level <lvl>`, `--strict`,
`--ignore <type>`, `-f/--env-file`, `--overload`, `-fk/--env-keys-file`.
**⚠️ VERIFY** the full set and their scoping (global vs. per-command).

### `run`
`dotenvx run [-f …] [--overload] [--] <command> [args…]`
Load + decrypt env, merge into the child process environment, exec `<command>`,
and propagate its exit code. This is the primary command.

### `get`
`dotenvx get [KEY] [-f …] [--all] [--format json|shell|…]`
Print one decrypted value, or all values. **⚠️ VERIFY** output formats and
whether missing key is empty output vs. error.

### `set`
`dotenvx set KEY VALUE [-f …] [--plain]`
Add/update `KEY`, **encrypting the value** in place using the file's public key
(generating a keypair + `.env.keys` entry if none exists). `--plain` writes
cleartext. **⚠️ VERIFY** flag name and keypair-bootstrap behavior.

### `encrypt`
`dotenvx encrypt [-f …] [-k KEY…]`
Encrypt plaintext values in the target file(s), inserting `DOTENV_PUBLIC_KEY`
and writing private keys to `.env.keys`. Idempotent on already-encrypted values.
**⚠️ VERIFY** `-k` (encrypt only specific keys) and stdout mode.

### `decrypt`
`dotenvx decrypt [-f …] [-k KEY…]`
Inverse of `encrypt`: replace `encrypted:…` values with plaintext using the
private key. **⚠️ VERIFY** in-place vs. stdout, and `-k`.

### `keypair`
`dotenvx keypair [KEY] [-f …] [--format json]`
Print the public/private keypair(s) for the file/environment. **⚠️ VERIFY**
output shape.

### `ls`
`dotenvx ls [directory] [-f glob]`
List `.env*` files in the tree. **⚠️ VERIFY** default globs and output.

### `gitignore`
Append dotenvx's recommended `.env*` ignore patterns (keeping `.env.example`
etc.) to `.gitignore`. **⚠️ VERIFY** exact patterns.

### `precommit`
Install / check a git pre-commit hook that blocks committing plaintext secrets.
`--install` writes the hook. **⚠️ VERIFY** flags and hook contents.

### `prebuild`
Guard against `.env` files being baked into a Docker image (intended to run in a
Dockerfile). **⚠️ VERIFY** exact behavior/exit semantics.

---

## 7. Library API

Python-importable surface (`import dotenvx`):

- `config(path=".env", *, override=False, …) -> dict` — load + decrypt into
  `os.environ`; return the parsed mapping. Mirrors Node `config()` /
  python-dotenv `load_dotenv`. **⚠️ VERIFY** kwargs.
- `parse(src: str | bytes) -> dict[str, str]` — parse (and decrypt if keys are
  available) without touching `os.environ`.
- `get(key, *, path=".env") -> str | None` — decrypt and return one value.
- `set(key, value, *, path=".env", encrypt=True) -> None` — write a value.
- Consider a `python-dotenv` compatibility shim (`load_dotenv`,
  `dotenv_values`) so existing code can switch imports. **⚠️ VERIFY** desired
  surface.

All functions fully type-annotated; return types stable across CLI and library.

---

## 8. Exit codes & error handling

- `run` returns the child's exit code.
- Other commands: `0` success; non-zero on error. **⚠️ VERIFY** the specific
  codes dotenvx uses (missing key, decrypt failure, bad file).
- `--strict` turns warnings into failures; `--ignore <type>` suppresses named
  error classes. **⚠️ VERIFY** the taxonomy of error types.
- Error messages should be actionable (dotenvx prints suggested fixes) — match
  the *intent*, and where cheap, the wording.

---

## 9. Test strategy (contract-level)

- **Golden interop fixtures**: commit real `.env` + `.env.keys` pairs generated
  by Node dotenvx (throwaway keys only) and assert Python decrypts them to the
  expected plaintext; assert Python-encrypted output decrypts under Node in CI
  where feasible.
- **Property tests** for the parser/interpolator against edge cases (quotes,
  escapes, nested expansion).
- **CLI tests** invoking `dotenvx` end-to-end via subprocess, asserting stdout,
  files written, and exit codes.
- Every **⚠️ VERIFY** above becomes a concrete test once resolved.

---

## 10. Open questions

Consolidated list of things to resolve before/while implementing (all the
**⚠️ VERIFY** markers, plus):

1. Exact ECIES parameters and wire format (§3) — **highest priority**; blocks
   all crypto.
2. `_PLAIN` suffix semantics and precedence (§2.1, §3.4).
3. Command-substitution default (on/off) and its security posture (§4).
4. Default precedence + exact `--overload`/`--override` naming (§5).
5. Which conventions to support in v1 (§5).
6. python-dotenv compatibility surface — how far to go (§7).
7. `.env.vault` legacy support — in or out (§1).
