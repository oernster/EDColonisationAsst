"""Shared scaffolding for the test_api_carriers modules.

Split out of test_api_carriers.py when that file passed the module cap. Not named
test_* on purpose: pytest collects only the modules that use it.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Callable
import httpx
import pytest
from fastapi import FastAPI
import src.api.carriers as carriers_api
from src.api.carriers import router as carriers_router


def _write_journal_file(journal_dir: Path, events: list[dict]) -> Path:
    """Helper to write a Journal.*.log file with the given JSON events."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    file_path = journal_dir / "Journal.2025-12-15T104644.01.log"
    lines = [json.dumps(e) for e in events]
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def _write_market_export(
    journal_dir: Path,
    *,
    market_id: int,
    station_name: str = "X7J-BQG",
    star_system: str = "Test System",
    timestamp: str = "2025-12-15T11:25:25Z",
    items: list[dict] | None = None,
) -> Path:
    """Helper to write a Market.json export in the journal directory."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    path = journal_dir / "Market.json"
    payload = {
        "timestamp": timestamp,
        "event": "Market",
        "StationName": station_name,
        "StationType": "FleetCarrier",
        "StarSystem": star_system,
        "MarketID": market_id,
        "Items": items or [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
