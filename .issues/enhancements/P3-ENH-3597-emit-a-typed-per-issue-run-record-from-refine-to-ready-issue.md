---
id: ENH-3597
type: ENH
title: Emit a typed per-issue run record from refine-to-ready-issue
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:49Z'
blocks:
- ENH-3599
- ENH-3601
parent: EPIC-3565
relates_to:
- ENH-3577
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
- Call it from `classify_terminal`, `write_broke_down` and the `done` paths
  (`check_outcome`, `check_missing_artifacts`, `check_scores_from_file` → `done`).
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

### Tests
- New unit tests for the record schema/round-trip
- Real-FSM test: each child terminal writes a record whose `outcome` matches the mapping
- `scripts/tests/test_builtin_loops.py` (structural)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Test idioms for the write sites, all established: run the real state action under `bash -c` with a stub `ll-issues` first on PATH (test_spike_verdict_routing.py one-line stub; test_autodev_scores_freshness.py `_interpolate`/`_run_action` ~L113-144), run the real `ll-issues` against a tmp `.issues/` tree (test_ll_issues_check_gate.py `_run_state` ~L26-51), or invoke `cmd_<name>(config, args)` directly (test_arm_proposal_revision.py:40). Routing-level assertions use a `yaml.safe_load` fixture over the loop YAML (test_builtin_loops.py `TestRefineToReadyIssueSubLoop` ~L1434), and test_builtin_loops.py:7935 `test_check_readiness_call_sites_pass_honor_waiver` pins `--honor-waiver` at every call site.
- MR-3 (`fsm/validation/meta_rules.py:202`) lints that loop shell actions write artifacts under `${context.run_dir}/` — the record path satisfies it by construction; `.issues/` and `.loops/diagnostics/` are the sanctioned exceptions.
- `.claude/workflows/refine-to-ready.js` exists but contains none of the terminal-state names (classify_terminal, check_outcome, breakdown_issue, check_issue_resolved — searched, zero hits); the mirror is structural, not state-complete. "Mirror the record write" means adding it to whatever terminal handling the mirror does have, not porting the FSM state graph.

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

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - new record module, writer CLI, and a write at every child terminal
- **Risk**: Low - additive; no routing changes
- **Breaking Change**: No

## Scope Boundaries

- No routing changes in `autodev.yaml` or any other caller; consumers adopt the record in ENH-3599 / ENH-3601 / ENH-3600.
- Legacy files are not removed here.

## Acceptance Criteria

- [ ] Every terminal of `refine-to-ready-issue` that has an issue ID writes a valid run record; `no_work` writes none
- [ ] `outcome == "ready"` iff autodev's `check_passed` would pass for the same issue state
- [ ] Running two issues in one shared `run_dir` never lets issue A's record be read as issue B's (real-FSM test)
- [ ] The schema and writer accept `writer: prepare-issue` (unit test), ready for ENH-3601
- [ ] Legacy `refine-terminal-class` / `refine-broke-down` output is byte-identical to before
- [ ] No routing change in `autodev.yaml` or any other caller

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, applied 2026-09-25): After ENH-3601 (Option B) autodev re-enters the `prepare-issue` wrapper, not `refine-to-ready-issue` directly. The wrapper's record is authoritative. The body now defines both writers (`writer` field) and a per-writer, per-ID path (`run-records/<writer>/<ID>.json`) that ENH-3600 reads directly.


## Session Log
- `/ll:refine-issue` - 2026-09-25T19:50:11 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:19 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
