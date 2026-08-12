"""Deciding whether there is a newer release worth mentioning.

The whole rule set for the update check lives here so that the tray is left
holding Qt wiring and nothing else. The service reads a release, compares it
against the running version and decides what the user should be told; it
never reaches the network itself and never touches a widget.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..models.update_info import ReleaseAsset, UpdateStatus
from .release_source import ReleaseSource
from .version_compare import is_newer

PLATFORM_WINDOWS = "windows"
PLATFORM_MACOS = "macos"
PLATFORM_LINUX = "linux"

# The installer filename suffix to offer per platform. EDCA ships a packaged
# release for Windows only; the other two keys exist so that a source checkout
# on another platform resolves to no asset rather than to the wrong one.
_ASSET_SUFFIXES = {
    PLATFORM_WINDOWS: ".exe",
    PLATFORM_MACOS: ".dmg",
    PLATFORM_LINUX: ".flatpak",
}

_WINDOWS_PLATFORM_PREFIX = "win"
_MACOS_PLATFORM = "darwin"


def platform_key_for(sys_platform: str) -> str:
    """Map a ``sys.platform`` value onto the asset key for that platform."""
    if sys_platform.startswith(_WINDOWS_PLATFORM_PREFIX):
        return PLATFORM_WINDOWS
    if sys_platform == _MACOS_PLATFORM:
        return PLATFORM_MACOS
    return PLATFORM_LINUX


def select_asset_url(
    assets: Sequence[ReleaseAsset],
    platform_key: str,
) -> str | None:
    """Return the download URL for this platform's asset; None when absent.

    An unknown platform key and a release carrying no matching asset are the
    same answer, because both leave the prompt with only the release page to
    offer.
    """
    suffix = _ASSET_SUFFIXES.get(platform_key)
    if suffix is None:
        return None
    for asset in assets:
        if asset.name.lower().endswith(suffix):
            return asset.download_url
    return None


@dataclass(frozen=True, slots=True)
class UpdateService:
    """Answers one question: is there a newer release worth mentioning?"""

    source: ReleaseSource
    current_version: str
    platform_key: str

    def check(self, skipped_version: str | None = None) -> UpdateStatus:
        """Return what the commander should be told.

        ``skipped_version`` is supplied by the automatic checks and left out
        by the manual one, which is the entire difference between them: a
        version the user dismissed stays dismissed until they ask directly.
        """
        release = self.source.latest_release()
        if release is None:
            return UpdateStatus(
                current_version=self.current_version,
                latest_version=None,
                update_available=False,
            )

        newer = is_newer(release.version, self.current_version)
        available = newer and release.version != skipped_version
        return UpdateStatus(
            current_version=self.current_version,
            latest_version=release.version,
            update_available=available,
            download_url=(
                select_asset_url(release.assets, self.platform_key)
                if available
                else None
            ),
            page_url=release.page_url,
        )


__all__ = [
    "PLATFORM_LINUX",
    "PLATFORM_MACOS",
    "PLATFORM_WINDOWS",
    "UpdateService",
    "platform_key_for",
    "select_asset_url",
]
