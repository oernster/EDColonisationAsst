"""What the update check is willing to follow and to open.

The tray opens whatever URL the release payload names; the request followed
redirects to any host. A payload naming a `file:` URL or another site was
accepted as given (measured), as was a redirect to one. It takes a
compromise on the GitHub side to matter; it is closed anyway: only HTTPS
github.com URLs under this project are kept and a redirect may not leave the
API host.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from email.message import Message

import pytest

from src.services.github_release_source import (
    SameHostRedirectHandler,
    is_trusted_release_url,
    parse_release,
)

_PAGE = "https://github.com/oernster/EDColonisationAsst/releases/tag/v9.9.9"
_ASSET = (
    "https://github.com/oernster/EDColonisationAsst/releases/download/v9.9.9/"
    "EDColonisationAsst-setup.exe"
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/System32/calc.exe",
        "http://github.com/oernster/EDColonisationAsst/releases/tag/v9.9.9",
        "https://evil.example/oernster/EDColonisationAsst/releases/tag/v9.9.9",
        "https://github.com.evil.example/oernster/EDColonisationAsst/x",
        "https://github.com/someone-else/EDColonisationAsst/releases/tag/v9",
        "https://user@github.com/oernster/EDColonisationAsst/releases/tag/v9",
    ],
)
def test_an_untrusted_url_is_refused(url: str) -> None:
    assert is_trusted_release_url(url) is False


def test_the_project_release_urls_are_trusted() -> None:
    assert is_trusted_release_url(_PAGE) is True
    assert is_trusted_release_url(_ASSET) is True


def test_a_release_whose_page_is_untrusted_is_not_a_release() -> None:
    payload = {"tag_name": "v9.9.9", "html_url": "file:///C:/evil.html"}

    assert parse_release(payload) is None


def test_an_untrusted_asset_is_dropped() -> None:
    payload = {
        "tag_name": "v9.9.9",
        "html_url": _PAGE,
        "assets": [
            {"name": "evil.exe", "browser_download_url": "https://evil.example/x"},
            {"name": "setup.exe", "browser_download_url": _ASSET},
        ],
    }

    release = parse_release(payload)

    assert [asset.download_url for asset in release.assets] == [_ASSET]


def _redirect(target: str):
    handler = SameHostRedirectHandler()
    request = urllib.request.Request(
        "https://api.github.com/repos/oernster/EDColonisationAsst/releases/latest"
    )
    return handler.redirect_request(request, None, 301, "Moved", Message(), target)


def test_a_redirect_off_the_api_host_is_refused() -> None:
    with pytest.raises(urllib.error.HTTPError):
        _redirect("https://evil.example/latest")


def test_a_redirect_within_the_api_host_is_followed() -> None:
    followed = _redirect("https://api.github.com/repositories/1/releases/latest")

    assert followed.full_url == "https://api.github.com/repositories/1/releases/latest"
