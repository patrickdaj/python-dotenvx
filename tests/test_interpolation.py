"""M3: interpolation / expansion (SPEC.md §4).

The vectors here reproduce the exact `node -e` run against the real
`@dotenvx/primitives` module documented in SPEC.md §4, so a regression here
means a real divergence from dotenvx, not a guess gone stale.
"""

from __future__ import annotations

from dotenvx.parser import resolve


def test_confirmed_vectors_from_spec() -> None:
    src = "\n".join(
        [
            "A='raw ${NOTHING} literal'",
            'B="${A}"',
            'C="${UNSET:-fallback}"',
            'D="${UNSET:+alt}"',
            'E="${A:+alt}"',
            'F="\\${ESCAPED}"',
            'G="$(echo cmd-sub-works)"',
        ]
    )
    result = resolve(src)
    assert result == {
        "A": "raw ${NOTHING} literal",
        "B": "raw ${NOTHING} literal",
        "C": "fallback",
        "D": "",
        "E": "alt",
        "F": "${ESCAPED}",
        "G": "cmd-sub-works",
    }


def test_braceless_var_expansion() -> None:
    assert resolve("A=hello\nB=$A world\n") == {"A": "hello", "B": "hello world"}


def test_unset_var_expands_to_empty() -> None:
    assert resolve('A="${NOPE}"\n') == {"A": ""}


def test_default_precedence_process_env_wins_without_overload() -> None:
    result = resolve("A=fromfile\n", process_env={"A": "fromprocess"})
    assert result == {"A": "fromprocess"}


def test_overload_flips_precedence_to_file() -> None:
    result = resolve("A=fromfile\n", process_env={"A": "fromprocess"}, overload=True)
    assert result == {"A": "fromfile"}


def test_single_quoted_skips_command_substitution_too() -> None:
    result = resolve("A='$(echo not-run)'\n")
    assert result == {"A": "$(echo not-run)"}


def test_command_substitution_failure_is_swallowed() -> None:
    # dotenvx catches command-substitution errors and leaves the raw text.
    result = resolve("A=$(exit 1)\n")
    assert result == {"A": "$(exit 1)"}


def test_expansion_sees_earlier_lines_in_same_file() -> None:
    result = resolve("A=base\nB=${A}-suffix\n")
    assert result == {"A": "base", "B": "base-suffix"}
