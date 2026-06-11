---
id: ENH-2093
type: ENH
priority: P2
status: done
captured_at: 2026-06-11 20:40:00+00:00
completed_at: 2026-06-11 21:23:31+00:00
discovered_by: brennon
relates_to: []
labels:
- ll-logs
- scan-failures
- signal-quality
- issue-capture
confidence_score: 98
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2093: `ll-logs scan-failures --capture` produces near-100% noise (wrong-project + non-bug failures)

## Summary

A single `ll-logs scan-failures --capture --all --window-days 3` run created 71 P1
BUG issues (BUG-2093 … BUG-2163), of which **zero** described a reproducible
little-loops defect. All 71 were deleted after review. The capturer has three
independent defects that compound: it scans every project on the machine, it
matches non-CLI `ll-`-prefixed tokens as if they were ll CLIs, and it only
filters `TRANSIENT` failures — letting shell-sandbox errors, OOM kills, and
user-cancelled calls through as P1 bugs.

## Current Behavior

From the 71-issue run, the captured "failures" broke down as:

| Category | ~Count | Example | Why it's noise |
|---|---|---|---|
| Wrong project (`ll-labs` etc.) | ~44 | `ll-labs` tsx/vega/video-pipeline build errors | Separate repo at `/Users/brennon/AIProjects/ai-workspaces/ll-labs`; not an ll CLI |
| Shell-sandbox env | ~7 | `(eval): command not found: grep/head/awk/python3`, `read-only variable: status` | The CLI never ran; Claude's eval sandbox lacked PATH |
| User error / correct behavior | ~5 | `Issue 'FEAT-035' not found`, `<tool_use_error>Cancelled`, JS `NameError: 'true'` | Expected output or user-initiated cancel |
| OOM / kill | ~4 | Exit 137 on `video-pipeline` loop | SIGKILL, not a defect |
| Content-free stubs / aggregates | ~11 | `Exit code 1` only; `[67x] ll-issues exit 1` roll-up | No reproducible signal |

### Root causes (verified in source)

1. **`--all` scans the whole machine.** `_cmd_scan_failures` with no `--project`
   calls `discover_all_projects(logger)` (`scripts/little_loops/cli/logs.py:913`),
   iterating session logs for Agrobot, blender, craft-cards, headstorm, ll-labs,
   etc. The "Decoded path does not exist" spam at the top of the run is this walk.
   Failures from other repos get filed as little-loops bugs.

2. **The CLI matcher accepts any `ll-` token.**
   `_LL_BASH_RE = re.compile(r"\b(ll-[\w-]+)")` (`logs.py:207`) matches `ll-labs`,
   `ll-marketing`, `ll-auto-website`, `ll-labs-loop-viz` — directory/project names,
   not ll CLIs. There is no allowlist against the real CLI set (the `ll-*` tools
   enumerated in `.claude/CLAUDE.md` / the `[project.scripts]` entry points).

3. **Only `TRANSIENT` is filtered.** `classify_failure`
   (`scripts/little_loops/issue_lifecycle.py:54`) screens rate-limit / network /
   timeout / resource / server / context failures, but nothing screens:
   - exit 127 sandbox `command not found` / `read-only variable` (the CLI never executed),
   - exit 137 (SIGKILL/OOM),
   - user cancellations (`<tool_use_error>Cancelled`),
   - inline-snippet tracebacks whose top frame is `File "<string>"` or `File "<stdin>"`
     (an ad-hoc `python -c`/heredoc in the session, not the ll CLI).

## Expected Behavior

`scan-failures --capture` should default to the **current project** and capture
only failures attributable to a **real ll CLI** that represent a **genuine
non-transient defect**. Cross-machine sweeps should be explicit and clearly
labeled, not the path that files bugs into the current repo.

## Motivation

The `--capture` mode of `scan-failures` is currently unusable: a single invocation created 71 P1 bugs that all had to be manually deleted. This blocks:
- `ll-auto` and `ll-parallel` from consuming scan-failures-derived issues without poisoning the backlog with foreign-project and sandbox artifacts
- Maintainers from trusting any automatically captured bugs at all
- The issue-capture pipeline from providing reliable signal about real ll CLI defects

## Proposed Solution

1. **Scope to current project by default.** Treat `--all` as opt-in for *analysis*
   only; require an explicit `--capture-foreign` (or refuse `--capture` together
   with `--all`) before writing issues sourced from projects other than the cwd.
   At minimum, tag each cluster with its originating `cwd_path` and skip capture
   for clusters whose `cwd_path` != the current project root.

2. **Allowlist real CLIs.** Replace the open `ll-[\w-]+` match with membership in
   the known CLI set (derive from `[project.scripts]` in `scripts/pyproject.toml`
   so it stays in sync). Tokens like `ll-labs` then never match.

3. **Extend `classify_failure` (or add a pre-capture filter)** to mark as
   non-capturable:
   - exit 127 with `command not found` / `read-only variable` in output,
   - exit 137 / negative returncodes (signals),
   - `<tool_use_error>` / `Cancelled` content,
   - tracebacks whose top user frame is `<string>` or `<stdin>`.

4. **Drop content-free clusters.** Skip clusters whose only signal is a bare
   `Exit code N` with no error body, and roll-up clusters that mix unrelated exit
   codes for the same tool.

## Implementation Steps

1. **Project scoping**: Update `_cmd_scan_failures` to default to the current project; block `--capture` with `--all` unless `--capture-foreign` is explicit; tag each cluster with its `cwd_path` and skip capture for foreign projects
2. **CLI allowlist**: Replace `_LL_BASH_RE` open regex with an allowlist derived from `[project.scripts]` in `scripts/pyproject.toml` so `ll-labs`, `ll-marketing`, etc. never match
3. **Failure classification**: Extend `classify_failure` (or add a pre-capture filter) to reject exit 127 sandbox errors, exit 137 SIGKILL, user cancellations (`<tool_use_error>Cancelled`), and tracebacks with `<string>`/`<stdin>` as the top user frame
4. **Content-free cluster suppression**: Drop clusters whose only signal is a bare `Exit code N` with no error body; collapse roll-up clusters for the same tool
5. **Unit tests**: Add at least one test per new filter category using representative fixture lines from the 71-issue run
6. **Verification**: Re-run `ll-logs scan-failures --capture --all --window-days 3` over the original logs and confirm ≤ a handful of clusters, all pointing at real ll CLIs with a real error body

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`_FailureCluster` has no `cwd_path` field** (`logs.py:890–898`). To implement project-scoping in `_capture_failure_clusters` (line 1072), add `cwd_path: Path` to the `_FailureCluster` dataclass and populate it in the inner loop at line 924. Without this, `_capture_failure_clusters` cannot route issues to the correct project.
- **`returncode` in `classify_failure` is synthetic** (`logs.py:999`): it is `1 if is_error_flag else 0`, not the actual process exit code extracted from JSONL. Real exit codes (127, 137) are not available at call time. Exit 127 and exit 137 filtering must be text-pattern based (`"command not found"`, `"read-only variable"` for 127; `"Killed"` / `"killed"` for 137) rather than numeric. Extend `classify_failure` to check `error_lower` for these patterns, or add a pre-capture filter in `_cmd_scan_failures` before calling `classify_failure`.
- **`<tool_use_error>Cancelled` filtering**: the string `"<tool_use_error>"` or `"cancelled"` in `error_output` is a reliable text-pattern signal that is not currently screened.
- **`<string>`/`<stdin>` traceback filtering**: tracebacks with `File "<string>"` or `File "<stdin>"` in the top user frame survive `_normalize_error_sig` (those filenames contain no `/` so path-stripping leaves them intact). Add a check for `'file "<string>"'` or `'file "<stdin>"'` in `error_lower` to `classify_failure` (or the pre-capture filter).
- **`tomllib` for allowlist loading**: `tomllib` (Python 3.11+ stdlib) is already imported in `scripts/little_loops/host_runner.py:30`. Add a `_load_cli_allowlist(root: Path) -> frozenset[str]` function to `logs.py` that reads `[project.scripts]` from `root / "scripts/pyproject.toml"` at startup. Full current allowlist (35 entries as of this analysis): `ll-action`, `ll-harness`, `ll-auto`, `ll-parallel`, `ll-messages`, `ll-loop`, `ll-sprint`, `ll-sync`, `ll-workflows`, `ll-history`, `ll-verify-docs`, `ll-verify-skill-budget`, `ll-verify-skills`, `ll-check-links`, `ll-create-extension`, `ll-issues`, `ll-deps`, `ll-doctor`, `ll-gitignore`, `ll-migrate`, `ll-migrate-relationships`, `ll-migrate-labels`, `ll-migrate-status`, `ll-logs`, `ll-session`, `ll-history-context`, `ll-ctx-stats`, `ll-generate-schemas`, `ll-generate-skill-descriptions`, `ll-adapt-skills-for-codex`, `ll-learning-tests`, `ll-verify-triggers`, `ll-adapt-agents-for-codex`, `ll-init`, `ll-create-extension`.
- **Test fixtures to reuse**: `TestScanFailures._make_project_dir` (line 1909), `_assistant_bash_record` (line 1937), `_user_tool_result_record` (line 1961) are the established fixture helpers for new `scan-failures` tests. Add new test methods to `TestScanFailures` (not a new test class) for each new filter category.
- **Related issues**: `P3-ENH-2070` (wiring scan-failures into automated bug intake) and `P3-ENH-1922` (original auto-file-bugs) are upstream dependents. Parent epic: `P3-EPIC-1918`.

## Acceptance Criteria

- [ ] `scan-failures --capture` with no `--project` captures only current-project failures (or errors out directing the user to `--project`).
- [ ] `ll-labs`, `ll-marketing`, `ll-auto-website` and other non-CLI tokens are never captured (allowlist-driven).
- [ ] Sandbox `command not found`, `read-only variable`, exit 137, cancelled calls, and `<string>`/`<stdin>` tracebacks are filtered before capture.
- [ ] Re-running the original command (`--all --window-days 3`) over the same logs yields ≤ a handful of clusters, all pointing at real ll CLIs with a real error body.
- [ ] Unit tests cover each new filter with a representative fixture line from this run.

## Success Metrics

- Noise rate: 71/71 (100%) → ≤10% when re-running `--all --window-days 3` over the same logs
- Foreign-project issues captured: any → 0 for default `--capture` (no `--project` flag)
- Unit test coverage: 0 → ≥1 test per new filter category (exit 127, exit 137, cancellation, `<string>`/`<stdin>`)

## Scope Boundaries

- **In scope**: `scan-failures --capture` default project scoping; `_LL_BASH_RE` allowlist replacement; `classify_failure` extension; content-free cluster suppression; unit tests for new filters
- **Out of scope**: changes to analysis mode (`--all` without `--capture`); fixing or touching `ll-labs` or other foreign repos; refactoring the broader scan-failures clustering algorithm

## Impact

- **Severity**: Medium (capturer is currently unusable for `--capture`; every run poisons the backlog and would mislead `ll-auto`/`ll-parallel` into "fixing" foreign repos)
- **Effort**: Medium
- **Risk**: Low (additive filtering + scoping; defaults become stricter)
- **Breaking Change**: No (behavior change to a maintainer tool; stricter capture)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_LL_BASH_RE` (line 207), `_cmd_scan_failures` (line 901), `discover_all_projects` call (line 913)
- `scripts/little_loops/issue_lifecycle.py` — `classify_failure` (line 54)
- `scripts/pyproject.toml` — read `[project.scripts]` entries to derive CLI allowlist

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — calls `classify_failure` in the issue-capture workflow
- `scripts/little_loops/fsm/executor.py` — calls `classify_failure` during FSM evaluation
- `scripts/tests/test_ll_logs.py:TestScanFailures` (line 1906) — integration tests for `scan-failures`; uses `_make_project_dir`, `_assistant_bash_record`, `_user_tool_result_record` fixture helpers
- `scripts/tests/test_issue_lifecycle.py:TestClassifyFailure` (line 551) — parametrized tests for `classify_failure`

### Similar Patterns
- `scripts/little_loops/cli/logs.py:_LL_VERIFY_RE` (line 861) — existing `re.compile(r"^ll-verify-\w+")` exclusion; matched against `tool_name` with `.match()` before capture. Model the CLI allowlist after this pattern (module-level compiled regex, `.match()` on resolved `tool_name`).
- `scripts/little_loops/cli/logs.py:_load_catalog_names()` (line 743) — loads skill/command names from SKILL.md files for `dead-skills`. Analogous pattern for loading CLI names from `pyproject.toml` at startup; `tomllib` (stdlib, Python 3.11+) is already used in `scripts/little_loops/host_runner.py:30`.
- `scripts/little_loops/fsm/evaluators.py:evaluate_mcp_result()` (line 642) — handles exit codes 127 (`not_found`) and 124 (`timeout`) as named verdicts. Documents the existing exit-code semantics convention in the codebase.
- `--project`/`--all` mutually exclusive group pattern — used verbatim in `_cmd_sequences` (line 476), `_cmd_extract` (line 579), `_cmd_scan_failures` (line 901), and `_cmd_stats` (line 1097). New `--capture-foreign` guard should follow this same argparse pattern.

### Tests
- `scripts/tests/` — add unit tests for each new filter; check for an existing `test_logs.py` or `test_issue_lifecycle.py`

### Documentation
- N/A

### Configuration
- N/A

## Steps to Reproduce

1. From little-loops root: `ll-logs scan-failures --capture --all --window-days 3`
2. Observe dozens of P1 BUG files created for `ll-labs` and other non-little-loops sources, plus sandbox `command not found` and exit-137 failures.

## References

- `scripts/little_loops/cli/logs.py:901` — `_cmd_scan_failures`
- `scripts/little_loops/cli/logs.py:207` — `_LL_BASH_RE` (over-broad matcher)
- `scripts/little_loops/cli/logs.py:913` — `discover_all_projects` (machine-wide sweep)
- `scripts/little_loops/issue_lifecycle.py:54` — `classify_failure` (only TRANSIENT screened)


## Resolution

All four root causes addressed:
1. **Project scoping**: `_FailureCluster.cwd_path` added; `--all --capture` filters to `Path.cwd()` by default; `--capture-foreign` allows cross-project capture
2. **CLI allowlist**: `_load_cli_allowlist()` reads `[project.scripts]` from `scripts/pyproject.toml`; allowlist check gates `_LL_BASH_RE` matches so `ll-labs`, `ll-marketing` etc. never produce clusters
3. **Failure classification**: Extended `classify_failure` with sandbox `command not found`/`read-only variable`, `\bkilled\b` (exit 137/OOM), `<tool_use_error>` cancellations, and `file "<string>"`/`file "<stdin>"` inline-snippet tracebacks
4. **Content-free suppression**: `_is_content_free_error()` drops bare `Exit code N` clusters

Files changed: `scripts/little_loops/cli/logs.py`, `scripts/little_loops/issue_lifecycle.py`
Tests added: 9 new test cases covering each new filter category

## Session Log
- `/ll:ready-issue` - 2026-06-11T21:12:21 - `3ac2514b-07b6-4ff4-a922-29f9a1bce6c3.jsonl`
- `/ll:refine-issue` - 2026-06-11T20:44:21 - `51577893-49ed-4585-85fe-085f192947be.jsonl`
- `/ll:format-issue` - 2026-06-11T20:38:55 - `434467be-41b0-476c-9ed1-087b016d3835.jsonl`
- `/ll:confidence-check` - 2026-06-11T21:00:00Z - `c4275055-dcda-46fd-8df5-e3d9c2532a2d.jsonl`
- `/ll:manage-issue` - 2026-06-11T21:23:31Z
