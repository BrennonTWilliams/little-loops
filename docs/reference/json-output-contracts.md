# JSON Output Contracts

This document defines the stable JSON output shapes for the `--json` flag on
the three CLI surfaces consumed by Hermes (`ll_status`, `ll_portfolio`) and
other machine-readable callers.

## Stability policy

- **Non-breaking** (no announcement required): adding new optional keys to an object.
- **Breaking** (requires migration note in CHANGELOG and version bump): removing a key,
  renaming a key, or changing the type of an existing key.

Callers should tolerate unknown keys (additive fields) and treat all non-documented keys
as unstable.

---

## `ll-loop list --json`

Returns a JSON array. Each element describes one available loop.

```json
[
  {
    "name": "fix-quality-and-tests",
    "path": ".loops/fix-quality-and-tests.yaml",
    "category": "quality",
    "labels": ["hermes"],
    "visibility": "public",
    "description": "Fix failing tests and lint errors.",
    "built_in": true
  }
]
```

### Field reference

| Field | Type | Always present | Description |
|---|---|---|---|
| `name` | string | yes | Relative loop identifier accepted by `ll-loop run <name>` |
| `path` | string | yes | Absolute or relative path to the loop YAML file |
| `category` | string | yes | Category tag from the loop YAML (empty string if omitted) |
| `labels` | array of strings | yes | Label tags from the loop YAML |
| `visibility` | string | yes | Visibility tier: `"public"`, `"internal"`, or `"example"` |
| `description` | string | yes | First-line description from the loop YAML (empty string if omitted) |
| `built_in` | boolean | no | Present and `true` only for bundled (built-in) loops |

Default listing (no `--visibility` flag) returns only `"public"` loops. Pass
`--visibility all` to receive all tiers. Pass `--visibility internal` or
`--visibility example` to filter to those tiers.

---

## `ll-loop status --json`

Returns the state of one or more instances of the named loop. The shape depends
on the number of instances found:

- **One instance**: returns a JSON object for that instance (plus `pid`,
  `pid_source`, `log_file`, `log_updated_ago`, `last_event`, and `events_file`
  diagnostic fields that are not in the base contract).
- **Multiple instances**: returns a JSON array of state objects, one per
  instance. Each entry additionally includes an `instance_id` field plus the
  `pid`, `pid_source`, `log_file`, `log_updated_ago`, and `events_file`
  diagnostic fields; `last_event` is only present in the single-instance case.

Each state object corresponds to one active or interrupted loop instance.

```json
{
  "loop_name": "rn-implement",
  "current_state": "run_remediation",
  "iteration": 4,
  "captured": {},
  "prev_result": null,
  "last_result": null,
  "started_at": "2026-06-16T12:00:00+00:00",
  "updated_at": "2026-06-16T12:05:00+00:00",
  "status": "running",
  "accumulated_ms": 300000
}
```

### Field reference

| Field | Type | Always present | Description |
|---|---|---|---|
| `loop_name` | string | yes | Name of the loop |
| `current_state` | string | yes | FSM state the loop is currently in |
| `iteration` | integer | yes | Current iteration count (1-based) |
| `captured` | object | yes | Map of captured variable names to their last output records |
| `prev_result` | object or null | yes | Previous state's action result (output, exit_code, state) |
| `last_result` | object or null | yes | Last evaluation verdict and details |
| `started_at` | string (ISO 8601) | yes | Timestamp when the loop started |
| `updated_at` | string (ISO 8601) | yes | Timestamp when the state was last persisted |
| `status` | string | yes | Execution status: `"running"`, `"completed"`, `"failed"`, `"interrupted"`, `"awaiting_continuation"`, `"timed_out"` |
| `accumulated_ms` | integer | yes | Total elapsed milliseconds across all segments |
| `continuation_prompt` | string | no | Continuation context (only when `status` is `"awaiting_continuation"`) |
| `retry_counts` | object | no | Per-state retry counts (omitted when all zero) |
| `rate_limit_retries` | object | no | Per-state rate-limit retry counts (omitted when empty) |
| `consecutive_rate_limit_exhaustions` | integer | no | Running count of back-to-back `rate_limit_exhausted` events, used for storm detection (omitted when zero) |
| `edge_revisit_counts` | object | no | Per-edge (`from->to`) traversal counts backing cycle detection (omitted when empty) |
| `iteration_count` | integer | no | Full-pass (maintain-mode) restart count, distinct from `iteration` (omitted when zero) |
| `active_sub_loop` | object or string | no | Descriptor of the sub-loop currently executing (omitted when the loop is not inside one) |
| `reconciled_at` | string (ISO 8601) | no | Timestamp of the last reconciliation pass against on-disk truth (omitted when never reconciled) |
| `messages` | array of strings | no | Shared append-only message log surfaced to interpolation as `${messages}` (omitted when empty) |
| `pid` | integer or null | no | OS PID of the running process. In `ll-loop status --json` output this key is always present, emitted as `null` when not available; the raw `LoopState.to_dict()` contract omits the key entirely when unavailable |

All rows marked "no" above are emitted by `LoopState.to_dict()` only when the
underlying value is non-empty / non-`None` — an absent key means "zero, empty, or
never set", never "unknown". Consumers should default rather than require them.

> **Note (BUG-2485):** the loop's full `fsm.context` (positional `input`,
> `program.md` fields, `--context` values) is persisted to the on-disk
> `.state.json` for resume, but is **intentionally omitted from this CLI JSON
> contract**. `LoopState.to_dict()` emits it only on the persistence path
> (`include_context=True`), never in `ll-loop status`/`list --json`.

### Alternate entry point: `ll-loop list --running --json`

`ll-loop list --running --json`, `ll-loop list --all-runs --json`, and
`ll-loop list --status <status> --json` all return a JSON array of the **same
base state objects** — but none of the diagnostic fields. It is a plain
`[state.to_dict() for state in states]`, so `pid_source`, `log_file`,
`log_updated_ago`, `last_event`, `events_file`, and `instance_id` are all
absent; `pid` appears only when the persisted state itself carries one
(unlike `status --json`, which always emits the key, `null` included).

**Status filtering (BUG-3232):** `--running` alone applies a `{running,
starting}` allowlist — only dispatches genuinely executing right now.
`--all-runs` returns every state with saved state regardless of status
(`completed`, `failed`, `interrupted`, `user_stopped`, `awaiting_continuation`,
etc. — this was `--running`'s behavior before the fix). An explicit `--status
<value>` selects exactly that status and overrides the `--running` allowlist
if both are given (e.g. `--running --status interrupted` still returns the
`interrupted` entries).

Use `ll-loop status --json` when you need process/log diagnostics, and
`ll-loop list --json` when you only need the loop-state contract across many
loops.

---

## `ll-issues list --json`

Returns a JSON array. Each element describes one issue file.

```json
[
  {
    "id": "ENH-2197",
    "priority": "P2",
    "type": "ENH",
    "title": "Add `ll-loop run --model` host-action passthrough flag",
    "path": "/path/to/.issues/enhancements/P2-ENH-2197-ll-loop-run-model-host-action-passthrough.md",
    "status": "open",
    "discovered_date": null,
    "completed_at": null,
    "parent": "EPIC-2196",
    "labels": [],
    "milestone": null
  }
]
```

### Field reference

| Field | Type | Always present | Description |
|---|---|---|---|
| `id` | string | yes | Issue ID (e.g. `"ENH-2197"`) |
| `priority` | string | yes | Priority tier: `"P0"` through `"P5"` |
| `type` | string | yes | Issue type: `"BUG"`, `"ENH"`, `"FEAT"`, or `"EPIC"` |
| `title` | string | yes | Issue title from the markdown heading |
| `path` | string | yes | Absolute path to the issue file |
| `status` | string | yes | Issue status: `"open"`, `"in_progress"`, `"blocked"`, `"deferred"`, `"done"`, `"cancelled"` |
| `discovered_date` | string or null | yes | `YYYY-MM-DD` date the issue was captured (null if not set). Only computed when `--sort created` is passed; on a plain `ll-issues list --json` call this field is always `null` |
| `completed_at` | string or null | yes | `YYYY-MM-DD` completion date, resolved from the `completed_at` frontmatter or a `**Completed/Fixed/Closed**:` resolution line (null for non-done issues or when no completion date is recorded). Day-granularity; consumed by `/ll:manage-release` to select issues completed since the last tag |
| `parent` | string or null | yes | Parent epic ID (null if not set) |
| `labels` | array of strings | yes | Labels from the issue frontmatter |
| `milestone` | string or null | yes | Milestone tag (null if not set) |
| `summary` | string | no | Plain text of the `## Summary` section body; only present when `--include-summary` is passed (empty string `""` if the section is absent) |
