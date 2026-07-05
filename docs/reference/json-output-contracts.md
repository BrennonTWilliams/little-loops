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
  instance (without the diagnostic fields above).

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
| `pid` | integer | no | OS PID of the running process (omitted when not available) |

> **Note (BUG-2485):** the loop's full `fsm.context` (positional `input`,
> `program.md` fields, `--context` values) is persisted to the on-disk
> `.state.json` for resume, but is **intentionally omitted from this CLI JSON
> contract**. `LoopState.to_dict()` emits it only on the persistence path
> (`include_context=True`), never in `ll-loop status`/`list --json`.

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
| `discovered_date` | string or null | yes | ISO 8601 date the issue was captured (null if not set) |
| `parent` | string or null | yes | Parent epic ID (null if not set) |
| `labels` | array of strings | yes | Labels from the issue frontmatter |
| `milestone` | string or null | yes | Milestone tag (null if not set) |
| `summary` | string | no | Plain text of the `## Summary` section body; only present when `--include-summary` is passed (empty string `""` if the section is absent) |
