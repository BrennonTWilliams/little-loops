---
id: EPIC-3436
type: EPIC
title: 'Restore CI unit-suite signal: fix the 6 root causes behind the 7 chronic failures'
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
---

# EPIC-3436: Restore CI unit-suite signal: fix the 6 root causes behind the 7 chronic failures

## Summary

The unit suite on the Linux CI leg had seven chronic failures traced to six root causes. This epic fixes each root cause so a red run means a real regression again. The seven children cover a dead exponential-backoff branch in the SSE fan-in producer, a `commit_leaf` state in `rn-refine` that reports success without committing, an `E2BIG` failure when FSM shell actions exceed Linux `MAX_ARG_STRLEN`, an `ll-doctor` health check that passes a corrupt `history.db`, a missing packaged-profile fallback in `load_design_tokens`, a shallow CI checkout that blinds the evidence gate, and a CPU-count test that only passes on hosts with many cores.

## Motivation

A chronically red unit suite gives no signal: contributors learn to ignore it, and a new regression is indistinguishable from the known failures. Several of these failures only reproduce on Linux or on a clean checkout (`E2BIG`, SQLite build differences, the gitignored design-token mirror, the shallow clone, the 4-core runner), so they pass on the maintainer's machine and never surface in local runs.

## Goal

`python -m pytest scripts/tests/` exits 0 on a clean Linux checkout, and the CI unit-suite run is green without relying on any gitignored local state.

## Scope

**In scope**: the six root causes behind the seven failures, each fixed at its cause (runner, loop YAML, doctor, token loader, CI checkout policy, test patching) with a regression test that pins the fix.

**Out of scope**: unrelated flaky tests, adding paid CI, and changes to the conformance job on the self-hosted runner.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` (BUG-3437: fan-in producer backoff)
- `scripts/little_loops/loops/rn-refine.yaml`, `scripts/little_loops/loops/rn-stepwise.yaml` (BUG-3438: `commit_leaf` failure routing)
- `scripts/little_loops/fsm/runners.py` (BUG-3439: shell actions via temp script file instead of argv)
- `scripts/little_loops/cli/doctor.py` (BUG-3440: SQLite header-magic check)
- `scripts/little_loops/design_tokens.py` (ENH-3441: packaged-profile fallback)
- `.github/workflows/ci.yml` (BUG-3442: `fetch-depth: 0`)
- `scripts/tests/test_conftest_cap.py` (BUG-3443: patch `os.cpu_count`)

### Dependent Files (Callers/Importers)
- N/A — the fixes are independent; each is exercised through its own child's tests.

### Tests
- `scripts/tests/test_feat3323_sse_bridge.py`, `scripts/tests/test_rn_refine.py`, `scripts/tests/test_fsm_runners.py`, `scripts/tests/test_loop_router.py`, `scripts/tests/test_cli_doctor.py`, `scripts/tests/test_enh3441_packaged_profile_fallback.py`, `scripts/tests/test_ci_checkout_policy.py`, `scripts/tests/test_verify_evidence.py`, `scripts/tests/test_conftest_cap.py`

### Documentation
- `docs/reference/API.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`, `docs/reference/loops.md`, `.claude/CLAUDE.md`

## Impact

- **Priority**: P1 - a chronically red suite hides new regressions
- **Effort**: Medium - seven small, independent fixes
- **Risk**: Low - each fix is local and ships with a regression test; BUG-3439 touches the shared shell-action runner
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Children
- **BUG-3437** — SSE fan-in backoff never engages; producers at max_clients re-probed ~10/s forever (done)
- **BUG-3438** — rn-refine commit_leaf reports COMMITTED without committing and routes failure to record_leaf_done (done)
- **BUG-3439** — FSM shell actions pass the whole rendered script via argv; E2BIG on Linux above 128 KiB (done)
- **BUG-3440** — ll-doctor reports a corrupt history.db as healthy on Linux SQLite builds (done)
- **ENH-3441** — load_design_tokens falls back to packaged profiles when .ll/design-tokens/ mirror is absent (done)
- **BUG-3442** — CI shallow checkout makes the evidence gate structurally unable to pass (done)
- **BUG-3443** — test_env_var_overrides_cpu_count asserts against host CPU count instead of patching os.cpu_count (done)

## Success Metrics

- All seven children are `done`.
- The CI unit-suite run on `ubuntu-latest` passes with no known-failure exclusions.
- Each root cause has a regression test that fails without its fix.

## Status

**Open** | Created: 2026-09-10 | Priority: P1

---

## Session Log
- `/ll:format-issue` - 2026-10-01T21:49:14 - `e3920276-5e7a-47b4-bd7c-8c925a02b795.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
