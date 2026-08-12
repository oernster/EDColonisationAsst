"""Value objects for the in-app update check.

Plain frozen dataclasses rather than the pydantic models beside them: nothing
here crosses the HTTP boundary. These are internal readings of one GitHub
release, built by the adapter and consumed by the tray, so the validation
belongs at the point the payload is parsed rather than in the type itself.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    """One downloadable file attached to a published release."""

    name: str
    download_url: str


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """The latest published release, as much of it as the check needs."""

    version: str
    page_url: str
    assets: tuple[ReleaseAsset, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    """The answer to one update check.

    ``update_available`` is false both when the running version is current and
    when a newer one was found that the commander has already skipped, so a
    caller never has to tell those two apart. The manual check passes no
    skipped version, which is the whole reason it reports anyway.
    """

    current_version: str
    latest_version: str | None
    update_available: bool
    download_url: str | None = None
    page_url: str | None = None

    @property
    def reachable(self) -> bool:
        """Whether the check reached GitHub at all.

        An unreachable check and an up-to-date one are the same shape and must
        not read as the same outcome: one says nothing is newer, the other says
        nothing is known.
        """
        return self.latest_version is not None


__all__ = ["ReleaseAsset", "ReleaseInfo", "UpdateStatus"]
