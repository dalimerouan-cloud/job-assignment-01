# AI usage record

Complete this file even when no AI tool was used.

## Tools used

- Claude (Anthropic), used conversationally throughout the assignment: to read and interpret `docs/protocol.md` and `docs/runtime-contract.md` before writing any code, to review the existing implementation against those rules, to draft fixes and tests, and to explain Python/SQLite/asyncio behavior I was less familiar with (my production experience is in Go, not Python).

## Important prompts or prompt summaries

- Pasted `docs/protocol.md` and `docs/runtime-contract.md` in full and worked through what each specific rule implies for the implementation before touching any code (e.g. what "bootId is opaque, no ordering meaning" actually rules out; what "publish only after a successful commit and only when current state changed" requires in terms of call order).

- Pasted the actual `register_boot`, `ingest`, and `RealtimeHub.publish` implementations and asked whether they satisfied specific rules from the docs, rather than assuming anything was broken without checking.

- Asked for a test proving "same sequence number, different boot, should not be treated as a duplicate" — this test failing against the real implementation is what surfaced the actual bug (missing `boot_id` in the unique constraint).

- Asked for the correct `asyncio.Queue`-based pattern to isolate slow WebSocket clients without blocking healthy ones, then implemented and adjusted it myself, including adding a `finally` cleanup block not present in the original suggestion.


## Generated output rejected or corrected


- A first draft of the `migration_002` table-rebuild had the `INSERT INTO` statement targeting the wrong table (the old `telemetry_events` instead of the new `telemetry_events_new`). I caught this by reading the SQL myself before running it against my real database.

- I initially considered fixing the missing-`boot_id` constraint bug by editing the already-applied `migration_001` directly, but rejected that approach once I realized my local database already had that migration applied — editing it in place would not fix an existing database file, only new ones. I used a proper `migration_002` instead.

- An early test used a fake repository constructor signature that didn't match how it was actually called (`FakeRepositoryNoChange(state)` vs. a no-argument constructor). I caught the mismatch by running the test and reading the real Python error rather than assuming generated code was correct as written.

## Verification performed

- Every fix is backed by a specific automated test in `tests/test_database.py` or `tests/test_service.py`, written and run by me, targeting the exact behavior described in `docs/protocol.md` / `docs/runtime-contract.md`. I did not accept "it should work" without seeing the test actually pass.

- I ran the provided `simulator.py --chaos` tool against the running server and inspected real server logs to confirm correct behavior under realistic, adversarial conditions: device restarts, duplicate delivery, delayed/out-of-order events, and bad device clocks.

- I did not write a separate `tests/test_api.py` HTTP-level suite; instead I verified the same behavior end-to-end through the real HTTP API using manual curl requests against the running server (boot idempotency, duplicate detection, `409 unknown_boot`, and generation-based ordering across boot restarts).
- I manually tested the WebSocket/dashboard behavior in a real browser, using DevTools' Network tab, to confirm the reconnect-snapshot fix actually triggers a fresh `GET /api/devices` call on reconnection, since this behavior is not covered by the Python test suite.

- After discovering my local `data/telemetry.db` still showed the old, buggy schema despite the code fix, I confirmed the root cause (an already-applied migration doesn't rerun on code changes) and verified the corrected schema directly by querying `sqlite_master` after adding and running `migration_002`.