---
id: BUG-3442
type: BUG
title: CI shallow checkout makes the evidence gate structurally unable to pass
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
decision_needed: true
learning_tests_required:
  - git
  - actions/checkout
---

# BUG-3442: CI shallow checkout makes the evidence gate structurally unable to pass

## Summary

ci.yml unit-tests uses bare actions/checkout@v4 (fetch-depth 1), collapsing the `git log --all --raw` HistoryIndex 65x so ll-verify-evidence reports exactly 149 unverifiable spans and TestRepoGate::test_no_new_unverifiable_evidence always fails, providing zero signal. Add fetch-depth: 0 with a comment recording why, and add a `git rev-parse --is-shallow-repository` precondition to the gate test that fails loudly with a one-line diagnostic instead of a 149-item mystery (A1).

## Steps to Reproduce

1. Push any commit to `main` (or re-run the `unit-tests` workflow).
2. The `unit-tests` job checks out with bare `actions/checkout@v4` — default `fetch-depth: 1`, a shallow clone with only the tip commit.
3. The test suite runs `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py`), which invokes `ll-verify-evidence --all --json`; `HistoryIndex` builds its `path -> blob OIDs` map from one `git log --all --raw` pass.
4. Observe: every span quoted from history older than the tip commit is unverifiable — exactly 149 findings beyond baseline — so the gate test fails on every CI run regardless of corpus state.

## Current Behavior

CI's `unit-tests` job (`.github/workflows/ci.yml`) uses bare `actions/checkout@v4`, which defaults to `fetch-depth: 1`. The evidence gate test then runs `ll-verify-evidence --all` against that shallow clone: `HistoryIndex`'s single `git log --all --raw` pass sees only the tip commit, so spans quoted from any earlier artifact state resolve to nothing. The gate reports exactly 149 unverifiable spans and `TestRepoGate::test_no_new_unverifiable_evidence` always fails — the gate is always-red and provides zero regression signal.

## Expected Behavior

- The `unit-tests` checkout uses `fetch-depth: 0` (full history) so `HistoryIndex` sees all commits and the gate passes/fails on actual corpus regressions.
- If the repository is shallow anyway (local shallow clone or a future workflow regression), the gate test detects it up front via `git rev-parse --is-shallow-repository` and fails fast with a one-line diagnostic pointing at the missing fetch-depth, instead of a 149-item findings dump.

## Root Cause

- **File**: `.github/workflows/ci.yml` (unit-tests job checkout, line 67) interacting with `scripts/little_loops/cli/verify_evidence.py`
- **Anchor**: `HistoryIndex.ensure_full()` (`verify_evidence.py:733-745`), exercised by `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py:951`)
- **Cause**: The `unit-tests` job's bare `actions/checkout@v4` defaults to `fetch-depth: 1` (shallow). `ensure_full()` builds the `path -> blob OIDs` map from a single `git log --all --raw -z` pass (`verify_evidence.py:745`), which sees only the tip commit — every span quoted from an earlier artifact state resolves to nothing. The gate test compares findings against the checked-in ID-keyed baseline (`.ll/evidence-baseline.json`, `BASELINE_PATH` at `verify_evidence.py:83`) and fails on any excess; on a shallow clone the excess (~149) is structural, so the gate is always-red regardless of corpus state. Nothing in the test distinguishes "corpus regression" from "checkout lacks history". No code or CI script in the repo runs `git rev-parse --is-shallow-repository` today, and no workflow sets `fetch-depth`.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

Two dispositions exist for the shallow-repo precondition in `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py:951`) — the codebase's conventions are contested on exactly this case, and the issue text itself hedges ("skip-or-fail-fast", "must skip (or fail …) rather than silently pass").

**Option A**: Skip when `git rev-parse --is-shallow-repository` reports shallow — same-file precedent: missing git state already skips (`test_verify_evidence.py:88`, `:952-953`), and `.claude/CLAUDE.md` § Testing & CI Policy codifies skip-when-missing for gate preconditions.

**Option B**: Fail fast with a one-line diagnostic naming the missing `fetch-depth` — the issue's own Expected Behavior ("fails fast with a one-line diagnostic pointing at the missing fetch-depth, instead of a 149-item findings dump"); fail-not-skip precedent for protected regression signals (`test_fragment_store.py:6-7`, `test_check_private_refs_hook.py:84`).

**Recommended**: Option B — per the issue's Expected Behavior: a skip silently disarms the gate on every shallow checkout (exactly the CI state this bug describes), and the fail-not-skip rule covers "absence of a thing the gate exists to protect". Residual trade-off to weigh in the decision: Option B hard-fails a contributor's full local suite if they made a local `--depth 1` clone.

Workflow side is uncontested: `.github/workflows/ci.yml:67` gains `with: fetch-depth: 0` with an adjacent BUG-3442 + failure-mode comment (ID+failure-mode convention, `ci.yml:73-80`).

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
- `.ll/evidence-baseline.json` — checked-in baseline, ID-keyed span hashes; "149" is a runtime count beyond this baseline, not a stored constant
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

- The `unit-tests` checkout at `.github/workflows/ci.yml:67` carries `with: fetch-depth: 0` with an adjacent comment naming BUG-3442 and the failure mode it prevents (always-red evidence gate), per the workflow's ID+failure-mode comment convention (`ci.yml:73-80`)
- `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py:951`) checks `git rev-parse --is-shallow-repository` before invoking the gate subprocess (`:956-957`), with whichever disposition the Proposed Solution decision selects; a failure diagnostic is one line and names the missing `fetch-depth`
- After the fix, the pinned-blob flagship tests (`_read_blob`, `test_verify_evidence.py:78-88`; `BUG_3278_SHA` at `:49`) stop skipping on CI and start executing there for the first time — verify they pass on a full-history clone before merging
- `python -m pytest scripts/tests/test_verify_evidence.py -v` passes on a full local clone; the precondition fires loudly (or skips, per the decision) inside a `git clone --depth 1` copy of the repo
- No CLI surface change: `main_verify_evidence`'s argparse (`verify_evidence.py:1874-1915`) is untouched, so `docs/reference/CLI.md:4610-4653` and `scripts/tests/test_wiring_cli_registry.py:22` need no update

## Impact

- **Priority**: P2 - The gate is structurally always-red on CI, so it provides zero regression signal there (the very thing it exists for), but local full checkouts are unaffected and no product behavior is wrong.
- **Effort**: Small - Two-line workflow change (`fetch-depth: 0`) plus a small `git rev-parse --is-shallow-repository` precondition in one test.
- **Risk**: Low - No product-code behavior change; full checkout slightly increases CI clone time. The precondition must skip (or fail with the one-line diagnostic) rather than silently pass, so a future fetch-depth regression stays loud.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-10T23:35:28 - `f7f133b9-d4c3-4ee0-8f6a-731e118bc458.jsonl`
- `/ll:format-issue` - 2026-09-10T22:05:39 - `e4ad77c2-694f-4e6b-a115-46d679e823a4.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:18 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
