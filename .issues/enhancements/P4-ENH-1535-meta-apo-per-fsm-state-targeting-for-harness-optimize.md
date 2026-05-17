---
id: ENH-1535
type: ENH
priority: P4
captured_at: "2026-05-17T01:43:21Z"
discovered_date: "2026-05-17"
discovered_by: capture-issue
status: open
relates_to:
  - FEAT-1120
  - FEAT-766
  - FEAT-849
---

# ENH-1535: Meta-APO — Per-FSM-State Targeting for harness-optimize

## Summary

Extend `harness-optimize.yaml` (FEAT-1120) to support a per-FSM-state targeting mode, so the `action:` prompt of an individual state inside a loop YAML can be optimized in isolation against a state-scoped example set. Today `harness-optimize` treats targets as whole files via globs; this is fine for `SKILL.md` / `CLAUDE.md` but the wrong shape for loop YAMLs, where each state has its own contract (input fields, output fields, downstream consumers) and each state should be APO'd against state-specific labeled examples — not against a single rollup score for the whole loop.

## Current Behavior

`harness-optimize` mutates target files end-to-end and gates acceptance on a numeric benchmark score for the whole artifact. Pointing it at `scripts/little_loops/loops/apo-textgrad.yaml` would let the mutator rewrite any part of the YAML against one global score — there is no way to:

- Isolate a single state's `action:` block as the mutable surface
- Supply per-state labeled examples (e.g., `(test_results.output) → expected gradient text` for `compute_gradient`)
- Score state-local quality (gradient usefulness, refinement faithfulness) instead of full-loop convergence

## Expected Behavior

`harness-optimize` accepts a structured target spec for loop YAMLs:

```yaml
targets:
  - file: scripts/little_loops/loops/apo-textgrad.yaml
    states:
      - name: compute_gradient
        examples_file: .ll/meta-apo/compute_gradient.json
        eval: lib/judge-gradient-quality.yaml
      - name: apply_gradient
        examples_file: .ll/meta-apo/apply_gradient.json
        eval: lib/judge-refinement-faithfulness.yaml
```

For each listed state:

1. Extract the `action:` block via the YAML parser (preserve surrounding state config).
2. Treat that block as the `prompt_file` analogue, with the supplied `examples_file` as labeled I/O.
3. Run the eval fragment to score outputs (state-local, not whole-loop).
4. Accept the mutation only if state-local score rises; otherwise revert.
5. Persist the mutated `action:` block back into the YAML state in place, preserving formatting.

Trajectory is kept per-state under `.ll/runs/harness-optimize/<run-id>/states/<state-name>/trajectory.jsonl`.

## Motivation

**Why**: The current `apo-textgrad` loop has three prompt blocks (`test_on_examples`, `compute_gradient`, `apply_gradient`) that each have a tight, well-defined contract. Treating them as one opaque file (the only option today) discards the structural information that makes per-state APO tractable — and conflates noise from one state's failures into another's score. The cleanest place to gain this is by extending `harness-optimize` rather than building a new loop, because mutation/score/revert/commit plumbing is already in place.

**How to apply**: Reach for this when a maintainer wants to tune the loop's own state prompts (meta-APO). Skip if the artifact is a single-prompt file (skill, agent, CLAUDE.md) — `harness-optimize`'s existing whole-file mode is already correct for those.

## Proposed Solution

Extend the existing `harness-optimize` loop rather than forking a new loop, since mutation/score/revert/commit plumbing is already in place. Two pieces to add:

1. **Schema extension** — add optional `targets[].states[]` to the loop config (see API/Interface). When `states:` is omitted, today's whole-file behavior is preserved.
2. **YAML state-block round-trip helper** — small helper in `scripts/little_loops/loops/` that uses `ruamel.yaml` (round-trip mode) to extract a named state's `action:` block, hand it to the mutator as the prompt-under-test, and write the result back in place while preserving sibling keys and formatting. Avoid regex on `action: |` blocks (brittle under indentation changes).

Existing utilities to reuse:

- `harness-optimize.yaml` runtime — mutation/accept/revert state machine
- `ruamel.yaml` round-trip parser (already used elsewhere in the loops package)
- The trajectory writer (extend to key by state name)
- Eval fragment loader used by existing `harness-optimize` runs

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/harness-optimize.yaml` — schema and state-mode wiring
- `scripts/little_loops/loops/` — new state-block extractor/replacer helper

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/apo-textgrad.yaml` — canonical first consumer; once state-mode lands this loop becomes the meta-APO target

### Similar Patterns
- Whole-file mutation path inside `harness-optimize` — state-mode should mirror its accept/revert structure, not invent a parallel one

### Tests
- `scripts/tests/test_harness_optimize.py` — add 2-state fixture loop covering: extraction, isolated mutation, state-local score gating, in-place rewrite preserves siblings; confirm existing whole-file tests still pass

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — document state-mode as opt-in under `harness-optimize`

### Configuration
- N/A — no new global config; targeting lives in the loop YAML itself

## Implementation Steps

1. Add `targets[].states[]` schema to `harness-optimize.yaml` and validation in the loop config loader.
2. Add a YAML state-block extractor/replacer in `scripts/little_loops/loops/` (likely a small helper next to `harness-optimize` runtime) that round-trips through `ruamel.yaml` (preserves formatting) — pure regex on `action: |` blocks is brittle and should be avoided.
3. Replace the single-trajectory writer with a per-state writer keyed by state name.
4. Extend the score reducer so accept/revert is computed per state, not globally.
5. Add fixture loop + two-state example to `scripts/tests/test_harness_optimize.py` covering: state extraction, isolated mutation, state-local score gating, in-place rewrite preserves siblings.
6. Document the mode in `docs/guides/LOOPS_GUIDE.md` under `harness-optimize` — keep the whole-file mode as the default and the new state-mode as opt-in.

## API/Interface

New optional field on `targets[]` entries:

```yaml
targets:
  - file: <path>            # existing
    glob: <pattern>         # existing
    states:                 # NEW — only valid when file is a *.yaml loop config
      - name: <state-name>
        examples_file: <path>
        eval: <fragment-path>
```

Backwards compatible: omitting `states:` retains today's whole-file behavior.

## Related Key Documentation

| Doc | Why relevant |
|-----|--------------|
| `docs/guides/LOOPS_GUIDE.md` | Where `harness-optimize` is documented; needs the new state-mode section |
| `scripts/little_loops/loops/harness-optimize.yaml` | The loop being extended |
| `scripts/little_loops/loops/apo-textgrad.yaml` | Canonical first consumer of state-mode |

## Scope Boundaries

In scope:
- New optional `targets[].states[]` schema on existing `harness-optimize` loop config
- Per-state extraction, mutation, scoring, accept/revert, and trajectory writing
- One canonical consumer: `apo-textgrad.yaml` (used as the fixture for the integration test)

Out of scope:
- Changing whole-file `harness-optimize` semantics (must remain the default and unchanged for existing runs)
- Building a separate "meta-APO" loop YAML — this is an extension, not a new loop
- Cross-state coupling logic (e.g., joint optimization, shared budgets across states) — each listed state is optimized independently in v1
- New evaluators or judges — state-mode reuses whatever the user passes via `eval:`
- Surface-level prompt mutation strategies (TextGrad/critique-and-refine choice) — orthogonal to targeting

## Impact

- **Priority**: P4 — quality-of-life for maintainers tuning loop prompts; no user-facing feature, no incident driving it
- **Effort**: Medium — schema + ruamel.yaml round-trip helper + per-state trajectory keying + 2-state fixture test. Mutation/accept/revert plumbing is reused unchanged
- **Risk**: Low — opt-in via new optional `states:` key; whole-file path is untouched. Main risk is `ruamel.yaml` round-trip formatting drift, mitigated by the in-place-rewrite test
- **Breaking Change**: No — omitting `states:` retains today's whole-file behavior

## Labels

`enhancement`, `loops`, `harness-optimize`, `meta-apo`, `captured`

## Acceptance Criteria

- [ ] `targets[].states[]` schema parses and validates (rejects when sibling `file` is not a `.yaml` loop config)
- [ ] State-mode extracts each named `action:` block, mutates it in isolation, and writes it back preserving surrounding YAML
- [ ] Score gating is per-state — one state regressing does not revert another state's accepted mutation in the same iteration
- [ ] Trajectory files land at `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl`
- [ ] Existing whole-file `harness-optimize` runs are unchanged (no regression in `test_harness_optimize.py`)
- [ ] Test exercises a 2-state fixture loop end-to-end and asserts only the targeted state's `action:` text changes

## Session Log
- `/ll:format-issue` - 2026-05-17T01:46:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c6e016f-d3b2-4f3e-a2c1-6c7553275998.jsonl`

- `/ll:capture-issue` - 2026-05-17T01:43:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ff744fb-fd2c-4c52-b59d-5acb13e9557a.jsonl`

---

## Status

- **Status**: open
- **Discovered**: 2026-05-17
