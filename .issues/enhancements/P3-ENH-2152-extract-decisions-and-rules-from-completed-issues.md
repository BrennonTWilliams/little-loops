---
id: ENH-2152
type: ENH
priority: P3
status: open
title: Extract decisions and rules from completed issues into decisions.yaml
captured_at: '2026-06-14T19:15:05Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
relates_to:
- ENH-2151
confidence_score: 94
outcome_confidence: 77
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 20
---

# ENH-2152: Extract decisions and rules from completed issues into decisions.yaml

## Summary

Completed issues contain implicit decisions, architectural choices, and coding rules that were agreed upon during implementation — but this knowledge currently dies in the issue file. `decisions.yaml` (managed by `ll-issues decisions`) is the designated home for active rules that guide coding agents, yet it is only populated manually or via `ll-issues decisions generate`. This enhancement adds both a **one-shot CLI command** and an **automated extraction loop** that mine completed issues for decisions/rules and promote them into `decisions.yaml`.

## Current Behavior

Decisions and architectural constraints embedded in completed issue files are not automatically extracted. `decisions.yaml` must be populated manually via `ll-issues decisions add` or `ll-issues decisions generate`. Agents re-litigating settled tradeoffs or repeating fixed bugs have no mechanism to detect that the outcome was already decided in a prior issue.

## Expected Behavior

- `ll-issues decisions extract-from-completed [--since YYYY-MM-DD] [--issue ID] [--dry-run] [--min-confidence 0.7]` scans completed issues and appends extracted decisions/rules to `decisions.yaml`.
- `.loops/distill-decisions.yaml` runs automatically (hook-triggered or scheduled) to keep `decisions.yaml` enriched as issues complete.
- Deduplication prevents near-identical rules from accumulating across extraction runs.
- `--dry-run` prints candidates without writing, enabling review before committing.

## Motivation

When a BUG is fixed or an ENH lands, the issue often documents a constraint ("never use X pattern", "always escape Y"), a tradeoff that was settled ("we chose A over B because..."), or a rule that should govern future work. Today that context is either:
- Lost when the issue file is archived/completed
- Manually re-entered into `decisions.yaml` if the developer remembers
- Silently absent, so agents repeat the same mistake or re-litigate the same tradeoff

Systematically extracting this knowledge closes the loop between completed work and active agent guidance.

## Proposed Solution

### 1. One-Shot Command: `ll-issues decisions extract-from-completed`

```
ll-issues decisions extract-from-completed [--since YYYY-MM-DD] [--issue ID] [--dry-run] [--min-confidence 0.7]
```

- Scans completed issues (status `done`) in `.issues/` (or snapshots from `issue_snapshots` table once ENH-2151 lands)
- For each issue, sends title + body to an LLM structured extractor that returns candidate decisions/rules in the `decisions.yaml` schema
- Filters by `--min-confidence` (default 0.7); candidates below threshold are logged but not written
- With `--dry-run`, prints candidates without writing
- Deduplicates against existing `decisions.yaml` entries (fingerprint match)
- Appends accepted candidates via `ll-issues decisions add`
- Outputs a summary: N candidates found, M written, K skipped (duplicate/low-confidence)

### 2. Automated Loop: `.loops/distill-decisions.yaml`

An FSM loop that runs on a schedule (or triggered post-completion) to keep `decisions.yaml` continuously enriched:

- **States**: `scan_completed → extract_candidates → deduplicate → propose → apply → verify`
- **Trigger**: After any issue transitions to `done` (hook-driven), or run periodically via `ll-loop run distill-decisions`
- **Guard**: Only processes issues completed since the last run (checkpoint stored in loop run artifact)
- **Non-LLM evaluator** (MR-1 compliant): `exit_code` check on `ll-issues decisions list --since <ts> | wc -l` to verify new entries were actually written
- **Artifact isolation** (MR-3 compliant): checkpoint written to `${context.run_dir}/last_processed.txt`

### Extraction Prompt Shape

The LLM extractor receives:
```
Issue: [ID] - [Title]
Type: [BUG|FEAT|ENH]
Body: [full markdown body]

Extract any decisions, constraints, or rules that should guide future coding agents.
For each, return:
  - rule: (imperative sentence, ≤ 120 chars)
  - rationale: (why this rule exists, from issue context)
  - category: (architecture | testing | style | security | performance | other)
  - confidence: (0.0–1.0)
  - scope: (global | issue)
```

## Implementation Steps

1. **`ll-issues decisions extract-from-completed` sub-command** — add to `scripts/little_loops/cli/issues/decisions.py`:
   - Register parser in `add_decisions_parser()` with `--since YYYY-MM-DD`, `--issue ID`, `--dry-run`, `--min-confidence 0.7` args.
   - Add dispatch branch in `cmd_decisions()`: `elif sub == "extract-from-completed": return _cmd_extract_from_completed(config, args)`.
   - Use `scan_completed_issues_from_db()` (from `scripts/little_loops/issue_history/parsing.py`) when `.ll/history.db` exists; fallback to `scan_completed_issues()`.
   - LLM extraction: follow `evaluate_llm_structured()` pattern in `scripts/little_loops/fsm/evaluators.py` — call `resolve_host().build_blocking_json(prompt=..., model=...)`, append `["--json-schema", json.dumps(EXTRACTION_SCHEMA), "--no-session-persistence"]`, run `subprocess.run()`, parse from `envelope["structured_output"]`.
   - Promote accepted candidates using `add_entry()` from `scripts/little_loops/decisions.py`; write `RuleEntry` instances (not `DecisionEntry`) when `confidence >= --min-confidence` and rule text passes content-dedup.
2. **Deduplication** — two levels: (a) existing issue_id match against `DecisionEntry.issue` fields (same as `generate_from_completed()`); (b) content-level near-dedup: lowercase + normalize the extracted `rule` string, compare against all existing `RuleEntry.rule` values using significant-token intersection (≥ 60% overlap = duplicate). The `_cmd_suggest_rules()` token extraction logic in `decisions.py` is a reference for tokenization.
3. **`.loops/distill-decisions.yaml`** — author FSM loop following `diagnose → propose → apply → measure-externally` meta-loop shape (CLAUDE.md meta-loop rules). States: `count_baseline (shell) → scan_completed (shell) → extract_candidates (prompt) → deduplicate (shell) → apply (shell: ll-issues decisions add) → verify_count_delta`. Use `output_numeric` evaluator on JSON count delta (`ll-issues decisions list --format json | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"`) as non-LLM validator. Reference: `scripts/little_loops/loops/issue-discovery-triage.yaml:count_baseline` pattern. **Do not use `wc -l`** — text output spans 2–4 lines per entry.
4. **Hook trigger** — extend the existing `PostToolUse Write` hook in `hooks/scripts/issue-completion-log.sh` (which already detects `status: done` writes via `awk`) to also invoke `ll-issues decisions extract-from-completed --issue <ID> --min-confidence 0.8`. No new `hooks.json` entry needed — extend the existing bash handler.
5. **`ll-session backfill` integration** — add `--extract-decisions` flag to `backfill` sub-command in `scripts/little_loops/cli/session.py`; after `backfill_incremental()` completes, call `extract-from-completed --since <since_date>` (ENH-2151 dependency).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `hooks/scripts/issue-completion-log.sh` — append `ll-issues decisions extract-from-completed --issue <ID> --min-confidence 0.8 2>/dev/null || true` after the existing `append_session_log_entry` call; ensure the call is suppressed with `|| true` so hook exit code is not affected by missing binary in test environments
7. Update `docs/reference/CLI.md` — add `extract-from-completed` row to the `ll-issues decisions` sub-command table; add `--extract-decisions` row to the `ll-session backfill` flags table
8. Update `docs/guides/DECISIONS_LOG_GUIDE.md` — add `extract-from-completed` sub-command documentation alongside `generate`; add `### Automated Extraction Loop` section for `distill-decisions`
9. Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` — extend `### Issue completion log` to describe the new `extract-from-completed` call
10. Update `commands/help.md` — add `extract-from-completed` to the `decisions (...)` parenthetical
11. Verify `scripts/tests/test_hooks_integration.py::TestIssueCompletionLog::test_single_quote_in_transcript_path_appends_log` still passes with `|| true` suppression; add assertion or new test method confirming the hook fires without non-zero exit when `ll-issues` is unavailable

## Scope Boundaries

- **In scope**: `ll-issues decisions extract-from-completed` CLI sub-command; `.loops/distill-decisions.yaml` FSM loop; deduplication against existing entries; `--since`, `--issue`, `--min-confidence`, `--dry-run` flags; optional hook trigger on `done` transition; `--extract-decisions` flag for `ll-session backfill` (ENH-2151 dependency).
- **Out of scope**: Modifying or removing existing `decisions.yaml` entries (extraction appends only); integration with external issue trackers beyond `.issues/`; real-time per-keystroke extraction; UI/dashboard for reviewing extracted decisions; retroactive re-extraction of issues already processed in a prior run (covered by checkpoint guard).

## Success Metrics

- `ll-issues decisions list --format json | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"` count increases after running extraction against ≥ 5 completed issues (text output spans multiple lines per entry; `wc -l` is unreliable).
- Dedup logic: re-running extraction on the same issue set produces 0 new entries (idempotent).
- Loop checkpoint: second run of `.loops/distill-decisions.yaml` with no new completed issues exits without writing new entries.
- `--dry-run` produces candidate output without modifying `decisions.yaml` (verified via file diff).

## API/Interface

```
ll-issues decisions extract-from-completed [--since YYYY-MM-DD] [--issue ID] [--dry-run] [--min-confidence 0.7]
```

LLM extractor output schema (per candidate):
```python
{
  "rule": str,        # imperative sentence, ≤ 120 chars
  "rationale": str,   # why this rule exists (from issue context)
  "category": str,    # architecture | testing | style | security | performance | other
  "confidence": float,  # 0.0–1.0
  "scope": str        # global | issue
}
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/decisions.py` — add `extract-from-completed` sub-command (actual path; file has `cmd_decisions()` dispatcher and `add_decisions_parser()`)
- `.loops/distill-decisions.yaml` — new FSM loop to create (user loops live in `.loops/`; `resolve_loop_path()` in `scripts/little_loops/cli/loop/_helpers.py:842` searches `.loops/` before falling back to built-in `scripts/little_loops/loops/`)
- `scripts/little_loops/cli/session.py` — add `--extract-decisions` flag to `backfill` (when ENH-2151 lands)
- `hooks/scripts/issue-completion-log.sh` — extend with `ll-issues decisions extract-from-completed --issue <ID> --min-confidence 0.8 2>/dev/null || true` call after existing `append_session_log_entry` invocation (Step 4 of Implementation Steps)

### Dependent Files (Callers/Importers)
- `.ll/decisions.yaml` — output file; managed by `ll-issues decisions`
- `hooks/hooks.json` — optional hook entry to trigger extraction on `done` transition

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — imports `add_decisions_parser` and `cmd_decisions` from `decisions.py` (lines 27-30); wires the decisions sub-parser at line 691 and dispatches `ll-issues decisions` at line 750-751. No changes needed here, but any rename or signature change to `add_decisions_parser()`/`cmd_decisions()` must be reflected in this file.

### Similar Patterns
- `scripts/little_loops/cli/issues_decisions.py` — existing `generate` sub-command for LLM-based decision generation
- `loops/` — existing FSM loops for reference on MR-1/MR-3 compliance patterns

### Tests
- `scripts/tests/test_decisions.py` — add tests for `generate_from_completed`-style logic and LLM extraction (existing class: `TestGenerateFromCompleted`)
- `scripts/tests/test_cli_decisions.py` — add CLI-level tests for `extract-from-completed`, dedup, dry-run, checkpoint behavior (existing class: `test_cmd_decisions_*`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py` — add test in `TestArgumentParsing` asserting `--extract-decisions` flag parses correctly (`args.extract_decisions == False` default); follow `TestBackfillSinceFlag` pattern [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py` — `TestIssueCompletionLog::test_single_quote_in_transcript_path_appends_log` will **break** after hook extension if `ll-issues decisions extract-from-completed` is unavailable in test PATH with `set -euo pipefail`; fix by either: (a) suppressing the extraction call with `|| true` in the hook script, or (b) mocking `ll-issues` binary in the test; must verify `result.returncode == 0` still holds [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — `decisions.yaml` design section may need update
- `.claude/CLAUDE.md` — no changes needed

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-issues decisions` sub-command table (under `#### ll-issues decisions`) missing `extract-from-completed` row; `ll-session backfill` flags table missing `--extract-decisions` row [Agent 2 finding]
- `docs/guides/DECISIONS_LOG_GUIDE.md` — `## Auto-generating from History` section describes only `ll-issues decisions generate`; add parallel section for `extract-from-completed` (LLM-driven vs. structural stubs) and document the `distill-decisions` FSM loop trigger mechanism [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — `### Issue completion log` section describes hook as doing only `append_session_log_entry()`; will be incomplete after hook is extended to also call `extract-from-completed`; add a sentence describing the extraction call [Agent 2 finding]
- `commands/help.md` — parenthetical `decisions (list, add, outcome, generate, sync, suggest-rules, promote)` at line 275 does not enumerate `extract-from-completed`; add to the list [Agent 2 finding]

### Configuration
- N/A — no new config keys required

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Key discovery — `generate_from_completed()` already exists but is not LLM-driven:**
- `scripts/little_loops/decisions.py:generate_from_completed()` (called by the existing `generate` sub-command) creates skeleton `DecisionEntry` records with an empty `rule` field — it is a *structural* generator, not a semantic extractor. The new `extract-from-completed` sub-command must perform actual LLM extraction to populate `rule` with meaningful content.

**Callers and dispatch:**
- `scripts/little_loops/cli/issues/decisions.py:cmd_decisions()` dispatches on `args.subcommand`; add `elif sub == "extract-from-completed": return _cmd_extract_from_completed(config, args)` alongside the existing branches.
- `scripts/little_loops/cli/issues/decisions.py:add_decisions_parser()` registers all sub-parsers; add a new `subs.add_parser("extract-from-completed", ...)` with `--since`, `--issue`, `--dry-run`, `--min-confidence` args.

**Issue scanning (for `--since` / `--issue` filtering):**
- `scripts/little_loops/issue_history/parsing.py:scan_completed_issues_from_db()` — queries `issue_events` table `WHERE transition = 'done'`; preferred when `.ll/history.db` exists.
- `scripts/little_loops/issue_history/parsing.py:scan_completed_issues()` — filesystem scan fallback; checks `status == "done"` in frontmatter.
- `scripts/little_loops/issue_history/parsing.py:parse_completed_issue()` — parses a single issue file into a `CompletedIssue` dataclass.

**LLM invocation pattern for structured extraction:**
- `scripts/little_loops/fsm/evaluators.py:evaluate_llm_structured()` (line 1) — canonical pattern using `resolve_host().build_blocking_json(prompt=..., model=...)`, then appending `["--json-schema", json.dumps(schema), "--no-session-persistence"]` to `invocation.args`.
- Response envelope: `envelope["structured_output"]` (dict) is the primary path; fallback is `json.loads(envelope["result"])`.
- `subtype == "error_max_structured_output_retries"` signals schema-validation retry exhaustion.

**Deduplication:**
- Current `generate_from_completed()` deduplicates by exact `issue_id` string match only (`existing_issue_ids = {e.issue for e in existing if isinstance(e, DecisionEntry) and e.issue}`).
- Content-level dedup (near-identical rule text) needs to be added; the `_cmd_suggest_rules()` token-frequency approach in `decisions.py` is a reference but is read-only. Implement a fingerprint of the extracted `rule` string (e.g., lowercase + strip + set of significant tokens) and check against all existing `RuleEntry.rule` values.

**Loop count-delta evaluator:**
- `ll-issues decisions list --format json 2>/dev/null | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"` — use JSON format for accurate counts; `wc -l` is unreliable (text output spans 2–4 lines per entry).
- Pattern reference: `scripts/little_loops/loops/issue-discovery-triage.yaml:count_baseline` / `count_new` states use this delta pattern with `output_numeric` evaluator.

**Loop file location:**
- `resolve_loop_path()` in `scripts/little_loops/cli/loop/_helpers.py:842` searches `.loops/<name>.yaml` first, then falls back to built-in `scripts/little_loops/loops/<name>.yaml`. The existing user loop `.loops/ll-logs-telemetry-digest.yaml` confirms `.loops/` is the correct home for project-specific loops.

**FSM loop pattern references:**
- `scripts/little_loops/loops/issue-discovery-triage.yaml` — count-baseline → scan → count-delta pattern (closest analogue to scan_completed → extract → verify_count_delta)
- `scripts/little_loops/loops/dead-code-cleanup.yaml` — `${context.run_dir}/` checkpoint write for cross-iteration state (MR-3 compliant)
- `scripts/little_loops/loops/rn-remediate.yaml` — `type: exit_code` evaluator examples (MR-1 compliant)

**Test fixture model:**
- `scripts/tests/test_decisions.py:TestGenerateFromCompleted` — uses `unittest.mock.patch("little_loops.issue_history.parsing.scan_completed_issues", return_value=completed)` to stub scanning; model new `TestExtractFromCompleted` after this class.

## Acceptance Criteria

- [ ] `ll-issues decisions extract-from-completed --dry-run` prints candidate rules for completed issues without writing anything.
- [ ] `ll-issues decisions extract-from-completed` writes accepted candidates to `decisions.yaml` and skips duplicates.
- [ ] `--since`, `--issue`, and `--min-confidence` flags work correctly.
- [ ] `.loops/distill-decisions.yaml` passes `ll-loop validate` (no MR-1, MR-3, MR-4 violations).
- [ ] Loop checkpoint prevents re-processing already-extracted issues across runs.
- [ ] Non-LLM evaluator (decision count delta) correctly detects when no new rules were written.
- [ ] Tests cover: extraction from a fixture issue, deduplication, dry-run output, loop checkpoint behavior.

## Impact

- **Priority**: P3 — Knowledge management enhancement; not blocking current work but reduces agent drift over time.
- **Effort**: Medium — New CLI sub-command + FSM loop + LLM structured extraction + fingerprint-based dedup logic.
- **Risk**: Low — Additive feature; writes only to `decisions.yaml` (already managed by `ll-issues`); no changes to core FSM or session infrastructure.
- **Breaking Change**: No

## Labels

`enhancement`, `automation`, `decisions`, `knowledge-management`

## Status

**Open** | Created: 2026-06-14 | Priority: P3

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | `decisions.yaml` design and session store patterns |
| `.claude/CLAUDE.md` | Meta-loop authoring rules (MR-1 through MR-6) |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Loop shape guidance |

## Session Log
- `/ll:confidence-check` - 2026-06-14T20:15:34Z - `413bf450-1c8b-4a6f-9ca4-b824ce9038c6.jsonl`
- `/ll:wire-issue` - 2026-06-14T20:09:39 - `f76a9942-cc29-47cd-b1cd-b20e4d22d86a.jsonl`
- `/ll:refine-issue` - 2026-06-14T20:01:30 - `17e3b819-a92e-48b7-886a-f4c624acc236.jsonl`
- `/ll:format-issue` - 2026-06-14T19:28:42 - `acf85e7c-ff0e-4e7c-abfe-8806a1d70428.jsonl`
- `/ll:capture-issue` - 2026-06-14T19:15:05Z - (conversation context)
