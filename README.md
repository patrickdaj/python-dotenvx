# python-dotenvx

A Python port of [dotenvx](https://dotenvx.com) — *a better dotenv*: run
anywhere, multiple environments, and built-in encryption. Aims for
byte-for-byte file/crypto interop with the Node.js `dotenvx` CLI and library.

> **Status: pre-alpha, under active construction.** See [`PLAN.md`](./PLAN.md)
> for the build roadmap, [`SPEC.md`](./SPEC.md) for the behavior contract, and
> [`CLAUDE.md`](./CLAUDE.md) for development setup.

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
