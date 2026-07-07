"""M2: plaintext ``.env`` parsing (SPEC.md §2.1).

Behavior is pinned to `@dotenvx/primitives` `src/scan.js`, confirmed by
running the real module (see SPEC.md §2.1 for the verified vectors).
"""

from __future__ import annotations

from dotenvx.parser import parse, scan


def test_basic_key_value() -> None:
    assert parse("HELLO=World\n") == {"HELLO": "World"}


def test_blank_lines_and_comments_are_skipped() -> None:
    src = "\n# a full-line comment\nA=1\n\nB=2\n"
    assert parse(src) == {"A": "1", "B": "2"}


def test_export_prefix_is_ignored() -> None:
    assert parse("export A=exported_ok\n") == {"A": "exported_ok"}


def test_trailing_inline_comment_stripped_for_unquoted() -> None:
    assert parse("A=bare # trailing comment\n") == {"A": "bare"}


def test_trailing_inline_comment_stripped_for_quoted() -> None:
    assert parse('A="quoted" # trailing comment\n') == {"A": "quoted"}


def test_single_quotes_are_fully_literal() -> None:
    assert parse("A='raw ${NOTHING} literal'\n") == {"A": "raw ${NOTHING} literal"}


def test_double_quote_escapes_expand_n_r_t() -> None:
    assert parse('A="line1\\nline2"\n') == {"A": "line1\nline2"}
    assert parse('B="tab\\there"\n') == {"B": "tab\there"}
    assert parse('C="cr\\rhere"\n') == {"C": "cr\rhere"}


def test_double_quote_escaped_quote_is_not_unescaped() -> None:
    # Confirmed quirk (inherited from `dotenv`): \" inside a double-quoted
    # value stays as the literal two characters, it does not become `"`.
    assert parse('A="say \\"hi\\" now"\n') == {"A": 'say \\"hi\\" now'}


def test_multiline_value_via_quotes() -> None:
    src = 'A="line one\nline two\nline three"\n'
    assert parse(src) == {"A": "line one\nline two\nline three"}


def test_duplicate_key_last_wins() -> None:
    assert parse("A=first\nA=second\n") == {"A": "second"}


def test_key_charset_dots_and_hyphens() -> None:
    assert parse("my.key-name=value\n") == {"my.key-name": "value"}


def test_colon_separator() -> None:
    assert parse("A: value\n") == {"A": "value"}


def test_scan_preserves_quote_type_and_duplicates() -> None:
    lines = scan("A=1\nA='2'\n")
    assert [(line.name, line.value, line.quote) for line in lines] == [
        ("A", "1", ""),
        ("A", "2", "'"),
    ]


def test_empty_value() -> None:
    assert parse("A=\n") == {"A": ""}
