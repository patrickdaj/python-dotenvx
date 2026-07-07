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

**RESOLVED** by reading `@dotenvx/primitives` 1.7.1 source (`src/scan.js`,
`src/parse.js`) and confirming empirically against the real CLI/module.

Line regex (JS, `dotenv` + dotenvx's own `scan.js` — identical):
```
^\s*(?:export\s+)?([\w.-]+)(?:\s*=\s*?|:\s+?)(\s*'(?:\\'|[^'])*'|\s*"(?:\\"|[^"])*"|\s*`(?:\\`|[^`])*`|[^#\r\n]+)?\s*(?:#.*)?$
```
applied per-line (multiline mode). Key = `[\w.-]+`. Separator is `=` or a
YAML-style `: ` (colon + whitespace).

- Blank lines and lines not matching the key pattern (e.g. `# comment`) are
  skipped — there's no special-cased "comment line"; it's simply a non-match.
- `export KEY=VALUE` — leading `export ` (+whitespace) is an accepted,
  ignored prefix. **Confirmed.**
- Value trimmed; a trailing unquoted `# comment` is stripped for *all* value
  types (quoted or not), since the trailing `(?:#.*)?` applies after the
  matched value.
- Quoting, by first non-whitespace char of the raw value: `'`, `"`, `` ` ``, or
  none (bare/unquoted).
  - **Multiline**: quoted values may literally contain newlines — the regex's
    `[^']`/`[^"]`/`` [^`] `` classes match `\n` directly, no special handling
    needed. **Confirmed** — this is the entire multiline mechanism.
  - **Double-quoted**: after stripping the outer quotes, `\n`→newline,
    `\r`→CR, **`\t`→tab** are expanded. **`\"` is NOT unescaped** — it stays
    as the literal two characters `\"` in the value (its only role in the
    regex is letting an escaped quote not terminate the string early).
    **Confirmed empirically** — a long-standing quirk inherited from `dotenv`.
  - **Single-quoted**: fully literal — no escape expansion, no interpolation
    (§4 skips values where `quote == "'"`).
  - **Unquoted**: interpolation applies (§4); no escape expansion beyond what
    §4's `\$`→`$` unescaping does.
- Escaping: only `\$` is meaningful (see §4); there is no general backslash
  escaping of other characters.

An **encrypted** `.env` additionally contains:
- A `DOTENV_PUBLIC_KEY[_<ENV>]=<hex>` line (see §3).
- Values that are ciphertext strings prefixed `encrypted:` (see §3.3).
- `_PLAIN`-suffixed keys as a cleartext escape hatch. **RESOLVED**: it's a
  pure key-*naming* convention, nothing more — any key whose name matches
  `/_PLAIN$/` (`isPlainKey.js`) is simply skipped by `encrypt`/`set`, which
  leave its value untouched (`encrypt.js`: `if (isDotenvPublicKey(key) ||
  isPlainKey(key)) { /* don't encrypt */ }`; `set.js`: same check forces
  `noEncrypt`). There's no pairing with a same-named encrypted key — it's
  just "this literal key is never encrypted." Read-side, a `_PLAIN` key needs
  no special handling at all: it was never `encrypted:`-prefixed, so parsing
  treats it like any other plaintext key. Relevant to CLI `encrypt`/`set`
  (M7), not to decryption (M5).

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

The single most interop-critical section. **RESOLVED** against dotenvx 2.1.5 /
`@dotenvx/primitives` 1.7.1 (which bundles `eciesjs`), and confirmed by
round-tripping real Node-produced ciphertext in `tests/fixtures/` (see §9).

### 3.1 Curve & keys
- Curve: **secp256k1**.
- Private key (`DOTENV_PRIVATE_KEY`): 32-byte scalar, **lowercase hex, no
  prefix** (64 hex chars).
- Public key (`DOTENV_PUBLIC_KEY`): **compressed** SEC1 point (33 bytes → 66 hex
  chars, `02`/`03` prefix), lowercase hex. Derived from the private key.

### 3.2 Scheme (ECIES, eciesjs defaults)
Per-value encryption. All parameters below are the confirmed dotenvx defaults:

1. Generate an ephemeral secp256k1 keypair per value.
2. **ECDH**: `shared_point = ephemeral_sk · receiver_pk`, serialized **uncompressed**
   (65 bytes, `0x04 ‖ X ‖ Y`) — the *full point*, not the x-only secret.
3. **KDF**: `key = HKDF-SHA256(IKM, salt="", info="", L=32)` where
   `IKM = ephemeral_pubkey_uncompressed(65) ‖ shared_point(65)`.
   (Empty salt ≡ 32 zero bytes here, since HMAC zero-pads to its block size.)
4. **Symmetric**: **AES-256-GCM**, **16-byte** nonce/IV, **16-byte** tag, no AAD.

**Wire layout of the blob** (confirmed by byte measurement):
```
ephemeral_pubkey (65, uncompressed 0x04‖X‖Y)  ‖  nonce (16)  ‖  tag (16)  ‖  ciphertext (N)
```
Note the **tag precedes the ciphertext**. pyca `cryptography`'s AESGCM expects
`ciphertext ‖ tag`, so reassemble as `ct + tag` when using it.

> Implementation note: pyca `cryptography` alone **cannot** produce this — its
> `exchange(ECDH())` returns only the x-coordinate, and it exposes no raw EC
> point multiplication. secp256k1 point math requires **`coincurve`**
> (libsecp256k1). HKDF + AES-GCM can still come from pyca `cryptography`.
> See PLAN.md M1 decision for the chosen dependency set.

### 3.3 Encrypted value encoding
Each encrypted value in `.env` is `encrypted:` + **standard base64** (with `+`,
`/`, `=` padding) of the §3.2 blob. Node **preserves the original quote style**
around the value: `K=encrypted:…`, `K="encrypted:…"`, `K='encrypted:…'`.

### 3.4 Decryption resolution
**RESOLVED and implemented** (`keys.py` + `parser.resolve`'s `private_key`
param), confirmed end-to-end against the real Node-produced fixture. For a
given key:
1. If the value is `encrypted:…`, find the matching
   `DOTENV_PRIVATE_KEY[_<ENV>]` (via `keys.keynames` + `keys.find_private_key`
   — §2.3) and decrypt. (`_PLAIN` is unrelated to decryption — see §2.1.)
2. Missing private key → dotenvx raises a `missingPrivateKey` error; a wrong key
   raises `wrongPrivateKey` (GCM auth failure). `--ignore`/non-strict behavior
   **⚠️ VERIFY**.

---

## 4. Interpolation / expansion

**RESOLVED** by reading `@dotenvx/primitives` `src/expand.js`, `src/evaluate.js`,
and `src/parse.js` (`parseWithRing`), confirmed empirically. Applies to
unquoted and double-quoted values; **skipped entirely when `quote == "'"`**
(single-quoted is fully literal).

### Per-value pipeline (order matters), from `parseWithRing`:
1. **Precedence** (§5): if not `--overload` and the name already exists in
   `process_env`, the file value is replaced by the **existing process_env
   value** before anything below runs.
2. **Decryption** (§3), if the value is `encrypted:…`.
3. **Command substitution** — attempted only if: value isn't
   `encrypted:…`, `quote != "'"`, and (the name isn't in `process_env` **or**
   `process_env[name] == parsedValue` at this point). Regex `\$\(([^)]+(?:\)[^(]*)*)\)`
   finds all `$(...)` spans; each is run via a subprocess shell
   (`execSync(command, {env: {...process_env, ...running_parsed}})`) and
   replaced with stdout, **trailing `\r`/`\n` chomped**. **Runs unconditionally
   by default — not opt-in.** Errors are **caught and swallowed**: on failure
   the value is left as its pre-substitution string (no exception propagates).
   Security implication: a malicious `.env` can execute arbitrary shell
   commands merely by being loaded — document this prominently.
4. **`${VAR}` / `$VAR` expansion** — attempted only if step 3 did **not**
   change the value, and only if `quote != "'"` and (`process_env[name]` is
   falsy **or** `--overload`). Regex:
   `(?<!\\)\$\{([^{}]+)\}|(?<!\\)\$([A-Za-z_][A-Za-z0-9_]*)` — both braced
   and braceless forms are supported; a preceding `\` suppresses expansion of
   that occurrence.
   - Lookup env is `{**running_parsed, **process_env}` by default (existing
     process env wins over same-file earlier vars), or
     `{**process_env, **running_parsed}` under `--overload` (file wins).
   - Operator inside the braces/name — split on the *first* of `:+`, `+`,
     `:-`, `-` (checked in that order):
     - `:+` / `+` (**no behavioral difference between the two**): result is
       the text after the operator if the var is **truthy** (set and
       non-empty) in the lookup env, else `""`.
     - `:-` / `-` (**no behavioral difference**): result is the var's value if
       truthy, else the text after the operator (i.e. unset **and** empty
       string both trigger the default — dotenvx does not distinguish
       `${VAR-x}` from `${VAR:-x}`).
     - No operator: plain substitution; `""` if unset.
   - A self-reference guard (`result === env[name]` after substitution) and a
     "literal contains an unexpanded pattern" guard (for a same-named
     single-quoted var whose raw text still looks like `${...}`) stop the
     re-scan loop to avoid infinite loops on self-referential/literal values.
   - After expansion (whether or not a substitution happened), `\$` is
     globally replaced with a literal `$` (`resolveEscapeSequences`). This is
     the *only* place backslash-escaping happens for interpolation, and it
     runs even when quote is `'` is false but no `${...}`/`$VAR` was present.
5. Result becomes `running_parsed[name]` (visible to later lines' expansion)
   and the final `parsed[name]` (returned value).

### Confirmed test vectors (see `tests/test_interpolation.py`)
```
A='raw ${NOTHING} literal'        # single-quoted -> no expansion
B="${A}"                          # -> value of A (unquoted/double allowed)
C="${UNSET:-fallback}"            # -> "fallback"
D="${UNSET:+alt}"                 # -> ""            (UNSET is falsy)
E="${A:+alt}"                     # -> "alt"          (A is truthy)
F="\${ESCAPED}"                   # -> "${ESCAPED}"   (escaped, not expanded)
G="$(echo cmd-sub-works)"         # -> "cmd-sub-works"
```

---

## 5. Loading & precedence

- Default file is `.env` in the cwd.
- `-f <path>` may be repeated; multiple files load in order.
- **Precedence** (confirmed empirically, §4 step 1): by default, if a name
  already exists in `process_env` (`os.environ`), that value wins over the
  file's — the file value is discarded before interpolation even runs.
  `--overload` flips this so the file's (interpolated) value wins.
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

**Resolved** (crossed off as milestones landed — see PLAN.md for how each was
confirmed): ECIES parameters/wire format (§3, M1); `_PLAIN` semantics (§2.1,
M5 research — it's just a naming convention); command-substitution default
(§4, M3 — on by default, errors swallowed); default precedence /
`--overload` naming (§5, M3/M4 — confirmed against the real CLI).

Still open:

1. `--ignore`/non-strict behavior for decryption errors (§3.4) — CLI-level,
   relevant once `run`/`--strict` land (M6).
2. Which `--convention` presets to support in v1 (§5) — deferred until CLI
   flag work (M6+).
3. python-dotenv compatibility surface — how far to go (§7) — decide when
   implementing the library API's polish pass (M9).
4. `.env.vault` legacy support — in or out (§1) — decide if/when a parity
   target needs it; default remains skip.
