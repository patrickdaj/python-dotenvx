"""M8: `ls`, `gitignore`, `precommit`, `prebuild` (SPEC.md §6).

See `ext.py`'s module docstring for the one documented simplification
(fnmatch-based ignore matching instead of full `.gitignore` spec).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from dotenvx import ext

# --- ls() -------------------------------------------------------------


def test_ls_finds_env_files_recursively(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / ".env.production").write_text("A=2\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / ".env").write_text("A=3\n")

    result = ext.ls(tmp_path)

    assert result == [".env", ".env.production", "sub/.env"]


def test_ls_skips_node_modules_and_git(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / ".env").write_text("A=x\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / ".env").write_text("A=x\n")

    assert ext.ls(tmp_path) == [".env"]


def test_ls_respects_exclude_patterns(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / ".env.keys").write_text("DOTENV_PRIVATE_KEY=x\n")

    assert ext.ls(tmp_path, exclude_env_file=[".env.keys"]) == [".env"]


# --- sealed() -----------------------------------------------------------


def test_sealed_true_when_all_values_encrypted() -> None:
    src = 'DOTENV_PUBLIC_KEY="02abc"\nA=encrypted:xyz\n'
    assert ext.sealed(src) is True


def test_sealed_false_with_plaintext_value() -> None:
    assert ext.sealed("A=plaintext\n") is False


def test_sealed_ignores_plain_suffixed_keys() -> None:
    src = 'DOTENV_PUBLIC_KEY="02abc"\nA=encrypted:xyz\nB_PLAIN=visible\n'
    assert ext.sealed(src) is True


# --- gitignore() --------------------------------------------------------


def test_gitignore_creates_gitignore_if_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = ext.gitignore()

    assert ".gitignore" in result.changed_files
    assert (tmp_path / ".gitignore").read_text().strip() == ".env*"


def test_gitignore_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ext.gitignore()

    result = ext.gitignore()

    assert result.changed_files == []
    assert ".gitignore" in result.unchanged_files


def test_gitignore_only_updates_dockerignore_if_present(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    ext.gitignore()

    assert not (tmp_path / ".dockerignore").exists()


def test_gitignore_updates_existing_dockerignore(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".dockerignore").write_text("node_modules\n")

    result = ext.gitignore()

    assert ".dockerignore" in result.changed_files
    assert ".env*" in (tmp_path / ".dockerignore").read_text()


def test_gitignore_custom_patterns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    ext.gitignore([".env.production"])

    assert ".env.production" in (tmp_path / ".gitignore").read_text()


# --- install_precommit_hook() -------------------------------------------


def test_install_precommit_hook_creates_executable_hook(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"

    message = ext.install_precommit_hook(git_dir)

    hook = git_dir / "hooks" / "pre-commit"
    assert "installed" in message
    assert hook.is_file()
    assert "dotenvx precommit" in hook.read_text()
    assert hook.stat().st_mode & 0o111  # executable


def test_install_precommit_hook_is_idempotent(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    ext.install_precommit_hook(git_dir)

    message = ext.install_precommit_hook(git_dir)

    assert "exists" in message


def test_install_precommit_hook_appends_to_existing_unrelated_hook(
    tmp_path: Path,
) -> None:
    git_dir = tmp_path / ".git"
    hook = git_dir / "hooks"
    hook.mkdir(parents=True)
    (hook / "pre-commit").write_text("#!/bin/sh\necho existing-hook\n")

    message = ext.install_precommit_hook(git_dir)

    content = (hook / "pre-commit").read_text()
    assert "appended" in message
    assert "echo existing-hook" in content
    assert "dotenvx precommit" in content


# --- precommit_check() / prebuild_check() -------------------------------


def test_prebuild_check_passes_for_encrypted_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text('DOTENV_PUBLIC_KEY="02abc"\nA=encrypted:xyz\n')

    result = ext.prebuild_check(tmp_path)

    assert result.ok is True
    assert "encrypted/dockerignored" in result.message


def test_prebuild_check_fails_for_plaintext_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=plaintext\n")

    result = ext.prebuild_check(tmp_path)

    assert result.ok is False
    assert "not encrypted" in result.message


def test_prebuild_check_warns_missing_dockerignore(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text('DOTENV_PUBLIC_KEY="02abc"\nA=encrypted:xyz\n')

    result = ext.prebuild_check(tmp_path)

    assert any(".dockerignore missing" in w for w in result.warnings)


def test_prebuild_check_passes_when_file_is_dockerignored(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=plaintext\n")
    (tmp_path / ".dockerignore").write_text(".env\n")

    result = ext.prebuild_check(tmp_path)

    assert result.ok is True


def test_prebuild_check_no_env_files(tmp_path: Path) -> None:
    result = ext.prebuild_check(tmp_path)
    assert result.ok is True
    assert "no .env files" in result.message


def test_precommit_check_outside_git_repo_treats_all_files_as_committed(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("A=plaintext\n")

    result = ext.precommit_check(tmp_path)

    assert result.ok is False


def test_precommit_check_passes_inside_git_repo_for_unstaged_plaintext(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    # a plaintext .env exists but was never `git add`-ed / staged
    (tmp_path / ".env").write_text("A=plaintext\n")

    result = ext.precommit_check(tmp_path)

    assert result.ok is True


def test_precommit_check_fails_for_staged_plaintext_env(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    (tmp_path / ".env").write_text("A=plaintext\n")
    subprocess.run(["git", "add", ".env"], cwd=tmp_path, check=True)

    result = ext.precommit_check(tmp_path)

    assert result.ok is False
    assert ".env not encrypted" in result.message
