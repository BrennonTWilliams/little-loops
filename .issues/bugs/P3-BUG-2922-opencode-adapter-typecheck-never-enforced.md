---
id: BUG-2922
title: "opencode adapter typecheck has never run \u2014 tsconfig declares uninstalled\
  \ bun-types, no gate"
type: BUG
status: done
priority: P3
captured_at: '2026-07-29T21:41:18Z'
completed_at: '2026-07-29T22:06:58Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
parent: FEAT-1451
labels:
- opencode
- host-compat
- tooling
confidence_score: 98
outcome_confidence: 90
score_complexity: 23
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
---

# BUG-2922: opencode adapter typecheck has never run — tsconfig declares uninstalled bun-types, no gate

## Summary

`hooks/adapters/opencode/tsconfig.json` sets `"types": ["bun-types"]`, but
`package.json` declares no `devDependencies` and `bun.lock` contains zero
references to that package. So `bun x tsc --noEmit -p tsconfig.json` fails
immediately with `TS2688: Cannot find type definition file for 'bun-types'`
and typechecks nothing. The adapter has been shipping unverified against its
own `strict: true` setting since FEAT-1451 created it.

Discovered while hardening the adapter's interpreter resolution under
BUG-2921 — the typecheck was run to validate that change and turned out to be
broken independently of it (confirmed by stashing the change: pristine tree
fails identically).

## Current Behavior

```
$ cd hooks/adapters/opencode && bun x tsc --noEmit -p tsconfig.json
error TS2688: Cannot find type definition file for 'bun-types'.
  The file is in the program because:
    Entry point of type library 'bun-types' specified in compilerOptions
```

`node_modules/` contains only `@opencode-ai` and `zod`. No test invokes `tsc`
at all, so nothing in `python -m pytest scripts/tests/` notices. The failure is
invisible unless someone runs the typecheck by hand.

## Steps to Reproduce

```bash
cd hooks/adapters/opencode
bun x tsc --noEmit -p tsconfig.json
# => error TS2688: Cannot find type definition file for 'bun-types'.
```

Reproduces on a pristine checkout with no local modifications (verified via
`git stash`). Requires Bun on `PATH` (reproduced against Bun 1.3.9).

## Expected Behavior

1. `tsc --noEmit` resolves Bun's globals (`Bun.spawn`, `Bun.which`,
   `process.env`) and reports real type errors only.
2. The typecheck runs as part of the project's single enforced gate
   (`python -m pytest scripts/tests/`), skipping gracefully when Bun is absent
   so contributors without the toolchain aren't hard-blocked.

## Root Cause

`hooks/adapters/opencode/tsconfig.json` — `compilerOptions.types` names
`bun-types` while `hooks/adapters/opencode/package.json` never lists it under
`devDependencies`. A declared-but-uninstalled type library is a hard `tsc`
error, not a warning, so the very first invocation of the typecheck would have
failed. It appears never to have been invoked in CI or locally, because no gate
calls it.

Compounding factor: `bun-types` is the legacy package name; the current one is
`@types/bun`, consumed as `"types": ["bun"]`.

## Proposed Solution

Three parts, mirroring an existing precedent in this repo:

1. **Fix the declaration.** Add `"devDependencies": {"@types/bun": "<pin>"}` to
   `hooks/adapters/opencode/package.json`, change `tsconfig.json` to
   `"types": ["bun"]`, and refresh `bun.lock`. This is a dev-only type package
   in an isolated `private: true` workspace — it does not touch
   `scripts/pyproject.toml`, so the minimize-dependencies rule for the Python
   package does not apply.
2. **Gate it in pytest.** Follow
   `scripts/tests/test_policy_builder_node_gate.py`, which exists for exactly
   this shape: subprocess-wrap an external-toolchain check so it runs under
   `python -m pytest scripts/tests/`, and skip (never fail) when the tool is
   missing. Its docstring states the governing principle — *"an unenforced gate
   does not count as met."*
3. **Extend the existing module.** Add the gate to
   `scripts/tests/test_opencode_adapter.py` rather than a new file: it already
   has the Bun-detection skip (`pytestmark = pytest.mark.skipif(_BUN is None,
   ...)`) that would otherwise be duplicated.

Without part 2 this silently re-rots the moment anyone's `node_modules` goes
stale — which is plausibly how it broke in the first place.

## Implementation Steps

1. Add `@types/bun` to the adapter's `package.json` devDependencies; run
   `bun install` to update `bun.lock`. **Needs network access** — if the
   registry is unreachable, stop rather than commit a half-updated lockfile.
2. Flip `tsconfig.json` `"types": ["bun-types"]` → `["bun"]`.
3. Run the typecheck and fix whatever it surfaces. Code never checked under
   `strict: true` may well have latent errors; treat any that imply a real
   behavior change as a separate finding rather than silently editing.
4. Add the `tsc --noEmit` gate to `test_opencode_adapter.py`, asserting exit 0
   and skipping when Bun is unavailable.
5. Confirm `python -m pytest scripts/tests/test_opencode_adapter.py` passes and
   is not skipped in an environment with Bun present.

## Integration Map

### Files to Modify
- `hooks/adapters/opencode/package.json` — add `devDependencies`
- `hooks/adapters/opencode/tsconfig.json` — `bun-types` → `bun`
- `hooks/adapters/opencode/bun.lock` — regenerated by `bun install`
- `scripts/tests/test_opencode_adapter.py` — new `tsc --noEmit` gate

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/adapters/opencode/README.md` § Smoke Test (lines 126-131) — currently
  describes only the Bun-backed integration smoke test
  (`test_opencode_adapter.py`); optionally extend to mention the new
  `tsc --noEmit` gate for completeness once added. Not required for the fix to
  function — no doc currently makes a stale claim about typecheck status.

### Related
- **FEAT-1451** (parent) — created the adapter with this latent config gap
- **BUG-2921** — interpreter hardening; surfaced this while validating, out of scope there
- `scripts/tests/test_policy_builder_node_gate.py` — the external-toolchain gate pattern to copy
- `.claude/CLAUDE.md` § Testing & CI Policy — no hosted CI; wrap external gates as pytest tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scripts/tests/test_opencode_adapter.py:25-29`** — the existing Bun-detection
  guard is a *module-level* `pytestmark`, not per-test:
  ```python
  _BUN = shutil.which("bun")
  pytestmark = pytest.mark.skipif(_BUN is None, reason="Bun runtime not available")
  BUN: str = _BUN or "bun"
  ```
  A new `tsc --noEmit` gate appended to this file inherits this skip
  automatically — no separate skipif needed — and can reuse the already-bound
  `BUN` constant and `REPO_ROOT`/`ADAPTER_PATH` (`line 31-32`) path anchors.
  None of the file's current four tests (`test_adapter_files_exist`,
  `test_session_compacted_writes_state_file`,
  `test_session_created_runs_session_start`,
  `test_adapter_sets_ll_hook_host_opencode`) shell out to `tsc` today.
- **`scripts/tests/test_policy_builder_node_gate.py:31-71`** — exact pattern to
  mirror for the new gate: `shutil.which()` probe → `pytest.skip()` (not
  fail) if absent → `subprocess.run([...], capture_output=True, text=True,
  timeout=...)` → `assert proc.returncode == 0` with stdout/stderr embedded in
  the failure message for diagnosability. No version-gate helper (like this
  file's `_node_major`) is needed for the `tsc` gate since Bun's own
  `pytestmark` already handles presence.
- **`hooks/adapters/opencode/index.ts:35,42`** — `Bun.which` and `Bun.spawn`
  are referenced with no import; they resolve only through the ambient `Bun`
  global that `bun-types`/`@types/bun` injects. This is why the typecheck is
  not a no-op once fixed — real ambient-global resolution is exercised, not
  just an empty compile.
- **Current `hooks/adapters/opencode/package.json`** has no `devDependencies`
  block at all (only a `dependencies` block with
  `"@opencode-ai/plugin": "1.2.27"` and an `engines.bun` constraint) — the
  new block is additive, not a rewrite of an existing section.
- **Current `hooks/adapters/opencode/bun.lock`** — the `packages` map
  resolves exactly three packages (`@opencode-ai/plugin`, `@opencode-ai/sdk`,
  `zod`); no `bun-types` or `@types/bun` entry exists anywhere in it,
  confirming the type package has never been installed, consistent with the
  issue's Root Cause.
- No other `package.json`/`tsconfig.json` pair exists anywhere else in this
  repo (outside `hooks/adapters/opencode/` and its own `node_modules/`), so
  there is no in-repo precedent for a `devDependencies` pin style to match
  beyond the `dependencies` block's exact-pin convention
  (`"@opencode-ai/plugin": "1.2.27"`, no caret/tilde range) — Implementation
  Step 1 should pin `@types/bun` the same way (exact version, not a range).

## Impact

- **Priority**: P3 — no runtime effect; the adapter demonstrably works (4 Bun-backed integration tests pass). This is dev-tooling correctness and latent-defect exposure, not a user-facing break.
- **Effort**: Small — one dependency, two config lines, one gate test; unknown tail if step 3 surfaces real `strict` errors.
- **Risk**: Low — changes are confined to an isolated private workspace and the test suite.
- **Breaking Change**: No

## Resolution

Implemented all three parts of the Proposed Solution:

1. Added `@types/bun` (exact pin `1.3.14`, matching the `dependencies` block's
   no-range convention) to `hooks/adapters/opencode/package.json`
   `devDependencies`; ran `bun install` to regenerate `bun.lock`. Flipped
   `tsconfig.json`'s `"types": ["bun-types"]` → `["bun"]`.
2. Running `bun x tsc --noEmit -p tsconfig.json` after the fix surfaced 4 real
   `TS2339` errors: `ctx.cwd` does not exist on `PluginInput` (the actual field
   is `ctx.directory`, confirmed via `@opencode-ai/plugin`'s `index.d.ts`).
   `index.ts` was shipping against an untyped `ctx: any`-equivalent the whole
   time; renamed all four `ctx.cwd` call sites to `ctx.directory`. This is a
   real bug fix enabled by the typecheck finally running, not a cosmetic
   change — confirms the issue's own prediction (`.ll/learning-tests/typesbun.md`)
   that the typecheck would not be a no-op.
3. Added `TestOpenCodeAdapterTypecheck::test_tsc_noemit_passes` to
   `scripts/tests/test_opencode_adapter.py`, shelling out to
   `bun x tsc --noEmit -p tsconfig.json` and asserting exit 0. It inherits the
   file's existing module-level Bun-availability skip. Also updated the
   existing test driver's synthetic `ctx` to use `directory` instead of `cwd`,
   matching the real `PluginInput` contract.
4. Updated `README.md` § Smoke Test to mention the new typecheck gate.

Verification: `python -m pytest scripts/tests/` — 17115 passed, 42 skipped (Bun
present in this environment, so the new gate ran and passed, not skipped).
`ruff check scripts/` — all checks passed.

## Session Log
- `/ll:manage-issue` - 2026-07-29T22:06:22Z - `25766da4-2bfb-4a98-9695-b173379f82c5.jsonl`
- `/ll:wire-issue` - 2026-07-29T21:52:55 - `6641a576-7afa-4ddd-b20f-8a1ae69f494c.jsonl`
- `/ll:refine-issue` - 2026-07-29T21:48:20 - `4366b74f-a38f-4e86-beed-e7be4ae5f2f0.jsonl`
- `/ll:capture-issue` - 2026-07-29T21:41:18Z - `26fb7019-7a23-4352-9810-40f816595875.jsonl`

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
