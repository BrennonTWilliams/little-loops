---
id: FEAT-3446
type: FEAT
title: 'll-history activity subcommand: --workspace scope flag with JSON output'
priority: P2
status: open
verify_verdict: VALID
blocked_by:
- FEAT-3445
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T23:53:23Z'
confidence_score: 70
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3446: ll-history activity subcommand: --workspace scope flag with JSON output

## Summary

New `ll-history activity` subcommand exposing the workspace activity reader (FEAT-3445): per-repo and union activity counts over a `--since` window, with `--workspace` following the established scope-flag convention and `--format json` as the primary machine-readable output.

## Context

Companion CLI surface for FEAT-3445 (create that first; this issue is blocked by it). Surfaced by the same downstream-consumer design review: the consumer's briefing/portfolio tools need one command returning per-repo AND union activity counts, machine-readable.

**Premise correction:** the review task claimed "there is NO JSON workspace formatter" — false. `format_agent_quality_json` (agent_quality.py:872-878) already serializes `AggregationResult` via duck-typed `to_dict()`; only text/markdown needed workspace variants. So there is no quality-side JSON gap to fix; this issue's JSON formatter is new code for the new result type only.

## Current Behavior

`ll-history` has no `activity` subcommand. Subcommands today: `summary`, `analyze`, `rework`, `quality`, `sessions`, `collisions`, `root`, `export` (+ `gendocs`). Only `quality` is workspace-scoped (`--workspace` via `nargs="?"`, history.py:315-321), and its four formatters already include JSON (`format_agent_quality_json`, agent_quality.py:872) — there is no quality-side JSON gap. A consumer wanting cross-repo activity counts must shell out per project (`ll-loop list --running --json`, `ll-issues list --json`) because the FEAT-3445 reader has no CLI surface yet.

## Expected Behavior

`ll-history activity [--workspace[=MANIFEST]] [--since ISO_DATE] [--until ISO_DATE] [--format text|json|markdown|yaml]` prints per-repo and union activity counts from FEAT-3445's reader. Bare `--workspace` discovers `ll-workspace.yaml`; zero discovered members falls back to a single-repo result; the scope flag never changes which formatters run; JSON is the machine contract with `null` counts for non-ok members.

## Motivation

- The scope-flag convention ("a scope flag changes WHAT is collected, never WHICH formatter runs") is established by `quality --workspace` (history.py:315-321); activity is the second consumer and should not invent a new convention.
- `ll-history summary` already owns `--since`/`--until` as ISO dates; a second, different window syntax on the same CLI would be churn.

## Proposed Solution

```
ll-history activity [--workspace[=MANIFEST]] [--since ISO_DATE] [--until ISO_DATE]
                    [--format text|json|markdown|yaml]
```

**Flag semantics:**
- `--workspace` — `nargs="?"` with `default=None, const=""` exactly like quality's (registered history.py:314-323, consumed at :555): absent → `None` (single-repo); bare → `""` (falsy → discovery from `project_root`); value → explicit manifest path. Manifest resolution precedence: explicit arg → `history.workspace_manifest_path` config key → nearest-ancestor `ll-workspace.yaml` walk (`_resolve_manifest_path`, workspace.py:103-123). **Error surface (decision, resolved: mirror quality's exactly):** declared-but-missing manifest → `FileNotFoundError` (workspace.py:214-221) caught, printed to stderr, exit 1 (history.py:558-560). Malformed manifests (`yaml.YAMLError`/`KeyError`/`ValueError`, workspace.py:224-236) and duplicate resolved db_paths (ValueError, workspace.py:233-237) raise uncaught in quality today — leave that shared behavior unchanged rather than diverging.
- **Zero members → single-repo fallback (decision, resolved: yes):** when `--workspace` discovers no members, report the current repo as a one-member result. Consistency beats failing empty. Implementation shape mirrors quality's structure (history.py:551-581): quality initializes `quality_analysis = None`, aggregates `if members:`, and its fallback does **not** synthesize a one-member workspace — it calls the single-repo analyzer directly against the env/config-resolved local db (`resolve_history_db(project_root / DEFAULT_DB_PATH)`). Activity does the same over the FEAT-3445 reader: build the fallback result from the local db (synthesize a one-member member list for `project_root`, or equivalently a single-db read path) so the emitted shape is identical whether zero or one member was in play.
- `--since`/`--until` — **full ISO-8601 timestamps** (date or datetime, e.g. `2026-08-10T14:00:00Z`), validated with `datetime.fromisoformat` (Python 3.11+ accepts `Z`); inclusive (`>=` / `<=`) bounds; both optional, default unbounded. **Deliberate divergence from `summary`'s date-only `--since`/`--until`:** the consumer's windows are rolling (now−7d) and arbitrary datetimes, not date-aligned, so date granularity is insufficient. **Validation placement (deliberate improvement, not a mirror):** `summary` parses post-dispatch with no try/except (history.py:385-389) — invalid input raises `ValueError` through the arm and exits 1 with a raw traceback (`cli_event_context` records exit code 1 on the cli_events row and re-raises, writers.py:556-558). Activity validates at the parser via a `type=` callable (the `--sensitivity`/`_non_negative_float` pattern at history.py:21-26/:292-299), so AC 3's "clear error" is an argparse usage message, not a traceback. Timestamps are compared via the reader's normalized comparison (FEAT-3445), never raw lexicographic string compare.
- `--format` — `choices=["text", "json", "markdown", "yaml"]`, default `text`.

**JSON output shape** (exact contract):

```json
{
  "since": "2026-08-10T14:00:00Z",
  "until": null,
  "per_repo": [
    {
      "repo_path": "/abs/path/to/little-loops",
      "role": "source",
      "label": "little-loops (source)",
      "status": "ok",
      "ok": true,
      "instrumented": true,
      "error": null,
      "loops_run": 12,
      "loops_completed": 10,
      "issues_completed": 4,
      "issues_deferred": 1,
      "issues_closed": null
    },
    {
      "repo_path": "/abs/path/to/other-repo",
      "role": "consumer",
      "label": "other-repo (consumer)",
      "status": "db_missing",
      "ok": false,
      "instrumented": false,
      "error": "history.db not found at ...",
      "loops_run": null,
      "loops_completed": null,
      "issues_completed": null,
      "issues_deferred": null,
      "issues_closed": null
    }
  ],
  "totals": {
    "members": 2,
    "instrumented": true,
    "instrumented_members": 1,
    "loops_run": 12,
    "loops_completed": 10,
    "issues_completed": 4,
    "issues_deferred": 1,
    "issues_closed": null
  }
}
```

**Canonical shape decisions (consumer contract, folded from the downstream review):**
- `per_repo` is an **array** of member objects, each carrying `repo_path`/`role`/`label` explicitly. This diverges from quality's label-keyed dict deliberately: machine consumers need stable identity fields, not display-label keys to parse.
- `ok`/`error` are the canonical consumer-facing fields; `status` rides along as the finer-grained discriminator (`ok == (status == "ok")`, `error` is the reason string).
- Metrics unavailable from history.db serialize as `null`, **never `0`**: `issues_closed` is an explicit always-`null` reserved key (history.db collapses issue closed→completed into transition `'done'`, so the split cannot be made), and the three FSM signals (stalls / cycles / rate-limits, webhook-only) are deliberately absent — consumers must model them as unavailable, not measured zero.
- `totals.instrumented` is the OR over members; counts sum over `ok` members only.

**Formatters (placement resolved: `issue_history/workspace_activity.py`, beside the result type — quality's formatters live in `agent_quality.py` beside `QualityAnalysis`):** `format_workspace_activity_json` / `_yaml` / `_text` / `_markdown`. Mirror the quality quartet's mechanics (agent_quality.py): JSON is `json.dumps(result.to_dict(), indent=2)` with no dispatch at all (:872-878 — the `to_dict()` duck-type alone is the contract); YAML is `yaml.dump(result.to_dict(), ...)` and **falls back to the JSON formatter on `ImportError`** — JSON is valid YAML, so output stays parseable (:881-889); text/markdown render per-member sections + totals. Quality's `hasattr(analysis, "per_repo")` dispatch (:646/:749) exists solely to dodge a runtime import cycle (workspace_quality imports agent_quality) — no cycle applies here, and the predicate must NOT be copied anyway: both result types carry `per_repo`, but quality's is a label-keyed dict of `QualityAnalysis` while activity's is a repo_path-keyed dict of `RepoActivity`. Write dedicated formatters; do not reuse or extend quality's.

**Docs:** `docs/reference/CLI.md` gains the subcommand row; `ll-history --help` epilog examples updated.

## Program Design

### Types

- Result types come verbatim from FEAT-3445 (`WorkspaceActivityResult`, serialized via its `to_dict()`); the CLI defines none of its own.
- Formatter set: `format_workspace_activity_json` / `_yaml` / `_text` / `_markdown`, one per `--format` choice.

### Signatures

- `format_workspace_activity_json(result: WorkspaceActivityResult) -> str` (and `_yaml`/`_text`/`_markdown` siblings) — JSON/YAML serialize the duck-typed `to_dict()` exactly as `format_agent_quality_json` (agent_quality.py:872) does; text/markdown render `per_repo` + `totals` keyed by quality's `"{repo_path.name} ({role})"` labels.

### Call Path

`main_history` (cli/history.py:37) [new `activity` dispatch arm alongside the `quality` arm at history.py:523] -> `discover_workspace_members` (workspace.py:163; manifest errors → stderr + exit 1, zero members → single-repo fallback) -> `aggregate_workspace_activity` [FEAT-3445] -> `format_workspace_activity_json` (or sibling selected by `--format`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — new `activity` subparser + dispatch arm; `--help` epilog examples updated.
- Formatter functions land beside the result type (FEAT-3445's `issue_history/workspace_activity.py`) or in the CLI module, following quality's formatter placement.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/workspace_activity.py` [FEAT-3445] — the reader + result types this subcommand exposes.
- A downstream briefing/portfolio plugin — external consumer of the JSON contract (out of repo).

### Similar Patterns
- `quality` subcommand (parser at history.py:272, dispatch at history.py:523, workspace resolution + fallback at history.py:552-573) — the scope-flag convention, manifest-error path, and zero-member fallback to mirror.
- `format_agent_quality_text/markdown/json/yaml` (agent_quality.py:636/743/872/881) — the four-formatter duck-typing pattern.

### Tests
- `scripts/tests/test_cli_history.py` — CLI integration tests: multi-member workspace fixture, db_missing member, single-repo fallback, invalid `--since` error path, exit 0 with `totals: null`. Fixture shape: write a real `ll-workspace.yaml` via `yaml.dump({"members": ...})` and call `discover_workspace_members` (test_workspace.py:16-28), or build members directly over `tmp_path` (test_feat3410.py:28-43); use non-default db names (`<name>-history.db`) to dodge the autouse `_isolate_history_db` fixture (conftest.py:915-949).
- Golden-shape JSON test (AC 1/7): exact key order + `null`-count contract.

_Wiring pass added by `/ll:wire-issue`:_
- Model the `--workspace[=MANIFEST]` / zero-member fallback tests on `TestHistoryQualityWorkspaceFlag` (`test_cli_history.py:319-427`), specifically its `_member_db` fixture (`:322-348` — full-schema db via `ensure_db()` + direct `schema_version` UPDATE) and `test_workspace_bare_flag_no_manifest_matches_no_flag_output` (exact single-repo-fallback-parity assertion FEAT-3446 needs). [Agent 3 finding, confirmed]
- Model `--since`/`--until` argparse `type=` rejection tests on `test_quality_sensitivity_negative_rejected` / `test_quality_baseline_windows_zero_rejected` (`test_cli_history.py:306-316`) — existing precedent for a parser-level `type=` callable rejecting bad input via `SystemExit`. [Agent 3 finding, confirmed]
- Model the golden-shape JSON test on `TestAggregationResultFormatters::test_json_round_trips_structure` (`test_feat3410_workspace_quality.py:253-260`) and `test_quality_json_format_routes_to_json_formatter` (`test_cli_history.py:239-254`). [Agent 3 finding, confirmed]

### Documentation
- `docs/reference/CLI.md` — `ll-history activity` subcommand row.
- `ll-history --help` epilog — example invocation.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md:452-502` — documents `ll-history quality`/`rework` side by side and states the two "share one ... windowing convention" (cross-referencing `CLI.md#ll-history-quality`); add `ll-history activity` to this comparison so the guide doesn't go stale. [Agent 2 finding, confirmed]
- `skills/analyze-history/SKILL.md` (optional) — enumerates `ll-history` subcommands (`summary`, `analyze`, `export`, `rework`) but already omits `quality` and is not test-enforced; adding `activity` is optional, not required for correctness. [Agent 2 finding, confirmed]

### Configuration
- N/A — flags only; manifest discovery reuses `ll-workspace.yaml` conventions unchanged.

## Implementation Steps

1. Wire the subparser in `cli/history.py` following the `quality` handler's structure (history.py:552-590).
2. Add formatter functions; JSON first (it's the contract), then text/markdown.
3. Golden-shape JSON test; CLI integration tests per AC 2/3/5.
4. Update `docs/reference/CLI.md` + epilog examples.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/HISTORY_SESSION_GUIDE.md` — add `ll-history activity` to the `quality`/`rework` windowing-convention comparison (lines ~452-502).

## Impact

- Purely additive CLI surface plus docs; depends on FEAT-3445's reader.
- The FSM-signals limitation documented in FEAT-3445 carries into the CLI docs (`activity` cannot report stalls/cycles/rate-limits — webhook-only).

## Use Case

A downstream sync runs `ll-history activity --workspace --since 2026-08-10T14:00:00Z --format json` once per sync instead of N subprocess spawns + N direct sqlite connections; the JSON contract above is consumed verbatim by the consumer's briefing/portfolio tools, whose rolling windows need datetime-granularity bounds and null-unavailable metrics.

## Acceptance Criteria

1. `ll-history activity --workspace --since <ISO-8601 timestamp> --format json` emits the exact shape above (stable key order, `per_repo` as an array of member objects with `repo_path`/`role`/`ok`/`error`/`instrumented`, `issues_closed: null`, `totals.instrumented` as the OR over members, `null` counts for non-ok members).
2. Bare `--workspace`, `--workspace <path>`, and absent flag (single-repo result) all work; a declared-but-missing manifest exits 1 with the path on stderr.
3. `--since`/`--until` accept full ISO-8601 timestamps (date or datetime) as inclusive bounds; invalid input exits non-zero with a clear argparse usage error (parser-level `type=` validation, not a raw traceback).
4. All four `--format` values render; scope flag never changes which formatters are available.
5. Exit 0 with `totals: null` when no member is `ok`.
6. `docs/reference/CLI.md` and the `--help` epilog document the subcommand; `docs/guides/HISTORY_SESSION_GUIDE.md`'s `quality`/`rework` windowing-convention comparison (lines ~452-502) is updated to include `activity`.
7. Tests cover: multi-member workspace fixture, db_missing member, single-repo fallback, JSON shape golden test.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Module reference for the reader/formatter placement this CLI exposes |
| guidelines | .claude/CLAUDE.md | Testing & CI policy — new CLI tests belong in `python -m pytest scripts/tests/` |

## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND**

All 23 code/test/doc file:line citations checked against HEAD were accurate
(history.py, workspace.py, agent_quality.py formatter placements and
dispatch, `test_cli_history.py` fixtures/tests, `test_feat3410_workspace_quality.py`
golden-shape test). No claim about current state is false.

The defect is in AC coverage of the proposal's own Integration Map: the
Wiring Phase explicitly requires updating
`docs/guides/HISTORY_SESSION_GUIDE.md:452-502` to add `ll-history activity`
to the `quality`/`rework` windowing-convention comparison, but no Acceptance
Criterion covers it — AC6 covers only `docs/reference/CLI.md` and the
`--help` epilog. A point named in the Integration Map/Wiring Phase with no
corresponding AC is a gap an implementer can silently skip.

~~Remaining: add an AC (or fold into AC6) requiring the
`HISTORY_SESSION_GUIDE.md` comparison update~~ — closed in a follow-up pass
(2026-09-11): AC6 extended to require the `HISTORY_SESSION_GUIDE.md`
windowing-convention comparison update. No outstanding action items remain.

Decisions log: no active required rules found. Evidence-quote check
(`ll-verify-evidence --json`): clean, 0 findings.

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-10_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 96/100 → HIGH CONFIDENCE

### Gaps to Address
- Dependencies Hard Override (BUG-3051): `blocked_by: FEAT-3445` is unresolved (FEAT-3445 status: open). This issue's reader (`aggregate_workspace_activity`, `WorkspaceActivityResult`) does not exist yet, so the CLI dispatch arm has nothing to call. Implement/merge FEAT-3445 first, then re-run this check.

## Session Log
- `/ll:confidence-check` - 2026-09-11T01:14:23 - `226e3334-05f8-455d-a6d0-352e3badc359.jsonl`
- `/ll:reconcile-issue` - 2026-09-11T01:00:11 - `96fc360a-b5db-40dd-bb89-1981614713ee.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:53:16 - `74560d07-2a1c-4247-b7b2-e91055dab494.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:47:45 - `e2289526-f05e-4914-b7bb-dee1a954062a.jsonl`
- `/ll:wire-issue` - 2026-09-11T00:38:37 - `2e842a0e-c20b-4811-ac47-806369f06e2c.jsonl`
- `/ll:format-issue` - 2026-09-10T23:59:04 - `977177b4-c924-4eb0-8524-717b55725bed.jsonl`
- `/ll:capture-issue` - 2026-09-10T23:53:44 - `98b64441-1d76-4822-ab69-c295348ddfd6.jsonl`
