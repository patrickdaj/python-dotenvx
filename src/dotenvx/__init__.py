"""python-dotenvx — a Python port of dotenvx.

Public API surface grows across milestones (see PLAN.md).
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from dotenvx.crypto import is_encrypted
from dotenvx.keys import find_private_key, keynames
from dotenvx.parser import resolve
from dotenvx.transforms import SetResult, set_value

__all__ = ["ConfigResult", "SetResult", "__version__", "config", "get", "parse", "set"]

__version__ = "0.0.1"


def parse(
    src: str | bytes,
    *,
    process_env: MutableMapping[str, str] | None = None,
    overload: bool = False,
) -> dict[str, str]:
    """Parse + interpolate ``src`` (SPEC.md §2/§4) without touching ``os.environ``.

    ``process_env`` supplies the values ``${VAR}``/precedence resolve against;
    it defaults to an empty mapping, not ``os.environ`` — use :func:`config`
    to load into the real process environment.
    """
    if isinstance(src, bytes):
        src = src.decode("utf-8")
    return resolve(src, process_env=dict(process_env or {}), overload=overload)


@dataclass
class ConfigResult:
    """Mirrors dotenvx's ``config()`` return shape: parsed/injected/existed/errors."""

    parsed: dict[str, str] = field(default_factory=dict)
    injected: dict[str, str] = field(default_factory=dict)
    existed: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def config(
    path: str | os.PathLike[str] | Sequence[str | os.PathLike[str]] = ".env",
    *,
    overload: bool = False,
    encoding: str = "utf-8",
    environ: MutableMapping[str, str] | None = None,
    env_keys_path: str | os.PathLike[str] | None = None,
) -> ConfigResult:
    """Load, decrypt, and interpolate ``.env`` file(s) into ``environ``.

    ``path`` may be repeated (a list) to mirror dotenvx's repeatable ``-f``
    flag: earlier files win over later ones unless ``overload`` is set, in
    which case later files win (SPEC.md §5, confirmed against the real CLI).
    ``environ`` defaults to ``os.environ`` (mutated in place, like Node's
    ``process.env``); pass a plain ``dict`` in tests to avoid touching it.

    Encrypted (``encrypted:``) values are decrypted using the private key
    named for each file by :func:`dotenvx.keys.keynames` — from ``environ``
    if present there, else a colocated ``.env.keys`` (or ``env_keys_path`` if
    given). A value that can't be decrypted is left as-is and reported in
    ``errors`` (SPEC.md §3.4).
    """
    paths = [path] if isinstance(path, (str, os.PathLike)) else list(path)
    target = os.environ if environ is None else environ

    result = ConfigResult()
    for p in paths:
        file_path = Path(p)
        if not file_path.is_file():
            result.errors.append(f"missing file ({file_path})")
            continue

        before = dict(target)
        src = file_path.read_text(encoding=encoding)

        names = keynames(file_path, src)
        private_key = find_private_key(
            file_path,
            names.private_key_name,
            process_env=target,
            env_keys_path=env_keys_path,
        )

        file_parsed = resolve(
            src, process_env=dict(target), overload=overload, private_key=private_key
        )

        unresolved = [
            name for name, value in file_parsed.items() if is_encrypted(value)
        ]
        if unresolved:
            result.errors.append(f"could not decrypt {', '.join(unresolved)}")

        for name, value in file_parsed.items():
            result.parsed[name] = value
            if name in before and not overload:
                result.existed[name] = before[name]
            else:
                result.injected[name] = value
                target[name] = value

    return result


def get(
    key: str,
    *,
    path: str | os.PathLike[str] | Sequence[str | os.PathLike[str]] = ".env",
    overload: bool = False,
) -> str | None:
    """Read one decrypted value from ``path`` without touching ``os.environ``.

    Returns ``None`` if ``key`` isn't set (SPEC.md §7).
    """
    result = config(path, overload=overload, environ={})
    return result.parsed.get(key)


def set(  # noqa: A001 - matches dotenvx's own `set` name (SPEC.md §7)
    key: str,
    value: str,
    *,
    path: str | os.PathLike[str] = ".env",
    encrypt: bool = True,
    env_keys_path: str | os.PathLike[str] | None = None,
) -> SetResult:
    """Add/update ``key=value`` in the ``.env`` file at ``path`` (SPEC.md §6/§7).

    Encrypted by default (bootstrapping a keypair on first use); pass
    ``encrypt=False`` for a plaintext value, or use a key name ending in
    ``_PLAIN`` for the same effect (dotenvx's own convention).
    """
    return set_value(path, key, value, encrypt=encrypt, env_keys_path=env_keys_path)
