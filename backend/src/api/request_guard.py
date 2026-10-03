"""Which requests the backend answers and which writes it accepts.

Two rules, applied before any route runs:

- **The Host must name this machine.** A page can rebind its own DNS name to
  127.0.0.1; to the browser it is then same-origin with the backend, so CORS
  never applies and the page reads everything. An IP literal cannot be rebound
  (the browser only sends it to that address), nor can `localhost`, which
  browsers resolve to loopback themselves; this machine's own names are the
  only other names a real user types. Everything else is refused. That keeps
  the documented tablet access, which uses the PC's LAN address.
- **A write that names an Origin must come from a trusted one.** A bodiless
  POST is a CORS "simple request": the browser sends it without a preflight
  and only hides the answer, so the write has already happened. Browsers name
  the Origin on every cross-origin POST; a request with no Origin is not from
  a web page. Trusted means same-origin with the Host or listed in the
  configured CORS origins (the Vite dev server).

Neither rule authenticates anybody: a LAN peer that can reach the port can
still read and write, which DECISIONS-TRADEOFFS.md records.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import ipaddress
import socket
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# Methods that change state. Everything else is a read.
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# The loopback name browsers resolve themselves; also the reserved suffix
# under which every name is loopback too (RFC 6761).
_LOOPBACK_NAME = "localhost"
_LOOPBACK_SUFFIX = "." + _LOOPBACK_NAME

# The multicast DNS suffix a LAN device may use to reach this machine by name.
_MDNS_SUFFIX = ".local"

# The status codes the two refusals answer with.
_UNTRUSTED_HOST_STATUS = 400
_UNTRUSTED_ORIGIN_STATUS = 403
_UNTRUSTED_HOST_TEXT = "Untrusted Host header"
_UNTRUSTED_ORIGIN_TEXT = "Cross-origin write refused"

_HEADER_ENCODING = "latin-1"


def _hostname_of(host_header: str) -> str | None:
    """The bare host name of a Host header value; None when malformed."""
    value = host_header.strip().lower()
    if value.startswith("["):
        closing = value.find("]")
        if closing < 0:
            return None
        return value[1:closing]
    if value.count(":") == 1:
        value = value.rsplit(":", 1)[0]
    return value.rstrip(".")


def _is_ip_literal(name: str) -> bool:
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def host_is_trusted(host_header: str, machine_names: frozenset[str]) -> bool:
    """Whether a Host header names this machine rather than a rebound domain.

    An absent Host (HTTP/1.0) cannot carry a rebound name, so it is accepted.
    """
    if not host_header.strip():
        return True
    name = _hostname_of(host_header)
    if name is None:
        return False
    if _is_ip_literal(name):
        return True
    if name == _LOOPBACK_NAME or name.endswith(_LOOPBACK_SUFFIX):
        return True
    return name in machine_names


def origin_is_trusted(
    origin: str, host_header: str, allowed_origins: Iterable[str]
) -> bool:
    """Whether a write's Origin is this page itself or a configured origin."""
    normalised = origin.strip().rstrip("/").lower()
    if normalised in {entry.rstrip("/").lower() for entry in allowed_origins}:
        return True
    netloc = urlsplit(normalised).netloc
    return bool(netloc) and netloc == host_header.strip().lower()


def local_machine_names(
    hostname: Callable[[], str] = socket.gethostname,
    fqdn: Callable[[], str] = socket.getfqdn,
) -> frozenset[str]:
    """This machine's own names: its host name, that name on mDNS and its FQDN."""
    short = hostname().strip().lower().rstrip(".")
    return frozenset(
        {short, short + _MDNS_SUFFIX, fqdn().strip().lower().rstrip(".")}
    ) - {""}


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", ()):
        if key == name:
            return value.decode(_HEADER_ENCODING)
    return ""


class RequestGuardMiddleware:
    """Refuses an untrusted Host on every request and a foreign Origin on writes."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_origins: Iterable[str],
        machine_names: frozenset[str],
    ) -> None:
        self._app = app
        self._allowed_origins = tuple(allowed_origins)
        self._machine_names = machine_names

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        host = _header(scope, b"host")
        if not host_is_trusted(host, self._machine_names):
            response = PlainTextResponse(
                _UNTRUSTED_HOST_TEXT, status_code=_UNTRUSTED_HOST_STATUS
            )
            await response(scope, receive, send)
            return

        origin = _header(scope, b"origin")
        if (
            scope.get("method") in STATE_CHANGING_METHODS
            and origin
            and not origin_is_trusted(origin, host, self._allowed_origins)
        ):
            response = PlainTextResponse(
                _UNTRUSTED_ORIGIN_TEXT, status_code=_UNTRUSTED_ORIGIN_STATUS
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
