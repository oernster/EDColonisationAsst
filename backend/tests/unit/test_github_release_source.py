"""Reading the GitHub releases payload, plus every way it can be unusable.

No test here reaches the network: the opener is injected and every case is
driven through a hand-written stand-in that behaves like `urlopen`, which
returns a context manager.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import json
from typing import Any
import urllib.request

from src.services.github_release_source import (
    ACCEPT_HEADER,
    RELEASES_API_URL,
    REQUEST_TIMEOUT_S,
    GitHubReleaseSource,
    parse_release,
)

PAYLOAD = {
    "tag_name": "v3.3.0",
    "html_url": "https://example.invalid/releases/tag/v3.3.0",
    "assets": [
        {
            "name": "EDColonisationAsstInstaller.exe",
            "browser_download_url": "https://example.invalid/setup.exe",
        }
    ],
}


class FakeResponse:
    """The part of a urlopen response the adapter uses."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class FakeOpener:
    """Records the request it was handed and returns a canned body."""

    def __init__(self, body: bytes | None = None, error: Exception | None = None):
        self._body = body if body is not None else json.dumps(PAYLOAD).encode("utf-8")
        self._error = error
        self.request: Any = None
        self.timeout: float | None = None

    def __call__(self, request: Any, timeout: float | None = None) -> FakeResponse:
        self.request = request
        self.timeout = timeout
        if self._error is not None:
            raise self._error
        return FakeResponse(self._body)


def _source(**kwargs: Any) -> tuple[GitHubReleaseSource, FakeOpener]:
    opener = FakeOpener(**kwargs)
    return GitHubReleaseSource(opener=opener), opener


# ---------------------------------------------------------------- the request


def test_the_request_targets_the_latest_release_endpoint() -> None:
    source, opener = _source()

    source.latest_release()

    assert isinstance(opener.request, urllib.request.Request)
    assert opener.request.full_url == RELEASES_API_URL
    # The repository name is baked into the URL, so a check pointed at the
    # wrong project is a silent defect this assertion exists to catch.
    assert "EDColonisationAsst" in RELEASES_API_URL


def test_the_request_asks_for_the_github_json_media_type() -> None:
    source, opener = _source()

    source.latest_release()

    # Request title-cases header names as it stores them.
    assert opener.request.get_header("Accept") == ACCEPT_HEADER


def test_the_request_carries_a_timeout() -> None:
    """An update check must never be able to hang the tray."""
    source, opener = _source()

    source.latest_release()

    assert opener.timeout == REQUEST_TIMEOUT_S


def test_the_default_opener_is_urlopen() -> None:
    """Constructed with nothing, the adapter is the real thing."""
    assert GitHubReleaseSource()._opener is urllib.request.urlopen


def test_an_explicit_url_overrides_the_default() -> None:
    opener = FakeOpener()
    source = GitHubReleaseSource(opener=opener, url="https://example.invalid/api")

    source.latest_release()

    assert opener.request.full_url == "https://example.invalid/api"


# ---------------------------------------------------------------- happy path


def test_a_published_release_is_read_whole() -> None:
    source, _ = _source()

    release = source.latest_release()

    assert release is not None
    assert release.version == "3.3.0"
    assert release.page_url == PAYLOAD["html_url"]
    assert len(release.assets) == 1
    assert release.assets[0].name == "EDColonisationAsstInstaller.exe"
    assert release.assets[0].download_url == "https://example.invalid/setup.exe"


# ---------------------------------------------------------------- failures


def test_an_unreachable_host_reads_as_nothing() -> None:
    source, _ = _source(error=OSError("no route to host"))

    assert source.latest_release() is None


def test_a_body_that_is_not_json_reads_as_nothing() -> None:
    source, _ = _source(body=b"<html>rate limited</html>")

    assert source.latest_release() is None


def test_a_body_that_is_not_utf8_reads_as_nothing() -> None:
    source, _ = _source(body=b"\xff\xfe not text")

    assert source.latest_release() is None


# ---------------------------------------------------------------- parsing


def test_a_payload_that_is_not_an_object_is_not_a_release() -> None:
    assert parse_release(["a list"]) is None
    assert parse_release(None) is None
    assert parse_release("a string") is None


def test_a_missing_tag_is_not_a_release() -> None:
    assert parse_release({"html_url": "https://example.invalid/x"}) is None


def test_an_empty_or_mistyped_tag_is_not_a_release() -> None:
    page = "https://example.invalid/x"
    assert parse_release({"tag_name": "", "html_url": page}) is None
    assert parse_release({"tag_name": 330, "html_url": page}) is None


def test_a_missing_page_url_is_not_a_release() -> None:
    assert parse_release({"tag_name": "v3.3.0"}) is None


def test_an_empty_or_mistyped_page_url_is_not_a_release() -> None:
    assert parse_release({"tag_name": "v3.3.0", "html_url": ""}) is None
    assert parse_release({"tag_name": "v3.3.0", "html_url": 7}) is None


def test_a_leading_v_is_stripped_from_the_tag() -> None:
    page = "https://example.invalid/x"

    assert parse_release({"tag_name": "v3.3.0", "html_url": page}).version == "3.3.0"
    assert parse_release({"tag_name": "V3.3.0", "html_url": page}).version == "3.3.0"
    assert parse_release({"tag_name": "3.3.0", "html_url": page}).version == "3.3.0"


def test_a_release_with_no_assets_key_carries_none() -> None:
    release = parse_release(
        {"tag_name": "v3.3.0", "html_url": "https://example.invalid/x"}
    )

    assert release is not None
    assert release.assets == ()


def test_assets_that_are_not_a_list_carry_none() -> None:
    release = parse_release(
        {
            "tag_name": "v3.3.0",
            "html_url": "https://example.invalid/x",
            "assets": {"not": "a list"},
        }
    )

    assert release is not None
    assert release.assets == ()


def test_unusable_asset_entries_are_dropped_and_the_rest_kept() -> None:
    """One bad entry must not cost the release its usable assets."""
    release = parse_release(
        {
            "tag_name": "v3.3.0",
            "html_url": "https://example.invalid/x",
            "assets": [
                "not an object",
                {"name": "no url"},
                {"browser_download_url": "https://example.invalid/no-name"},
                {"name": "", "browser_download_url": "https://example.invalid/empty"},
                {"name": "EDCA.exe", "browser_download_url": ""},
                {"name": 7, "browser_download_url": "https://example.invalid/n"},
                {
                    "name": "EDColonisationAsstInstaller.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                },
            ],
        }
    )

    assert release is not None
    assert len(release.assets) == 1
    assert release.assets[0].name == "EDColonisationAsstInstaller.exe"
