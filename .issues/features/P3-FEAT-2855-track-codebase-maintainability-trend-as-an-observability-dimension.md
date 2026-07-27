---
id: FEAT-2855
title: Track codebase maintainability trend as an observability dimension
type: FEAT
priority: P3
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
---

# FEAT-2855: Track codebase maintainability trend as an observability dimension

Origin: ll-product #FEAT-053

## Summary

Existing agent-quality observability measures agent *outcome* quality — success rate, retries, corrections, cost, regressions with model attribution. Nothing measures whether the repo itself is getting harder to change under sustained agent activity.

Derive a maintainability trend from repo-history signals (change coupling, shotgun-surgery spread, churn concentration) joined against `.ll/history.db` runs, so degradation attributable to agent batches becomes visible.

## Motivation

Coding agents are good at closing a task and indifferent to what that task does to the codebase's long-term shape. The cost of poor structure is paid over months; nothing in a per-issue success signal can see it. A project can therefore show a rising fix-rate and a falling cost-per-issue while steadily becoming more expensive to work in — and the existing metrics will report that as improvement.

This is distinct from quality-regression detection, which attributes regressions in *agent outcomes* to models or host versions. Here the subject is the repository, and the question is whether it is getting worse.

## Proposed Change

Compute a small set of structural signals over repo history, sampled at intervals, and join them to the `.ll/history.db` run record so a trend can be attributed to periods of agent activity.

Candidate signals (all derivable from `git log` alone, no LLM):

- **Change coupling** — pairs of files that repeatedly change together despite not being obviously related. Rising coupling means edits are spreading.
- **Shotgun-surgery spread** — files touched per logical change, trended. A rising median means single changes require more places.
- **Churn concentration** — share of total churn landing in the top-N hottest files. Rising concentration flags files becoming change magnets.
- **Change-set entropy** — how scattered a typical commit's touched paths are across the directory tree.

Output:

1. A command that reports each signal as a time series across sampling points, over any repo with history.
2. A join against `.ll/history.db` so sampling windows can be labeled by the agent runs that occurred in them.
3. A summary verdict per signal: improving / stable / degrading (conforming to the existing `issue_history` verdict vocabulary — see Advisory), with the magnitude and the window compared.

## Design Notes

- Everything must be computable from `git log` plus `.ll/history.db`. No language-specific static analysis in the first cut — that would restrict the feature to one ecosystem and is not where the signal is.
- These signals are noisy on small histories. Define and enforce a minimum-history threshold and refuse to report a trend below it rather than emitting a confident-looking number from three commits.
- Attribution is *correlational*, and the output must say so. A window labeled with agent runs is not a claim those runs caused the trend. Overclaiming here would make the whole metric family untrustworthy.
- Reuse the existing history/report substrate rather than building a parallel one — concretely, home the command under the existing `ll-history` CLI (a `trend`/`maintainability` subcommand) rather than adding a new top-level entry point.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No existing `git log`-derived structural-signal code today.** `scripts/little_loops/issue_history/coupling.py::analyze_coupling()`, `hotspots.py::analyze_hotspots()`, and `regressions.py::analyze_regression_clustering()` already implement close analogs of "change coupling," "churn concentration," and "shotgun surgery" — but their input is **file paths mentioned in issue markdown text** (`_extract_paths_from_issue()` in `issue_history/parsing.py`), not actual `git log` diffs. This is a real gap between the existing analog and what FEAT-2855 needs: a new git-log-driven module, not a repurposing of these.
- **`git log --numstat`/rename detection does not exist anywhere in the codebase yet.** The only existing `git log` subprocess wrapper is `_backfill_commit_events()` in `scripts/little_loops/session_store.py` (~line 2001), which runs `git log --all --name-only --pretty=format:...` (file paths touched only, no line-diff counts, no `-M`/`--follow`). It's the nearest template to copy the subprocess-invocation shape from (timeout, `cwd=repo_root`, `capture_output=True, text=True`, delimiter-based parsing via `\x1e`/`\x1f`), but a new module must add `--numstat` and `-M` itself.
- **Commit → issue attribution already exists** via the `commit_events` table (`session_store.py`, schema ~line 677: `commit_sha` UNIQUE, `issue_id`, `files_json`, ...), written by `record_commit_event()`/`_infer_issue_id()` and read via `history_reader.py::recent_commit_events(branch, issue_id, ...)`. This is the "issue = unit of logical change" join point the Design Notes call for. There is currently no reverse lookup (commit SHA → issue); it would be a trivial `SELECT issue_id FROM commit_events WHERE commit_sha = ?` addition to `history_reader.py` if needed.
- **Verdict classification precedent**: `analyze_rejection_rates()` in `scripts/little_loops/issue_history/quality.py` (~line 197) already implements the improving/stable/degrading shape this issue asks for — bucket a metric by period, compare the most recent window against an earlier one with ratio thresholds (`rates[-1] < rates[0] * 0.8` → improving, `> 1.2` → degrading, else stable), defaulting to "stable" below a minimum bucket count (`len(sorted_months) < 3`). The three-way trend string is stored on dataclass fields in `issue_history/models.py` (`trend: str = "stable"`) and rendered via a symbol lookup in `issue_history/formatting.py`. A new maintainability verdict should mirror this ratio-threshold-vs-earliest-bucket shape rather than invent a new scheme.
- **Minimum-history guard precedent**: `issue_history/debt.py` guards derived metrics with inline thresholds (e.g. `if len(issue_dirs) < 3:`, `if outcome.total_count >= 5:`) and always **silently omits/defaults the field** rather than raising — matching this issue's AC that a below-threshold repo gets an explicit "insufficient history" result, not an exception.
- **Read-only DB access idiom**: `history_reader.py::_connect_readonly(db_path)` (line 417) is the established helper — `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`, returns `None` on failure. `issue_history/evolution.py::_open_db()` additionally sets `PRAGMA query_only = ON`. A new module should import `_connect_readonly` directly rather than re-implementing the URI-mode connect.
- **CLI subcommand shape to copy**: `scripts/little_loops/cli/history.py::main_history()` uses one `argparse` subparser + arg block per subcommand (`summary`, `analyze`, `export`, `sessions`, `root`) followed by a single `if args.command == "...":` dispatch chain. A new `trend` subcommand follows the same shape — its own `subparsers.add_parser("trend", ...)` block plus a dispatch branch that lazily imports the new analysis function. Multi-format output (`format_analysis_{json,yaml,markdown,text}`) is the existing convention to reuse for `--format`.
- **Synthetic-repo test fixture**: `scripts/tests/helpers.py::copy_git_template()` (process-wide cached `git init` template, `shutil.copytree`d per test) plus the `temp_git_repo` fixture pattern in `test_merge_coordinator.py` is the fast-path template for the four required synthetic-repo tests (degradation, improvement, flat, below-threshold) — extend it with a sequence of commits shaping each scenario, including a `git mv`-based rename in one to exercise the rename-detection AC.
- **Define the unit of "logical change".** A raw commit is a bad unit — squash vs. granular commit styles skew shotgun-surgery spread arbitrarily. Since `.ll/history.db` links commits to issues, the unit is the *issue* (all commits attributed to one issue = one logical change), falling back to per-commit for unattributed history, and the report labels which unit each window used.
- **Rename detection is required.** Compute file identity with git rename detection (`-M`/`--follow` semantics); without it, churn concentration and change coupling degrade to noise after any refactor that moves files.
- Read-only against every source, including `.ll/history.db`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — add a `trend`/`maintainability` subparser + dispatch branch in `main_history()`, following the `analyze` subcommand's shape (arg block + `resolve_history_db()` + lazy import + multi-format print)

### New Files (implementation)
- `scripts/little_loops/issue_history/maintainability.py` (suggested new module, sibling to `coupling.py`/`hotspots.py`) — git-log-driven signal computation (change coupling, shotgun-surgery spread, churn concentration, change-set entropy), `git log --numstat -M` invocation, minimum-history guard, verdict classification

### Dependent Files (Reused Infrastructure)
- `scripts/little_loops/session_store.py:_backfill_commit_events()` (~line 2001) — template for the `git log` subprocess invocation shape (must add `--numstat`, `-M` — not present today)
- `scripts/little_loops/session_store.py` `commit_events` table (schema ~line 677) — existing commit ↔ issue attribution to join sampling windows against
- `scripts/little_loops/history_reader.py:_connect_readonly()` (line 417), `recent_commit_events()` — read-only DB idiom and existing issue→commits read path
- `scripts/little_loops/issue_history/quality.py:analyze_rejection_rates()` (~line 197) — verdict (improving/stable/degrading) ratio-threshold pattern to mirror
- `scripts/little_loops/issue_history/debt.py` — minimum-sample guard pattern (`if len(x) < 3:` → silent default, not exception)
- `scripts/little_loops/issue_history/hotspots.py:analyze_hotspots()` — top-N churn aggregation shape to mirror for churn concentration
- `scripts/little_loops/issue_history/analysis.py:calculate_analysis()` — existing aggregation entry point other signal modules plug into

### Similar Patterns
- `scripts/little_loops/issue_history/formatting.py` — `format_analysis_{json,yaml,markdown,text}()` multi-format dispatch to follow for `--format`
- `scripts/little_loops/cli/ctx_stats.py` / `little_loops.cli_args.add_json_arg()` — `--json` flag convention

### Tests
- `scripts/tests/helpers.py:copy_git_template()` + `temp_git_repo` fixture (`test_merge_coordinator.py:22-35`) — synthetic-repo fixture base for the four required test scenarios (degradation, improvement, flat, below-threshold), including a `git mv` rename case
- `scripts/tests/test_issue_history_advanced_analytics.py`, `scripts/tests/test_cli_history.py` — existing test files most analogous to where new coverage would live (advanced-analytics signal tests, CLI subcommand tests)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_history_advanced_analytics.py::TestRejectionAnalysis`/`TestAnalyzeRejectionRates` (~line 1389) — verdict-string assertion shape to mirror: construct the dataclass with known inputs, call `to_dict()`, assert the trend field is a plain string literal — not enum/tolerance math in the test itself.
- `scripts/tests/test_cli_history.py` (`TestHistoryAnalyzeYaml`/`TestHistoryRootSubcommand`, ~lines 46-130) — CLI end-to-end pattern: patch `sys.argv`, mock `little_loops.issue_history.<fn>` (function-local imports in `main_history()` mean mocks must target the *source* module, not `little_loops.cli.history.*`) — same convention applies to mocking `little_loops.issue_history.maintainability.*`. Also mirror `test_root_no_db_returns_1`'s "returns 1 gracefully, prints message" shape for the new subcommand's minimum-history guard path.
- `scripts/tests/test_issue_history_parsing.py:200-239` (`test_git_log_fallback_when_no_date_field` and neighbors) — `subprocess.run` mock pattern (`patch("little_loops.issue_history.parsing.subprocess.run", return_value=CompletedProcess(...))`) to isolate `git log --numstat -M` parsing/aggregation logic from real git behavior; covers empty-stdout, non-zero-exit, and `OSError` branches. Use this for fast unit coverage of `maintainability.py`'s parsing, complementary to the `temp_git_repo` fixture (which should be reserved for end-to-end rename-detection correctness).
- **No existing example for the `git mv` rename-detection scenario** — confirmed via grep, zero matches for `git mv`/rename in `test_merge_coordinator.py`. This test must be authored from scratch: stage a file, `git mv` it, commit, then run `git log --numstat -M` against the resulting `temp_git_repo` and assert churn/coupling continuity across the rename.
- Dispatch-chain risk check: `main_history()` dispatches via sequential `if args.command == "...":` (not `elif`/`match`) at lines 242/258/296/313/373 — adding a `trend` branch is additive; no exhaustive-match test exists over the subcommand set, so no at-risk existing test was found.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`### ll-history` section, line ~2078) — add a `#### ll-history trend` subsection with its own examples block, following the existing per-subcommand format (`summary` @2093, `analyze` @2104, `export` @2117, `sessions` @2132, `root` @2160).
- `docs/reference/API.md` (`main_history()` doc, ~line 4028) — module-reference summary sentence and/or a worked example block needs the new subcommand mentioned, mirroring the existing `export` example (lines 4047-4078).
- `.claude/CLAUDE.md` (`ll-history` line, ~212-213) **and** `scripts/little_loops/init/writers.py` (~line 108) — the CLAUDE.md description is duplicated verbatim in `writers.py`, which is what `ll-init` stamps into a fresh project's generated CLAUDE.md. Both copies must be updated together or they drift.
- `skills/analyze-history/SKILL.md` — "When to Activate" bullets (~lines 16-24) and the intent-mapping table (~lines 96-103) are this feature's primary *skill*-level routing surface (activates on "project health"/"trends" queries). Add a maintainability-trend trigger phrase (e.g. "is our code getting harder to maintain?") and route it to the new subcommand, or the skill won't surface it.
- `docs/reference/COMMANDS.md` — unconfirmed but flagged: may contain a parallel "user asks X → run ll-history Y" intent table mirroring `analyze-history/SKILL.md`'s; worth a direct check during implementation.
- `ll-verify-docs` (`main_verify_docs`) — unconfirmed whether it enumerates `ll-history` subcommand counts as part of its documented-vs-actual count check; worth a direct read before assuming no gate impact.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` (`history` block, line ~1798, "single namespace owner for all history.db consumer tunables") — a minimum-history-threshold / sampling-window config knob belongs here as a new property with `type`/`default`/`description`, following the existing `velocity_window` (ENH-1905) pattern rather than a new top-level block.

### Advisory (non-blocking)

_Wiring pass added by `/ll:wire-issue`:_
- **Verdict vocabulary mismatch**: this issue's Proposed Change/AC text uses "improving / flat / degrading," but the existing codebase convention (`analyze_rejection_rates()` in `issue_history/quality.py:197-209`, the pattern this issue explicitly says to mirror) uses **"improving" / "degrading" / "stable"** — no `"flat"` synonym exists elsewhere in `issue_history/`. Recommend conforming to `"stable"` for consistency with existing fixtures/tests unless there's a deliberate reason to diverge.
- `scripts/little_loops/issue_history/__init__.py` (lines 65-207) — the package's public API is re-exported here from each submodule (`analyze_coupling`, `analyze_hotspots`, etc.); the new `maintainability.py` module's public functions should be added to this export list to match the existing package convention, even though `cli/history.py` could import the submodule directly.

## Acceptance Criteria

- [ ] A command computes each structural signal as a time series over an arbitrary git repo's history.
- [ ] Signals are derived from `git log` and `.ll/history.db` only — no language-specific static analysis, no LLM calls.
- [ ] Sampling windows are joinable to the agent runs recorded in `.ll/history.db`.
- [ ] The command ships as an `ll-history` subcommand, not a new top-level CLI.
- [ ] The logical-change unit is the issue where `.ll/history.db` attribution exists, per-commit otherwise, and the output labels which unit applied.
- [ ] File identity survives renames (git rename detection); a synthetic-repo test with a renamed hot file shows continuity.
- [ ] Each signal reports a verdict (improving / stable / degrading — matching `analyze_rejection_rates()`'s vocabulary) with magnitude and comparison window.
- [ ] A repo below the minimum-history threshold gets an explicit "insufficient history" result, not a computed trend.
- [ ] Output states that agent-run attribution is correlational.
- [ ] All source data is opened read-only; no source DB or repo state is mutated.
- [ ] Tests cover: a synthetic repo with injected degradation, one with injected improvement, a flat repo, and a repo below the history threshold.


## Session Log
- `/ll:wire-issue` - 2026-07-27T17:11:17 - `ab74d852-fc92-408d-88fc-3f7779e039d6.jsonl`
- `/ll:refine-issue` - 2026-07-27T16:36:13 - `508c9316-4962-416d-986d-9fbcbeb490a0.jsonl`
