---
id: FEAT-3309
title: "Loop\u2192artifact handoff: promote a run artifact to a durable path"
type: FEAT
priority: P2
status: done
discovered_by: manual
discovered_date: '2026-08-23'
completed_at: '2026-08-25T01:18:33Z'
parent: EPIC-3299
depends_on: []
relates_to:
- FEAT-3308
- FEAT-3318
- ENH-3035
labels:
- artifact
- ll-artifact
- fsm
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 21
---

# FEAT-3309: Loop→artifact handoff: promote a run artifact to a durable path

## Summary

Connect the HTML-producing FSM loops to the artifact system. Today they are
entirely disconnected: a loop writes `${run_dir}/index.html` and terminates, and
nothing captures, names, catalogs, or offers to reuse the result. This issue adds
a promotion path that lifts a run's deliverable out of the transient run directory
into a durable, declared location, reported at the end of the run.

**Scope note (split 2026-08-24):** this issue is Part A (promotion) only. Part B —
the `artifact_mode: template` native-emission contract from FEAT-3036 design
principle 1 — is now **FEAT-3318**, which depends on this issue. The two differ in
effort, risk, and subsystem, and Part A is independently valuable; keeping them
fused made the acceptance criteria untestable in isolation.

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
  `fsm/schema.py:1393`, consumed solely by the meta-rule at
  `fsm/validation/meta_rules.py:270-350`. It is not a registry, not a handoff, and
  not read by any runtime code.

Two loops already open-code the missing handoff by hand:
`hitl-md.yaml:256-263` copies `index.html` out of the run dir under a fixed name, and
`vega-viz.yaml:505-513` copies into per-iteration dirs plus `best.html`. Loop
authors want this; there is no infrastructure for it, so they write shell states.

## Expected Behavior

A run's deliverable can be promoted to a durable path in one step, without a
hand-written `cp` state in each loop's YAML, and the promoted path is reported
after the run — including in `--quiet` runs.

## Motivation

Without the handoff, a loop-generated artifact isn't even discoverable: the run
directory is transient, the archive keeps only `summary.json`, and the user is left
copying paths out of terminal scrollback. It is also the precondition for the
epic's user-facing entry point — a user who cannot find the artifact cannot hand it
to `ll-artifact templatize` (FEAT-3308, **done**).

## Proposed Solution

Generalize the `hitl-md` `cp` pattern into runner-side behavior: a loop declares its
deliverable, and on reaching a non-failure terminal the runner copies it to a
durable directory under a declared name, then records the promoted path so the
existing display surface picks it up.

### Deliverable declaration — source and destination

**Decision (resolves the AC-2 conflict):** `artifact_output` declares **both** ends,
because `hitl-md.yaml:263` promotes to a *fixed* filename (`./hitl-md-review.html`)
while a run-identified default is what a generic mechanism wants. A source-only
scalar cannot express both, so a fixed-name promotion must be expressible or
`hitl-md` regresses:

```yaml
artifact_output:
  from: index.html          # required; relative to run_dir
  to: hitl-md-review.html   # optional; default = "{run_id}-{loop_name}{suffix}"
  on: [done]                # optional; default = all non-failure terminals
```

The run-identified default follows `archive_run()`'s precedent
(`fsm/persistence.py:552-589`: `run_id` from `state.started_at`, compact ISO
truncated to 17 chars). A scalar shorthand (`artifact_output: index.html`) is
accepted and means `from:` with the default `to:` and the default `on:`.

`from` is resolved against `fsm.context["run_dir"]`, which carries a **trailing
`/`** and may be **cwd-relative** (`cli/loop/run.py:199`,
`lifecycle.py:667`). `promote_run_artifact` resolves it exactly the way
`hitl-md.yaml:59-63` does today — absolute paths pass through, relative paths are
anchored to the invocation cwd — so the two agree on which directory
`${captured.run_dir.output}` named.

#### Terminal gating — why `on:` exists

**Decision (2026-08-24 review):** "promote on any non-failure terminal" is not a
safe default for the loop this issue retires. `hitl-md.yaml` declares **no
`failure: true` state at all** — `grep failure: hitl-md.yaml` returns only
comments; its `failed:` terminal (`:326-330`) is `terminal: true` only. So
`get_failure_states()` is empty for that loop and *every* terminal is a
non-failure terminal. Today's `cp` is reachable **only** via `score → on_yes →
finalize` (`:251-253`), so an ungated promotion would newly fire on:

- the `finalize_failed → failed` diagnostic path, and
- max-iterations exhaustion, which lands in `done` (`:306` comment).

Both would be behavior changes recorded as PRESERVED. `on:` names the terminal
states that authorize promotion; `hitl-md` declares `on: [done]`, and the
exhaustion case is handled below.

Separately — and as an independent line item, not a substitute for `on:` —
`hitl-md.yaml:326` gains `failure: true`. It is already documented as the
"explicit failure terminal … making failure mode visible in `ll-loop history`",
and the missing flag is a latent defect in its own right. This changes that
loop's reported final status (and exit code) on the failure path, so it is
tracked in the parity table rather than folded in silently.

Max-iterations exhaustion still reaches `done`, which `on:` authorizes. That case
is covered by the missing-source rule below: an exhausted run that never wrote
`index.html` promotes nothing. An exhausted run that *did* write one promotes it
— a deliberate, stated widening of today's behavior, on the grounds that a
best-effort artifact is more useful on the user's disk than in a transient run
dir.

### Destination directory

**Decision:** promotion does **not** use `config.artifacts.default_output_dir` —
it defaults to `"."` (`config/features.py:378`), so promoting there would drop a
file into the project root on every run of nine loops. Add a dedicated key:

```json
"artifacts": { "promotion_dir": ".loops/artifacts" }
```

`promotion_dir` is relative to the project root, created on demand, and already
inside the gitignored `.loops/` tree. A loop's `to:` may be an explicit relative
path (`./hitl-md-review.html`) which is honoured as-is relative to the invocation
cwd — that is how `hitl-md` keeps its current behavior.

Overwrite semantics: promotion overwrites its destination unconditionally (matching
today's `cp`); no `--force` gate, because the destination is either run-identified
(collision-free) or explicitly named by the loop author.

Missing-source semantics: a declared `from:` that does not exist at the terminal
is a **no-op, not an error** — log and return `None`, leave the run's exit status
alone. This is a reachable state, not a defensive branch: a run that exhausts
`max_iterations` before the generate state ever writes `index.html` terminates
cleanly in an `on:`-authorized state with no deliverable on disk.

### Out of scope — `vega-viz.yaml`

`vega-viz.yaml:494-515` is **not** retired by this issue. Its per-iteration
`iter-N/` snapshots plus best-score `best.html` tournament are iterative versioning
across a single run, not a one-shot terminal promotion — closer to the
`artifact_versioning`/MR-5 concern (`meta_rules.py:268-355`). Retiring it into the
generic mechanism is not like-for-like without a versioning story, and it was the
only Medium-risk piece of Part A. Leave the loop alone.

## Use Case

A user runs `html-anything` over an architecture planning document, likes the
result, and — without hunting through `.loops/runs/` — has the artifact promoted to
a durable path they can hand straight to `ll-artifact templatize`.

## Program Design

### Types

- `FSMLoop.artifact_output: ArtifactOutput | None` — a `from`/`to`/`on` triple (see above)

No paired `_ok` suppression flag. The `tamper_guard`/`tamper_guard_ok`,
`prepatch_check`/`prepatch_check_ok` convention (`fsm/schema.py:1373-1382`) exists
for **lint/guard** fields whose warnings an author may need to dismiss.
`artifact_output` is a behavior declaration, not a guard, so the convention does not
apply — this is a deliberate deviation, not an omission.

### Signatures

- `promote_run_artifact(fsm: FSMLoop, run_dir: Path, config: BRConfig) -> Path | None`

### Deviations

- 2026-08-25 (`/ll:manage-issue`): `promote_run_artifact`'s implemented signature is
  `(fsm, run_dir, config, result: ExecutionResult, started_at: str) -> Path | None`,
  two params beyond the cited `(fsm, run_dir, config)`. The design's own Terminal
  Gating and Hook Point sections require `result.failure_terminal`,
  `result.final_state` (the `on:` allowlist check), and `started_at` (the
  run-identified default name, mirroring `archive_run()`'s `state.started_at`
  usage) — passing `result` and `started_at` explicitly avoids re-deriving them
  from executor internals inside the function. Also: `config.artifacts.promotion_dir`
  is resolved against `config.project_root` when relative (not the process cwd) —
  the design's "anchored to the invocation cwd" resolution note applies to `run_dir`
  and a fixed `to:` (loop-authored values), not to this project-level config default;
  anchoring it to cwd caused a real bug in initial implementation (writes landed in
  whatever directory the test/process happened to run from instead of the project
  root) caught by the E2E test in `test_fsm_persistence.py`.
- 2026-08-25: `artifact_output.on` is written unquoted (`on: [done]`) in the design's
  own example YAML, but PyYAML resolves an unquoted `on:` mapping key to the Python
  boolean `True` (YAML 1.1 bareword-boolean resolver) — a landmine that bit the
  `hitl-md.yaml` implementation directly (`ll-loop validate` round-tripped it as
  `{True: ['done']}`). Fixed by quoting `"on":` in `hitl-md.yaml`, and
  `ArtifactOutput.from_dict` now falls back to the `True` key when `"on"` is absent,
  so a loop author who forgets to quote it still gets the declared allowlist instead
  of a silently-empty one.

### Call Path

`PersistentExecutor.run()` -> `promote_run_artifact` ->
`fsm.context["promoted_artifact"]` -> `_artifact_lines` (unchanged) -> new
post-run print

The context key is `promoted_artifact`, not `promoted`: `_artifact_lines`
iterates the whole context, and a bare `promoted` is plausible enough as a loop's
own capture/context name to collide.

### Reporting: `_artifact_lines` needs no change

`_artifact_lines` (`_helpers.py:1258-1280`) iterates `fsm.context` generically and
emits **any** path-like string value. So `promote_run_artifact` setting
`fsm.context["promoted_artifact"] = str(dest)` surfaces the path for free:

- no signature change to `_artifact_lines`;
- the 8 exact-tuple-shape assertions in
  `test_state_feed_renderer.py:369-501` (`TestArtifactLines`) and the consumer
  tests in `test_loop_layout_alignment.py:502,522` build their own contexts and
  therefore stay green.

What *does* remain true: `_artifact_lines` has **no post-run call site** — its two
callers are `_render_artifact_header_lines` (`:1341`, the live per-step diagram
header, during the run) and `run_foreground` (`:1797`, the pre-run banner). So the
CLI still needs **one new post-run print**. That is a line, not a refactor.

### Hook point

`PersistentExecutor.run()` (`fsm/persistence.py:967-1004`).

**Call it immediately after `result = self._executor.run()` (`:979`)** — before
`final_status = map_final_status(...)` (`:982-984`), and specifically before the
`final_state = LoopState(...)` construction (`:986-999`). That constructor
snapshots the context by value at `:997` (`context=dict(self.fsm.context)`), and
that snapshot is what `save_state` (`:1000`) persists and `archive_run` (`:1002`)
archives. Promoting *after* it — anywhere in the "between `map_final_status` and
`archive_run`" window a looser reading allows — sets
`fsm.context["promoted_artifact"]` on a dict nobody reads again, so the promoted
path reaches the terminal print but never the persisted state, and `ll-loop
show`/`history` cannot surface it.

`result.failure_terminal`, `result.terminated_by`, and `result.final_state` (for
the `on:` allowlist check) are all resolved as of `:979`, so nothing about the
earlier call site costs information.

- `resume()` (`:1006-1073`) needs **no separate wiring** — it restores state then
  unconditionally `return self.run(clear_previous=False)` (`:1073`), so it inherits
  the hook.
- `archive_run_only()` (`:916-965`), the signal-driven force-exit path
  (`terminated_by="interrupted_force"`), is **explicitly excluded**: promotion
  requires a clean non-failure terminal, and a force-killed run has not produced a
  vetted deliverable.
- The CLI-layer success check `_is_success = ...` (`_helpers.py:1909-1912`) is
  **not** the hook point: it sits inside `if not renderer.quiet:`, so keying
  promotion to it would silently skip `--quiet` runs.

### Paths that deliberately do not promote

- **Sub-loops.** A child loop launched by a `loop:` state runs through a plain
  `Executor` inside `executor.py:~890-1000`, never a `PersistentExecutor`, so it
  never reaches the hook — even though it *does* inherit the parent's `run_dir`
  (`:903`, `:979-981`). A child declaring `artifact_output` is therefore silently
  ignored. **Out of scope**, but not silently: `ll-loop validate` emits a warning
  when a loop reachable only as a sub-loop declares `artifact_output`, so the
  gap is discoverable rather than mysterious.
- **`cmd_simulate`.** `cli/loop/testing.py:266` calls a bare `executor.run()`, so
  simulate cannot promote — correct, since its `run_dir`
  (`testing.py:217`, `{loop_name}-simulate`) is a fixture directory whose
  `index.html` may be arbitrarily stale. Recorded here so a later reader does not
  "fix" the omission.

### `--quiet` and the post-run print

Every print in `_helpers.py` is guarded by `if not renderer.quiet` — ~15 sites
across `:1049-1206` and `:1792-1897`. The new post-run promotion print is
**deliberately unguarded**, which is the point of AC-1: `--quiet` suppresses the
live decoration, not the one line naming the file the run produced. Implementation
must check for tests asserting that `--quiet` output is empty and update them
with this rationale rather than re-guarding the print.

`failure_terminal`/`terminated_by` are computed in `_finish()`
(`fsm/executor.py:3661-3758`), where `failure_terminal = terminated_by ==
"terminal" and self.current_state in self.fsm.get_failure_states()`;
`get_failure_states()` (`fsm/schema.py:1688-1697`) returns states flagged
`failure: true`.

### Config plumbing

Neither `PersistentExecutor.__init__` (`persistence.py:685-731`, only
`**executor_kwargs` scalar pass-through at `:692,726`) nor `run_foreground`
(`_helpers.py:1720-1735`) accepts a `BRConfig`. `run.py:231` resolves `_config =
BRConfig(Path.cwd())` but threads only scalar derived values (e.g. `run.py:605`).
`promote_run_artifact`'s `config` parameter needs **new plumbing** — either thread
the `BRConfig`, or (simpler, matching the existing idiom) thread the two resolved
scalars: `promotion_dir` and `project_root`.

### Archival

The promoted artifact is **not** additionally archived by `archive_run()`.
Promotion *is* the durability story; copying it twice would leave two sources of
truth with no reconciliation path.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — new `artifact_output` header field beside `artifact_versioning_ok` (`:1393`), serialize (`:1528-1529`), parse (`:1654`)
- `scripts/little_loops/fsm/validation/_base.py:113` — register `artifact_output` in `KNOWN_TOP_LEVEL_KEYS`
- `scripts/little_loops/fsm/persistence.py:967-1004` — call `promote_run_artifact` in `PersistentExecutor.run()`
- `scripts/little_loops/cli/loop/run.py` / `_helpers.py` — thread the promotion config scalars; add the one post-run print
- `scripts/little_loops/loops/hitl-md.yaml:255-269` — replace the hand-written `cp` state; also add `failure: true` to the `failed` terminal (`:326-330`)
- `scripts/little_loops/fsm/validation/` — warn when a sub-loop-only loop declares `artifact_output` (see Program Design → Paths that deliberately do not promote)
- `scripts/little_loops/config/features.py:368-395` — `ArtifactsConfig.promotion_dir`
- `scripts/little_loops/config/core.py:339,476` — `from_dict`/`.artifacts` property/`to_dict` wiring
- `scripts/little_loops/config-schema.json` § `artifacts` (`:1875-1894`) — `additionalProperties: false`; add `promotion_dir` with `type`/`default`/issue-citing description, matching the dataclass default field-for-field

**Not modified** (corrections to the pre-split wiring pass):
- `cli/loop/config_cmds.py::cmd_validate()` — the Part B terminal-shape check moved to FEAT-3318 and is a *runtime* check there, so nothing needs splicing into `ll-loop validate` for it. (Part A does add one advisory rule — the sub-loop-only warning above — but it lands in `fsm/validation/`, which `cmd_validate` already dispatches to unchanged.)
- `_artifact_lines` — see Program Design → Reporting.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation/structural_rules.py:30` — imports `KNOWN_TOP_LEVEL_KEYS`; second consumer of the registry
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()` calls `_artifact_lines`/`_render_artifact_header_lines`; would surface a promoted path if in scope for `ll-loop show`
- `scripts/little_loops/fsm/persistence.py:552-598` — `archive_run`; unchanged (see Archival)

### Similar Patterns
- `fsm/persistence.py:552-589` — `archive_run()`'s run-identified naming (`{run_id}-{loop_name}`), the precedent for the default `to:`
- `fsm/validation/meta_rules.py:270-350` — the existing `artifact_versioning_ok` meta-rule; the new field must not confuse it
- `cli/artifact/templatize.py:585` — `promote(tmp_dir, out_dir, force)`, atomic *directory* promotion with sibling-temp + backup/restore, plus `_sweep_stale_siblings` (`:574`). Not needed for Part A's single-file copy; cited because **FEAT-3318 should reuse it** rather than reimplement.

### Tests
- `scripts/tests/test_fsm_schema.py:3788+` — schema field coverage alongside the existing `artifact_versioning_ok` tests
- `scripts/tests/test_feat3033_idle_timeout.py:27,60-61` (`test_default_idle_timeout_is_known_top_level_key`) — minimal-unit pattern for the `KNOWN_TOP_LEVEL_KEYS` registration
- `scripts/tests/test_fsm_validation_meta_rules.py:843-860` (`test_artifact_versioning_ok_recognized_as_top_level_key`) — closest pattern for confirming `artifact_output` doesn't trip the "Unknown top-level" warning; the MR-5 suite (`:697-860`) is the regression gate for "meta-rule behavior unchanged"
- `scripts/tests/test_fsm_persistence.py:1326-1342` (`test_run_archives_to_history_on_completion`) and `:1430+` (`test_meta_eval_archived_after_run`) — E2E templates for `promote_run_artifact`: run a `PersistentExecutor` to completion and assert the finish-path filesystem side-effect; the meta-eval sibling also covers the "no-op when absent" shape
- `scripts/tests/test_config_schema.py:473-493,1300-1343` — `test_artifacts_in_schema` enumerates `artifacts` keys by name; the BUG-3192 "Guard 1" parity test walks `BRConfig(...).to_dict()` against `config-schema.json` leaf-by-leaf and **auto-fails** on any default mismatch for `promotion_dir`
- New coverage: promotion in a `--quiet` run (the reason the hook is in `persistence.py`, not the CLI success check)
- New coverage: promoted path readable back from **saved state**, not stdout — the regression gate for the `:979`-vs-`:997` ordering
- New coverage: terminal outside `on:` promotes nothing; declared-but-absent `from:` is a clean no-op
- `scripts/tests/test_builtin_loops.py` — loop YAML conformance for `hitl-md.yaml`, including its new `failure: true` terminal

### Documentation
- `docs/reference/API.md:5520-5573` — the hand-maintained `FSMLoop` field-by-field reproduction with inline `#` comments per flag (e.g. `artifact_versioning_ok: bool = False  # ... (ENH-1957)` at `:5561`); nothing auto-generates it, so `artifact_output` needs a hand-written entry
- `docs/reference/CONFIGURATION.md:182,917-923` — documents `default_output_dir`; add `promotion_dir`, and note explicitly that promotion does **not** use `default_output_dir`
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop header fields
- `docs/ARCHITECTURE.md`

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `hitl-md.yaml:255-269` (`finalize` state) | Bash `cp "${captured.run_dir.output}/index.html" "./hitl-md-review.html"`, gated by `output_contains: "FINALIZED"`; `on_yes`/`on_no`/`on_error` all route to `finalize_done` (best-effort, non-blocking) | PRESERVED | Reproduced as `artifact_output: {from: index.html, to: ./hitl-md-review.html, on: [done]}`. `promote_run_artifact` must reproduce the "never fail the run" routing — a promotion failure logs and returns `None`, it does not change the run's exit status. |
| `hitl-md.yaml` reachability of the `cp` | Reachable **only** via `score → on_yes → finalize` (`:251-253`); a failing critique routes to `finalize_failed → failed` and no copy happens | PRESERVED **via `on: [done]`** | Not preserved by "promote on any non-failure terminal": the loop declares no `failure: true` state, so `get_failure_states()` is empty and `failed` reads as a clean terminal. See Proposed Solution → Terminal gating. |
| `hitl-md.yaml:326-330` (`failed` terminal) | `terminal: true` with **no** `failure: true`, despite the comment calling it the "explicit failure terminal … visible in `ll-loop history`" | **CHANGED (intentional)** | Gains `failure: true`. Latent defect fixed on its own merits; `on:` — not this flag — is what protects promotion. Changes the loop's reported final status and exit code on the failure path, which is the intended correction. |
| `hitl-md.yaml` max-iterations exhaustion | Lands in `done` (`:306`) without passing `finalize`, so no copy happens even when `index.html` exists | **CHANGED (intentional)** | `on: [done]` authorizes this terminal, so an exhausted run that produced an `index.html` now promotes it; one that never wrote the file is a no-op per the missing-source rule. Deliberate widening — a best-effort artifact is more useful on disk than in a transient run dir. |
| `hitl-md.yaml:271-284` (`finalize_done` prompt) | Reports artifact paths as plain prose inside an LLM prompt action, independent of `_artifact_lines` | PRESERVED | A second, un-unified reporting convention. Reconciling it is out of scope; leaving it means the path is reported twice, which is harmless. |
| `vega-viz.yaml:494-515` | Per-iteration `iter-N/` snapshots plus a running `best.html`/`best_score.txt`, updated in-place when an iteration beats the stored best | PRESERVED (out of scope) | See Proposed Solution → Out of scope. Iterative versioning, not one-shot promotion; not retired by this issue. |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25; revised at the 2026-08-24 split review:_

- **`KNOWN_TOP_LEVEL_KEYS` is a flat literal frozenset** (`fsm/validation/_base.py:81-143`), not computed — a field absent from it is either silently dropped or flagged unrecognized by the generic unknown-key rule. `fsm-loop-schema.json` has zero references to any header field; header-field shape validation lives entirely in the Python dataclass + this registry.
- **`config.artifacts` extension precedent**: schema keys at `config-schema.json:1875-1894` (each with `type`/`default`/an issue-citing description) and `ArtifactsConfig` at `config/features.py:368-395`, wired at `config/core.py:339,476`. Schema default and dataclass default are hand-kept in sync — no single source of truth.
- **`archive_run()`'s run-identified naming** (`fsm/persistence.py:552-589`) is the one precedent for stable run-identified destination naming, and disagrees with the fixed-overwriting-filename idiom in `hitl-md.yaml:263`. The `from`/`to` pair above exists specifically to span that disagreement.
- **`FEAT-3308` and `FEAT-3036` are both `status: done`** — `depends_on` is cleared; no remaining upstream blocker.

## Implementation Steps

1. Add `ArtifactsConfig.promotion_dir` + the `config-schema.json` key + `config/core.py` wiring, with the parity test green.
2. Add the `artifact_output` header field (`from`/`to`/`on`, scalar shorthand) to `FSMLoop` + `KNOWN_TOP_LEVEL_KEYS`, with tests.
3. Implement `promote_run_artifact` — terminal allowlist, `run_dir` resolution, missing-source no-op — and call it from `PersistentExecutor.run()` immediately after `result = self._executor.run()` (`persistence.py:979`), i.e. **before** the `final_state` context snapshot at `:997`; set `fsm.context["promoted_artifact"]`.
4. Add the one post-run print in the CLI (outside the `quiet` guard), updating any test that asserts `--quiet` output is empty.
5. Retire the hand-written `cp` state in `hitl-md.yaml` with `on: [done]`, and add `failure: true` to its `failed` terminal.
6. Add the `ll-loop validate` advisory for `artifact_output` on a sub-loop-only loop.
7. Docs: `API.md` `FSMLoop` entry, `CONFIGURATION.md` `promotion_dir`, `CLI.md`/`HARNESS_OPTIMIZATION_GUIDE.md` header fields.

## Acceptance Criteria

- [ ] A loop declaring `artifact_output` has its deliverable promoted to the resolved destination on an `on:`-authorized terminal, and the promoted path is reported after the run — **including under `--quiet`**.
- [ ] The promoted path is present in the **persisted** state and the archived run, not just the terminal output — i.e. promotion runs before the `final_state` context snapshot (`persistence.py:997`). Asserted by reading the path back from saved state, not from stdout.
- [ ] `hitl-md.yaml` still produces `./hitl-md-review.html` in the invocation cwd after its hand-written `cp` state is removed, and a promotion failure still routes the run to a normal completion rather than failing it.
- [ ] `hitl-md.yaml` promotes **nothing** on the `finalize_failed → failed` path, matching today's `on_yes`-gated `cp`; the `failed` terminal reports as a failure in `ll-loop history`.
- [ ] Promotion is a no-op (not an error) for loops that declare nothing, for terminals outside `on:`, for failure terminals, for the `archive_run_only()` force-exit path, and for a **declared `from:` that does not exist** at the terminal (the max-iterations-without-output case).
- [ ] A loop declaring `artifact_output` and run as a sub-loop promotes nothing and `ll-loop validate` says so.
- [ ] `promotion_dir` defaults to a directory inside `.loops/`, and nothing is written to the project root by default; the `config-schema.json`/`ArtifactsConfig` default parity test is green.
- [ ] `_artifact_lines`' return shape is unchanged — asserted by `TestArtifactLines` (`test_state_feed_renderer.py:369-501`) staying green with no edits.
- [ ] The existing `artifact_versioning_ok` meta-rule behavior is unchanged — asserted by the current MR-5 tests staying green.
- [ ] `vega-viz.yaml` is untouched.

## Impact

- **Priority**: P2 — the epic's motivating loops have zero connection to the artifact system today; without this the epic improves only the hand-built dashboard lineage.
- **Effort**: Medium.
- **Risk**: Low — additive header field, a copy on an authorized terminal, and one config key. The Medium-risk `vega-viz` retirement was cut from scope, and Part B moved to FEAT-3318. The one non-additive change is `hitl-md`'s `failed` terminal gaining `failure: true`, scoped to that loop and tracked in the parity table.
- **Breaking Change**: No for the field (defaults to today's behavior). `hitl-md`'s failure-path exit code changes — intentionally, as a defect fix.

## Related Key Documentation

- `.issues/features/P2-FEAT-3318-artifact-mode-template-loops-emit-template-data-natively.md` — Part B, split out of this issue
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design principle 1
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`

## Status

**Open** | Created: 2026-08-23 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-08-25T01:18:14 - `c0b9fe69-0e8b-4aa4-850b-b9fc74a99fe4.jsonl`
- `/ll:ready-issue` - 2026-08-25T00:48:41 - `6b9d2b35-5899-4da0-a89c-c5c8e28da0ba.jsonl`
- `/ll:confidence-check` - 2026-08-25T00:41:40 - `0e80376c-027e-4f90-86a7-35c1d4c043e1.jsonl`
- Pre-implementation review - 2026-08-24 - added `artifact_output.on:` terminal gating (hitl-md declares no `failure: true` state, so "non-failure terminal" was not a safe default), pinned the hook to `persistence.py:979` ahead of the `:997` context snapshot, added missing-source and sub-loop/simulate semantics, renamed the context key to `promoted_artifact`
- `/ll:confidence-check` - 2026-08-25T00:30:25 - `050c493c-d9d9-4791-a094-bde43a4931f1.jsonl`
- Split review (Part B → FEAT-3318) - 2026-08-24
- `/ll:wire-issue` - 2026-08-25T00:18:20 - `b8595162-30d1-4d8e-aa96-0405ac242701.jsonl`
- `/ll:refine-issue` - 2026-08-25T00:09:15 - `e68d9c91-c92e-440c-bb0a-512c7293fa47.jsonl`
