---
id: ENH-2198
type: ENH
priority: P3
status: open
captured_at: 2026-06-16T18:21:36Z
discovered_date: 2026-06-16
discovered_by: scope-epic
parent: EPIC-2196
labels: [hermes, cli, loop, discovery]
---

# Add `ll-loop list --visibility` inheritance-aware filter

## Summary

Add a `--visibility public|internal|example` filter to `ll-loop list` so callers
can restrict the catalog to routable (`public`) loops. Today `ll-loop list`
exposes `--json`, `--label`, and `--builtin` but has no visibility filter, so the
Hermes loop-router cannot select only dispatchable loops. The filter must be
inheritance-aware: resolve `from:` chains via `is_runnable_loop()` so non-runnable
stubs are excluded from `public`. Source: `PRD-Hermes-Integration-v4.md` (EG-2).

## Current Behavior

`ll-loop list` exposes `--json`, `--label`, and `--builtin` flags but has no
visibility filter. All loops — including non-runnable `from:` stubs and
`internal`/`example`-tier loops — appear in catalog output. Automated callers
such as the Hermes loop-router must filter client-side, coupling them to the
visibility model internals and surfacing stubs that would fail dispatch.

## Expected Behavior

`ll-loop list` accepts a `--visibility public|internal|example|all` flag. When
set to `public`, only runnable loops whose visibility tier is `public` are
returned; `from:` inheritance chains are resolved before the routability check
so stubs are never surfaced as dispatchable. The flag composes with `--label`
and `--json`.

## Motivation

The Hermes loop-router (EPIC-2196) must enumerate routable loops to dispatch
user requests. Without a visibility filter, it receives the full catalog and
must filter client-side — coupling the router to the visibility model internals
and surfacing stubs that would fail dispatch. A server-side `--visibility` flag
is the clean interface contract that keeps routing logic in the CLI where the
visibility model lives.

## Acceptance Criteria

- `ll-loop list --json --visibility public` returns only runnable, `public`-tier loops.
- `--visibility internal` and `--visibility example` filter to their respective tiers.
- `--visibility all` (or omitting the flag, per chosen default) reveals `from:` stubs.
- `from:` inheritance chains are resolved before the routability decision
  (`is_runnable_loop()`), so a stub that resolves to a runnable public loop is
  classified correctly.
- `--visibility` composes with `--label` and `--json`.

## Proposed Solution

Add a `--visibility {public,internal,example,all}` argument to the `ll-loop list`
subparser.

**Wiring point**: `scripts/little_loops/cli/loop/__init__.py` (`list` subparser,
`add_argument` block ~line 157) and the list handler in
`scripts/little_loops/cli/loop/`.

**Implementation approach**:
1. Add `--visibility` argument with choices `['public', 'internal', 'example', 'all']`
   and default `'all'` to preserve current behavior.
2. In the list handler, resolve each loop's effective visibility by walking `from:`
   chains via `is_runnable_loop()`.
3. Filter the catalog to only loops matching the requested visibility tier.
4. Confirm the visibility tier source of truth (loop YAML field name — likely
   `visibility:`) and the fallback default when a loop omits the field.

## Scope Boundaries

- **In scope**: `ll-loop list --visibility` filter with `public|internal|example|all`
  values; `from:` chain resolution for routability; composition with `--label` and
  `--json`
- **Out of scope**: Changing visibility defaults on existing loops; migrating loops
  between tiers; the Hermes dispatch mechanism itself (EPIC-2196); adding
  `--visibility` to `ll-loop run` or other subcommands

## API/Interface

```
ll-loop list [--json] [--label LABEL] [--builtin] [--visibility {public,internal,example,all}]
```

New argument:
- `--visibility {public,internal,example,all}` — Filter loops by visibility tier.
  Default: `all` (no filter, preserves current behavior). Composes with `--label`
  and `--json`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — `list` subparser, argument definition
- `scripts/little_loops/cli/loop/` — list handler, visibility filter logic

### Dependent Files (Callers/Importers)
- TBD — grep for callers: `grep -r 'loop list\|ll-loop list' scripts/`
- Hermes loop-router code (pending EPIC-2196 implementation)

### Similar Patterns
- TBD — check how `--label` and `--builtin` flags filter loops in the list handler

### Tests
- `scripts/tests/` — add tests for `--visibility` flag (exclude stubs from `public`,
  composition with `--label`, missing-field default behavior)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add `--visibility` flag to `ll-loop list` reference

### Configuration
- N/A

## Implementation Steps

1. Confirm visibility YAML field name and default value in existing loop files
2. Add `--visibility` argument to `list` subparser in `scripts/little_loops/cli/loop/__init__.py`
3. Implement filter in list handler: resolve `from:` chains via `is_runnable_loop()`, then apply visibility predicate
4. Add tests covering `--visibility public` (excludes stubs), `--visibility` + `--label` composition, and missing-visibility-field default behavior
5. Verify `ll-loop list --json --visibility public` satisfies Hermes EG-2 contract

## Impact

- **Priority**: P3 — Enabler for EPIC-2196 (Hermes integration); non-blocking for other work
- **Effort**: Small — Adding one CLI argument and a filter step in an existing list handler; reuses `is_runnable_loop()`
- **Risk**: Low — Additive change; `all` default preserves current behavior; no existing API changes
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-16 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-16T18:28:38 - `595ca16b-86af-4c4e-8a92-aed41afd4055.jsonl`
