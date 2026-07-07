"""M5: key-name derivation (SPEC.md §2.3), pinned to dotenvx's
`conventions/keynames.js` / `conventions/environment.js`.
"""

from __future__ import annotations

from pathlib import Path

from dotenvx.keys import KeyNames, canonical_env_filename, environment_suffix, keynames


def test_canonical_env_filename_lowercases_and_strips_txt() -> None:
    assert canonical_env_filename("/x/.ENV.Production.txt") == ".env.production"
    assert canonical_env_filename("/x/.env") == ".env"


def test_environment_suffix_single_segment() -> None:
    assert environment_suffix(".env.production") == "production"
    assert environment_suffix(".env.ci") == "ci"


def test_environment_suffix_two_segments_joined() -> None:
    assert environment_suffix(".env.foo.bar") == "foo_bar"


def test_environment_suffix_more_than_two_segments_truncates() -> None:
    assert environment_suffix(".env.foo.bar.baz") == "foo_bar"


def test_environment_suffix_no_segments_falls_back_to_development() -> None:
    assert environment_suffix(".env1") == "development1"


def test_keynames_plain_env_file() -> None:
    assert keynames(".env") == KeyNames("DOTENV_PUBLIC_KEY", "DOTENV_PRIVATE_KEY")


def test_keynames_environment_suffixed_file() -> None:
    assert keynames(".env.production") == KeyNames(
        "DOTENV_PUBLIC_KEY_PRODUCTION", "DOTENV_PRIVATE_KEY_PRODUCTION"
    )


def test_keynames_file_content_wins_over_filename(tmp_path: Path) -> None:
    # A file literally named .env.production but containing a _CI public key
    # (e.g. copied from elsewhere) resolves by content, not filename.
    src = 'DOTENV_PUBLIC_KEY_CI="02abc"\n'
    assert keynames(tmp_path / ".env.production", src) == KeyNames(
        "DOTENV_PUBLIC_KEY_CI", "DOTENV_PRIVATE_KEY_CI"
    )
