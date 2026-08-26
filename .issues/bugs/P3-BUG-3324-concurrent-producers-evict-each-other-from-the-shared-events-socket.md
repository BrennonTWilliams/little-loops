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
confidence_score: 100
outcome_confidence: 90
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 20
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
- A producer's `close()` only ever unlinks a file it actually owns — the same
  inode it bound, not merely the same path.
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

Replace the unconditional unlink with a connect probe. Only three outcomes drive
behavior — the probe is deliberately coarse:

| `connect()` result | Classification | Action |
|---|---|---|
| Succeeds | **live** | bind `events-<pid>.sock` alongside |
| `ENOENT` (`FileNotFoundError`) | **absent** | bind configured path |
| `ENOTSOCK` or `ECONNREFUSED` | **reclaimable** | unlink, bind configured path |
| Anything else (`EACCES`, `EPERM`, timeout, `EAGAIN`, …) | **assume live** | bind `events-<pid>.sock` alongside |

Note the table does *not* try to distinguish "regular file" from "socket whose
owner is dead" — both are reclaimable and take the identical action, so the
implementation must not branch on which errno it got beyond the three
classifications above. Verified empirically on Darwin 25.5.0 (Python 3.11): a
regular file yields `ENOTSOCK`, a bound-but-closed socket yields
`ECONNREFUSED`, and a live listener accepts. **Linux's errno for the
regular-file case is deliberately unverified** — it is reported as
`ECONNREFUSED` on some kernels rather than `ENOTSOCK`, and since both map to
the same action there is no need to confirm it. Do not spend a Linux
verification detour here. Use the `errno` symbols, never the numeric literals —
`ENOTSOCK` is 38 on Darwin and 88 on Linux.

The catch-all "assume live" row matters for a real case: the socket is
`chmod 0o600` (`transport.py:161`), so a probe from a *different uid* gets
`EACCES`/`EPERM`, not `ECONNREFUSED`. Classifying that as live is the correct
and safe direction — a second user's producer takes a suffixed path rather than
deleting the first user's endpoint — but it should be an explicit row rather
than an accident of the fallthrough.

Notes on the shape:

- **Suffix with pid, not uuid4.** `AF_UNIX` paths have an OS length ceiling
  (~104 bytes on macOS) — the reason `test_transport.py` uses a `short_tmp_path`
  fixture (`:52`) instead of `tmp_path`. A 36-character uuid in the filename
  would push realistic paths past that ceiling and make the existing fixture
  insufficient. A pid is short, is a natural stable per-process identifier, and
  makes an orphaned file diagnosable (`ps <pid>`).
- **Record ownership by inode, not by path.** Store the path actually bound
  *and* its `(st_dev, st_ino)` identity, and have `close()` unlink only on an
  identity match. Path alone is insufficient — see "`close()` is a third
  cross-unlink site" below.
- **Probe with a short timeout** and treat any unexpected `OSError` as
  "occupied" (bind suffixed) rather than "stale" (unlink) — erring toward never
  evicting a live producer.
- **Claim the suffixed path too.** `events-<pid>.sock` is not guaranteed free:
  a prior producer under a recycled pid may have crashed and left one, and a
  re-exec'd process can meet its own orphan. Run the *same* claim logic on the
  fallback path rather than binding it blind. One level of fallback is enough —
  if the pid-suffixed path is itself claimed by a live listener, that listener
  is this pid, which cannot happen for a distinct live process; treat a live
  result there as a hard error rather than recursing further.
- **Single-producer behavior is unchanged**, which is why this is preferable to
  unconditional per-producer paths: no migration for `nc -U`, and the existing
  path-shape assertions keep passing untouched.

### Why a connect probe rather than this codebase's pid-liveness pattern

The Codebase Research Findings below correctly note that this repo's existing
"is the owner still alive" convention is pid-based (`os.kill(pid, 0)` in
`fsm/concurrency.py:56-68`, psutil-hardened in `cli/queue.py:508-533`), and that
a connect-errno probe would be the first of its kind here. That convention is
**not applicable to this case and should not be adopted**: the *configured*
path (`.ll/events.sock`) encodes no pid, so there is no owner identifier to
`os.kill`. Deriving one would require a sidecar pidfile — new state, its own
staleness problem, and its own races. The connect probe asks the operating
system the question directly and needs no extra state. Do not "align" this with
the pid pattern during implementation; the divergence is intentional.

### The probe perturbs the live producer

A probe that connects and immediately closes is not free on the *other* side.
`wire_transports` passes `_make_seed_callback()` as `on_connect`
(`transport.py:586-599`), and `_accept_loop` (`:203-204`) invokes it inside the
clients lock for every accepted connection. So each probe against a live
producer causes that producer to: accept the connection, append a
`_SocketClient`, run `list_running_loops(Path(".loops"))` — **a filesystem
scan** — enqueue a seed event per running loop, spawn a client thread, and then
tear the whole thing down when the first `sendall` fails against the
already-closed probe socket (`_client_loop`, `:215-224`).

This is self-healing and harmless to correctness, but it means every producer
startup costs every live producer a directory walk plus thread churn, and it
must not leave residue. Two consequences for the implementation:

- Close the probe socket promptly and unconditionally (`try/finally`), so the
  live producer's client list drains immediately rather than at its next send.
- A probe must not leave *residue* in the live producer's client pool — no net
  client-list growth, no slot still held once the probe returns, no events
  missed by its already-attached consumers. This is worth a test, not just a
  comment.

Note the probe still classifies correctly when the live producer is *saturated*
at `max_clients`: `connect()` succeeds at the kernel level regardless of whether
the listener ever accepts, and the rejection path (`:196-201`) closes the
connection after the fact. "Live" is the right answer in that case.

**Two observable effects are accepted, not defects.** "The probe changes
nothing" is too strong a claim to make literally, and the implementation should
not be contorted to satisfy it:

- Probing a *saturated* producer runs `_record_rejection` (`:189`), which
  permanently increments `_rejections_total` — surfaced by `get_stats()`
  (`:281-283`). This counter will tick up for a probe that was never a real
  consumer. Accepted: the alternative is a second, slot-free liveness channel,
  which is far more machinery than the signal is worth.
- A probe momentarily *does* occupy a slot, so a genuine consumer connecting at
  `max_clients - 1` concurrently with a probe can be rejected where it would
  otherwise have been accepted. Accepted for the same reason; the window is one
  accept-and-close.

The requirement is therefore about the *steady state after the probe returns*,
which is what the acceptance criterion and its test assert.

### TOCTOU: the fallback must actually exist

There is an inherent window between probe and bind. It is not worth a lock file
— but the "safe outcome" this relies on has to be *built*, not assumed:

- **`EADDRINUSE` on the configured path must fall back to the suffixed path,
  not propagate.** As originally specified, the loser of the race would simply
  raise out of the constructor. The claim needs an explicit retry: if `bind()`
  on the configured path fails with `EADDRINUSE`, re-enter the claim and take
  the pid-suffixed path. Without this, the stated rationale for skipping a lock
  file is false.
- **The constructor's failure handler is a second cross-unlink site.** Today
  `except: self._server.close(); self._path.unlink(missing_ok=True)`
  (`transport.py:167-170`) fires on *any* exception from bind/chmod/listen. In
  the race above, that unlinks the *winner's* freshly-bound socket — the same
  class of bug as step 4, at a different line. Fix by narrowing the `try` so a
  failed `bind()` never reaches the unlink: only unlink in that handler when
  `bind()` succeeded and a later step (`chmod`/`listen`) failed, since only then
  is the file ours.

Worth a comment at the probe site, in the `session_log.py:176-180` style (cite
BUG-3324, describe the interleaving, state the fallback), so a future reader
does not "fix" the window.

### `close()` is a third cross-unlink site

"Store the bound path and unlink only that" is **not** sufficient on its own,
because a producer can legitimately bind the configured path and still unlink
someone else's socket at it. `close()` (`:285-320`) does:

1. `self._server.close()` (`:299`) — the listener stops accepting.
2. Shut down and join every client thread, budgeted against
   `_CLOSE_TOTAL_TIMEOUT = 10.0` (`:286`, `:312`).
3. `self._path.unlink(missing_ok=True)` (`:320`).

Between steps 1 and 3 there is a window of **up to ten seconds** — not a
microsecond race — during which A's path exists but nothing is listening on it.
A producer B starting inside that window probes, gets `ECONNREFUSED`, correctly
classifies `RECLAIMABLE`, unlinks and binds the configured path. A then reaches
step 3 and unlinks **B's** socket. Ownership-by-bound-path does not catch this:
A really did bind that path, and B's classification really was correct.

Fix by identity rather than by name: `os.stat()` the path immediately after a
successful `bind()`, keep `(st_dev, st_ino)`, and in `close()` re-`stat` and
unlink only when it matches. That closes step 4 and this window with one
mechanism. A residual TOCTOU remains between the `stat` and the `unlink`, but it
is now bounded by two adjacent syscalls rather than by a thread-join budget —
which is what makes skipping a lock file defensible. Treat a `FileNotFoundError`
from the `stat` as "already gone, nothing to do".

### Out of scope: a dangling symlink at the configured path

`connect()` through a dangling symlink yields `ENOENT`, which classifies as
`ABSENT`, after which `bind()` fails rather than reclaiming. That lands in the
generic bind-failure path instead of being cleaned up. This is not handled and
is not worth handling — recorded so it is not mistaken for a regression of the
stale-file case, which is about a *real* file and does classify correctly.

### Non-goal: sweeping orphaned suffixed sockets

A producer that crashes without running `close()` leaves `events-<pid>.sock`
behind forever. Nothing in this fix reclaims those: the claim logic only ever
probes the one path it wants, so a dead sibling is never visited. Files
accumulate in `.ll/` across crashes.

**This is explicitly out of scope for BUG-3324**, recorded here so it is owned
rather than silently unhandled. The consequence transfers to FEAT-3323: a bridge
that enumerates the directory to reach all producers **must tolerate dead
endpoints** — connect failures with `ECONNREFUSED`/`ENOENT` against a sibling
are expected, not exceptional, and are that consumer's cue to skip (and
optionally unlink) the file. If a sweep is wanted later it belongs in a
follow-up; do not grow this fix into one.

## Program Design

### Signatures

- `_probe_socket_path(path: Path, timeout: float = 0.2) -> _PathState` —
  module-level helper. **Pure: performs no filesystem mutation.** Opens a
  probing `AF_UNIX` connection, closes it in a `finally`, and classifies the
  result as one of three states: `LIVE`, `ABSENT`, or `RECLAIMABLE` (a small
  `enum.Enum` or three module constants — not a bool). The catch-all
  unexpected-`OSError` case returns `LIVE`.
- `_claim_socket_path(configured: Path, *, force_suffix: bool = False) -> Path`
  — the only mutating helper. **Never binds.** Calls `_probe_socket_path`,
  unlinks on `RECLAIMABLE`, and returns the path to bind: `configured` for
  `ABSENT`/`RECLAIMABLE`, else
  `configured.with_name(f"{configured.stem}-{os.getpid()}{configured.suffix}")`
  — itself claimed through the same probe/unlink logic before being returned
  (see "Claim the suffixed path too" above). `force_suffix=True` skips the
  configured path entirely and claims the suffixed path directly; this is how
  the constructor re-enters after `EADDRINUSE`.

**The `EADDRINUSE` fallback lives in the constructor, not the helper.** The
constructor runs a bounded **two-attempt** loop, and the helper stays
non-binding:

1. `path = _claim_socket_path(configured)`; create a socket; `bind()`.
2. On `OSError` with `errno.EADDRINUSE` on attempt 1 only:
   `path = _claim_socket_path(configured, force_suffix=True)`; **create a fresh
   `socket.socket`**; `bind()` again.
3. A failure on attempt 2 — or any non-`EADDRINUSE` error on attempt 1 —
   propagates.

Two attempts, never a loop-until-success. The fresh socket on attempt 2 is
deliberate: rebinding a socket object whose previous `bind()` failed is subtly
platform-dependent, and a new object costs nothing. Close the attempt-1 socket
before discarding it.

The split matters: the original spec had `_probe_socket_path` both described as
a predicate ("returns `True` if a live listener owns `path`") *and* unlinking as
a side effect, while `_claim_socket_path` was described as making the
free-vs-stale decision. A mutating function named `_probe_*` will be misused by
the next caller. Keep every unlink inside `_claim_socket_path`.

### Call Path

`wire_transports` (`transport.py:611`) -> `_resolve_socket_path` (`:678`) ->
`UnixSocketTransport.__init__` (`:134`) -> `_claim_socket_path` ->
`_probe_socket_path` -> `bind()` -> (on `EADDRINUSE`)
`_claim_socket_path(force_suffix=True)` -> fresh socket -> `bind()`

### New state

- `UnixSocketTransport._path` becomes the *bound* path rather than the
  *configured* path.
- `UnixSocketTransport._bound_id: tuple[int, int] | None` — `(st_dev, st_ino)`
  captured by `os.stat()` immediately after the successful `bind()`. `close()`
  (`:320`) re-`stat`s `self._path` and unlinks only on a match, treating
  `FileNotFoundError` as "already gone". Path alone is not enough — see
  "`close()` is a third cross-unlink site" above.

### The sibling-path naming contract

The suffixed path is `{stem}-{pid}{suffix}` as a **sibling of the configured
path** — `.ll/events-1234.sock` for the default `.ll/events.sock`. This is a
contract a directory-enumerating consumer may key on, not an implementation
detail: FEAT-3323's bridge (which `depends_on` this issue) has to know which
files in `.ll/` are event sockets, and a loose `events*.sock` glob would also
match unrelated names. State the rule in `CONFIGURATION.md` so FEAT-3323 is not
inferring it by reading this code.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- `close()` (`transport.py:285-320`) sets `self._shutdown`, joins the accept thread
  against a `_CLOSE_TOTAL_TIMEOUT` budget, closes `self._server`, shuts down/joins each
  client, and only then unlinks `self._path` at line 320 — the unlink is the last step,
  confirming no ownership check exists anywhere earlier in the teardown sequence either.
- `EventBus.close_transports` (`events.py:109-115`), which runs immediately before
  `emit`, wraps each `transport.close()` call in the same per-transport
  `try/except Exception: logger.warning(...)` isolation as `emit` (`events.py:134-138`)
  — so a `close()`-time failure from this fix (e.g. an unlink race) would already be
  isolated the same way a `send()`-time failure is, with no propagation to other
  transports or the caller.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — `UnixSocketTransport.__init__`
  (`:134-175`): the unlink at `:157`, **the failure handler at `:167-170`**
  whose `try` must be narrowed so a failed `bind()` cannot reach the unlink, and
  the two-attempt `EADDRINUSE` bind loop; `close()` (`:320`), whose unlink
  becomes inode-identity-checked; add the two helpers plus the `errno` and `os`
  imports (`errno` is not present in this module today)

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
- New test: **the probe leaves the live producer's state unchanged** — attach a
  real consumer to A, construct B (which probes A), then assert A's client list
  is back to exactly the one real consumer and that consumer has missed no
  events. Guards the `on_connect`/seed side effect described above. Poll with a
  bounded wait rather than a bare sleep, since the probe's client is removed
  asynchronously by `_client_loop`'s `finally` (`:217-224`).
- New test: **stale pid-suffixed path is reclaimed** — pre-create a dead/regular
  file at `events-<os.getpid()>.sock`, stand up a live producer on the
  configured path, then construct a second transport and assert it binds (does
  not raise) and the suffixed path is a live socket.
- New test: **`EADDRINUSE` on the configured path falls back rather than
  raising** — simulate the TOCTOU loser by monkeypatching so the first `bind()`
  attempt raises `OSError(errno.EADDRINUSE, ...)`; assert the transport comes up
  on the pid-suffixed path and that the pre-existing file at the configured path
  is untouched.
- New test: **`close()` does not unlink a socket reclaimed during its drain** —
  the regression guard for the ten-second window. Stand up A on the configured
  path with a client attached so its `close()` spends real time in the join
  loop; from another thread, once A's listener is shut, let B reclaim and bind
  the configured path; assert that when `A.close()` returns, B's socket file
  still exists and B still delivers events. Drive the interleaving
  deterministically (e.g. a client whose thread blocks until released) rather
  than with sleeps.
- New test: **`close()` unlinks normally in the uncontended case** — the
  identity check must not regress ordinary cleanup; this is
  `test_close_unlinks_socket_file` (`:421-426`) and it must pass unmodified.
- New test: **a failed `bind()` does not unlink the winner's socket** — the
  regression guard for the `:167-170` handler. Bind a live socket at the
  configured path out-of-band, force the constructor down the bind-failure path,
  and assert the out-of-band socket's file still exists.
- All new tests use the `short_tmp_path` fixture (`:52`), not `tmp_path`.

### Documentation
- `docs/reference/CONFIGURATION.md:1559-1589` — the `events.socket` block and
  the `nc -U` subscription note; document that a concurrent second producer
  binds a pid-suffixed sibling path, and that a consumer wanting *all* producers
  must read the directory (which is what FEAT-3323's bridge does)
- `docs/reference/CONFIGURATION.md` (same block) — state the sibling naming
  contract explicitly — `{stem}-{pid}{suffix}` next to the configured path — as
  the rule a directory-enumerating consumer keys on, so FEAT-3323 does not have
  to infer it from the implementation
- `docs/reference/CONFIGURATION.md` (same block) — state that orphaned
  `events-<pid>.sock` files from crashed producers are **not** swept, so a
  consumer enumerating the directory must tolerate dead endpoints
- `docs/ARCHITECTURE.md:613-615` — transport fan-out and socket seeding; note
  that a probe transiently triggers the seed callback on a live producer
- `docs/reference/API.md` — `UnixSocketTransport`

### Configuration
- No new keys. `events.socket.path` (default `.ll/events.sock`) and
  `events.socket.max_clients` (default `32`) keep their current meaning; `path`
  becomes "the preferred path" rather than "the path".

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- PID-suffixed sibling-path naming (dash-separated `{base}-{os.getpid()}`) is an
  established convention in this codebase, matching the shape this issue proposes for
  the claimed-path fallback — evidence: `worktree_utils.py:280-281`
  (`f".ll-session-{os.getpid()}"`), `fsm/persistence.py:848`
  (`f"{dest.name}.tmp-{os.getpid()}"`), `cli/artifact/templatize.py:604`
  (`f"{out_dir.name}.bak-{os.getpid()}"`).
- This codebase's established "is this resource still owned by a live process" pattern
  is PID-based (`os.kill(pid, 0)` or `psutil`-backed), not connect-and-inspect-errno —
  evidence: `fsm/concurrency.py:56-68` (`_process_alive`, bare `os.kill(pid, 0)`,
  ESRCH = dead) and `cli/queue.py:508-533` (`_verify_owner_alive`, layers
  `psutil.Process(pid).cmdline()`/`create_time()` on top specifically to avoid
  false-alive reads under a recycled PID, per its docstring at `queue.py:514`). No file
  under `scripts/` currently probes a socket path's connect-errno (`ENOTSOCK`/
  `ECONNREFUSED`) to test liveness, and `errno` is not imported in `transport.py` today —
  this issue's `_probe_socket_path` would be the first instance of that specific pattern
  in this codebase (searched: `errno.`, `ECONNREFUSED`, `ENOTSOCK` across `scripts/`).
- Module-level pure-function helpers that take explicit args and are called from outside
  the class (e.g. from `wire_transports`) are placed near the bottom of `transport.py`,
  after the class body they support — evidence: `_resolve_socket_path`
  (`transport.py:678-692`), `_make_seed_callback` (`transport.py:586-599`). Both proposed
  helpers (`_probe_socket_path`, `_claim_socket_path`) fit this existing placement shape.
- Every existing log call in `transport.py` is `logger.warning`, each message prefixed
  `"UnixSocketTransport: <message>"` — evidence: `_record_drop` (`:237-256`),
  `_record_rejection` (`:258-279`), `close()`'s join-timeout warnings (`:293-296`,
  `:314-318`). There is no `logger.info` precedent anywhere in this file today, though
  `logger.info` for notable/non-error conditions is an established pattern elsewhere in
  the codebase (e.g. `issue_manager.py:380`).
- This codebase's convention for documenting an accepted (not locked) TOCTOU race is:
  cite the originating bug ID, describe the concrete interleaving, and state the chosen
  fallback behavior — evidence: `session_log.py:176-180` ("Guard the stat() against a
  TOCTOU race (BUG-2489): the live host process can rotate or delete a .jsonl between
  the glob() above and the stat() below. Skip files that vanish...").

## Implementation Steps

1. Add `_probe_socket_path` (pure, three-state) and `_claim_socket_path`
   (all mutation) per the classification table above, using `errno` symbols
   rather than numeric literals. Close the probe socket in a `finally`.
2. Replace the unconditional unlink at `transport.py:157` with the claim; store
   the bound path on `self._path`.
3. Capture `(st_dev, st_ino)` into `self._bound_id` immediately after the
   successful `bind()`, and make `close()`'s unlink (`:320`) conditional on a
   re-`stat` matching it (`FileNotFoundError` → nothing to do).
4. Narrow the constructor's `try` so the failure handler at `:167-170` can only
   unlink after a successful `bind()`, and add the two-attempt `EADDRINUSE`
   fallback (fresh socket on attempt 2) to the suffixed path.
5. Log at INFO when a suffixed path is claimed, naming both paths — this is the
   only signal a user gets that two producers are live. Note at the call site
   that this is the first `logger.info` in `transport.py` (every existing call
   is `logger.warning`) and that the level is deliberate, so a later consistency
   sweep does not downgrade it.
6. Add TOCTOU comments in the `session_log.py:176-180` style (cite BUG-3324,
   describe the interleaving, state the fallback) at **two** sites: the probe,
   and the identity-checked unlink in `close()`.
7. Add the nine new tests; confirm the five existing path-shape tests pass
   unmodified.
8. Update `CONFIGURATION.md`, `ARCHITECTURE.md`, and `API.md`, including the
   sibling naming contract, the note that orphaned `events-<pid>.sock` files are
   not swept, and that directory-reading consumers must tolerate dead endpoints.

## Impact

- **Priority**: P3 — a real correctness defect, but it only bites projects that
  have opted into `events.transports: ["socket"]`, which is `[]` by default,
  and only when two runs overlap.
- **Effort**: Small-Medium — one constructor (three separate changes: the
  claim, the narrowed failure handler, the two-attempt `EADDRINUSE` fallback),
  `close()`'s inode-identity check, two helpers, nine tests. The upper end of
  Small-Medium: the `close()`-drain interleaving test needs deterministic
  thread coordination rather than sleeps, and is the most expensive item here.
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
- [ ] A producer exiting unlinks only a file that is still *the inode it bound*:
      if the path was reclaimed by another producer while `close()` was draining
      its client threads, the reclaimer's socket survives — asserted by a test
      that deterministically interleaves a reclaim into A's close-drain window.
- [ ] A stale socket file (both the regular-file and the bound-but-dead-owner
      cases) is still reclaimed automatically, with no manual cleanup.
- [ ] With a single producer, the bound path is exactly the configured path;
      `test_socket_registered_by_name`, `test_socket_uses_socket_path_from_config`,
      `test_socket_and_jsonl_both_registered`, `test_init_unlinks_stale_socket_file`,
      and `test_close_unlinks_socket_file` pass unmodified.
- [ ] Probing a live producer leaves no residue in its client pool once the
      probe returns: no net growth of its client list, no slot still held, and
      no events missed by its already-attached consumers — asserted by a test.
      (A `client_rejections` increment when probing a *saturated* producer, and
      a one-accept-wide slot occupancy during the probe itself, are accepted
      effects and explicitly not covered by this criterion.)
- [ ] A `bind()` that fails with `EADDRINUSE` on the configured path falls back
      to the pid-suffixed path instead of propagating out of the constructor,
      via a bounded two-attempt loop in the constructor (never in
      `_claim_socket_path`, which does not bind) — asserted by a test.
- [ ] A failed `bind()` never unlinks the path: the constructor's failure
      handler only removes a file it successfully bound — asserted by a test
      that forces the bind-failure path against a live out-of-band socket.
- [ ] A stale file at the pid-suffixed path is reclaimed by the same
      probe/unlink logic as the configured path, rather than being bound blind.
- [ ] Claiming a suffixed path is logged at INFO naming both paths.
- [ ] The multi-producer path shape is documented in
      `docs/reference/CONFIGURATION.md` alongside the `nc -U` note, including
      the `{stem}-{pid}{suffix}` sibling naming contract, that orphaned
      `events-<pid>.sock` files are not swept, and that a consumer enumerating
      the directory must tolerate dead endpoints.

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-26T17:26:24 - `7e9b1604-00c9-4e37-8a90-6f2ad32b27f1.jsonl`
- `/ll:confidence-check` - 2026-08-26T15:21:06 - `517f6995-71e2-43fd-9e62-23da16cd2b72.jsonl`
- `/ll:refine-issue` - 2026-08-26T15:07:47 - `48865e33-f926-4071-bfdf-2723c61ab53b.jsonl`
- `/ll:confidence-check` - 2026-08-26T15:03:51 - `48865e33-f926-4071-bfdf-2723c61ab53b.jsonl`
