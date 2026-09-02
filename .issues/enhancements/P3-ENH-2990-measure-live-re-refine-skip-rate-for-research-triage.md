---
id: ENH-2990
title: Measure the live re-refine skip rate for research-triage
type: ENH
priority: P3
status: open
captured_at: '2026-08-02T05:14:22Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
parent: EPIC-3023
testable: true
relates_to:
- ENH-2971
labels:
- issues
- measurement
- cost
verify_verdict: VALID
depends_on:
- ENH-3000
decision_needed: false
confidence_score: 95
outcome_confidence: 86
score_complexity: 16
score_test_coverage: 24
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2990: Measure the live re-refine skip rate for `research-triage`

## Summary

ENH-2971's `triage_research_axes()` shipped with its yield measured over the
`.issues/` corpus in each issue's *final* state. That measurement is a poor
proxy for the case the change exists to optimize — `autodev.yaml` re-refining
an issue minutes to hours after a prior pass — and the two numbers differ by
4x. Instrument the real call path (or replay the historical one) to establish
which end of the range production actually sees.

## Current Behavior

The recorded measurement (ENH-2971 § Threshold Validation, 2026-08-02, 2,893
issues / 8,679 axis-spawns):

| Predicate | axis-spawns skipped | locator band spread |
|---|---|---|
| coverage only (`check_staleness=False`) | **33.7%** | 12.4pt |
| coverage + staleness (production default) | **8.6%** | 37.4pt |

Nothing in the corpus sweep observes a real invocation. It scores each issue as
it stands today, against a repo whose files have almost all been committed
since that issue's last recorded `/ll:refine-issue` Session Log entry — so the
Staleness Check invalidates nearly every otherwise-covered axis. The corpus is
also dominated by `done` issues, whose last refine is weeks old.

ENH-2971's own Expected Yield section already names this limitation ("It scores
each issue in its *current* (final) state, not the state it was in at each
historical refine invocation. It is a proxy for the re-refine case, not a replay
of it."). Adding the Staleness Check made the limitation dominant rather than
marginal, which is what this issue exists to resolve.

## Expected Behavior

A measured, defensible figure for the production skip rate, with the
measurement method recorded so it can be re-run after future changes to the
predicate.

## Motivation

The number decides whether the mechanism is worth its complexity, and it is
currently unknown within a 4x band:

- At ~34%, the Staleness Check is nearly free in practice and ENH-2971's
  "~1,700 subagent calls avoided" estimate roughly holds.
- At ~9%, the Staleness Check is eating three quarters of the benefit, and the
  right follow-up is to make it less blunt — it is deliberately file-grained,
  so an unrelated edit anywhere in a large referenced file forces a re-spawn.

There is no way to choose between those responses without the measurement.
`ll-issues research-triage` is on `autodev.yaml`'s critical path, so the data
accumulates on its own once something records it.

## Proposed Solution

**Option A — instrument the live CLI (recommended).** Record each
`ll-issues research-triage` invocation's per-axis verdict, and for uncovered
axes the discriminating reason (`below_threshold` / `no_qualified_refs` /
`missing_symbol` / `stale`). The `analytics.capture.cli_commands` config already
declares `["*"]`, and `.ll/history.db` is the existing sink; check whether the
existing CLI-invocation capture can carry a structured payload before adding a
table. Then read it back after enough autodev cycles have accumulated.

Distinguishing `stale` from the coverage-side reasons is the whole point — that
split is exactly the 33.7%-vs-8.6% gap, measured on real invocations instead of
inferred from a corpus sweep.

> **Selected:** Option A — instrument the live CLI. A near-identical shape
> already shipped (`advisor_consults`, schema v45/FEAT-3300: a new table for
> one call site's structured per-invocation outcome, written directly from
> feature code rather than through `cli_event_context`), and it directly
> captures the `stale`-vs-coverage discriminant that is the whole point of
> this measurement.

**Option B — historical replay.** For each recorded `/ll:refine-issue` Session
Log entry, reconstruct the issue's content and the repo state at that timestamp
(`git show <rev>:<path>`) and score the predicate as it would have run. No
waiting, and it covers the 2,261 recorded invocations — but reconstructing each
issue file's own historical content is the expensive part, and issues are
committed less often than source, so the reconstruction is lossy for
working-tree state that was never committed.

**Option C — bounded live sample.** Wrap the next N autodev runs with a shim
that logs the triage JSON, and stop at a fixed sample size. Cheapest to build,
smallest sample, no permanent instrumentation.

A follow-up worth scoping only after the number is in hand: if `stale`
dominates, consider making the Staleness Check line-grained or scoping it to
the specific paths an axis's evidence resolved against, rather than every
resolved path in the section.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

- Option B precedent: `read_paths_at_ref()` (`scripts/little_loops/test_tamper_guard.py:112-120`, backed by `_git()` at `:572-586`) already reconstructs file content at a git ref via `git show {ref}:{path}` — built for ENH-2935's non-FSM orchestrators, which verify after the run instead of at a live moment. A separate file gives a concrete per-call cost: `scripts/little_loops/cli/verify_evidence.py:799-809`'s `BlobReader` docstring measures `git show` at ~7ms/process-spawn vs. 0.048ms/blob for a long-lived `git cat-file --batch` process — the cost Option B's "expensive" framing should be checked against if chosen. This is separate from Option B's own stated lossiness for uncommitted issue-file state.
- Option C precedent: `ab_writer.py`'s `_AB_SCHEMA`/`calculate_ab_summary()`/`ABResults.per_item` (used by `ll-loop run --baseline`) is the closest existing "run N times, log one structured record per item, then summarize" shape in this codebase — but it serves harness/baseline arms, not a CLI-invocation sampler. No existing implementation of "wrap the next N autodev runs with a shim, stop at a fixed sample size" was found (searched repo-wide for shim/wrap-run/bounded-sample/sample_size patterns, no hits) — Option C would be built from scratch.
- Where to record the eventual number: two section-heading conventions exist in this repo for "measure X, then decide" results — ENH-2971 uses a custom `## Threshold Validation (Implementation Step N — measured DATE)` heading (which is what this issue's own Implementation Step 4 already targets); ENH-3291 instead uses the standard `## Verification Notes` template heading plus a checked-in labelled-sample artifact (`.ll/evidence-precision-labels.json`) for reproducibility. Since this issue already commits to extending ENH-2971's heading specifically, follow ENH-3291's "check in the sample" pattern only if the eventual measurement is non-trivial to reproduce from `history.db` alone.

### Decision Rationale

**Selected: Option A — instrument the live CLI.**

Scored via parallel codebase-evidence gathering across all three options:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — instrument live CLI | 3 | 2 | 2 | 3 | **10/12** |
| B — historical replay | 2 | 1 | 2 | 1 | 6/12 |
| C — bounded live sample | 1 | 1 | 2 | 1 | 5/12 |

Option A wins on both consistency and risk. A near-identical shape already
shipped and can be copied directly: `advisor_consults` (schema v45/FEAT-3300)
is a new `history.db` table for one call site's structured per-invocation
outcome, with a fail-soft writer (`write_advisor_consult()`,
`session_store/writers.py:1823-1877`) called directly from feature code —
sidestepping `cli_event_context`'s per-process-only granularity the same way
`research-triage` would need to. The migration mechanics (`_MIGRATIONS[N]`
append, `_apply_migrations()`) are simple and already exercised. Risk is low
because the change is additive and the writer never raises.

Option B's replay is undermined by the codebase's own admission that this
repo runs with a persistently dirty working tree and `issues.auto_commit`
defaults to `false` and self-skips whenever other files are dirty
(`research_triage.py:19-25`, `hooks/scripts/issue-auto-commit.sh:47,62-69`) —
so `git show <ref>:<issue-path>` at a recorded refine timestamp has no
structural guarantee of matching what the predicate actually saw. That
lossiness directly threatens the "defensible figure" the issue asks for, not
just implementation cost.

Option C's single wrappable call site (`commands/refine-issue.md:169`) makes
its "cheapest to build" framing plausible on paper, but the call happens
inside an LLM-executed markdown bash block rather than Python/FSM
machinery — there is no existing subprocess-shim or self-disabling-after-N
pattern to build on, and `ll-issues` isn't in the one hook
(`scratch-pad-redirect.sh`) that intercepts shelled-out commands today. It
would cost as much to build as Option A while producing a smaller, temporary
sample instead of a durable measurement pipeline.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/research_triage.py` — the instrumentation
  point for Option A (`cmd_research_triage` already computes the full verdict)
- `scripts/little_loops/issues/research_triage.py` — `AxisCoverage.evidence` is
  currently free-text prose; a machine-readable reason code would need adding
  for any of the three options to classify verdicts without parsing strings
- `.ll/history.db` — the existing sink; confirm whether CLI-invocation capture
  can carry a structured payload before adding a table

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/schema_manifest.json` — checked-in
  structural snapshot of the schema, compared byte-for-byte against a live
  build by `test_schema_manifest_matches_checked_in_file`; must be
  regenerated (exact command is in that test's docstring) after the new
  `_MIGRATIONS` entry lands, or CI fails with "schema_manifest.json is stale
  against the current migrations" [Agent 2 finding]
- `scripts/little_loops/session_store/__init__.py` — re-exports
  `cli_event_context` and `write_advisor_consult` as the public import
  surface (lines 135, 164, 217, 231); the new fail-soft writer needs the
  same export to be usable from `cmd_research_triage` [Agent 1 finding]
- `scripts/little_loops/session_store/queries.py` — `_KIND_TABLE` maps
  `"advisor_consult_event": ("advisor_consults", "ts")` (line 109); if the
  new table should be queryable via `ll-session recent --kind <X>` the same
  way `advisor_consults` is, it needs an analogous entry here (and a
  `VALID_KINDS`/`_KIND_TABLE` registration in `schema.py`, already a primary
  file) [Agent 1 + Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/refine-issue.md` — Step 3.0 (line 169) is the real call site:
  `TRIAGE=$(ll-issues research-triage "${ISSUE_ID}" --json ...)`; the step's
  prose documents the JSON contract as "a three-key object; each value has
  `covered` (bool) and `evidence` (string)" with a literal two-key JSON
  example — becomes stale/incomplete once `to_dict()` gains a reason-code
  key. No `jq`/positional parsing consumes `$TRIAGE` (an LLM agent reads it
  directly), so the added field is functionally harmless there; only the
  prose contract and example need updating [Agent 1 + Agent 2 finding]
- Host-adapter mirrors of `commands/refine-issue.md` (`.qwen/commands/ll/
  refine-issue.md`, `.gemini/commands/refine-issue.toml`,
  `.kimi-code/skills/ll-refine-issue/SKILL.md`) are auto-generated by
  `scripts/little_loops/adapters/` from the source command file — confirmed
  not hand-edited, excluded from Files to Modify [Agent 1 finding,
  confirmed against `scripts/little_loops/adapters/core.py`]
- `scripts/little_loops/loops/autodev.yaml` — the "critical path" this
  issue's Motivation refers to invokes `/ll:refine-issue` (not
  `ll-issues research-triage` directly); it is coupled transitively through
  `commands/refine-issue.md` above, not a direct call site [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` § `ll-issues research-triage` — the `--json`/`-j`
  flag row hard-codes the two-key shape ("each value `{"covered": bool,
  "evidence": str}`"); needs updating for the new reason-code field. Already
  listed under Related Key Documentation as a relevance pointer — this
  upgrades it to a required edit [Agent 2 finding]
- `docs/ARCHITECTURE.md` § "History DB: Producer→Consumer Flow" — the
  `history.db` schema-versions table runs v1→v45 (v45 =
  `advisor_consults`/FEAT-3300), one row per migration, naming the exact
  column tuple, writer function, and rebuild-exclusion status; needs a new
  row for this issue's migration, following the v45 row as template
  [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — carries a second, shorter
  schema-history table (rows v2…v45) plus a separate `| Table | What it
  stores |` reference section with a dedicated `advisor_consults` row; needs
  a new row in both. Note: this file is already known-stale against `main`
  per `.issues/bugs/P2-BUG-3187-...schema-table-stops-at-v33.md`, so parity
  with the checked-in file (not full accuracy) is the bar [Agent 2 finding]

### Tests

- `scripts/tests/test_research_triage.py` — `TestCorpusBaseline` holds the
  existing corpus-sweep measurement and its documented coverage-only reading;
  whatever this issue measures should be recorded alongside it rather than
  replacing it.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_research_triage.py::TestSparseIssue::
  test_no_sections_covers_nothing` (line ~104) — asserts `coverage.evidence
  == ""` for the zero-eligible branch across all three axes; breaks once
  that branch populates a reason code. Sibling tests
  `test_sections_present_but_pathless_covers_nothing` and
  `test_below_threshold_fails` only assert `covered is False` and will not
  break [Agent 3 finding]
- `scripts/tests/test_ll_issues_research_triage.py::TestResearchTriageJson::
  test_all_axes_unmet_exits_zero` — asserts strict dict equality
  (`assert axis == {"covered": False, "evidence": ""}`) against the full
  `--json` payload; breaks on any new key added to `AxisCoverage.to_dict()`,
  not just a populated `evidence` string. Sibling tests in the same file use
  membership/substring checks and are additive-safe [Agent 3 finding]
- `scripts/tests/test_session_store_schema.py` — `SCHEMA_VERSION` (currently
  45) is hand-maintained, not derived from `len(_MIGRATIONS)`; ~19 lines in
  this file hardcode `assert SCHEMA_VERSION == 45` and need bumping to `46`
  alongside the new migration.
  `TestSchemaV45AdvisorConsults` (line 2577: `test_advisor_consults_columns`,
  `test_advisor_consults_indexes_exist`,
  `test_v44_db_upgrade_gains_advisor_consults`, `test_kind_registration`,
  `test_excluded_from_rebuild`, `test_not_kindless`) is the exact pattern to
  copy into a new `TestSchemaV46...` class.
  `TestSchemaManifest::test_schema_manifest_matches_checked_in_file` will
  fail until `schema_manifest.json` is regenerated [Agent 3 + Agent 2
  finding]
- `scripts/tests/test_session_store_writers.py::TestWriteAdvisorConsult`
  (line 2712: `test_graceful_when_store_unwritable`,
  `test_issued_consult_persists_all_fields`,
  `test_skipped_consult_persists_outcome_reason`) is the pattern to copy for
  the new fail-soft writer's test class — including the
  monkeypatch-`connect`-raises pattern that proves the writer never raises
  [Agent 3 finding]
- `scripts/tests/test_refine_issue_command.py` (lines 371, 380-381) — asserts
  `commands/refine-issue.md`'s Step 3 text calls `ll-issues research-triage`;
  re-verify against the doc edit above, though the assertion targets the
  call itself, not the JSON-shape prose, so it is unlikely to break
  [Agent 1 finding]
- `scripts/tests/test_text_utils.py::TestClassifyFileRef` (line 210) — the
  closest existing pattern for testing a new `Literal[...]` reason-code
  taxonomy: one test method per literal value, asserting the exact string
  returned (used for `RefStatus`). No `assert_never`/exhaustiveness-check
  convention exists anywhere in this codebase to follow instead — confirmed
  by repo-wide search [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-02 — based on codebase analysis:_

- `cli_events` (`scripts/little_loops/session_store/schema.py:242-249`) has no free-form JSON/payload column — `args` is raw `sys.argv[1:]` capped to 50 entries, `exit_code`/`duration_ms` are the only outcome columns. A structured per-axis verdict payload cannot attach to the existing row without a schema change (new table or new column); the answer to this issue's own "check whether the existing CLI-invocation capture can carry a structured payload" question is confirmed no, not as-is.
- `cli_event_context()` wraps the entire `ll-issues` process once (`scripts/little_loops/cli/issues/__init__.py:21`), not per-subcommand — every one of `ll-issues`' ~90 subcommands writes `binary="ll-issues"`; a `research-triage` row is identifiable today only by parsing `args[0]` from its stored JSON array.
- Event tables in this codebase that do model a closed-set outcome column enforce the set with a SQL `CHECK` constraint at the DB layer (`verdict_events.verdict`, `schema.py:768-781`/`:1202-1219`; the cross-column `abstention_reason` constraint) — independent of whatever Python-side type the value has before the INSERT. Relevant if the new reason code lands as its own `history.db` column.
- ENH-3000 (`.issues/enhancements/P3-ENH-3000-*.md`) is still `status: open` and unimplemented — `RefStatus` (`scripts/little_loops/text_utils.py:161`) is the pre-ENH-3000 five-member `Literal`, with no `untracked_by_design` anywhere in `scripts/little_loops/` (repo-wide search, no hits). Confirms the reconciliation constraint this issue's own Scope Boundary note already flags.

## Program Design

### Types

- `AxisCoverage` (`scripts/little_loops/issues/research_triage.py:97`, `@dataclass(frozen=True)`) — exactly `axis: ResearchAxis`, `covered: bool`, `evidence: str`. No reason-code field exists today. `evidence` currently collapses three distinct rejection paths into an identical empty string: the ratio rejection and the zero-eligible rejection (`_triage_axis`, line 423-424, single `return AxisCoverage(axis=axis, covered=False, evidence="")` for both) and the symbol-requirement rejection (line 431-432, same bare `evidence=""`). Only the staleness rejection (line 437-448) populates `evidence`, with a `"stale: "`-prefixed prose string (line 445) — today that prefix is the *only* machine-checkable signal separating `stale` from the three coverage-side reasons.
- `cli_events` (`scripts/little_loops/session_store/schema.py:242-249`): `id, ts, binary, args, exit_code, duration_ms`. No free-form JSON/payload column. `args` is raw `sys.argv[1:]` (JSON-encoded, capped to the first 50 elements, `writers.py:524`) — not a slot a caller can attach a structured verdict to. `cli_event_context()` wraps the entire `ll-issues` process once (`cli/issues/__init__.py:21`), not per-subcommand: every one of `ll-issues`' ~90 subcommands writes `binary="ll-issues"`, so identifying a `research-triage` row today requires parsing `args[0]` out of the stored JSON array.

### Signatures

- `_triage_axis(...) -> AxisCoverage` (`scripts/little_loops/issues/research_triage.py:402-451`) — the one function containing all four rejection branches this issue's reason-code taxonomy needs to distinguish.
- `cmd_research_triage(config, args)` (`scripts/little_loops/cli/issues/research_triage.py:45-71`) — confirmed thin wrapper: calls `triage_research_axes(path, config.project_root)` with all staleness/index args defaulted, then `print_json({c.axis: c.to_dict() for c in coverages})`. No telemetry write happens inside it today.
- `cli_event_context(db_path, binary, args)` (`scripts/little_loops/session_store/writers.py:482-560`) — inserts one `cli_events` row per `ll-issues` process on enter, updates `exit_code`/`duration_ms` on exit; best-effort (`sqlite3.Error` caught and logged, never propagated).

### Call Path

`ll-issues research-triage <ID>` → `main_issues()` opens `cli_event_context` and dispatches (`cli/issues/__init__.py:21,1073`) → `cmd_research_triage()` (`cli/issues/research_triage.py:61`) → `triage_research_axes()` → `_triage_axis()` per axis (`issues/research_triage.py:334`) → `AxisCoverage.to_dict()` → JSON printed to stdout. The verdict never reaches `history.db` on this path — `cli_event_context.__exit__` only records `exit_code`/`duration_ms` against the raw-argv row already inserted on entry.

### Decision Rules

- New reason codes to add (named in this issue's own Summary/Integration Map): `below_threshold`, `no_qualified_refs`, `missing_symbol`, `stale`.
- Discriminator: `no_qualified_refs` when `eligible == 0`; `below_threshold` when `eligible > 0` and `len(resolved) / eligible < COVERAGE_THRESHOLD` — both currently the *same* branch (`_triage_axis`, line 423-424), so splitting them requires branching that single `if`. `missing_symbol` when coverage passes but the symbol-requirement filter (`_has_symbol`, lines 426-430) empties `resolved` (line 431-432). `stale` when both pass but `build_change_time_index` finds a resolved path changed after the issue's last refine (lines 437-448) — already prefixed `"stale: "` in `evidence`.
- Modeling convention: a new `Literal[...]` alias, not an `Enum` or a dataclass field wrapping one — this is the codebase's stated convention for a classifying function's return value that is stored and compared (`ResearchAxis`, `research_triage.py:59`; `RefStatus`, `text_utils.py:161`; `Verdict`, `doctor_trim.py:66`; documented explicitly as convention in `.issues/enhancements/P3-ENH-3298-*.md:232`). `Enum` classes in this codebase (`RunnerType`, `MergeStatus`, `WorkerStage`, `InstallStatus`, `HandoffBehavior`, `ValidationSeverity`) model internal lifecycle/control-flow state instead — a different shape of problem, not a competing convention for this case.
- If the reason code is persisted as its own `history.db` column rather than staying in-process: existing closed-set outcome columns (`verdict_events.verdict`, `schema.py:768-781`/`:1202-1219`; the cross-column `abstention_reason` constraint) enforce the set with a SQL `CHECK` constraint at the DB layer, independent of the Python-side `Literal` type — the same pattern would apply here.
- Escape hatch: the reason code is additive to `evidence`, not a replacement — `evidence`'s existing prose stays human-readable.
- Reconciliation constraint (already flagged by this issue's own Scope Boundary note): ENH-3000 is still `status: open` and unimplemented — `RefStatus` (`text_utils.py:161`) is still the pre-ENH-3000 five-member `Literal` with no `untracked_by_design` value anywhere in `scripts/little_loops/` (repo-wide search, no hits). The reason-code taxonomy should leave room for that eventual sixth value rather than being finalized as a closed set independently of it.

## Implementation Steps

1. Decide between A/B/C — the choice is a cost/latency tradeoff, not a
   correctness one.
2. Add a machine-readable reason code to `AxisCoverage` (or a sibling field)
   so `stale` is distinguishable from the coverage-side rejections without
   parsing `evidence` prose.
3. Implement the chosen measurement path.
4. Record the result in ENH-2971's Threshold Validation section next to the
   corpus numbers, so the two are read together.
5. If `stale` dominates, open a follow-up to narrow the Staleness Check.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Export the new fail-soft writer from `scripts/little_loops/session_store/__init__.py`
- Register the new kind in `_KIND_TABLE`/`VALID_KINDS` (`schema.py`) and
  `scripts/little_loops/session_store/queries.py`, if the new table should
  be queryable via `ll-session recent --kind <X>`
- Regenerate `scripts/little_loops/session_store/schema_manifest.json` after
  the new `_MIGRATIONS` entry (command in the manifest test's docstring)
- Bump `SCHEMA_VERSION` to 46 in `scripts/little_loops/session_store/
  schema.py` and update the ~19 hardcoded `assert SCHEMA_VERSION == 45`
  lines in `test_session_store_schema.py`
- Add a `TestSchemaV46...` class to `test_session_store_schema.py` (copy
  `TestSchemaV45AdvisorConsults`) and a matching writer-test class to
  `test_session_store_writers.py` (copy `TestWriteAdvisorConsult`)
- Update `test_research_triage.py::test_no_sections_covers_nothing` and
  `test_ll_issues_research_triage.py::test_all_axes_unmet_exits_zero` for
  the new `evidence`/reason-code shape
- Update `docs/reference/CLI.md` § `ll-issues research-triage` and
  `commands/refine-issue.md` Step 3.0 to document the new JSON key
- Add a row to `docs/ARCHITECTURE.md`'s `history.db` schema-versions table
  and to `docs/guides/HISTORY_SESSION_GUIDE.md`'s schema-history table

## Impact

- **Effort**: Small-Medium — instrumentation plus a wait, or a replay harness.
- **Expected benefit**: Resolves a 4x uncertainty in the value of a shipped
  mechanism, and tells us whether the Staleness Check needs narrowing.
- **Risk**: Low — measurement only; no change to the predicate's behavior
  beyond adding a reason code.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: measuring the live/replayed skip rate and its `stale`-vs-
  coverage split; the reason code needed to do so.
- **Out of scope**: changing `COVERAGE_THRESHOLD`, changing the Staleness
  Check's granularity, or acting on the result — those are follow-ups the
  measurement is meant to inform.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CLI.md` § `ll-issues research-triage` | The predicate's documented contract and axis semantics |
| `.issues/enhancements/P3-ENH-2971-*.md` § Threshold Validation | The corpus measurement this issue exists to supersede for the live case |

## Session Log
- `/ll:confidence-check` - 2026-09-02T17:09:25 - `0b967ffb-47f4-465e-882a-47e8e31d96be.jsonl`
- `/ll:wire-issue` - 2026-09-02T16:52:28 - `68e96fc1-615b-4baf-b426-514ab46b57c5.jsonl`
- `/ll:decide-issue` - 2026-09-02T15:00:37 - `57e4152b-6dc7-4f50-8257-b25ad8c5fb2f.jsonl`
- `/ll:decide-issue` - 2026-09-02T14:37:20 - `9308501c-41cd-4971-a426-00e3bbc69dd5.jsonl`
- `/ll:decide-issue` - 2026-09-02T06:11:49 - `5cd97cca-9f12-4312-9a9d-0482900c54a9.jsonl`
- `/ll:refine-issue` - 2026-09-02T05:15:39 - `4773592b-afeb-43e5-9f21-5583f07f1f43.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:58 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:52:52 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:capture-issue` - 2026-08-02T05:15:40 - `3204c464-5212-4b68-a6a3-d963db2a8337.jsonl`

---

## Status

**Open** | Created: 2026-08-02 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's reason-code taxonomy for `AxisCoverage` (distinguishing `stale` from coverage-side rejections) and ENH-3000's new `untracked_by_design` verdict/denominator status both touch coverage/denominator accounting in `scripts/little_loops/issues/research_triage.py`. When implementing, reconcile both into one consistent enum rather than two independently-evolving classification schemes in the same module.
