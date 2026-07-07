"""`ls`, `gitignore`, `precommit`, `prebuild` (SPEC.md §6).

Ported from dotenvx's ``lib/resolvers/ls.js``, ``cli/actions/ext/gitignore.js``,
``lib/helpers/installPrecommitHook.js``, ``lib/services/precommit.js``,
``lib/services/prebuild.js``, and ``src/sealed.js`` (primitives).

Known, deliberate simplification: the real ``precommit``/``prebuild`` checks
use the full `.gitignore`-spec `ignore` npm package to decide whether an
``.env*`` file is covered. We use Python's stdlib :mod:`fnmatch` against each
ignore-file line instead — it handles the common ``.env*``-style patterns
dotenvx itself defaults to, but doesn't implement negation (``!pattern``),
directory-anchored patterns, or ``**`` recursion semantics. See PLAN.md M8.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from dotenvx.crypto import is_encrypted
from dotenvx.parser import parse

_IGNORE_DIRS = {"node_modules", ".git"}
_DEFAULT_EXCLUDE_ENV_FILES = [
    "test/**",
    "tests/**",
    "spec/**",
    "specs/**",
    "pytest/**",
    "test_suite/**",
]
_ALWAYS_ALLOWED = {".env.example", ".env.x"}


def ls(
    directory: str | os.PathLike[str] = ".",
    *,
    env_file: list[str] | None = None,
    exclude_env_file: list[str] | None = None,
) -> list[str]:
    """List ``.env*``-matching files under ``directory`` (relative paths, sorted).

    Skips ``node_modules/`` and ``.git/``. Mirrors ``resolvers/ls.js``.
    """
    patterns = env_file or [".env*"]
    excludes = exclude_env_file or []
    root = Path(directory).resolve()

    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for name in filenames:
            if any(fnmatch.fnmatch(name, pat) for pat in excludes):
                continue
            if any(fnmatch.fnmatch(name, pat) for pat in patterns):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                results.append(rel)
    return sorted(results)


def sealed(src: str) -> bool:
    """``True`` if every non-public-key/``_PLAIN`` value is ``encrypted:``."""
    for name, value in parse(src).items():
        if name.startswith("DOTENV_PUBLIC_KEY") or name.endswith("_PLAIN"):
            continue
        if not is_encrypted(value):
            return False
    return True


@dataclass
class GitignoreResult:
    changed_files: list[str] = field(default_factory=list)
    unchanged_files: list[str] = field(default_factory=list)


def add_ignore_patterns(
    ignore_filename: str,
    patterns: list[str] | None = None,
    *,
    create_if_missing: bool = False,
) -> list[str]:
    """Append any of ``patterns`` missing from ``ignore_filename``.

    Return what was added.

    Mirrors ``ext/gitignore.js``'s ``Generic`` class. Does nothing if the file
    doesn't exist and ``create_if_missing`` is ``False``.
    """
    patterns = patterns or [".env*"]
    path = Path(ignore_filename)

    if not path.is_file():
        if not create_if_missing or not patterns:
            return []
        path.write_text("")

    existing_lines = path.read_text(encoding="utf-8").splitlines()
    added = [p for p in patterns if p.strip() not in existing_lines]
    if added:
        with path.open("a", encoding="utf-8") as f:
            for pattern in added:
                f.write(f"\n{pattern}")
    return added


def gitignore(patterns: list[str] | None = None) -> GitignoreResult:
    """Add ``patterns`` (default ``.env*``) to .gitignore/.dockerignore/.npmignore/
    .vercelignore.

    Only ``.gitignore`` is created if missing; the others are updated only if
    already present. Mirrors ``ext/gitignore.js``.
    """
    result = GitignoreResult()
    targets = [
        (".gitignore", True),
        (".dockerignore", False),
        (".npmignore", False),
        (".vercelignore", False),
    ]
    for filename, create_if_missing in targets:
        added = add_ignore_patterns(
            filename, patterns, create_if_missing=create_if_missing
        )
        if added:
            result.changed_files.append(filename)
        elif Path(filename).is_file():
            result.unchanged_files.append(filename)
    return result


_HOOK_MARKER = "dotenvx precommit"
_HOOK_SCRIPT = """#!/bin/sh

if command -v dotenvx >/dev/null 2>&1
then
  dotenvx precommit
elif npx dotenvx -V >/dev/null 2>&1
then
  npx dotenvx precommit
else
  echo "dotenvx precommit command not found. fix: [curl -sfS https://dotenvx.sh|sh]" >&2
  exit 1
fi
"""


def install_precommit_hook(git_dir: str | os.PathLike[str] = ".git") -> str:
    """Install/append the dotenvx pre-commit git hook; returns a status message.

    Mirrors ``helpers/installPrecommitHook.js``.
    """
    hook_path = Path(git_dir) / "hooks" / "pre-commit"
    if hook_path.is_file():
        current = hook_path.read_text(encoding="utf-8")
        if _HOOK_MARKER in current:
            return f"dotenvx precommit exists [{hook_path}]"
        with hook_path.open("a", encoding="utf-8") as f:
            f.write("\n" + _HOOK_SCRIPT)
        return f"dotenvx precommit appended [{hook_path}]"

    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(_HOOK_SCRIPT, encoding="utf-8")
    hook_path.chmod(0o755)
    return f"dotenvx precommit installed [{hook_path}]"


def _ignored_by(ignore_file_lines: list[str], filepath: str) -> bool:
    name = os.path.basename(filepath)
    for line in ignore_file_lines:
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        if fnmatch.fnmatch(filepath, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def _files_to_be_committed(directory: str | os.PathLike[str]) -> set[str] | None:
    """Git-changed files relative to HEAD, or ``None`` outside a git repo / on error."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=directory,
            capture_output=True,
            check=True,
        )
        output = subprocess.run(
            ["git", "diff", "HEAD", "--name-only"],
            cwd=directory,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return set(output.splitlines())
    except (subprocess.SubprocessError, OSError):
        return None


@dataclass
class CheckResult:
    ok: bool
    message: str
    warnings: list[str] = field(default_factory=list)


def _check_env_files_ignored(
    directory: str | os.PathLike[str],
    ignore_filename: str,
    *,
    only_committed: bool,
) -> CheckResult:
    directory = Path(directory)
    warnings: list[str] = []

    if not (directory / ignore_filename).is_file():
        warnings.append(f"{ignore_filename} missing (fix: touch {ignore_filename})")
        ignore_lines: list[str] = []
    else:
        ignore_lines = (
            (directory / ignore_filename).read_text(encoding="utf-8").splitlines()
        )

    committed = _files_to_be_committed(directory) if only_committed else None
    count = 0
    for rel_file in ls(directory, exclude_env_file=_DEFAULT_EXCLUDE_ENV_FILES):
        count += 1
        if only_committed and committed is not None and rel_file not in committed:
            continue

        ignored = _ignored_by(ignore_lines, rel_file)
        if ignored:
            if rel_file in _ALWAYS_ALLOWED:
                warnings.append(f"{rel_file} ignored (should not be)")
            continue

        if rel_file in _ALWAYS_ALLOWED:
            continue

        src = (directory / rel_file).read_text(encoding="utf-8")
        if not sealed(src):
            return CheckResult(
                ok=False,
                message=f"{rel_file} not encrypted/{ignore_filename[1:]}d",
                warnings=warnings,
            )

    message = (
        "no .env files" if count == 0 else f"encrypted/{ignore_filename[1:]}d ({count})"
    )
    if warnings:
        message += f" with warnings ({len(warnings)})"
    return CheckResult(ok=True, message=message, warnings=warnings)


def precommit_check(directory: str | os.PathLike[str] = ".") -> CheckResult:
    """Verify every non-example ``.env*`` file about to be committed is
    encrypted/ignored.

    Simplified port of ``services/precommit.js`` (see module docstring for the
    ignore-pattern-matching gap).
    """
    return _check_env_files_ignored(directory, ".gitignore", only_committed=True)


def prebuild_check(directory: str | os.PathLike[str] = ".") -> CheckResult:
    """Verify every non-example ``.env*`` file is encrypted/dockerignored.

    Simplified port of ``services/prebuild.js``.
    """
    return _check_env_files_ignored(directory, ".dockerignore", only_committed=False)
