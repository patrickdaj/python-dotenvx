"""M6/M7: `dotenvx set`, `encrypt`, `decrypt`, `keypair` CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dotenvx.cli import app

runner = CliRunner()


def test_set_bootstraps_keypair_and_encrypts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["set", "HELLO", "world"])

    assert result.exit_code == 0
    assert "encrypted HELLO" in result.stdout
    assert "encrypted:" in (tmp_path / ".env").read_text()
    assert (tmp_path / ".env.keys").exists()


def test_set_plain_flag_stores_plaintext(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["set", "HELLO", "world", "--plain"])

    assert result.exit_code == 0
    assert "set HELLO" in result.stdout
    assert (tmp_path / ".env").read_text() == 'HELLO="world"\n'
    assert not (tmp_path / ".env.keys").exists()


def test_set_then_get_round_trips(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["set", "HELLO", "world"])

    result = runner.invoke(app, ["get", "HELLO"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "world"


def test_encrypt_reports_no_change_when_already_encrypted(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=hello\n")
    runner.invoke(app, ["encrypt"])

    result = runner.invoke(app, ["encrypt"])

    assert result.exit_code == 0
    assert "no change" in result.stdout


def test_encrypt_then_decrypt_cli_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=hello\nB=world\n")

    enc_result = runner.invoke(app, ["encrypt"])
    assert enc_result.exit_code == 0
    assert "encrypted:" in (tmp_path / ".env").read_text()

    dec_result = runner.invoke(app, ["decrypt"])
    assert dec_result.exit_code == 0

    get_result = runner.invoke(app, ["get"])
    assert json.loads(get_result.stdout)["A"] == "hello"
    assert json.loads(get_result.stdout)["B"] == "world"


def test_keypair_prints_public_and_private(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["set", "HELLO", "world"])

    result = runner.invoke(app, ["keypair"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["DOTENV_PUBLIC_KEY"] is not None
    assert payload["DOTENV_PRIVATE_KEY"] is not None


def test_keypair_single_key_lookup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["set", "HELLO", "world"])

    result = runner.invoke(app, ["keypair", "DOTENV_PRIVATE_KEY"])

    assert result.exit_code == 0
    assert len(result.stdout.strip()) == 64  # 32-byte hex private key


def test_keypair_for_plaintext_file_is_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\n")

    result = runner.invoke(app, ["keypair"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["DOTENV_PUBLIC_KEY"] is None
