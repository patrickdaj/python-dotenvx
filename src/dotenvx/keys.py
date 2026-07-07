"""Key-name derivation and private-key lookup for encrypted ``.env`` files.

Ported from dotenvx's ``conventions/keynames.js``, ``conventions/environment.js``,
and ``helpers/canonicalEnvFilename.js`` — see SPEC.md §2.3, confirmed against
the real CLI/source.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenvx.parser import parse

_PUBLIC_PREFIX = "DOTENV_PUBLIC_KEY"
_PRIVATE_PREFIX = "DOTENV_PRIVATE_KEY"


def canonical_env_filename(filepath: str | os.PathLike[str]) -> str:
    """Lowercase basename, with a trailing ``.txt`` stripped from ``.env*.txt``."""
    filename = Path(filepath).name.lower()
    if filename.startswith(".env") and filename.endswith(".txt"):
        filename = filename[:-4]
    return filename


def environment_suffix(filename: str) -> str:
    """The ``PRODUCTION`` in ``.env.production`` -> ``DOTENV_PUBLIC_KEY_PRODUCTION``."""
    parts = filename.split(".")
    possible = parts[2:]
    if not possible:
        return filename.replace(".env", "development", 1)
    if len(possible) == 1:
        return possible[0]
    return "_".join(possible[:2])


@dataclass(frozen=True)
class KeyNames:
    """The public/private key variable names a given ``.env`` file uses."""

    public_key_name: str
    private_key_name: str


def keynames(filepath: str | os.PathLike[str], src: str = "") -> KeyNames:
    """Derive key names for ``filepath``: file content wins over filename convention."""
    if src:
        for name in parse(src):
            if name.startswith(_PUBLIC_PREFIX):
                return KeyNames(name, name.replace(_PUBLIC_PREFIX, _PRIVATE_PREFIX, 1))

    filename = canonical_env_filename(filepath)
    if filename == ".env":
        return KeyNames(_PUBLIC_PREFIX, _PRIVATE_PREFIX)

    suffix = environment_suffix(filename).upper()
    return KeyNames(f"{_PUBLIC_PREFIX}_{suffix}", f"{_PRIVATE_PREFIX}_{suffix}")


def find_private_key(
    env_file: str | os.PathLike[str],
    private_key_name: str,
    *,
    process_env: Mapping[str, str],
    env_keys_path: str | os.PathLike[str] | None = None,
) -> str | None:
    """Resolve the private key: ``process_env`` wins, else a colocated ``.env.keys``.

    Mirrors dotenvx's ``fk`` resolution in ``resolvers/envs.js``: an explicit
    ``env_keys_path`` (``-fk``) takes precedence; otherwise, if the key is
    already in ``process_env`` (e.g. exported directly), ``.env.keys`` is
    never read at all — this is what lets ``.env.keys`` be `chmod a-r` and
    still work.
    """
    if private_key_name in process_env:
        return process_env[private_key_name]

    if env_keys_path:
        keys_path = Path(env_keys_path)
    else:
        keys_path = Path(env_file).parent / ".env.keys"
    if not keys_path.is_file():
        return None

    return parse(keys_path.read_text(encoding="utf-8")).get(private_key_name)
