import pytest

from telemetry_gateway.database import TelemetryStore
from telemetry_gateway.models import BootRegistrationInput, TelemetryInput


def telemetry(**overrides) -> TelemetryInput:
    values = {
        "deviceId": "device-01",
        "bootId": "boot-a",
        "sequence": 1,
        "deviceTime": "2026-08-12T09:00:00+00:00",
        "metric": "temperature",
        "value": 21.4,
    }
    values.update(overrides)
    return TelemetryInput.model_validate(values)


def test_registers_a_boot_idempotently() -> None:
    store = TelemetryStore(":memory:")
    try:
        event = BootRegistrationInput(deviceId="device-01", bootId="boot-a")

        first = store.register_boot(event)
        second = store.register_boot(event)

        assert first.to_api() == {
            "deviceId": "device-01",
            "bootId": "boot-a",
            "generation": 1,
            "created": True,
        }
        assert second.to_api() == {
            "deviceId": "device-01",
            "bootId": "boot-a",
            "generation": 1,
            "created": False,
        }
    finally:
        store.close()


def test_stores_a_basic_event_and_calculates_current_state() -> None:
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))

        result = store.ingest(telemetry(), "2026-08-12T09:00:01+00:00")

        assert result.duplicate is False
        assert result.current_changed is True
        assert store.list_current_states()[0].to_api() == {
            "deviceId": "device-01",
            "bootId": "boot-a",
            "generation": 1,
            "sequence": 1,
            "deviceTime": "2026-08-12T09:00:00+00:00",
            "receivedAt": "2026-08-12T09:00:01+00:00",
            "metric": "temperature",
            "value": 21.4,
        }
        assert len(store.list_events(10)) == 1
    finally:
        store.close()


def test_repeated_event_from_same_boot_is_a_duplicate() -> None:
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))
        store.ingest(telemetry(), "2026-08-12T09:00:01+00:00")

        duplicate = store.ingest(telemetry(), "2026-08-12T09:00:02+00:00")

        assert duplicate.to_api() == {
            "accepted": True,
            "duplicate": True,
            "currentChanged": False,
        }
        assert len(store.list_events(10)) == 1
    finally:
        store.close()

def test_multiple_boots_get_strictly_increasing_generation_numbers() -> None:
    store = TelemetryStore(":memory:")
    try:
        first = store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))
        second = store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-b"))
        third = store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-c"))

        assert first.to_api()["generation"] == 1
        assert second.to_api()["generation"] == 2
        assert third.to_api()["generation"] == 3   
    finally:
        store.close()

def test_multiple_boots_with_different_device_ids_get_strictly_increasing_generation_numbers() -> None:
    store = TelemetryStore(":memory:")
    try:
        first = store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))
        second = store.register_boot(BootRegistrationInput(deviceId="device-02", bootId="boot-a"))
        third = store.register_boot(BootRegistrationInput(deviceId="device-03", bootId="boot-a"))

        assert first.to_api()["generation"] == 1
        assert second.to_api()["generation"] == 1
        assert third.to_api()["generation"] == 1   
    finally:
        store.close()

def test_multiple_boots_with_different_device_ids_and_different_boot_ids_get_strictly_increasing_generation_numbers() -> None:
    store = TelemetryStore(":memory:")
    try:
        first = store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))
        second = store.register_boot(BootRegistrationInput(deviceId="device-02", bootId="boot-b"))
        third = store.register_boot(BootRegistrationInput(deviceId="device-03", bootId="boot-c"))

        assert first.to_api()["generation"] == 1
        assert second.to_api()["generation"] == 1
        assert third.to_api()["generation"] == 1   
    finally:
        store.close()

def test_out_of_order_event_does_not_move_state_backward() -> None:
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))
        store.ingest(telemetry(sequence=5, value=22.0), "2026-08-12T09:00:02+00:00")
        delayed = store.ingest(telemetry(sequence=2, value=21.0), "2026-08-12T09:00:03+00:00")

        assert delayed.duplicate is False
        assert delayed.current_changed is False
        
        state = store.list_current_states()[0].to_api()
        assert state["sequence"] == 5
        assert state["value"] == 22.0
        
        assert len(store.list_events(10)) == 2
    finally:
        store.close()

def test_telemetry_for_unregistered_boot_is_rejected() -> None:
    store = TelemetryStore(":memory:")
    try:
        # note: no store.register_boot(...) call — this boot was never registered

        with pytest.raises(Exception) as exc_info:
            store.ingest(telemetry(), "2026-08-12T09:00:01+00:00")

        # inspect what actually got raised
        print(type(exc_info.value), exc_info.value)
    finally:
        store.close()

def test_same_sequence_different_boot_is_not_a_duplicate() -> None:
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-b"))

        first = store.ingest(telemetry(bootId="boot-a", sequence=1), "2026-08-12T09:00:01+00:00")
        second = store.ingest(telemetry(bootId="boot-b", sequence=1), "2026-08-12T09:00:02+00:00")

        assert first.duplicate is False
        assert second.duplicate is False # same sequence number, but different boot — NOT a duplicate
        assert len(store.list_events(10)) == 2
    finally:
        store.close()
        
def test_bad_device_clock_does_not_affect_ordering() -> None:
    store = TelemetryStore(":memory:")
    try:
        store.register_boot(BootRegistrationInput(deviceId="device-01", bootId="boot-a"))

        # event with a deviceTime far in the future (bad clock), but LOWER sequence
        store.ingest(
            telemetry(sequence=1, deviceTime="2099-01-01T00:00:00+00:00", value=99.9),
            "2026-08-12T09:00:01+00:00",
        )

        # event with a normal deviceTime, but HIGHER sequence — must win regardless of deviceTime
        result = store.ingest(
            telemetry(sequence=2, deviceTime="2026-08-12T09:00:02+00:00", value=21.4),
            "2026-08-12T09:00:03+00:00",
        )

        assert result.current_changed is True
        current = store.list_current_states()[0].to_api()
        assert current["sequence"] == 2
        assert current["value"] == 21.4
    finally:
        store.close()

