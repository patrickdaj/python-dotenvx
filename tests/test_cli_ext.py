"""M8 CLI: `dotenvx ls`, `gitignore`, `precommit`, `prebuild`."""

from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from dotenvx.cli import app

runner = CliRunner()


def test_ls_command_lists_env_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / ".env.production").write_text("A=2\n")

    result = runner.invoke(app, ["ls"])

    assert result.exit_code == 0
    assert set(result.stdout.split()) == {".env", ".env.production"}


def test_gitignore_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["gitignore"])

    assert result.exit_code == 0
    assert "ignored" in result.stdout
    assert ".env*" in (tmp_path / ".gitignore").read_text()


def test_precommit_install_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git" / "hooks").mkdir(parents=True)

    result = runner.invoke(app, ["precommit", "--install"])

    assert result.exit_code == 0
    assert "installed" in result.stdout
    assert (tmp_path / ".git" / "hooks" / "pre-commit").is_file()


def test_precommit_check_fails_for_plaintext_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hi\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    (tmp_path / ".env").write_text("A=plaintext\n")
    subprocess.run(["git", "add", ".env"], cwd=tmp_path, check=True)

    result = runner.invoke(app, ["precommit"])

    assert result.exit_code == 1
    assert "not encrypted" in result.stdout


def test_prebuild_command_passes_for_encrypted_file(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text('DOTENV_PUBLIC_KEY="02abc"\nA=encrypted:xyz\n')

    result = runner.invoke(app, ["prebuild"])

    assert result.exit_code == 0
    assert "encrypted/dockerignored" in result.stdout


def test_prebuild_command_fails_for_plaintext(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=plaintext\n")

    result = runner.invoke(app, ["prebuild"])

    assert result.exit_code == 1
