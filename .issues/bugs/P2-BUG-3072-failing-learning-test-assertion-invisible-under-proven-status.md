---
id: BUG-3072
priority: P2
type: BUG
status: done
discovered_commit: 5d0a711f
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: manual-investigation
completed_at: '2026-08-06T03:45:05Z'
labels:
- learning-tests
- confidence-check
- registry
testable: true
size: Large
verify_verdict: VALID
confidence_score: 85
outcome_confidence: 59
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
---

# BUG-3072: A `result: fail` assertion is invisible to every consumer once the record is `proven`

## Summary

`.ll/learning-tests/pytest.md` carries `status: proven` alongside an assertion whose
`result` is `fail`:

> `claim: using an unregistered marker with --strict-markers active causes collection error (exit non-zero)` → `result: fail`

That combination is **correct per spec** — `skills/explore-api/SKILL.md:190-192` defines
`proven` as "at least one assertion is `pass`" and `refuted` as "*all* exercised
assertions are `fail`". So this is not a status-computation bug.

The defect is downstream: once a record is `proven`, its failing claims are unreachable.
Every consumer branches on `record.status` alone, so a registry entry that explicitly
records a contradicted claim is indistinguishable from one where everything held.

## Current Behavior

`status` is author-supplied and never reconciled against `assertions`. Nothing in
`scripts/little_loops/learning_tests/` derives, validates, or re-checks it:

- `LearnTestRecord.from_dict` (`learning_tests/__init__.py:63`) reads `status` straight
  from frontmatter, defaulting to `"proven"` when the key is absent.
- `write_record` (`:90`) serializes whatever the caller set.
- `mark_stale` (`:130`) is the only mutation, and it only writes `"stale"`.

Consumers then use status as the whole truth:

| Consumer | Behavior on a `proven` record with failing assertions |
|---|---|
| `run_release_gate` (`learning_tests/release_gate.py:58`) | filters `status == "refuted" or is_record_stale(...)` → record passes silently |
| `cmd_check --stale-aware` (`cli/learning_tests.py:41`) | `record.status != "proven"` → exit 0, clean |
| `cmd_prove` (`:71`) | `return 0 if record.status == "proven" else 1` → reports success |
| `/ll:confidence-check` rubric (`skills/confidence-check/rubric.md:167`) | `proven` → **0 penalty**; only `refuted`/`missing`/`stale` score against readiness |

So an issue that depends on a claim the registry has already recorded as contradicted
passes the confidence gate with no deduction and no mention.

The one place that does read per-assertion results is
`scripts/little_loops/cli/history_context.py:75-77` (counts pass/fail/untested) — it is a
history-display path, not a gate.

**Secondary finding: `fail` conflates two different things.** The raw output
(`.ll/learning-tests/raw/pytest.txt:3`) for this claim is:

```
[FAIL] claim3_strict_markers_blocks_unregistered: rc=0 has_error=True
```

The probe demanded a non-zero exit code *and* an error marker; it got the error but
`rc=0`, so its compound condition failed. pytest's actual `--strict-markers` behavior is
not in doubt — this is a defective probe, not a contradicted API. Nothing distinguishes
"the API contradicted the claim" from "the proof script was wrong", and nothing ever
revisits it.

## Steps to Reproduce

1. `ll-learning-tests check pytest` → JSON with `status: proven` and one `result: fail`.
2. `ll-learning-tests check pytest --stale-aware` → considers only status; the failing
   assertion has no effect on the exit code (aside from the independent staleness flag).
3. Run `/ll:confidence-check` on an issue naming `pytest` as a learning target → the
   target scores `proven`, 0 penalty, failing claim never surfaced.

## Expected Behavior

A recorded `fail` assertion is visible wherever the record is consumed as evidence:

- `ll-learning-tests check` output makes the failing claims explicit (not merely present
  in the JSON body).
- The confidence-check rubric applies a deduction, or at minimum surfaces the failing
  claim text in the learning-test table, rather than treating `proven` as unqualified.
- A `fail` is distinguishable from an untrustworthy probe, so it can be triaged instead
  of silently persisting.

## Root Cause

Two-part:

1. **Status is a lossy summary used as the sole interface.** The record schema carries
   per-claim results, but every gate collapses to the three-valued `status`. `proven`
   means "≥1 claim held", which is a much weaker guarantee than the consumers treat it as.
2. **No reconciliation step exists.** `status` is written once by `/ll:explore-api` and
   never recomputed, so even a later edit to `assertions` cannot change it.

## Proposed Solution

Options, to be decided:

- **A — surface, don't gate** (smallest): make `cmd_check` print failing claims to stderr
  and add a `failing_claims` count to the JSON; add a rubric row so
  `/ll:confidence-check` reports them. Status semantics unchanged.
- **B — derive and validate status**: compute status from assertions on read
  (`from_dict`), and add a fourth state (e.g. `partial`) for "some pass, some fail" so
  gates can branch on it. Larger blast radius: every consumer's status comparison and the
  `Literal` type must be updated, and `skills/explore-api/SKILL.md` re-specified.
- **C — treat any `fail` as gate-relevant**: leave status alone but add
  `has_failing_assertions` to the release gate and `--stale-aware` exit conditions.

A is the minimum that fixes the observed harm; B is the principled fix. Recommend A now,
B behind a separate decision.

Independently: re-run the `pytest` `--strict-markers` probe with a corrected condition and
update that assertion, since the current `fail` is a probe artifact.

## Program Design

**Invariant.** No consumer treats a record as unqualified evidence while that record
contains an assertion with `result: fail`.

### Types

```python
result: Literal["pass", "fail", "untested"]
status: Literal["proven", "refuted", "stale"]
```

### Signatures

```python
def check_learning_test(target: str, *, base_dir: Path | None = None) -> LearnTestRecord | None:
def cmd_check(args: argparse.Namespace) -> int:
def run_release_gate(cwd: Path, *, base_dir: Path | None = None) -> int:
```

### Call Path

- `cmd_check` (`cli/learning_tests.py:13`) → `check_learning_test`
  (`learning_tests/__init__.py:140`) → `read_record` (`:105`) → `LearnTestRecord.from_dict` (`:63`)
- `run_release_gate` (`learning_tests/release_gate.py:36`) → `list_records` (`:117`)
- `skills/confidence-check/rubric.md:130` shells out to `ll-learning-tests check`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Audit `scripts/little_loops/loops/rn-implement.yaml`, `learning-tests-audit.yaml`, `migrate-sdk-version.yaml`, and the generator `scripts/little_loops/cli/loop/scaffold_eval.py` for the same status-only blind spot before finalizing the option — `fsm/executor.py` and `cli/ctx_stats.py` already branch on proven status the same way as the primary consumers
- If a new record field is added (Option B/C), extend `session_store/writers.py`'s `learning_test_events` INSERT/upsert and table schema for the new top-level column
- Update `docs/guides/LEARNING_TESTS_GUIDE.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md` to match the chosen option
- After editing `skills/confidence-check/{SKILL.md,rubric.md}` or `skills/explore-api/SKILL.md`, run the adapter sync (`ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply`) to keep the untested `.gemini`/`.kimi-code` mirrors from going stale

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Additional Types (from analyzer)

```python
@dataclass
class Assertion:
    claim: str
    result: Literal["pass", "fail", "untested"]
```
Declared once at `learning_tests/__init__.py:27-41`; `from_dict` defaults `result` to `"untested"` when absent (`:37-41`), `claim` has no default. `LearnTestRecord.status` `Literal` is likewise declared exactly once (`:50`) — no other `Literal["proven","refuted","stale"]` exists elsewhere in the codebase, so a 4th status value (Option B's `partial`) has a single declaration site to change, but 8 separate string-equality call sites to update (release_gate.py:58,78; cli/learning_tests.py:42,74; hooks/learning_tests_gate.py:128,140; hooks/install_learning_gate.py:121; history_context.py:74).

### Existing reusable pattern

`_render_learning_test_section()` (`cli/history_context.py:59-92`) already computes an "effective status" independent of the stored field — `effective_status = "stale" if is_record_stale(record, stale_after_days) else record.status` (`:74`) — and separately counts `passes`/`fails`/`untested` via three `sum(1 for a in record.assertions if a.result == X)` comprehensions (`:75-77`). This is the only place in the codebase that inspects `assertions` at all; it is inline, not exposed as a method on `Assertion`/`LearnTestRecord`, and would need extracting to be reused by Option A/B/C's gating logic. It also demonstrates the precedent shape (a derived value shadowing the stored `status`) that Option B or a `has_failing_assertions` property (Option C) would follow.

No JSON Schema constrains `status`/`result` values — `config-schema.json:1032`+ only covers `learning_tests` gate *configuration* (`enabled`, `stale_after_days`, etc.), not the record file schema; parsing stays permissive via `.get()` calls with no enum enforcement.

The write-time rule producing this exact symptom is authored prose, not code: `skills/explore-api/SKILL.md` § Phase 4: Refine (lines 181-217, rule at 190-193) — "`proven` = at least one assertion is `pass`", independent of any coexisting `fail`.

## Acceptance Criteria

- [x] `ll-learning-tests check <target>` on a record containing a `result: fail` assertion
      makes the failing claim(s) explicit in its output.
- [x] A test asserts that a `proven` record with ≥1 failing assertion is distinguishable
      from a `proven` record with none, at the consumer boundary chosen by the decision.
- [x] `skills/confidence-check/rubric.md` states how failing assertions affect scoring.
- [x] The `pytest` record's `claim3` assertion is re-run and its result corrected, or the
      claim reworded to match what the probe actually tests.
- [x] `python -m pytest scripts/tests/` exits 0 for every test this change touches
      (`test_learning_tests.py`, `test_cli_learning_tests.py`, `test_confidence_check_skill.py`
      all pass). The full-suite run has 48 pre-existing failures on `main`
      (`test_hook_session_start.py`, `test_codex_adapter.py`, `test_kimi_adapter.py`,
      `test_opencode_adapter.py`, `test_history_context_cli.py::TestPriorWorkCondensedSection`)
      confirmed present before this change via `git stash` — unrelated to learning tests,
      out of scope here.

## Impact

The registry exists so implementation decisions rest on proven API behavior. A claim the
registry has recorded as contradicted still reads as proven evidence to the confidence
gate — the exact failure mode the gate is meant to prevent. Currently one record is
affected, but nothing prevents recurrence, and the same mechanism hides genuine
refutations behind a single passing claim.

## Integration Map

- `scripts/little_loops/learning_tests/__init__.py` — record model / status handling
- `scripts/little_loops/cli/learning_tests.py` — `check`, `prove` exit semantics
- `scripts/little_loops/learning_tests/release_gate.py` — gate filter
- `skills/confidence-check/rubric.md`, `skills/confidence-check/SKILL.md` — scoring
- `skills/explore-api/SKILL.md:187-192` — status determination spec
- `.ll/learning-tests/pytest.md`, `.ll/learning-tests/raw/pytest.txt` — the affected record

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `scripts/little_loops/hooks/learning_tests_gate.py:128,140` — two additional `record.status == "proven"` gate checks not listed above; same blind spot to `fail` assertions coexisting with `proven` status
- `scripts/little_loops/hooks/install_learning_gate.py:121` — third `record.status == "proven"` gate check with the same blind spot
- `scripts/little_loops/learning_tests/gate.py` — `is_record_stale` (`:40`), `format_nudge_message` (`:26`), `run_learning_gate_for_issue` (`:61`); has its own unrelated `Literal["passed", "blocked", "impl_failed", "skipped"]` gate-verdict type (`:67`) for `proof-first-task`/`ready-to-implement-gate` loop runs — distinct concept from `LearnTestRecord.status`, do not conflate when scoping a status-Literal change
- Test files to extend per option: `scripts/tests/test_learning_tests.py` (`TestLearnTestRecord` round-trip tests — status/assertion derivation logic), `scripts/tests/test_cli_learning_tests.py` (`TestStaleAwareCLI` lines 220-310 exercises the `cmd_check --stale-aware` gate branch; `TestMainLearningTestsProve` lines 312-412 exercises `cmd_prove`'s return code), `scripts/tests/test_release_gate.py` (`TestReleaseGateWarnMode`/`TestReleaseGateBlockMode` lines 146-207 test the `problem_records` filter), `scripts/tests/test_learning_tests_discoverability.py` (covers the `hooks/learning_tests_gate.py` call sites).
  > ⚠ Superseded — `test_history_context_cli.py` already covers this (see Tests below)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:1160,1166,1200` — checks `record.status == "proven"` for learning-gate FSM states; same proven-blind-to-fail-assertions blind spot as the release/hook gates
- `scripts/little_loops/cli/ctx_stats.py:660,662,663` — renders learning-test status counts for `ll-ctx-stats`; would misreport a `proven`-with-`fail` record the same way
- `scripts/little_loops/session_store/writers.py` — `record_learning_test_event()`/`_backfill_learning_test_events()` mirror `status`/`assertions` into the `learning_test_events` SQLite table; a new top-level record field (Option B/C) needs an explicit column added to the INSERT/upsert, a new `Assertion` field round-trips via the existing JSON blob for free
- `hooks/hooks.json:93` — manifest registration for the already-known `learning_tests_gate` PreToolUse hook

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_history_context_cli.py` — `TestRenderLearningTestSection` (420-488) already covers `_render_learning_test_section`, including a `fail`-assertion fixture (`test_formats_table_with_assertion_counts`, line 435, asserting the `"1/1/1"` pass/fail/untested column). Extend this class for AC2's distinguishability test rather than writing a first test for this function.
- `scripts/tests/test_learning_tests_extractor.py`, `test_learning_tests_gate.py`, `test_install_learning_gate.py`, `test_cli_ctx_stats.py`, `test_history_reader.py`, `test_session_store_writers.py`, `test_session_store_lifecycle.py`, `test_learning_state.py`, `test_issue_manager.py`, `test_worker_pool.py`, `test_sprint_integration.py`, `tests/integration/test_init_e2e.py` — cover the newly-found callers/importers above; review each for `assertions=[]`/all-`pass` fixtures that would need a `fail`-assertion variant once the option is decided (none of the existing `.ll/learning-tests/*.md` test fixtures across the codebase currently construct a `proven` record with a `fail` assertion, so no currently-passing test breaks under any option)
- `scripts/tests/test_rn_implement.py` — asserts exact substrings of the embedded `ll-learning-tests check --stale-aware` invocation in `rn-implement.yaml` (lines 1189, 1191, 1259, 1328) and stubs a fake `ll-learning-tests` binary keyed on exit code only (line 1360); extend the stub if the fix changes exit-code semantics
- `scripts/tests/test_ll_loop_scaffold_eval.py:92`, `test_create_eval_from_issues.py:547,610` — assert the literal generated-YAML substring `"ll-learning-tests check --stale-aware"`
- `scripts/tests/test_confidence_check_skill.py` — `TestConfidenceCheckRubricLearningTestStatus` (418-429) asserts `rubric.md`'s exact penalty strings (`−10`, `−5` — en-dash); AC3's rubric change must preserve or update these in lockstep
- `scripts/tests/test_ready_issue_lint.py` (137-200), `test_scope_epic_skill.py` (128-167) — assert verbatim `ll-learning-tests check` / status-branching prose in `commands/ready-issue.md` and `skills/scope-epic/SKILL.md`; must stay in sync with any status-model wording change

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LEARNING_TESTS_GUIDE.md` — canonical guide; "Record Status: proven, refuted, stale" section (~line 97) and release-gate table (389-425) restate the three-value contract
- `docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md` — restate the `LearnTestRecord`/status field table, `check` exit-code semantics, and the `release_gate` config block
- `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/ISSUE_TEMPLATE.md`, `docs/reference/COMMANDS.md` — loop-catalog entries and verdict-mapping prose duplicate the proven/refuted/stale contract
- `commands/ready-issue.md` (250-254), `commands/refine-issue.md` (906-922), `commands/manage-release.md`, `skills/go-no-go/SKILL.md` (158-167), `skills/scope-epic/SKILL.md`, `skills/init/SKILL.md`, `skills/configure/SKILL.md` + `areas.md`, `skills/create-eval-from-issues/SKILL.md`, `skills/spike/SKILL.md` + `plan-template.md`, `skills/audit-loop-run/SKILL.md` — each independently re-implements or restates the proven/stale/refuted/missing branching; keep consistent with whichever option is chosen
- `.gemini/skills/confidence-check/*`, `.kimi-code/skills/confidence-check/*`, `.gemini/skills/explore-api/SKILL.md`, `.kimi-code/skills/explore-api/SKILL.md` — git-tracked adapter mirrors (ENH-2996 pattern) with no drift test for confidence-check/explore-api (only wire-issue's own mirror is test-enforced); editing the primary skill/rubric files without re-running the adapter leaves these silently stale

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1032-1083` — `learning_tests` block (`stale_after_days`, `discoverability.mode`, `release_gate`); Option B/C's new status value or `has_failing_assertions` flag has no schema slot today
- `.ll/ll-config.json` — project-level `learning_tests` config, review defaults if a new gate mode is added

## Related Issues

- ENH-2214 — release gate blocking on stale/refuted records
- ENH-3073 — staleness policy for the same registry

## Status

Done. Implemented Option A ("surface, don't gate") as recommended in Proposed Solution.

## Resolution

Implemented **Option A**: status semantics (`proven`/`refuted`/`stale`) are unchanged;
failing claims are surfaced at every point a human or gate reads a record, without
gating on them.

- `LearnTestRecord.failing_claims()` (`learning_tests/__init__.py`) derives the list of
  `result: fail` claim text independent of `status`.
- `ll-learning-tests check` (`cli/learning_tests.py::cmd_check`) adds a `failing_claims`
  count to its JSON output and prints the failing claim text to stderr when any exist.
- `skills/confidence-check/rubric.md` adds a `−5` scoring row for a `learning_tests_required`
  target that is `proven` with `failing_claims > 0`, and Phase 1.5's fetch script surfaces
  the count in the injected Learning Test Context table's Notes column.
- `docs/reference/CLI.md` and `docs/guides/LEARNING_TESTS_GUIDE.md` document the new field.
- `.ll/learning-tests/pytest.md`'s `claim3` (`--strict-markers` + unregistered marker) was
  re-verified directly (`python -m pytest --strict-markers` against an unregistered
  marker exits 2 with a collection error) — the claim is true; the original `fail` was a
  probe artifact (the proof script read `rc=0` instead of the real exit code). Corrected to
  `result: pass`; `raw/pytest.txt` updated with a note explaining the correction.

**Option B** (deriving/validating `status` from `assertions`, adding a `partial` state) is
deferred — the issue explicitly recommended A now, B as a separate decision. The 8+
string-equality call sites, `fsm/executor.py`, hook gates, and `release_gate.py` are
unaffected because status semantics did not change.

AC2 ("a test asserts a `proven` record with ≥1 failing assertion is distinguishable from
one with none") is satisfied at the CLI boundary: `test_check_surfaces_failing_claims_on_proven_record`
and `test_check_proven_record_with_no_failures_is_distinguishable` in
`scripts/tests/test_cli_learning_tests.py`, plus unit coverage in
`scripts/tests/test_learning_tests.py::TestLearnTestRecord`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-05_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 59/100 → LOW

### Concerns
- Remedy option (A/B/C) is explicitly undecided in the issue body; Criterion 2 and the
  outcome-confidence Complexity/Change Surface scores assume the recommended minimal
  Option A footprint, not Option B/C's larger blast radius (8+ status-check call sites,
  `Literal` type change, `skills/explore-api/SKILL.md` re-spec).
- Format-check (`ll-issues format-check`) flagged `ll-learning-tests check` and
  `ll-learning-tests check --stale-aware` as stale CLI references (`stale_cli_flag`),
  capping Criterion 4 at 10 per the ENH-3047 parity/claim cap. Manual verification
  (`ll-learning-tests --help`, `ll-learning-tests check --help`) shows both are valid,
  currently-registered subcommands — this reads as a format-check false positive, but
  per skill policy the CLI-derived signal is not re-judged, so the cap is applied as-is.

### Outcome Risk Factors
- Ambiguity (Criterion C, scored 10/25): the A/B/C decision is unresolved and materially
  changes scope — Option B requires updating 8 separate string-equality call sites plus
  the `LearnTestRecord.status` `Literal` declaration and `skills/explore-api/SKILL.md`.
- Complexity (Criterion A, scored 14/25): breadth is scored assuming the wiring-pass audit
  (checking `fsm/executor.py`, `rn-implement.yaml`, `learning-tests-audit.yaml`,
  `migrate-sdk-version.yaml`, `scaffold_eval.py` for the same blind spot) surfaces
  additional touch points before the option is finalized, not just Option A's minimal
  footprint.

## Session Log
- `/ll:manage-issue` - 2026-08-06T03:44:46 - `bf103488-a31f-4dd9-a3e6-d8cbc150b2c3.jsonl`
- `/ll:ready-issue` - 2026-08-06T03:32:49 - `657c1532-4b4b-49ec-ba80-7e4debdd4dbe.jsonl`
- `/ll:confidence-check` - 2026-08-06T02:00:48 - `96c3fd03-2fac-40c0-96a7-577067bc1c31.jsonl`
- `/ll:verify-issues` - 2026-08-06T01:57:41 - `62bb44a7-83be-436c-8b10-ab0f9ad7fe0f.jsonl`
- `/ll:wire-issue` - 2026-08-06T01:55:59 - `e9e22ffe-68d7-422e-8491-1092bcde8600.jsonl`
- `/ll:refine-issue` - 2026-08-06T01:47:53 - `291de748-bfdc-4d40-8b57-e67e2eaa46a8.jsonl`
