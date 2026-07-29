---
id: BUG-2922
title: opencode adapter typecheck has never run — tsconfig declares uninstalled bun-types, no gate
type: BUG
status: open
priority: P3
captured_at: "2026-07-29T21:41:18Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
parent: FEAT-1451
labels:
- opencode
- host-compat
- tooling
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

### Related
- **FEAT-1451** (parent) — created the adapter with this latent config gap
- **BUG-2921** — interpreter hardening; surfaced this while validating, out of scope there
- `scripts/tests/test_policy_builder_node_gate.py` — the external-toolchain gate pattern to copy
- `.claude/CLAUDE.md` § Testing & CI Policy — no hosted CI; wrap external gates as pytest tests

## Impact

- **Priority**: P3 — no runtime effect; the adapter demonstrably works (4 Bun-backed integration tests pass). This is dev-tooling correctness and latent-defect exposure, not a user-facing break.
- **Effort**: Small — one dependency, two config lines, one gate test; unknown tail if step 3 surfaces real `strict` errors.
- **Risk**: Low — changes are confined to an isolated private workspace and the test suite.
- **Breaking Change**: No

## Session Log
- `/ll:capture-issue` - 2026-07-29T21:41:18Z - `26fb7019-7a23-4352-9810-40f816595875.jsonl`

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
