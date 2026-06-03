---
id: FEAT-1813
title: "`migrate-sdk-version` FSM loop \u2014 re-prove stale learning-test records"
type: FEAT
priority: P3
status: done
captured_at: '2026-05-30T21:35:04Z'
completed_at: '2026-06-03T02:25:19Z'
discovered_date: '2026-05-30'
discovered_by: capture-issue
parent: EPIC-1694
depends_on:
- FEAT-1739
relates_to:
- EPIC-1694
- FEAT-1739
- FEAT-1287
- FEAT-1286
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1813: `migrate-sdk-version` FSM loop — re-prove stale learning-test records

## Summary

Add `scripts/little_loops/loops/migrate-sdk-version.yaml` — an FSM loop that is
the counterpart to `learning-tests-audit` (FEAT-1739). After audit marks
records stale on dependency bumps, this loop iterates the stale set,
re-runs `/ll:explore-api` against each target with current installed package
versions, and classifies each result as `still-valid` (re-prove without
changes), `needs-upgrade` (assertion bodies drifted but API contract is
intact), or `refuted` (API broke). The loop then updates `LearnTestRecord`
fields (`date`, `assertions`, `status`) atomically.

## Current Behavior

`ll-learning-tests mark-stale` exists as a CLI command
(`scripts/little_loops/cli/learning_tests.py:cmd_mark_stale`), and FEAT-1739
automates marking when registries publish newer versions than the record's
`date`. But there is no automated path from "marked stale" to "re-proven."
Today a developer must:

1. Run `ll-learning-tests list` to find every stale record.
2. Hand-invoke `/ll:explore-api "<target>"` for each one.
3. Manually decide whether the new record is the same shape, an upgrade, or
   a refute.
4. Manually clean up any drift between old assertions and the re-proven ones.

Note: `ll-learning-tests list` (`scripts/little_loops/cli/learning_tests.py:cmd_list`)
outputs a JSON array of all records with no `--status` filter flag — the loop
must apply an inline Python filter to isolate `status: stale` entries.

This is exactly the bulk loop FEAT-1739 sets up demand for. Without it,
"stale" is a sticker, not a workflow — and the registry's health degrades
as soon as more than a handful of records are stale at once.

## Expected Behavior

```bash
ll-loop run migrate-sdk-version
# or scoped:
ll-loop run migrate-sdk-version --context targets="anthropic,@anthropic-ai/sdk"
```

The loop:

1. `list_stale` (shell) — calls `ll-learning-tests list` then filters via an
   inline Python script to records with `status: stale` (no CLI flag available).
   Writes one target per line to
   `${context.run_dir}/migrate-sdk-version-queue.txt`. Empty → terminal
   `done_empty`.

2. `reprove_next` (shell) — pops the head of the queue file using the
   `head -1` / `tail -n +2` / `mv` idiom (same as
   `oracles/implement-issue-chain.yaml:implement_next`). Reads the old record
   via `ll-learning-tests check "$TARGET"` before re-proving. Then calls
   `ll-action invoke explore-api --args "$TARGET"` to re-explore. **Important**:
   `ll-action` returns an NDJSON event stream — it does not return the record.
   The skill writes the new `LearnTestRecord` to disk at
   `.ll/learning-tests/<slug>.md` via `write_record()` in
   `scripts/little_loops/learning_tests.py`. After `ll-action` completes, the
   state calls `ll-learning-tests check "$TARGET"` again to read the new record
   back. Outputs `{"target": "...", "old": {...}, "new": {...}}` for the next state.

3. `classify_outcome` (prompt) — receives the old and new records from
   `captured.reprove.output`, compares them: same assertions and pass/fail map →
   `still-valid`; same API shape but extra assertions or version drift →
   `needs-upgrade`; any previously-passing assertion now `fail` or `refuted` →
   `refuted`. Emits `CLASSIFY_JSON:{"verdict": "still-valid"|"needs-upgrade"|"refuted"}`
   on the last line of the response.

4. `apply_update` (shell) — parses `CLASSIFY_JSON:` via reverse-scan (see
   `oracles/enumerate-and-prove.yaml:parse_enumeration`). For `refuted`,
   additionally calls `update_frontmatter(content, {"status": "refuted"})` from
   `scripts/little_loops/learning_tests.py`. Note: `LearnTestRecord` has no
   `versions` field — the only fields updated are `date`, `assertions`, and
   `status`.

5. `advance_queue` (shell) — checks queue file with `wc -l`; non-empty →
   back to `reprove_next`; empty → `prepare_report_path`.

6. `prepare_report_path` (shell) + `build_report` (prompt) — follows
   `learning-tests-audit.yaml` exactly. `prepare_report_path` echoes
   `${context.run_dir}/report-$(date +%Y-%m-%dT%H%M%S).md` into
   `capture: report_path` with `next: build_report`. `build_report` uses
   `fragment: llm_gate` to write a four-section markdown report (re-proven,
   upgraded, refuted, per-record diffs) using the Write tool.

7. `done` (terminal).

## Use Case

**Who**: A developer maintaining a project that depends on versioned SDKs (e.g., the Anthropic Python SDK or `@anthropic-ai/sdk`)

**Context**: After FEAT-1739's audit marks learning-test records stale following a dependency bump, the developer needs to bulk re-prove those records against the current installed versions rather than manually invoking `/ll:explore-api` for each one.

**Goal**: Run `ll-loop run migrate-sdk-version` to re-prove all stale records in a single automated pass.

**Outcome**: The loop processes the full stale queue, classifies each record as `still-valid`, `needs-upgrade`, or `refuted`, updates the registry atomically, and produces a triage report — letting the developer focus on the `refuted` regressions that require code changes.

## Motivation

- **Closes the loop after FEAT-1739.** Audit marks stale; migrate re-proves.
  Without both, the registry rots whenever dependencies bump.
- **Bulk-friendly.** Manual re-exploration scales poorly past ~3 stale
  records. The loop runs them in a queue with a single report at the end.
- **Three-way classification surfaces real regressions.** Distinguishing
  "API shape unchanged but version bumped" from "API broke" is the signal
  that matters at sprint planning — refuted records need code changes, not
  just record updates.

## Proposed Solution

The state graph follows the queue-driven shell pattern from
`learning-tests-audit.yaml` — not `ready-to-implement-gate.yaml`, which was
refactored in ENH-1741 to use `type: learning` states and no longer uses the
shell-level queue idiom. Structural patterns to reuse directly:

- **Queue seed**: filter `ll-learning-tests list` JSON output via `python3 -c
  "import json,sys; records=json.load(sys.stdin); [print(r['target']) for r in records if r['status']=='stale']"`,
  write to `${context.run_dir}/migrate-sdk-version-queue.txt`
- **Queue pop**: `head -1` / `tail -n +2` / `mv` idiom (see
  `oracles/implement-issue-chain.yaml:implement_next`; use `fragment: shell_exit`
  with `capture: current_target`)
- **Re-exploration**: call `ll-action invoke explore-api --args "$TARGET"` via
  `subprocess.run(["ll-action", "invoke", "explore-api", "--args", target], ...)` inside
  a Python heredoc (see `assumption-firewall.yaml` lines 142–146 for the Python
  subprocess form); then call `ll-learning-tests check "$TARGET"` to retrieve
  the written record
- **Classification**: tagged-line prompt (`CLASSIFY_JSON:{...}` on the last line)
  + `output_contains` evaluator + reverse-scan parse shell state (see
  `oracles/enumerate-and-prove.yaml:parse_enumeration` for the exact Python)
- **Record write**: `write_record()` in `scripts/little_loops/learning_tests.py`
  overwrites by slug unconditionally; `update_frontmatter()` for status-only
  changes (e.g., marking `status: refuted`)
- **Report**: copy `learning-tests-audit.yaml:prepare_report_path` +
  `build_report` verbatim; both states already handle `${context.run_dir}`

Top-level YAML header (following `learning-tests-audit.yaml` conventions):

```yaml
name: migrate-sdk-version
category: api-adoption
description: >
  Re-proves stale learning-test records after a dependency bump, classifying
  each as still-valid, needs-upgrade, or refuted, and producing a triage report.
initial: list_stale
max_iterations: 50
timeout: 7200
on_handoff: spawn
import:
  - lib/common.yaml
context:
  targets: ""   # optional comma-separated filter; empty = process all stale records
```

## Implementation Steps

1. **Create `scripts/little_loops/loops/migrate-sdk-version.yaml`** with the
   7-state FSM. For `list_stale`: call `ll-learning-tests list`, pipe output
   through `python3 -c "import json,sys; records=json.load(sys.stdin);
   [print(r['target']) for r in records if r['status']=='stale']"`, write to
   `${context.run_dir}/migrate-sdk-version-queue.txt`. Use `evaluate.type:
   exit_code` (exit 0 = queue non-empty, 1 = empty).

2. **Implement `reprove_next`** (shell state with `fragment: shell_exit`):
   - Read old record: `OLD=$(ll-learning-tests check "$TARGET" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)))")`
   - Pop target via `head -1` / `tail -n +2` / `mv` on queue file (copy from
     `oracles/implement-issue-chain.yaml:implement_next`)
   - Call `ll-action invoke explore-api` via Python subprocess (not shell string
     — use the form from `assumption-firewall.yaml:record_untestable` lines 142–146)
   - Read new record: `NEW=$(ll-learning-tests check "$TARGET" ...)`
   - Output `{"target": "...", "old": {...}, "new": {...}}` for `classify_outcome`

3. **Write `classify_outcome` prompt state**: receive old+new records from
   `${captured.reprove.output}`; instruct LLM to emit `CLASSIFY_JSON:{"verdict":
   "still-valid"|"needs-upgrade"|"refuted"}` on the last line; use `evaluate:
   type: output_contains, pattern: "CLASSIFY_JSON:"` (not `llm_structured` —
   avoids MR-1 meta-loop constraint since the tagged-line pattern is sufficient).

4. **Implement `apply_update`** (shell state): parse `CLASSIFY_JSON:` via
   reverse-scan (copy `parse_enumeration` from
   `oracles/enumerate-and-prove.yaml`). For `refuted` verdict, call
   `python3 -c "from little_loops.learning_tests import update_frontmatter, ..."` to
   set `status: refuted`. Output per-record result JSON accumulating into
   a list for `build_report`.

5. **Implement `advance_queue`**: `wc -l < ${context.run_dir}/migrate-sdk-version-queue.txt`;
   exit 0 if `> 0` (route `on_yes: reprove_next`), exit 1 if empty (route
   `on_no: prepare_report_path`).

6. **Copy `prepare_report_path` + `build_report`** from
   `learning-tests-audit.yaml` verbatim; update the report prompt to summarize
   the three outcome categories: still-valid, needs-upgrade, refuted.

7. **Register the loop**: add `"migrate-sdk-version"` to the `expected` set in
   `scripts/tests/test_builtin_loops.py:TestBuiltinLoopFiles.test_expected_loops_exist`
   (line 67). The test does `BUILTIN_LOOPS_DIR.glob("*.yaml")` set equality —
   `BUILTIN_LOOPS_DIR` is `scripts/little_loops/loops/` (line 17). Only top-level
   YAML files count; `lib/` and `oracles/` subdirs are excluded automatically.

8. **Validate**: run `ll-loop validate migrate-sdk-version` and confirm no
   ERRORs. Run `python -m pytest scripts/tests/test_builtin_loops.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/little_loops/loops/README.md` — add a `migrate-sdk-version` row to the hand-maintained `## API Adoption` table (match `learning-tests-audit` row format)
10. Write `TestMigrateSdkVersionLoop` structural test class in `scripts/tests/test_builtin_loops.py` — follow `TestLearningTestsAuditLoop` (line 507) as template; verify required states: `list_stale`, `reprove_next`, `classify_outcome`, `apply_update`, `advance_queue`, `prepare_report_path`, `build_report`, `done`, `done_empty`; assert `classify_outcome` uses `output_contains` evaluator with `"CLASSIFY_JSON:"` pattern; assert `list_stale` action contains `${context.run_dir}`
11. Update `docs/ARCHITECTURE.md` — `### CLI Surface` within `## Learning Test Registry` (line 1241): extend the `ll-loop run learning-tests-audit` reference sentence to name `migrate-sdk-version` as the counterpart re-prove step in the same two-step workflow
12. Add `CHANGELOG.md` entry — `### Added` block: `- **\`migrate-sdk-version\` loop** — FSM loop for bulk re-proving stale learning-test records after a dependency bump. (FEAT-1813)`

## Scope Boundaries

- **In scope**: Bulk re-exploration of stale records; three-way
  classification; updating `LearnTestRecord` with new `date` / `assertions` /
  `status`; a triage report.
- **Out of scope**: Cross-package migration (e.g. moving from SDK A to a
  forked SDK B — that's a manual decision); manual diff review of every
  assertion change (audit-loop's report and this loop's report give
  triage, but the developer still owns merging into code); generating
  codemods to update callers when assertions drift.
- **No `versions` field**: `LearnTestRecord` (`scripts/little_loops/learning_tests.py`)
  does not have a `versions` field — only `target`, `date`, `status`,
  `assertions`, and `raw_output_path` are serialized. Any reference to bumping
  `versions` in earlier drafts was incorrect.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/migrate-sdk-version.yaml` (new — FSM loop definition)
- `scripts/tests/test_builtin_loops.py` — add `"migrate-sdk-version"` to `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist()` (line 67)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — add `migrate-sdk-version` row to hand-maintained `## API Adoption` table [Agent 2]
- `CHANGELOG.md` — add `### Added` entry for the new loop under the current release block [Agent 2]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/learning_tests.py:cmd_list` — called by `list_stale` via `ll-learning-tests list`
- `scripts/little_loops/cli/learning_tests.py:cmd_check` — called by `reprove_next` (before and after `ll-action invoke`) via `ll-learning-tests check "<target>"`
- `scripts/little_loops/cli/learning_tests.py:cmd_mark_stale` — called by `apply_update` for `refuted` records
- `scripts/little_loops/cli/action.py:cmd_invoke` — called by `reprove_next` via `ll-action invoke explore-api`
- `scripts/little_loops/learning_tests.py:write_record` — overwrites record by slug unconditionally; called by `explore-api` skill during reprove
- `scripts/little_loops/learning_tests.py:update_frontmatter` — used for status-only field patches (e.g., marking `refuted`)
- `scripts/little_loops/learning_tests.py:LearnTestRecord` — schema: `target` (str), `date` (str ISO), `status` (`proven`|`refuted`|`stale`), `assertions` (list of `Assertion` with `claim`+`result`), `raw_output_path` (str|None)
- `scripts/little_loops/learning_tests.py:list_records` — underlying function behind `ll-learning-tests list`

### Similar Patterns
- `scripts/little_loops/loops/learning-tests-audit.yaml` — sibling queue-driven loop; reuse `list_records`, `mark_stale_candidates`, `prepare_report_path`, and `build_report` state patterns directly
- `scripts/little_loops/loops/lib/common.yaml:queue_pop` — fragment supplying `action_type: shell` + `evaluate.type: exit_code` for the head/tail/mv pop pattern
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml:implement_next` — concrete `head -1` / `tail -n +2` / `mv` pop idiom to copy for `reprove_next`
- `scripts/little_loops/loops/assumption-firewall.yaml` — `ll-action invoke explore-api` Python subprocess call (lines 142–146)
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml:parse_enumeration` — reverse-scan tagged-JSON parse state to copy for `apply_update`

### Tests
- `scripts/tests/test_builtin_loops.py` — add `"migrate-sdk-version"` to `test_expected_loops_exist` expected set (line 67)
- `scripts/tests/test_learning_tests.py` — existing tests for `write_record`, `mark_stale`, `list_records` (validate functions the loop calls)
- `scripts/tests/test_learning_state.py` — FSM `type: learning` dispatch reference (shows how `explore-api` is invoked and writes records)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — also write `TestMigrateSdkVersionLoop` structural test class following `TestLearningTestsAuditLoop` (line 507); verify all 9 required states (`list_stale`, `reprove_next`, `classify_outcome`, `apply_update`, `advance_queue`, `prepare_report_path`, `build_report`, `done`, `done_empty`); assert `classify_outcome` uses `output_contains` evaluator with `"CLASSIFY_JSON:"` pattern; assert `list_stale` action contains `${context.run_dir}` [Agent 3]

### Documentation
- `docs/guides/LOOPS_GUIDE.md` § API Adoption — document alongside `learning-tests-audit`
- `docs/guides/LEARNING_TESTS_GUIDE.md` — update registry lifecycle documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — `### CLI Surface` within `## Learning Test Registry` (line 1241): extend `learning-tests-audit` reference to include `migrate-sdk-version` as the counterpart re-prove step [Agent 2]

### Configuration
- N/A

## Acceptance Criteria

- `ll-loop validate migrate-sdk-version` reports no ERRORs.
- `python -m pytest scripts/tests/test_builtin_loops.py -v` passes with
  `"migrate-sdk-version"` added to `test_expected_loops_exist`.
- `ll-loop list` surfaces the loop.
- End-to-end smoke: with one stale record and one proven record in the
  registry, the loop re-proves only the stale one and produces a report
  listing it under either "re-proven" or "upgraded."
- End-to-end smoke: with zero stale records, the loop reaches
  `done_empty` without invoking `/ll:explore-api`.
- Queue file is written to `${context.run_dir}/migrate-sdk-version-queue.txt`
  (not `.loops/tmp/`) — `ll-loop validate` MR-3 check passes with no warnings.

## Impact

- **Priority**: P3 — Pairs with FEAT-1739 (also P3) and unblocks
  "first-class learning testing" as defined by EPIC-1694.
- **Effort**: Medium — one new loop YAML (~7 states), tests, and a small
  classification prompt. Reuses existing `ll-action invoke explore-api`
  and `LearnTestRecord` write path.
- **Risk**: Low — additive loop; no changes to existing loops, schema, or
  CLI.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/LEARNING_TESTS_GUIDE.md` | Documents the registry lifecycle this loop participates in |
| `docs/guides/LOOPS_GUIDE.md` § API Adoption | Where this loop will be documented alongside `learning-tests-audit` |

## Labels

`feat`, `loop`, `learning-tests`, `migration`, `staleness`, `captured`

---

**Open** | Created: 2026-05-30 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-03T02:16:48 - `00137671-8110-4649-8269-ae3d5c6f0d2e.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00 - `b0a48dc1-6a85-46f4-8764-aa2d11e6b971.jsonl`
- `/ll:wire-issue` - 2026-06-03T02:10:14 - `5180bf5e-e0da-4d9d-a534-7fe5dd2250b1.jsonl`
- `/ll:refine-issue` - 2026-06-03T02:04:27 - `ecc0aecd-eede-434b-92d3-79b8ec92833a.jsonl`
- `/ll:format-issue` - 2026-06-03T01:53:08 - `5c43b0ea-deca-4327-a3d1-d4336af7197f.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:43 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T21:35:04Z - `f3ee23bc-341c-48d2-b09f-f34e658c7031.jsonl`
