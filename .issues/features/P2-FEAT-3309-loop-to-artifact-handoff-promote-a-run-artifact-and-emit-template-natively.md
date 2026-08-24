---
id: FEAT-3309
title: 'Loop→artifact handoff: promote a run artifact, and emit template+data natively'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-23'
parent: EPIC-3299
depends_on:
- FEAT-3036
relates_to:
- FEAT-3308
- ENH-3035
labels:
- artifact
- ll-artifact
- fsm
- templates
---

# FEAT-3309: Loop→artifact handoff: promote a run artifact, and emit template+data natively

## Summary

Connect the HTML-producing FSM loops to the artifact system. Today they are
entirely disconnected: a loop writes `${run_dir}/index.html` and terminates, and
nothing captures, names, catalogs, or offers to reuse the result. This issue adds
(a) a promotion path that lifts a run's artifact out of the run directory into a
durable, named location, and (b) the `artifact_mode: template` loop-output contract
from FEAT-3036's design principle 1 — loops emitting template + data natively
rather than a fused single file.

## Current Behavior

Verified against the tree:

- `run_dir` is seeded by the CLI (`cli/loop/run.py:198-199`, `lifecycle.py:666-667`,
  `testing.py:216-217`) and created at `run.py:572`.
- Loops write `${context.run_dir}/index.html`: `html-website-generator.yaml:78`,
  `html-anything.yaml:133`, `interactive-component-generator.yaml:211,399`,
  `generative-art.yaml:104`, `pixi-generative-art.yaml:108`, `pixi-data-viz.yaml`,
  `p5js-sketch-generator.yaml`, `vega-viz.yaml:262`, `hitl-md.yaml:167`.
- After the run the runner only **displays** paths — `_artifact_lines`
  (`cli/loop/_helpers.py:1258`), rendered by `_render_artifact_header_lines` (`:1310`).
- `FSMPersistence.archive_run` (`fsm/persistence.py:552-598`) copies only
  `summary.json`. The artifact is not even retained by the archive path.
- `artifact_versioning_ok` is **only** a lint concept: declared at
  `fsm/schema.py:1363`, consumed solely by the meta-rule at
  `fsm/validation/meta_rules.py:270-350`. It is not a registry, not a handoff, and
  not read by any runtime code.

Two loops already open-code the missing handoff by hand:
`hitl-md.yaml:256-263` copies `index.html` out of the run dir under a fixed name, and
`vega-viz.yaml:505-513` copies into per-iteration dirs plus `best.html`. Loop
authors want this; there is no infrastructure for it, so they write shell states.

## Expected Behavior

1. A run's HTML deliverable can be promoted to a durable path in one step, without
   a hand-written `cp` state in each loop's YAML.
2. A loop can declare that it emits template + data rather than a fused artifact,
   and the runner treats that output as an artifact template directly — the
   lossless path, with FEAT-3308's post-hoc `templatize` as the lossy fallback.

## Motivation

FEAT-3036 design principle 1 states: "Artifact-producing FSM loops should emit
template + data natively; post-hoc extraction is a second, lossier path." Nothing
in EPIC-3299 currently owns that principle — no child issue, no loop change, no
runner change. As a result *both* routes from a loop-generated artifact to a
reusable template are unscoped, and the epic's four existing children all serve the
hand-built policy-builder/dashboard lineage instead.

Without the handoff, a promoted artifact isn't even discoverable: the run directory
is transient, the archive keeps only `summary.json`, and the user is left copying
paths out of terminal scrollback.

## Proposed Solution

**Part A — promotion (small, unblocks the user story now).**
Generalize the `hitl-md`/`vega-viz` `cp` pattern into runner-side behavior: a loop
declares its deliverable (e.g. `artifact_output: index.html`), and on reaching a
non-failure terminal the runner copies it to
`config.artifacts.default_output_dir` under a stable, run-identified name, then
reports the promoted path through the existing `_artifact_lines` surface. Existing
hand-written `cp` states become redundant and can be removed loop-by-loop.

**Part B — native emission (`artifact_mode: template`).**
A new FSM header field alongside `artifact_versioning_ok` (`fsm/schema.py:1362-1363`)
declaring that the loop's deliverable is a template directory (manifest + body +
`data.json`) rather than a single fused file. The generate prompts in the HTML loop
family gain a variant that writes the two separately. Validation (`fsm/validation/`)
checks the declared output shape exists at the terminal state.

Part A is worth landing alone; Part B depends on FEAT-3036 Phase 1 fixing the
template format.

## Use Case

A user runs `html-anything` over an architecture planning document, likes the
result, and — without hunting through `.loops/runs/` — has the artifact promoted to
a durable path they can hand to `ll-artifact templatize` (FEAT-3308) or, if the loop
ran in `artifact_mode: template`, has a ready-made template with no extraction step
at all.

## Program Design

### Types

- `FSMLoop.artifact_output: str | None` — deliverable filename relative to `run_dir`
- `FSMLoop.artifact_mode: Literal["file", "template"] = "file"`

### Signatures

- `promote_run_artifact(fsm: FSMLoop, run_dir: Path, config: BRConfig) -> Path | None`
- `_artifact_lines(fsm: FSMLoop, loop_path: Path) -> list[str]` — extended to report the promoted path

### Call Path

`main_loop` -> `promote_run_artifact` -> `_artifact_lines` -> `_render_artifact_header_lines`

(`_artifact_lines` is `scripts/little_loops/cli/loop/_helpers.py:1258`;
`_render_artifact_header_lines` is the same file at `:1310`; `promote_run_artifact`
is new.)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — new header fields beside `artifact_versioning_ok` (`:1362-1363`), serialize (`:1498`), parse (`:1624`)
- `scripts/little_loops/fsm/validation/_base.py:113` — register the new known keys
- `scripts/little_loops/cli/loop/_helpers.py` — promotion + reporting (`_artifact_lines` `:1258`)
- `scripts/little_loops/loops/hitl-md.yaml:256-263`, `vega-viz.yaml:505-513` — replace hand-written `cp` states once promotion exists

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:198-199,572` — run_dir seeding/creation
- `scripts/little_loops/fsm/persistence.py:552-598` — `archive_run`; decide whether a promoted artifact is archived

### Similar Patterns
- `fsm/validation/meta_rules.py:270-350` — the existing `artifact_versioning_ok` meta-rule; new fields must not confuse it

### Tests
- `scripts/tests/test_fsm_schema.py:3788+` — schema field coverage, alongside the existing `artifact_versioning_ok` tests
- `scripts/tests/test_builtin_loops.py` — loop YAML conformance for any loop declaring the new fields
- New coverage for `promote_run_artifact`

### Documentation
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (loop header fields), `docs/ARCHITECTURE.md`

### Configuration
- `scripts/little_loops/config-schema.json` § `artifacts` (`:1870-1880`) — `additionalProperties: false` today; promotion naming/behavior settings must be added there explicitly

## Implementation Steps

1. Add `artifact_output` to the FSM header + validation known-keys, with tests.
2. Implement `promote_run_artifact` and surface the promoted path via `_artifact_lines`.
3. Retire the hand-written `cp` states in `hitl-md.yaml` and `vega-viz.yaml`.
4. (Part B, after FEAT-3036 Phase 1) Add `artifact_mode: template`, the template-emitting generate-prompt variant, and terminal-shape validation.

## Acceptance Criteria

- [ ] A loop declaring `artifact_output` has its deliverable promoted to `config.artifacts.default_output_dir` on a non-failure terminal, and the promoted path is reported in the run summary.
- [ ] `hitl-md.yaml` and `vega-viz.yaml` produce the same user-visible outputs after their hand-written `cp` states are removed.
- [ ] Promotion is a no-op (not an error) for loops that declare nothing, and for failure terminals.
- [ ] `artifact_mode: template` validates that the terminal state produced a manifest + body + `data.json`, and the result is directly accepted by `ll-artifact render` with no `templatize` step.
- [ ] `ll-loop validate` rejects a loop declaring `artifact_mode: template` without a declared deliverable.
- [ ] The existing `artifact_versioning_ok` meta-rule behavior is unchanged — asserted by the current tests staying green.

## Impact

- **Priority**: P2 — the epic's motivating loops have zero connection to the artifact system today; without this the epic improves only the hand-built dashboard lineage.
- **Effort**: Medium for Part A, Large for Part B.
- **Risk**: Low for Part A (additive header field + copy on terminal); Medium for Part B (changes the loop output contract).
- **Breaking Change**: No — both fields default to today's behavior.

## Related Key Documentation

- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design principle 1
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`

## Status

**Open** | Created: 2026-08-23 | Priority: P2
