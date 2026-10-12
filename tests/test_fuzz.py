"""Property-based fuzz tests for functions that parse user-provided strings.

Each test feeds arbitrary input to a parser and checks that it either
succeeds or raises the documented exception (``ValueError`` with a clear
message). Any other exception fails the test. Where a parser has a real
property worth checking (a pattern matches itself, a date round-trips),
that is asserted too.
"""

from __future__ import annotations

import re
import tempfile
from datetime import date
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from archetype.analysis.codeowners import _matches, parse_codeowners_text
from archetype.analysis.git_utils import parse_date_string
from archetype.analysis.path_filters import normalize_exclude_patterns
from archetype.analysis.pattern import (
    find_matching_nodes,
    matches_pattern,
    pattern_to_regex,
    suggest_patterns,
    validate_pattern,
)
from archetype.config import _parse_check_config, load_check_config
from archetype.rule import escalate, since

# Module-name segments: identifier-ish text without dots.
_SEGMENT = st.text(
    alphabet=st.characters(blacklist_characters=".*", blacklist_categories=("Cs",)),
    min_size=1,
    max_size=8,
)
_MODULE_NAME = st.lists(_SEGMENT, min_size=1, max_size=5).map(".".join)
# Pattern segments may also be a literal wildcard segment.
_PATTERN_SEGMENT = st.one_of(_SEGMENT, st.sampled_from(["*", "**"]), _SEGMENT.map(lambda s: f"{s}*"))
_VALID_PATTERN = st.lists(_PATTERN_SEGMENT, min_size=1, max_size=5).map(".".join)
# Text weighted toward the characters patterns care about.
_PATTERNISH_TEXT = st.text(alphabet=st.sampled_from("ab.*_-/?[]\\ \n"), max_size=20) | st.text(max_size=20)


def _assert_clear_value_error(exc: ValueError) -> None:
    assert str(exc), "ValueError raised without a message"


# --- module patterns -------------------------------------------------------


@given(_PATTERNISH_TEXT)
def test_validate_pattern_only_raises_value_error(pattern: str) -> None:
    try:
        validate_pattern(pattern)
    except ValueError as exc:
        _assert_clear_value_error(exc)


@given(_PATTERNISH_TEXT, _PATTERNISH_TEXT)
def test_matches_pattern_never_crashes(module_name: str, pattern: str) -> None:
    try:
        result = matches_pattern(module_name, pattern)
    except ValueError as exc:
        _assert_clear_value_error(exc)
    else:
        assert isinstance(result, bool)


@given(_PATTERNISH_TEXT, st.lists(_PATTERNISH_TEXT, max_size=5))
def test_find_matching_nodes_never_crashes(pattern: str, nodes: list[str]) -> None:
    try:
        matched = find_matching_nodes(pattern, nodes)
    except ValueError as exc:
        _assert_clear_value_error(exc)
    else:
        assert all(node in nodes for node in matched)


@given(_PATTERNISH_TEXT, st.lists(_PATTERNISH_TEXT, max_size=5))
def test_suggest_patterns_never_crashes(pattern: str, nodes: list[str]) -> None:
    suggestions = suggest_patterns(pattern, nodes)
    assert len(suggestions) <= 3
    assert all(s in nodes for s in suggestions)


@given(_VALID_PATTERN)
def test_valid_pattern_matches_itself(pattern: str) -> None:
    validate_pattern(pattern)
    assert matches_pattern(pattern, pattern)
    assert find_matching_nodes(pattern, [pattern]) == [pattern]


@given(_MODULE_NAME, _MODULE_NAME)
def test_exact_pattern_matches_itself_and_descendants(name: str, child: str) -> None:
    assert matches_pattern(name, name)
    assert matches_pattern(f"{name}.{child}", name)
    assert find_matching_nodes(name, [name, f"{name}.{child}"]) == [name, f"{name}.{child}"]


@given(_PATTERNISH_TEXT, st.lists(_PATTERNISH_TEXT, max_size=5))
def test_find_matching_nodes_agrees_with_matches_pattern(pattern: str, nodes: list[str]) -> None:
    # Regression: the compiled regex once missed descendants containing a
    # newline ("0.\n" under "0") that matches_pattern() accepted.
    try:
        validate_pattern(pattern)
    except ValueError:
        return
    expected = [node for node in nodes if matches_pattern(node, pattern)]
    assert find_matching_nodes(pattern, nodes) == expected


@given(_MODULE_NAME)
def test_globstar_matches_every_module(name: str) -> None:
    assert matches_pattern(name, "**")


@given(_VALID_PATTERN, _MODULE_NAME)
def test_matches_pattern_agrees_with_compiled_regex(pattern: str, name: str) -> None:
    assert matches_pattern(name, pattern) == bool(pattern_to_regex(pattern).fullmatch(name))


# --- @since / @escalate dates ----------------------------------------------


@given(st.text(max_size=20) | st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True))
def test_parse_date_string_only_raises_value_error(text: str) -> None:
    try:
        parsed = parse_date_string(text)
    except ValueError as exc:
        _assert_clear_value_error(exc)
    else:
        assert isinstance(parsed, date)
        assert parsed.isoformat() == text


@given(st.dates(min_value=date(1000, 1, 1)))
def test_parse_date_string_round_trips(value: date) -> None:
    assert parse_date_string(value.isoformat()) == value


@given(st.text(max_size=20))
def test_since_and_escalate_reject_bad_dates_with_value_error(text: str) -> None:
    for decorator in (since, escalate):
        try:
            decorator(text)
        except ValueError as exc:
            _assert_clear_value_error(exc)


# --- archetype.toml / [tool.archetype] config ------------------------------

_TOML_SCALAR = st.one_of(
    st.booleans(),
    st.integers(min_value=-(2**63), max_value=2**63 - 1),
    st.text(max_size=10),
    st.sampled_from(["text", "json", "sarif", "error", "warning", "off"]),
)
_TOML_VALUE = st.recursive(
    _TOML_SCALAR,
    lambda children: st.lists(children, max_size=3)
    | st.dictionaries(st.text(max_size=8), children, max_size=3),
    max_leaves=10,
)
_CONFIG_KEYS = st.sampled_from(
    ["format", "quiet", "group", "exclude", "excludes", "workers", "cache", "rules", "defaults"]
)
_CONFIG_PAYLOAD = st.dictionaries(_CONFIG_KEYS | st.text(max_size=8), _TOML_VALUE, max_size=6)


@given(_CONFIG_PAYLOAD)
def test_parse_check_config_only_raises_value_error(payload: dict[str, object]) -> None:
    try:
        _parse_check_config(payload, scope="archetype.toml")
    except ValueError as exc:
        _assert_clear_value_error(exc)


@settings(deadline=None, max_examples=50)
@given(st.text(max_size=200))
def test_load_check_config_from_arbitrary_file(text: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "archetype.toml").write_text(text, encoding="utf-8")
        try:
            load_check_config(root)
        except ValueError as exc:
            _assert_clear_value_error(exc)


# --- CODEOWNERS -------------------------------------------------------------

_PATH_TEXT = st.text(alphabet=st.sampled_from("ab/._*?[]! -"), max_size=20) | st.text(max_size=20)


@given(st.text(max_size=300), _PATH_TEXT)
def test_parse_codeowners_never_crashes(text: str, path: str) -> None:
    codeowners = parse_codeowners_text(text)
    owners = codeowners.owners_for(path.replace("\x00", ""))
    assert isinstance(owners, tuple)


@given(_PATH_TEXT, _PATH_TEXT)
def test_codeowners_matcher_never_crashes(pattern: str, path: str) -> None:
    assert isinstance(_matches(pattern, path), bool)


@given(st.lists(st.from_regex(r"[a-z]{1,6}(/[a-z]{1,6}){0,3}", fullmatch=True), min_size=1, max_size=3))
def test_codeowners_last_matching_rule_wins(paths: list[str]) -> None:
    path = paths[0]
    text = f"* @everyone\n/{path} @owner\n"
    assert parse_codeowners_text(text).owners_for(path) == ("@owner",)
    assert parse_codeowners_text(text).owners_for("zzz_unrelated") == ("@everyone",)


# --- exclude patterns -------------------------------------------------------


@given(st.lists(_PATH_TEXT, max_size=6))
def test_normalize_exclude_patterns_is_idempotent(patterns: list[str]) -> None:
    normalized = normalize_exclude_patterns(patterns)
    assert len(set(normalized)) == len(normalized)
    assert all(p and not p.startswith("./") and "\\" not in p for p in normalized)
    # Whitespace is stripped before "./" is removed, so "./ x" keeps its
    # leading space (it names the path " x"); only check idempotence when
    # no such pattern is present.
    if all(not re.match(r"\s", p) for p in normalized):
        assert normalize_exclude_patterns(normalized) == normalized
