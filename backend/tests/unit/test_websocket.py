"""Tests for WebSocket connection manager and notification helpers (no mocking frameworks)."""

from __future__ import annotations

from datetime import datetime, UTC
import json

import pytest

from src.api import websocket as ws_api
from src.models.api_models import WebSocketMessageType


class StubWebSocket:
    """Minimal in-memory stand-in for FastAPI's WebSocket."""

    def __init__(self) -> None:
        self.accepted = False
        self.sent_messages: list[dict] = []

    async def accept(self) -> None:  # type: ignore[override]
        self.accepted = True

    async def send_json(self, message: dict) -> None:  # type: ignore[override]
        self.sent_messages.append(message)


class FailingWebSocket(StubWebSocket):
    """WebSocket that raises on send_json to exercise error paths."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_on_send = True

    async def send_json(self, message: dict) -> None:  # type: ignore[override]
        if self.fail_on_send:
            raise RuntimeError("send failed")
        await super().send_json(message)


class EndpointStubWebSocket:
    """Stub WebSocket used to drive websocket_endpoint without a real network."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self.accepted = False
        self.sent_messages: list[dict] = []

    async def accept(self) -> None:  # type: ignore[override]
        self.accepted = True

    async def receive_text(self) -> str:  # type: ignore[override]
        if self._messages:
            return self._messages.pop(0)
        # Simulate client disconnect to exit the websocket loop
        raise ws_api.WebSocketDisconnect()

    async def send_json(self, message: dict) -> None:  # type: ignore[override]
        self.sent_messages.append(message)


class EndpointManagerStub:
    """Records calls made by websocket_endpoint."""

    def __init__(self) -> None:
        self.connected: list[object] = []
        self.disconnected: list[object] = []
        self.subscribed: list[tuple[object, str]] = []
        self.unsubscribed: list[tuple[object, str]] = []
        self.personal_messages: list[dict] = []

    async def connect(self, websocket):  # type: ignore[override]
        """Mimic ConnectionManager.connect by accepting the WebSocket."""
        self.connected.append(websocket)
        # In the real ConnectionManager, connect() calls websocket.accept().
        # The endpoint under test expects this side-effect.
        if hasattr(websocket, "accept"):
            await websocket.accept()  # type: ignore[func-returns-value]

    async def disconnect(self, websocket):  # type: ignore[override]
        self.disconnected.append(websocket)

    async def subscribe(self, websocket, system_name: str) -> None:  # type: ignore[override]
        self.subscribed.append((websocket, system_name))

    async def unsubscribe(self, websocket, system_name: str) -> None:  # type: ignore[override]
        self.unsubscribed.append((websocket, system_name))

    async def send_personal_message(self, websocket, message: dict) -> None:  # type: ignore[override]
        self.personal_messages.append(message)
        await websocket.send_json(message)

    async def broadcast_to_system(self, system_name: str, message: dict) -> None:  # type: ignore[override]
        # For endpoint-focused tests we don't need broadcast behaviour here
        pass


@pytest.mark.asyncio
async def test_connection_manager_connect_and_disconnect():
    """ConnectionManager should track connections on connect/disconnect."""
    manager = ws_api.ConnectionManager()
    ws = StubWebSocket()

    await manager.connect(ws)
    assert ws.accepted is True
    assert ws in manager.active_connections
    assert manager.active_connections[ws] == set()

    await manager.disconnect(ws)
    assert ws not in manager.active_connections
    # All subscriptions for this socket should be removed
    for subscribers in manager.system_subscriptions.values():
        assert ws not in subscribers


@pytest.mark.asyncio
async def test_connection_manager_subscribe_and_unsubscribe():
    """Subscribing and unsubscribing should update internal mappings."""
    manager = ws_api.ConnectionManager()
    ws = StubWebSocket()

    await manager.connect(ws)
    await manager.subscribe(ws, "Test System")

    assert manager.active_connections[ws] == {"Test System"}
    assert "Test System" in manager.system_subscriptions
    assert ws in manager.system_subscriptions["Test System"]

    await manager.unsubscribe(ws, "Test System")
    assert manager.active_connections[ws] == set()
    assert (
        "Test System" not in manager.system_subscriptions
        or ws not in manager.system_subscriptions.get("Test System", set())
    )


@pytest.mark.asyncio
async def test_broadcast_to_system_sends_messages_and_cleans_disconnected():
    """broadcast_to_system should deliver messages and drop failing websockets."""
    manager = ws_api.ConnectionManager()
    ok_ws = StubWebSocket()
    failing_ws = FailingWebSocket()

    await manager.connect(ok_ws)
    await manager.connect(failing_ws)

    await manager.subscribe(ok_ws, "Alpha")
    await manager.subscribe(failing_ws, "Alpha")

    payload = {"msg": "hello"}
    await manager.broadcast_to_system("Alpha", payload)

    # OK websocket should have received the message
    assert payload in ok_ws.sent_messages

    # Failing websocket should have been disconnected
    assert failing_ws not in manager.active_connections
    for subscribers in manager.system_subscriptions.values():
        assert failing_ws not in subscribers


@pytest.mark.asyncio
async def test_broadcast_to_system_with_no_subscribers_returns_quickly():
    """broadcast_to_system should be a no-op when there are no subscribers."""
    manager = ws_api.ConnectionManager()
    # No subscriptions have been registered for this system; call should not crash.
    await manager.broadcast_to_system("Nowhere System", {"msg": "noop"})


@pytest.mark.asyncio
async def test_send_personal_message_handles_send_error():
    """send_personal_message should disconnect websocket when send_json fails."""
    manager = ws_api.ConnectionManager()
    ws = FailingWebSocket()
    await manager.connect(ws)

    await manager.send_personal_message(ws, {"ping": True})

    # WebSocket should have been disconnected due to send error
    assert ws not in manager.active_connections


class _DummySystemData:
    """Simple stand-in for SystemColonisationData used by notify_system_update."""

    def __init__(self, system_name: str) -> None:
        self.system_name = system_name
        self.construction_sites = []
        self.total_sites = 0
        self.completed_sites = 0
        self.in_progress_sites = 0
        self.completion_percentage = 0.0


class _DummyAggregator:
    def __init__(self, system_name: str = "Alpha System") -> None:
        self._system_name = system_name
        self.calls: list[str] = []

    async def aggregate_by_system(self, name: str) -> _DummySystemData:
        self.calls.append(name)
        return _DummySystemData(system_name=name)


class _RecordingManager:
    """Records broadcast_to_system calls for inspection in tests."""

    def __init__(self) -> None:
        self.broadcast_calls: list[tuple[str, dict]] = []

    async def broadcast_to_system(self, system_name: str, message: dict) -> None:
        self.broadcast_calls.append((system_name, message))


@pytest.mark.asyncio
async def test_notify_system_update_uses_aggregator_and_broadcasts():
    """notify_system_update should aggregate system data and broadcast an UPDATE message."""

    dummy_agg = _DummyAggregator()
    recording_manager = _RecordingManager()

    orig_agg = ws_api._aggregator
    orig_manager = ws_api.manager
    try:
        ws_api._aggregator = dummy_agg  # type: ignore[assignment]
        ws_api.manager = recording_manager  # type: ignore[assignment]

        await ws_api.notify_system_update("Alpha System")
    finally:
        ws_api._aggregator = orig_agg  # type: ignore[assignment]
        ws_api.manager = orig_manager  # type: ignore[assignment]

    # Aggregator should have been called once with the requested system
    assert dummy_agg.calls == ["Alpha System"]

    # Manager should have broadcasted a single UPDATE message for that system
    assert len(recording_manager.broadcast_calls) == 1
    system_name, message = recording_manager.broadcast_calls[0]
    assert system_name == "Alpha System"
    assert message["type"] == WebSocketMessageType.UPDATE
    assert message["system_name"] == "Alpha System"
    assert message["timestamp"]  # non-empty ISO timestamp string


@pytest.mark.asyncio
async def test_notify_system_update_no_aggregator_is_noop():
    """When no aggregator is configured, notify_system_update should return immediately."""
    orig_agg = ws_api._aggregator
    try:
        ws_api._aggregator = None  # type: ignore[assignment]
        # Should not raise and should not attempt to broadcast
        await ws_api.notify_system_update("Alpha System")
    finally:
        ws_api._aggregator = orig_agg  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_notify_global_refresh_broadcasts_to_all_connections():
    """notify_global_refresh should send a REFRESH message to all connected websockets."""
    # Use the real ConnectionManager but stub websockets.
    manager = ws_api.ConnectionManager()
    ws1 = StubWebSocket()
    ws2 = StubWebSocket()

    await manager.connect(ws1)
    await manager.connect(ws2)

    orig_manager = ws_api.manager
    try:
        ws_api.manager = manager  # type: ignore[assignment]
        await ws_api.notify_global_refresh()
    finally:
        ws_api.manager = orig_manager  # type: ignore[assignment]

    assert any(m.get("type") == WebSocketMessageType.REFRESH for m in ws1.sent_messages)
    assert any(m.get("type") == WebSocketMessageType.REFRESH for m in ws2.sent_messages)


class _BoomAggregator:
    async def aggregate_by_system(self, system_name: str) -> _DummySystemData:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_notify_system_update_handles_aggregator_exception():
    """Errors from the aggregator should be caught and not crash the notifier."""
    boom_agg = _BoomAggregator()
    recording_manager = _RecordingManager()

    orig_agg = ws_api._aggregator
    orig_manager = ws_api.manager
    try:
        ws_api._aggregator = boom_agg  # type: ignore[assignment]
        ws_api.manager = recording_manager  # type: ignore[assignment]
        # Should not raise even though the aggregator fails
        await ws_api.notify_system_update("Alpha System")
    finally:
        ws_api._aggregator = orig_agg  # type: ignore[assignment]
        ws_api.manager = orig_manager  # type: ignore[assignment]

    # Since aggregation failed, no broadcast should have been attempted
    assert recording_manager.broadcast_calls == []


def test_set_aggregator_sets_global():
    """set_aggregator should wire the global _aggregator reference."""
    orig_agg = ws_api._aggregator
    try:
        sentinel = object()
        ws_api.set_aggregator(sentinel)  # type: ignore[arg-type]
        assert ws_api._aggregator is sentinel
    finally:
        ws_api._aggregator = orig_agg  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_websocket_endpoint_subscribe_ping_unsubscribe():
    """websocket_endpoint should handle subscribe, ping, and unsubscribe messages."""
    subscribe_msg = json.dumps({"type": "subscribe", "system_name": "Alpha"})
    ping_msg = json.dumps({"type": "ping"})
    unsubscribe_msg = json.dumps({"type": "unsubscribe", "system_name": "Alpha"})

    ws = EndpointStubWebSocket([subscribe_msg, ping_msg, unsubscribe_msg])
    manager = EndpointManagerStub()
    dummy_agg = _DummyAggregator()

    orig_manager = ws_api.manager
    orig_agg = ws_api._aggregator
    try:
        ws_api.manager = manager  # type: ignore[assignment]
        ws_api._aggregator = dummy_agg  # type: ignore[assignment]

        await ws_api.websocket_endpoint(ws)
    finally:
        ws_api.manager = orig_manager  # type: ignore[assignment]
        ws_api._aggregator = orig_agg  # type: ignore[assignment]

    assert ws.accepted is True
    # We should have subscribed and unsubscribed to "Alpha"
    assert any(name == "Alpha" for _, name in manager.subscribed)
    assert any(name == "Alpha" for _, name in manager.unsubscribed)

    # A PONG should have been sent in response to the ping
    pong_messages = [
        m for m in manager.personal_messages if m["type"] == WebSocketMessageType.PONG
    ]
    assert pong_messages

    # Initial UPDATE after subscribe should have been sent to the websocket
    update_messages = [
        m for m in ws.sent_messages if m["type"] == WebSocketMessageType.UPDATE
    ]
    assert update_messages


@pytest.mark.asyncio
async def test_websocket_endpoint_invalid_json_sends_error():
    """Invalid JSON messages should result in an ERROR WebSocketMessage."""
    ws = EndpointStubWebSocket(["not valid json"])
    manager = EndpointManagerStub()

    orig_manager = ws_api.manager
    orig_agg = ws_api._aggregator
    try:
        ws_api.manager = manager  # type: ignore[assignment]
        ws_api._aggregator = None  # type: ignore[assignment]

        await ws_api.websocket_endpoint(ws)
    finally:
        ws_api.manager = orig_manager  # type: ignore[assignment]
        ws_api._aggregator = orig_agg  # type: ignore[assignment]

    error_messages = [
        m for m in manager.personal_messages if m["type"] == WebSocketMessageType.ERROR
    ]
    assert error_messages
    assert "Invalid JSON" in (error_messages[0].get("error") or "")
