---
id: ENH-3597
type: ENH
title: Emit a typed per-issue run record from refine-to-ready-issue
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:49Z'
completed_at: '2026-09-25T23:24:18Z'
blocks:
- ENH-3599
- ENH-3601
parent: EPIC-3565
relates_to:
- ENH-3577
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3597: Emit a typed per-issue run record from refine-to-ready-issue

## Summary

Make `refine-to-ready-issue` write one typed per-issue run record
(`${context.run_dir}/run-records/<writer>/<ID>.json`) on every terminal that has an issue,
alongside the existing `refine-terminal-class` / `refine-broke-down` files. Define the
schema and API so a second writer, ENH-3601's `prepare-issue` wrapper, can emit the same
record. Additive: no routing in either loop changes. Step A of the ENH-3577 decomposition.

## Current Behavior

The child reports its result through two ad-hoc files: `refine-terminal-class` (free-text
`proposal_unsound | gate_unmet | infra | spike_inconclusive | decision_unresolved`, absent =
`quality`) and `refine-broke-down`. Autodev infers everything else by re-reading frontmatter.
The child's `done` terminal does not mean "ready" — autodev re-checks with `check_passed`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Exact writer map for `refine-terminal-class` in `refine-to-ready-issue.yaml`: record_proposal_unsound → proposal_unsound; record_gate_unmet → gate_unmet; mark_rate_limit_infra, mark_evidence_absent_infra, mark_spike_no_verdict_infra → infra; record_spike_inconclusive → spike_inconclusive; record_decision_unresolved → decision_decision_unresolved's token is decision_unresolved; classify_terminal → quality by default, infra when any captured exit code is 143/137/124/negative or any failure_type is transient/non_recoverable/infra_retry. Nothing writes it on `done` or `no_work`, and `write_broke_down.on_error` reaches `failed` with no class written at all. `refine-broke-down` is seeded 0 by `resolve_issue` and set to 1 by `write_broke_down`.
- Terminal inventory: `done` is reached from check_outcome.on_yes, check_scores_from_file.on_yes, check_missing_artifacts.on_yes, and write_broke_down.next; `failed` from every record_*/mark_* state, write_broke_down.on_error, and classify_terminal; `no_work` only from check_issue_resolved.on_no (blank issue_id). `on_max_steps` routes to classify_terminal. `resolve_issue.on_error` goes to diagnose.

## Expected Behavior

Every child exit with an issue ID (`done`, `failed`, and `breakdown_issue` → `write_broke_down`
→ `done`) writes a JSON record:
`{writer, issue_id, outcome, child_ids, evidence_refs, legacy_class, readiness, outcome_confidence}`
where `outcome` is a `PreparationOutcome`. `no_work` is reached only when no issue ID was
supplied (`check_issue_resolved` → `no_work`), so it writes no record. Readers treat a
missing record as absent. Legacy files keep being written unchanged.

## Record location and isolation

The child runs in autodev's **shared** `run_dir` (`refine-to-ready-issue.yaml:197-199`;
`context_passthrough: true` on `refine_current`). A single fixed filename would:

- leak one issue's record into the next issue's run. This is the same bug class that
  `resolve_issue`'s `rm -f refine-terminal-class` already fixes.
- collide with the `prepare-issue` wrapper's record after ENH-3601.

Therefore:

- The path is `${context.run_dir}/run-records/<writer>/<ID>.json`, with
  `writer ∈ {refine-to-ready-issue, prepare-issue}`.
- `resolve_issue` deletes this writer's record for the current ID on entry.
- `read_run_record` returns `None` when the stored `issue_id` or `writer` does not match
  the requested one.
- ENH-3600 reads the `prepare-issue` record directly from this layout. No copy step.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Citation correction: `context_passthrough: true` is set by the caller — `refine_current` in `autodev.yaml` (~L510) — not inside `refine-to-ready-issue.yaml`; the ~L197-199 location cited above is now a comment inside `check_issue_resolved`. The merge mechanics live in `fsm/executor.py` `_execute_sub_loop`: the child context is `{**parent_context, **captured_as_context, **child_fsm.context}`, so `run_dir` is inherited and parent/child share one directory. Parent captures are flattened (`.output` becomes a plain string), which is how autodev's `captured.input` becomes the child's `context.input`.
- `resolve_issue`'s entry action (`mkdir -p ${context.run_dir}`; `rm -f` of refine-terminal-class; re-seeding refine-broke-down plus eight other counters — refine-to-ready-refine-count, -wire-done, -hedge-attempts, -reconcile-attempts, -decide-attempts, -proposal-revisions, -verify-retries, -format-fallback; removal of the proposal-revision marker) is where the per-writer record deletion must land. Note the asymmetry: autodev's `dequeue_next` clears refine-broke-down and autodev-broke-down but NOT refine-terminal-class — only `resolve_issue` does.
- `recursive-refine.yaml` also consumes `refine-broke-down` (cleared ~L217, read ~L484), so byte-identical legacy output is load-bearing beyond autodev. `spike-runs-<ID>` files are per-issue and never reset (BUG-3593) — a precedent for per-ID naming inside the shared run_dir.

## Proposed Solution

- Add `PreparationOutcome` (`ready | decomposed | cancelled | blocked | deferred | retryable_error`)
  and a `RunRecord` dataclass with `write_run_record(run_dir, record) -> Path` /
  `read_run_record(run_dir) -> RunRecord | None` in a small `little_loops` module.
- Expose a CLI writer (e.g. `ll-issues run-record write ...`) so FSM shell states don't
  hand-roll JSON.
- Call it from **every terminal-bearing path**, not a subset: the `done` paths
  (`check_outcome`, `check_missing_artifacts`, `check_scores_from_file` → `done`),
  `write_broke_down`, `classify_terminal`, **and each state whose `next`/`on_error` is
  `failed` and which writes its own terminal class** — `record_proposal_unsound`,
  `record_gate_unmet`, `mark_rate_limit_infra`, `mark_evidence_absent_infra`,
  `mark_spike_no_verdict_infra`, `record_spike_inconclusive`, `record_decision_unresolved`
  — all of which bypass `classify_terminal` (refine-to-ready-issue.yaml:1551's own
  comment enumerates them). Each call passes the legacy class that state just wrote, so
  the mapping below resolves its outcome (`decision_unresolved`/`proposal_unsound` →
  `blocked`, `spike_inconclusive`/`gate_unmet` → `deferred`, `infra` → `retryable_error`).
  This stays additive: the write rides each state's existing action — no edge is
  re-routed. A hard crash before any terminal runs leaves no record; readers already
  treat that as absent.
- Mapping, first match wins:
  1. The issue's frontmatter `status` is `cancelled` at terminal time (closed during
     verify/refine) → `cancelled`.
  2. broke-down → `decomposed`.
  3. `infra`/rate-limit → `retryable_error`.
  4. `decision_unresolved`, `proposal_unsound`, `quality` → `blocked`.
  5. `spike_inconclusive`, `gate_unmet` → `deferred`.
  6. `done` → `ready` only when `ll-issues check-readiness --honor-waiver` passes with
     fresh scores (the predicate autodev's `check_passed` uses). Otherwise `blocked`.
- `writer` is a required field. The record schema and `write_run_record` belong to both
  writers, not to the child alone.
- Mirror the record write in `.claude/workflows/refine-to-ready.js`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Record-module convention: a module-level write_/read_ function pair whose read is tolerant (absent file, malformed JSON, OSError all → None) is the established shape — `scripts/little_loops/ab_writer.py` write_ab_json/read_ab_json (FEAT-1790) is the closest analog; serialized dataclasses carry hand-written to_dict/from_dict pairs with conditional-key presence (decisions.py:88-100). For the outcome vocabulary, Literal[...] fields dominate on frozen dataclasses (advisor.py:81, observability/schema.py), while closed machine-readable reason codes use a plain string-valued Enum (issue_lifecycle.py DeferReason/ClosureReason); StrEnum is deliberately unused repo-wide (issue_lifecycle.py:126-128).
- Atomic writes outside `fsm/` import the shared helper `atomic_write_json` from `little_loops.file_utils` (creates parent dirs, round-trip validates before rename) — decisions.py:426 and advisor.py:400 are precedent call sites. Hand-rolled mkstemp+os.replace lives only inside `fsm/`.
- `ll-issues` registration is three touchpoints in `cli/issues/__init__.py`: the `add_<name>_parser(subs)` call inside `main_issues()`'s parser build (~L779 pattern), the dispatch `if args.command == "<name>"` branch (~L1087 pattern), and the epilog Sub-commands help line (~L133-169). One module per subcommand under `scripts/little_loops/cli/issues/`, docstring opening `ll-issues <name>: ... (ISSUE-ID)`, with `add_config_arg(p)` always added. Sibling precedents: spike_verdict.py (BUG-3592), arm_proposal_revision.py (BUG-3574), check_gate.py (ENH-3575).
- The `ready` mapping's predicate is exactly `cmd_check_readiness` (`cli/issues/check_readiness.py`): exit 2 = issue not found, exit 3 = SCORES_ABSENT (checked before any threshold comparison, waiver-independent), exit 1 = threshold fail, exit 0 = pass; `--honor-waiver` swaps `meets_outcome` for `meets_outcome_or_waived` (true when `outcome_gate_waived` is set). Thresholds resolve explicit `--readiness`/`--outcome` → `commands.confidence_gate` in `.ll/ll-config.json` → 85/65. Scores are read fresh from frontmatter via `parse_frontmatter(..., coerce_types=True)`.
- Docs/gates: a new subcommand needs a `#### ll-issues run-record` section under CLI.md's ll-issues Subcommands list, an API.md module-table row, and hand-curated rows in `test_wiring_reference_docs.py` DOC_STRINGS_PRESENT; the `test_doc_counts.py` entry-point gate will not fire (no new entry point), and no epilog/subcommand sync test exists. `scripts/tests/data/loop_interpolation_baseline.json` pins refine state names — new states or changed actions may require regenerating that baseline.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `scripts/little_loops/cli/issues/` (writer subcommand)
- `.claude/workflows/refine-to-ready.js` (gitignored, machine-local mirror of the loop)

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — `skip_inflight` (~L571) is the **only** loop reader of `refine-terminal-class` (`CLASS=$(cat ... || printf 'quality')`); byte-identical legacy output is load-bearing for its infra-vs-quality split. `copy_broke_down` (~L642) copies `refine-broke-down` → `autodev-broke-down`; `dequeue_next` (:107) clears it (but not the terminal class)
- `scripts/little_loops/loops/recursive-refine.yaml` — also subloops refine-to-ready-issue (`loop: refine-to-ready-issue` at :237); consumes `refine-broke-down` (:217 clear, :484 read)

### Tests
- New unit tests for the record schema/round-trip
- Real-FSM test: each child terminal writes a record whose `outcome` matches the mapping
- `scripts/tests/test_builtin_loops.py` (structural)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `MR11_MARKER_ALLOWLIST` (:21037) and the captured-key allowlist (:21129-21167, incl. `captured.check_outcome.*`): new `capture:` keys or lint markers on added states/actions require allowlist additions. Interp-sweep scope: `loop_interpolation_baseline.json` records only `${...}` tokens inside **Python bodies** (`interp_sweep.py:37-48`) — a plain `ll-issues run-record write` shell action creates no site; the JSON is hand-maintained in-commit (no regen CLI; `test_completeness_guard` :20974 is bidirectional)
- Byte-identity pins: `test_builtin_loops.py:1993` (`read_text() == "gate_unmet"` byte-exact); `test_resolve_issue_does_not_reset_spike_counter` (`test_spike_verdict_routing.py:153`) asserts `"spike" not in` the `resolve_issue` action — the per-writer record deletion must preserve that
- Exemplars: record round-trip → `TestABJsonIO` (`test_ab_writer.py:157-216`) and `TestRecordVersionFields` (`test_learning_tests_version_staleness.py:283-299`); `cmd_` invocation → `_run` (`test_arm_proposal_revision.py:40`); state-action idioms → `TestRefineToReadyIssueSubLoop` (`test_builtin_loops.py:1434`), `_run_classify_terminal` (:2521), stub-ll-issues (`test_spike_verdict_routing.py:21-39`)
- No test pins `.claude/workflows/refine-to-ready.js` content — the mirror change is untested territory; a mirror-content test would be new
- Corpus gates for any new state: `test_all_validate_as_valid_fsm` (:77), `test_no_failure_edge_routes_to_a_success_terminal` (:87); no epilog/subcommand-enumeration test exists — mirror `test_subcommand_in_help` (`test_ll_issues_check_gate.py:157`) for the new subcommand
- Grep-noise warning: `scripts/little_loops/cli/logs.py:1110` defines an unrelated `_LoopRunRecord` (fleet-review history aggregation)

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-issues run-record` section plus the subcommand-list line (~L2234)
- `docs/reference/API.md` — Sub-commands table row under the `ll-issues` docs (~L4625-4651; check-gate row at :4648); full `## little_loops.cli.issues.<name>` sections are NOT the convention (only create/scaffold_epic/link_epics have them)
- `docs/guides/LOOPS_REFERENCE.md` — refine-to-ready-issue section: inventory row (:82), ENH-3031 gate-chain paragraph (:144), and the autodev "Notes" paragraph (~L1081) documenting the `classify_terminal` → `refine-terminal-class` contract — the run record parallels this contract; extend with record semantics

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Test idioms for the write sites, all established: run the real state action under `bash -c` with a stub `ll-issues` first on PATH (test_spike_verdict_routing.py one-line stub; test_autodev_scores_freshness.py `_interpolate`/`_run_action` ~L113-144), run the real `ll-issues` against a tmp `.issues/` tree (test_ll_issues_check_gate.py `_run_state` ~L26-51), or invoke `cmd_<name>(config, args)` directly (test_arm_proposal_revision.py:40). Routing-level assertions use a `yaml.safe_load` fixture over the loop YAML (test_builtin_loops.py `TestRefineToReadyIssueSubLoop` ~L1434), and test_builtin_loops.py:7935 `test_check_readiness_call_sites_pass_honor_waiver` pins `--honor-waiver` at every call site.
- MR-3 (`fsm/validation/meta_rules.py:202`) lints that loop shell actions write artifacts under `${context.run_dir}/` — the record path satisfies it by construction; `.issues/` and `.loops/diagnostics/` are the sanctioned exceptions.
- `.claude/workflows/refine-to-ready.js` exists but contains none of the terminal-state names (classify_terminal, check_outcome, breakdown_issue, check_issue_resolved — searched, zero hits); the mirror is structural, not state-complete. "Mirror the record write" means adding it to whatever terminal handling the mirror does have, not porting the FSM state graph.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/LOOPS_REFERENCE.md` — run-record semantics alongside the `refine-terminal-class` contract paragraphs
- Extend `MR11_MARKER_ALLOWLIST` / captured-key allowlists in `scripts/tests/test_builtin_loops.py` when adding captures or markers to the new states
- Keep the `resolve_issue` spike-counter pin green (`test_spike_verdict_routing.py:153` — no "spike" token in the action)
- Mirror note: `.claude/workflows/refine-to-ready.js` is phase-structural (`meta.phases`) — add the record write to its Finalize-phase handling, not a state port

## Program Design

### Types

- `PreparationOutcome: Literal["ready", "decomposed", "cancelled", "blocked", "deferred", "retryable_error"]` — per-issue verdict
- `RunRecordWriter: Literal["refine-to-ready-issue", "prepare-issue"]` — which loop wrote the record
- `RunRecord: dataclass` — `writer`, `issue_id`, `outcome`, `child_ids`, `evidence_refs`, `legacy_class`, `readiness`, `outcome_confidence`

### Signatures

- `write_run_record(run_dir: Path, record: RunRecord) -> Path` — writes `run-records/<writer>/<ID>.json` atomically
- `read_run_record(run_dir: Path, writer: RunRecordWriter, issue_id: str) -> RunRecord | None` — returns `None` when absent, malformed, or the stored writer/issue_id mismatch
- `cmd_run_record_write(config: BRConfig, args: argparse.Namespace) -> int` — `ll-issues run-record write` subcommand used by FSM shell states
- `outcome_from_legacy_class(legacy_class: str | None, broke_down: bool, thresholds_met: bool, status: str | None) -> PreparationOutcome` — the mapping above

### Call Path

`main_issues` -> `cmd_run_record_write` -> `outcome_from_legacy_class` -> `write_run_record`

`refine-to-ready-issue.yaml:classify_terminal` -> `cmd_run_record_write`

`refine-to-ready-issue.yaml:{record_proposal_unsound, record_gate_unmet, mark_rate_limit_infra, mark_evidence_absent_infra, mark_spike_no_verdict_infra, record_spike_inconclusive, record_decision_unresolved, write_broke_down, check_outcome, check_missing_artifacts, check_scores_from_file}` -> `cmd_run_record_write`

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - new record module, writer CLI, and a write at every child terminal
- **Risk**: Low - additive; no routing changes
- **Breaking Change**: No

## Scope Boundaries

- No routing changes in `autodev.yaml` or any other caller; consumers adopt the record in ENH-3599 / ENH-3601 / ENH-3600.
- Legacy files are not removed here.

## Acceptance Criteria

- [x] Every terminal of `refine-to-ready-issue` that has an issue ID writes a valid run record; `no_work` writes none
- [x] `outcome == "ready"` iff autodev's `check_passed` would pass for the same issue state
- [x] Running two issues in one shared `run_dir` never lets issue A's record be read as issue B's (real-FSM test)
- [x] The schema and writer accept `writer: prepare-issue` (unit test), ready for ENH-3601
- [x] Legacy `refine-terminal-class` / `refine-broke-down` output is byte-identical to before
- [x] No routing change in `autodev.yaml` or any other caller
- [x] The record write is mirrored in `.claude/workflows/refine-to-ready.js` (Finalize-phase handling)

## Verification Notes

**Verdict at time of check: PROPOSAL_UNSOUND** — resolved 2026-09-25 by a bounded design revision (same session): the call-site bullet in `## Proposed Solution` now enumerates every terminal-bearing path (the seven `record_*`/`mark_*` states that bypass `classify_terminal`, verified as the complete `next/on_error: failed` set at refine-to-ready-issue.yaml:720/1204/1275/1299/1310/1320/1342/1377/1614), the Program Design Call Path lists them, and a mirror AC was added for `.claude/workflows/refine-to-ready.js`. The mechanism was never refuted; only the call-site enumeration was incomplete. Re-verify with `/ll:verify-issues ENH-3597 --check` to persist a fresh verdict.

All claims about current state verified accurate — every code/test/doc citation was spot-checked: the `refine-terminal-class` writer map and terminal inventory in `refine-to-ready-issue.yaml` (done via `check_outcome`/`check_missing_artifacts`/`check_scores_from_file` `.on_yes`, `write_broke_down.next`; `no_work` only from `check_issue_resolved.on_no`; `on_max_steps` → `classify_terminal`); `resolve_issue`'s entry action (rm + 9 seeded counters + proposal-revision marker removal); autodev `refine_current:510`/`context_passthrough:534`, `skip_inflight` class read (~L570), `copy_broke_down:641`, `dequeue_next` clearing `refine-broke-down` at :107 but not the class; `recursive-refine.yaml` :217/:237/:484; `fsm/executor.py` `_execute_sub_loop` context merge (:1148); `ab_writer.py` write/read pair; `decisions.py:88-100`; `advisor.py:81`; `issue_lifecycle.py` StrEnum note (:124-129, `DeferReason`:65/`ClosureReason`:98); `atomic_write_json` (`file_utils.py:70`; call sites `decisions.py:426`, `advisor.py:400`); `cli/issues/__init__.py` registration touchpoints (:779/:1087/epilog) and sibling modules; `check_readiness` exit-code contract (2/3/1/0, `--honor-waiver` → `meets_outcome_or_waived`) matching autodev `check_passed:666`'s predicate; all test-file line cites (`test_builtin_loops.py` :77/:87/:1434/:1993/:2522/:7935/:20974/:21037/:21129-21167, spike-routing :153, `TestABJsonIO:157`, `TestRecordVersionFields:283`, arm-proposal `_run:40`, check-gate `test_subcommand_in_help:157`, scores-freshness `_interpolate:113`/`_run_action:125`, `meta_rules.py:202`); `cli/logs.py:1110` `_LoopRunRecord`; `.claude/workflows/refine-to-ready.js` exists with zero terminal-state names; docs cites (CLI.md ~L2234, API.md :4648, LOOPS_REFERENCE.md :82/:144/~L1081). Evidence-quote check (`ll-verify-evidence`): clean. Graph: codegraph, stale — every conclusion was confirmed by direct read; none graph-originated. Dependencies: backlinks present in ENH-3599, ENH-3601, EPIC-3565, and ENH-3577's decomposition note; no cycles. No completed-issue match; no regression analysis applicable. Active required decision rules: none.

**B6 proposal-consequence finding (drives the verdict)**: the Proposed Solution's call-site list — "Call it from `classify_terminal`, `write_broke_down` and the `done` paths" — does not cover the `failed` terminals reached directly from `record_proposal_unsound`, `record_gate_unmet`, `mark_rate_limit_infra`, `mark_evidence_absent_infra`, `mark_spike_no_verdict_infra`, `record_spike_inconclusive`, `record_decision_unresolved` (each `next: failed`, bypassing `classify_terminal` — the loop's own comment at `refine-to-ready-issue.yaml:1551-1554` and this issue's Current Behavior writer map both say so). Implemented as written, those exits write no run record, contradicting the issue's own Expected Behavior ("Every child exit with an issue ID (`done`, `failed`, …)") and failing AC1 plus the Tests-section per-terminal real-FSM test. The mapping's rules 4–5 consume legacy classes (`decision_unresolved`, `proposal_unsound`, `spike_inconclusive`, `gate_unmet`) that *only* those bypassing states ever write — the mapping presumes call sites the call-site bullet omits. The fix belongs in `## Proposed Solution` (extend the call-site enumeration to the `record_*`/`mark_*` states, or a shared pre-`failed` write), which `reconcile-issue` cannot edit — hence PROPOSAL_UNSOUND rather than DIRECTIVE_DRIFT (BUG-3574). The selected mechanism (typed record + CLI writer + `run-records/<writer>/<ID>.json` layout) is not refuted.

Secondary gap (not verdict-driving): `.claude/workflows/refine-to-ready.js` is a Files-to-Modify integration point with no corresponding Acceptance Criterion (the research itself notes no test pins the mirror).

Citation nits (no action needed): `_run_classify_terminal` sits at `test_builtin_loops.py:2522` (decorator at :2521); `dequeue_next`'s state header is at `autodev.yaml:88` with the `rm -f refine-broke-down` at :107 — both resolve unambiguously as cited.

## Resolution

- **Action**: improve (implement)
- **Completed**: 2026-09-25
- **Status**: Completed

### Changes Made

- `scripts/little_loops/run_record.py` (new): `PreparationOutcome`/`RunRecordWriter` Literals, frozen `RunRecord` dataclass with `to_dict`/`from_dict`, `record_path`, atomic `write_run_record`, tolerant `read_run_record` (None on absent/malformed/OSError/writer-or-issue mismatch), and the first-match-wins `outcome_from_legacy_class` mapping.
- `scripts/little_loops/cli/issues/run_record.py` (new): `ll-issues run-record write` — gathers frontmatter status/scores, the `refine-broke-down` counter, and children derived from `parent:` frontmatter (autodev `detect_children`'s provenance); `ready` resolved in-process via `readiness_status` with the waiver honored and scores-absent counting as not-met; prints `[RUN_RECORD_WRITTEN] <ID> <outcome> <path>`; exit 2 on unresolvable ID.
- `scripts/little_loops/cli/issues/__init__.py`: registers the subcommand (import, parser build, dispatch, epilog line).
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: `resolve_issue` now computes the ID in-shell and deletes this writer's `<ID>.json` on entry (stdout unchanged); all 11 terminal-bearing states (seven `record_*`/`mark_*`, `classify_terminal`, `write_broke_down`, `check_outcome`, `check_scores_from_file`, `check_missing_artifacts`) append an exit-code-neutral `ll-issues run-record write … || true`; the done-path gates write only on their done-bound (exit-0) exit with the gate's exit code preserved. No edges re-routed; legacy files byte-identical.
- `.claude/workflows/refine-to-ready.js` (gitignored mirror): Finalize phase gained a `run-record:<ID>` step that runs the same CLI write and reports the `[RUN_RECORD_WRITTEN]` line.
- `scripts/tests/test_run_record.py` (new, 82 tests): round-trip/isolation/mapping units, real-CLI tests against a tmp `.issues/` tree (incl. `ready` iff `check-readiness --honor-waiver` exits 0, waiver, scores-absent, cancelled-precedence, child derivation, `prepare-issue` writer), YAML call-site structure, real state-action execution per terminal (legacy byte-identity pins included), and the skip-when-absent mirror test.
- `scripts/tests/test_wiring_reference_docs.py`: five DOC_STRINGS_PRESENT rows for the new docs.
- `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md`: `ll-issues run-record` section + tables + the **Typed run record (ENH-3597)** contract paragraph.

### Verification Results

- Tests: PASS — `python -m pytest scripts/tests/` → 26003 passed, 60 skipped, 1 pre-existing failure (`test_issue_parser.py::TestBug3295ContainmentCorpusDifferential` corpus-count baseline), proven unrelated by re-running with this change stashed: it is caused by other in-flight working-tree `.issues/` edits (FEAT-3589/3594, ENH-3602), not by ENH-3597.
- Lint: PASS — `ruff check` clean on every touched file (16 pre-existing errors in untouched `cli/loop/`/spike-test files remain, per known main drift).
- Types: PASS — `python -m mypy scripts/little_loops/` reports no errors in any touched file (88 pre-existing errors in untouched files).
- Run: `ll-loop validate refine-to-ready-issue` → valid; `ll-issues run-record --help` lists `write`.
- Integration: PASS — reuses `readiness_status`, `_resolve_issue_id`, `atomic_write_json`; no routing changes anywhere; `MR11_MARKER_ALLOWLIST` untouched (all new `${captured.*}` refs are `:shell`-suffixed or single-quoted).

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, applied 2026-09-25): After ENH-3601 (Option B) autodev re-enters the `prepare-issue` wrapper, not `refine-to-ready-issue` directly. The wrapper's record is authoritative. The body now defines both writers (`writer` field) and a per-writer, per-ID path (`run-records/<writer>/<ID>.json`) that ENH-3600 reads directly.


## Session Log
- `/ll:manage-issue` - 2026-09-25T23:24:17 - `7b789d67-fc48-44f9-855e-6fe5312352e1.jsonl`
- `/ll:confidence-check` - 2026-09-25T22:29:31 - `b8c40ebf-16af-4b02-99b1-152fd47cd2b8.jsonl`
- `bounded design revision (PROPOSAL_UNSOUND remediation)` - 2026-09-25T22:25:11 - `3888403c-6bad-4d3f-8a59-c1af5a2bbcd2.jsonl`
- `/ll:verify-issues` - 2026-09-25T22:20:36 - `3888403c-6bad-4d3f-8a59-c1af5a2bbcd2.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:22:43 - `345d0814-f8e9-469f-ad62-bef9083d17be.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:51:15 - `85e4cae3-0d07-49cf-9a70-1d94df7e46ab.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:50:11 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:19 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
