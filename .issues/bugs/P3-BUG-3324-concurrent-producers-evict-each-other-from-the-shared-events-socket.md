---
id: BUG-3324
type: BUG
title: Concurrent producers evict each other from the shared events socket
priority: P3
status: open
discovered_by: manual-review
discovered_date: '2026-08-26'
captured_at: '2026-08-26T00:00:00Z'
relates_to:
- FEAT-3323
labels:
- transport
- events
---

# BUG-3324: Concurrent producers evict each other from the shared events socket

## Summary

Every little-loops process that wires the `socket` transport binds the same
`AF_UNIX` path, and `UnixSocketTransport.__init__` unconditionally unlinks any
file already there before binding. A second concurrent run therefore silently
steals the socket from the first. The first producer's already-connected
consumers stay attached to an unlinked inode and keep receiving only the dead
producer's events; any new consumer sees only the second producer. No error is
raised on either side.

This is an independent correctness defect in a shipped transport, split out of
FEAT-3323 (which needs the fix but is otherwise a separate greenfield feature).
It degrades today's documented `nc -U .ll/events.sock` consumer story with no
browser or HTTP involved.

## Location

- **File**: `scripts/little_loops/transport.py`
- **Line(s)**: 157 (in `UnixSocketTransport.__init__`)
- **Anchor**: `in UnixSocketTransport.__init__`, immediately before `bind()`
- **Code**:
```python
self._path.parent.mkdir(parents=True, exist_ok=True)
self._path.unlink(missing_ok=True)   # <-- unconditional; evicts a live producer

self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    self._server.bind(str(self._path))
```

The unlink is correct for a *stale* file left by a crashed producer, which is
what it was written for (`test_init_unlinks_stale_socket_file`,
`test_transport.py:411`). It is wrong for a file a *live* producer is currently
listening on, and the code cannot presently tell the two apart.

## Current Behavior

All four `wire_transports` call sites — `cli/loop/run.py:593`,
`cli/loop/lifecycle.py:737`, `cli/parallel.py:322`, `cli/sprint/run.py:801` —
resolve `events.socket.path` through `_resolve_socket_path`
(`transport.py:678`) to one path per project (default `.ll/events.sock`).

With producer A running and a consumer attached:

1. Producer B starts, unlinks `.ll/events.sock`, binds its own socket at the
   same path.
2. A's listening socket still exists as an unlinked inode. A's accept loop keeps
   running; A's already-connected clients keep receiving A's events only.
3. Any *new* consumer connecting to `.ll/events.sock` reaches B, and will never
   see A's events.
4. When A finishes, `close()` (`transport.py:320`) unlinks the path — which now
   belongs to **B**. B keeps emitting into an unlinked inode, and further
   consumers get `ENOENT` even though B is alive and configured.

Step 4 is the nastier half: a *short* concurrent run tears down the socket file
of a *long* one, so the failure outlives the overlap.

## Steps to Reproduce

```bash
# In a project with events.transports: ["socket"]

# Terminal 1 — consumer
nc -U .ll/events.sock | jq -c .

# Terminal 2 — producer A (long)
ll-sprint run <sprint>

# Terminal 3 — producer B (short), started while A is mid-run
ll-loop run <loop>
```

Observed: the consumer in terminal 1 shows only A's events for the whole
session, never B's. A second consumer started after B shows only B's. When B
exits, `.ll/events.sock` is gone; a third consumer gets
`nc: unix connect failed: No such file or directory` while A is still running
and still configured to stream.

Expected: every consumer sees events from both producers, and a producer exiting
does not remove another producer's endpoint.

## Expected Behavior

- Starting a second producer does not disturb a running producer or disconnect
  its attached consumers.
- A producer's `close()` only ever unlinks a path it actually owns.
- A genuinely stale socket file (crashed producer) is still reclaimed
  automatically — no manual `rm` step, no change to today's recovery behavior.
- With a single producer, everything is byte-identical to today, including the
  path a `nc -U .ll/events.sock` consumer connects to.

## Root Cause

`Path.unlink(missing_ok=True)` cannot distinguish "stale file from a crashed
producer" from "file a live producer is listening on". The constructor assumes
the former unconditionally. There is no liveness probe and no ownership
tracking, so `close()` likewise assumes the file it unlinks is its own.

## Proposed Solution

**Probe before unlinking, and bind a suffixed path when the configured one is
live.**

Replace the unconditional unlink with a connect probe. The four outcomes are
distinguishable by errno, and each maps to exactly one action:

| Path state | `connect()` result | Action |
|---|---|---|
| Missing | `FileNotFoundError` / `ENOENT` | bind configured path |
| Regular file (not a socket) | `OSError` / `ENOTSOCK` | unlink, bind configured path |
| Socket file, owner dead | `ConnectionRefusedError` / `ECONNREFUSED` | unlink, bind configured path |
| Socket file, owner alive | connect succeeds | bind `events-<pid>.sock` alongside |

Verified empirically on Darwin 25.5.0 (Python 3.11): a regular file at the path
yields `ENOTSOCK`, a bound-but-closed socket yields `ECONNREFUSED`, and a live
listener accepts. Use the `errno` symbols, never the numeric literals —
`ENOTSOCK` is 38 on Darwin and 88 on Linux.

Notes on the shape:

- **Suffix with pid, not uuid4.** `AF_UNIX` paths have an OS length ceiling
  (~104 bytes on macOS) — the reason `test_transport.py` uses a `short_tmp_path`
  fixture (`:52`) instead of `tmp_path`. A 36-character uuid in the filename
  would push realistic paths past that ceiling and make the existing fixture
  insufficient. A pid is short, is a natural stable per-process identifier, and
  makes an orphaned file diagnosable (`ps <pid>`).
- **Record ownership.** Store the path actually bound and have `close()` unlink
  only that, fixing the step-4 cross-unlink.
- **Probe with a short timeout** and treat any unexpected `OSError` as
  "occupied" (bind suffixed) rather than "stale" (unlink) — erring toward never
  evicting a live producer.
- **Single-producer behavior is unchanged**, which is why this is preferable to
  unconditional per-producer paths: no migration for `nc -U`, and the existing
  path-shape assertions keep passing untouched.

There is an inherent TOCTOU window between probe and bind. It is not worth a
lock file: the loser of a genuine race lands on its own pid-suffixed path, which
is the safe outcome. Worth a comment at the probe site so a future reader does
not "fix" it.

## Program Design

### Signatures

- `_probe_socket_path(path: Path, timeout: float = 0.2) -> bool` — module-level
  helper; returns `True` if a live listener owns `path`. Unlinks the file and
  returns `False` for the `ENOENT` / `ENOTSOCK` / `ECONNREFUSED` cases.
- `_claim_socket_path(configured: Path) -> Path` — returns `configured` when
  free/stale, else `configured.with_name(f"{configured.stem}-{os.getpid()}{configured.suffix}")`.

### Call Path

`wire_transports` (`transport.py:611`) -> `_resolve_socket_path` (`:678`) ->
`UnixSocketTransport.__init__` (`:134`) -> `_claim_socket_path` ->
`_probe_socket_path` -> `bind()`

### New state

- `UnixSocketTransport._path` becomes the *bound* path rather than the
  *configured* path; `close()` (`:320`) unlinks `self._path` as it does today,
  which is then automatically correct.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — `UnixSocketTransport.__init__`
  (`:134-175`, the unlink at `:157`), `close()` (`:320`); add the two helpers

### Dependent Files (Callers/Importers)
- The four `wire_transports` call sites need no change if the claim happens
  inside the constructor: `cli/loop/run.py:593`, `cli/loop/lifecycle.py:737`,
  `cli/parallel.py:322`, `cli/sprint/run.py:801`
- `scripts/little_loops/__init__.py:63,117` — `wire_transports` is a public
  export; its signature is unchanged

### Tests
- `scripts/tests/test_transport.py::test_init_unlinks_stale_socket_file`
  (`:411-419`) — writes a *regular file* at the path, which the probe classifies
  as `ENOTSOCK` → unlink + bind. Must keep passing unmodified; it is the
  regression guard for the stale-file path.
- `::test_close_unlinks_socket_file` (`:421-426`) — single producer owns the
  configured path, so it keeps passing unmodified.
- `::test_socket_registered_by_name` (`:323-335`),
  `::test_socket_uses_socket_path_from_config` (`:338-351`),
  `::test_socket_and_jsonl_both_registered` (`:354-368`) — assert the literal
  resolved path exists. Keep passing unmodified, because a lone producer still
  binds the configured path. This is the main reason to prefer probe-and-claim
  over unconditional per-producer paths.
- New test: bound-but-dead socket file is reclaimed — bind, `close()` the raw
  socket without unlinking, assert a new transport takes the configured path.
- New test: two live transports on one configured path — assert the second binds
  a distinct, pid-suffixed path, that the first's path still exists, and that a
  consumer attached to the first keeps receiving its events. Model on
  `test_multi_client_each_receives_every_event` (`:458-479`) and
  `test_client_disconnect_does_not_affect_other_clients` (`:481-504`).
- New test: the step-4 cross-unlink — A binds configured, B binds suffixed,
  `B.close()`, assert A's path still exists and A still delivers.
- All new tests use the `short_tmp_path` fixture (`:52`), not `tmp_path`.

### Documentation
- `docs/reference/CONFIGURATION.md:1559-1589` — the `events.socket` block and
  the `nc -U` subscription note; document that a concurrent second producer
  binds a pid-suffixed sibling path, and that a consumer wanting *all* producers
  must read the directory (which is what FEAT-3323's bridge does)
- `docs/ARCHITECTURE.md:613-615` — transport fan-out and socket seeding
- `docs/reference/API.md` — `UnixSocketTransport`

### Configuration
- No new keys. `events.socket.path` (default `.ll/events.sock`) and
  `events.socket.max_clients` (default `32`) keep their current meaning; `path`
  becomes "the preferred path" rather than "the path".

## Implementation Steps

1. Add `_probe_socket_path` and `_claim_socket_path` with the errno table above,
   using `errno` symbols rather than numeric literals.
2. Replace the unconditional unlink at `transport.py:157` with the claim; store
   the bound path on `self._path` so `close()` becomes correct by construction.
3. Log at INFO when a suffixed path is claimed, naming both paths — this is the
   only signal a user gets that two producers are live.
4. Add the four new tests; confirm the five existing path-shape tests pass
   unmodified.
5. Update `CONFIGURATION.md`, `ARCHITECTURE.md`, and `API.md`.

## Impact

- **Priority**: P3 — a real correctness defect, but it only bites projects that
  have opted into `events.transports: ["socket"]`, which is `[]` by default,
  and only when two runs overlap.
- **Effort**: Small — one constructor, two helpers, four tests.
- **Risk**: Low-Medium — touches a live path inside every FSM loop, but the
  single-producer case is unchanged by construction and is pinned by five
  existing tests. `EventBus.emit` isolates transport exceptions
  (`events.py:134-138`), so a defect degrades the stream rather than failing a
  run.
- **Breaking Change**: No. Single-producer path shape, permissions, and cleanup
  are unchanged; the suffixed path only appears in a case that is broken today.

## Related Key Documentation

- `docs/reference/CONFIGURATION.md` — `events.transports`, `events.socket`
- `docs/reference/EVENT-SCHEMA.md` — wire format and event catalog
- `docs/ARCHITECTURE.md` — transport fan-out and socket seeding
- `docs/reference/API.md` — `UnixSocketTransport`, `wire_transports`

## Acceptance Criteria

- [ ] Starting a second producer while a first is running leaves the first's
      socket path intact and does not disconnect its attached consumers —
      asserted by a test.
- [ ] A producer exiting unlinks only the path it bound; a test covers the
      short-run-exits-while-long-run-continues case.
- [ ] A stale socket file (both the regular-file and the bound-but-dead-owner
      cases) is still reclaimed automatically, with no manual cleanup.
- [ ] With a single producer, the bound path is exactly the configured path;
      `test_socket_registered_by_name`, `test_socket_uses_socket_path_from_config`,
      `test_socket_and_jsonl_both_registered`, `test_init_unlinks_stale_socket_file`,
      and `test_close_unlinks_socket_file` pass unmodified.
- [ ] Claiming a suffixed path is logged at INFO naming both paths.
- [ ] The multi-producer path shape is documented in
      `docs/reference/CONFIGURATION.md` alongside the `nc -U` note.

## Status

**Open** | Created: 2026-08-26 | Priority: P3
