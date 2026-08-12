---
id: ENH-3152
type: ENH
title: Promote test_tamper_guard._test_functions() to public extract_test_functions()
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-12'
captured_at: '2026-08-12T03:58:18Z'
labels:
- refactor
- verification
testable: true
---

# ENH-3152: Promote test_tamper_guard._test_functions() to public extract_test_functions()

## Summary

Promote `test_tamper_guard._test_functions()` to a public
`extract_test_functions()` so consumers outside the module can reuse the
top-level-`test*`-function AST extraction without importing an
underscore-prefixed name. Pure rename plus call-site update; no behavior change.

Split out of ENH-3142, which needs this helper cross-module and would otherwise
have to reach into a private name or carry an unrelated second-module edit.

## Current Behavior

`scripts/little_loops/test_tamper_guard.py:369-380` defines:

```python
def _test_functions(source: str) -> dict[str, ast.AST] | None:
    """Top-level ``test*`` function nodes by name; None when unparseable."""
```

It is used only inside the module, at four call sites — `:424`, `:432`, `:433`,
`:455`, all within `filter_weakening_findings()`. The leading underscore marks
it module-private, so the only way for another module to reuse it is to import
a private name.

## Expected Behavior

The same function is exported as `extract_test_functions()` with identical
signature, docstring semantics, and return contract (`dict[str, ast.AST]`, or
`None` when the source does not parse). All four internal call sites use the new
name. Nothing else changes.

## Motivation

ENH-3142 (`prepatch_check.py` core) needs exactly this extraction to compute the
added-vs-modified test split — `set(after_names) - set(before_names)` — against
base-ref text from `read_paths_at_ref()`. Without the promotion, ENH-3142 must
either import `_test_functions` across a module boundary or grow a second AST
implementation. Both are worse than a five-minute rename, and the rename is
independent of everything else in ENH-3142, so it does not belong in that
issue's diff.

## Proposed Solution

Rename `_test_functions` to `extract_test_functions` and update the four
in-module call sites.

**Name choice — not `test_functions()`.** A module-level callable named `test_*`
is collectable by pytest if the suite is ever pointed at `scripts/` rather than
`scripts/tests/`, and this module's filename (`test_tamper_guard.py`) already
matches default test-file patterns. `extract_test_functions` avoids that
entirely.

No back-compat alias is needed: the name is private, has zero external callers
(verified by repo-wide grep), and is not referenced by any test.

## Integration Map

### Files to Modify
- `scripts/little_loops/test_tamper_guard.py` — the `def` at `:369` and four
  call sites at `:424`, `:432`, `:433`, `:455`.

### Dependent Files (Callers/Importers)
- None outside `test_tamper_guard.py`. A repo-wide `grep -rn "_test_functions"
  scripts/` returns only the definition, the four in-module call sites, and one
  unrelated substring match (`test_test_tamper_guard.py:636`,
  `test_counts_asserts_test_functions_and_skip_markers` — a test *name*, not a
  reference to this function; leave it alone).
- ENH-3142 will be the first external consumer, once landed.

### Similar Patterns
- `read_paths_at_ref()` (`test_tamper_guard.py:112`) is the precedent for a
  public helper in this module consumed by outside callers — same module, same
  role, already public.

### Tests
- `scripts/tests/test_test_tamper_guard.py` — no test references
  `_test_functions` directly, so no rename is forced. Add a small direct test
  class for `extract_test_functions()` covering: top-level `test*` functions
  returned by name, non-`test*` functions excluded, unparseable source returning
  `None`, and — as documented contract, not a bug to fix here — class-method
  tests **not** returned (it walks `tree.body`, not `ast.walk`). Making that
  limitation explicit in a test matters because ENH-3142 depends on it to decide
  when to take its file-fallback path.
- The existing `filter_weakening_findings()` tests are the regression guard for
  the call-site updates; they must stay green unchanged.

### Documentation
- `docs/reference/API.md:97` — the `little_loops.test_tamper_guard` Module
  Overview row enumerates the module's public surface inline
  (`snapshot_test_paths()`, `compare_snapshots()`, `measure_test_strength()`,
  `is_weakening()`, `filter_weakening_findings()`, …); add
  `extract_test_functions()` to that list.

### Configuration
- N/A

## Program Design

### Types

None — no new types. The return type is unchanged: `dict[str, ast.AST] | None`,
mapping top-level `test*` function names to their `ast.FunctionDef` /
`ast.AsyncFunctionDef` nodes, with `None` signaling a `SyntaxError` during
`ast.parse()`.

### Signatures

- `extract_test_functions(source: str) -> dict[str, ast.AST] | None` (new
  public name; body verbatim from `_test_functions`,
  `test_tamper_guard.py:369-380`)
- `_test_functions(source: str) -> dict[str, ast.AST] | None` (removed — no
  alias retained)

### Call Path

`filter_weakening_findings` -> `extract_test_functions` (four call sites:
`:424`, `:432`, `:433`, `:455`)

`prepatch_check.collect_candidates` -> `extract_test_functions` (ENH-3142, after
this lands)

No new call paths, no new imports in `test_tamper_guard.py`, and no change to
which nodes are returned — the rename is behavior-preserving by construction.

## Implementation Steps

1. Rename the definition and its four in-module call sites.
2. Add the direct test class for `extract_test_functions()`, including the
   class-method-not-returned contract test.
3. Document it in `docs/reference/API.md`.
4. Verify `python -m pytest scripts/tests/test_test_tamper_guard.py` and
   `ruff check scripts/` are clean.

## Impact

- **Priority**: P3 — no user-visible effect; it unblocks a clean import in
  ENH-3142 rather than fixing anything broken.
- **Effort**: Small — one rename, four call sites, one test class, one doc line.
- **Risk**: Low — private name, zero external callers, no behavior change.
- **Breaking Change**: No — the promoted name is currently private.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-11 | Priority: P3

## Success Metrics

- `grep -rn "_test_functions" scripts/little_loops/` returns nothing.
- ENH-3142 imports `extract_test_functions` from `test_tamper_guard` with no
  underscore-prefixed import.

## Scope Boundaries

- **Not this issue**: fixing `_test_functions`'s top-level-only limitation
  (class-method and nested test functions are invisible to it). ENH-3142 handles
  that case via its documented file-fallback path; changing the extraction's
  behavior here would silently change `filter_weakening_findings()`'s
  relocation-detection semantics, which is a separate decision with its own
  ENH-2964 context.
- **Not this issue**: any change to `measure_test_strength()`,
  `filter_weakening_findings()`, or tamper-guard policy.
- **Not this issue**: adding a back-compat `_test_functions` alias.

## Backwards Compatibility

None required — the name is private and has no callers outside its own module.

## API/Interface

```python
def extract_test_functions(source: str) -> dict[str, ast.AST] | None:
    """Top-level ``test*`` function nodes by name; None when unparseable."""
```

## Acceptance Criteria

- [ ] `test_tamper_guard.extract_test_functions()` exists with the signature
      above and identical behavior to the former `_test_functions()`.
- [ ] `grep -rn "_test_functions" scripts/little_loops/` returns no matches.
- [ ] The public name is not `test_functions` (pytest-collectable).
- [ ] A direct test class covers: top-level `test*` returned, non-`test*`
      excluded, unparseable source returning `None`, and class-method tests not
      returned.
- [ ] Existing `filter_weakening_findings()` tests pass unchanged.
- [ ] `docs/reference/API.md` lists `extract_test_functions()` under
      `little_loops.test_tamper_guard`.

## Related Issues

- `ENH-3142` (consumer) — `prepatch_check.py` core; first external caller.
  Split out of that issue's scope.
- `ENH-2854` (origin) — landed `test_tamper_guard.py` and `_test_functions()`.
- `ENH-2964` (context) — the cross-file relocation logic that is
  `_test_functions()`'s current sole consumer.
