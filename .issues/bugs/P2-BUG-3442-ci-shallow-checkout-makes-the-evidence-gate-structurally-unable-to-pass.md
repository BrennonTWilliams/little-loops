---
id: BUG-3442
type: BUG
title: CI shallow checkout makes the evidence gate structurally unable to pass
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
completed_at: '2026-09-11T05:39:06Z'
parent: EPIC-3436
decision_needed: false
learning_tests_required:
- git
- actions/checkout
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3442: CI shallow checkout makes the evidence gate structurally unable to pass

## Summary

ci.yml unit-tests uses bare actions/checkout@v4 (fetch-depth 1), collapsing the `git log --all --raw` HistoryIndex so ll-verify-evidence reports a large structural excess of unverifiable spans and TestRepoGate::test_no_new_unverifiable_evidence always fails, providing zero signal. Add fetch-depth: 0 with a comment recording why, and add a `git rev-parse --is-shallow-repository` precondition to the gate test that fails loudly with a one-line diagnostic instead of a 150-item mystery (A1).

**Scope correction (2026-09-10 confidence check, measured).** Two claims in this issue are wrong and change what "done" means:

1. The excess is **155**, not 149 — the count drifts as issue files are added, so it must not be pinned as a constant anywhere.
2. **`fetch-depth: 0` alone does not make CI green.** On a full-history clone the same gate still reports **4 findings beyond baseline** and still exits 1 — `TestRepoGate::test_no_new_unverifiable_evidence` **fails on `main` today, locally, with full history**. Those 4 come from sibling issue files (BUG-3439, BUG-3443), not from checkout depth. Fixing this issue takes CI from 155 excess → 4 excess → still red. Clearing the 4 live findings is a prerequisite for a green gate and is tracked in Implementation Steps step 1.

## Steps to Reproduce

1. Push any commit to `main` (or re-run the `unit-tests` workflow).
2. The `unit-tests` job checks out with bare `actions/checkout@v4` — default `fetch-depth: 1`, a shallow clone with only the tip commit.
3. The test suite runs `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py`), which invokes `ll-verify-evidence --all --json`; `HistoryIndex` builds its `path -> blob OIDs` map from one `git log --all --raw` pass.
4. Observe: every span quoted from history older than the tip commit is unverifiable — 155 findings beyond baseline as of 2026-09-10 (the count grows as issue files are added) — so the gate test fails on every CI run regardless of corpus state.
5. Control: run the same gate in a full-history clone. It reports **4** findings beyond baseline and still fails — proving the shallow checkout is not the only thing keeping the gate red.

## Current Behavior

CI's `unit-tests` job (`.github/workflows/ci.yml`) uses bare `actions/checkout@v4`, which defaults to `fetch-depth: 1`. The evidence gate test then runs `ll-verify-evidence --all` against that shallow clone: `HistoryIndex`'s single `git log --all --raw` pass sees only the tip commit, so spans quoted from any earlier artifact state resolve to nothing. The gate reports a large structural excess (155 spans as of 2026-09-10) and `TestRepoGate::test_no_new_unverifiable_evidence` always fails — the gate is always-red and provides zero regression signal.

The shallow checkout is the *dominant* cause but not the *only* one. Reproduced side by side on 2026-09-10:

| Clone | `git rev-list --count --all` | Findings beyond baseline | `ok` | exit |
|---|---|---|---|---|
| `git clone --depth 1` | 1 | **155** | `false` | 1 |
| full history | 8407 | **4** | `false` | 1 |

So the fix converts a structural 155-item mystery into a genuine 4-item corpus regression — which is the point of the gate — but the 4 must also be cleared before CI is green.

## Expected Behavior

- The `unit-tests` checkout uses `fetch-depth: 0` (full history) so `HistoryIndex` sees all commits and the gate passes/fails on actual corpus regressions rather than on checkout depth.
- If the repository is shallow anyway (local shallow clone or a future workflow regression), the gate test detects it up front via `git rev-parse --is-shallow-repository` and **fails fast** with a one-line diagnostic pointing at the missing fetch-depth, instead of a 150-item findings dump. (Decided — Option B; see Proposed Solution.)
- **Success criterion, stated precisely:** after this fix the gate's excess on a full-history checkout equals the *real* corpus regression count and nothing structural. It is **not** "CI goes green" — the 4 live findings from BUG-3439 and BUG-3443 are a separate defect that this issue does not fix, and the gate stays red until they are cleared. Both must land for a green `unit-tests` job.

## Root Cause

- **File**: `.github/workflows/ci.yml` (unit-tests job checkout, line 67) interacting with `scripts/little_loops/cli/verify_evidence.py`
- **Anchor**: `HistoryIndex.ensure_full()` (`verify_evidence.py:733-745`), exercised by `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py:951`)
- **Cause**: The `unit-tests` job's bare `actions/checkout@v4` defaults to `fetch-depth: 1` (shallow). `ensure_full()` builds the `path -> blob OIDs` map from a single `git log --all --raw -z` pass (`verify_evidence.py:745`), which sees only the tip commit — every span quoted from an earlier artifact state resolves to nothing. The gate test compares findings against the checked-in ID-keyed baseline (`.ll/evidence-baseline.json`, `BASELINE_PATH` at `verify_evidence.py:83`) and fails on any excess; on a shallow clone the excess is structural, so the gate is always-red regardless of corpus state. Nothing in the test distinguishes "corpus regression" from "checkout lacks history". No code or CI script in the repo runs `git rev-parse --is-shallow-repository` today, and no workflow sets `fetch-depth`.
- **Secondary cause (independent of checkout depth)**: the corpus genuinely carries 4 unverifiable spans beyond baseline as of 2026-09-10 — 2 from `.issues/bugs/P1-BUG-3439-…md:50` attributed to `scripts/tests/test_loop_router.py` (`subprocess.Popen(["bash", "-c", action])` and `OSError: [Errno 7] Argument list too long`), and 2 from `.issues/bugs/P3-BUG-3443-…md:43,50` (line refs refreshed 2026-09-10 after commit `a06961726` shifted them from `:37,44`) attributed to `scripts/tests/test_conftest_cap.py` (`AssertionError: assert 2 == 3` and `max(1, min(int(env), cpus - 2))`). These reproduce on a full-history clone and are not caused by, nor fixed by, `fetch-depth`.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

Two dispositions exist for the shallow-repo precondition in `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py:951`) — the codebase's conventions are contested on exactly this case, and the issue text itself hedges ("skip-or-fail-fast", "must skip (or fail …) rather than silently pass").

**Option A (rejected)**: `pytest.skip` when `git rev-parse --is-shallow-repository` reports shallow — same-file precedent: missing git state already skips (`test_verify_evidence.py:88`, `:952-953`), and `.claude/CLAUDE.md` § Testing & CI Policy codifies skip-when-missing for gate preconditions.

**Option B**: `pytest.fail` fast with a one-line diagnostic naming the missing `fetch-depth` — the issue's own Expected Behavior; fail-not-skip precedent for protected regression signals (`test_fragment_store.py:6-7`, `test_check_private_refs_hook.py:84`).

> **Selected:** Option B — fail fast with a one-line diagnostic naming the missing `fetch-depth`. A skip silently disarms the gate on every shallow checkout, which is precisely the CI state this bug describes; the fail-not-skip rule covers "absence of a thing the gate exists to protect". Option A is rejected because it would have made this very bug invisible rather than loud.

### Decision Rationale

Decided 2026-09-10 (user-confirmed during the pre-implementation confidence check). Clearing the `decision_needed: true` frontmatter flag is `/ll:decide-issue`'s job and is not done by hand here.

Residual trade-off accepted: Option B hard-fails a contributor's local suite if they cloned with `--depth 1`. That is the intended behavior — the diagnostic names the remedy (`git fetch --unshallow`) in one line, which is strictly more useful than the 155-item dump it replaces, and a silent skip would let a shallow-clone contributor believe the evidence gate had passed.

Workflow side is uncontested: `.github/workflows/ci.yml:67` gains `with: fetch-depth: 0` with an adjacent BUG-3442 + failure-mode comment (ID+failure-mode convention, `ci.yml:73-80`). Verified: `ci.yml:67` is a bare `- uses: actions/checkout@v4` with no `with:` block, and no workflow in the repo sets `fetch-depth`. The `conformance` job's checkout at `:152` is also bare but runs only `-m conformance`, so it never executes `TestRepoGate`; leaving it alone is correct.

## Integration Map

### Files to Modify
- `.github/workflows/ci.yml:67` — unit-tests job checkout: add `with: fetch-depth: 0` plus a comment citing BUG-3442 and the failure mode (always-red evidence gate), following the workflow's ID+failure-mode comment convention (e.g. the BUG-3208 pin-assertion comment at `ci.yml:73-80`)
- `scripts/tests/test_verify_evidence.py:951` — `TestRepoGate::test_no_new_unverifiable_evidence`: add the `git rev-parse --is-shallow-repository` precondition before the gate subprocess run (`:956-957`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/verify_evidence.py:654` — `HistoryIndex`, the component checkout depth feeds via `ensure_full()` (`:733-745`)
- `scripts/little_loops/cli/__init__.py:97` — re-exports `main_verify_evidence` (`__all__` at `:149`)
- `scripts/pyproject.toml:125` — console-script entry point `ll-verify-evidence = "little_loops.cli:main_verify_evidence"`
- `.pre-commit-config.yaml:20,29` — warn-only layer runs `ll-verify-evidence --added-only`; unaffected (local clones are full)
- `scripts/tests/test_verify_evidence.py:78-88` — `_read_blob()` pinned-SHA reads currently **skip silently** on CI for the same shallow reason; after `fetch-depth: 0` the flagship tests using `BUG_3278_SHA = "baa553d9"` (`:49`) start executing on CI for the first time

### Conventions in Force
- Gate tests shell out via `subprocess.run` with an explicit timeout converted to `pytest.fail`, never a bare assert — evidence: `test_verify_evidence.py:963-968`, sibling `test_verify_private_refs.py:360-361`
- Missing external tool → `pytest.skip` (canonical idiom, `test_decisions_yaml_gate.py:49-63`, codified in `.claude/CLAUDE.md` § Testing & CI Policy); locked fixture / protected regression signal → `pytest.fail` — evidence: `test_fragment_store.py:6-7`, `test_check_private_refs_hook.py:84`. A shallow clone sits between these two rules; see the decision point under Proposed Solution
- Every non-obvious workflow option carries an adjacent comment naming the issue ID and the failure mode it prevents — evidence: `ci.yml:73-80` (BUG-3208), `:88-100`
- CI-visible gate tests are unmarked (no pytest marker) so they run in the unit job's `-m "not integration and not conformance"` selection — evidence: marker registry `scripts/pyproject.toml:280-284`, job selector `ci.yml:119-120`

### Tests
- `scripts/tests/test_verify_evidence.py` — `TestRepoGate` trio: `test_no_new_unverifiable_evidence` (`:951`), `test_baseline_is_tracked_and_parseable` (`:985`), `test_baseline_size_is_bounded` (`:992`, total <= 400)
- `scripts/tests/test_wiring_cli_registry.py:22` — asserts `docs/reference/CLI.md` documents `ll-verify-evidence`; no CLI surface change planned, so unaffected
- New coverage: the shallow-repo precondition itself — no test anywhere in the repo exercises `git rev-parse --is-shallow-repository`

### Documentation
- `docs/reference/CLI.md:4610-4653` — `ll-verify-evidence` reference incl. the three-layer gate model; no flag changes, so no edit required
- `.claude/CLAUDE.md` § Testing & CI Policy — describes the unit job; a fetch-depth note is optional

### Configuration
- `.ll/evidence-baseline.json` — checked-in baseline, ID-keyed span hashes; the excess count is a runtime figure, not a stored constant (it was 149 when this issue was written and is **155** as of 2026-09-10 — never hardcode it). Current headroom: `load_baseline()` returns **297 spans across 228 files**, against `test_baseline_size_is_bounded`'s cap of 400, so `--update-baseline` has only ~100 spans of room left and is not a comfortable way to absorb the 4 live findings
- `.github/workflows/ci.yml:152` — the conformance job's checkout is also bare, but it runs only `-m conformance` and `TestRepoGate` is unmarked, so it never executes this gate; adding `fetch-depth` there is harmless but unnecessary

## Program Design

### Types

- None — no new data structures; this is a workflow-config change plus a precondition branch in an existing test.

### Signatures

- `test_no_new_unverifiable_evidence(gate_cli: str) -> None` — existing; gains the shallow-repo precondition inline. No new functions.

### Call Path

`pytest` -> `TestRepoGate::test_no_new_unverifiable_evidence` -> `git rev-parse --is-shallow-repository` (new precondition: skip-or-fail-fast with one-line diagnostic) -> `ll-verify-evidence --all --json` -> `HistoryIndex` (`git log --all --raw`)

Workflow side: `.github/workflows/ci.yml` `unit-tests` job, checkout step gains `with: fetch-depth: 0` plus a comment recording why (the gate needs full history).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- `HistoryIndex.ensure_full() -> None` (`verify_evidence.py:733-745`) is the exact call collapsed by `fetch-depth: 1` — one pass `["git", "log", "--all", "--raw", "-z", "--no-abbrev", "--no-renames", "--format="]` at `:745`; class defined at `:654`
- `BASELINE_PATH = Path(".ll") / "evidence-baseline.json"` (`verify_evidence.py:83`); `load_baseline` at `:1264`; `--update-baseline` requires `--all` (`main_verify_evidence`, `:1842`)
- `DEFAULT_MAX_REVISIONS = 80` (`verify_evidence.py:645`, `--max-revisions` default): even with full history the index walks at most the 80 most recent revisions — the shallow-to-full change restores visibility up to that cap, matching how the local baseline was generated
- The CLI has no `--baseline <value>` flag and no shallow-clone awareness anywhere in its argparse surface (`verify_evidence.py:1874-1915`); the only suppression mechanism is the `<!-- ll-evidence-ok: reason -->` comment (`:1865-1867`)
- Confirmed test mechanics: `test_no_new_unverifiable_evidence` runs `[gate_cli, "--all", "--json", "-C", str(REPO_ROOT)]` (`test_verify_evidence.py:956-957`) under `GATE_TIMEOUT = 120` (`:71`, mandatory why-comment per the xdist-orphan incident)

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

1. **Prerequisite — clear the 4 live corpus findings, or the gate stays red.** `TestRepoGate::test_no_new_unverifiable_evidence` fails on `main` today on a full-history clone (verified: `1 failed, 2 passed`). The 4 spans are attributed to BUG-3439 (`test_loop_router.py`) and BUG-3443 (`test_conftest_cap.py`). Fix the quotes/attributions, or suppress a reviewed counter-example with `<!-- ll-evidence-ok: reason -->`. Do **not** reach for `--update-baseline`: the baseline is at **297 of its 400-span cap** (`test_baseline_size_is_bounded`), so re-seeding absorbs only ~100 more spans and the test's own docstring warns that a growing baseline means the checker got worse. Sequence this step with or immediately after the `fetch-depth` change — landing `fetch-depth: 0` alone produces a CI run that is still red, with a different number, and invites someone to re-seed the baseline to force it green

   **Per-span disposition (2026-09-10 pre-implementation review, measured).** Re-running `ll-verify-evidence --all --json` today still reports 4 findings, but BUG-3443's line refs drifted (`:37,44` → `:43,50` after commit `a06961726`, plus uncommitted working-tree edits on that file) — **re-run the gate at implementation time; do not trust pinned counts or line refs.** `git log --all -S` confirms none of the 4 spans ever existed verbatim in its attributed file's history. Disposition, one per span:
   - `P3-BUG-3443-…md:50` — `max(1, min(int(env), cpus - 2))`: **misattribution, not a bad quote.** The span is real and lives at `scripts/tests/conftest.py:71`; the issue points it at `test_conftest_cap.py`. Correct the attribution in BUG-3443's Root Cause and the span verifies — no suppression needed.
   - `P3-BUG-3443-…md:43` — `AssertionError: assert 2 == 3`: hypothetical output for a <5-core host; never existed verbatim. Suppress with `<!-- ll-evidence-ok: ... -->` or reword.
   - `P1-BUG-3439-…md:50` — `subprocess.Popen(["bash", "-c", action])` and `OSError: [Errno 7] Argument list too long`: paraphrases of pre-fix behavior (real code is `["bash", "-c", script]`, `test_loop_router.py:348`). BUG-3439 is closed as already-fixed (`db45ec9f6`), but the gate has **no status filter** — `verify_evidence.py` scans all of `.issues/` regardless of open/closed — so closure retires nothing. `<!-- ll-evidence-ok: ... -->` is the right mechanism; rewriting the prose to verbatim-quotable form would degrade the issue text.

2. The `unit-tests` checkout at `.github/workflows/ci.yml:67` carries `with: fetch-depth: 0` with an adjacent comment naming BUG-3442 and the failure mode it prevents (always-red evidence gate), per the workflow's ID+failure-mode comment convention (`ci.yml:73-80`)
3. `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py:951`) checks `git rev-parse --is-shallow-repository` before invoking the gate subprocess (`:956-957`) and **`pytest.fail`s** with a one-line diagnostic naming the missing `fetch-depth` and the `git fetch --unshallow` remedy (Option B, decided). It must not `pytest.skip`, and must not silently pass
4. **Learning-test prerequisite — CLOSED 2026-09-11** (commit `d3bea3f8f`). The `actions/checkout` record now exists in the Learning Test Registry (`ll-learning-tests check actions/checkout` → `proven`, 7/7 assertions, 0 failing) and covers exactly the claims this fix rests on: `fetch-depth` defaults to 1 in `actions/checkout@v4`'s `action.yml`; `git rev-parse --is-shallow-repository` prints `true` in a depth-1 clone / `false` in a full clone; `git rev-list --count --all` prints 1 at depth 1 (so `git log --all --raw` sees only the tip); a `<parent-commit>:<file>` blob is unresolvable at depth 1; `git fetch --unshallow` flips the predicate. No further learning-test work before implementing
5. After the fix, the pinned-blob flagship tests (`_read_blob`, `test_verify_evidence.py:78-88`; `BUG_3278_SHA` at `:49`) stop skipping on CI and start executing there for the first time — verify they pass on a full-history clone before merging, since a newly-live test is a new way for the job to go red
6. **Verification requires an actual CI run — local green proves nothing here.** This is a CI-only defect: the local clone is already full (`git rev-parse --is-shallow-repository` → `false`), so the `fetch-depth` change is a no-op locally and the precondition never fires. Steps: (a) `python -m pytest scripts/tests/test_verify_evidence.py -v` passes locally, which requires step 1 first; (b) inside a `git clone --depth 1` copy, the precondition fails loudly with the one-line diagnostic rather than dumping ~155 findings; (c) push and confirm in the `unit-tests` job log that the checkout fetches full history and that the gate's excess is 0
7. Budget check on CI cost, measured locally: `git log --all --raw -z --no-abbrev --no-renames --format=` emits **64.7 MB in 0.91 s** over 8407 commits, and the whole gate (`ll-verify-evidence --all --json -C .`) completes in **4.46 s** against `GATE_TIMEOUT = 120`. `.git` is 116 MB, so `fetch-depth: 0` adds a tolerable one-time clone cost. `DEFAULT_MAX_REVISIONS = 80` still caps the per-path revision walk, so full history does not make the index unbounded. Re-confirm the gate stays well under 120 s on a cold CI runner with no page cache
8. No CLI surface change: `main_verify_evidence`'s argparse (`verify_evidence.py:1874-1915`) is untouched, so `docs/reference/CLI.md:4610-4653` and `scripts/tests/test_wiring_cli_registry.py:22` need no update

## Impact

- **Priority**: P2 - The gate is structurally always-red on CI, so it provides zero regression signal there (the very thing it exists for), and no product behavior is wrong. **Correction:** the earlier claim that "local full checkouts are unaffected" is false — the gate fails locally on `main` too, from 4 genuine corpus findings. Locals are unaffected by the *shallow-checkout* cause, not by the red gate.
- **Effort**: Small for this issue - Two-line workflow change (`fetch-depth: 0`) plus a small `git rev-parse --is-shallow-repository` precondition in one test. **But it does not deliver a green gate on its own**: step 1 (clearing the 4 live findings across two sibling issue files) is additional work that must land alongside it. (Learning-test record: done — commit `d3bea3f8f`.)
- **Risk**: Low for the workflow change - No product-code behavior change; `fetch-depth: 0` adds a one-time ~116 MB clone (`.git` size measured) and the gate itself runs in 4.46 s against a 120 s timeout. Two real risks: (a) the precondition must **fail**, not skip, or a future `fetch-depth` regression goes quiet again — decided as Option B; (b) `fetch-depth: 0` newly activates the pinned-SHA `_read_blob` flagship tests on CI for the first time, which is a fresh way for the job to go red and must be checked before merging. Residual: CI's ref set (`refs/remotes/origin/*` for all branches and tags) is not byte-identical to a local clone's, so a small finding-count difference between local and CI remains possible — another reason step 6(c) requires reading an actual CI job log rather than trusting a local run.
- **Breaking Change**: No

## Verification Notes

_Added by `/ll:verify-issues` on 2026-09-11_

Verdict at time of check: **VALID** (no corrections required — every claim re-verified against the working tree on 2026-09-11; this section records what was checked, not an outstanding action item).

- **CI anchors confirmed**: unit-tests checkout is bare `- uses: actions/checkout@v4` at `ci.yml:67` (no `with:` block); conformance checkout bare at `:152`; BUG-3208 comment convention at `:73`; selector `-m "not integration and not conformance"` at `:120`. Grep across `.github/` + `scripts/`: zero matches for `fetch-depth` or `is-shallow-repository`.
- **Gate state re-measured**: `ll-verify-evidence --all --json` exits 1 with exactly the **4 findings** this issue records (BUG-3439:50 ×2 → `test_loop_router.py`; BUG-3443:43,50 → `test_conftest_cap.py`); per-file scan of this issue is clean. Baseline: 297 spans / 228 files against the 400 cap (`total <= 400` assert confirmed). `TestRepoGate::test_no_new_unverifiable_evidence` fails on `main` locally with full history.
- **Span dispositions confirmed**: `max(1, min(int(env), cpus - 2))` lives at `conftest.py:71` (misattribution, as claimed); real loop-router code is `["bash", "-c", script]` at `test_loop_router.py:348` (paraphrase, as claimed); BUG-3443 line refs read `:43,50` (post-`a06961726` drift, as claimed). `scan_all` has no status filter — BUG-3439 is `done` yet its spans still report, as claimed.
- **Prerequisites re-confirmed**: BUG-3439 closed already-fixed via `db45ec9f6`; `a06961726` is the BUG-3443 line-ref-shifting commit; learning tests `actions/checkout` and `git` both `proven`, 0 failing claims (`d3bea3f8f`).
- **Proposal trace**: both integration points covered by Implementation Steps 2–3; the new shallow-repo subprocess lands beside the `gate_cli` fixture (which only does `shutil.which`) so no fixture/mock invalidation; the `_read_blob` activation risk is already flagged in step 5. No `PROPOSAL_UNSOUND` findings.
- **Decisions check**: no active required rules. Dependencies: parent EPIC-3436 exists; no `Blocked By`/`Blocks` edges on this issue.

## Resolution

- **Action**: fix
- **Completed**: 2026-09-11
- **Status**: Completed

### Changes Made

- .github/workflows/ci.yml — unit-tests checkout now sets fetch-depth 0 (full history) with a BUG-3442 ID+failure-mode comment; conformance job untouched (never runs TestRepoGate)
- scripts/tests/test_verify_evidence.py — new _fail_if_shallow_checkout helper: git rev-parse --is-shallow-repository precondition that pytest.fails (Option B, decided) with a one-line diagnostic naming the CI remedy (fetch-depth 0) and local remedy (git fetch --unshallow); wired into test_no_new_unverifiable_evidence after the existing .git skip; new TestShallowCheckoutPrecondition covers both branches against real depth-1 (file:// clone) and full-history repos
- scripts/tests/test_ci_checkout_policy.py — new pin test: the unit-tests job's actions/checkout steps must carry fetch-depth 0 (red before the workflow change, green after)
- Step 1 prerequisite (clear the 4 live corpus findings) — P1-BUG-3439:50: one ll-evidence-ok comment suppressing both paraphrased spans (pre-fix spawn + errno text; never existed verbatim; BUG-3439 closed already-fixed and the gate has no status filter); P3-BUG-3443:43: ll-evidence-ok suppression of the hypothetical sub-5-core-host output; P3-BUG-3443:50: clamp span re-attributed via a following parenthetical to scripts/tests/conftest.py:71 where the text actually lives (misattribution, not a bad quote). Baseline untouched (297/400 spans — no re-seed)

### Verification Results

- Gate: PASS — ll-verify-evidence --all --json exits 0 with 0 findings (was 4 on full history / ~155 structural on depth 1)
- Tests: PASS — new tests red-first (3 FAILED pre-implementation), then 6/6 green incl. TestRepoGate (previously always-failing on main); full suite 23984 passed / 43 skipped / 3 failed — all 3 failures proven pre-existing on clean HEAD (test_issue_parser.py priority-regex allowlist + BUG-3295 differential, 569 = 569 with and without this change; mcp_server/tools.py line drift, untouched by this fix)
- Lint: PASS — ruff check scripts/ clean
- Types: PASS — mypy scripts/little_loops/ clean (no source change)
- Shallow-clone control: PASS — depth-1 clone of the repo fails with exactly the one-line shallow diagnostic instead of a findings dump
- Run: SKIP — no run_cmd configured
- Integration: PASS — no CLI surface change (docs/reference/CLI.md and test_wiring_cli_registry.py unaffected, per plan); follow-up outside this issue: confirm on the next real unit-tests CI run that the checkout fetches full history and the gate's excess is 0 (issue step 6c — requires a push; this workflow commits but does not push)

## Status

**Done** | Created: 2026-09-10 | Priority: P2 | Completed: 2026-09-11


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-10_

**Readiness Score**: 90/100 → ~~STOP — ADDRESS GAPS~~ → **PROCEED** (re-graded 2026-09-11: the Learning Test hard override is cleared and the decision is recorded; see resolutions below)
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Gaps to Address
- ~~**`actions/checkout` has no Learning Test Registry record.**~~ **RESOLVED 2026-09-11** (commit `d3bea3f8f`). `ll-learning-tests check actions/checkout` now returns `proven`, 7/7 assertions, 0 failing — and it covers exactly the claims this fix rests on: `fetch-depth` defaults to 1 in `actions/checkout@v4`'s `action.yml`; `git rev-parse --is-shallow-repository` prints `true` in a depth-1 clone and `false` in a full clone; `git rev-list --count --all` prints 1 at depth 1; a `<parent-commit>:<file>` blob is unresolvable at depth 1; and `git fetch --unshallow` flips the predicate. The `git` target remains `proven` (7/7). Hard override no longer applies.
- ~~**`decision_needed: true` with an unresolved Option A/B fork.**~~ **RESOLVED 2026-09-11** by `/ll:decide-issue` (session log 03:59:41): Option B recorded at `> **Selected:**` in Proposed Solution, `decision_needed` cleared to `false` via the CLI that owns it.
- **STILL OPEN — the fix does not produce a green gate, and the issue previously implied it would.** Measured: shallow clone → 155 findings beyond baseline; full history → **4 findings, still exit 1**. Re-verified 2026-09-11 after BUG-3439 was closed as already-fixed (`db45ec9f6`): `TestRepoGate::test_no_new_unverifiable_evidence` **still fails on `main`** (`1 failed, 2 passed`) — closing an issue does not retire the spans it quotes. Attribution is BUG-3439 (`test_loop_router.py`) and BUG-3443 (`test_conftest_cap.py`). The prior verification step claiming `pytest scripts/tests/test_verify_evidence.py -v` "passes on a full local clone" was false. Tracked as Implementation Steps step 1 and still required before CI can go green.
- **STILL OPEN — no CI verification step existed for a CI-only defect.** The local clone is already full, so the `fetch-depth` change is a local no-op and the new precondition never fires here. Step 6 requires reading an actual `unit-tests` job log.
- **STILL OPEN — baseline headroom is thin.** `load_baseline()` returns 297 spans across 228 files against a 400 cap, so `--update-baseline` is not a safe way to absorb the 4 live findings — and re-seeding is exactly the wrong move the always-red gate invites.


## Session Log
- `/ll:manage-issue` - 2026-09-11T05:38:50 - `41114809-db81-4f83-950b-bb3150388af6.jsonl`
- `/ll:confidence-check` - 2026-09-11T04:24:15 - `f16a24e6-6fa0-452a-b7ce-1eeea1fffebf.jsonl`
- `/ll:verify-issues` - 2026-09-11T04:19:33 - `b3354d99-33ae-4069-82e6-d632e46bda87.jsonl`
- `/ll:confidence-check` - 2026-09-11T04:10:37 - `15f92a63-fb8d-44e1-92df-1b973a2a54e8.jsonl`
- `/ll:decide-issue` - 2026-09-11T03:59:41 - `2f065e0e-57e0-408e-a9b6-f6686371abe7.jsonl`
- `/ll:confidence-check` - 2026-09-11T03:46:23 - `513f555f-2dcc-4cef-a40a-121044c26dea.jsonl`
- `/ll:refine-issue` - 2026-09-10T23:35:28 - `f7f133b9-d4c3-4ee0-8f6a-731e118bc458.jsonl`
- `/ll:format-issue` - 2026-09-10T22:05:39 - `e4ad77c2-694f-4e6b-a115-46d679e823a4.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:18 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
