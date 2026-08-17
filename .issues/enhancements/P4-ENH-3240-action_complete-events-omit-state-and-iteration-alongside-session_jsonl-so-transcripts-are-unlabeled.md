---
id: ENH-3240
type: ENH
title: action_complete events omit state and iteration alongside session_jsonl so
  transcripts are unlabeled
priority: P4
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T18:23:48Z'
---

# ENH-3240: action_complete events omit state and iteration alongside session_jsonl so transcripts are unlabeled

## Summary

`action_complete` events in a run's `events.jsonl` record `session_jsonl` — the host session
transcript for that action — but omit the `state` and `iteration` fields the same run's
`usage.jsonl` records at identical timestamps. The pointers are therefore present but unlabeled:
recovering "which transcript was `verify_issue`" requires a timestamp join against a second file,
or opening each transcript to identify it.

## Current Behavior

For run `.loops/.history/2026-08-17T170259-refine-to-ready-issue`, every event carrying a
`session_jsonl` looks like this — four fields, none of which name the state:

```
{'event': 'action_complete', 'ts': '2026-08-17T17:09:30.536676+00:00'}
{'event': 'action_complete', 'ts': '2026-08-17T17:15:53.232580+00:00'}
{'event': 'action_complete', 'ts': '2026-08-17T17:17:54.464016+00:00'}
{'event': 'action_complete', 'ts': '2026-08-17T17:19:27.383191+00:00'}
```

(printed filtering to `event`/`type`/`state`/`iteration`/`action`/`ts`; `state`, `iteration` and
`action` are absent, not null-valued)

The pointers themselves are correct — they resolve to the four prompt-state transcripts:

```
0d1d5748-…  (refine_issue)
874f81b5-…  (wire_issue)
038b6ab4-…  (verify_issue)
83adf706-…  (confidence_check)
```

The run's `usage.jsonl` records `state` and `iteration` for those same four moments, at
byte-identical timestamps:

```json
{"iteration": 10, "state": "verify_issue", "action_type": "prompt", ...,
 "timestamp": "2026-08-17T17:17:54.464016+00:00"}
```

So the attribution is fully recoverable — by joining two files on `ts` — but is not directly
readable from the event that names the transcript.

The `events.jsonl` schema does carry `state` on other event types; the observed key set across
the file includes `state`, `iteration`, `from`, `to`, `verdict`, `session_jsonl`, and others. It
is specifically the `session_jsonl`-bearing `action_complete` event that lacks it.

## Expected Behavior

An `action_complete` event that records `session_jsonl` also records the `state` and
`iteration` that produced it, so a run's per-state transcripts can be attributed to their
states by reading `events.jsonl` alone — no timestamp join against `usage.jsonl`, and no
opening each transcript to identify it.

## Motivation

Reconstructing why a loop reached a given verdict is the core diagnostic task behind
`/ll:debug-loop-run` and `/ll:audit-loop-run`, and it starts with reading the right transcript.
The run already records exactly the pointer needed; withholding the state name turns a direct
lookup into a two-file join that a reader has to know about. The fix is additive and touches one
event payload.

## Integration Map

_Added by pre-implementation review — 2026-08-17 — verified against the working tree._

### Files to Modify

- `scripts/little_loops/fsm/executor.py` (`:2304-2337`) — the emit site. The `payload` dict is
  built at `:2304`; `self._emit("action_complete", payload)` fires at `:2337`. **Both values
  are already in scope**: `self.current_state` is used ten lines below at `:2333`
  (`self._usage_events_collected.append((self.current_state, usage))`), and `self.iteration`
  is an executor attribute initialized at `:253` and incremented at `:604`/`:664`/`:2815`.
  Other events already emit it under the key `"iteration"` (`:670`, `:2821`) — match that key
  exactly rather than inventing a variant.
- `scripts/little_loops/generate_schemas.py` (`:136-159`) —
  `SCHEMA_DEFINITIONS["action_complete"]` is the wire-format contract. Add `state` and
  `iteration` properties. **Keep them out of the `required` list** (currently
  `["exit_code", "duration_ms", "is_prompt"]`) — the second emitter below cannot supply them.
  Regenerate `docs/reference/schemas/` via `ll-generate-schemas`.
- `scripts/little_loops/observability/schema.py` (`:267-273`) — `ActionCompleteVariant`
  (frozen dataclass, currently carries `exit_code` / `duration_ms`). Add the two fields with
  defaults, matching the `EvaluateVariant` shape at `:290-296`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/audit.py` (`:177-215`) — **the consumer this obsoletes.**
  `audit_run()`'s docstring at `:181-184` asserts *"the `state_enter`-tracking correlation
  technique ... to attribute `action_complete`/`evaluate` events to the state active when
  they fired (neither event type carries its own `state` field)"* — false once this lands.
  It tracks `current_state` from `state_enter` at `:207-210` and applies it to
  `action_complete` at `:211-215`. Either update the docstring or read the direct field with
  the correlation retained as fallback (see the archived-run AC below).
- `scripts/little_loops/analytics/variance.py` (`_correlate_verdicts`) — the technique
  `audit.py:181` cites as its precedent; same correlation, same staleness question.
- `scripts/little_loops/cli/action.py` (`:255`) — **a second, independent `action_complete`
  emitter**, from `ll-action` outside any FSM. It has no state, no iteration, and emits no
  `session_jsonl`, so it is out of scope (see Scope Boundaries) — but it is the reason the new
  schema fields must be optional rather than required.
- `scripts/little_loops/cli/loop/info.py` (`:800-818`) — renders `action_complete` for
  `ll-loop history`, and already special-cases `session_jsonl` at `:811-813`. The natural
  place to *display* the state next to the transcript path; optional, not required by the ACs.
- `scripts/little_loops/transport.py` (`:405-406`, `_handle_action_complete()` at `:456`) and
  `scripts/little_loops/fsm/persistence.py` (`:777`, `usage.jsonl` writer) — additive-field
  consumers; listed to confirm no change is needed, per the "existing readers tolerate" AC.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` (`:1092`, live-run display renderer's
  `elif event_type == "action_complete":` branch; also `:1766-1781`,
  `_capture_failure()`) — a second and third CLI-side reader of the
  `action_complete` payload beyond `cli/loop/info.py`. Additive-field-tolerant,
  no change required, but the issue's Integration Map did not name them.
  [Agent finding]

### Similar Patterns

- `state_enter` (`generate_schemas.py:91`) already carries `state` as a first-class payload
  field — the shape being extended to `action_complete`, not a new convention.
- `fsm/executor.py:670` and `:2821` emit `"iteration"` in other payloads; the key name and
  integer type are settled precedent.

### Tests

- `scripts/tests/test_generate_schemas.py` — catalog-completeness over `SCHEMA_DEFINITIONS`
  (the precedent `test_des_schema.py:7` cites); asserts generated schema files.
- `scripts/tests/test_des_schema.py` (`:27-55`) — `TestSchemaDefinitions` gates
  `DES_VARIANTS` against `SCHEMA_DEFINITIONS`; both must stay in lockstep, so a change to one
  without the other fails here.
- New test for the emit site: assert a prompt-state `action_complete` names its state and
  iteration, and that they match the `usage.jsonl` record at the same timestamp.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_audit.py::TestAuditRun` — the module-level `_EVENTS`
  fixture (`:37-49`) and `test_counters_match_events` (`:78`) already exercise the
  pre-change shape (`action_complete` with no `state` key), attributed purely via
  `state_enter` correlation. This is the archived-run fallback regression case and
  must keep passing unchanged; add a **second** fixture where `action_complete`
  carries a direct `state` key to test the new direct-read path. [Agent finding]
- `scripts/tests/test_generate_schemas.py::TestSchemaDefinitions.test_action_complete_schema`
  (`:154-171`) — needs `assert "state" in props` / `assert "iteration" in props`
  added, mirroring `test_state_enter_schema` (`:145-152`). [Agent finding]
- `scripts/tests/test_fsm_executor.py::TestStderrPreview._run_and_collect()`
  (`:10592`) and `TestObservedEffortFromSessionJsonl._run_and_collect()`
  (`:10659`) — the harness pattern (build FSM, run, filter events by type) to
  follow for the new emit-site test. `TestMaxIterations.test_state_enter_includes_iteration_count`
  (`~:10463`) shows the exact `all(key in e for e in filtered)` idiom for
  asserting a field is present on every event of a type. [Agent finding]

### Documentation

- `docs/reference/schemas/action_complete.json` — generated output, regenerate rather
  than hand-edit.
- `cli/loop/audit.py:177-186` docstring — see Dependent Files; it makes a factual claim this
  change falsifies.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` (`### action_complete`, `:202-248`) — the
  **hand-maintained** canonical field-table doc, distinct from the auto-regenerated
  `docs/reference/schemas/action_complete.json`. `ll-generate-schemas` does not
  touch this file, so it needs a manual field-table row and JSON-example update
  (examples at `:221-230`, `:233-248` currently show no `state`/`iteration` keys).
  [Agent finding]
- `skills/debug-loop-run/SKILL.md` (`:42`, `:140-151`) and
  `skills/debug-loop-run/reference.md` (`:17`, `:42-43`) — documents the
  `state_enter`-correlation technique as an analysis rule independent of
  `audit.py`; the event-field table at `reference.md:17` omits `state`/`iteration`.
  [Agent finding]
- `skills/audit-loop-run/SKILL.md` (`:144`, `:181-183`, `:207-216`) — same
  correlation technique, documented independently. [Agent finding]
- `skills/distill-traces/SKILL.md` (`:73`) — a third independent
  `state_enter`/`action_complete` adjacency-correlation implementation. [Agent finding]
- `docs/generalized-fsm-loop.md` (`:1711-1724`) — illustrative sample event stream
  showing `action_complete` lines without the new fields; lower priority, visual
  only. [Agent finding]

### Configuration
- N/A — no config surface.

## Implementation Steps

1. Add `state` (`self.current_state`) and `iteration` (`self.iteration`) to the
   `action_complete` payload in `fsm/executor.py:2304-2337`, before the `_emit` at `:2337`.
2. Extend `SCHEMA_DEFINITIONS["action_complete"]` (`generate_schemas.py:136-159`) with both
   properties, **not** added to `required`; regenerate `docs/reference/schemas/`.
3. Add the matching fields to `ActionCompleteVariant` (`observability/schema.py:267-273`) so
   `test_des_schema.py`'s lockstep gate stays green.
4. Update `cli/loop/audit.py`'s docstring (`:181-184`) and decide whether `audit_run()` reads
   the direct field; if it does, keep the `state_enter` correlation as the fallback path for
   archived runs.
5. Verify: new test asserting a prompt-state action's `action_complete` names its state and
   iteration and agrees with `usage.jsonl`; then `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/EVENT-SCHEMA.md` — manually add `state`/`iteration` to
  the `### action_complete` field table and both JSON examples; not covered by
  `ll-generate-schemas`.
- Update `skills/debug-loop-run/reference.md` — add `state`/`iteration` to the
  `action_complete` event-field table (`:17`).
- Update `skills/debug-loop-run/SKILL.md`, `skills/audit-loop-run/SKILL.md`, and
  `skills/distill-traces/SKILL.md` — note the direct `state` field as the
  preferred read, retaining the `state_enter`-correlation description as the
  fallback for archived runs.
- Add `scripts/tests/test_cli_loop_audit.py::TestAuditRun` coverage for the new
  direct-`state`-field read path, keeping the existing `_EVENTS`-based test as
  the archived-run fallback regression.
- Extend `scripts/tests/test_generate_schemas.py::test_action_complete_schema`
  with `state`/`iteration` presence assertions.

## Impact

Low severity, purely diagnostic friction. It surfaces when reconstructing why a loop reached a
particular verdict — the exact task ENH-3238's investigation required. Without knowing the
`ts`-join trick, the fallback is grepping every session JSONL in
`~/.claude/projects/<project>/` for the state's slash-command text (~25 files for a single day's
runs) to identify four transcripts the run had already recorded.

No data is lost and no behavior is wrong; the information is one join away.

## Proposed Solution

Add `state` (and `iteration`, for consistency with `usage.jsonl`) to the `action_complete` event
payload at the site where `session_jsonl` is written. Both values are in scope at emission time —
`usage.jsonl` is written from the same point with the same timestamp.

## Program Design

_Added by pre-implementation review — 2026-08-17._

### Types

No new types. Two optional fields are added to an existing payload:

- `state: str` — the FSM state whose action produced the transcript. Same value and same key
  name `state_enter` already carries (`generate_schemas.py:91`).
- `iteration: int` — the executor's step counter. Same key name already emitted at
  `fsm/executor.py:670` and `:2821`.

Both are **optional** in the schema, not required. `SCHEMA_DEFINITIONS["action_complete"]`
currently requires `["exit_code", "duration_ms", "is_prompt"]` (`generate_schemas.py:158`) and
must keep exactly that list — the `cli/action.py:255` emitter has neither value to supply.

### Signatures

- `FSMExecutor._emit(self, event: str, data: dict[str, Any]) -> None`
  (`fsm/executor.py:3306`) — unchanged; only the `payload` dict passed at `:2337` grows.
- `audit_run(run_dir: Path, max_steps: int | None = None) -> RunAuditStats`
  (`cli/loop/audit.py:178`) — signature unchanged; its state-attribution body and its
  docstring's factual claim both change.

### Call Path

Emission: `FSMExecutor._run_action()` builds `payload` (`fsm/executor.py:2304`) → adds
`session_jsonl` in the `action_mode == "prompt"` branch (`:2311-2313`) → **adds `state` from
`self.current_state` and `iteration` from `self.iteration`** → `self._emit("action_complete",
payload)` (`:2337`) → transports (`transport.py:405`) → `.loops/.history/<run>/events.jsonl`.

Consumption: `audit_run()` (`cli/loop/audit.py:178`) reads events, tracks `current_state` from
`state_enter` (`:207-210`), and applies it to `action_complete` (`:211-215`). After this
change it prefers `event.get("state")` and falls back to the tracked value when the key is
absent.

### Why the fallback is not optional

`self.current_state` and `self.iteration` are both already in scope at the emit site —
`current_state` is used ten lines below at `:2333` — so the emission half is genuinely a
two-line change. The consumption half is not, because **every run already archived under
`.loops/.history/` was written without these fields**. A consumer that switches to the direct
read unconditionally silently misattributes every historical run to `None`. The
`state_enter` correlation must therefore be retained as a fallback rather than deleted, and
`audit.py`'s docstring updated to describe it as the compatibility path rather than the only
path.

## Scope Boundaries

**In scope**: adding `state` and `iteration` to the `action_complete` event payload that already
carries `session_jsonl`.

**Out of scope**: the split whereby `.loops/runs/<run>/` holds marker files and `usage.jsonl`
while `.loops/.history/<run>/` holds `events.jsonl` and `state.json`. That is existing design;
consolidating the two locations is a separate question and should not be folded in here.

**Out of scope**: any change to what is written to the host session transcripts themselves, or
to their retention.

**Out of scope** (added by the 2026-08-17 review): the second `action_complete` emitter at
`cli/action.py:255`. `ll-action` emits the same event type from outside any FSM — it has no
state, no iteration, and no `session_jsonl`, so there is nothing to label. It is named here
because it constrains the fix: the new schema properties must be **optional**, or this
emitter's payload becomes schema-invalid.

## Acceptance Criteria

- [ ] `action_complete` events carrying `session_jsonl` also carry `state` and `iteration`.
- [ ] The values match the corresponding `usage.jsonl` record for the same timestamp.
- [ ] Existing `events.jsonl` readers tolerate the added fields (additive change only; no
      existing field renamed or removed).
- [ ] A test asserts that a prompt-state action's `action_complete` event names its state.
- [ ] The new `state` / `iteration` properties are declared in
      `SCHEMA_DEFINITIONS["action_complete"]` (`generate_schemas.py:136-159`) and on
      `ActionCompleteVariant` (`observability/schema.py:267-273`), and
      `docs/reference/schemas/` is regenerated. Both are **optional, not `required`** — the
      `cli/action.py:255` emitter cannot supply them and must remain schema-valid.
- [ ] Archived runs keep working: every run already under `.loops/.history/` was written
      without these fields, so any consumer switched to the direct read must fall back to the
      existing `state_enter` correlation when `state` is absent. A test covers an event with
      no `state` key resolving to the correct state via the fallback.
- [ ] `cli/loop/audit.py`'s `audit_run()` docstring (`:181-184`) no longer asserts that
      `action_complete` carries no `state` field — it is the claim this change falsifies.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found while investigating ENH-3238; the initial assumption that run artifacts carried *no*
transcript pointer was wrong — `session_jsonl` is recorded, and correctly. This issue is only
about labeling it.

Note that the per-run directory under `.loops/runs/<run>/` holds only marker files and
`usage.jsonl`; the `session_jsonl` pointers live in `.loops/.history/<run>/events.jsonl`. That
split is existing design and not in scope here.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-08-17T21:49:12 - `0510d699-a148-43d1-84c2-d05ff33b93f2.jsonl`
- `/ll:format-issue` - 2026-08-17T21:42:04 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:capture-issue` - 2026-08-17T18:23:57 - `66dab8b6-e923-43d4-9f0e-eccb97176e0f.jsonl`
