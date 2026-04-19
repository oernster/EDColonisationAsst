"""AJAX long-poll endpoint for UI live updates."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..services.change_bus import change_bus


router = APIRouter(prefix="/api/changes", tags=["changes"])


@router.get("/longpoll", response_model=dict)
async def longpoll(
    since: int = Query(0, ge=0, description="Last seen change sequence"),
    timeout_s: float = Query(
        25.0,
        gt=0,
        le=120.0,
        description="Max seconds to block before returning",
    ),
) -> dict:
    snapshot = await change_bus.wait_for_change(since=since, timeout_s=timeout_s)
    return {"seq": snapshot.seq, "changed": snapshot.changed}

