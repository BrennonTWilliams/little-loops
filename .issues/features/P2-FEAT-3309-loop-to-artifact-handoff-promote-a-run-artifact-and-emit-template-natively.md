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

Part A is worth landing alone; Part B's template format precondition (FEAT-3036
Phase 1) is done, so Part B is unblocked on that front.

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

> ⚠ Confirmed against the tree: `_artifact_lines` has **no existing post-run call
> site** — its two callers are `_render_artifact_header_lines` at `_helpers.py:1341`
> (the live per-step diagram header, called *during* the run) and `run_foreground`
> at `_helpers.py:1797` (the pre-run banner, called *before* `executor.run()`).
> Neither fires after completion; wiring `promote_run_artifact` into this surface
> means adding a **new** call after the run, not repurposing an existing one.
>
> The clean, quiet-mode-independent hook point is
> `PersistentExecutor.run()` (`fsm/persistence.py:967-1004`): `result =
> self._executor.run()` (`:979`) is immediately followed by `final_status =
> map_final_status(result.terminated_by, failure_terminal=result.failure_terminal)`
> (`:982-984`) and `self.persistence.archive_run(run_dir=...)` (`:1002`) before
> `return result` (`:1004`) — `promote_run_artifact` fits between those two calls,
> with `result.failure_terminal`/`result.terminated_by` already resolved.
> `resume()` has its own separate finish path (`:940-945`) needing the same call.
>
> By contrast, the CLI layer's own success check — `_is_success = result.terminated_by
> in ("terminal", "interrupted", "handoff") and not result.failure_terminal`
> (`_helpers.py:1909-1912`) — sits **inside** `if not renderer.quiet:`, so a
> promotion hook keyed to that line would silently skip in `--quiet` runs.
>
> Neither `PersistentExecutor.__init__` (`persistence.py:685-731`) nor
> `run_foreground` (`_helpers.py:1720-1735`) currently accepts a `BRConfig`/
> `ArtifactsConfig` object — `run.py:231` resolves `_config = BRConfig(Path.cwd())`
> but only threads scalar derived values through (e.g. `run.py:605`), never the
> config object itself. `promote_run_artifact(fsm, run_dir, config)`'s `config`
> parameter needs new plumbing, not an existing pass-through.
>
> `failure_terminal`/`terminated_by` themselves are computed in `_finish()`
> (`fsm/executor.py:3661-3758`): `failure_terminal = terminated_by == "terminal"
> and self.current_state in self.fsm.get_failure_states()`, where
> `get_failure_states()` (`fsm/schema.py:1688-1697`) returns states with an
> explicit `failure: true` flag.
> — _Added by `/ll:refine-issue` (codebase-analyzer, FEAT-3309)_

### Decision Rules

Part B's terminal-shape check ("Validation ... checks the declared output shape
exists at the terminal state") is a new kind of gate — no existing
`fsm/validation/` rule inspects the filesystem post-run (see Integration Map →
Codebase Research Findings). Before implementation this gate needs its inputs
pinned down, none of which the issue currently specifies:

- Exact manifest/body/data filenames the check requires (`data.json` is named;
  "manifest" and "body" are not given concrete filenames or extensions).
- Whether the check runs inside `fsm/validation/` (pre-execution, against
  declared paths only — consistent with every existing rule) or as a new
  post-run runtime check (the only way to verify files that don't exist until
  the loop has actually run) — these are different subsystems with different
  failure semantics, and the issue's placement ("Validation (`fsm/validation/`)
  checks ...") reads as the former while the actual need is the latter.
- The escape hatch / dismissal path when a `artifact_mode: template` loop's
  terminal state is a failure state (no output expected) vs. a non-failure
  terminal that's missing the declared shape (a real defect).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — new header fields beside `artifact_versioning_ok` (`:1362-1363`), serialize (`:1498`), parse (`:1624`)
- `scripts/little_loops/fsm/validation/_base.py:113` — register the new known keys
- `scripts/little_loops/cli/loop/_helpers.py` — promotion + reporting (`_artifact_lines` `:1258`)
- `scripts/little_loops/loops/hitl-md.yaml:256-263`, `vega-viz.yaml:505-513` — replace hand-written `cp` states once promotion exists

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:368-395` — `ArtifactsConfig` dataclass needs a new promotion-naming key alongside `default_output_dir`/`templates_dir`/`templatize_max_input_bytes` [Agent 1/2 finding]
- `scripts/little_loops/config/core.py:339,476` — wiring for the new `ArtifactsConfig` key (`from_dict`/`.artifacts` property/`to_dict`) [Agent 1/2 finding]
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` (`:14`) is the actual site `ll-loop validate`'s new terminal-shape/deliverable check must be spliced into; no existing pattern in this function merges a second, independently-sourced validation pass into the same violations list for both `--json` (`:69-84`) and plain-text (`:31-37`, raise-inside-try) exit paths [Agent 2 finding — directly implements the AC]
- `scripts/little_loops/fsm/validation/__init__.py` — strict per-symbol re-export registry (`__all__`, `:44-267`); any new `_validate_*` function added for the Part B terminal-shape check must be added here or it's invisible to `fsm/executor.py`/`fsm/persistence.py`/`fsm/route_table.py` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:198-199,572` — run_dir seeding/creation
- `scripts/little_loops/fsm/persistence.py:552-598` — `archive_run`; decide whether a promoted artifact is archived
- `scripts/little_loops/fsm/persistence.py:967-1004` — `PersistentExecutor.run()`; the hook point for `promote_run_artifact`, between `result = self._executor.run()` (`:979`) and `self.persistence.archive_run(...)` (`:1002`) — no config object flows through this constructor today (confirmed: only `**executor_kwargs` scalar pass-through, `:692,726`)
- `scripts/little_loops/cli/loop/run.py:231,605` — `_config = BRConfig(Path.cwd())` is resolved here but only scalar derived values are threaded into `run_foreground` (e.g. `show_input=_config.loops.run_defaults.show_input`); no existing path threads the config object (or `config.artifacts.default_output_dir`) into the executor

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py:1006-1073` — `PersistentExecutor.resume()`: confirmed it has **no independent finish path** — it restores state then unconditionally `return self.run(clear_previous=False)` (`:1073`). The `promote_run_artifact` hook only needs wiring once, inside `run()`; `resume()` gets it for free via delegation [Agent 1/2 finding — resolves the Program Design note's open question]
- `scripts/little_loops/fsm/persistence.py:916-965` — `PersistentExecutor.archive_run_only()`, the signal-driven force-exit path (`terminated_by="interrupted_force"`), is a **third** `archive_run()` call site not covered by `run()`/`resume()`. It shares `map_final_status()` with `run()` "so the two paths cannot drift" (`:124-128` docstring) but calls `self.persistence.archive_run(...)` independently at `:965`. Since promotion is scoped to "a non-failure terminal," this path is presumably excluded — but that's an explicit decision to make, not an automatic exclusion [Agent 2 finding]
- `scripts/little_loops/fsm/validation/structural_rules.py:30` — imports `KNOWN_TOP_LEVEL_KEYS` from `_base.py`; another consumer of the registry the new keys are added to [Agent 1 finding]
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()` already calls `_artifact_lines`/`_render_artifact_header_lines` from `_helpers.py` for the existing artifact-path display; the only found consumer that would surface a promoted path via `ll-loop show` if that's in scope [Agent 2 finding]

### Similar Patterns
- `fsm/validation/meta_rules.py:270-350` — the existing `artifact_versioning_ok` meta-rule; new fields must not confuse it

### Tests
- `scripts/tests/test_fsm_schema.py:3788+` — schema field coverage, alongside the existing `artifact_versioning_ok` tests
- `scripts/tests/test_builtin_loops.py` — loop YAML conformance for any loop declaring the new fields
- New coverage for `promote_run_artifact`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation_meta_rules.py:697-860` — `test_artifact_versioning_ok_recognized_as_top_level_key` (`:843-860`) is the closest existing pattern for confirming `artifact_output`/`artifact_mode` don't trip the "Unknown top-level" warning; the MR-5 suite here is also the regression gate for the AC "existing `artifact_versioning_ok` meta-rule behavior is unchanged" [Agent 1/3 finding]
- `scripts/tests/test_config_schema.py:473-493,1300-1343` — `test_artifacts_in_schema` (`:473-493`) enumerates `artifacts` keys by name against `additionalProperties: false`; the BUG-3192 "Guard 1" parity test (`:1300-1323`) walks `BRConfig(...).to_dict()` against `config-schema.json` defaults leaf-by-leaf and **already auto-fails** on any default mismatch between `ArtifactsConfig` and the schema for a new promotion key [Agent 1/2 finding]
- `scripts/tests/test_state_feed_renderer.py:369-501` (`class TestArtifactLines`) — 8 existing tests assert the **exact tuple-list shape** of `_artifact_lines`' return value (e.g. `result == [("loop", str(loop_path))]`); likely to break if the promoted-path extension changes ordering or adds an unconditional entry [Agent 3 finding — likely to break]
- `scripts/tests/test_loop_layout_alignment.py:502,522` — a second, independent `_artifact_lines` consumer test [Agent 3 finding]
- `scripts/tests/test_fsm_persistence.py:1326-1342` (`test_run_archives_to_history_on_completion`) and `:1430+` (`test_meta_eval_archived_after_run`) — the closest existing E2E templates for a new `promote_run_artifact` test: run a `PersistentExecutor` to completion and assert on the finish-path filesystem side-effect; the meta-eval sibling also covers the "no-op when absent" shape needed for the AC [Agent 3 finding]
- `scripts/tests/test_feat3033_idle_timeout.py:27,60-61` (`test_default_idle_timeout_is_known_top_level_key`) — minimal-unit pattern for a new `KNOWN_TOP_LEVEL_KEYS` registration, simpler than the full `load_and_validate` integration pattern above [Agent 3 finding]
- No existing test exercises `ll-loop validate` (or `load_and_validate`) **rejecting** a field-value combination — every existing precedent (`test_artifact_versioning_ok_recognized_as_top_level_key` et al.) only checks for the *absence* of an unknown-key warning. A genuinely new test is required for the AC "`ll-loop validate` rejects a loop declaring `artifact_mode: template` without a declared deliverable" [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (loop header fields), `docs/ARCHITECTURE.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `FSMLoop` (`:5520-5573`) — a hand-maintained field-by-field reproduction of the dataclass with inline `#` comments per flag (e.g. `artifact_versioning_ok: bool = False  # Suppress MR-5 ... (ENH-1957)` at `:5561`); nothing auto-generates this, so `artifact_output`/`artifact_mode` need an equivalent hand-written entry or the doc goes stale immediately [Agent 2 finding]
- `docs/reference/API.md:6312` — MR-5 rule prose (`"MR-5 (WARNING): harness-category loop writes artifact files..."`), a near-duplicate of `docs/reference/CLI.md:870`'s consolidated "suppressed by" sentence; if the Part B terminal-shape check is framed as a new numbered MR rule, both files need independent updates (no shared source) [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:182,917-923` — documents `default_output_dir`'s default and purpose; needs an entry for the new promotion-naming config key [Agent 1 finding]

### Configuration
- `scripts/little_loops/config-schema.json` § `artifacts` (`:1875-1894`) — `additionalProperties: false` today; exactly three keys exist (`default_output_dir`, `templates_dir`, `templatize_max_input_bytes`); promotion naming/behavior settings must be added there explicitly, matching `ArtifactsConfig`'s new key field-for-field (see Files to Modify above)

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `hitl-md.yaml:255-269` (`finalize` state) | Bash `cp "${captured.run_dir.output}/index.html" "./hitl-md-review.html"`, gated by `output_contains: "FINALIZED"`; `on_yes`/`on_no`/`on_error` all route to `finalize_done` (best-effort, non-blocking) | PRESERVED | Fixed, overwriting destination filename in the invocation cwd — not run-identified. A generic `promote_run_artifact` must reproduce this "never fail the run" routing, or the change is user-visible. |
| `hitl-md.yaml:271-284` (`finalize_done` prompt) | Reports the promoted/build artifact paths as plain prose inside an LLM prompt action — independent of `_artifact_lines`/CLI header rendering | PRESERVED or CHANGED (implementer's call) | This is a second, un-unified reporting convention alongside `_artifact_lines`; the issue's plan to report via `_artifact_lines` does not by itself remove or reconcile this prompt-text path. |
| `vega-viz.yaml:494-515` | Per-iteration snapshot into `iter-N/` plus a running `best.html`/`best_score.txt` pair, updated in-place when a new iteration's score beats the stored best | DROPPED (per Proposed Solution) or PRESERVED (implementer's call) | Not a one-shot final promotion — it is iterative versioning across the loop's own run, closer to the `artifact_versioning`/MR-5 concern (`meta_rules.py:268-355`) than to the single-terminal-copy promotion this issue designs. Retiring it into the generic mechanism is not a like-for-like replacement without a versioning story. |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **New `str | None` header field convention**: every prior loop-header field of this shape pairs the field with a same-named `_ok` suppression-flag bool (e.g. `tamper_guard`/`tamper_guard_ok`, `prepatch_check`/`prepatch_check_ok`). Precedent: field declarations at `fsm/schema.py:1373-1382`, conditional `to_dict()` emission at `:1505-1513`, `from_dict()` at `:1644-1647`, `KNOWN_TOP_LEVEL_KEYS` registration (field + `_ok` flag together) at `fsm/validation/_base.py:124-129`. `artifact_output`/`artifact_mode` as currently scoped have no paired `_ok` flag — a deliberate deviation from this convention, or an omission, is the implementer's call.
- **`KNOWN_TOP_LEVEL_KEYS` is a flat literal frozenset** (`fsm/validation/_base.py:81-143`), not computed — a field absent from it is either silently dropped or flagged unrecognized by the generic unknown-key rule. `fsm-loop-schema.json` has zero references to any of these header fields — header-field shape validation lives entirely in the Python dataclass + this registry, not the JSON schema file.
- **No existing meta-rule (or any `fsm/validation/` rule) checks the filesystem for a file's actual post-run existence.** Every rule found (`_validate_terminal_action_ok` `evaluator_rules.py:32`, `_validate_llm_evidence_contract` `:478`, `_validate_artifact_isolation`/`_validate_artifact_overwrite` `meta_rules.py:191,268`) operates purely on the statically parsed `FSMLoop`/`StateConfig` structure before execution — none opens a file handle. A runtime "does the terminal state's manifest+body+data.json exist" check for `artifact_mode: template` (Proposed Solution Part B) is not an extension of this static-validation family; it is a new kind of check with no existing precedent to extend.
- **`config.artifacts` has one prior extension precedent**: schema keys at `config-schema.json:1875-1894` (each with `type`/`default`/a description citing its introducing issue) and the matching `ArtifactsConfig` dataclass at `config/features.py:368-395`, wired at `config/core.py:339,476`. The rule shared by every key: schema default and dataclass default are hand-kept in sync (no single source of truth) — adding a promotion-related key means touching both files plus the `from_dict()` line.
- **`archive_run()`'s run-identified naming** (`fsm/persistence.py:552-589`, `run_id` derived from `state.started_at`, compact ISO truncated to 17 chars, dir `{run_id}-{loop_name}`) is the one precedent for stable run-identified destination naming in this codebase. It disagrees with the two hand-rolled `cp` idioms it would replace: `hitl-md.yaml:263` and `vega-viz.yaml:513-514` both promote to a **fixed, overwriting filename** with no run-id or timestamp embedded.

## Implementation Steps

1. Add `artifact_output` to the FSM header + validation known-keys, with tests.
2. Implement `promote_run_artifact` and surface the promoted path via `_artifact_lines`.
3. Retire the hand-written `cp` states in `hitl-md.yaml` and `vega-viz.yaml`.
4. (Part B, after FEAT-3036 Phase 1) Add `artifact_mode: template`, the template-emitting generate-prompt variant, and terminal-shape validation.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/config/features.py` (`ArtifactsConfig`) and `scripts/little_loops/config/core.py` alongside `config-schema.json` — the BUG-3192 "Guard 1" parity test in `test_config_schema.py` auto-fails on any default mismatch between the dataclass and the schema for the new key.
- Update `scripts/little_loops/cli/loop/config_cmds.py::cmd_validate()` to splice the Part B terminal-shape/deliverable check's result into `ll-loop validate`'s existing violations list — no current pattern merges a second, independently-sourced validation pass for both the `--json` and plain-text exit paths.
- Decide whether `PersistentExecutor.archive_run_only()` (`fsm/persistence.py:916-965`, the signal-driven force-exit path) also runs `promote_run_artifact`, or is explicitly excluded as a third `archive_run()` call site outside `run()`/`resume()`.
- Add `artifact_output`/`artifact_mode` entries to `docs/reference/API.md`'s hand-maintained `FSMLoop` field reproduction (`:5520-5573`) and, if Part B's check is framed as a new MR rule, its MR-rule prose (`:6312`) alongside `docs/reference/CLI.md:870`.
- Write a new `ll-loop validate`-level rejection test — no existing test exercises rejecting a field-value combination (only unknown-key warning-list presence checks exist).

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


## Session Log
- `/ll:wire-issue` - 2026-08-25T00:18:20 - `b8595162-30d1-4d8e-aa96-0405ac242701.jsonl`
- `/ll:refine-issue` - 2026-08-25T00:09:15 - `e68d9c91-c92e-440c-bb0a-512c7293fa47.jsonl`
