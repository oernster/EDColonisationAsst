"""Comparing two version strings, without ever guessing.

Anything unparseable compares as not newer. A malformed tag must never raise
a prompt telling the commander to upgrade to a version that does not exist,
so every doubt resolves towards saying nothing.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

# Where the numeric core of a version ends. A tag may carry a suffix
# (`1.2.3-beta`, `1.2.3+build`, `1.2.3 (2)`); only the dotted integers in
# front of it take part in the comparison, which is what makes a prerelease
# of the running version compare as not newer rather than as newer.
_SUFFIX_SEPARATORS = ("-", "+", " ", "(")

_VERSION_PREFIXES = ("v", "V")


def _numeric_parts(version: str) -> tuple[int, ...] | None:
    """Return the dotted integers in ``version``; None when it holds none."""
    core = version.strip()
    if core[:1] in _VERSION_PREFIXES:
        core = core[1:]
    for separator in _SUFFIX_SEPARATORS:
        core = core.split(separator)[0]
    if not core:
        return None
    parts: list[int] = []
    for piece in core.split("."):
        # isascii as well as isdigit: a superscript digit satisfies isdigit
        # on its own and then raises inside int(), which is exactly the
        # exception this function exists to avoid.
        if not (piece.isascii() and piece.isdigit()):
            return None
        parts.append(int(piece))
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """Whether ``latest`` is a strictly newer version than ``current``.

    Versions of differing length are compared as though the shorter one were
    padded with zeroes, so 1.3 is newer than 1.2.9 and equal to 1.3.0.
    """
    left = _numeric_parts(latest)
    right = _numeric_parts(current)
    if left is None or right is None:
        return False
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    return padded_left > padded_right


__all__ = ["is_newer"]
