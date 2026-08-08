"""Reading startup progress off a health response.

Split out of backend_server, which had grown past the module limit and was
carrying two unrelated jobs: running the uvicorn server, and interpreting what
that server says about itself. This is the second.

Everything here is defensive by design. It runs against a backend that is by
definition still starting, so a truncated response, an older build that does
not report progress at all, or a response object with no body to read are all
expected answers rather than faults. Each of them yields None, and None means
the splash keeps showing whatever it was already showing.
"""

from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(frozen=True)
class StartupReport:
    """What the backend says it is doing while the splash waits.

    Every field is optional, because a backend part-way through starting can
    answer the health check while having nothing useful to say yet.
    """

    percent: int | None = None
    message: str | None = None
    explanation: str | None = None


def read_startup_report(body: bytes) -> StartupReport | None:
    """Pull the startup block out of a health response body."""
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    startup = payload.get("startup")
    if not isinstance(startup, dict):
        return None

    percent = startup.get("percent")
    message = startup.get("message")
    explanation = startup.get("explanation")
    return StartupReport(
        percent=percent if isinstance(percent, int) else None,
        message=message if isinstance(message, str) else None,
        explanation=explanation if isinstance(explanation, str) else None,
    )


def read_body_report(response: object) -> StartupReport | None:
    """Read the startup block off a response object, or give up quietly.

    Readiness is the signal that matters on the probe this serves; progress
    is a nicety on top of it. So every way reading the body can fail ends
    here, rather than being allowed to make a healthy backend look
    unreachable.
    """
    try:
        return read_startup_report(response.read())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None


__all__ = ["StartupReport", "read_body_report", "read_startup_report"]
