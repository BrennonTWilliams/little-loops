---
id: ENH-1114
title: Intent Parameter for Large ll-* CLI Outputs
type: ENH
priority: P4
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
blocked_by: []
relates_to:
- FEAT-1112
- ENH-1111
- FEAT-1160
confidence_score: 88
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
milestone: refined-ready
parent: EPIC-1812
---

# ENH-1114: Intent Parameter for Large ll-* CLI Outputs

## Summary

Add an optional `--intent <query>` parameter to `ll-history`, `ll-deps`, `ll-scan-*`, `ll-workflows`, and similar CLIs so the full result is indexed but only the slice matching the intent is returned to the caller.

## Motivation

These CLIs today dump their entire result to stdout. A single `ll-deps` run on a mature issue set can be thousands of lines; `ll-history` analysis excerpts push the same. In loop contexts, the agent reads the full dump, even when it only needs "which issues touch FSM state machine rate limits."

Context-mode (github.com/mksglu/context-mode) calls this "intent-driven filtering": when tool output exceeds a threshold and an intent is supplied, the full result is indexed and only the relevant sections return. They report this as one of their highest-impact context reductions.

## Current Behavior

- `ll-history`, `ll-deps`, `ll-scan-*` all print full results
- No way to ask "dependency chain for FEAT-960 only" without piping through grep (which loses context)
- Output sizes routinely exceed 500 lines on real projects

## Expected Behavior

- Affected CLIs accept `--intent "<query>"` and `--intent-limit <N>` (default 50 lines)
- When `--intent` is supplied and full output >200 lines:
  - Full result written to `.ll/scratch/<cmd>-<timestamp>.txt` (or indexed into session DB once FEAT-1112 lands)
  - Ranked subset returned to stdout with a footer: `# Full output: <path> (N lines)`
- Step 1: Wire `--intent` flag into affected CLIs as a no-op pass-through (full output returned, `--intent` value captured but not used)
- Step 2: After FEAT-1112 ships, implement ranking directly against FTS5 — no interim BM25 layer
- `--intent` without a threshold hit is a no-op

## Success Metrics

- **CLI coverage**: 3+ CLIs accept `--intent`/`--intent-limit` flags (target: ll-history, ll-deps, ll-workflows)
- **Output reduction**: Intent-filtered output is measurably shorter than full output (`wc -l` comparison)
- **No tech debt**: Zero `ranking.py` or BM25 files created; ranking uses FTS5 exclusively
- **Docs updated**: `.claude/CLAUDE.md` and `docs/reference/API.md` reflect new flags

## API/Interface

New CLI flags across affected tools:

```python
# scripts/little_loops/cli_args.py
def add_intent_arg(parser: argparse.ArgumentParser) -> None:
    """Add --intent <query> flag to a parser."""
    parser.add_argument("--intent", type=str, default=None,
                        help="Intent query for output filtering")

def add_intent_limit_arg(parser: argparse.ArgumentParser) -> None:
    """Add --intent-limit <N> flag to a parser."""
    parser.add_argument("--intent-limit", type=int, default=50,
                        help="Max lines for intent-filtered output")
```

- **ll-history**: `main_history()` — top-level `--intent`/`--intent-limit` on main parser
- **ll-deps**: `main_deps()` — top-level `--intent`/`--intent-limit` on main parser
- **ll-workflows**: `main()` — `analyze` subparser `--intent`/`--intent-limit`

## Acceptance Criteria

- `--intent` flag wired into at least 3 CLIs (`ll-history`, `ll-deps`, `ll-scan-codebase`)
- No `ranking.py` / BM25 module — ranking is implemented exclusively against FEAT-1112's FTS5 store
- Integration test: `ll-history --intent "rate limit" | wc -l` returns < `ll-history | wc -l` (only valid after FEAT-1112 lands)
- CLAUDE.md / API reference updated

## References

- Inspiration: context-mode intent-driven filtering
- Blocked by FEAT-1112: implement ranking only after FTS5 store ships (no interim BM25)
- Pairs with ENH-1111 scratch-pad enforcement

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

- `scripts/little_loops/cli_args.py` — Add `add_intent_arg(parser)` and `add_intent_limit_arg(parser)` helpers; follow `add_handoff_threshold_arg()` pattern (default=None for intent string, default=50 for limit)
- `scripts/little_loops/cli/history.py` — Wire `--intent`/`--intent-limit` into `main_history()` top-level parser (alongside existing `add_config_arg(parser)`); Step 2 intercept points are `print(format_analysis_*(analysis))` in the `analyze` branch and `print(doc)` in the `export` branch
- `scripts/little_loops/cli/deps.py` — Wire into `main_deps()` top-level parser; Step 2 intercept points are `print(format_report(report, ...))` and `print(_json.dumps(data, indent=2))` in `analyze`, plus `print("\n".join(lines))` in `validate`
- `scripts/little_loops/workflow_sequence/__init__.py` — Wire into `main()` `analyze` subparser; note: this CLI writes to a file (not stdout) so intent filtering applies differently — the output file path is the intercept point, not a `print()` call

### Dependent Files (no changes needed)

- `scripts/little_loops/cli/__init__.py` — imports `main_history` and `main_deps`; no changes needed unless helper signatures change
- `scripts/pyproject.toml` — defines CLI entry points (`main_history`, `main_deps`, `workflow_sequence:main`); no changes needed

### Similar Patterns

- `scripts/little_loops/cli/messages.py:_save_combined()` — timestamped file output + `--stdout` toggle; closest existing "full to file, summary to stdout" pattern
- `scripts/little_loops/cli/history.py:main_history()` — `--output` flag for file vs. `print(doc)` for stdout in `export` subcommand
- `scripts/little_loops/subprocess_utils.py:_list_scratch_files()` — canonical scratch directory is `.loops/tmp/scratch/` (NOT `.ll/scratch/` as stated in Expected Behavior; update that spec when implementing)

### Tests

- `scripts/tests/test_issue_history_cli.py` — follow `capsys` + `patch.object(sys, "argv", [...])` + `mock.call_args.kwargs` pattern for all new CLI tests
- `scripts/tests/test_cli_args.py` — add unit tests for `add_intent_arg()` and `add_intent_limit_arg()` helpers
- `scripts/tests/test_dependency_mapper.py` — existing ll-deps tests to extend

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_workflow_sequence_analyzer.py` — existing coverage for `workflow_sequence/__init__.py:main()` via `TestMainDefaultInput`; add new test for `--intent`/`--intent-limit` pass-through wiring following the `monkeypatch.chdir(tmp_path)` + `patch.object(sys, "argv")` + `capsys` pattern already used in that class [Agent 3 finding]

### Documentation

- `docs/reference/CLI.md` — documents ll-history, ll-deps flags; update for `--intent`/`--intent-limit`
- `.claude/CLAUDE.md` — Scratch Pad section already documents `.loops/tmp/scratch/`; no changes needed for Step 1

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### main_history` and `### main_deps` function sections need `--intent`/`--intent-limit` added to their options lists [Agent 2 finding]
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — `## CLI Deep Dive: ll-workflows` section contains an explicit flags table for `ll-workflows analyze`; add `--intent` and `--intent-limit` rows [Agent 2 finding]

### Acceptance Criteria Correction

`ll-scan-codebase` (listed in Acceptance Criteria) is a Claude Code slash command (`commands/scan-codebase.md`), not a Python CLI — it has no argparse setup and cannot receive `--intent`. The third Python CLI should be `ll-workflows` (`workflow_sequence/__init__.py:main()`), which has argparse but is currently file-out only.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Step 1: Flag Wire-up (before FEAT-1112)

1. Add `add_intent_arg(parser)` to `scripts/little_loops/cli_args.py` — `parser.add_argument("--intent", type=str, default=None, help="...")` following `add_handoff_threshold_arg()` pattern
2. Add `add_intent_limit_arg(parser)` to `scripts/little_loops/cli_args.py` — `parser.add_argument("--intent-limit", type=int, default=50, ...)` following same pattern
3. In `scripts/little_loops/cli/history.py:main_history()` — call `add_intent_arg(parser)` and `add_intent_limit_arg(parser)` on the top-level parser (alongside `add_config_arg(parser)`); `args.intent` and `args.intent_limit` are stored but unused (no-op)
4. In `scripts/little_loops/cli/deps.py:main_deps()` — call same helpers on the top-level parser
5. In `scripts/little_loops/workflow_sequence/__init__.py:main()` — add `--intent`/`--intent-limit` to the `analyze` subparser
6. Add tests to `scripts/tests/test_cli_args.py` for the two new helpers; add pass-through wiring tests to `scripts/tests/test_issue_history_cli.py` verifying `--intent foo` doesn't break existing output (use `capsys` + `patch.object(sys, "argv")` pattern from `TestMainHistoryIntegration`)
7. Update `docs/reference/CLI.md` for the new flags on ll-history, ll-deps, ll-workflows

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7a. Update `scripts/tests/test_workflow_sequence_analyzer.py` — add `--intent`/`--intent-limit` pass-through test in `TestMainDefaultInput` using the `monkeypatch.chdir(tmp_path)` + `patch.object(sys, "argv")` + `capsys` pattern already in use
7b. Update `docs/reference/API.md` — add `--intent <query>` and `--intent-limit <N>` to the options listed under `### main_history` and `### main_deps`
7c. Update `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — add `--intent` and `--intent-limit` rows to the flags table in `## CLI Deep Dive: ll-workflows`

### Step 2: Ranking Implementation (after FEAT-1112)

8. In each CLI's `print()` intercept point: if `args.intent` and `len(output) > 200 lines`: write full output to `.loops/tmp/scratch/<cmd>-<timestamp>.txt` (use `datetime.now().strftime("%Y%m%d-%H%M%S")` per `messages.py:_save_combined()` pattern); return ranked subset to stdout with footer `# Full output: <path> (N lines)`
9. Implement FTS5 ranking against FEAT-1112's store (no `ranking.py` / BM25 layer per Scope Boundary constraint)
10. Add integration test: `ll-history --intent "rate limit" | wc -l` returns fewer lines than `ll-history | wc -l`

## Impact

- **Priority**: P4 — Nice-to-have context reduction; not blocking any current workflow
- **Effort**: Medium — Step 1 (flag wiring) is straightforward argparse work; Step 2 (FTS5 ranking) requires FEAT-1112 completion but avoids BM25 complexity
- **Risk**: Low — `--intent` flag is a no-op pass-through until Step 2; zero existing behavior changes
- **Breaking Change**: No — new optional flags only; existing CLI invocations are unaffected

## Related Key Documentation

- `docs/reference/CLI.md` — CLI flag documentation (needs `--intent`/`--intent-limit` added)
- `docs/reference/API.md` — `### main_history` and `### main_deps` function reference (needs update)
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — ll-workflows flags table (needs update)
- `.claude/CLAUDE.md` — Scratch Pad section (already documents `.loops/tmp/scratch/`)

## Labels

`enhancement`, `cli`, `context-management`, `blocked-by-FEAT-1112`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- No `--intent` flag in `ll-history`, `ll-deps`, or `ll-scan-codebase` ✓
- No `scripts/little_loops/ranking.py` module ✓
- Feature not yet implemented ✓

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-18_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- FEAT-1112 is `done` — the `ll-session` CLI and SQLiteTransport have landed. Both Step 1 and Step 2 are now unblocked.

## Session Log
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:format-issue` - 2026-06-05T22:18:08 - `4aca9a88-34ed-4bf8-bf0d-7490f0e759bf.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:59 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:35 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:16 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `340fa85e-4e72-49ac-847d-86142062faa9.jsonl`
- `/ll:wire-issue` - 2026-05-18T10:11:01 - `340fa85e-4e72-49ac-847d-86142062faa9.jsonl`
- `/ll:refine-issue` - 2026-05-18T10:06:57 - `8e94093a-31ac-4afe-8d9f-df3bc2a5bd8f.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-14T20:57:51 - `75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:55 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:tradeoff-review-issues` - 2026-04-27T02:55:53 - `3d048a1c-d492-434e-87b2-d34bc1ea2f6c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:06 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

---

## Scope Boundaries

~~**Note** (added by `/ll:audit-issue-conflicts` — superseded 2026-06-03): The `ranking.py` BM25 module introduced by this issue is an interim implementation. Once FEAT-1112 (unified SQLite + FTS5 store) lands, the ranking backend should be replaced with FTS5. Implement `ranking.py` as a thin, swappable backend so the transition is a drop-in replacement, not a rewrite.~~ **Superseded** — do not author `ranking.py`. See authoritative constraint below.

**Implementation constraint** (added by `/ll:audit-issue-conflicts` 2026-05-04): `ranking.py` MUST NOT be authored — neither as an interim nor as a final implementation. Do not build a BM25 layer. FEAT-1112 ships. The correct sequence is: (1) wire the `--intent` flag UI into the affected CLIs with full unranked output as a no-op placeholder, (2) wait for FEAT-1112's FTS5 store to land, (3) implement ranking directly against FTS5. Building the BM25 interim layer creates throwaway code with HIGH technical debt (confirmed by tradeoff review 2026-04-26).

- **Cross-issue coordination** (added by `/ll:audit-issue-conflicts` 2026-05-17): Schema extensions to FEAT-1112's `tool_events` table must be coordinated with FEAT-1160. ENH-1114 adds FTS5 intent-ranking indexing; FEAT-1160 adds per-tool `bytes_in`/`bytes_out`/`cache_hit` columns. Both must target FEAT-1112's migration framework to avoid column collisions — implement sequentially after FEAT-1112 ships, not concurrently.

---

## Tradeoff Review Note

**Reviewed**: 2026-04-26 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | HIGH |
| Complexity added | MEDIUM |
| Technical debt risk | HIGH |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — This issue is explicitly blocked by FEAT-1112 (SQLite + FTS5 store), which does not yet exist. The proposed `ranking.py` BM25 module is designed to be thrown away once FEAT-1112 lands, creating throwaway tech debt. Defer implementation until FEAT-1112 is complete and replace BM25 backend directly with FTS5 rather than building the interim layer. If you do implement the interim, ensure `ranking.py` is a thin swappable backend with no callers hard-coupling to BM25 specifics.

---

## Status

**Open** | Created: 2026-04-15 | Priority: P4
