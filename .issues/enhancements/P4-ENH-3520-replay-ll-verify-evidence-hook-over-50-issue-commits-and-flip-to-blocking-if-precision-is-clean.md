---
id: ENH-3520
type: ENH
title: Replay ll-verify-evidence hook over 50 issue commits and flip to blocking if
  precision is clean
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T23:24:10Z'
labels:
- enhancement
- verify-evidence
- pre-commit
relates_to:
- BUG-3282
- ENH-3518
blocked_by: []
parent: ENH-3515
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3520: Replay ll-verify-evidence hook over 50 issue commits and flip to blocking if precision is clean

## Summary

Decide with evidence whether the warn-only `ll-verify-evidence` pre-commit hook can become blocking: replay it over the 50 most recent `.issues/` commits in historical isolation, classify every finding, and drop `|| true` only if there are zero false positives. Split out of ENH-3515.

## Current Behavior

The hook is warn-only (BUG-3282) because it fires inside ll-auto / ll-parallel / refine-loop commits, where a precision miss would block a commit mid-run. The BUG-3282 comment says to flip "once the whole-corpus precision smoke test has a stable ceiling", but `TestWholeCorpusPrecision` covers extraction only — no measurement of hook precision on real staged changes exists.

## Expected Behavior

A retained replay report either justifies blocking (hook flipped, comment and display name updated) or records why it stays warn-only.

## Motivation

The BUG-3282 comment defers blocking to a precision signal that does not exist, so the hook would otherwise stay warn-only indefinitely. A one-time, reproducible measurement turns that into a decision. The repo gate remains the backstop; refine-time coverage becomes available when ENH-3519 lands. Prefer deploying that write-time feedback before enabling blocking, without making it a prerequisite for conducting this replay.

## Proposed Solution

- **Reproducible replay**: freeze and record the verifier revision and the 50 most recent commits touching `.issues/` at the measurement cutoff. For each commit, use an isolated repository with its parent as HEAD and the commit's tree staged and checked out; pass explicit changed issue filenames to `ll-verify-evidence --added-only`. Define first-parent handling for merges and deletion/rename handling. Do not mutate the developer's index or working tree. Simply checking out a commit produces no staged additions and is not a replay.
- **Historical isolation**: the matcher uses `git log --all`. Restrict replay refs to history available at the parent, with the target commit's tree supplying the staged/working content; exclude later revisions and unrelated refs. A normal worktree sharing current refs is insufficient. Isolate verdict caches per replay repository so cached results do not leak across historical states.
- **Evidence and coverage**: retain a replay report with cutoff, commit IDs, verifier revision, setup/reproduction instructions, changed files/added lines, eligible candidate counts, findings and their manual true/false-positive classifications, and execution errors. Confirm nonzero eligible coverage and use a deliberately invalid staged quote as a positive control. Zero findings on an empty or broken replay is not precision evidence. Store the report under `postmortems/` and cite its path, date, and summary in the hook comment.
- **Maintenance operations**: exercise rename/move and substantial rewrite fixtures containing grandfathered invalid evidence. Classify findings along two axes: quote accuracy (true/false positive), and origin (newly authored versus pre-existing evidence exposed as added lines). Record which routine maintenance operations would block. Zero quote-accuracy false positives alone does not establish safe rollout; explicitly document and justify the intended handling of pre-existing evidence before flipping. If handling remains undecided, retain warn-only. Do not change matching rules merely to make these fixtures pass.
- **Staged-scan failure policy**: explicitly document and test production behavior when staged-line detection fails. The existing whole-file fallback can surface grandfathered findings, so it must not silently masquerade as a successful staged scan. Retaining fail-closed behavior is allowed with a visible execution/fallback diagnosis; do not silently switch to fail-open to avoid blocking. Record the resulting exit/output contract. If safe behavior requires a verifier change, capture that as a prerequisite follow-up and keep this issue warn-only until it lands. Replay failures still invalidate the measurement.
- **Conditional flip to blocking** (drop `|| true`): only after the complete, valid 50-commit replay has zero false positives, its coverage/control checks pass, and maintenance-operation and staged-scan-failure policies are explicitly settled and tested. Report the actual eligible sample size and its limitations; nonzero coverage alone does not justify broad confidence. Otherwise retain warn-only + verbose and record the false positives or why the measurement was inconclusive. If blocking is enabled, also remove "(warn-only)" from the hook's display name.

## Integration Map

### Files to Modify
- `.pre-commit-config.yaml` — conditionally drop `|| true`; rewrite the BUG-3282 comment with the replay date, result and report path; display name
- `postmortems/` — the replay report (gitignored, source-repo-only)
- `docs/reference/CLI.md` — `ll-verify-evidence` entry, only if the hook flips to blocking

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — on a flip, the `**--added-only FILE...**` mode bullet ("The pre-commit hook.") and the `**Exit codes:**` line under `### ll-verify-evidence` are the only hook-behavior prose; neither currently says warn-only, so add blocking-behavior wording there rather than hunting for a "warn-only" string [Agent 2 finding]
- `.pre-commit-config.yaml` — the `ll-verify-private-refs` sibling entry (`exclude: ^(postmortems/|...)`) shows the exclusion convention; the `ll-verify-evidence` entry's `files: ^\.issues/.*\.md$` already excludes `postmortems/`, so the report path needs no hook change [Agent 1 finding]

### Tests
- Rename/move and substantial-rewrite fixtures distinguish newly authored findings from pre-existing evidence; inject a staged-line Git failure and assert the documented output/exit policy. Scrub inherited Git repository/index environment overrides in isolated test and replay subprocesses.
- `scripts/tests/test_verify_evidence_pre_commit_gate.py` (landed via ENH-3518) derives the expected exit status from the configured policy; after a flip it must assert a non-zero exit for the invalid staged quote with no test rewrite beyond that.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_cli_registry.py` — `DOC_STRINGS_PRESENT` pins `("docs/reference/CLI.md", "ll-verify-evidence", "BUG-3282")`; a CLI.md edit on flip must keep that string present (no change needed, regression guard) [Agent 3 finding]
- `scripts/tests/test_ci_checkout_policy.py` — `test_unit_tests_checkout_fetches_full_history` pins `fetch-depth: 0` for the suite gate; unaffected by the flip, but confirms the suite gate stays the backstop [Agent 3 finding]
- No existing test asserts the hook's `|| true` / "(warn-only)" text today (only ENH-3518's new module will); the flip is otherwise untested until that module exists [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **Hook path never consults the verdict cache.** `scan_paths` (`scripts/little_loops/cli/verify_evidence.py`) builds `ArtifactMatcher` without `verdict_cache`; only `scan_all` (and `scan_all_parallel`'s serial fallback) attaches one. `VERDICT_CACHE_PATH` is a module constant resolved as `base_dir / ".ll/evidence-verdict-cache.json"` with no env/flag/config override. Constraint: per-replay cache isolation is satisfied by giving each replay repo its own root (`-C/--directory` or cwd); it is not a separate mechanism, and the replay report should record that `--added-only` never reads the cache.
- **`--added-only` fails open.** `staged_added_lines(base_dir, paths)` returns `None` on any git error or non-zero exit, and `scan_paths` then scans the *whole* file (`allowed_lines=None`). Constraint: a replay commit that hits this path measures whole-file precision, not staged-addition precision, and must be recorded as an execution error rather than a clean result.
- **Index vs working tree must agree.** `staged_added_lines` reads `git diff --cached -U0` (index), but `scan_file` reads the working-tree file and matches added line numbers against it. Constraint: the replay repo must have the commit's tree both staged against the parent HEAD and checked out, or added-line numbers will not line up.
- **History matching is scoped by `git log --all`.** `HistoryIndex._run_full` / `ensure_paths` run `git log --all --raw` in `base_dir`, capped by `max_revisions` (default `DEFAULT_MAX_REVISIONS = 80`), and tiers are working tree → history blobs. Constraint: an isolated repo containing only the parent's history is what makes "no later revisions" true; the verifier's `--max-revisions` value belongs in the recorded verifier identity.
- **The `|| true` wrapper hides the verdict.** `.pre-commit-config.yaml` entry is `bash -c 'll-verify-evidence --added-only "$@" || true' --` (`pass_filenames: true`, `files: ^\.issues/.*\.md$`), so a replay through pre-commit cannot observe exit status; findings are only visible via output. Constraint: replay measurement needs the CLI's own exit code / `--json` findings (`_findings_to_json`), and must also reproduce the hook's `files` filter so the same file set is eligible.
- **`TestWholeCorpusPrecision` is extraction-only.** Its sole test (`test_candidate_extraction_precision_ceiling` in `scripts/tests/test_verify_evidence.py`) never calls `resolve_artifact`, `ArtifactMatcher`, `staged_added_lines` or the CLI, and omits the `section` argument `scan_file` passes — confirming the issue's premise that no hook-precision measurement exists.
- **ENH-3518's gate module has landed.** `scripts/tests/test_verify_evidence_pre_commit_gate.py` exists and derives the policy from the real config (`_is_warn_only` reads the `entry:` line for `|| true`; asserts name "warn-only" text agrees with it). The hook also carries `verbose: true`. `blocked_by: ENH-3518` is resolved.
- **Conventions in force (evidence, not templates):**
  - Pre-commit gate tests assert structure by reading `.pre-commit-config.yaml` as text (substring checks), never via YAML parsing (`test_decisions_yaml_pre_commit_gate.py`), so a flip must keep `entry:` and the `name:` "(warn-only)" text mutually consistent as literal strings.
  - Throwaway repos are `tmp_path` + `git init` + repo-local identity, with explicit subprocess timeouts (60s/120s) because an untimed subprocess once wedged an xdist run (`test_verify_evidence.py` `GATE_TIMEOUT`); identity values and initial branch vary between files. No existing test scrubs inherited `GIT_DIR`/`GIT_INDEX_FILE` — contested/absent, so a replay running under pre-commit or ll-auto should decide this knowingly.
  - `postmortems/` is gitignored, flat `.md` reports with a title and header-fields block; filename scheme varies (`<topic>-<date>.md`, `<date>-<topic>.md`), so no single naming rule is in force. It is also excluded from `ll-verify-private-refs`.

## Implementation Steps

1. Build the isolated replay harness (parent as HEAD, commit tree staged, refs restricted to the parent's history, per-replay verdict cache); validate it with the positive control, maintenance-operation fixtures, and staged-line failure injection.
2. Run the 50-commit replay; classify every finding by both accuracy and evidence origin; record sample-size limitations and production failure/maintenance policies; write the report under `postmortems/`.
3. Flip to blocking only if all conditions pass; otherwise keep warn-only. Update comment and display name consistently; update `docs/reference/CLI.md` only on a flip.
4. Run the hook gate tests and the full suite.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- On a flip, update `docs/reference/CLI.md` `### ll-verify-evidence` — the `--added-only` mode bullet and `**Exit codes:**` line; keep the literal `ll-verify-evidence` string (pinned by `test_wiring_cli_registry.py` `DOC_STRINGS_PRESENT`)
- Run `scripts/tests/test_wiring_cli_registry.py` and `scripts/tests/test_docs_audience_gate.py` after any CLI.md edit

## Impact

- **Priority**: P4 — the suite gate remains the backstop either way.
- **Effort**: Moderate-Large — isolated historical replay plus manual classification.
- **Risk**: Low if gated as specified; a blocking hook with imperfect precision could stall automation commits.

## Parent Issue

Decomposed from ENH-3515: Shift-left evidence verification to refine-time and make the pre-commit hook visible

## Program Design

### Types

- None — no new code shapes; the replay harness is throwaway tooling recorded in the report.

### Signatures

- `main_verify_evidence(argv: list[str] | None = None) -> int` — invoked unchanged with `--added-only`
- `staged_added_lines(base_dir: Path, paths: list[Path]) -> dict[str, set[int]] | None` — why the replay must stage the commit's tree (a plain checkout yields no added lines)

### Call Path

replay harness -> isolated repo (parent as HEAD, commit tree staged) -> `main_verify_evidence` `--added-only` -> `staged_added_lines` -> findings -> manual classification -> report -> conditional `.pre-commit-config.yaml` edit

## Acceptance Criteria

- [ ] A replay report exists under `postmortems/` with the cutoff, the 50 commit IDs, verifier revision, reproduction steps, eligible candidate counts, per-finding accuracy and new/pre-existing origin classifications, sample-size limitations, and execution errors.
- [ ] The replay used staged changes in isolated repositories with historically restricted refs and per-replay verdict caches; it shows nonzero eligible coverage and a working positive control.
- [ ] Rename/move and rewrite fixtures document how grandfathered evidence behaves; staged-line failure injection verifies an explicit production diagnostic/exit policy. Unsettled behavior or a required verifier follow-up keeps the hook warn-only.
- [ ] Blocking is enabled only if the replay is complete, has zero manually classified false positives, and the maintenance/failure policies are settled and tested; otherwise the hook stays warn-only and the reason is recorded.
- [ ] The hook comment records the date, result, and report path; display name and entry agree with the behavior; the hook gate tests pass under the resulting policy.
- [ ] If the hook flips to blocking, `docs/reference/CLI.md` `### ll-verify-evidence` (`--added-only` bullet and **Exit codes:** line) describes blocking behavior and keeps the pinned `ll-verify-evidence` string.

## Scope Boundaries

- **Non-goal: surfacing warn-only hook findings in ll-auto / ll-parallel run summaries.** Capture a follow-up only if the hook stays warn-only *and* automation-written findings keep reaching the suite gate.
- **Non-goal: changing verifier matching rules** to make the replay pass.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-19 | Priority: P4


## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND** (AC-coverage gaps corrected in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

All referenced files, line numbers and code claims verified against the current tree; `ll-verify-evidence` reports no unverifiable quotes. Graph provider: codegraph (fresh) available; not needed.

- AC coverage: the conditional `docs/reference/CLI.md` update on a flip had no acceptance criterion — added.
- Confirmed: `staged_added_lines` fails open (`None` → whole-file scan); `scan_paths` never attaches a verdict cache; hook entry still `|| true`.

_Corrections in the `/ll:verify-issues` 2026-09-20 pass:_ `blocked_by: ENH-3518` cleared (ENH-3518 is done); the "gate module absent" claim was outdated — the module exists and is policy-derived; `scan_paths` now also takes a `strict` flag (`ScanExecutionError` on infra failure), but `--added-only` still calls `staged_added_lines` unguarded, so the fail-open-to-whole-file behavior claim still needs a direct check during the staged-scan-failure step.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-19_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- `stale_file_ref`: `scripts/tests/test_verify_evidence_pre_commit_gate.py` is not git-tracked — expected, since ENH-3518 creates it.

### Gaps to Address
- Unresolved dependency: `blocked_by` ENH-3518 is still `open`. Land ENH-3518 (it creates the gate test module this issue's flip relies on), or drop the edge if the replay should proceed independently (the Motivation says ENH-3519, not ENH-3518, is the non-prerequisite).

### Outcome Risk Factors
- Moderate per-site complexity: the isolated historical replay harness (parent-as-HEAD, staged tree, restricted refs, env scrubbing) is throwaway but non-trivial and untested itself.
- Conditional outcome: several branches (maintenance-op policy, staged-scan failure policy) may resolve to "stay warn-only" or require a verifier follow-up.

## Session Log
- `/ll:confidence-check` - 2026-09-20T04:27:53 - `9af02f8b-62d4-49a5-a1db-e54179e5abc0.jsonl`
- `/ll:verify-issues` - 2026-09-20T04:26:17 - `870e2333-9233-4bbd-8a9b-511ffb8b0392.jsonl`
- `/ll:confidence-check` - 2026-09-20T02:58:31 - `977f15ce-7c46-446a-8bf0-6c67847cf478.jsonl`
- `/ll:verify-issues` - 2026-09-20T01:36:18 - `58521fbd-d3a2-45c1-879f-6abf803572a3.jsonl`
- `/ll:wire-issue` - 2026-09-20T00:32:34 - `1b17328e-89d8-45f8-a318-abba67ffafef.jsonl`
- `/ll:refine-issue` - 2026-09-20T00:19:02 - `09e2af9d-eb90-432a-a570-962fb9c5f142.jsonl`
- `/ll:format-issue` - 2026-09-20T00:10:58 - `d0eb6446-04cf-4c6e-ada1-f1ab3056d581.jsonl`
