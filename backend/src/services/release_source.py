"""The seam between the update check and wherever releases are read from.

An abstract base class rather than a Protocol, matching
``IColonisationRepository``: the adapter subclasses it, so this module is
imported at runtime and measured like any other file, instead of needing an
exemption from the coverage gate that a TYPE_CHECKING-only Protocol would.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.update_info import ReleaseInfo


class ReleaseSource(ABC):
    """Somewhere the latest published release can be read from."""

    @abstractmethod
    def latest_release(self) -> ReleaseInfo | None:
        """Return the latest published release; None when it cannot be had.

        None is the entire error contract. A source that cannot be reached, a
        payload that cannot be read and a release missing a field the check
        needs are all the same thing to the caller: nothing to compare
        against, so say nothing.
        """


__all__ = ["ReleaseSource"]
