"""Crypto tests, including byte-for-byte interop with Node dotenvx.

The ``node_interop`` fixture was produced by the real Node ``dotenvx`` CLI; if
these pass, we decrypt Node ciphertext correctly (SPEC §3). No Node is needed to
run them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dotenvx import crypto

FIXTURES = Path(__file__).parent / "fixtures" / "node_interop"


def _load_private_key() -> str:
    for line in (FIXTURES / ".env.keys").read_text().splitlines():
        if line.startswith("DOTENV_PRIVATE_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise AssertionError("no DOTENV_PRIVATE_KEY in fixture")


def _load_encrypted_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (FIXTURES / ".env").read_text().splitlines():
        if "encrypted:" in line:
            key, rest = line.split("=", 1)
            values[key] = "encrypted:" + rest.split("encrypted:", 1)[1].strip("'\"")
    return values


def _load_public_key() -> str:
    for line in (FIXTURES / ".env").read_text().splitlines():
        if line.startswith("DOTENV_PUBLIC_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise AssertionError("no DOTENV_PUBLIC_KEY in fixture")


EXPECTED: dict[str, str] = json.loads((FIXTURES / "expected.json").read_text())


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_decrypts_node_ciphertext(key: str) -> None:
    priv = _load_private_key()
    encrypted = _load_encrypted_values()
    assert crypto.decrypt(priv, encrypted[key]) == EXPECTED[key]


def test_public_key_derivation_matches_fixture() -> None:
    priv = _load_private_key()
    assert crypto.public_key_from_private(priv) == _load_public_key()


def test_python_encrypt_is_decryptable_with_node_key() -> None:
    # Encrypt to the fixture's public key, decrypt with its private key.
    pub, priv = _load_public_key(), _load_private_key()
    token = crypto.encrypt(pub, "round-trip ✓ café")
    assert token.startswith("encrypted:")
    assert crypto.decrypt(priv, token) == "round-trip ✓ café"


@pytest.mark.parametrize("value", ["", "simple", "with=equals", "multi\nline", "☃"])
def test_round_trip_generated_keypair(value: str) -> None:
    kp = crypto.generate_keypair()
    token = crypto.encrypt(kp.public_key, value)
    assert crypto.decrypt(kp.private_key, token) == value


def test_encryption_is_nondeterministic() -> None:
    kp = crypto.generate_keypair()
    assert crypto.encrypt(kp.public_key, "x") != crypto.encrypt(kp.public_key, "x")


def test_passthrough_non_encrypted() -> None:
    assert crypto.decrypt("", "plain value") == "plain value"
    assert not crypto.is_encrypted("plain")
    assert crypto.is_encrypted("encrypted:abc")


def test_missing_key_raises() -> None:
    encrypted = _load_encrypted_values()
    with pytest.raises(ValueError, match="missing private key"):
        crypto.decrypt("", next(iter(encrypted.values())))
