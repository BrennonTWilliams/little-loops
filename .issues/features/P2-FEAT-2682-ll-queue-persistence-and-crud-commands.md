---
id: FEAT-2682
title: ll-queue persistence layer and add/list/status/remove commands
type: FEAT
priority: P2
status: done
captured_at: '2026-07-18T00:00:00Z'
completed_at: '2026-07-18T21:50:56Z'
discovered_date: 2026-07-18
discovered_by: issue-size-review
parent: EPIC-2670
depends_on:
- ENH-2668
relates_to:
- FEAT-2669
- FEAT-2683
- FEAT-2684
labels:
- queue
- cli
- scheduling
confidence_score: 97
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 22
---

# FEAT-2682: `ll-queue` persistence layer and `add`/`list`/`status`/`remove` commands

## Summary

Build the real, persisted queue entry store for `ll-queue` — schema
`{id, action: ActionSpec, enqueuedAt, priority, status, result}` — plus
the CRUD-facing commands (`add`, `list`, `status`, `remove`) that operate
on it. This is the foundation child of FEAT-2669's decomposition; the
dequeue-execute worker (FEAT-2683) and the `ll-loop queue` compat shim
(FEAT-2684) both build on the schema and storage introduced here.

## Parent Issue

Decomposed from FEAT-2669: Generic `ll-queue` (heterogeneous work-item
queue). FEAT-2669's own Scope Boundaries deferred "persistence vs.
commands as separate issues" until its four open design questions were
resolved; they are now resolved (see FEAT-2669's Codebase Research
Findings / Decision Rationale), which unblocks this split.

## Motivation

`ll-loop queue` today is a liveness-marker mechanism, not a real queue —
entries are only ever created as a side effect of `ll-loop run --queue`
losing a lock race, and there is no `add`/`enqueue` command for
non-FSM work (a skill invocation, a one-shot command, a prompt). This
child introduces the actual persisted store and the commands to
populate and inspect it.

## Current Behavior

`ll-loop queue` is not a real queue: entries only appear as a side effect
of `ll-loop run --queue` losing a lock race (`cli/loop/run.py:356-427`,
`_queue_entry_file`/`_cleanup_queue_entry`), and there is no `add`/
`enqueue` command for non-FSM work. `cli/loop/queue.py`'s `list`/`remove`
operate on PID-liveness JSON markers under `.queue/*.json`, not
persisted rows — there is no schema, no priority ordering, and no way to
enqueue a skill/command/prompt invocation directly.

## Use Case

A user wants to queue a one-off skill invocation (e.g.
`/ll:audit-docs`) to run once the current FSM loop iteration frees up,
without writing a bespoke wrapper script. They run `ll-queue add
--skill audit-docs`, run `ll-queue list` to confirm it's queued at the
right priority tier, and later `ll-queue status <id>` to check whether
it ran and inspect its result.

## Expected Behavior

- Persisted queue entries — sqlite (`.ll/queue.db`, consistent with
  `.ll/history.db`) per FEAT-2669's Decision Rationale — with schema
  `{id, action: ActionSpec, enqueuedAt, priority, status, result}`.
  `result` is hybrid per FEAT-2669 Q4: small metadata
  (`exit_code`/`error`) stored inline; large `stdout`/`stderr` written to
  a per-entry-id scratch artifact referenced by path.
- Numeric priority ordering reusing `IssuePriorityQueue`'s model
  (`parallel/priority_queue.py:22-259`, `QueuedIssue.__lt__` comparing
  `(priority, timestamp)`) per FEAT-2669 Q3 — P0>...>P5 tiered, FIFO
  within a tier.
- `ll-queue add <action-spec>` — accepts an FSM loop name, a
  skill/command name, or a raw CLI invocation, normalized into an
  `ActionSpec` via ENH-2668's `runner_spec.py`, and persists it.
- `ll-queue list` — lists entries with priority/status, ordered per the
  priority model above.
- `ll-queue status <id>` — shows a single entry's current state and
  result metadata.
- `ll-queue remove <id>` — deletes a pending entry (mirrors today's
  `ll-loop queue remove` semantics for non-running entries).
- Possible `queue.*` namespace in `.ll/ll-config.json` for persistence
  location.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Create
- `scripts/little_loops/queue_store.py` (new) — sqlite persistence layer for
  `.ll/queue.db`, modeled on `session_store.py`'s migration/schema-version
  pattern (`_MIGRATIONS`, `_apply_migrations()`, `ensure_db()`, `connect()`,
  `_configure_connection()` for WAL + `busy_timeout`).
- `scripts/little_loops/cli/queue.py` (new) — `main_queue()` entry point plus
  `cmd_add`/`cmd_list`/`cmd_status`/`cmd_remove`, modeled on
  `cli/learning_tests.py:143` (`main_learning_tests()` — smallest complete
  argparse-subcommand-dispatch template) and `cli/loop/queue.py`'s
  `cmd_queue_list()`/`cmd_queue_remove()` for output conventions (short-id
  prefix resolution, `--json` vs. colorized-text dual output via
  `cli/output.py`'s `print_json()`/`colorize()`).

### Files to Modify
- `scripts/pyproject.toml:51-97` — add
  `ll-queue = "little_loops.cli:main_queue"` to `[project.scripts]`.
- `scripts/little_loops/cli/__init__.py` — register `main_queue` (mirrors
  `main_history`, `main_session`, etc.).
- `scripts/little_loops/config-schema.json` (near the `history` block, ~line
  1751) — add a `queue.*` namespace (e.g. `db_path` override) following
  `history.db_path`'s pattern.
- `scripts/little_loops/config/features.py` (~line 1076) — add a
  `QueueConfig` dataclass with a lenient `from_dict()`, mirroring
  `HistoryConfig`.
- `scripts/little_loops/config/core.py` (`BRConfig`) — **required, not
  optional**: three touch points mirroring `HistoryConfig`'s wiring —
  (1) import `QueueConfig` alongside the `HistoryConfig` import block
  (~line 23-39), (2) constructor line
  `self._queue = QueueConfig.from_dict(self._raw_config.get("queue", {}))`
  (parallel to `self._history = HistoryConfig.from_dict(...)` at
  ~line 250), (3) `@property def queue(self) -> QueueConfig` accessor
  (parallel to `history` property at ~line 363), and (4) a `"queue": {...}`
  entry inside `BRConfig.to_dict()` (~line 570-729, parallel to the
  `"history": {...}` entry). `resolve_variable()` (`ll-config get`, ~line
  830) resolves dotted paths exclusively against `to_dict()` — without the
  `to_dict()` entry, `ll-config get queue.<field>` silently returns `None`
  even with the dataclass and schema both present. [Wiring pass added by
  `/ll:wire-issue`]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py` — `BRConfig` is the central config
  aggregator every feature-config dataclass (`HistoryConfig`, `LoopsConfig`,
  etc.) wires into; `QueueConfig` must join the same way (see above).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — add a module reference table row + a
  `## little_loops.queue_store` prose section (mirrors the
  `little_loops.session_store` entry at ~line 81 / ~line 7627), plus
  `main_queue`/subcommand documentation analogous to the `ll-session`/
  `ll-history` entries (~lines 4112-4140).
- `docs/reference/CLI.md` — add a `### ll-queue` section with
  `#### ll-queue add|list|status|remove` subcommand headers and an
  Examples block, mirroring `### ll-history` (~line 1985) / `### ll-session`
  (~line 2424).
- `docs/reference/CONFIGURATION.md` — add a `queue.*` documentation block
  (table + `####` sub-headers), mirroring the `history.*` block starting
  ~line 569.
- `docs/ARCHITECTURE.md` — add a `little_loops.queue_store` capability-table
  row; if `queue_store.py` adopts its own `_MIGRATIONS` versioning (per the
  session_store.py-modeled pattern), add matching schema-migration table
  rows (mirrors the `v1`-`v22` table at ~lines 647-682) and a producer/
  consumer table row + Mermaid diagram node (~lines 743-765). Note: `ll-verify-kinds`
  only asserts `session_store._MIGRATIONS` coverage — a separate
  `queue_store._MIGRATIONS` would not be auto-covered by that gate unless
  explicitly extended (advisory, not a hard requirement for this issue).
- `CONTRIBUTING.md` — add a `cli/queue.py` line to the `cli/` directory-tree
  listings (~line 266 and ~line 195-196).
- `commands/help.md` — add an `ll-queue` catalog line (mirrors the
  `ll-history`/`ll-session` lines ~232-299) so `/ll:help` reflects the new CLI.
- `.claude/CLAUDE.md` "## CLI Tools" section — add an `ll-queue` bullet
  following the established one-line convention (name — description,
  subcommands).

### Existing Mechanism Being Superseded (context only — not in scope here)
- `scripts/little_loops/cli/loop/queue.py` — today's `ll-loop queue
  list`/`remove` operate on PID-liveness JSON markers under `.queue/*.json`,
  not a persisted store. `cli/loop/_helpers.py:read_queue_entries()` does
  dead-PID pruning as a list side effect; `cli/loop/run.py` (~lines 356-427,
  `_queue_entry_file`/`_cleanup_queue_entry`) creates entries only as a
  fallback when `ll-loop run --queue` loses a lock race. FEAT-2684 migrates
  this; the new `.ll/queue.db` schema should use a distinct id space so the
  two mechanisms don't collide during the transition.

### Reusable / Adaptation-Needed Code
- **`ActionSpec`/`RunnerType`/`run_action()`** (`scripts/little_loops/runner_spec.py`)
  — direct reuse for the `action` field and execution dispatch. **Gap**: no
  existing code infers `RunnerType` from a bare string — every current
  caller (`cli/harness.py`'s `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`/
  `cmd_dsl`, `cli/action.py`'s `cmd_invoke`) hard-codes the runner kind via
  its own subcommand. `ll-queue add`'s classification of an FSM loop name
  vs. a skill/command name vs. a raw CLI invocation has no existing code
  path to call into and must be written new before invoking `run_action()`.
  Note also that `run_action()` does not dispatch `RunnerType.LOOP` (FSM
  loops are stateful/resumable and go through `PersistentExecutor`
  directly per the module docstring) — a queued FSM-loop entry needs the
  same "spec for identity/observability, dispatch elsewhere" treatment,
  relevant to FEAT-2683's worker loop.
- **`IssuePriorityQueue`/`QueuedIssue`** (`scripts/little_loops/parallel/priority_queue.py`,
  `scripts/little_loops/parallel/types.py:20-40`) — **not directly reusable
  as a class**: `QueuedIssue.issue_info` is typed concretely as `IssueInfo`,
  and `IssuePriorityQueue.add()` hardcodes `issue.issue_id`/
  `issue.priority_int`. Only the `(priority, timestamp)` `__lt__` comparator
  shape and the `DEFAULT_PRIORITIES = ["P0", ..., "P5"]` lower-is-higher
  convention are reusable as-is; the sqlite schema's `ORDER BY` should
  replicate this tuple ordering rather than importing the class directly.
- **`session_store.py`** — the `_MIGRATIONS`/`_apply_migrations()`/
  `ensure_db()` pattern is the direct template for `.ll/queue.db`. The
  closest column-shape precedent for a "batch execution ground truth" table
  (written directly from Python, not JSONL-derived) is
  `orchestration_runs`/`loop_runs` — nullable `error TEXT`, `status TEXT NOT
  NULL`, ISO8601 TEXT timestamps.
- **Scratch artifact writing** — no existing Python helper writes an
  arbitrary payload to a per-id scratch file and returns a path reference;
  the only existing mechanism (`hooks/scripts/scratch-pad-redirect.sh`) is a
  bash `PreToolUse` hook, PID-keyed, and host-side only. The hybrid
  `result.stdout`/`result.stderr` scratch-artifact write this issue
  requires needs new Python code (e.g. a queue-entry-id-keyed file under
  `.loops/tmp/`), not a reuse of the PID-keyed hook convention.

### Tests
- `scripts/tests/test_session_store.py` — sqlite test-fixture pattern to
  follow (module-scoped tmp parent + per-test unique subdir via a
  `tmp_path` fixture override; raw `sqlite3.connect()` assertions against
  `meta`/`sqlite_master`, not the public API).
- `scripts/tests/test_priority_queue.py` — priority/FIFO ordering test
  pattern.
- `scripts/tests/test_cli_loop_queue.py` — `list`/`remove` CLI coverage
  pattern (includes the BUG-1281 FIFO regression test) to model new CRUD
  tests after.
- `scripts/tests/test_runner_spec.py` — existing `ActionSpec`/`RunnerType`/
  `run_action()` coverage to extend, not duplicate.
- New: a `test_queue_persistence.py`-style module per this issue's
  Acceptance Criteria (persistence, ordering, `add` normalization for all
  three `ActionSpec` kinds).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — add a `test_queue_in_schema`
  method to `TestConfigSchema`, following the `test_code_query_in_schema`/
  `test_history_in_schema` template (root schema has
  `additionalProperties: false`, so an undeclared `queue` block would
  reject any config that sets it).
- `scripts/tests/test_config.py` — add a `TestQueueConfig` class following
  `TestLoopsConfig`'s two-test minimum shape (`test_from_dict_with_all_fields`,
  `test_from_dict_with_defaults`), plus a `BRConfig`-level test proving
  `queue` is wired into `to_dict()` (the same way `self._loops`/`self._history`
  are asserted).
- New: `scripts/tests/test_cli_queue.py` for `cmd_add`/`cmd_list`/
  `cmd_status`/`cmd_remove` CLI coverage — named distinctly from the
  existing `test_cli_loop_queue.py`, which covers the unrelated FSM
  lock-queue subsystem (`little_loops.cli.loop.queue`), to avoid
  confusion between the two queue mechanisms during the transition period.

## Acceptance Criteria

- `ll-queue add` accepts all three work-item kinds (FSM loop,
  skill/command/prompt, raw CLI invocation) and persists real entries
  matching the schema above.
- `ll-queue list`/`status`/`remove` operate on real persisted entries —
  no PID-liveness inference.
- Priority ordering matches `IssuePriorityQueue`'s tiered
  `(priority, timestamp)` model, with a test proving FIFO-within-tier.
- New test module covers persistence, ordering, and `add`
  normalization (all three `ActionSpec` kinds).
- `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Foundational child of EPIC-2670; blocks FEAT-2683
  (worker loop) and FEAT-2684 (compat shim), but has no direct end-user
  facing impact on its own.
- **Effort**: Medium - New sqlite store modeled directly on
  `session_store.py`'s migration pattern, new CLI module modeled on
  `cli/learning_tests.py`, plus four `BRConfig` wiring touch-points.
- **Risk**: Low - Purely additive (new `.ll/queue.db`, new `ll-queue`
  binary); does not modify the existing `ll-loop queue` PID-marker
  mechanism, which FEAT-2684 migrates separately.
- **Breaking Change**: No

## Scope Boundaries

- **In**: queue persistence schema/storage, `add`/`list`/`status`/
  `remove` commands, priority ordering, config namespace.
- **Out**: the dequeue-and-execute worker loop (`ll-queue run`) — that's
  FEAT-2683, which consumes this child's persistence layer. The
  `ll-loop run --queue` compat shim and `ll-loop queue` migration — that's
  FEAT-2684.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| FEAT-2669 | Parent issue — full design context and resolved open questions |
| `thoughts/plans/2026-07-17-generic-ll-queue-design.md` | Source design doc |
| ENH-2668 | `RunnerType`/`ActionSpec`/`run_action()` — normalization target for `add` |

## Session Log
- `/ll:manage-issue` - 2026-07-18T21:50:29Z - `f5149286-4d10-4f85-879a-86840628af63.jsonl`
- `/ll:ready-issue` - 2026-07-18T21:23:11 - `c589fd87-81d8-47a3-82ad-70a6bc68a020.jsonl`
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `a8293915-a151-42a8-922a-8c3f0537584d.jsonl`
- `/ll:wire-issue` - 2026-07-18T21:18:15 - `e8edafc3-4777-464b-99ef-efa1fab0b9c1.jsonl`
- `/ll:refine-issue` - 2026-07-18T21:11:19 - `ea9a2eb6-06f2-47db-8e5b-70af3dfc6567.jsonl`
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `000582b3-d456-48ac-97b3-fcefbd8047d4.jsonl`

---

## Status

**Open** | Created: 2026-07-18 | Priority: P2
