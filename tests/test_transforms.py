"""M6/M7: `set`, `encrypt`, `decrypt`, `keypair` (SPEC.md §6).

Ported from dotenvx's `upsert.js` / `mutateSrc.js` / `mutateKeysSrc.js` /
`transforms/*.js`; the bootstrap banner text is checked against real
`dotenvx set` output captured manually (see PLAN.md M6/M7 notes) and, where
practical, round-tripped through the real Node CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import dotenvx
from dotenvx import crypto, transforms


def _find_node_dotenvx() -> str | None:
    # shutil.which() would happily return *our own* installed `dotenvx`
    # console-script from this project's venv — skip any candidate that
    # lives under a Python venv so we always exercise the real Node CLI.
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / "dotenvx"
        if (
            candidate.is_file()
            and os.access(candidate, os.X_OK)
            and "venv" not in str(candidate)
        ):
            return str(candidate)
    return None


NODE_DOTENVX = _find_node_dotenvx()
FIXTURES = Path(__file__).parent / "fixtures" / "node_interop"


# --- upsert() -----------------------------------------------------------


def test_upsert_updates_existing_unquoted_value() -> None:
    assert transforms.upsert("A=old\nB=2\n", "A", "new") == "A=new\nB=2\n"


def test_upsert_updates_existing_quoted_value_preserving_quote_style() -> None:
    assert transforms.upsert('A="old"\n', "A", "new") == 'A="new"\n'
    assert transforms.upsert("A='old'\n", "A", "new") == "A='new'\n"


def test_upsert_preserves_export_prefix() -> None:
    assert transforms.upsert("export A=old\n", "A", "new") == "export A=new\n"


def test_upsert_appends_new_key_double_quoted() -> None:
    assert transforms.upsert("A=1\n", "B", "2") == 'A=1\nB="2"\n'


def test_upsert_appends_to_empty_source() -> None:
    assert transforms.upsert("", "A", "1") == 'A="1"\n'


def test_upsert_appends_without_trailing_newline_in_source() -> None:
    # No trailing newline added when the source itself lacked one (matches upsert.js).
    assert transforms.upsert("A=1", "B", "2") == 'A=1\nB="2"'


def test_upsert_duplicate_keys_each_get_their_own_replacement() -> None:
    src = "A=1\nA=2\n"
    assert transforms.upsert(src, "A", ["first", "second"]) == "A=first\nA=second\n"


def test_upsert_leaves_other_keys_untouched() -> None:
    src = "# a comment\nA=1\nB=2\n"
    assert transforms.upsert(src, "A", "99") == "# a comment\nA=99\nB=2\n"


# --- prepend_public_key() / mutate_src() / mutate_keys_src() -------------


def test_prepend_public_key_matches_real_dotenvx_banner() -> None:
    # Byte-for-byte against banner text captured from a real `dotenvx set`.
    result = transforms.prepend_public_key("DOTENV_PUBLIC_KEY", "02abc", ".env")
    assert result == (
        "#/-------------------[DOTENV_PUBLIC_KEY]--------------------/\n"
        "#/            public-key encryption for .env files          /\n"
        "#/       [how it works](https://dotenvx.com/encryption)     /\n"
        "#/----------------------------------------------------------/\n"
        'DOTENV_PUBLIC_KEY="02abc"\n'
        "\n"
        "# .env"
    )


def test_mutate_keys_src_first_time_matches_real_dotenvx_banner() -> None:
    result = transforms.mutate_keys_src(None, "DOTENV_PRIVATE_KEY", "deadbeef", ".env")
    assert result == (
        "#/------------------!DOTENV_PRIVATE_KEYS!-------------------/\n"
        "#/ private decryption keys. DO NOT commit to source control /\n"
        "#/     [how it works](https://dotenvx.com/encryption)       /\n"
        "#/          ⛨ ARMORED KEYS: `dotenvx armor up`              /\n"
        "#/----------------------------------------------------------/\n"
        "\n"
        "# .env\n"
        "DOTENV_PRIVATE_KEY=deadbeef\n"
    )


def test_preserve_shebang() -> None:
    preserved, rest = transforms.preserve_shebang("#!/usr/bin/env dotenvx\nA=1\n")
    assert preserved == "#!/usr/bin/env dotenvx\n"
    assert rest == "A=1\n"

    preserved, rest = transforms.preserve_shebang("A=1\n")
    assert preserved == ""
    assert rest == "A=1\n"


# --- set_value() ----------------------------------------------------------


def test_set_value_bootstraps_keypair_on_fresh_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    result = transforms.set_value(env_path, "HELLO", "world")

    assert result.changed is True
    assert result.encrypted is True
    assert result.public_key is not None
    assert "DOTENV_PUBLIC_KEY" in env_path.read_text()
    assert (tmp_path / ".env.keys").exists()

    private_key = [
        line.split("=", 1)[1]
        for line in (tmp_path / ".env.keys").read_text().splitlines()
        if line.startswith("DOTENV_PRIVATE_KEY=")
    ][0]
    encrypted_line = [
        line for line in env_path.read_text().splitlines() if line.startswith("HELLO=")
    ][0]
    encrypted_value = encrypted_line.split("=", 1)[1].strip('"')
    assert crypto.decrypt(private_key, encrypted_value) == "world"


def test_set_value_reuses_existing_keypair(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    first = transforms.set_value(env_path, "A", "1")
    second = transforms.set_value(env_path, "B", "2")

    assert second.public_key == first.public_key
    # only one DOTENV_PUBLIC_KEY banner, not two
    assert env_path.read_text().count("DOTENV_PUBLIC_KEY=") == 1


def test_set_value_updating_to_same_plaintext_is_a_noop(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    transforms.set_value(env_path, "A", "same")
    before = env_path.read_text()

    result = transforms.set_value(env_path, "A", "same")

    assert result.changed is False
    assert env_path.read_text() == before


def test_set_value_plain_flag_skips_encryption(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    result = transforms.set_value(env_path, "A", "plaintext", encrypt=False)

    assert result.changed is True
    assert result.encrypted is False
    assert env_path.read_text() == 'A="plaintext"\n'
    assert not (tmp_path / ".env.keys").exists()


def test_set_value_plain_suffix_key_skips_encryption_even_with_encrypt_true(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"

    result = transforms.set_value(env_path, "A_PLAIN", "plaintext", encrypt=True)

    assert result.encrypted is False
    assert env_path.read_text() == 'A_PLAIN="plaintext"\n'


def test_set_wrapper_in_public_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = dotenvx.set("A", "hello")
    assert result.changed is True
    # get() finds the colocated .env.keys set() just created and decrypts.
    assert dotenvx.get("A", path=tmp_path / ".env") == "hello"


# --- encrypt_file() / decrypt_file() round trip ----------------------------


def test_encrypt_then_decrypt_round_trips(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("A=hello\nB=world\n")

    enc = transforms.encrypt_file(env_path)
    assert enc.changed is True
    assert set(enc.keys) == {"A", "B"}
    src_after_encrypt = env_path.read_text()
    assert "encrypted:" in src_after_encrypt

    dec = transforms.decrypt_file(env_path)
    assert dec.changed is True
    assert set(dec.keys) == {"A", "B"}
    # DOTENV_PUBLIC_KEY correctly stays in the raw file after decrypt (matches
    # real dotenvx: decrypt only rewrites keys whose value actually changed).
    result = dotenvx.parse(env_path.read_text())
    assert result["A"] == "hello"
    assert result["B"] == "world"


def test_encrypt_file_skips_plain_suffixed_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("SECRET=hide\nPUBLIC_PLAIN=visible\n")

    transforms.encrypt_file(env_path)

    src = env_path.read_text()
    assert "PUBLIC_PLAIN=visible" in src or 'PUBLIC_PLAIN="visible"' in src
    assert "encrypted:" in src


def test_encrypt_file_is_idempotent(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("A=hello\n")
    transforms.encrypt_file(env_path)
    once = env_path.read_text()

    again = transforms.encrypt_file(env_path)

    assert again.changed is False
    assert env_path.read_text() == once


def test_decrypt_file_without_private_key_leaves_values_encrypted(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    shutil.copy(FIXTURES / ".env", env_path)  # no .env.keys alongside it

    result = transforms.decrypt_file(env_path)

    assert result.changed is False
    assert "encrypted:" in env_path.read_text()


# --- get_keypair() ----------------------------------------------------------


def test_get_keypair_for_encrypted_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    # Bootstrap from a nonexistent file so the first set() actually persists
    # the new banner+keypair (see PLAN.md: a same-value set() against an
    # already-present raw value is a real, faithfully-ported upstream no-op).
    transforms.set_value(env_path, "A", "1")

    kp = transforms.get_keypair(env_path)

    assert kp.public_key_name == "DOTENV_PUBLIC_KEY"
    assert kp.private_key_name == "DOTENV_PRIVATE_KEY"
    assert kp.public_key is not None
    assert kp.private_key is not None


def test_get_keypair_for_plaintext_file_has_no_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("A=1\n")

    kp = transforms.get_keypair(env_path)

    assert kp.public_key is None
    assert kp.private_key is None


# --- cross-interop with the real Node CLI (skipped if not installed) ------


@pytest.mark.skipif(NODE_DOTENVX is None, reason="Node dotenvx CLI not installed")
def test_python_set_is_readable_by_real_node_dotenvx(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    transforms.set_value(env_path, "GREETING", "hello from python")

    output = subprocess.run(
        [NODE_DOTENVX, "get", "GREETING"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert output == "hello from python"


@pytest.mark.skipif(NODE_DOTENVX is None, reason="Node dotenvx CLI not installed")
def test_python_encrypt_file_is_readable_by_real_node_dotenvx(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("A=hello\n")
    transforms.encrypt_file(env_path)

    output = subprocess.run(
        [NODE_DOTENVX, "get", "--format", "shell"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # get's output also includes DOTENV_PUBLIC_KEY (it isn't filtered out).
    assert "A=hello" in output


@pytest.mark.skipif(NODE_DOTENVX is None, reason="Node dotenvx CLI not installed")
def test_node_set_is_readable_by_python(tmp_path: Path) -> None:
    subprocess.run(
        [NODE_DOTENVX, "set", "GREETING", "hello from node"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    result = dotenvx.config(tmp_path / ".env", environ={})

    assert result.parsed["GREETING"] == "hello from node"
    assert json.loads(json.dumps(result.parsed))  # sanity: plain JSON-safe strings
