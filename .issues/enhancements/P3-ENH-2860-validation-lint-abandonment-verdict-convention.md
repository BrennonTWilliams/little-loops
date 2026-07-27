---
id: ENH-2860
status: open
priority: P3
captured_at: "2026-07-27T16:17:56Z"
discovered_date: 2026-07-27
discovered_by: capture-issue
labels: [fsm, validation, loops]
parent: EPIC-2861
relates_to: [ENH-2857]
blocked_by: [ENH-2857]
---

# ENH-2860: validation lint — abandonment must reach summary.json and downgrade the verdict (MR-13)

## Summary

Two builtin loops now independently need the convention "abandonment must reach
summary.json and downgrade the verdict": `auto-refine-and-implement.yaml` implements it
(ENH-2657: `abandoned` field + `incomplete-abandoned` verdict taking precedence over
closed>0) and `general-task.yaml` is getting it via ENH-2857. The general-task
postmortem showed what happens without it: a hardcoded `"verdict":"success"` over 8
abandoned-of-34 steps, invisible to all audit tooling. Shift this check left into
`fsm/validation.py` as a new MR-13-style WARN, same as MR-1..12 did for their failure
taxonomy.

## Current Behavior

Nothing in `ll-loop validate` notices a loop that caps per-step/per-item attempts and
rewrites plan/queue entries as abandoned, but whose summary-emitting state prints a
verdict JSON with no `abandoned` field — the exact shape that let general-task launder
8 abandoned steps into `success`.

## Expected Behavior

New WARN in `scripts/little_loops/fsm/validation.py` (suppress flag e.g.
`abandonment_verdict_ok`): fires when a loop has an abandonment mechanism — heuristics:
a shell action rewriting `- [ ]` checkbox lines while inserting an "abandoned"
annotation **or rewriting them to the `- [!]` abandonment marker** (the heuristic must
match both the old laundering shape — `[x]` + abandoned note — and the post-ENH-2857
`[!]` convention, otherwise the lint won't recognize general-task as having an
abandonment mechanism at all and the "all builtin loops pass" criterion below would be
satisfied vacuously rather than by the carve-out working), or an attempt-cap counter
pattern (`max_step_attempts`-style context var consumed in a shell action) — but no
state whose action emits an `"abandoned"` key in a summary JSON `printf`/write. Additionally flag a shell action containing a literal
hardcoded `"verdict":"success"` (or `verdict=success`) — but **only when the emitting
action has no conditional branch on an abandonment/failure counter and emits no
`"abandoned"` key in the same state**. This carve-out is load-bearing: after ENH-2857,
`general-task.yaml`'s success path will still contain a literal `"verdict":"success"`
printf on its zero-abandoned branch, and `write_partial_summary` will branch between
literal `"partial"` and `"incomplete-abandoned"` strings on its own abandoned-count
check (ENH-2857 gives the partial path the same verdict precedence, so do not assume
that state emits an unconditional `"partial"`). A naive literal-match lint would warn
on the very builtin this epic fixes, contradicting the "all builtin loops pass"
criterion below. A literal verdict string guarded by a counter branch is the *correct*
shape, not the defect.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `_validate_abandonment_verdict` (or similar), module-level regex constants, register in `validate_fsm()` chain, add flag to `KNOWN_TOP_LEVEL_KEYS`
- `scripts/little_loops/fsm/schema.py` — add `abandonment_verdict_ok: bool = False` field + `to_dict()`/`from_dict()` wiring (~lines 1276-1510, alongside `parse_swallow_ok`)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add a top-level boolean `abandonment_verdict_ok` property, mirroring the `terminal_action_ok` entry (~lines 363-367); the standalone JSON Schema file is a separate coupling from the `FSMLoop` dataclass and is missed if only `schema.py` is updated _(`/ll:wire-issue` finding)_
- `.claude/CLAUDE.md` — add MR-13 row to Loop Authoring rule table
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — add MR-13 to the MR rule table (~lines 85-107) and summary lines (~311, ~324)

### Reference Implementations (Loops)
- `scripts/little_loops/loops/general-task.yaml` — defect-shape target: `max_step_attempts` (line 22), `select_step` abandonment rewrite (lines 155-199), `summarize_success` hardcoded `"verdict":"success"` with no `abandoned` key (lines 542-582), `write_partial_summary` (lines 683-728)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — correct-shape reference: `$P-abandoned.txt` marker + count (~lines 805-815), `VERDICT=incomplete-abandoned` precedence (~932-938), summary emission with `"abandoned"` key + interpolated `"verdict"` (~955-961)

### Tests
- `scripts/tests/test_fsm_validation.py` — `TestParseSwallow` (lines 4210-4341) is the direct template class; `BUILTIN_LOOPS_DIR` (line 1085) and `TestMetaLoopValidation.test_harness_optimize_passes_clean` (1107-1117) template the "all builtin loops pass" assertion
- `scripts/tests/test_fsm_flow.py` — `TestBuiltinLoopRegression.test_all_builtin_loops_still_load` (324-331), general builtin-loop-loads-cleanly gate
- `scripts/tests/test_fsm_schema.py` — round-trip test class for `abandonment_verdict_ok` (true round-trips through `to_dict()`/`from_dict()`, false is omitted from `to_dict()`, default is False when absent), modeled on the `terminal_action_ok` round-trip tests (~lines 4082-4116); the schema.py dataclass field needs its own serialization test, distinct from the validation-rule tests _(`/ll:wire-issue` finding)_
- `scripts/tests/test_ll_loop_commands.py` — e2e test exercising `ll-loop validate` plain-text and `--json` output surfacing the MR-13 warning, modeled on `test_validate_no_json_still_warns_mr12_check3_under_config_sdk` (line 251) / `test_validate_json_still_warns_mr12_check3_under_config_cli` (line 294) _(`/ll:wire-issue` finding)_
- Note: `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_all_validate_as_valid_fsm` only asserts ERROR-severity is empty, so a new WARN-severity MR-13 finding won't break it — but nothing currently asserts `general-task.yaml`/`auto-refine-and-implement.yaml` are MR-13-clean; the acceptance criterion "all builtin loops pass" needs an explicit new assertion, not reliance on this existing test _(`/ll:wire-issue` finding)_

### Blocking/Related Issues
- `.issues/enhancements/P2-ENH-2857-...` — general-task abandonment visibility fix this lint validates (blocked_by)
- `.issues/enhancements/P2-ENH-2657-...` (done) — precedent implementation in auto-refine-and-implement

## Motivation

Same rationale as the MR-1..12 family: two independent recurrences of a defect class in
builtin loops justify a validator gate so third-party/meta loops don't reinvent the bug.

## Implementation Steps

1. Grep `loops/` for literal `"verdict":"success"` to scope the hardcode check and
   establish the allowlist/fix set (general-task is fixed by ENH-2857).
2. Add the lint + suppress flag to `fsm/validation.py`, register in the CLAUDE.md
   Loop Authoring rule table and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.
3. Tests in the validation test module (positive fixture, suppressed fixture, and
   assert all builtin loops pass).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Add a top-level boolean `abandonment_verdict_ok` property to
   `scripts/little_loops/fsm/fsm-loop-schema.json` (mirrors `terminal_action_ok`).
5. Add a round-trip serialization test for `abandonment_verdict_ok` in
   `scripts/tests/test_fsm_schema.py`.
6. Add an e2e test in `scripts/tests/test_ll_loop_commands.py` exercising
   `ll-loop validate` plain and `--json` output for MR-13.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Rule-function template to follow**: `_validate_parse_swallow` (MR-10,
`scripts/little_loops/fsm/validation.py:2094`) is the closest structural analog —
it composes multiple independent module-level regexes with AND logic plus an
absence condition (`state.on_error is None`), gated by an early
`if fsm.parse_swallow_ok: return []`. MR-13 needs the same shape but with two
compound conditions (mechanism-without-abandoned-key, and
hardcode-without-guard), likely as two loops in one function or two sibling
functions sharing one suppress flag (e.g. `abandonment_verdict_ok`).

**Suppress-flag wiring (3 touch points + 1 registration)**:
- `FSMLoop` dataclass field in `scripts/little_loops/fsm/schema.py` (~line 1276,
  next to `parse_swallow_ok: bool = False`)
- `to_dict()` conditional serialization (`schema.py` ~1388-1407)
- `from_dict()` deserialization (`schema.py` ~1501-1510)
- `KNOWN_TOP_LEVEL_KEYS` frozenset in `validation.py:214-268` (must add the new
  flag name or authors get a spurious "Unknown top-level key" warning)
- Call-site registration: `errors.extend(_validate_<name>(fsm))` added to the
  sequential chain inside `validate_fsm()` (`validation.py:1350-1399`, near the
  MR-10 call at ~1372)

**general-task.yaml abandonment mechanism (actual states/lines)**:
- `max_step_attempts: 3` top-level param (line 22)
- `select_step` state (lines 155-199): when `PRIOR -ge max_step_attempts`, `awk`
  rewrites `- [ ]` → `- [x]` and appends `"  (abandoned: verify failed after $n
  attempts)"` (line 178) — the old laundering shape (not yet the `[!]` marker;
  ENH-2857 is expected to change this to `- [!]`)
- `summarize_success` state (lines 542-582): `printf` at lines 578-579 emits
  `{"verdict":"success",...}` — a hardcoded literal with **no** conditional
  branch and **no** `"abandoned"` key. This is the exact defect shape the
  postmortem found (8-of-34 abandoned steps laundered into `success`).
- `write_partial_summary` state (lines 683-728): its `printf` (718-719) also
  has no `"abandoned"` key today; post-ENH-2857 it's expected to branch between
  literal `"partial"` and `"incomplete-abandoned"` on an abandoned-count check —
  this guarded-literal shape is correct and must NOT be flagged.

**auto-refine-and-implement.yaml — the "good" comparison case** (ENH-2657,
already implements the target convention):
- Per-issue marker file `$RUN_DIR/$P-abandoned.txt` created/appended (lines
  ~805-815), counted via `ABANDONED=$(count $P-abandoned.txt)`
- `VERDICT=incomplete-abandoned` assigned when `ABANDONED -gt 0` takes
  precedence over other buckets (lines ~932-938, comment cites ENH-2657)
- Final `printf` (~955-961) emits `"abandoned":%s` as a first-class key
  alongside an *interpolated* `"verdict":"%s"` (not a bare literal) — this is
  the reference shape for what "reaches summary.json" should look like.

**Test template**: `TestParseSwallow` class in
`scripts/tests/test_fsm_validation.py:4210-4341` — covers positive fixture
(fires), negative fixture (state has the escape hatch, e.g. `on_error`),
suppressed fixture (`*_ok=True` → `errors == []`), full `validate_fsm()` wiring
assertion (message contains `"(MR-10)"`), and a top-level-key-recognized
assertion via `load_and_validate`. All five sub-patterns are directly reusable.
`BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"`
(`test_fsm_validation.py:1085`) plus the per-rule "passes clean" pattern in
`TestMetaLoopValidation.test_harness_optimize_passes_clean`
(`test_fsm_validation.py:1107-1117`) is the template for the "all builtin loops
pass" acceptance criterion — load each builtin YAML via `load_and_validate` and
assert the new rule's WARNING list is empty, specifically for
`auto-refine-and-implement.yaml` and `general-task.yaml` (post-ENH-2857).

**Docs to update**: `.claude/CLAUDE.md` § Loop Authoring rule table (add an
`MR-13` row) and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s MR-1..MR-12
table (lines ~85-107) plus its summary lines (~311, ~324) that enumerate which
MRs a check enforces.

## Acceptance Criteria

- [ ] `ll-loop validate` warns on abandonment-mechanism-without-abandoned-field and on hardcoded success verdicts
- [ ] Suppress flag documented in CLAUDE.md rule table + HARNESS_OPTIMIZATION_GUIDE.md
- [ ] All builtin loops pass validation after ENH-2857 lands (this issue is blocked_by ENH-2857)
- [ ] `abandonment_verdict_ok` round-trips through `FSMLoop.to_dict()`/`from_dict()` and is present in `fsm-loop-schema.json`

## Session Log
- `/ll:wire-issue` - 2026-07-27T17:54:35 - `01b0f441-7c32-42ef-bbf2-05be0142591f.jsonl`
- `/ll:refine-issue` - 2026-07-27T17:52:00 - `ce1c6ca2-b49a-4eda-8b78-3c7318aa2efb.jsonl`
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
