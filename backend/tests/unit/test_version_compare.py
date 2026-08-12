"""Comparing version strings, especially the ones that are not versions.

The rule under test throughout: anything that cannot be read as a dotted
integer version compares as not newer. A prompt telling the commander to
upgrade to a version that does not exist is worse than no prompt at all, so
every doubt has to resolve the same way.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from src.services.version_compare import is_newer


def test_a_higher_version_is_newer() -> None:
    assert is_newer("3.3.0", "3.2.1") is True


def test_an_equal_version_is_not_newer() -> None:
    assert is_newer("3.2.1", "3.2.1") is False


def test_a_lower_version_is_not_newer() -> None:
    assert is_newer("3.2.0", "3.2.1") is False


def test_each_component_is_compared_numerically_not_as_text() -> None:
    """The case a string comparison gets wrong: 10 sorts before 9 as text."""
    assert is_newer("3.10.0", "3.9.0") is True
    assert is_newer("3.9.0", "3.10.0") is False


def test_a_leading_v_is_ignored_on_either_side() -> None:
    assert is_newer("v3.3.0", "3.2.1") is True
    assert is_newer("3.3.0", "v3.2.1") is True
    assert is_newer("v3.2.1", "v3.2.1") is False


def test_an_uppercase_v_is_ignored_too() -> None:
    assert is_newer("V3.3.0", "3.2.1") is True


def test_surrounding_whitespace_is_ignored() -> None:
    """The VERSION file is read with strip(), a tag need not be."""
    assert is_newer("  3.3.0\n", "3.2.1") is True


def test_a_shorter_version_is_padded_with_zeroes() -> None:
    assert is_newer("3.3", "3.2.9") is True
    assert is_newer("3.3", "3.3.0") is False
    assert is_newer("3.3.1", "3.3") is True


def test_an_extra_component_counts() -> None:
    assert is_newer("3.2.1.1", "3.2.1") is True


def test_a_prerelease_of_the_running_version_is_not_newer() -> None:
    """Only the numeric core compares, so 3.2.1-beta is not newer than 3.2.1."""
    assert is_newer("3.2.1-beta", "3.2.1") is False
    assert is_newer("3.2.1+build7", "3.2.1") is False
    assert is_newer("3.2.1 (2)", "3.2.1") is False


def test_a_prerelease_of_a_later_version_is_still_newer() -> None:
    assert is_newer("3.3.0-rc1", "3.2.1") is True


def test_an_unparseable_latest_is_not_newer() -> None:
    assert is_newer("banana", "3.2.1") is False


def test_an_unparseable_current_is_not_newer() -> None:
    """The 0.0.0-dev style fallback must never be told it is out of date."""
    assert is_newer("3.3.0", "not-a-version") is False


def test_both_unparseable_is_not_newer() -> None:
    assert is_newer("", "") is False


def test_a_bare_v_is_not_a_version() -> None:
    assert is_newer("v", "3.2.1") is False


def test_a_non_ascii_digit_is_not_a_version() -> None:
    """A superscript satisfies isdigit and then raises inside int()."""
    assert is_newer("3.².1", "3.2.1") is False


def test_an_empty_component_is_not_a_version() -> None:
    assert is_newer("3..1", "3.2.1") is False
