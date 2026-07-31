---
id: ENH-2932
type: ENH
priority: P3
status: done
discovered_date: 2026-07-30
captured_at: '2026-07-30T23:22:05Z'
completed_at: '2026-07-31T02:21:06Z'
discovered_by: capture-issue
relates_to:
- ENH-1833
- ENH-1834
- ENH-1835
- ENH-1841
labels:
- enhancement
- captured
confidence_score: 100
outcome_confidence: 86
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
decision_needed: false
---

# ENH-2932: Wire analytics.capture.skills and cli_commands gates onto skill/CLI event writers

## Summary

`ll-config.json`'s `analytics.capture.skills` and `analytics.capture.cli_commands`
glob-pattern fields are defined in `config-schema.json` and parsed into
`AnalyticsCaptureConfig` (`scripts/little_loops/config/features.py`), but no write
path ever consults them. `record_skill_event()`/`skill_event_context()` and
`cli_event_context()` (`scripts/little_loops/session_store/writers.py`) accept a
`config` parameter documented as a "forward-compatibility stub ... accepted but not
yet used," and the two call sites (`hooks/post_tool_use.py:246`,
`hooks/user_prompt_submit.py:130`) still carry
`# TODO(ENH-1835): wire ... gate when ENH-1833/ENH-1834 lands` comments. Both
prerequisite issues (ENH-1833 skill events, ENH-1834 CLI events) have since shipped,
but the follow-up wiring was never done.

## Current Behavior

Setting `analytics.capture.skills` or `analytics.capture.cli_commands` to anything
other than `["*"]` (e.g. narrowing to specific skill/binary names) has no effect —
every `/ll:`-prefixed skill invocation and every `ll-*` CLI invocation that calls
`cli_event_context()` is written to `skill_events`/`cli_events` unconditionally. The
config keys are documented in `config-schema.json` and covered by unit tests for the
`feature_enabled_for()` glob-matching helper itself, but nothing threads that helper
into the two live write paths.

## Expected Behavior

`record_skill_event()`/`skill_event_context()` and `cli_event_context()` consult
`AnalyticsCaptureConfig.skills` / `.cli_commands` (via `feature_enabled_for()`) before
writing a row, using the same pattern ENH-1841 already established for
`analytics.capture.file_events` and `analytics.capture.corrections`. A skill/binary
name that doesn't match any configured glob pattern is silently skipped; the default
`["*"]` preserves today's unconditional-capture behavior.

## Motivation

This closes a real, currently-misleading gap: the config schema and `ll-doctor`
capture-state reporting present `analytics.capture.skills`/`cli_commands` as live
controls, but they are inert scaffolding. High-volume projects that set these to
narrow the DB growth get no effect and no error — a silent no-op is worse than an
unsupported key. The fix is small and low-risk: the pattern was already proven twice
in ENH-1841 for the other two capture categories.

## Proposed Solution

Follow the exact ENH-1841 pattern:

```python
from little_loops.config.features import AnalyticsCaptureConfig, feature_enabled_for

capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
if not feature_enabled_for({"skills": capture.skills}, "skills", skill_name):
    return
```

Thread this gate inside `record_skill_event()`/`skill_event_context()` (using
`capture.skills`) and inside `cli_event_context()` (using `capture.cli_commands`),
not only at the hook call sites — matching ENH-1841's Wiring Phase note #6 that
gating must live in the write-path functions themselves so it also applies to
non-hook callers (e.g. `ll-*` CLI entry points calling `cli_event_context()`
directly). Remove the two now-stale `TODO(ENH-1835)` comments once wired.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact target locations** (`scripts/little_loops/session_store/writers.py`):
  `record_skill_event()` lines 257–282, `cli_event_context()` (contextmanager)
  lines 402–470, `skill_event_context()` (contextmanager) lines 486–559. The
  ENH-1841 precedent (`write_file_event()` lines 190–221, `record_correction()`
  lines 224–254) gates plain boolean flags with `if not capture.<flag>: return`;
  `skills`/`cli_commands` are glob-pattern lists, so the new gate must call
  `feature_enabled_for(...)` per this section's snippet above rather than a bare
  attribute check — not a byte-identical copy of the ENH-1841 shape.
- **Context-manager gating caveat**: `skill_event_context()` and
  `cli_event_context()` are `@contextmanager` functions whose caller always
  enters a `with ... as completion:` (or bare `with ...:`) block and runs code
  inside it regardless of whether the row write happened. A gated-off early
  `return` before the `yield` would break every caller. The gate must instead
  skip the `_pkg.connect(...)`/`INSERT` work but still `yield` (a
  `SkillEventCompletion()` default instance for `skill_event_context()`, bare
  `None` for `cli_event_context()`) — the same "yield anyway, stay inert" shape
  the existing INSERT-failure path already uses (`conn = None; row_id = None`
  then falls through to yield).
- **`hooks/post_tool_use.py:246` TODO has no accompanying skill-event call to
  gate.** That file only writes `tool_events` (unconditional) and `file_events`
  (already gated on `capture.file_events`) — there is no
  `record_skill_event()`/`skill_event_context()` call anywhere in it. The
  `# TODO(ENH-1835): wire analytics.capture.skills gate when ENH-1833 lands`
  comment is a placeholder note with nothing to wire at that line.
- **`hooks/user_prompt_submit.py:130` TODO is mislabeled.** The comment reads
  `# TODO(ENH-1835): wire analytics.capture.cli_commands gate when ENH-1834
  lands`, but the code immediately following it (lines 131–136) is a
  `record_skill_event()` call on `m.group(1)` (the matched `/ll:<skill-name>`
  token) — i.e. this is the real `capture.skills` gate site, not
  `cli_commands`. `capture` (an `AnalyticsCaptureConfig`) is already built two
  lines above at line 123, so `capture.skills`/`m.group(1)` are both in scope
  to gate this call directly, without needing the writer-level gate for this
  particular call site (though the writer-level gate is still required per
  Implementation Step 1 for non-hook callers).
- **Writer-level gating alone will not activate `cli_commands` gating for any
  real caller today.** Grepped all `cli_event_context()`/`skill_event_context()`
  call sites: ~40 `ll-*` CLI entry points (e.g.
  `scripts/little_loops/cli/action.py:227,379`,
  `scripts/little_loops/cli/session.py:390`,
  `scripts/little_loops/cli/queue.py:730`,
  `scripts/little_loops/cli/issues/__init__.py:21`, and ~35 more) call these
  context managers with 2–3 positional args and never pass a `config=` dict —
  none load project config at all. Per the write-path-gate design (`if config
  is not None: ...`), an un-migrated caller that never passes `config` is
  treated as permissive (no behavior change) — so wiring the gate inside the
  three writer functions is necessary but not sufficient to make
  `analytics.capture.cli_commands` narrowing actually take effect for `ll-*`
  CLI invocations; those ~40 call sites would need a follow-up change to load
  and pass `config` through. This issue's Implementation Steps don't currently
  list that caller-side wiring — worth deciding explicitly whether it's in
  scope here or a distinct follow-up, since without it the `cli_commands` half
  of this issue closes the write-path TODO but leaves the config option still
  practically inert for its primary use case.

**Option A**: Keep this issue scoped to writer-level gating only (as currently
written in Scope Boundaries/Implementation Steps) — wire the gate inside
`record_skill_event()`/`skill_event_context()`/`cli_event_context()`, remove the
stale TODOs, add the mirrored tests, and stop there. Wiring `config=` through the
~40 `ll-*` CLI entry points that call these context managers becomes a distinct
follow-up issue.

> **Selected:** Option A — matches the ENH-1841 precedent exactly (writer-level
> gate only, caller migration deferred), keeps this issue's "Small effort" sizing
> honest, and follows the codebase's convention of splitting cross-cutting
> mechanism wiring from per-surface propagation (see Decision Rationale below).

**Option B**: Expand this issue's scope to also load and pass `config=` through
the ~40 un-migrated `ll-*` CLI entry points, so `analytics.capture.cli_commands`
narrowing takes effect immediately for its primary use case instead of remaining
practically inert until a follow-up lands.

**Recommended**: Option A — the Impact section already sizes this issue as
"Small effort" (the exact ENH-1841 pattern applied to two more write paths) and
P3 priority; touching ~40 call sites is a materially larger, separately
reviewable change with its own risk surface (verifying each entry point's config
loading doesn't break existing behavior), consistent with how ENH-1841 landed
the writer-level gate for `file_events`/`corrections` before any caller-side
follow-up was required.

- **Existing test to update, not just add to**:
  `TestRecordSkillEvent.test_record_skill_event_config_stub_accepted`
  (`scripts/tests/test_session_store_writers.py:382-389`) currently asserts
  `config={"analytics": {}}` does *not* suppress the write, with a docstring
  claiming "no gate applied." Once the gate lands, this specific assertion
  still holds (empty `capture` dict → `AnalyticsCaptureConfig.skills` defaults
  to `["*"]` → still matches `"check-code"` → still not suppressed), but its
  docstring/comment goes stale and should be updated to reflect that a gate
  now exists and simply isn't triggered by this fixture's permissive config.
- **Test pattern to mirror**: `TestRecordCorrection.test_record_correction_gate_disabled`
  (`scripts/tests/test_session_store_writers.py:319`) and
  `test_write_file_event_gate_disabled` (line 334) — pass
  `config={"analytics": {"capture": {"<flag>": False}}}` directly, assert
  `recent(db, kind=...)` returns zero rows. A `skills`/`cli_commands` analogue
  narrows the list instead of flipping a bool, e.g.
  `config={"analytics": {"capture": {"skills": ["other-skill"]}}}` then call
  with `skill_name="check-code"` and assert no row was written.

### Decision Rationale

_Added by `/ll:decide-issue`:_

**Selected**: Option A — writer-level gating only; caller-side `config=`
threading through the ~40 (actually 47, per Phase 4 evidence) `ll-*` CLI entry
points is a distinct follow-up issue, not part of this one.

**Reasoning**: Option A is the exact ENH-1841 precedent — `write_file_event()`/
`record_correction()` were gated at the writer level in this same file with
caller migration explicitly deferred (ENH-1841 itself scoped `skills`/
`cli_commands` gating out and left only TODO markers). Option B's target
population is real (47 call sites across 46 files, not "~40") and mechanically
uniform, but expanding this issue to cover it contradicts the Impact section's
own "Small effort" sizing rationale ("the exact pattern already implemented
twice") and departs from this codebase's established convention of splitting
core-mechanism wiring from per-surface propagation into separate issues (e.g.
the `FEAT-1116` → `FEAT-1451` → `FEAT-1489` → `FEAT-1466` OpenCode hook-intent
chain, and the narrower single-file `ENH-2925` consolidation kept standalone
rather than folded into a larger sweep).

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| A — writer-level only | 3 | 3 | 3 | 3 | 12/12 |
| B — expand to 47 CLI call sites | 1 | 0 | 1 | 1 | 3/12 |

**Key evidence**:
- ENH-1841's own scope statement explicitly deferred `skills`/`cli_commands`
  caller wiring as future work, placing only TODO markers
  (`.issues/enhancements/P3-ENH-1841-analytics-capture-write-path-gating.md:68-81`).
- `write_file_event()`/`record_correction()` each had exactly one production
  caller to leave permissive under the writer-level gate
  (`scripts/little_loops/session_store/writers.py:190-254`); `cli_event_context()`
  has 47 call sites across 46 files, none passing `config=` today — a
  materially larger surface than what "the exact pattern applied to two more
  write paths" describes.
- Mirrored gate tests already exist to copy directly:
  `TestRecordCorrection.test_record_correction_gate_disabled` /
  `test_write_file_event_gate_disabled`
  (`scripts/tests/test_session_store_writers.py:319,334`).
- Codebase convention for propagating a new cross-cutting mechanism splits
  core-mechanism and per-surface wiring into separate issues rather than
  bundling them (`FEAT-1116`/`FEAT-1451`/`FEAT-1489`/`FEAT-1466`).

## Scope Boundaries

- **In scope**: Threading `analytics.capture.skills` into `record_skill_event()` /
  `skill_event_context()`; threading `analytics.capture.cli_commands` into
  `cli_event_context()`; removing the two stale TODO comments; tests mirroring
  ENH-1841's gating tests for the new categories.
- **Out of scope**: Capturing project-local (non-`/ll:`-prefixed) skill invocations —
  `user_prompt_submit.py`'s regex only recognizes `^/ll:[a-z][a-z0-9-]*`, a separate
  capture-surface limitation, not a gating bug. Capturing arbitrary non-`ll-*` CLI
  invocations (e.g. `python3 tools/*.py`) — `cli_event_context()` is only called from
  inside `ll-*` entry points by design (ENH-1834 explicitly scoped non-`ll-` tools as
  out of scope). Both are legitimate follow-ups but distinct from finishing this
  gating wire-in.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py` — `record_skill_event()` (lines
  257–282), `cli_event_context()` (lines 402–470), `skill_event_context()` (lines
  486–559); mirror the `write_file_event()`/`record_correction()` gate shape (lines
  190–221, 224–254) but use `feature_enabled_for()` since `skills`/`cli_commands`
  are glob lists, not booleans.
- `scripts/little_loops/hooks/user_prompt_submit.py:130` — remove/replace the
  mislabeled `TODO(ENH-1835)` comment; the `record_skill_event()` call at lines
  131–136 is the real `capture.skills` gate site (already has `capture` and
  `m.group(1)` in scope at line 123).
- `scripts/little_loops/hooks/post_tool_use.py:246` — remove the stale TODO; no
  accompanying skill-event call exists at this site to gate.

### Dependent Files (Callers)
- ~40 `ll-*` CLI entry points call `cli_event_context()`/`skill_event_context()`
  with no `config=` argument today (e.g. `scripts/little_loops/cli/action.py:227,379`,
  `scripts/little_loops/cli/session.py:390`, `scripts/little_loops/cli/queue.py:730`,
  `scripts/little_loops/cli/issues/__init__.py:21`). Per the `if config is not
  None:` gate shape, these remain unaffected (permissive) until each is updated to
  load and pass `config` — see the Codebase Research Findings note under Proposed
  Solution for the scope question this raises.
- `scripts/little_loops/cli/doctor.py` (`_capture_section_data()` line 123,
  `_print_capture_section()` line 142) — reads `capture.skills`/`.cli_commands`
  for display only; unaffected by this change but worth a spot-check per
  Implementation Step 5.

### Similar Patterns
- `write_file_event()`/`record_correction()` gating —
  `scripts/little_loops/session_store/writers.py:190-254` (ENH-1841).

### Tests
- `scripts/tests/test_session_store_writers.py` — `TestRecordCorrection.test_record_correction_gate_disabled`
  (line 319) and `test_write_file_event_gate_disabled` (line 334) are the patterns
  to mirror for `TestRecordSkillEvent`/`TestCliEventContext`. Also update
  `test_record_skill_event_config_stub_accepted` (line 382) — its "no gate
  applied" docstring goes stale once wired (assertion itself still passes).
- `scripts/tests/test_config.py` — `TestFeatureEnabledForHelper` (line 1499)
  already covers `feature_enabled_for()` glob semantics; no changes needed there.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_writers.py` — `TestRecordSkillEvent` (class at
  line 350) is missing `test_record_skill_event_gate_disabled`; insert after
  `test_record_skill_event_config_stub_accepted` (ends line 389). Assert with
  `config={"analytics": {"capture": {"skills": ["other-skill"]}}}` +
  `skill_name="check-code"` that no row is written.
- `scripts/tests/test_session_store_writers.py` — `TestCliEventContext` (class at
  line 392) has zero gate coverage; insert `test_cli_event_context_gate_disabled`
  at the end of the class, right before `class TestMineCorrectionsFromMessages:`
  (line 526). Assert with `config={"analytics": {"capture": {"cli_commands":
  ["not-this-binary"]}}}` that `recent(db, kind="cli")` returns zero rows.
- `scripts/tests/test_session_store_writers.py` — `TestSkillEventContext` (class
  at line 730) currently has **no test at all** exercising a `config=` argument
  (unlike `record_skill_event`, which has `test_record_skill_event_config_stub_accepted`).
  Insert two tests after `test_best_effort_on_unopenable_db` (ends line 794),
  before `class TestInferIssueId:` (line 797): a stub-accepted-style test proving
  the permissive default still yields a populated `SkillEventCompletion`/writes a
  row, and a gate-disabled test proving a narrowed `capture.skills` list still
  yields a `SkillEventCompletion()` instance (not `None`) but skips the write —
  this exercises the "yield anyway" contract called out above under Codebase
  Research Findings.
- `scripts/tests/test_hook_user_prompt_submit.py` — `TestUserPromptSubmitSkillWrite`
  (lines 223–309) has no test covering the `capture.skills` gate for the
  `record_skill_event()` call at `hooks/user_prompt_submit.py:134`. Add
  `test_skill_prompt_write_skipped_when_capture_skills_gate_excludes` using the
  existing `_write_config(..., analytics_capture={"skills": [...]})` helper
  (already defined at line 30 — no new fixture needed).
- Three docstrings in `scripts/little_loops/session_store/writers.py` still use
  the stale "forward-compatibility stub ... accepted but not yet used" language
  and need updating alongside the code change: `record_skill_event` (lines
  266–267), `cli_event_context` (lines 419–420), `skill_event_context` (lines
  502–503).

## Program Design

Signatures below are unchanged (`config: dict | None = None` already exists on all
three functions per `scripts/little_loops/session_store/writers.py:253,402,486`);
only the function bodies gain the gate. File/line references and rationale are
covered in Codebase Research Findings and Integration Map above.

### Types

- `skills: list[str]`
- `cli_commands: list[str]`

### Signatures

- `feature_enabled_for(config_data: dict, dot_path: str, subject: str) -> bool`
- `record_skill_event(db_path: Path, session_id: str, skill_name: str, args: str, config: dict) -> None`
- `cli_event_context(db_path: Path, binary: str, args: list, config: dict) -> Generator[None, None, None]`
- `skill_event_context(db_path: Path, session_id: str, skill_name: str, args: str, config: dict) -> Generator[SkillEventCompletion, None, None]`

### Call Path

`user_prompt_submit.py` -> `record_skill_event` -> `AnalyticsCaptureConfig.from_dict` -> `feature_enabled_for` -> `_pkg.connect`

## Implementation Steps

1. Add the `capture.skills` gate inside `record_skill_event()` and
   `skill_event_context()` in `scripts/little_loops/session_store/writers.py`.
   `skill_event_context()` must still `yield` a `SkillEventCompletion()` default
   instance when gated off — never return before the `yield`. Update the stale
   "forward-compatibility stub" docstring language on both functions (lines
   266–267, 502–503).
2. Add the `capture.cli_commands` gate inside `cli_event_context()` in the same
   file (lines 402–470); it must still `yield` (bare `None`) when gated off.
   Update its stale docstring (lines 419–420).
3. Remove the two stale `TODO(ENH-1835)` comments in `hooks/post_tool_use.py` and
   `hooks/user_prompt_submit.py` (or replace with a short note that gating now lives
   in the writer, if the hook call sites don't already pass `config` through).
4. Add gating tests mirroring `TestRecordCorrection`'s
   `test_record_correction_gate_disabled` pattern for both new categories, per the
   Wiring pass additions under Integration Map > Tests above: a
   `TestRecordSkillEvent` gate-disabled test, a `TestCliEventContext` gate-disabled
   test, both a stub-accepted and a gate-disabled test for `TestSkillEventContext`
   (currently zero `config=` coverage there), and a hook-level test in
   `test_hook_user_prompt_submit.py` for the `capture.skills` gate at the real
   call site (`hooks/user_prompt_submit.py:134`).
5. Verify `ll-doctor`'s existing capture-state reporting block (added by ENH-1842)
   still reads correctly now that the flags are live.

## Impact

- **Priority**: P3 — matches sibling capture-config issues (ENH-1833/1834/1835/1841);
  not urgent, but closes a documented-but-inert config surface.
- **Effort**: Small — the exact pattern is already implemented twice (ENH-1841); this
  is the same threading applied to two more write paths.
- **Risk**: Low — safe default (`["*"]`) preserves current unconditional-capture
  behavior; no behavior change unless a user narrows the glob list.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-30_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

Both hard overrides from the prior check are now clear: the `## Program
Design` section is present with concrete signatures and call path, and the
Decision Rationale section resolves the caller-wiring scope question (Option
A — writer-level gating only, caller-side `config=` threading deferred to a
follow-up). No gaps or outcome risk factors remain.

## Resolution

Wired `analytics.capture.skills` into `record_skill_event()`/`skill_event_context()`
and `analytics.capture.cli_commands` into `cli_event_context()`
(`scripts/little_loops/session_store/writers.py`), gating via `feature_enabled_for()`
per the ENH-1841 precedent. `skill_event_context()`/`cli_event_context()` still
`yield` when gated off (never return early before the `yield`). Removed the two
stale `TODO(ENH-1835)` comments in `hooks/post_tool_use.py` (no accompanying call
to gate) and `hooks/user_prompt_submit.py` (passed `config=config` through to
`record_skill_event()` so the real call site is actually gated, not just the
writer-level mechanism). Added mirrored gate tests to
`test_session_store_writers.py` (`TestRecordSkillEvent`, `TestCliEventContext`,
`TestSkillEventContext`) and a hook-level gate test to
`test_hook_user_prompt_submit.py`. `ll-doctor`'s capture-state reporting is
display-only and unaffected. Full suite: 17297 passed, 42 skipped, 1 pre-existing
unrelated failure (`test_prose_dep_sweep_gate.py`, confirmed failing identically
on clean `main` before this change).

## Session Log
- `/ll:manage-issue` - 2026-07-31T02:20:21Z - `be45f1e8-165f-42f9-9ef8-cd637d37da16.jsonl`
- `/ll:ready-issue` - 2026-07-31T02:12:59 - `a5ab3484-d90f-4050-b5cf-3333753371cf.jsonl`
- `/ll:confidence-check` - 2026-07-31T02:15:00 - `860e4784-3e3e-43cf-a58b-0f6c68e44f88.jsonl`
- `/ll:decide-issue` - 2026-07-31T02:09:54 - `32dca2d5-81fe-4979-8d83-cc3b842f5ae0.jsonl`
- `/ll:refine-issue` - 2026-07-31T02:05:32 - `85185af4-900d-4c27-b4ce-ce471b2ece68.jsonl`
- `/ll:refine-issue` - 2026-07-31T02:04:58 - `85185af4-900d-4c27-b4ce-ce471b2ece68.jsonl`
- `/ll:confidence-check` - 2026-07-31T02:00:06 - `92c64fff-092f-4069-a449-51d720f5182f.jsonl`
- `/ll:wire-issue` - 2026-07-31T01:57:38 - `406783e5-2497-4e48-8bf8-2a31f7ad518e.jsonl`
- `/ll:refine-issue` - 2026-07-31T01:51:26 - `29a79f42-1d84-495a-b94d-df88bc9b8824.jsonl`
- `/ll:capture-issue` - 2026-07-30T23:22:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4be5df0-3d5b-4e4c-86d2-f958207fe7cb.jsonl`

---

## Status

**Open** | Created: 2026-07-30 | Priority: P3
