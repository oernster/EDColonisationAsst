"""What the update check decides, given a release and a running version.

Every test drives a hand-written source rather than a mock library, so nothing
here reaches the network and the seam under test is the real one.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from src.models.update_info import ReleaseAsset, ReleaseInfo, UpdateStatus
from src.services.release_source import ReleaseSource
from src.services.update_service import (
    PLATFORM_LINUX,
    PLATFORM_MACOS,
    PLATFORM_WINDOWS,
    UpdateService,
    platform_key_for,
    select_asset_url,
)

INSTALLER = ReleaseAsset(
    name="EDColonisationAsstInstaller.exe",
    download_url="https://example.invalid/EDColonisationAsstInstaller.exe",
)
PAGE_URL = "https://example.invalid/releases/tag/v3.3.0"


class StubSource(ReleaseSource):
    """A release source that returns whatever the test handed it."""

    def __init__(self, release: ReleaseInfo | None) -> None:
        self._release = release
        self.calls = 0

    def latest_release(self) -> ReleaseInfo | None:
        self.calls += 1
        return self._release


def _release(
    version: str = "3.3.0", assets: tuple[ReleaseAsset, ...] = ()
) -> ReleaseInfo:
    return ReleaseInfo(version=version, page_url=PAGE_URL, assets=assets)


def _service(
    release: ReleaseInfo | None,
    current: str = "3.2.1",
    platform_key: str = PLATFORM_WINDOWS,
) -> UpdateService:
    return UpdateService(
        source=StubSource(release),
        current_version=current,
        platform_key=platform_key,
    )


# ----------------------------------------------------------------- the outcomes


def test_an_unreachable_source_reports_nothing_known() -> None:
    """Not the same as up to date: the check has no reading at all."""
    status = _service(None).check()

    assert status == UpdateStatus(
        current_version="3.2.1",
        latest_version=None,
        update_available=False,
    )
    assert status.reachable is False


def test_a_newer_release_is_available_with_its_asset_and_page() -> None:
    status = _service(_release(assets=(INSTALLER,))).check()

    assert status.update_available is True
    assert status.latest_version == "3.3.0"
    assert status.download_url == INSTALLER.download_url
    assert status.page_url == PAGE_URL
    assert status.reachable is True


def test_the_running_version_is_reachable_but_not_available() -> None:
    status = _service(_release(version="3.2.1", assets=(INSTALLER,))).check()

    assert status.update_available is False
    assert status.reachable is True
    assert status.latest_version == "3.2.1"
    # No download is offered for a version already installed.
    assert status.download_url is None


def test_an_older_release_is_not_available() -> None:
    status = _service(_release(version="3.1.0")).check()

    assert status.update_available is False


def test_a_release_with_no_matching_asset_still_offers_the_page() -> None:
    status = _service(_release(assets=())).check()

    assert status.update_available is True
    assert status.download_url is None
    assert status.page_url == PAGE_URL


# ------------------------------------------------------------------ the skip


def test_the_skipped_version_is_seen_but_not_offered() -> None:
    status = _service(_release(assets=(INSTALLER,))).check(skipped_version="3.3.0")

    assert status.latest_version == "3.3.0"
    assert status.update_available is False
    assert status.download_url is None


def test_a_different_skipped_version_still_prompts() -> None:
    """Skipping one release must not silence every release after it."""
    status = _service(_release(assets=(INSTALLER,))).check(skipped_version="3.2.5")

    assert status.update_available is True


def test_the_manual_check_passes_no_skip_and_so_still_offers() -> None:
    """The manual path is exactly `check()` with no argument."""
    service = _service(_release(assets=(INSTALLER,)))

    assert service.check(skipped_version="3.3.0").update_available is False
    assert service.check().update_available is True


def test_the_source_is_asked_once_per_check() -> None:
    source = StubSource(_release())
    service = UpdateService(
        source=source,
        current_version="3.2.1",
        platform_key=PLATFORM_WINDOWS,
    )

    service.check()
    service.check()

    assert source.calls == 2


# ------------------------------------------------------------- asset selection


def test_each_platform_selects_its_own_installer() -> None:
    assets = (
        ReleaseAsset(name="EDCA.dmg", download_url="https://example.invalid/dmg"),
        INSTALLER,
        ReleaseAsset(name="EDCA.flatpak", download_url="https://example.invalid/fp"),
    )

    assert select_asset_url(assets, PLATFORM_WINDOWS) == INSTALLER.download_url
    assert select_asset_url(assets, PLATFORM_MACOS) == "https://example.invalid/dmg"
    assert select_asset_url(assets, PLATFORM_LINUX) == "https://example.invalid/fp"


def test_the_suffix_match_ignores_case() -> None:
    shouty = ReleaseAsset(name="EDCA.EXE", download_url="https://example.invalid/exe")

    assert select_asset_url((shouty,), PLATFORM_WINDOWS) == shouty.download_url


def test_no_asset_matches_an_empty_release() -> None:
    assert select_asset_url((), PLATFORM_WINDOWS) is None


def test_no_asset_matches_a_release_carrying_only_other_platforms() -> None:
    other = ReleaseAsset(name="EDCA.dmg", download_url="https://example.invalid/dmg")

    assert select_asset_url((other,), PLATFORM_WINDOWS) is None


def test_an_unknown_platform_key_selects_nothing() -> None:
    """Rather than falling through to the first asset in the list."""
    assert select_asset_url((INSTALLER,), "solaris") is None


def test_an_unknown_platform_key_leaves_the_prompt_the_page() -> None:
    status = _service(_release(assets=(INSTALLER,)), platform_key="solaris").check()

    assert status.update_available is True
    assert status.download_url is None
    assert status.page_url == PAGE_URL


# --------------------------------------------------------------- platform keys


def test_sys_platform_maps_onto_the_asset_keys() -> None:
    assert platform_key_for("win32") == PLATFORM_WINDOWS
    assert platform_key_for("windows") == PLATFORM_WINDOWS
    assert platform_key_for("darwin") == PLATFORM_MACOS
    assert platform_key_for("linux") == PLATFORM_LINUX
    assert platform_key_for("freebsd14") == PLATFORM_LINUX
