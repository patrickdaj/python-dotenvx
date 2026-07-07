"""``.env`` parsing and interpolation, byte-for-byte compatible with dotenvx.

Ported from ``@dotenvx/primitives`` (``src/scan.js``, ``src/expand.js``,
``src/evaluate.js``, ``src/parse.js``) — see SPEC.md §2 and §4 for the
resolved, source-verified behavior this implements.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

_LINE = re.compile(
    r"^\s*(?:export\s+)?([\w.-]+)(?:\s*=\s*|:\s+)"
    r"(\s*'(?:\\'|[^'])*'|\s*\"(?:\\\"|[^\"])*\"|\s*`(?:\\`|[^`])*`|[^#\r\n]+)?"
    r"\s*(?:#.*)?$",
    re.MULTILINE,
)

_EXPAND = re.compile(r"(?<!\\)\$\{([^{}]+)\}|(?<!\\)\$([A-Za-z_][A-Za-z0-9_]*)")
_OP = re.compile(r"(:\+|\+|:-|-)")
_COMMAND_SUB = re.compile(r"\$\(([^)]+(?:\)[^(]*)*)\)")
_ESCAPED_DOLLAR = re.compile(r"\\\$")

_QUOTE_CHARS = ("'", '"', "`")


@dataclass(frozen=True)
class ParsedLine:
    """One ``KEY=VALUE`` line: the quote character used, if any (``""`` if bare)."""

    name: str
    value: str
    quote: str


def _get_quote(raw: str | None) -> str:
    v = (raw or "").strip()
    return v[0] if v and v[0] in _QUOTE_CHARS else ""


def _clean(raw: str | None, quote: str) -> str:
    v = (raw or "").strip()
    if quote and len(v) >= 2 and v.startswith(quote) and v.endswith(quote):
        v = v[1:-1]
    if quote == '"':
        v = v.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
    return v


def scan(src: str) -> list[ParsedLine]:
    """Split ``src`` into ``ParsedLine``s, in file order, duplicates included."""
    normalized = src.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for match in _LINE.finditer(normalized):
        name, raw = match.group(1), match.group(2)
        quote = _get_quote(raw)
        lines.append(ParsedLine(name=name, value=_clean(raw, quote), quote=quote))
    return lines


def parse(src: str) -> dict[str, str]:
    """Parse ``src`` into a name -> value mapping (last duplicate wins).

    Quote-stripping and double-quote escape expansion (``\\n``/``\\r``/``\\t``)
    are applied; no ``${VAR}``/``$(...)`` interpolation (see :func:`resolve`).
    """
    return {line.name: line.value for line in scan(src)}


def _split_default(expression: str) -> tuple[str, str | None, str]:
    op_match = _OP.search(expression)
    if op_match is None:
        return expression, None, ""
    splitter = op_match.group(0)
    name, _, rest = expression.partition(splitter)
    return name, splitter, rest


def expand_value(
    value: str,
    *,
    process_env: dict[str, str],
    running_parsed: dict[str, str],
    overload: bool = False,
    literals: dict[str, str] | None = None,
) -> str:
    """Expand ``${VAR}`` / ``$VAR`` (with ``:-``/``-``/``:+``/``+``) in ``value``.

    Mirrors ``@dotenvx/primitives`` ``src/expand.js`` exactly, including its
    self-reference and literal-collision loop guards.
    """
    literals = literals or {}
    if overload:
        env = {**process_env, **running_parsed}
    else:
        env = {**running_parsed, **process_env}

    result = value
    # dotenvx's own loop has no explicit iteration cap, relying on the two
    # guards below to terminate; we add a generous backstop against any input
    # neither guard anticipates, without changing behavior for real inputs.
    for _ in range(1000):
        match = _EXPAND.search(result)
        if match is None:
            return result

        expression = match.group(1) if match.group(1) is not None else match.group(2)
        name, splitter, rest = _split_default(expression)

        if splitter in (":+", "+"):
            substitute = rest if env.get(name) else ""
        else:
            existing = env.get(name)
            substitute = existing if existing else rest

        result = result[: match.start()] + substitute + result[match.end() :]

        if result == env.get(name):
            return result
        literal = literals.get(name)
        if literal and _EXPAND.search(literal):
            return result
    return result


def evaluate_command_substitution(
    value: str,
    *,
    process_env: dict[str, str],
    running_parsed: dict[str, str] | None = None,
) -> str:
    """Replace ``$(command)`` spans with their (shell-executed) stdout.

    Mirrors ``src/evaluate.js``. Raises :class:`subprocess.SubprocessError` on
    failure — callers that want dotenvx's swallow-on-error behavior should
    catch it (see :func:`resolve`).
    """
    env = {**process_env, **(running_parsed or {})}
    result = value
    for match in _COMMAND_SUB.finditer(value):
        command = match.group(1)
        completed = subprocess.run(
            command,
            shell=True,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        output = completed.stdout.rstrip("\r\n")
        result = result.replace(match.group(0), output)
    return result


def resolve(
    src: str,
    *,
    process_env: dict[str, str] | None = None,
    overload: bool = False,
) -> dict[str, str]:
    """Parse + interpolate ``src`` the way dotenvx's ``parseWithRing`` does.

    Does not decrypt ``encrypted:`` values — see ``crypto.py`` / M5 for that
    layer, which sits between steps 1 and 2 of SPEC.md §4.
    """
    process_env = {} if process_env is None else process_env
    running_parsed: dict[str, str] = {}
    literals: dict[str, str] = {}
    parsed: dict[str, str] = {}

    for line in scan(src):
        name, value, quote = line.name, line.value, line.quote

        if not overload and name in process_env:
            value = process_env[name]

        evaled = False
        if quote != "'" and (name not in process_env or process_env.get(name) == value):
            try:
                new_value = evaluate_command_substitution(
                    value, process_env=process_env, running_parsed=running_parsed
                )
            except (subprocess.SubprocessError, OSError):
                new_value = value
            if new_value != value:
                evaled = True
                value = new_value

        if not evaled and quote != "'" and (not process_env.get(name) or overload):
            value = expand_value(
                value,
                process_env=process_env,
                running_parsed=running_parsed,
                overload=overload,
                literals=literals,
            )
            value = _ESCAPED_DOLLAR.sub("$", value)

        if quote == "'":
            literals[name] = value

        running_parsed[name] = value
        parsed[name] = value

    return parsed
