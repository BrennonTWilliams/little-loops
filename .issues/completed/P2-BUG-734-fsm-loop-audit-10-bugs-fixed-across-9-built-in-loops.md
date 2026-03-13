---
discovered_commit: 03befd29f842d74a82830ececb921397469252ef
discovered_branch: main
discovered_date: 2026-03-13T00:00:00Z
discovered_by: manual-audit
confidence_score: 100
outcome_confidence: 100
---

# BUG-734: FSM loop audit — 10 bugs fixed across 9 built-in loops

## Summary

Comprehensive state-by-state trace of all 19 built-in loops in `loops/`. Found and fixed
10 issues ranging from crash-on-entry bugs to inverted routing logic. Three were critical
(crash or fundamentally wrong behavior); seven were medium/low severity.

## Bugs Fixed

### Critical

**1. `plugin-health-check.yaml` — `fix_config` crash on early failure path**

`fix_config` referenced `${captured.audit_result.output}` in its action, but `audit_result`
is only populated after `audit_config` runs. When `validate_plugin` fails and jumps directly
to `fix_config`, `interpolate()` raises `InterpolationError` → loop terminates with "error"
instead of fixing.

*Fix:* Removed `${captured.audit_result.output}` reference from `fix_config`. State now
shows only `plugin_state.output`, which is always available on the early failure path.

---

**2. `priority-rebalance.yaml` — stale snapshot fed to `analyze_balance` on second iteration**

`snapshot` captured to `before_snapshot`; `verify` (post-rebalance) captured to `after_snapshot`.
On the second pass (`check_healthy` → `analyze_balance`), `analyze_balance` still read
`before_snapshot` (pre-rebalance data), making the second analysis think nothing had changed.

*Fix:* Unified both captures under `current_snapshot`. `snapshot` writes `current_snapshot`;
`verify` also writes `current_snapshot`. `analyze_balance` and `check_healthy` both read
`current_snapshot`, always seeing the freshest distribution.

---

**3. `pr-review-cycle.yaml` — `secrets_found` displayed branch metadata instead of secret matches**

`secrets_found` showed `${captured.branch_info.output}` (branch name + diff stat) when
secrets were detected. The AI reviewer received no information about what patterns triggered
the alert.

*Fix:* Replaced the captured variable reference with an instruction to run the grep command
directly, so the reviewer sees the actual matching lines.

---

### High

**4. `worktree-health.yaml` — `prune_branches` deleted all merged branches, not just ll-parallel ones**

Loop description says it targets branches from ll-parallel runs, but the shell action deleted
any branch merged into main (matching only `*` and `main` exclusions). User feature branches
merged but retained for reference would be silently deleted.

*Fix:* Added `grep 'issue-'` filter so only ll-parallel `issue-*` branches are pruned.

---

### Medium

**5. `type-error-fix.yaml` — no commit after fixing type errors**

Fixes accumulated across many iterations with no intermediate saves. A session handoff could
leave uncommitted changes or make diffs hard to review.

*Fix:* Added `commit_fixes` state between `fix_errors` and `run_mypy`.

---

**6. `issue-size-split.yaml` — no commit after splitting issues**

Issue files were created/modified by `split_issue` and normalized by `normalize`, but never
committed. A subsequent `ll-parallel` run could start with uncommitted split files.

*Fix:* Added `commit_split` state between `normalize` and `find_large`.

---

**7. `secret-scan.yaml` — no commit for remediation changes**

`remediate` replaced secrets with env var references but changes were never persisted. The
`on_handoff: terminate` safety is correct, but remediation work could be lost.

*Fix:* Added `commit_remediation` state between `create_issues` and `verify_clean`.

---

**8. `readme-freshness.yaml` — token budget too small; no re-verify back-loop**

`llm: max_tokens: 512` was too small for the structured evaluation that must process a full
discrepancy report. Also, `verify_accuracy` said "fix issues now" but then unconditionally
proceeded to `commit` with no loop-back.

*Fix:* Raised `max_tokens` to 1024. Added `capture: verify_result` on `verify_accuracy` and
a new `route_verify` state that routes back to `update_docs` on failure.

---

**9. `changelog-and-tag.yaml` — changelog not committed before tagging**

`generate_changelog` wrote CHANGELOG.md via a prompt but `create_release` ran
`/ll:manage-release` immediately after — potentially before the file was saved to git. Tags
could end up pointing at a commit without the changelog.

*Fix:* Added `commit_changelog` state between `generate_changelog` and `create_release`.

---

### Low

**10. `docs-sync.yaml` — inverted `on_success`/`on_failure` in `route_results`**

`output_contains` matching `FAIL|ERROR|BROKEN|MISMATCH` returned "success" when problems
were found (pattern matched) and "failure" when clean. Correct behavior, but deeply confusing
to read and maintain.

*Fix:* Added `negate: true` and swapped `on_success: done` / `on_failure: fix_docs`, so
the routing now reads semantically: success = clean, failure = has problems.

---

## Files Changed

- `loops/plugin-health-check.yaml`
- `loops/priority-rebalance.yaml`
- `loops/pr-review-cycle.yaml`
- `loops/worktree-health.yaml`
- `loops/type-error-fix.yaml`
- `loops/issue-size-split.yaml`
- `loops/secret-scan.yaml`
- `loops/readme-freshness.yaml`
- `loops/changelog-and-tag.yaml`
- `loops/docs-sync.yaml`

## Loops Audited and Found Correct

`issue-refinement`, `fix-quality-and-tests`, `dependency-audit`, `issue-staleness-review`,
`issue-discovery-triage`, `sprint-build-and-validate`, `dead-code-cleanup`, `sync-and-close`,
`issue-throughput-monitor` — all correct as-is.
