import asyncio
from datetime import datetime, timezone

import pytest

from telemetry_gateway.models import (
    BootRegistrationResult,
    DeviceState,
    IngestResult,
    TelemetryInput,
)
from telemetry_gateway.realtime import RealtimeHub, MAX_QUEUE_SIZE
from telemetry_gateway.service import TelemetryService


class FakeRepository:
    def __init__(self, state: DeviceState) -> None:
        self.state = state
        self.ingest_calls = 0

    def register_boot(self, _event):
        return BootRegistrationResult("device-01", "boot-a", 1, True)

    def preview_state(self, _event, _received_at):
        return self.state

    def ingest(self, _event, _received_at):
        self.ingest_calls += 1
        return IngestResult(False, True, self.state)

    def list_current_states(self):
        return []

    def list_events(self, _limit):
        return []

    def ping(self):
        return True


class RecordingPublisher:
    def __init__(self) -> None:
        self.states: list[DeviceState] = []

    async def publish(self, state: DeviceState) -> None:
        self.states.append(state)


def test_service_publishes_a_state_during_ingestion() -> None:
    event = TelemetryInput.model_validate(
        {
            "deviceId": "device-01",
            "bootId": "boot-a",
            "sequence": 1,
            "deviceTime": "2026-08-12T09:00:00Z",
            "metric": "temperature",
            "value": 21.4,
        }
    )
    state = DeviceState(
        device_id="device-01",
        boot_id="boot-a",
        generation=1,
        sequence=1,
        device_time="2026-08-12T09:00:00+00:00",
        received_at="2026-08-12T09:00:01+00:00",
        metric="temperature",
        value=21.4,
    )
    repository = FakeRepository(state)
    publisher = RecordingPublisher()
    service = TelemetryService(
        repository,
        publisher,
        now=lambda: datetime(2026, 8, 12, 9, 0, 1, tzinfo=timezone.utc),
    )

    result = asyncio.run(service.ingest(event))

    assert result.current_changed is True
    assert publisher.states == [state]
    assert repository.ingest_calls == 1

class FakeWebSocket:
    def __init__(self, slow: bool = False) -> None:
        self.slow = slow
        self.received: list[dict] = []
        self.closed = False
        self.close_code: int | None = None

    async def accept(self) -> None:
        pass

    async def send_json(self, message: dict) -> None:
        if self.slow:
            await asyncio.sleep(999)  # simulate a client that never actually reads
        self.received.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.close_code = code


def make_state() -> DeviceState:
    return DeviceState(
        device_id="device-01",
        boot_id="boot-a",
        generation=1,
        sequence=1,
        device_time="2026-08-12T09:00:00+00:00",
        received_at="2026-08-12T09:00:01+00:00",
        metric="temperature",
        value=21.4,
    )


@pytest.mark.anyio
async def test_slow_client_does_not_block_healthy_clients() -> None:
    hub = RealtimeHub()
    fast_ws = FakeWebSocket(slow=False)
    slow_ws = FakeWebSocket(slow=True)

    await hub.connect(fast_ws)
    await hub.connect(slow_ws)

    # publish more messages than the slow client's queue can hold
    for _ in range(MAX_QUEUE_SIZE + 5):
        await hub.publish(make_state())
        await asyncio.sleep(0)

    # give the fast client's sender loop a chance to actually drain its queue
    await asyncio.sleep(0.1)

    assert len(fast_ws.received) == MAX_QUEUE_SIZE + 5  # fast client got everything
    assert slow_ws.closed is True                          # slow client got dropped
    assert slow_ws.close_code == 1008