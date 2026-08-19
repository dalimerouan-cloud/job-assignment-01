# Engineering decisions
Complete this file as part of the assignment.

## Invariants identified

- Logical event identity is (deviceId, bootId, sequence), not (deviceId, sequence). Two different boots of the same device can legitimately reuse the same sequence number, since sequence restarts at 1 on every boot — so bootId must be part of the identity, or events from different boots get incorrectly treated as duplicates of each other.

- bootId is opaque and must never be compared, sorted, or used to infer chronological order. It is purely an identity key.

- generation is the real signal for boot recency, not bootId. It is assigned once per (deviceId, bootId), server-side, strictly increasing per device.

- Current-state ordering is (generation, sequence), compared as a tuple: higher generation always wins; if generation is equal, higher sequence wins. deviceTime must never be used to decide ordering — it is diagnostic metadata only, and device clocks can be arbitrarily wrong.

- A realtime publish must only happen after a successful database commit, and only when current state actually changed. Duplicate and stale/out-of-order events must never trigger a publish, even though they may still be legitimately recorded in raw history.

- The dashboard is a passive consumer of a snapshot plus a stream of updates, not the source of truth. It must re-fetch the authoritative snapshot on every successful WebSocket (re)connection, not just once at page load, since a dropped connection can silently miss updates.

- A slow realtime client must never block or slow down delivery to healthy clients, and must have a bounded memory footprint regardless of how unresponsive it becomes.



## Incidents fixed
- Duplicate detection missing boot_id (event identity): the telemetry_events table's uniqueness constraint was UNIQUE (device_id, sequence), missing boot_id. This caused a genuinely new event from a different boot to be incorrectly flagged as a duplicate whenever it reused a sequence number already used by another boot of the same device  which happens on every device restart, since sequence resets to 1. Confirmed with a test (test_same_sequence_different_boot_is_not_a_duplicate) that failed before the fix. Fixed via a new migration (migration_002) that rebuilds the table with UNIQUE (device_id, boot_id, sequence).

- Current-state ordering used deviceTime instead of (generation, sequence): the current_state upsert's WHERE clause compared excluded.device_time > current_state.device_time, directly violating the runtime contract's explicit prohibition on using deviceTime for ordering. A device with an incorrect (e.g. far-future) clock could corrupt current state even with a lower/older sequence and generation. Fixed by changing the comparison to a tuple comparison on (generation, sequence).

- Realtime publish happened before the database transaction, and unconditionally: in the service layer, ingest() called preview_state() and published to the realtime hub before the actual database write ran, and did so regardless of whether the event was a duplicate or stale. This violated the runtime contract's required order (commit first, publish only if state changed) and meant a failed transaction, duplicate, or stale event could all incorrectly trigger a realtime "state changed" message. Fixed by reordering ingest() to call the repository first, then publish only when result.current_changed is true, using the actual committed state.
- Slow WebSocket client could block all other clients / unbounded memory: RealtimeHub.publish() awaited each client's send_json() sequentially in a shared loop, with no per-client buffering or bound. A single slow client would block delivery to every other client. Fixed by giving each client its own bounded asyncio.Queue and a dedicated background sender task; publish() now only enqueues (non-blocking) and disconnects any client whose queue is full.
- Dashboard did not refetch snapshot after WebSocket reconnect: app.js fetched the current-state snapshot once on page load and correctly reconnected the WebSocket on disconnect, but never re-fetched the snapshot after a successful reconnection, meaning any state changes missed during a disconnect window were never recovered. Fixed by calling the snapshot fetch again inside the WebSocket's open event handler.


## Design choices and trade-offs

- Slow-client policy: when a client's queue fills, the connection is closed rather than silently dropping messages and keeping it open. This matches the runtime contract's wording ("close or drop a slow client") and pairs with the reconnect-snapshot fix — a dropped client simply reconnects and gets a fresh, correct snapshot.

- Publish source of truth: after the fix, the service publishes the state returned directly from the repository's committed ingest() result, rather than a separately computed preview state, removing any risk of the published state diverging from what was actually committed.

## Schema or API compatibility concerns

- The /api/boots and /api/telemetry request/response shapes were not changed; all fixes were internal (schema constraint, ordering logic, publish timing, connection handling) and preserve the documented API contract exactly.

- The telemetry_events table was rebuilt via migration rather than dropped and recreated from scratch, preserving existing raw audit history on any database that had already run migration_001.

## Remaining risks or incomplete work

- I did not write a separate tests/test_api.py HTTP-level test suite; the pytest suite covers the same logic at the repository/service layer, and I additionally verified end-to-end behavior manually via curl against the running server (idempotent registration, duplicate detection, unknown-boot rejection, and generation-based ordering across boot restarts) and via the provided simulator.py --chaos tool.

- The service layer calls the repository's synchronous, blocking SQLite methods directly from async def route handlers without offloading to a thread pool. This does not affect correctness but could reduce concurrency under heavier load than this local assignment is expected to see; left unchanged to keep scope focused on the six required behaviors.

- preview_state() on the repository is no longer called anywhere after the current-state-ordering fix. It builds a DeviceState from an event without performing any duplicate or ordering checks and without writing to the database, so it can return a state for an event that would actually be rejected or treated as stale by the real ingest() path — this is part of why it was safe to stop relying on it for publishing. I left the method in place rather than deleting it, since I could not fully rule out other callers depending on it within the time available, but it should not be reused for testing or previewing outcomes, since it does not reflect real validation/ordering behavior.


