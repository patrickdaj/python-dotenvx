"""ECIES encryption compatible with dotenvx / eciesjs.

Byte-for-byte interoperable with the Node.js ``dotenvx`` CLI. The scheme
(reverse-engineered from ``@dotenvx/primitives`` and pinned in SPEC.md §3):

* Curve: secp256k1 (via :mod:`coincurve` — pyca ``cryptography`` cannot do the
  full-point ECDH this scheme needs).
* Per-value ephemeral keypair.
* Shared secret: ``HKDF-SHA256`` over
  ``ephemeral_pubkey(65) || ecdh_shared_point(65)`` (both uncompressed), empty
  salt, no info, 32-byte output.
* Cipher: AES-256-GCM, 16-byte nonce, 16-byte tag, no AAD.
* Blob: ``ephemeral_pubkey(65) || nonce(16) || tag(16) || ciphertext`` — note
  the tag precedes the ciphertext.
* Encoding: ``"encrypted:"`` + standard base64 of the blob.
"""

from __future__ import annotations

import base64
import os
from typing import NamedTuple

from coincurve import PrivateKey, PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

#: Prefix marking an encrypted value in a ``.env`` file.
PREFIX = "encrypted:"

_UNCOMPRESSED_KEY_LEN = 65
_NONCE_LEN = 16
_TAG_LEN = 16


class KeyPair(NamedTuple):
    """A secp256k1 keypair as lowercase hex strings."""

    public_key: str
    private_key: str


def _derive_key(ephemeral_pubkey: bytes, shared_point: bytes) -> bytes:
    """HKDF-SHA256 the shared symmetric key from the ECDH inputs."""
    return HKDF(algorithm=SHA256(), length=32, salt=b"", info=None).derive(
        ephemeral_pubkey + shared_point
    )


def generate_keypair() -> KeyPair:
    """Generate a fresh secp256k1 keypair (compressed public key, like dotenvx)."""
    sk = PrivateKey()
    return KeyPair(
        public_key=sk.public_key.format(compressed=True).hex(),
        private_key=sk.secret.hex(),
    )


def public_key_from_private(private_key_hex: str) -> str:
    """Derive the compressed-hex public key for a private key."""
    sk = PrivateKey(bytes.fromhex(private_key_hex))
    return sk.public_key.format(compressed=True).hex()


def encrypt(public_key_hex: str, value: str) -> str:
    """Encrypt ``value`` for ``public_key_hex``; return an ``encrypted:`` string."""
    receiver_pk = PublicKey(bytes.fromhex(public_key_hex))
    ephemeral_sk = PrivateKey()
    ephemeral_pub = ephemeral_sk.public_key.format(compressed=False)
    shared_point = receiver_pk.multiply(ephemeral_sk.secret).format(compressed=False)
    key = _derive_key(ephemeral_pub, shared_point)

    nonce = os.urandom(_NONCE_LEN)
    ct_and_tag = AESGCM(key).encrypt(nonce, value.encode("utf-8"), None)
    ciphertext, tag = ct_and_tag[:-_TAG_LEN], ct_and_tag[-_TAG_LEN:]

    blob = ephemeral_pub + nonce + tag + ciphertext
    return PREFIX + base64.b64encode(blob).decode("ascii")


def decrypt(private_key_hex: str, value: str) -> str:
    """Decrypt an ``encrypted:`` ``value``; pass through anything not encrypted."""
    if not value.startswith(PREFIX):
        return value
    if not private_key_hex:
        raise ValueError("missing private key: cannot decrypt encrypted value")

    blob = base64.b64decode(value[len(PREFIX) :])
    ephemeral_pub = blob[:_UNCOMPRESSED_KEY_LEN]
    rest = blob[_UNCOMPRESSED_KEY_LEN:]
    nonce, tag, ciphertext = (
        rest[:_NONCE_LEN],
        rest[_NONCE_LEN : _NONCE_LEN + _TAG_LEN],
        rest[_NONCE_LEN + _TAG_LEN :],
    )

    sk = PrivateKey(bytes.fromhex(private_key_hex))
    shared_point = PublicKey(ephemeral_pub).multiply(sk.secret).format(compressed=False)
    key = _derive_key(ephemeral_pub, shared_point)

    # pyca AESGCM expects ciphertext || tag; dotenvx stores tag || ciphertext.
    plaintext = AESGCM(key).decrypt(nonce, ciphertext + tag, None)
    return plaintext.decode("utf-8")


def is_encrypted(value: str) -> bool:
    """Return ``True`` if ``value`` is an ``encrypted:`` string."""
    return value.startswith(PREFIX)
