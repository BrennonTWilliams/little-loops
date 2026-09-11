---
id: FEAT-3446
type: FEAT
title: 'll-history activity subcommand: --workspace scope flag with JSON output'
priority: P2
status: done
verify_verdict: VALID
blocked_by:
- FEAT-3445
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T23:53:23Z'
completed_at: '2026-09-11T04:56:06Z'
confidence_score: 90
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3446: ll-history activity subcommand: --workspace scope flag with JSON output

## Summary

New `ll-history activity` subcommand exposing the workspace activity reader (FEAT-3445): per-repo and union activity counts over a `--since` window, with `--workspace` following the established scope-flag convention and `--format json` as the primary machine-readable output.

## Context

Companion CLI surface for FEAT-3445, which was the hard prerequisite (this issue was blocked by it) and is now `done` (completed 2026-09-11T02:20:09Z) — the dependency has resolved. Surfaced by the same downstream-consumer design review: the consumer's briefing/portfolio tools need one command returning per-repo AND union activity counts, machine-readable.

**Premise correction:** the review task claimed "there is NO JSON workspace formatter" — false. `format_agent_quality_json` (agent_quality.py:872-878) already serializes `AggregationResult` via duck-typed `to_dict()`; only text/markdown needed workspace variants. So there is no quality-side JSON gap to fix; this issue's JSON formatter is new code for the new result type only.

## Current Behavior

`ll-history` has no `activity` subcommand. Subcommands today: `summary`, `analyze`, `rework`, `quality`, `sessions`, `audit-issue-collisions`, `root`, `export`. (An earlier draft of this section said "(+ `gendocs`)" — false: there is no `gendocs` subcommand; `export` was renamed from `generate-docs` in ENH-523 and only the parser variable is still `gendocs_parser`, history.py:181. Corrected 2026-09-11 pre-implementation review.) Only `quality` is workspace-scoped (`--workspace` via `nargs="?"`, history.py:315-321), and its four formatters already include JSON (`format_agent_quality_json`, agent_quality.py:872) — there is no quality-side JSON gap. A consumer wanting cross-repo activity counts must shell out per project (`ll-loop list --running --json`, `ll-issues list --json`) because the FEAT-3445 reader has no CLI surface yet.

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

- **Zero members → single-repo fallback (decision, resolved: yes):** when `--workspace` discovers no members, report the current repo as a one-member result. Consistency beats failing empty. Implementation shape mirrors quality's structure (history.py:551-581): quality initializes `quality_analysis = None`, aggregates `if members:`, and its fallback does **not** synthesize a one-member workspace — it calls the single-repo analyzer directly against the env/config-resolved local db (`resolve_history_db(project_root / DEFAULT_DB_PATH)`). Activity does the same over the FEAT-3445 reader: build the fallback result from the local db (synthesize a one-member member list for `project_root`, or equivalently a single-db read path) so the emitted shape is identical whether zero or one member was in play. **Fallback member construction (pinned):** `WorkspaceMember(repo_path=project_root, role="source", db_path=resolve_history_db(project_root / DEFAULT_DB_PATH))` — role `"source"` so the label reads `"<name> (source)"`, matching the JSON example above; pin it because `role`/`label` land verbatim in the consumer-facing JSON and the golden test depends on them.

- `--since`/`--until` — **full ISO-8601 timestamps** (date or datetime, e.g. `2026-08-10T14:00:00Z`), validated with `datetime.fromisoformat` (Python 3.11+ accepts `Z`); inclusive (`>=` / `<=`) bounds; both optional, default unbounded. **Deliberate divergence from `summary`'s date-only `--since`/`--until`:** the consumer's windows are rolling (now−7d) and arbitrary datetimes, not date-aligned, so date granularity is insufficient. **Validation placement (deliberate improvement, not a mirror):** `summary` parses post-dispatch with no try/except (history.py:385-389) — invalid input raises `ValueError` through the arm and exits 1 with a raw traceback (`cli_event_context` records exit code 1 on the cli_events row and re-raises, writers.py:556-558). Activity validates at the parser via a `type=` callable (the `--sensitivity`/`_non_negative_float` pattern at history.py:21-26/:292-299), so AC 3's "clear error" is an argparse usage message, not a traceback. **The `type=` callable returns the raw string, not the parsed datetime** (deliberate divergence from `_non_negative_float`, which returns the converted value): `_parse_ts()` runs `value.replace("Z", "+00:00")` on the bound value (TypeError on a datetime, workspace_activity.py:155) and `WorkspaceActivityResult.to_dict()` echoes `since`/`until` verbatim into `json.dumps` (datetime is not JSON serializable). Shape: `_iso_timestamp(raw: str) -> str` — validate via `datetime.fromisoformat`, return `raw`. Help text states that naive timestamps (no offset) are treated as UTC and bounds are inclusive; `metavar="TIMESTAMP"` distinguishes it from `summary`'s date-only `DATE`. **No `-S` short alias (decision, 2026-09-11 pre-implementation review):** `summary`/`analyze`/`export` spell `-S` as date-only `DATE`; reusing the alias for timestamp semantics would blur the granularity distinction the metavar exists to draw. Timestamps are compared via the reader's normalized comparison, never raw lexicographic string compare.

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
    "instrumented_members": 1,
    "instrumented": true,
    "ok_members": 1,
    "loops_run": 12,
    "loops_completed": 10,
    "issues_completed": 4,
    "issues_deferred": 1,
    "issues_closed": null
  }
}
```

**Canonical shape decisions (consumer contract, folded from the downstream review; totals example corrected 2026-09-11 pre-implementation review to match `WorkspaceTotals.to_dict()` exactly):**
- `totals` mirrors `WorkspaceTotals.to_dict()` exactly (`workspace_activity.py:111-123`) — key order `members, instrumented_members, instrumented, ok_members, loops_run, ...`, including `ok_members`; since/until echo the raw CLI strings verbatim.
- `per_repo` is an **array** of member objects, each carrying `repo_path`/`role`/`label` explicitly. This diverges from quality's label-keyed dict deliberately: machine consumers need stable identity fields, not display-label keys to parse. **Array order (pinned, 2026-09-11 pre-implementation review):** the manifest's declaration order — dict-insertion order through `aggregate_workspace_activity` (keyed by `db_path`). Consumers must key on `repo_path`, never array index; reordering a manifest must not be read as a data change.
- `ok`/`error` are the canonical consumer-facing fields; `status` rides along as the finer-grained discriminator (`ok == (status == "ok")`, `error` is the reason string).
- Metrics unavailable from history.db serialize as `null`, **never `0`**: `issues_closed` is an explicit always-`null` reserved key (history.db collapses issue closed→completed into transition `'done'`, so the split cannot be made), and the three FSM signals (stalls / cycles / rate-limits, webhook-only) are deliberately absent — consumers must model them as unavailable, not measured zero.
- `totals.instrumented` is the OR over members; counts sum over `ok` members only.

**Formatters (placement resolved: `issue_history/workspace_activity.py`, beside the result type — quality's formatters live in `agent_quality.py` beside `QualityAnalysis`):** `format_workspace_activity_json` / `_yaml` / `_text` / `_markdown`. Mirror the quality quartet's mechanics (agent_quality.py): JSON is `json.dumps(result.to_dict(), indent=2)` with no dispatch at all (:872-878 — the `to_dict()` duck-type alone is the contract); YAML is `yaml.dump(result.to_dict(), ...)` and **falls back to the JSON formatter on `ImportError`** — JSON is valid YAML, so output stays parseable (:881-889); text/markdown render per-member sections + totals. Quality's `hasattr(analysis, "per_repo")` dispatch (:646/:749) exists solely to dodge a runtime import cycle (workspace_quality imports agent_quality) — no cycle applies here, and the predicate must NOT be copied anyway: both result types carry `per_repo`, but quality's is a label-keyed dict of `QualityAnalysis` while activity's is a repo_path-keyed dict of `RepoActivity`. Write dedicated formatters; do not reuse or extend quality's.

**Docs:** `docs/reference/CLI.md` gains the subcommand row; `ll-history --help` epilog examples updated.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- `--workspace` flag registration on `quality` (the cited structural precedent) is `history.py:314-323`, not `:315-321` — the `add_argument(...)` call opens at `314` and its closing paren/help string is at `323`.
- `format_agent_quality_json`/`_yaml`/`_text`/`_markdown` anchors confirmed exactly as cited: `agent_quality.py:872-878` (JSON, `json.dumps(analysis.to_dict(), indent=2)`, no dispatch), `:881-889` (YAML, falls back to the JSON formatter on `ImportError`), `:636` (text), `:743` (markdown).
- `discover_workspace_members` and its manifest-error/zero-member paths confirmed exactly as cited: `workspace.py:103-123` (`_resolve_manifest_path` precedence), `:163-165` (signature), `:214-221` (declared-but-missing → `FileNotFoundError`), `:222` (undeclared/ancestor-walk missing → returns `[]` silently, no exception), `:224-238` (malformed-manifest `ValueError`/`KeyError` paths, uncaught), `:233-237` (duplicate-`db_path` `ValueError`).
- **JSON contract correction**: `WorkspaceTotals.to_dict()` (`workspace_activity.py:111-123`) includes an `ok_members` field and a key order (`members, instrumented_members, instrumented, ok_members, ...`) that diverges from the illustrative `totals` example above (which omits `ok_members` and orders `instrumented` before `instrumented_members`). Since the JSON formatter is a bare `json.dumps(result.to_dict(), indent=2)` with no transformation (mirroring `format_agent_quality_json`), the real, already-landed FEAT-3445 contract — not the illustrative example — is what AC1's "exact shape" must be verified against. _(The `totals` example in Proposed Solution was corrected in-place on 2026-09-11 to include `ok_members` and the `to_dict()` key order; example and contract now agree.)_
- No CLI wiring or dedicated test file exists yet for this issue: `aggregate_workspace_activity`/`WorkspaceActivityResult` have zero references in `cli/history.py` or `test_cli_history.py`; their only callers are in `scripts/tests/test_feat3445_workspace_activity.py`. `**/test_feat3446*` matches no files. FEAT-3445 is now `done` (completed 2026-09-11); the `blocked_by: FEAT-3445` dependency has resolved.

## Program Design

### Types

- Result types come verbatim from FEAT-3445 (`WorkspaceActivityResult`, serialized via its `to_dict()`); the CLI defines none of its own.
- Formatter set: `format_workspace_activity_json` / `_yaml` / `_text` / `_markdown`, one per `--format` choice.

### Signatures

- `format_workspace_activity_json(result: WorkspaceActivityResult) -> str` (and `_yaml`/`_text`/`_markdown` siblings) — JSON/YAML serialize the duck-typed `to_dict()` exactly as `format_agent_quality_json` (agent_quality.py:872) does; text/markdown render `per_repo` + `totals` sections using the precomputed `RepoActivity.label` (built once by `workspace_quality._label` as `"{repo_path.name} ({role})"`), not a recomputed format string.

### Call Path

`main_history` (cli/history.py:37) [new `activity` dispatch arm alongside the `quality` arm at history.py:523] -> `discover_workspace_members` (workspace.py:163; manifest errors → stderr + exit 1, zero members → single-repo fallback) -> `aggregate_workspace_activity` [FEAT-3445] -> `format_workspace_activity_json` (or sibling selected by `--format`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Confirmed at current HEAD: `aggregate_workspace_activity(members: list[WorkspaceMember], *, since: str | None, until: str | None = None) -> WorkspaceActivityResult` — `scripts/little_loops/issue_history/workspace_activity.py:248-250`. Docstring (`:251-257`) states it never raises: a missing db, schema-version mismatch, or `sqlite3.Error` all resolve to a status-carrying `RepoActivity`, never an exception.
- `WorkspaceActivityResult.to_dict()` — `workspace_activity.py:135-141`: `{"since", "until", "per_repo": [activity.to_dict() for activity in self.per_repo.values()], "totals": self.totals.to_dict()}`. `per_repo` is internally `dict[str, RepoActivity]` keyed by `str(member.db_path)`, serialized to a plain array via `.values()`.
- `RepoActivity.to_dict()` — `workspace_activity.py:79-94`, key order: `repo_path, role, label, status, ok, error, instrumented, loops_run, loops_completed, issues_completed, issues_deferred, issues_closed`.
- `WorkspaceTotals.to_dict()` — `workspace_activity.py:111-123`, key order: `members, instrumented_members, instrumented, ok_members, loops_run, loops_completed, issues_completed, issues_deferred, issues_closed`. Its docstring reads "Keys in declaration order above (stable order: FEAT-3446 AC 1)" — this key set/order is FEAT-3445's committed contract and includes `ok_members`, a field the illustrative JSON example in this issue's own Proposed Solution omitted at research time (see Proposed Solution findings; example corrected in-place 2026-09-11 and no longer omits it).
- `MemberActivityStatus` enum — `workspace_activity.py:54-60`: `OK`, `DB_MISSING`, `SCHEMA_SKEW`, `UNREADABLE`.
- Confirmed call chain gap: `main_history` (`cli/history.py:37`) has no `activity` dispatch arm today — a repo-wide search of `cli/history.py` and `test_cli_history.py` for `activity`/`WorkspaceActivityResult`/`aggregate_workspace_activity` returns zero hits. The `quality` structural precedent's dispatch arm is `if args.command == "quality":` at `history.py:523`; its `--workspace` resolution+fallback block spans `history.py:551-581` (line 551 is the `quality_analysis = None` init, 581 is where the local-db fallback branch ends). `583-590` is the shared format-dispatch block, downstream of and common to both branches — not part of workspace resolution itself.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — new `activity` subparser + dispatch arm; `--help` epilog examples updated.
- `scripts/little_loops/issue_history/workspace_activity.py` — the four formatters land beside the result type (placement resolved in Proposed Solution), not in the CLI module.
- `scripts/little_loops/issue_history/__init__.py` — re-export the four new formatters alongside `aggregate_workspace_activity` (already re-exported at `__init__.py:206,292`); `cli/history.py` imports formatters via the package init, same as quality's quartet.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/workspace_activity.py` [FEAT-3445] — the reader + result types this subcommand exposes.
- A downstream briefing/portfolio plugin — external consumer of the JSON contract (out of repo).

### Similar Patterns
- `quality` subcommand (parser at history.py:272, dispatch at history.py:523, workspace resolution + fallback at history.py:552-573) — the scope-flag convention, manifest-error path, and zero-member fallback to mirror.
- `format_agent_quality_text/markdown/json/yaml` (agent_quality.py:636/743/872/881) — the four-formatter duck-typing pattern.

### Tests
- `scripts/tests/test_cli_history.py` — CLI integration tests: multi-member workspace fixture, db_missing member, single-repo fallback, declared-but-missing manifest (exit 1 + path on stderr, AC 2 — model on `test_workspace_missing_declared_manifest_exits_nonzero`, test_cli_history.py:394), invalid `--since` AND invalid `--until` error paths (shared `type=` callable, but pin both), exit 0 with all-null totals counts (`ok_members: 0`, `loops_run: null`, …). Fixture shape: write a real `ll-workspace.yaml` via `yaml.dump({"members": ...})` and call `discover_workspace_members` (test_workspace.py:16-28), or build members directly over `tmp_path` (`_healthy_member`, test_feat3410_workspace_quality.py:28-43); use non-default db names (`<name>-history.db`) to dodge the autouse `_isolate_history_db` fixture (conftest.py:915-949).
- **Fallback status in tests (pinned 2026-09-11 pre-implementation review):** `cli_event_context` inserts its `cli_events` row at entry (writers.py:537), so the invocation itself creates the local `history.db` (current schema) before the fallback member gates it — the single-repo fallback reports `ok` with zero counts, never `db_missing`, while analytics capture is enabled; it reports `db_missing` when `analytics.capture.cli_commands` is disabled. Member dbs dodge this via non-default names, but the fallback member's `db_path` is fixed — a fallback test must pin which situation it asserts (default capture-on → `ok`).
- Golden-shape JSON test (AC 1/7): exact key order + `null`-count contract.

_Wiring pass added by `/ll:wire-issue`:_
- Model the `--workspace[=MANIFEST]` / zero-member fallback tests on `TestHistoryQualityWorkspaceFlag` (`test_cli_history.py:319-427`), specifically its `_member_db` fixture (`:322-348` — full-schema db via `ensure_db()` + direct `schema_version` UPDATE) and `test_workspace_bare_flag_no_manifest_matches_no_flag_output` (exact single-repo-fallback-parity assertion FEAT-3446 needs). [Agent 3 finding, confirmed]
- Model `--since`/`--until` argparse `type=` rejection tests on `test_quality_sensitivity_negative_rejected` / `test_quality_baseline_windows_zero_rejected` (`test_cli_history.py:306-316`) — existing precedent for a parser-level `type=` callable rejecting bad input via `SystemExit`. [Agent 3 finding, confirmed]
- Model the golden-shape JSON test on `TestAggregationResultFormatters::test_json_round_trips_structure` (`test_feat3410_workspace_quality.py:253-260`) and `test_quality_json_format_routes_to_json_formatter` (`test_cli_history.py:239-254`). [Agent 3 finding, confirmed]

### Documentation
- `docs/reference/CLI.md` — `ll-history activity` subcommand row.
- `ll-history --help` epilog — example invocation.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md:452-502` — documents `ll-history quality`/`rework` side by side and states the two "share one ... windowing convention" (cross-referencing `CLI.md#ll-history-quality`); add `ll-history activity` to this comparison so the guide doesn't go stale, presenting it with its distinct `summary`-style ISO-timestamp bounds rather than as a third member of the shared calendar-month convention. [Agent 2 finding, confirmed; distinct-semantics caveat added 2026-09-11 pre-implementation review]
- `skills/analyze-history/SKILL.md` (optional) — enumerates `ll-history` subcommands (`summary`, `analyze`, `export`, `rework`) but already omits `quality` and is not test-enforced; adding `activity` is optional, not required for correctness. [Agent 2 finding, confirmed]

### Configuration
- N/A — flags only; manifest discovery reuses `ll-workspace.yaml` conventions unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- The only current callers of `aggregate_workspace_activity`/`WorkspaceActivityResult` are test call sites in `scripts/tests/test_feat3445_workspace_activity.py:129-426`; no production/CLI caller exists yet, confirming `cli/history.py` needs a net-new dispatch arm rather than modifying an existing call site.
- `discover_workspace_members` (`scripts/little_loops/workspace.py:163-165`) signature confirmed: `discover_workspace_members(manifest_path: Path | None = None, *, start: Path | None = None) -> list[WorkspaceMember]`.

## Implementation Steps

1. Wire the subparser in `cli/history.py` following the `quality` handler's structure (history.py:552-590).
2. Add formatter functions; JSON first (it's the contract), then text/markdown.
3. Golden-shape JSON test; CLI integration tests per AC 2/3/5.
4. Update `docs/reference/CLI.md` + epilog examples.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/HISTORY_SESSION_GUIDE.md` — add `ll-history activity` to the `quality`/`rework` windowing-convention comparison (lines ~452-502), **presenting it alongside them with its distinct semantics**: `activity` does NOT share their `(calendar month, orchestrator)` convention — its bounds are `summary`-style inclusive ISO timestamps. Do not write "activity shares the windowing convention"; that claim is false.

## Impact

- Purely additive CLI surface plus docs; built atop FEAT-3445's reader (`done`, completed 2026-09-11T02:20:09Z).
- The FSM-signals limitation documented in FEAT-3445 carries into the CLI docs (`activity` cannot report stalls/cycles/rate-limits — webhook-only).

## Use Case

A downstream sync runs `ll-history activity --workspace --since 2026-08-10T14:00:00Z --format json` once per sync instead of N subprocess spawns + N direct sqlite connections; the JSON contract above is consumed verbatim by the consumer's briefing/portfolio tools, whose rolling windows need datetime-granularity bounds and null-unavailable metrics.

## Acceptance Criteria

1. `ll-history activity --workspace --since <ISO-8601 timestamp> --format json` emits the exact shape above (stable key order, `per_repo` as an array of member objects with `repo_path`/`role`/`ok`/`error`/`instrumented`, `issues_closed: null`, `totals.instrumented` as the OR over members, `totals.ok_members` present in `WorkspaceTotals.to_dict()` key order, `null` counts for non-ok members).
2. Bare `--workspace`, `--workspace <path>`, and absent flag (single-repo result) all work; a declared-but-missing manifest exits 1 with the path on stderr.
3. `--since`/`--until` accept full ISO-8601 timestamps (date or datetime) as inclusive bounds; invalid input exits non-zero with a clear argparse usage error (parser-level `type=` validation, not a raw traceback).
4. All four `--format` values render; scope flag never changes which formatters are available.
5. Exit 0 when no member is `ok`: `totals` still serializes as a full object with `ok_members: 0` and `null` count fields (`loops_run` … `issues_deferred`) — never `totals: null` itself.
6. `docs/reference/CLI.md` and the `--help` epilog document the subcommand; `docs/guides/HISTORY_SESSION_GUIDE.md`'s `quality`/`rework` windowing-convention comparison (lines ~452-502) is updated to mention `activity` alongside them, explicitly noting it does NOT share their `(calendar month, orchestrator)` convention — its bounds are `summary`-style inclusive ISO timestamps.
7. Tests cover: multi-member workspace fixture, db_missing member, single-repo fallback, declared-but-missing manifest (exit 1 + stderr), invalid `--since`/`--until` (argparse usage error), JSON shape golden test.

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

Re-verified 2026-09-11 (`/ll:verify-issues FEAT-3446 --auto`): all file/line
citations re-checked against HEAD — history.py anchors (main_history :37,
`_non_negative_float` :21-26, export parser var `gendocs_parser` :181-183,
quality `--workspace` :314-323, dispatch arms :523/:385-389, workspace
resolution :551-560, format dispatch :583-590), agent_quality.py formatter
quartet (:636/:743/:872-889), workspace.py manifest paths (:103-123/:163-238),
workspace_activity.py reader anchors (:54-60/:79-94/:111-141/:155/:248-257),
test anchors (test_cli_history.py :239/:306-316/:319/:323/:394,
test_feat3410_workspace_quality.py :234/:253/:28-43, conftest.py
`_isolate_history_db` :915-949), `issue_history/__init__.py:206,292`
re-exports, `HISTORY_SESSION_GUIDE.md:452-502` — all accurate. FEAT-3445
confirmed `done` (Completed 2026-09-11T02:20:09Z); no `activity` wiring in
`cli/history.py`; no `test_feat3446*` files — issue still accurately
describes unimplemented state. One stale filename corrected in place this
pass: `test_feat3410.py` → `test_feat3410_workspace_quality.py` (line range
28-43 was already correct). Verdict at time of check: **NEEDS_UPDATE**
(correction applied in the same pass, so the issue as it now reads is up to
date). Evidence-quote check: clean, 0 findings. Decisions log: no active
required rules.

## Resolution

---

- **Action**: implement
- **Completed**: 2026-09-10
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_history/workspace_activity.py`: four new formatters (`format_workspace_activity_json`/`_yaml`/`_text`/`_markdown`) beside the result type, mirroring the agent_quality quartet's mechanics (verbatim `to_dict()` dump for JSON/YAML with ImportError fallback; per-member sections + totals for text/markdown; no `hasattr` dispatch).
- `scripts/little_loops/issue_history/__init__.py`: re-exported the four formatters (import block + `__all__`).
- `scripts/little_loops/cli/history.py`: `_iso_timestamp` parser-level `type=` callable (validates ISO-8601, returns the raw string); `activity` subparser (`--format`, `--workspace[=PATH]`, `--since`/`--until TIMESTAMP`, no `-S` alias); dispatch arm mirroring quality's structure with the pinned single-repo fallback member (`role="source"`, `resolve_history_db`-resolved local db); epilog examples.
- `scripts/tests/test_cli_history.py`: `TestHistoryActivity` — 9 tests (golden JSON shape, bare/explicit/absent scope variants, zero-member fallback parity, declared-but-missing manifest exit 1 + stderr, invalid `--since`/`--until` SystemExit, all four formats, all-null totals).
- `docs/reference/CLI.md`: `ll-history activity` subsection (flag table + JSON contract) + all-subcommands example.
- `docs/guides/HISTORY_SESSION_GUIDE.md`: `activity` added to the quality/rework comparison with the explicit does-NOT-share-windowing-convention caveat (AC 6).

### Verification Results
- Tests: PASS — `TestHistoryActivity` 9/9; full suite 23972 passed, 43 skipped, with 4 pre-existing failures reproduced identically at clean HEAD (test_issue_parser priority-regex allowlist, BUG-3439/3443 evidence quotes in test_verify_evidence) — unrelated to this change.
- Lint: PASS — `ruff check scripts/` clean.
- Types: PASS — `mypy scripts/little_loops/` no issues.
- Integration: PASS — smoke-tested against a real two-member workspace fixture; JSON output byte-matches the issue's contract (key order, `ok_members`, null-unavailable counts, manifest-order `per_repo` array).

## Status

**Done** | Created: 2026-09-10 | Completed: 2026-09-11 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-10_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 96/100 → HIGH CONFIDENCE

### Gaps to Address
- Dependencies Hard Override (BUG-3051): `blocked_by: FEAT-3445` is unresolved (FEAT-3445 status: open). This issue's reader (`aggregate_workspace_activity`, `WorkspaceActivityResult`) does not exist yet, so the CLI dispatch arm has nothing to call. Implement/merge FEAT-3445 first, then re-run this check.
  - _Stale as of `/ll:refine-issue` 2026-09-10: FEAT-3445 is now `status: done` (completed 2026-09-11T02:20:09Z) and its reader (`aggregate_workspace_activity`, `WorkspaceActivityResult`) exists at `scripts/little_loops/issue_history/workspace_activity.py:248-312`/`:127-133`. This dependency is resolved; re-run `/ll:confidence-check` to clear this gap._

## Session Log
- `/ll:manage-issue` - 2026-09-11T04:55:48 - `613f688d-5c16-4731-ae31-d9e2c369747c.jsonl`
- `/ll:ready-issue` - 2026-09-11T04:32:35 - `0667d84c-ad15-42ea-9124-afb4af9bd8e3.jsonl`
- `/ll:confidence-check` - 2026-09-11T04:00:45 - `2647bc9d-a76b-4b62-b689-27cd746d4229.jsonl`
- `/ll:verify-issues` - 2026-09-11T03:57:41 - `3bfa767e-086c-4d89-88f3-e03049677079.jsonl`
- `/ll:confidence-check` - 2026-09-11T03:30:24 - `26036582-ea49-4a94-afdd-ed1d196dcb3d.jsonl`
- `/ll:refine-issue` - 2026-09-11T02:51:55 - `d66e9ab6-b157-4ab3-aa53-bdc98d019119.jsonl`
- `/ll:confidence-check` - 2026-09-11T01:14:23 - `226e3334-05f8-455d-a6d0-352e3badc359.jsonl`
- `/ll:reconcile-issue` - 2026-09-11T01:00:11 - `96fc360a-b5db-40dd-bb89-1981614713ee.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:53:16 - `74560d07-2a1c-4247-b7b2-e91055dab494.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:47:45 - `e2289526-f05e-4914-b7bb-dee1a954062a.jsonl`
- `/ll:wire-issue` - 2026-09-11T00:38:37 - `2e842a0e-c20b-4811-ac47-806369f06e2c.jsonl`
- `/ll:format-issue` - 2026-09-10T23:59:04 - `977177b4-c924-4eb0-8524-717b55725bed.jsonl`
- `/ll:capture-issue` - 2026-09-10T23:53:44 - `98b64441-1d76-4822-ab69-c295348ddfd6.jsonl`
