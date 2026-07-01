"""Coverage tests for src.api.carriers error handling paths.

These tests exercise the journal loading failure branches of the carriers
router using the real FastAPI wiring plus httpx. No mocking libraries are
used; pytest monkeypatch redirects journal directory resolution to fakes
that raise or return empty results.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import src.api.carriers as carriers_api
from src.api.carriers import router as carriers_router


def _build_app() -> FastAPI:
    """Create a minimal FastAPI app with only the carriers router."""
    app = FastAPI()
    app.include_router(carriers_router)
    return app


@pytest.mark.asyncio
async def test_carriers_endpoints_when_journal_directory_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing journal directory yields empty results plus a 404 state."""

    def _raise_missing() -> Path:
        raise FileNotFoundError("journal directory does not exist")

    monkeypatch.setattr(carriers_api, "get_journal_directory", _raise_missing)

    app = _build_app()
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp_current = await client.get("/api/carriers/current")
        assert resp_current.status_code == 200
        assert resp_current.json()["docked_at_carrier"] is False

        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 404
        assert resp_state.json()["detail"] == "No journal data available"

        resp_mine = await client.get("/api/carriers/mine")
        assert resp_mine.status_code == 200
        assert resp_mine.json() == {"own_carriers": [], "squadron_carriers": []}


@pytest.mark.asyncio
async def test_carriers_endpoints_on_unexpected_journal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected journal resolution errors degrade to empty results."""

    def _raise_unexpected() -> Path:
        raise RuntimeError("boom")

    monkeypatch.setattr(carriers_api, "get_journal_directory", _raise_unexpected)

    app = _build_app()
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp_current = await client.get("/api/carriers/current")
        assert resp_current.status_code == 200
        assert resp_current.json()["docked_at_carrier"] is False

        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 404
        assert resp_state.json()["detail"] == "No journal data available"


@pytest.mark.asyncio
async def test_carriers_endpoints_when_no_journal_files_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing but empty journal directory yields no carrier data."""
    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: tmp_path)
    monkeypatch.setattr(carriers_api, "get_journal_files", lambda _dir: [])

    app = _build_app()
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 404
        assert resp_state.json()["detail"] == "No journal data available"

        resp_mine = await client.get("/api/carriers/mine")
        assert resp_mine.status_code == 200
        assert resp_mine.json() == {"own_carriers": [], "squadron_carriers": []}
