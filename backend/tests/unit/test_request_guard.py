"""Which requests the backend answers; which writes it accepts.

Two defects closed here, both measured against a real server before the fix:

- No Host check. A page that rebinds its own DNS name to 127.0.0.1 is, to the
  browser, same-origin with the backend, so CORS never applies; `GET /api/sites`
  with `Host: attacker.example` returned the commander's data.
- A bodiless cross-origin POST is a CORS "simple request" with no preflight, so
  any site the user visited could make EDCA wipe and rebuild its database
  through `/api/debug/reload-journals`; with the journal folder missing it only
  wiped, because the database was cleared before the folder was checked.

The guard accepts IP literals, `localhost` and this machine's own names as the
Host, which keeps the documented tablet access by LAN address working. A write
that names an Origin must be same-origin or a configured CORS origin; a write
with no Origin is not from a browser page and is not a cross-site request.

These drive the real `src.main.app`, so what is asserted is the wiring as well
as the rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import src.config as config_mod
import src.main as main_mod
from src.api import routes as routes_api
from src.api.request_guard import (
    RequestGuardMiddleware,
    host_is_trusted,
    local_machine_names,
    origin_is_trusted,
)
from src.config import AppConfig, JournalConfig
from src.models.colonisation import ConstructionSite
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.data_aggregator import DataAggregator
from src.services.system_tracker import SystemTracker

_RELOAD = "/api/debug/reload-journals"
_EVIL_ORIGIN = "https://evil.example"
_MARKET_ID = 4242


def _client(host: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_mod.app), base_url=f"http://{host}"
    )


@pytest.fixture
async def one_site(
    repository: ColonisationRepository,
    aggregator: DataAggregator,
    system_tracker: SystemTracker,
) -> ColonisationRepository:
    await repository.clear_all()
    await repository.add_construction_site(
        ConstructionSite(
            market_id=_MARKET_ID,
            station_name="Kept Station",
            station_type="Outpost",
            system_name="Kept System",
            system_address=1,
            construction_progress=0.5,
            construction_complete=False,
            construction_failed=False,
        )
    )
    routes_api.set_dependencies(repository, aggregator, system_tracker)
    return repository


def _configure_journals(monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    monkeypatch.setattr(
        config_mod, "_config", AppConfig(journal=JournalConfig(directory=str(folder)))
    )


async def _total_sites(repository: ColonisationRepository) -> int:
    return (await repository.get_stats())["total_sites"]


# ---------------------------------------------------------------- Host (D-4)


@pytest.mark.asyncio
async def test_a_rebound_host_is_refused(one_site: ColonisationRepository) -> None:
    async with _client("attacker.example:47021") as client:
        response = await client.get("/api/sites")

    assert response.status_code == 400
    assert "Kept Station" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    ["127.0.0.1:47021", "localhost:47021", "[::1]:47021", "192.168.1.238:47021"],
)
async def test_loopback_and_lan_addresses_are_answered(
    one_site: ColonisationRepository, host: str
) -> None:
    async with _client(host) as client:
        response = await client.get("/api/sites")

    assert response.status_code == 200
    assert "Kept Station" in response.text


@pytest.mark.parametrize(
    ("host", "trusted"),
    [
        ("localhost", True),
        ("LOCALHOST.:47021", True),
        ("app.localhost:5173", True),
        ("10.0.0.5", True),
        ("[fe80::1]:80", True),
        ("mypc:47021", True),
        ("MyPC.local", True),
        ("mypc.example.lan", True),
        ("", True),
        ("attacker.example", False),
        ("localhost.attacker.example", False),
        ("[not-an-address]:80", False),
        ("[::1", False),
        ("127.0.0.1.nip.io", False),
    ],
)
def test_host_rule(host: str, trusted: bool) -> None:
    names = frozenset({"mypc", "mypc.local", "mypc.example.lan"})

    assert host_is_trusted(host, names) is trusted


@pytest.mark.asyncio
async def test_a_non_http_scope_passes_straight_through() -> None:
    """Lifespan and websocket scopes carry no Host to judge."""
    seen: list[str] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope["type"])

    guard = RequestGuardMiddleware(inner, allowed_origins=(), machine_names=frozenset())
    await guard({"type": "lifespan"}, None, None)

    assert seen == ["lifespan"]


def test_the_machine_names_include_its_mdns_name() -> None:
    names = local_machine_names(lambda: "MyPC", lambda: "MyPC.corp.example")

    assert names == frozenset({"mypc", "mypc.local", "mypc.corp.example"})


# ---------------------------------------------------------------- Origin (D-3)


@pytest.mark.parametrize(
    ("origin", "trusted"),
    [
        ("http://127.0.0.1:47021", True),
        ("http://localhost:5173", True),
        (_EVIL_ORIGIN, False),
        ("null", False),
        ("http://127.0.0.1:9999", False),
    ],
)
def test_origin_rule(origin: str, trusted: bool) -> None:
    allowed = ("http://localhost:5173",)

    assert origin_is_trusted(origin, "127.0.0.1:47021", allowed) is trusted


@pytest.mark.asyncio
async def test_a_cross_origin_reload_is_refused_and_wipes_nothing(
    one_site: ColonisationRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_journals(monkeypatch, tmp_path)

    async with _client("127.0.0.1:47021") as client:
        response = await client.post(_RELOAD, headers={"Origin": _EVIL_ORIGIN})

    assert response.status_code == 403
    assert await _total_sites(one_site) == 1


@pytest.mark.asyncio
async def test_a_cross_origin_settings_write_is_refused(
    one_site: ColonisationRepository,
) -> None:
    async with _client("127.0.0.1:47021") as client:
        response = await client.post(
            "/api/settings",
            headers={"Origin": _EVIL_ORIGIN},
            json={"journal_directory": "C:/elsewhere"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_same_origin_reload_is_accepted(
    one_site: ColonisationRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = tmp_path / "Journal.2025-01-01T000000.01.log"
    journal.write_text(
        json.dumps({"timestamp": "2025-01-01T00:00:00Z", "event": "Fileheader"}) + "\n",
        encoding="utf-8",
    )
    _configure_journals(monkeypatch, tmp_path)

    async with _client("127.0.0.1:47021") as client:
        response = await client.post(
            _RELOAD, headers={"Origin": "http://127.0.0.1:47021"}
        )

    assert response.status_code == 200


# ------------------------------------------------- reload ordering (D-3)


@pytest.mark.asyncio
async def test_a_reload_with_the_folder_missing_wipes_nothing(
    one_site: ColonisationRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_journals(monkeypatch, tmp_path / "gone")

    async with _client("127.0.0.1:47021") as client:
        response = await client.post(_RELOAD)

    assert response.status_code == 404
    assert await _total_sites(one_site) == 1


@pytest.mark.asyncio
async def test_a_reload_of_a_folder_with_no_journals_wipes_nothing(
    one_site: ColonisationRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_journals(monkeypatch, tmp_path)

    async with _client("127.0.0.1:47021") as client:
        response = await client.post(_RELOAD)

    assert response.status_code == 404
    assert await _total_sites(one_site) == 1
