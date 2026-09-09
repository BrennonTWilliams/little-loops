---
id: ENH-3416
title: Add attempt budget, backoff, and dead-lettering to ll-queue
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
labels:
- queue
- reliability
learning_tests_required:
- sqlite3
- psutil
confidence_score: 75
outcome_confidence: 35
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 0
missing_artifacts: true
---

## Summary

`ll-queue` ships with no failure policy, and the recovery path it does have is an unbounded retry loop. `queue_store.py` models pending/running/done with `claimed_at` and `owner_pid`; the only recovery is `reset_to_pending`, which clears both and carries no attempt counter. `cli/queue.py`'s `_reclaim_stale` runs on watcher startup and on every idle poll, returning any entry whose owner is not verifiably alive. An entry that reliably kills its own drainer — OOM, a crash in the dispatched action, a malformed spec — is therefore reclaimed and re-dispatched forever, with nothing recording that it has failed before. This is the precise failure that dead-lettering exists to stop, and a long-lived drainer makes it the normal case rather than a rare one someone is present to witness.

Specify and implement: an attempt counter per entry, bounded exponential backoff between attempts with a `next_attempt_at` the dequeue path honors, and a terminal dead-letter status carrying the last error so a poison entry leaves the rotation and stays inspectable. Distinguish the requeue semantics rather than collapsing them into one — a retry after failure consumes the attempt budget and applies backoff; a reclaim after an owner died without a verdict should preserve the original enqueue timestamp so the entry keeps its place in priority/FIFO fairness instead of going to the back; and an operator cancel should carry a reason and not be retried at all. Overflow and trimming should match each path's fairness intent rather than using one rule. Classify retryability from the error rather than guessing from an exit code, reusing whatever the open timeout-semantics issue settles — a dead owner and a rejected spec are not the same condition and should not share a policy.

## Current Behavior

`ll-queue`'s only failure-recovery path is `reset_to_pending()`
(`scripts/little_loops/queue_store.py:417`), which clears `claimed_at`/
`owner_pid` and returns an entry to `pending` with no attempt counter.
`_reclaim_stale()` (`scripts/little_loops/cli/queue.py:542`) calls it on
watcher startup and on every idle poll for any entry whose owner fails
`_verify_owner_alive()` (`cli/queue.py:514`). An entry whose dispatched
action reliably kills its own drainer (OOM, a crash in the action, a
malformed spec) is therefore reclaimed and re-dispatched indefinitely —
nothing on `QueueEntry` (`queue_store.py:267`) records that it has failed
before.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Full `QueueEntry` schema (`scripts/little_loops/queue_store.py:267`) has exactly these fields today: `id`, `action`, `enqueued_at`, `priority`, `status`, `result`, `claimed_at`, `owner_pid` — no attempt counter, no `next_attempt_at`, no reason/error field. `enqueued_at` is set once at `add_entry()` time and never mutated by `reset_to_pending`, `update_entry_result`, or `claim_entry`.
- `reset_to_pending` (`queue_store.py:417`) is a single SQL statement (`UPDATE ... SET status='pending', claimed_at=NULL, owner_pid=NULL WHERE id=? AND status='running'`) shared, per its own docstring, by both `_reclaim_stale`'s automatic sweep and `cmd_requeue`'s manual path — nothing distinguishes the two callers' intent today, and neither increments any counter.
- `claim_entry` (`queue_store.py:466`) claims any `pending` row unconditionally inside a `BEGIN IMMEDIATE` transaction (closing a TOCTOU race per BUG-2929) — it has no concept of a time-gated eligibility check, so honoring `next_attempt_at` will require either a `list_entries`/`claim_entry` filter or an additional in-Python check in `_drain_once` (`cli/queue.py:434`), which today selects the first priority/FIFO-ordered pending entry that wins the claim race.
- `cmd_requeue` (`cli/queue.py:686`) only accepts `id`, `--force`, `--json` — no `reason` argument exists anywhere on its argparse parser, and it can only act on a `status=='running'` entry (never a hypothetical `dead_letter` one). It always returns the entry to `pending`; there is no separate "cancel, never retry" verb today.
- No overflow, trimming, eviction, or max-size logic exists anywhere in `queue_store.py` or `cli/queue.py` (searched both files directly for `max.?size|trim|evict|overflow` — zero hits). The Summary's "rather than using one rule" phrasing presupposes an existing single overflow rule that is not actually present; per-path overflow/trimming is new functionality, not a refinement of differing existing behavior.
- The closest existing analog to an "operator-cancel" outcome is `force_stop` (`cli/queue.py:498-501`): a second shutdown signal mid-drain downgrades the entry to the ordinary `'failed'` status with `error: "interrupted by operator"` — it is triggered by signal handling during an in-flight drain, not an explicit subcommand, and lands on the same terminal status as any other failure rather than a distinct one.
- Two retryability mechanisms already coexist in the FSM engine, matching the exit-code-vs-error-type dichotomy this issue's Expected Behavior draws: `retryable_exit_codes: list[int] | None` (`fsm/schema.py:713`, exit-code allowlist) versus `classify_failure()`/`FailureType` (`issue_lifecycle.py:141-239`, text-pattern matching returning `(Enum, reason)`, consumed by `fsm/executor.py:2286-2327`). Neither is currently wired into `ll-queue`.
- `scripts/little_loops/mcp_server/tools.py:622,644` imports and calls `reset_to_pending`/`resolve_entry` for an MCP tool handler (FEAT-3343) — an additional caller of `reset_to_pending` not previously listed anywhere in this issue, which must be updated once the single-call semantics split.

## Expected Behavior

`QueueEntry` carries an attempt counter and a `next_attempt_at`, and the
dequeue path honors `next_attempt_at` with bounded exponential backoff
between attempts. Once the attempt budget is exhausted, the entry moves to a
terminal dead-letter status carrying the last error instead of re-entering
the pending rotation. Three requeue semantics stay distinct rather than
collapsing into one call: a failure retry (consumes the attempt budget,
applies backoff), an owner-death reclaim (preserves the original
`enqueued_at` so FIFO/priority position is unaffected), and an operator
cancel (carries a reason, is never retried). Retryability is classified from
the error's type, not guessed from an exit code.

## Reference shape

A production message-batching queue that has solved this exact problem lands on:

- **Bounded exponential backoff, 10 attempts, 5s → 300s, then dead-letter.**
- **Three distinct requeue semantics**, each preserving a different invariant that one generic retry would destroy: a budget-consuming requeue that applies backoff; a timestamp-preserving requeue, so an item retried after an owner death keeps its fairness position; and a cancelled-with-reason requeue that is never retried.
- **Overflow trimming that differs per path** — oldest-first in one, newest-first in the other — matching each path's fairness intent instead of applying one rule everywhere.
- **Typed retryability classification** at the transport layer: narrow the error to a class rather than guessing from a status code, and honor a server-supplied retry delay but **ceiling-clamp** it so worst-case latency stays bounded. Auth gets one refresh-and-retry, guarded so a static credential that "refreshes to itself" fails terminal immediately instead of replaying a byte-identical rejected request.

That last guard generalizes: a retry that cannot change the input is not a retry.

## Acceptance Criteria (added 2026-08-25)

- **Every error class marked retryable must be reachable by a policy whose maximum attempt count exceeds one.** Assert this as a deterministic test that enumerates the retryable classes and walks the policies that consume them. The failure it catches is silent and specific: a correct classification chain — retryable, non-fatal, backoff-eligible — rendered inert because the single policy that consumed it allowed one attempt. A durable-execution agent platform hit exactly this: a provider 429 killed a deployed run and tripped a circuit breaker, with the classification chain entirely correct and `maximum_attempts=1` making it make no difference. As `ll-queue` and the FSM executor gain richer error taxonomies, the gap between "classified retryable" and "actually retried" widens with nothing watching it. The companion retryable-vs-fail-fast admission table tabulates the classes and this issue sets the budgets; nothing currently asserts the join between them.

- **Express the policies as a small set of named constants, each carrying the failure that motivated it and the trade-off accepted in exchange, and lock the set with a test.** Not a post-hoc refactor — a shaping constraint on how this issue, the admission table, and the consecutive-failure circuit breaker are built, so all three land in one legible vocabulary instead of three slices with implicit rationale. A callsite that constructs its own policy literal rather than referencing a named constant is a bug of the same class, and the locking test is what makes that mechanically visible; this is the same discipline as restating a constraint where it is read rather than only where it is declared.

The named-constants requirement is not stylistic. The failure it prevents is a contract leak: a component declares a non-retryability policy on itself, and a caller hand-typing a fresh policy literal at the invocation site silently drops the declaration. The declaration was correct; the callsite quietly overrode it. Shared named constants re-imposed at the callsite, plus a test that locks them, is the answer that has been paid for elsewhere.

## Scope Boundaries

- **In scope**: an attempt counter and `next_attempt_at` on `QueueEntry`, bounded exponential backoff, a terminal dead-letter status, the three distinct requeue code paths (retry/reclaim/cancel) and their per-path overflow-trimming rules, and error-based (not exit-code-based) retryability classification.
- **Out of scope**: defining the retryable-error taxonomy itself — this issue consumes whatever the referenced open timeout-semantics issue settles, it does not own that classification. Also out of scope: the consecutive-failure circuit breaker and the retryable-vs-fail-fast admission table named in the Acceptance Criteria — those are companion issues this one's named policy constants must stay compatible with, not deliverables of this issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Searched `.issues/` repo-wide (exact and fuzzy) for a "timeout-semantics" issue — none exists. The Summary's "reusing whatever the open timeout-semantics issue settles" and this section's "it does not own that classification" both defer to an issue that is not filed under that name or a close synonym.
- Neither the "retryable-vs-fail-fast admission table" nor the "consecutive-failure circuit breaker" companion issues named above are filed under those names either (searched repo-wide). A broader search surfaced two FSM-side issues — `P3-FEAT-1637` (fsm stall detector for repeated state failures) and `P2-ENH-2245` (circuit-breaker recurrent window for non-consecutive state failures) — but both are FSM state-failure detectors, not `ll-queue`-side companions, and neither matches this issue's named companion by scope.

## Integration Map

### Files to Modify

- `scripts/little_loops/queue_store.py` — `QueueEntry` (line 267) gains `attempt`/`next_attempt_at` fields; `reset_to_pending` (417) splits into the retry/reclaim paths; a new `dead_letter_entry` function; `claim_entry` (466) must honor `next_attempt_at` eligibility; a new migration entry appended to `_MIGRATIONS` (currently ends at index 1, `SCHEMA_VERSION = 2`, lines 105-131)
- `scripts/little_loops/cli/queue.py` — `_reclaim_stale` (542) becomes the owner-death reclaim path (must preserve `enqueued_at`); `cmd_requeue` (686) becomes the operator-cancel-with-reason path; `_drain_once` (434) must filter/order pending entries by `next_attempt_at` eligibility; `_STATUS_COLOR` (50-55) needs an entry for the new `dead_letter` status or it silently falls through to the default color

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/queue_store.py:279-296` (`QueueEntry.to_dict()`) — an explicit hand-built dict literal, not `dataclasses.asdict()`; the new `attempt`/`next_attempt_at` (and dead-letter error/reason) fields will not appear in any `--json` output or MCP tool response unless added here explicitly [Agent 2 finding]
- `scripts/little_loops/cli/queue.py:306-317` (`cmd_status`'s human-readable `status_block` dict) — hand-lists `id`/`action`/`priority`/`status`/`enqueuedAt`/`result` only; needs `attempt`/`nextAttemptAt`/error fields added so non-JSON `ll-queue status <id>` shows them for a backing-off or dead-lettered entry [Agent 2 finding]
- `scripts/little_loops/mcp_server/tools.py:838` (`queue_list` tool `description=`) — hardcodes `"...entries (pending/running/done/failed)."`; needs `dead_letter` appended, a third independent enumeration of the status set beyond `_STATUS_COLOR` and doc tables [Agent 1 + Agent 2 finding]
- `scripts/little_loops/mcp_server/tools.py:615-645` (`_tool_queue_requeue`) — independently hand-builds the transition `{"field": "status", "from": "running", "to": "pending"}` in both its dry-run and applied branches (641, 645) and mirrors `ll-queue requeue`'s *current* running→pending meaning verbatim, with no `reason` parameter on its own schema; must track whichever new semantics `cmd_requeue`'s cancel-with-reason path settles into [Agent 2 finding]
- `scripts/little_loops/mcp_server/tools.py:585-612` (`_tool_queue_remove`), guard at `:601` `if entry.status != "pending":` — an independent status-transition gate, structurally identical to `cli/queue.py:331`'s `cmd_remove` guard (`if entry.status != "pending" and not getattr(args, "force", False):`); both gates must be updated in lockstep with a decision on whether a `dead_letter` entry is removable the same way a `pending` one is [Agent 2 finding]

### Dependent Files (Callers/Importers)

- `scripts/little_loops/mcp_server/tools.py:622,644` — imports and calls `reset_to_pending`/`resolve_entry` from `queue_store` for an MCP tool handler (FEAT-3343); once `reset_to_pending`'s single-call semantics split into retry/reclaim/cancel, this caller must be updated to invoke whichever path matches its MCP-tool intent
- `scripts/tests/test_queue_store.py:428,438,444` — `TestResetToPending` exercises `reset_to_pending`'s current single-call contract; splitting the call changes what this class needs to assert
- `scripts/tests/test_cli_queue_run.py:638-746` — `TestReclaimStale`, `TestCmdRequeue` exercise the two current callers of `reset_to_pending`; both patch `little_loops.cli.queue.psutil.Process` rather than starting a real process

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/tools.py:644` (`_tool_queue_requeue`, inside `queue_requeue` MCP tool handler) — a third caller of `reset_to_pending` not previously listed anywhere in this issue (Files to Modify above lists only `mcp_server/tools.py:622,644` as the *call site*; this entry records it as a semantic caller needing its own update once the split lands) [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/queue.py:331` (`cmd_remove`'s `if entry.status != "pending" and not getattr(args, "force", False):` guard) — duplicates the same status-gate independently hardcoded in `mcp_server/tools.py:601`'s `_tool_queue_remove`; see Files to Modify entry above [Agent 2 finding]
- `scripts/tests/test_cli_surface.py:139` — `("ll-queue", {"add", "list", "status", "remove", "run", "requeue"})`, a literal subcommand-set lock checked against the real `ll-queue --help` output. Program Design does not name a subcommand rename or addition, so no edit is expected here — flagged only so an implementer confirms it stays true if the `requeue` verb's *name* (not just its semantics) changes [Agent 2 + Agent 3 finding]

### Conventions in Force

- Bounded exponential backoff in this codebase is expressed as a named base constant and a named ceiling constant with `delay = base * 2^(attempt-1)` (optionally `+ jitter`) — evidence: `fsm/executor.py:105-114` (`_DEFAULT_RATE_LIMIT_BACKOFF_BASE`, jittered) and `transport.py:76-77,1830` (`_WEBHOOK_RETRY_BASE_S`/`_WEBHOOK_RETRY_MAX_S`, no jitter, iterative doubling). The two disagree on jitter, and no shared `compute_backoff()` helper exists between them — each module owns its own inline formula.
- A machine-readable reason/status code set in this codebase is declared as a plain `Enum` with a per-member rationale comment, then a consumer derives its accepted-values set via `frozenset(r.value for r in Enum)`, locked by a test asserting that derived set equals the enum-derived set — evidence: `DeferReason`/`_DEFERRAL_REASON_CODES` (`issue_lifecycle.py:65-93`, `cli/issues/set_status.py:21-23`, `test_issue_lifecycle.py:1985-1993`) and `ClosureReason` mirroring it. This is a closer match to the Acceptance Criteria's "lock the set with a test" requirement than the FSM's `_DEFAULT_RATE_LIMIT_*` numeric constants, which carry rationale comments but are never asserted against their declared defaults (only monkeypatched in tests).
- New nullable columns are added as one `ALTER TABLE ... ADD COLUMN` string per migration-list entry, no backfill, with a comment citing the motivating issue — evidence: `queue_store.py:124-131` (the `claimed_at`/`owner_pid` entry from FEAT-2930), mirrored throughout `session_store/schema.py` (e.g. `:933`, `:1372-1375`).
- Retryability classification elsewhere in this codebase is a plain function matching error-text patterns and returning `(Enum, reason: str)`, not a typed exception hierarchy — evidence: `classify_failure()`/`FailureType` (`issue_lifecycle.py:141-239`), consumed by `fsm/executor.py:2286-2327`. Its one exit-code-keyed branch (`returncode == 143 and result_seen`) is explicitly commented as the sole exception, since a clean `SIGTERM` leaves no text signature to match. A narrower, purely exit-code-based mechanism also exists (`retryable_exit_codes` on FSM `StateSpec`, `fsm/schema.py:713`) — this is the mechanism the issue's "not guessed from an exit code" language is contrasting against.
- An operator/automation-supplied reason for a terminal transition is stored as its own string field named to match its frontmatter/API key, with machine-emitted values drawn from an enum-derived frozenset and human-supplied values left as free text — evidence: `deferred_reason`/`DeferReason` (`docs/reference/DEFERRAL_CODES.md:3-6`), `close_reason` (`parallel/types.py:77,103,127,153`).
- `queue_store.py` has no existing `VALID_STATUSES`/terminal-status frozenset constant today (unlike `issue_progress.py`'s `_ALL_STATUSES`/`_TERMINAL_STATUSES`) — status values are ad hoc string literals across `cli/queue.py`.

### Tests

- `scripts/tests/test_queue_store.py` — one `TestX` class per function under test (`TestResetToPending`, `TestClaimEntry`, `TestV1ToV2Migration`, etc.), each test building its own isolated `tmp_path / "queue.db"`; `TestV1ToV2Migration` (lines 375-401) is the closest precedent for a new migration test, bootstrapping the prior schema via `_MIGRATIONS[0]` directly and asserting `PRAGMA table_info` afterward
- `scripts/tests/test_cli_queue_run.py` — `TestReclaimStale`, `TestCmdRequeue` (638-746) are the closest existing precedent for new dead-letter/backoff test classes; both patch `psutil.Process` and assert on the persisted `get_entry(entry_id).status` rather than only the function's return value; the file's autouse `_isolate_cwd` fixture and `_add()`/`_add_and_get_id()` helpers are the established harness
- No existing test locks the *values* of any numeric backoff constant in this codebase (the FSM's `_DEFAULT_RATE_LIMIT_*` are only ever monkeypatched, never asserted equal to their declared defaults) — the enum+frozenset+equality-lock shape (`DeferReason`) is the precedent to follow if this issue's named policy constants are meant to be "locked by a test" literally

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat_queue_mcp_tools.py` — not previously listed anywhere in this issue; exercises `mcp_server/tools.py`'s `queue_requeue`/`queue_remove`/`queue_add`/`queue_list`/`queue_get` MCP tools end-to-end over a real stdio MCP client/server (the closest thing to integration coverage this surface has). `test_queue_requeue_running_entry` (142-176) calls `reset_to_pending` via `_tool_queue_requeue` and will break once that call splits into retry/reclaim/cancel paths; its raw-SQL fixture (`UPDATE queue_entries SET status = 'running', owner_pid = 999999 ...`, line 157) will need the new columns/defaults once the migration lands [Agent 1 + Agent 3 finding]
- `scripts/tests/test_cli_queue.py` — not previously listed anywhere in this issue; imports `list_entries`/`update_entry_result` directly (16, 299, 376) and covers `cmd_list`/`cmd_add`. `test_list_json_unaffected_by_summary_change` (311-328) is a precedent showing this file already polices exact JSON key presence/absence on `to_dict()` output — the closest existing pattern to adapt for asserting the new `attempt`/`nextAttemptAt` keys appear correctly once `to_dict()` is updated [Agent 1 + Agent 3 finding]
- `scripts/tests/test_cli_queue_run.py` — beyond the already-known `TestReclaimStale`/`TestCmdRequeue`, this file has 13 assertions of `entry.status == "failed"` as the *immediate* post-failure terminal state (lines 121, 137, 153, 175, 212, 290, 412, 426), which will need reworking once some failures instead return to `pending` with backoff rather than landing directly on `failed`/`dead_letter`; its raw-SQL fixture `INSERT INTO queue_entries(id, action, enqueued_at, priority, status, result) VALUES (...)` (line 195) names the exact pre-migration column set and will need the new columns/defaults [Agent 2 + Agent 3 finding]
- Backoff/retry-counter test-pattern precedent (distinct from the `DeferReason` enum-lock shape already cited above): `TestAPIErrorRetries`/`TestInfraRetry` (`scripts/tests/test_fsm_executor.py:8903-9160`) patch `little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF`/`_DEFAULT_INFRA_RETRY_BACKOFF` to `0` to avoid wall-clock delay, then assert retry counts and emitted events — the closer shape to mirror for a queue-side attempt/backoff-constant test, since it's counter-plus-wall-clock-avoidance shaped rather than enum-derivation shaped [Agent 3 finding]

### Documentation

- `docs/ARCHITECTURE.md:827-838` ("Queue DB (ll-queue)" section) — describes the current schema/semantics; will need updating for attempt/backoff/dead_letter
- `docs/reference/API.md:10510-10533` (`little_loops.queue_store` module reference), `:5056-5066` (`ll-queue` CLI entry-point doc)
- `docs/reference/CLI.md:4052-4135` (`### ll-queue` command reference)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:5299-5304` — separate prose (outside the already-known 4052-4135 range) describing `queue_add`/`queue_remove`/`queue_requeue` as "`ll-queue`'s three mutating tools" and stating `queue_remove`/`queue_requeue` "drop the CLI's `--force` flag (removing/requeuing a non-matching-state entry)" — describes `queue_requeue`'s current running→pending-only semantics and needs revision once the cancel-with-reason path lands [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:717` — "`ll-queue` persistence configuration (FEAT-2682). Owns the `.ll/queue.db` location..."; would need updating alongside the Configuration section's open question below if attempt-budget/backoff values become configurable [Agent 1 finding]

### Configuration

- `scripts/little_loops/config-schema.json:2262-2270` — existing `queue` config block (FEAT-2682); this issue's Program Design does not currently specify whether attempt-budget/backoff values are configurable here or fixed as code constants — an open question, not settled by research

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:1559-1570` (`QueueConfig` dataclass) and `scripts/little_loops/config/core.py:522-525` (`LLConfig.queue` accessor) — the Python-side parser counterpart to `config-schema.json`'s `queue` block above; currently only parses `db_path`. If the open question above resolves to "configurable," this dataclass is the paired file that must gain the new field(s) alongside the schema — the two halves of this codebase's config surface always move together [Agent 1 finding]

## Program Design

### Types

- `QueueEntry` (`scripts/little_loops/queue_store.py:267`) — add `attempt: int`, `next_attempt_at: str | None`
- `status: str` on `QueueEntry` — extend the existing `pending`/`running`/`done` values with a terminal `dead_letter` status
- A small set of named backoff/policy constants (per the Acceptance Criteria's "named constants" requirement), e.g. defined alongside `QueueEntry` in `queue_store.py`

### Signatures

- `reset_to_pending(entry_id, db_path=...) -> bool` (`queue_store.py:417`) — split into the three distinct requeue paths below rather than one shared call
- `_reclaim_stale(db_path) -> int` (`cli/queue.py:542`) — the owner-death reclaim path; must preserve `enqueued_at` and not touch attempt/backoff
- `cmd_requeue(args) -> int` (`cli/queue.py:686`) — the operator-cancel-with-reason path; marks the entry non-retryable
- `dead_letter_entry(entry_id, error: str, db_path=...) -> bool` — new; sets the terminal status and records the last error

### Call Path

`cmd_run` (`cli/queue.py:562`) -> `claim_entry` (`queue_store.py:466`) -> action dispatch fails -> classify error -> `reset_to_pending` (`queue_store.py:417`, split into the retry/reclaim paths above) or `update_entry_result` (`queue_store.py:439`, for the dead-letter path) or `dead_letter_entry`

### Decision Rules

- **Retry-budget policy (max attempts, backoff base/ceiling seconds) is not pinned to concrete values anywhere in this issue.** The "Reference shape" section cites an external message-batching queue's values (10 attempts, 5s → 300s) as an example of the *shape* of a solution, not a decision for this codebase — the Acceptance Criteria requires "a small set of named constants" but does not state what those constants equal. UNRESOLVED: an implementer or `/ll:decide-issue` pass must pin concrete numbers, expressed as named constants in the `DeferReason`/frozenset-and-lock-test shape (see Integration Map → Conventions in Force), not as bare literals.
- **Retryability classification has no taxonomy to consume.** The Summary explicitly defers to "whatever the open timeout-semantics issue settles," but no issue matching "timeout-semantics" (or a close synonym) exists in `.issues/` (see Scope Boundaries → Codebase Research Findings). UNRESOLVED pending either that issue being filed or this issue's scope absorbing a minimal classification of its own. The existing precedent for the classification *mechanism* (not values) is `classify_failure()`/`FailureType` (`issue_lifecycle.py:141-239`) — a text-pattern function returning `(Enum, reason)` — contrasted with the exit-code-only `retryable_exit_codes` (`fsm/schema.py:713`) this issue explicitly rejects following.
- **Overflow/trimming has no existing baseline to differentiate from** (see Current Behavior → Codebase Research Findings) — per-path overflow/trimming is new functionality, not a differentiation of pre-existing behavior. Exact per-path rules (which path trims oldest-first vs newest-first, and at what size) are UNRESOLVED.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/queue_store.py:279-296` (`QueueEntry.to_dict()`) — add `attempt`/`next_attempt_at` (and dead-letter error/reason) fields to the explicit dict literal so `--json` output and MCP tool responses include them
- Update `scripts/little_loops/cli/queue.py:306-317` (`cmd_status`'s `status_block` dict) — add the same fields to the non-JSON `ll-queue status <id>` rendering
- Update `scripts/little_loops/mcp_server/tools.py:838` (`queue_list` tool description) — append `dead_letter` to the `(pending/running/done/failed)` enumeration
- Update `scripts/little_loops/mcp_server/tools.py:615-645` (`_tool_queue_requeue`) — replace the hardcoded `"to": "pending"` transition and add a `reason` parameter to the tool's own schema, tracking whichever cancel-with-reason semantics `cmd_requeue` settles into
- Update `scripts/little_loops/mcp_server/tools.py:585-612` (`_tool_queue_remove`) and `scripts/little_loops/cli/queue.py:331` (`cmd_remove`) in lockstep — decide and encode whether a `dead_letter` entry is removable the same way a `pending` one is today
- Update `scripts/tests/test_cli_queue_run.py` — rework the 13 assertions hardcoding `status == "failed"` as the immediate post-failure state (lines 121, 137, 153, 175, 212, 290, 412, 426) and the raw-SQL fixture column list at line 195
- Update `scripts/tests/test_feat_queue_mcp_tools.py` — rework `test_queue_requeue_running_entry` (142-176) for the split `reset_to_pending` call path and its raw-SQL fixture at line 157
- Add coverage in `scripts/tests/test_cli_queue.py` — extend the `test_list_json_unaffected_by_summary_change` (311-328) pattern to assert the new `attempt`/`nextAttemptAt` keys appear correctly in `--json` output

## Folded constraints

The following were closed as design constraints with no shippable unit of their own; this issue carries their rule.

- **Terminality is claimed per call site, not encoded into the error.** The error carries a structured reason; each call site (checkpoint vs read path) decides whether it is terminal and records that decision as metadata.
- **Classify agent failures by whether observable work exists, and revive in place.** Retryability keys on whether the user already saw output; revival reuses the same run identity; a persisted `retried_at` fence caps residue at one re-run per entry.

## Impact

- **Priority**: P1 - matches the existing frontmatter priority; an entry that reliably crashes its drainer is re-dispatched forever today, a live reliability gap for any long-running watcher.
- **Effort**: Large - new attempt/backoff fields, three distinct requeue code paths, per-path overflow trimming, and an error-classification layer, none of which exist today.
- **Risk**: Medium - a `QueueEntry` schema change (new columns via a migration, following the existing `_apply_migrations` pattern at `queue_store.py:170`) plus a behavior change to `_reclaim_stale`/`reset_to_pending` call sites.
- **Breaking Change**: Yes - `reset_to_pending`'s single-call semantics split into distinct retry/reclaim/cancel paths; existing callers must pick the right one.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 75/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 35/100 → VERY LOW

### Concerns
- Architecture Compliance (15/20): two existing backoff-constant conventions in this codebase disagree on jitter (`fsm/executor.py`'s `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` is jittered; `transport.py`'s `_WEBHOOK_RETRY_BASE_S`/`_WEBHOOK_RETRY_MAX_S` is not, no shared `compute_backoff()` helper exists) and the issue does not say which to follow.
- Issue Well-Specified (10/20): Program Design → Decision Rules explicitly flags three UNRESOLVED items requiring a decision before implementation can proceed cleanly: (a) concrete attempt-budget/backoff constant values, (b) retryability classification taxonomy — deferred to an open "timeout-semantics" issue that does not exist anywhere in `.issues/`, (c) per-path overflow/trimming rules with no existing baseline to differentiate from.
- Dependencies Satisfied (10/20): the retryability classification this issue relies on is explicitly out of scope and deferred to an unfiled companion issue; Scope Boundaries states this issue "does not own that classification" but nothing currently exists for it to consume, leaving only the existing `classify_failure()`/`FailureType` mechanism as a fallback shape.

### Outcome Risk Factors
- Complexity (0/25): 16+ distinct change sites across `queue_store.py`, `cli/queue.py`, two MCP tool handlers, four test files, four docs files, and two config files, combined with deep architectural rewiring — `reset_to_pending`'s single-call semantics splits into three distinct code paths, a stated breaking change to existing callers.
- Ambiguity (10/25): the same three UNRESOLVED design decisions noted above (backoff constants, retryability taxonomy, overflow/trim rules) will require judgment calls during implementation rather than being resolvable purely from the issue text.
- Change Surface (0/25): 11+ known callers/dependents of `reset_to_pending`/`cmd_requeue` span `cli/queue.py`, `mcp_server/tools.py`, and 13 existing test assertions hardcoding the post-failure `status == "failed"` state — a very wide blast radius for a breaking API split.

## Status

**Open** | Created: 2026-09-08 | Priority: P1


## Session Log
- `/ll:decide-issue` - 2026-09-09T03:43:16 - `96a64da7-7e7c-4bdc-9e11-d16d6c8ed5d2.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:41:28 - `96a64da7-7e7c-4bdc-9e11-d16d6c8ed5d2.jsonl`
- `/ll:wire-issue` - 2026-09-09T03:17:51 - `ae93785e-f7d9-41cc-96ab-d51f1883c15a.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:04:27 - `a4badc70-f3c5-4caf-beea-29940135de9c.jsonl`
- `/ll:format-issue` - 2026-09-09T02:34:54 - `b326158e-3610-46e0-8daf-a6fb008cff1f.jsonl`
