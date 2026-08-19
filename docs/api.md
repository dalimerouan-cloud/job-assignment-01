# Local API reference

## Register a boot

```http
POST /api/boots
```

Success response:

```json
{
  "deviceId": "device-17",
  "bootId": "boot-a",
  "generation": 2,
  "created": true
}
```
## register one its work perfectly first registration 

A repeated registration returns `created: false` and the original generation.

## Submit telemetry

```http
POST /api/telemetry
```

New event response:
## this true in the first attempte
```json
{
  "accepted": true,
  "duplicate": false,
  "currentChanged": true
}
```

Duplicate event response:

```json
{
  "accepted": true,
  "duplicate": true,
  "currentChanged": false
}
```

Unknown boot response:

```json
{
  "error": "unknown_boot"
}
```

## List current state

```http
GET /api/devices
```

## List raw telemetry

```http
GET /api/events?limit=100
```

This endpoint is provided for local investigation. It returns newest received rows first.

## WebSocket

Connect to:

```text
ws://127.0.0.1:3000/ws
```

Current-state change message:

```json
{
  "type": "device.state.changed",
  "data": {
    "deviceId": "device-17",
    "metric": "temperature",
    "bootId": "boot-a",
    "generation": 2,
    "sequence": 12,
    "deviceTime": "2026-08-12T09:00:00.000Z",
    "receivedAt": "2026-08-12T09:00:01.100Z",
    "value": 21.4
  }
}
```
