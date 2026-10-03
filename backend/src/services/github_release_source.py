"""Reading the latest published release from the public GitHub releases API.

This is the one outbound request the backend makes. It is anonymous, it is a
single GET and it carries nothing of the commander's: no identifier, no
journal data, no telemetry. Every failure is silent, because an update check
that cannot reach GitHub is not a problem the user needs telling about.

The standard library does the request rather than the httpx already in the
requirements, so the compiled runtime gains no import it would not otherwise
have for the sake of one call a day.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from ..models.update_info import ReleaseAsset, ReleaseInfo
from ..utils.logger import get_logger
from .release_source import ReleaseSource

logger = get_logger(__name__)

# The releases/latest endpoint returns only a published, non-draft,
# non-prerelease release, so a tag pushed mid-development is structurally
# invisible here and cannot prompt anybody to upgrade to it. That guard is the
# endpoint's own contract, which is why there is deliberately no client-side
# re-check of the draft and prerelease flags.
_SCHEME = "https"
_API_HOST = "api.github.com"
_SITE_HOST = "github.com"
_REPOSITORY = "oernster/EDColonisationAsst"

RELEASES_API_URL = f"{_SCHEME}://{_API_HOST}/repos/{_REPOSITORY}/releases/latest"

# Every URL the tray may open (the release page, an asset) lives under this.
_TRUSTED_PATH_PREFIX = f"/{_REPOSITORY}/"

ACCEPT_HEADER = "application/vnd.github+json"

# Long enough for a slow link, short enough that nothing waits on it. The
# check is a courtesy: one request, no retries.
REQUEST_TIMEOUT_S = 5.0

# Whatever performs the request. Injected so no test ever reaches the network.
Opener = Callable[..., Any]


def is_trusted_release_url(url: str) -> bool:
    """Whether a URL from the payload is this project's page on github.com.

    The tray hands the URL straight to the desktop to open, so a payload
    naming a `file:` URL or another site would be opened as given. Only
    HTTPS on github.com itself, with no credentials and under this
    repository, is kept.
    """
    parts = urllib.parse.urlsplit(url)
    return (
        parts.scheme == _SCHEME
        and parts.netloc == _SITE_HOST
        and parts.path.startswith(_TRUSTED_PATH_PREFIX)
    )


class SameHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only when it stays on the host asked.

    GitHub redirects a renamed repository within its API host; anything that
    leaves it is refused rather than followed to wherever it points.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if (
            urllib.parse.urlsplit(newurl).netloc
            != urllib.parse.urlsplit(req.full_url).netloc
        ):
            raise urllib.error.HTTPError(
                newurl, code, "Redirect off the API host refused", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_opener() -> Opener:
    """urlopen's behaviour, except that redirects may not change host."""
    return urllib.request.build_opener(SameHostRedirectHandler()).open


def _text(value: object) -> str | None:
    """Return a non-empty string; None for anything else at all."""
    if isinstance(value, str) and value:
        return value
    return None


def _read_assets(raw: object) -> tuple[ReleaseAsset, ...]:
    """Read the asset list, dropping every entry that is not usable.

    A malformed entry is skipped rather than failing the whole release: the
    version comparison is the part that matters; a release page is always offered
    even when no asset can be resolved.
    """
    if not isinstance(raw, list):
        return ()
    found: list[ReleaseAsset] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = _text(entry.get("name"))
        download_url = _text(entry.get("browser_download_url"))
        if (
            name is not None
            and download_url is not None
            and is_trusted_release_url(download_url)
        ):
            found.append(ReleaseAsset(name=name, download_url=download_url))
    return tuple(found)


def parse_release(payload: object) -> ReleaseInfo | None:
    """Read a releases/latest payload; None when it is not a usable one."""
    if not isinstance(payload, dict):
        return None
    tag = _text(payload.get("tag_name"))
    page_url = _text(payload.get("html_url"))
    if tag is None or page_url is None or not is_trusted_release_url(page_url):
        return None
    version = tag[1:] if tag[:1] in ("v", "V") else tag
    return ReleaseInfo(
        version=version,
        page_url=page_url,
        assets=_read_assets(payload.get("assets")),
    )


class GitHubReleaseSource(ReleaseSource):
    """The real source: one anonymous GET against the public releases API."""

    def __init__(
        self,
        opener: Opener | None = None,
        url: str = RELEASES_API_URL,
    ) -> None:
        self._opener = opener if opener is not None else _default_opener()
        self._url = url

    def latest_release(self) -> ReleaseInfo | None:
        """Fetch and read the latest release; None on any failure."""
        request = urllib.request.Request(
            self._url,
            headers={"Accept": ACCEPT_HEADER},
        )
        try:
            with self._opener(request, timeout=REQUEST_TIMEOUT_S) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError):
            # Every network failure arrives as an OSError (URLError and
            # HTTPError both subclass it); a body that is not JSON or not
            # UTF-8 arrives as a ValueError. Neither is worth surfacing.
            logger.debug("The update check could not read the latest release.")
            return None
        return parse_release(payload)


__all__ = [
    "ACCEPT_HEADER",
    "RELEASES_API_URL",
    "REQUEST_TIMEOUT_S",
    "GitHubReleaseSource",
    "SameHostRedirectHandler",
    "is_trusted_release_url",
    "parse_release",
]
