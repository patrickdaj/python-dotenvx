"""Raw-text ``.env``/``.env.keys`` mutation: `set`, `encrypt`, `decrypt`, `keypair`.

Ported from dotenvx's ``src/upsert.js`` (primitives), and its own
``helpers/cryptography/mutateSrc.js``, ``mutateKeysSrc.js``,
``helpers/prependPublicKey.js``, ``helpers/preserveShebang.js``,
``helpers/cryptography/isPlainKey.js``, and the ``set``/``encrypt``/
``decrypt``/``keypair`` transforms — confirmed by reading that source
directly (see PLAN.md M6/M7 notes).

Known, deliberate gap: dotenvx's ``upsert.js`` has an extra rule preserving
blank lines that trail a key with an empty value; that narrow cosmetic case
isn't replicated here (see PLAN.md).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenvx import crypto
from dotenvx.keys import find_private_key, keynames
from dotenvx.parser import _LINE, _get_quote

_PLAIN_SUFFIX = "_PLAIN"
_PUBLIC_PREFIX = "DOTENV_PUBLIC_KEY"

_PUBLIC_KEY_BANNER = [
    "#/-------------------[DOTENV_PUBLIC_KEY]--------------------/",
    "#/            public-key encryption for .env files          /",
    "#/       [how it works](https://dotenvx.com/encryption)     /",
    "#/----------------------------------------------------------/",
]

_FIRST_TIME_KEYS_SRC = "\n".join(
    [
        "#/------------------!DOTENV_PRIVATE_KEYS!-------------------/",
        "#/ private decryption keys. DO NOT commit to source control /",
        "#/     [how it works](https://dotenvx.com/encryption)       /",
        "#/          ⛨ ARMORED KEYS: `dotenvx armor up`              /",
        "#/----------------------------------------------------------/",
    ]
)


def is_plain_key(key: str) -> bool:
    """A key whose name ends in ``_PLAIN`` is never encrypted by ``set``/``encrypt``."""
    return key.endswith(_PLAIN_SUFFIX)


def _raw_values(src: str) -> dict[str, list[str]]:
    """Quote-stripped but escape-**un**expanded values per key, in file order.

    Unlike :func:`dotenvx.parser.parse`, this preserves literal backslash
    sequences — needed so :func:`upsert` can regex-match the exact text as it
    appears in the source file.
    """
    normalized = src.replace("\r\n", "\n").replace("\r", "\n")
    result: dict[str, list[str]] = {}
    for match in _LINE.finditer(normalized):
        name, raw = match.group(1), match.group(2)
        quote = _get_quote(raw)
        value = (raw or "").strip()
        if (
            quote
            and len(value) >= 2
            and value.startswith(quote)
            and value.endswith(quote)
        ):
            value = value[1:-1]
        result.setdefault(name, []).append(value)
    return result


def first_public_key(src: str) -> str | None:
    """The value of the first ``DOTENV_PUBLIC_KEY*`` line found, if any."""
    for name, values in _raw_values(src).items():
        if name.startswith(_PUBLIC_PREFIX):
            return values[-1]
    return None


def _replace_existing_value(
    src: str, key: str, original_value: str, replace_value: str
) -> str:
    escaped_key = re.escape(key)
    escaped_original = re.escape(original_value)
    enforce_eol = "$" if escaped_original == "" else ""
    pattern = re.compile(
        r"^(\s*)?(export\s+)?"
        + escaped_key
        + r"\s*=\s*([\"'`]?)"
        + escaped_original
        + r"\3"
        + enforce_eol,
        re.MULTILINE,
    )

    def _sub(m: re.Match[str]) -> str:
        spaces, export_part, quote = (
            m.group(1) or "",
            m.group(2) or "",
            m.group(3) or "",
        )
        return f"{spaces}{export_part}{key}={quote}{replace_value}{quote}"

    return pattern.sub(_sub, src, count=1)


def upsert(src: str, key: str, replace_value: str | list[str]) -> str:
    """Update ``key``'s value(s) in place, or append a new ``KEY="value"`` line.

    ``replace_value`` may be a single string (applied to every existing
    occurrence of a duplicated key) or a list (one replacement per
    occurrence, in scan order) — mirrors ``@dotenvx/primitives`` ``upsert.js``.
    """
    existing = _raw_values(src)
    if key in existing:
        all_values = existing[key]
        replacements = (
            replace_value
            if isinstance(replace_value, list)
            else [replace_value] * len(all_values)
        )
        output = src
        for index, value in enumerate(all_values):
            output = _replace_existing_value(
                output, key, value, f"\0DOTENVX_UPSERT_{index}\0"
            )
        for index, replacement in enumerate(replacements):
            output = output.replace(f"\0DOTENVX_UPSERT_{index}\0", replacement)
        return output

    value = replace_value if isinstance(replace_value, str) else replace_value[0]
    new_part = f'{key}="{value}"'
    if src == "" or src.endswith("\n"):
        new_part += "\n"
    else:
        new_part = "\n" + new_part
    return src + new_part


def preserve_shebang(src: str) -> tuple[str, str]:
    """Split off a leading ``#!...`` line, if present: ``(preserved, rest)``."""
    lines = src.split("\n")
    first_line = lines[0] if lines else ""
    if first_line.startswith("#!"):
        return first_line + "\n", "\n".join(lines[1:])
    return "", src


def prepend_public_key(
    public_key_name: str,
    public_key: str,
    filename: str,
    relative_keys_filepath: str = ".env.keys",
) -> str:
    comment = (
        ""
        if relative_keys_filepath == ".env.keys"
        else f" # -fk {relative_keys_filepath}"
    )
    lines = [
        *_PUBLIC_KEY_BANNER,
        f'{public_key_name}="{public_key}"{comment}',
        "",
        f"# {filename}",
    ]
    return "\n".join(lines)


def mutate_src(
    env_src: str,
    env_filepath: str | os.PathLike[str],
    keys_filepath: str | os.PathLike[str],
    public_key_name: str,
    public_key_value: str,
) -> str:
    """Prepend a fresh ``DOTENV_PUBLIC_KEY`` banner to ``env_src``."""
    filepath = Path(env_filepath).resolve()
    filename = filepath.name
    resolved_keys_filepath = Path(keys_filepath).resolve()
    relative_filepath = os.path.relpath(resolved_keys_filepath, filepath.parent)

    preserved, rest = preserve_shebang(env_src)
    prepended = prepend_public_key(
        public_key_name, public_key_value, filename, relative_filepath
    )
    return f"{preserved}{prepended}\n{rest}"


def mutate_keys_src(
    keys_src: str | None,
    private_key_name: str,
    private_key_value: str,
    comment: str,
) -> str:
    """Append a fresh private-key entry to ``keys_src`` (or start a new file)."""
    append_private_key = "\n".join(
        [f"# {comment}", f"{private_key_name}={private_key_value}", ""]
    )
    base = keys_src if keys_src else f"{_FIRST_TIME_KEYS_SRC}\n"
    return f"{base}\n{append_private_key}"


@dataclass
class SetResult:
    changed: bool
    encrypted: bool
    public_key: str | None = None


def set_value(
    path: str | os.PathLike[str],
    key: str,
    value: str,
    *,
    encrypt: bool = True,
    env_keys_path: str | os.PathLike[str] | None = None,
    create: bool = True,
    process_env: Mapping[str, str] | None = None,
) -> SetResult:
    """Add/update ``key=value`` in the ``.env`` file at ``path``, writing it to disk.

    Encrypts the value (bootstrapping a keypair + ``.env.keys`` entry on first
    use) unless ``encrypt=False`` or ``key`` matches dotenvx's ``_PLAIN``
    naming convention (SPEC.md §2.1). Mirrors ``transforms/set.js``, minus its
    interactive/Armor key-storage prompt (file storage only — see SPEC §1).
    """
    process_env = os.environ if process_env is None else process_env
    file_path = Path(path)
    no_encrypt = not encrypt or is_plain_key(key)

    if file_path.is_file():
        src = file_path.read_text(encoding="utf-8")
    elif create:
        src = ""
    else:
        raise FileNotFoundError(str(file_path))

    public_key = first_public_key(src)
    keys_path = Path(env_keys_path) if env_keys_path else file_path.parent / ".env.keys"
    new_private_key: str | None = None

    if public_key is None and not no_encrypt:
        kp = crypto.generate_keypair()
        public_key = kp.public_key
        new_private_key = kp.private_key
        names = keynames(file_path, src)
        src = mutate_src(src, file_path, keys_path, names.public_key_name, public_key)

    changed = False
    if no_encrypt:
        before = src
        src = upsert(src, key, value)
        changed = src != before
    else:
        assert public_key is not None
        private_key = new_private_key or find_private_key(
            file_path,
            keynames(file_path, src).private_key_name,
            process_env=process_env,
            env_keys_path=env_keys_path,
        )
        current_raw = _raw_values(src).get(key, [None])[-1]
        current_value = None
        if current_raw is not None and private_key:
            try:
                current_value = crypto.decrypt(private_key, current_raw)
            except Exception:  # noqa: BLE001 - treat undecryptable existing value as "different"
                current_value = None
        if value != current_value:
            encrypted_value = crypto.encrypt(public_key, value)
            src = upsert(src, key, encrypted_value)
            changed = True

    if changed:
        file_path.write_text(src, encoding="utf-8")

    if new_private_key is not None:
        names = keynames(file_path, src)
        keys_src = (
            keys_path.read_text(encoding="utf-8") if keys_path.is_file() else None
        )
        keys_src = mutate_keys_src(
            keys_src, names.private_key_name, new_private_key, file_path.name
        )
        keys_path.write_text(keys_src, encoding="utf-8")

    return SetResult(changed=changed, encrypted=not no_encrypt, public_key=public_key)


@dataclass
class EncryptResult:
    changed: bool
    keys: list[str] = field(default_factory=list)
    public_key: str | None = None


def encrypt_file(
    path: str | os.PathLike[str],
    *,
    env_keys_path: str | os.PathLike[str] | None = None,
    create: bool = True,
) -> EncryptResult:
    """Encrypt every plaintext value in the ``.env`` file at ``path`` in place.

    Skips ``DOTENV_PUBLIC_KEY*`` lines and ``_PLAIN``-suffixed keys (SPEC.md
    §2.1); already-``encrypted:`` values pass through unchanged. Bootstraps a
    keypair if the file has none yet. Mirrors ``transforms/encrypt.js``.
    """
    file_path = Path(path)
    if file_path.is_file():
        src = file_path.read_text(encoding="utf-8")
    elif create:
        src = ""
    else:
        raise FileNotFoundError(str(file_path))

    public_key = first_public_key(src)
    keys_path = Path(env_keys_path) if env_keys_path else file_path.parent / ".env.keys"
    new_private_key: str | None = None

    if public_key is None:
        kp = crypto.generate_keypair()
        public_key = kp.public_key
        new_private_key = kp.private_key
        names = keynames(file_path, src)
        src = mutate_src(src, file_path, keys_path, names.public_key_name, public_key)

    changed = new_private_key is not None
    keys: list[str] = []
    for name, values in _raw_values(src).items():
        if name.startswith(_PUBLIC_PREFIX) or is_plain_key(name):
            continue
        transformed = [
            v if crypto.is_encrypted(v) else crypto.encrypt(public_key, v)
            for v in values
        ]
        before = src
        src = upsert(src, name, transformed)
        if src != before:
            changed = True
            keys.append(name)

    if changed:
        file_path.write_text(src, encoding="utf-8")

    if new_private_key is not None:
        names = keynames(file_path, src)
        keys_src = (
            keys_path.read_text(encoding="utf-8") if keys_path.is_file() else None
        )
        keys_src = mutate_keys_src(
            keys_src, names.private_key_name, new_private_key, file_path.name
        )
        keys_path.write_text(keys_src, encoding="utf-8")

    return EncryptResult(changed=changed, keys=keys, public_key=public_key)


@dataclass
class DecryptResult:
    changed: bool
    keys: list[str] = field(default_factory=list)


def decrypt_file(
    path: str | os.PathLike[str],
    *,
    env_keys_path: str | os.PathLike[str] | None = None,
    process_env: Mapping[str, str] | None = None,
) -> DecryptResult:
    """Decrypt every ``encrypted:`` value in the ``.env`` file at ``path`` in place.

    Mirrors ``transforms/decrypt.js``. Values that can't be decrypted (no
    matching private key) are left untouched.
    """
    process_env = os.environ if process_env is None else process_env
    file_path = Path(path)
    src = file_path.read_text(encoding="utf-8")

    names = keynames(file_path, src)
    private_key = find_private_key(
        file_path,
        names.private_key_name,
        process_env=process_env,
        env_keys_path=env_keys_path,
    )

    changed = False
    keys: list[str] = []
    for name, values in _raw_values(src).items():
        decrypted = []
        for v in values:
            if crypto.is_encrypted(v) and private_key:
                try:
                    decrypted.append(crypto.decrypt(private_key, v))
                    continue
                except Exception:  # noqa: BLE001 - leave value as-is if it can't be decrypted
                    pass
            decrypted.append(v)

        before = src
        src = upsert(src, name, decrypted)
        if src != before:
            changed = True
            keys.append(name)

    if changed:
        file_path.write_text(src, encoding="utf-8")

    return DecryptResult(changed=changed, keys=keys)


@dataclass
class KeyPairEntry:
    public_key_name: str
    public_key: str | None
    private_key_name: str
    private_key: str | None


def get_keypair(
    path: str | os.PathLike[str],
    *,
    env_keys_path: str | os.PathLike[str] | None = None,
    process_env: Mapping[str, str] | None = None,
) -> KeyPairEntry:
    """The public/private keypair for the ``.env`` file at ``path`` (SPEC.md §6)."""
    process_env = os.environ if process_env is None else process_env
    file_path = Path(path)
    src = file_path.read_text(encoding="utf-8") if file_path.is_file() else ""

    names = keynames(file_path, src)
    public_key = first_public_key(src)
    private_key = None
    if public_key:
        private_key = find_private_key(
            file_path,
            names.private_key_name,
            process_env=process_env,
            env_keys_path=env_keys_path,
        )

    return KeyPairEntry(
        names.public_key_name, public_key, names.private_key_name, private_key
    )
