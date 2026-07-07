# python-dotenvx

A Python port of [dotenvx](https://dotenvx.com) — *a better dotenv*: run
anywhere, multiple environments, and built-in encryption. Files and keys are
byte-for-byte interoperable with the Node.js `dotenvx` CLI: a `.env` file
encrypted by Node `dotenvx` decrypts with `python-dotenvx`, and vice versa.

> **Status: pre-alpha, under active construction.** Core parsing,
> interpolation, encryption, and the `run`/`get` CLI commands work today (see
> [`PLAN.md`](./PLAN.md) for what's built vs. in progress). `set`,
> `encrypt`/`decrypt`/`keypair`, and the remaining CLI commands are still
> being implemented. See [`SPEC.md`](./SPEC.md) for the full behavior
> contract and [`CLAUDE.md`](./CLAUDE.md) for the development setup.

## Install

```bash
uv add python-dotenvx     # once published
# or, from a checkout:
uv sync
```

## CLI usage

Run a command with variables from `.env` injected into its environment:

```bash
echo 'API_KEY=abc123' > .env
uv run dotenvx run -- python my_script.py
```

Load multiple files (earlier files win, unless `--overload`):

```bash
uv run dotenvx run -f .env -f .env.production --overload -- npm start
```

Read a value without running anything:

```bash
uv run dotenvx get API_KEY        # -> abc123
uv run dotenvx get                # -> {"API_KEY": "abc123"}  (JSON, all vars)
uv run dotenvx get --format shell # -> API_KEY=abc123
```

## Library usage

```python
import dotenvx

# Load .env into os.environ (like python-dotenv's load_dotenv)
result = dotenvx.config()
print(result.parsed)    # everything read from the file(s)
print(result.injected)  # what actually got written into os.environ
print(result.errors)    # e.g. ["missing file (.env)"]

# Parse without touching os.environ
values = dotenvx.parse("API_KEY=abc123\nGREETING=Hello ${NAME:-World}\n")
# -> {"API_KEY": "abc123", "GREETING": "Hello World"}
```

`config()` accepts a list of paths (mirroring the CLI's repeatable `-f`), an
`overload` flag, and an `environ` mapping (defaults to `os.environ`; pass a
plain `dict` in tests to avoid touching the real process environment).

## `.env` syntax

```bash
# comments and blank lines are ignored
KEY=value
export KEY=value          # `export ` prefix is accepted and ignored
QUOTED='single: literal, no expansion'
INTERPOLATED="hello ${KEY}"
DEFAULTED="${MISSING:-fallback}"
MULTILINE="line one
line two"
COMMAND_SUB="$(whoami)"    # shell command substitution
```

`${VAR}` / `$VAR` expansion, `${VAR:-default}` / `${VAR:+alt}`, and
`$(command)` substitution are all supported — see [`SPEC.md` §4](./SPEC.md)
for the exact rules (precedence vs. already-set environment variables,
escaping with `\$`, etc.).

## Encryption

`.env` files can hold encrypted secrets safe to commit, decrypted with a
private key kept out of version control:

```bash
# produced by dotenvx (Node or Python) — same format either way:
cat .env
#   DOTENV_PUBLIC_KEY="02e7c649..."
#   API_KEY=encrypted:BHilF3YvNa+A8t...

cat .env.keys       # gitignored — the private key lives here
#   DOTENV_PRIVATE_KEY=c981b6886a1...
```

`dotenvx run` / `dotenvx get` / `dotenvx.config()` decrypt automatically: they
look for the private key in the environment first (so `.env.keys` can be
`chmod a-r` and still work), then in a `.env.keys` file next to the `.env`
file being loaded. The scheme is ECIES over secp256k1 (HKDF-SHA256 +
AES-256-GCM) — see [`SPEC.md` §3](./SPEC.md) for the full wire format.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # set up the environment
uv run pytest           # tests
uv run ruff check .     # lint
uv run mypy src         # type-check
uv run dotenvx --help   # try the CLI
```

## License

MIT
