"""Commodity name normalisation for Fleet carrier views.

Journal payloads carry commodity names in three shapes: a raw symbol
(``lowtemperaturediamond``), a localised label the game supplies and
``$name;`` wrappers. Both directions of that problem live here: one
function for what the user reads, one for the key orders are matched on.
"""

from __future__ import annotations

from ..utils.logger import get_logger

logger = get_logger(__name__)


def _prettify_commodity_name(raw_name: str, localised: str | None = None) -> str:
    """
    Produce a human‑friendly commodity name for display.

    Priority:
      1. Use the journal's localized name when provided (Commodity_Localised).
      2. Apply lightweight cleanup heuristics to the internal name as a fallback.

    The goal is to avoid obviously unformatted identifiers such as
    "fruitandvegetables" where possible, without trying to reimplement the
    entire commodity name table in code.
    """
    # Prefer the explicit localized label from the journal if available.
    if localised:
        return localised

    name = raw_name or ""
    name = name.strip()
    if not name:
        return raw_name

    # Strip common journal wrappers like "$Foo_Bar_Name;" if they ever appear
    # in carrier events.
    if name.startswith("$") and name.endswith(";"):
        name = name[1:-1]

    # Replace underscores with spaces.
    name = name.replace("_", " ")

    # Known manual overrides for common unspaced identifiers.
    overrides = {
        "fruitandvegetables": "Fruit and Vegetables",
    }
    key = name.lower().replace(" ", "")
    if key in overrides:
        return overrides[key]

    # Title-case the name but keep small connector words (and, of, in, the,
    # etc.) lower-case unless they are the first word.
    words = name.split()
    if not words:
        return name

    lowercase_words = {
        "and",
        "or",
        "of",
        "in",
        "on",
        "the",
        "for",
        "to",
        "at",
        "from",
        "by",
        "as",
    }

    normalised_words: list[str] = []
    for idx, w in enumerate(words):
        base = w.lower()
        if idx > 0 and base in lowercase_words:
            normalised_words.append(base)
        else:
            # Capitalise the first character and lower-case the rest.
            normalised_words.append(base[:1].upper() + base[1:])

    return " ".join(normalised_words)


def _normalise_carrier_commodity_key(name: str) -> str:
    """
    Normalise a carrier commodity identifier into a stable key.

    This ensures that logically identical commodities with different raw
    representations (e.g. "titanium", "Titanium", "$Titanium_Name;") are
    treated as the same thing for order aggregation and cancellation.
    """
    key = (name or "").strip().lower()
    if not key:
        return key

    # Strip journal-style wrappers.
    if key.startswith("$") and key.endswith(";"):
        key = key[1:-1]

    # Strip a trailing "_name" suffix if present.
    key = key.removesuffix("_name")

    # Normalise separators and whitespace.
    key = key.replace("_", " ")
    key = key.replace(" ", "")

    return key
