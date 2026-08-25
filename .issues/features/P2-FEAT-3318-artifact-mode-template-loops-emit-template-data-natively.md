---
id: FEAT-3318
title: '`artifact_mode: template`: loops emit template + data natively'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-24'
parent: EPIC-3299
depends_on:
- FEAT-3309
relates_to:
- FEAT-3308
- FEAT-3036
labels:
- artifact
- ll-artifact
- fsm
- templates
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-3318: `artifact_mode: template` — loops emit template + data natively

## Summary

Split out of FEAT-3309 (Part B) at the 2026-08-24 review. Adds the loop-output
contract from FEAT-3036 design principle 1: an FSM loop declares that its
deliverable is an artifact **template directory** (`manifest.yaml` + one
`template.*.j2` + `data.json`) rather than a single fused HTML file, and the runner
promotes and validates that shape directly — the lossless path, with FEAT-3308's
post-hoc `ll-artifact templatize` as the lossy fallback.

FEAT-3309 was carrying this as "Part B" alongside its promotion mechanism. They
differ in effort (Medium vs Large), risk (Low vs Medium), and subsystem (runner
finish path vs loop output contract plus generate-prompt rewrites), and fusing them
made both sets of acceptance criteria untestable in isolation.

## Current Behavior

- FEAT-3036 design principle 1 — "Artifact-producing FSM loops should emit template
  + data natively; post-hoc extraction is a second, lossier path" — is **unowned by
  any implementation issue** now that FEAT-3309 is promotion-only.
- Every HTML-producing loop writes a single fused `${run_dir}/index.html`
  (`html-anything.yaml:133`, `html-website-generator.yaml:78`, and seven siblings —
  full list in FEAT-3309 § Current Behavior).
- The only route from a loop artifact to a reusable template is
  `ll-artifact templatize` (FEAT-3308, **done**), which re-derives structure from
  finished HTML via an LLM discovery call — lossy by construction, and bounded by
  `artifacts.templatize_max_input_bytes` (`config/features.py:386`).
- No `fsm/validation/` rule — and no runtime check anywhere — inspects the
  filesystem for a loop's actual post-run output shape. Every rule found
  (`_validate_terminal_action_ok` `evaluator_rules.py:32`,
  `_validate_llm_evidence_contract` `:478`, `_validate_artifact_isolation` /
  `_validate_artifact_overwrite` `meta_rules.py:191,268`) operates purely on the
  statically parsed `FSMLoop`/`StateConfig` before execution; none opens a file
  handle.

## Expected Behavior

A loop can declare `artifact_mode: template`. On a non-failure terminal the runner
promotes the declared **directory** and verifies it is a loadable template — and
the result is directly accepted by `ll-artifact render` with no `templatize` step.

## Motivation

`templatize` reconstructs structure the generating loop already knew and threw
away. A loop that writes `data.json` alongside its Jinja2 body loses nothing, needs
no LLM discovery call, and has no round-trip fidelity risk. This is the lossless
half of the epic's fan-out story; without it the epic ships only the lossy half.

## Proposed Solution

### The template shape is already pinned — no design decision needed

FEAT-3309 left "exact manifest/body/data filenames" as an open decision. It is not
open: `artifact_templates.py` already fixes the contract, and these loaders are
what the check must call.

- `manifest.yaml` — `load_manifest(root)` (`artifact_templates.py:142`). Required
  keys `name`, `version`, `renderer`, `output`, `data_schema` (`:25`); optional
  `theme`, `source`, `extraction` (`:26`). Fails closed on unknown keys,
  `renderer != jinja2`, an invalid `theme`, a `data_schema` construct outside the
  documented subset, or a reserved top-level `ll` key.
- **Exactly one** `template.*.j2` body — `find_template_body(root)` (`:265`), which
  errors on both zero and multiple candidates.
- `data.json` — `load_data` (`:331`) + `validate_top_level_data` (`:233`), validated
  against `manifest.data_schema`.
- Optional `assets/` — `load_assets` (`:278`), UTF-8 text only in v1.
- Canonical directory name: `<stem>.llat/` (`templatize.py:769`).

### Two gates, two subsystems — do not conflate them

FEAT-3309 described a single "validation" gate whose placement was ambiguous. There
are two, and they are unrelated:

1. **Static gate (`fsm/validation/`)** — reject a loop declaring
   `artifact_mode: template` with **`fsm.artifact_output is None`** ("declared
   deliverable" = an `artifact_output` block; there is no other deliverable
   declaration in the schema). Operates on the parsed `FSMLoop` only, consistent
   with every existing rule. This is the gate that surfaces in `ll-loop validate`.

   **The gate fires on *selectability*, not just on the effective value.**
   Reading only `fsm.artifact_mode` makes the gate blind in exactly the
   scenario § Mode selection designs for: a loop that declares `artifact_mode`
   as a `context:` var for per-run `--context` selection has
   `fsm.artifact_mode == "file"`. But reading the effective mode
   (`fsm.context.get("artifact_mode", fsm.artifact_mode)`) is *also* not
   enough, and misses the more common shape: `html-anything` will declare
   `context: {artifact_mode: file}` — keeping default behavior unchanged — and
   be flipped per-run with `--context artifact_mode=template`. At validate
   time there is no `--context`, so the effective mode is `"file"` and a
   value-only gate never fires on the one loop template mode exists to serve.
   `context: {artifact_mode: template}` (the shape AC #2 names) is the *rarer*
   case.

   Fire the gate when the effective mode is `"template"` **or** when
   `"artifact_mode" in fsm.context` at any value — declaring the key as a
   context var *is* the declaration that the loop can run in template mode,
   and a loop that can run in template mode needs an `artifact_output` block.

   The gate also emits a **WARNING** when `artifact_output.to` is set under a
   template-capable loop and does not end in `.llat` — see § Default
   destination on why a non-`.llat` destination is unresolvable by bare name.

   **Registration is a call site, not an `__all__` entry.**
   `fsm/validation/__init__.py:160`'s `__all__` is a re-export list for test
   access and cross-module callers — adding a name to it does not make the rule
   run. The live precedent is `_validate_artifact_output_subloop_reachability`
   (`reachability.py:104`), which is *absent* from `__all__` yet runs, because it
   is invoked from `load_and_validate()` at `structural_rules.py:1757`. The new
   gate needs an equivalent call site — inside `validate_fsm()`
   (`structural_rules.py:910+`) since it needs no filesystem access.

   **Severity: ERROR, with no paired `artifact_mode_ok` suppression flag.** Of the
   three live precedents surfaced in research (`on_handoff` — no validator;
   `tamper_guard` — WARNING + suppression flag; `visibility` — inline WARNING, no
   flag), none applies: this is a behavior declaration that *cannot work* as
   written, not a dismissable lint opinion. Same reasoning the § Program Design
   already gives for omitting the `_ok` flag on the field itself.

   The gate cannot check that `artifact_output.from` names a *directory* — that is
   not knowable statically. That case is the runtime gate's (see § Failure-mode
   dispositions).
2. **Runtime gate (`promote_run_artifact`)** — verify the promoted directory
   actually loads **and renders**. This is **not** an extension of the
   static-validation family; it is a `load_manifest()` + `find_template_body()` +
   `validate_top_level_data()` + `render_template()` call at promotion time, and
   all four already exist and fail closed.

   The render step is load-bearing, not belt-and-braces: the three loaders never
   parse the Jinja body, so a `template.html.j2` with a syntax error — or an
   undefined-name mismatch between the body and `data.json` — passes a
   loaders-only gate, lands under `templates_dir`, and then fails at
   `ll-artifact render`, defeating the "accepted directly by render" contract.
   `render_template()` (`artifact_templates.py:319`) is pure, LLM-free, and
   cheap, and raises exactly the two exception types the gate already catches
   (`ManifestError` for a malformed body, `DataValidationError` for the
   StrictUndefined backstop). Discard the rendered string — the gate cares that
   the render *succeeds*, not what it produces.

Consequence: **nothing needs splicing into `cli/loop/config_cmds.py::cmd_validate()`
for the shape check.** FEAT-3309's wiring pass flagged that as the hardest
integration point on the assumption the shape check was static; it isn't.

### Failure-mode dispositions

- Failure terminal → no output expected; promotion and both gates are a no-op.
- Non-failure terminal missing/malformed shape → a real defect. Surface the
  loader's error text and mark the run's promotion as failed **without** changing
  the run's exit status (matching FEAT-3309's best-effort promotion contract).

  **Catch `ManifestError` *and* `DataValidationError`.** They are siblings, not
  a subclass pair — both derive from `ValueError` directly
  (`artifact_templates.py:35,39`). `load_manifest()` / `find_template_body()`
  raise `ManifestError`; `load_data()` and `validate_top_level_data()` raise
  `DataValidationError` (unparseable JSON, a reserved top-level `ll` key,
  a payload that fails `manifest.data_schema`). Catching only `ManifestError`
  lets the single most likely defect — a malformed `data.json` from a
  generating loop — escape the gate into the outer blanket handler, producing a
  generic "promotion failed" with none of the diagnostic text. Catch
  `(ManifestError, DataValidationError)` and log `str(exc)`.
- `artifact_mode: template` but `artifact_output.from` resolves to a **file** →
  reject at the runtime gate with an explicit "template mode requires a directory"
  message. Do not rely on `load_manifest()` to catch it: handed a file path it
  fails on a path that does not exist rather than on the actual mistake, and the
  resulting `ManifestError` text is misleading.
- Effective mode outside `{"file", "template"}` — reachable only via the context
  var, since the field is a `Literal` — → log an explicit warning naming the bad
  value and skip promotion. Do **not** silently fall back to `"file"`:
  `--context artifact_mode=tmeplate` would then produce a normal-looking
  file-mode run with no signal that template mode never engaged.

### Validate before promoting, not after

The runtime gate runs on the **staged temp directory**, before the `promote()`
swap — not on the promoted result. Validating after the swap means a malformed
`.llat/` has already landed in `templates_dir`, where it pollutes
`resolve_template()` name resolution and `ll-artifact status` discovery even
though promotion is then reported as failed. Load-then-swap keeps a rejected
shape entirely out of the destination.

### Directory promotion — reuse `templatize.promote()`, but wrap it

FEAT-3309 promotes a single file. This promotes a directory, which needs atomicity.
`cli/artifact/templatize.py:585-608` already implements the atomic swap:
`promote(tmp_dir, out_dir, force)` — backup/restore + rollback on failure. Reuse it
rather than reimplementing; no shared-module lift is needed (see § Codebase Research
Findings on import direction).

**It is not drop-in, and three mismatches with FEAT-3309's promotion contract must
be handled by the caller:**

1. **`promote()` MOVES.** `os.replace(tmp_dir, out_dir)` (`:601`) relocates the
   source. File mode uses `shutil.copy2` (`persistence.py:779`) and leaves the run's
   deliverable in `run_dir` intact. Template mode must not silently strip a finished
   run of its own output. → `shutil.copytree` the declared source into a sibling
   temp dir under the *destination* parent first, then `promote(tmp, dest, ...)`.
   **Name that temp dir `f"{dest.name}.tmp-{os.getpid()}"`**, not an arbitrary
   `mkdtemp` name: it is the name a same-pid retry and `cmd_templatize`'s own
   `_sweep_stale_siblings` know how to reclaim (both key off the
   `{out_dir.name}.tmp-` / `{out_dir.name}.bak-` prefixes), so any other name
   leaks a full directory copy on a crash between copytree and swap.
2. **`promote()` raises.** `SpliceError` when the destination exists and
   `force=False` (`:591`). `promote_run_artifact` is documented as never raising and
   never failing the run. → call with `force=True` and wrap the whole block in the
   same `except OSError`/`except Exception` → log-and-return-`None` handling the
   file path already uses.
3. **`os.replace` raises EXDEV across filesystems.** Live whenever a fixed `to:` or
   a configured `promotion_dir` points off-device. Staging the temp dir under the
   destination parent (per 1) makes the final `os.replace` same-device by
   construction, which removes this.

Also: `_sweep_stale_siblings` (`:574`) is **not** inside `promote()` — `cmd_templatize`
calls it separately at `:812`. Call it explicitly before promoting, or `.tmp-`/`.bak-`
leftovers from a crashed promotion accumulate in `promotion_dir`.

**But do not call it unmodified — the stable destination makes it a race.**
`_sweep_stale_siblings` rmtree's *every* `{dest.name}.tmp-*` and
`{dest.name}.bak-*` sibling, and under a stable per-loop destination two
concurrent runs of the same loop share `dest.name`. `ll-parallel`, `ll-sprint`,
or simply two terminals then collide: run A's sweep deletes run B's in-flight
`copytree` target out from under it, and B's promotion dies mid-copy. This
hazard did not exist under FEAT-3309's run-stamped names, where `dest.name`
differed per run — it is introduced by the stable-name decision below and must
be paid for here.

Disposition: **do not call `_sweep_stale_siblings(dest)`.** Before `copytree`,
remove only *our own* `{dest.name}.tmp-{os.getpid()}` (a leftover from a prior
crash by a recycled pid). Reclaiming another process's leftovers is not worth
destroying a live one's staging directory; a crashed run leaks one directory
that the next same-pid run or `cmd_templatize`'s own sweep reclaims.
(`promote()`'s internal `.bak-{pid}` collision is benign by comparison — the
worst case is last-writer-wins on `dest`, with no partial state.)

### Default destination — `<templates_dir>/{loop_name}.llat/`, stable per loop

FEAT-3309's `promotion_dir` (`.loops/artifacts`) is the wrong default here.
`resolve_template()` (`artifact_templates.py:67-82`) resolves a template *by name*
only under `config.artifacts.templates_dir` (`artifacts/templates`); it is
path-first, so a `.llat/` anywhere is renderable by full path, but only one under
`templates_dir` is renderable as `ll-artifact render <name>`. A directory whose
entire purpose is reuse should land where reuse-by-name works.

Default: **`<templates_dir>/{loop_name}.llat/`**. An explicit `artifact_output.to`
overrides as usual. Note this makes template mode's default destination key
*differ* from file mode's — deliberate, and worth one line in the
`artifact_output` docstring.

**Anchor `templates_dir` to `config.project_root`, not to the cwd.** The
default value is the *relative* `"artifacts/templates"`
(`config/features.py:391`), and `promote_run_artifact` already draws the
distinction for file mode: a loop-authored `to:` is honoured relative to the
invocation cwd, while the project-level config default `promotion_dir` is
anchored to `config.project_root` (`persistence.py` docstring, `:771-773`).
`templates_dir` is the same kind of value and gets the same treatment.
Skipping this puts the template wherever the run happened to be launched from
— and out of reach of `resolve_template()`, which is handed the
project-root-anchored `templates_dir`.

**An explicit `to:` is honoured verbatim — `.llat` is never appended to it.**
Only the *default* destination synthesizes the suffix. Appending to an
author's explicit path would silently rewrite a value they chose, and
`resolve_template()` is path-first, so a non-`.llat` destination still renders
by full path — it just cannot be named. That trade-off is the author's to
make, but it is also the exact failure this section exists to prevent, so the
static gate WARNs when a template-capable loop sets a `to:` not ending in
`.llat` (see § Two gates, gate 1).

**Deliberately *not* run-stamped** (`{run_id}-{loop_name}.llat`), unlike file
mode's `{run_id}-{fsm.name}{suffix}` (`persistence.py:777`). A unique name per run
breaks four things at once:

- `templates_dir` is project-visible (`artifacts/templates`), not the gitignored
  `.loops/` tree `promotion_dir` lives in — a new directory per run accumulates
  unboundedly in tracked space.
- `ll-artifact status` discovers every `*.llat` under `templates_dir`
  (`status.py:102-107`); run-stamped siblings flood it.
- Cheap refresh — re-render against an updated `data.json`, the epic's whole
  premise — needs a stable name. A fresh name each run orphans the previous one.
- It makes the atomic-swap machinery dead code: the destination never pre-exists,
  so `force=True`, `promote()`'s backup/restore, and `_sweep_stale_siblings` are
  all unreachable. `_sweep_stale_siblings` matches only `{dest.name}.tmp-`/`.bak-`
  prefixes, and `dest.name` would differ every run.

A stable name makes all of that load-bearing, and matches `templatize`'s own
`templates_dir / f"{stem}.llat"` (`templatize.py:769`). Overwriting the previous
run's template is the intended behavior — the run's own copy survives in
`run_dir`, and `promote()`'s backup/rollback covers a mid-swap failure.

**Overwriting someone *else's* template of the same name is not intended, and
needs a guard.** `templatize` writes to `templates_dir/{stem}.llat` from the
same namespace, so a hand-authored or `templatize`-derived
`artifacts/templates/html-anything.llat` is indistinguishable, by path, from a
prior promotion — and `force=True` (required by § Directory promotion item 2)
destroys it without a word. This is the one destructive edge in an otherwise
best-effort, never-fails path, and it lands in *tracked* project space.

Guard, cheaply — via a **new optional `produced_by` manifest key, not `source`**.
The 3rd-pass proposal stamped the producing loop into the existing `source` key,
but that repurposes a field with settled, different semantics: `load_manifest`
requires `source` to be a non-empty *string* (`artifact_templates.py:178-180`),
and `templatize` records the **source document path** there
(`templatize.py:535,883-888`; the `--source` help text says "recorded into
manifest.source"). A template-mode loop would naturally emit its input-document
path in `source` — overwriting it destroys loop-emitted provenance, and worse,
makes the mismatch comparison noisy: the same loop promoting over its own prior
output with a *different input document* would trip a spurious "foreign source"
warning, indistinguishable from the genuinely foreign-template case the guard
exists for. Instead: add `produced_by` to `_MANIFEST_OPTIONAL_KEYS`
(`artifact_templates.py:26`) with the same non-empty-string validation shape as
`source` (one line each in code this repo owns), stamp it with the producing
loop's name at promotion time, and leave `source` untouched.

**Stamp on the staged temp, before the runtime gate runs** — so the stamped
manifest is exactly what `load_manifest()` validates (a stamp that somehow
violates the manifest contract fails loudly at the gate instead of landing),
and what the destination carries for the *next* promotion's comparison.
Stamping implies a YAML re-dump of the loop-emitted `manifest.yaml`; formatting
churn (key order, comments) is acceptable — the file is machine-consumed only.

Comparison: before swapping, if the destination already exists, load its
manifest and compare `produced_by`. On a mismatch — or an unreadable/absent
`produced_by` (which covers every hand-authored or `templatize`-created
template, since neither writes the key) — log a WARNING naming both the
destination and the foreign producer (or its absence) before proceeding.
Proceed rather than refuse: refusing would make a promoting loop
permanently wedged behind a stale directory with no in-band way to clear it,
and `promote()`'s backup is deleted only after a successful swap. The
requirement is that the clobber is *never silent*, not that it is impossible.

Suffix: always append `.llat`; do **not** derive it from the source the way file
mode does. A loop that writes a plain `template/` directory has no suffix and
would promote to a directory `resolve_template` cannot find by name.

`manifest.name` is left untouched by promotion. `ll-artifact render <name>` keys
on the *directory* name; the manifest's `name` is metadata and the two need not
agree. Worth one line in the `artifact_output` docstring so the divergence isn't
read as a bug.

**Emitting a lockfile is out of scope; *inheriting a stale one* is not.**
`ll-artifact status` only discovers `.llat` dirs that have a lockfile sibling
(`status.py:103-107`), so a promoted template is invisible to `status` until
someone runs a command that writes one. Emitting a lockfile at promotion time
is a follow-up, not an AC here.

The sibling case is different and does belong here. `lock_path_for` returns
`root.parent / f"{root.name}.lock"` (`cli/artifact/lockfile.py:26-28`) — the
lockfile lives *outside* the `.llat/` directory, so `promote()`'s swap replaces
the template and leaves the lock untouched. A promotion over a previously
`templatize`d or rendered template therefore inherits a lockfile describing the
*old* template's renders, and `status` will classify the new one against it —
reporting FRESH/STALE on evidence that no longer applies. Delete the sibling
lockfile as part of a successful promotion (`lock_path_for(dest).unlink(
missing_ok=True)`, after the swap): NO-LOCK is honest and self-correcting,
a stale lock is neither.

### Mode selection — a context var, not a per-file constant

`artifact_mode` on `FSMLoop` is static: one value per YAML. That is enough for the
schema and both gates, but it does **not** by itself let a single `html-anything.yaml`
run in either mode, and the generate prompt is static text that has to branch on the
mode somehow.

Resolution: `html-anything` declares `artifact_mode` as a **`context:` var**
(alongside `pass_threshold` / `design_tokens_context`), and `promote_run_artifact`
reads the effective mode from `fsm.context` with the top-level field as the default.
Per-run selection then works through the *existing* `ll-loop run --context
artifact_mode=template` (`cli/loop/__init__.py:294`) with no new CLI flag, and the
generate prompt branches by interpolating the same var.

Rejected: a new `--artifact-mode` run flag (duplicates `--context` for one field);
shipping a second `html-anything-template.yaml` (doubles maintenance of a 220-line
loop to vary one prompt block).

Verified (4th pass): `--context KEY=VALUE` merges into `fsm.context`
unconditionally at `cli/loop/run.py:184-188`, *before* run-time validation — so
`ll-loop run --context artifact_mode=template` on a loop with no
`artifact_output` trips the static gate at run time too, even when the YAML
never declares the key. Desirable; worth one test line, no spec change.

### Generate-prompt variant — pilot one loop, and split it out

FEAT-3309 said "the generate prompts in the HTML loop family gain a variant" with no
bound; that is nine loops and no criterion for which get it or how a loop selects
the variant. **Pilot `html-anything` only** (it matches the epic's motivating use
case). Rolling the variant out to the remaining eight is a follow-up, scoped once
the pilot proves the prompt actually produces a loadable template reliably.

**The pilot should be its own issue, not step 5 of this one.** Steps 1–4 are the
plumbing: fully specified, mechanically testable, Medium effort, Low risk, and
verifiable end-to-end against a hand-written `.llat/` fixture with no LLM in the
loop. Step 5 is a prompt rewrite whose reliability is unproven, and it is the sole
driver of this issue's Large/Medium-risk rating. Fusing them makes the two sets of
acceptance criteria untestable in isolation — the same argument that split this
issue out of FEAT-3309.

Done: steps 1–6 + the round-trip test stay here (Medium / Low risk); the
`html-anything` prompt variant is **FEAT-3320**, a child of EPIC-3299 depending on
this issue. FEAT-3320 also carries the finding that surfaced while scoping it — the
oracle's screenshot/rubric cycle has nothing to screenshot in template mode, so the
pilot needs a per-iteration `ll-artifact render` rather than just a prompt rewrite.

## Use Case

A user runs `html-anything` in `artifact_mode: template` over an architecture
document. The run produces a `.llat/` directory that `ll-artifact render` consumes
directly — regenerating the artifact against updated `data.json` costs no LLM call
and no `templatize` round trip.

## Program Design

### Types

- `FSMLoop.artifact_mode: Literal["file", "template"] = "file"`

Defaults to `"file"` — today's behavior. No paired `_ok` suppression flag, for the
same reason as `artifact_output` (see FEAT-3309 § Program Design): the
`tamper_guard_ok` convention is for dismissable lint warnings, not behavior
declarations.

### Signatures

- `_validate_artifact_mode_deliverable(fsm: FSMLoop) -> list[ValidationError]` — the
  static gate; registered by an `errors.extend(...)` **call site in
  `validate_fsm()`** (`structural_rules.py:910+`), which is what makes a rule run.
  Adding it to `fsm/validation/__init__.py`'s `__all__` is optional and only
  affects direct import access from tests / cross-module callers.
  (`ValidationError` from `fsm/validation/_base.py` — there is no `Violation` type
  in this codebase; every rule returns `list[ValidationError]`.)
- `_effective_artifact_mode(fsm: FSMLoop) -> str` — `fsm.context.get("artifact_mode",
  fsm.artifact_mode)`, shared by the static gate and `promote_run_artifact` so the
  two can never disagree about which mode a run is in.
- `_is_template_capable(fsm: FSMLoop) -> bool` — `_effective_artifact_mode(fsm) ==
  "template" or "artifact_mode" in fsm.context`. What the *static* gate keys off;
  `promote_run_artifact` keys off `_effective_artifact_mode` alone, since at
  runtime the mode has an actual value. Splitting the two is the point: validation
  asks "can this loop ever run in template mode?", promotion asks "is it in
  template mode right now?"
- `promote_run_artifact(...)` — extended (from FEAT-3309) to branch on the effective
  `artifact_mode` (context var, falling back to the field) and run the runtime gate

### Call Path

`PersistentExecutor.run()` (`persistence.py:1103-1118`) -> `promote_run_artifact`
(`persistence.py:727-786`) -> `shutil.copytree` to a sibling temp under the
destination parent -> stamp `manifest.produced_by` on the temp ->
`load_manifest`/`find_template_body`/`validate_top_level_data`/`render_template`
(the runtime gate, on the temp) -> `produced_by` clobber comparison ->
`templatize.promote()` -> unlink sibling lockfile ->
`fsm.context["promoted_artifact"]` (the key `_helpers.py:1899` already reads)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- The `_validate_artifact_mode_deliverable(fsm: FSMLoop) -> list[Violation]` signature above cites a `Violation` return type that does not exist anywhere in this codebase. Every validation rule returns `list[ValidationError]` (`fsm/validation/_base.py`) — e.g. `_validate_tamper_guard(fsm: FSMLoop) -> list[ValidationError]` (`evaluator_rules.py:378`). The new function's signature should be `-> list[ValidationError]`.
- `promote_run_artifact` is already fully landed on this branch (not merely proposed by FEAT-3309): defined at `fsm/persistence.py:727-786`, called from `PersistentExecutor.run()` at `persistence.py:1103-1118`. It stashes the promoted path as `fsm.context["promoted_artifact"]` — not `fsm.context["promoted"]` as the Call Path above states.
- Three existing, disagreeing conventions for a restricted-choice `FSMLoop` field, any of which `artifact_mode` could follow: `on_handoff: Literal["pause","spawn","terminate"]` (`schema.py:1401`) has no runtime validator at all; `tamper_guard: str | None` has a dedicated registered validator plus a WARNING severity and a suppression flag (`evaluator_rules.py:378-419`); `visibility: str` is checked inline against a frozenset inside `load_and_validate()` (`structural_rules.py:1725-1737`), also WARNING-only with no suppression flag. **Settled** in § Two gates, gate 1: ERROR, no suppression flag — none of the three precedents applies, because this is a behavior declaration that cannot work as written rather than a dismissable lint opinion.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `artifact_mode` field beside `artifact_output`: `ArtifactOutput` dataclass at `:1308-1356`, `FSMLoop.artifact_output` field at `:1446`, serialize in `to_dict()` at `:1583-1584`, parse in `from_dict()` at `:1710-1714`
- `scripts/little_loops/fsm/validation/_base.py:116` — register `artifact_mode` in `KNOWN_TOP_LEVEL_KEYS` (`_base.py:81-144`), alongside the existing `artifact_output` entry
- `scripts/little_loops/fsm/validation/structural_rules.py:910+` — `validate_fsm()`; **the registration point**: add an `errors.extend(_validate_artifact_mode_deliverable(fsm))` call beside the existing `_validate_parameters` / `_validate_targets` extends (`:948,951`). This, not `__all__`, is what makes the rule run
- `scripts/little_loops/fsm/validation/__init__.py:44-267` — per-symbol re-export list for test access and cross-module callers (`fsm/executor.py`/`fsm/persistence.py`/`fsm/route_table.py`). Optional for this rule, which has no such caller — cf. `_validate_artifact_output_subloop_reachability`, absent from `__all__` and still live
- `scripts/little_loops/fsm/validation/reachability.py:104-141` — `_validate_artifact_output_subloop_reachability`, the existing `artifact_output` rule and the closest precedent for the new gate's shape, severity choice, and registration style (invoked from `structural_rules.py:1757`)
- `scripts/little_loops/fsm/validation/` — the new static gate (rule module TBD by category)
- `scripts/little_loops/fsm/persistence.py:727-786` — `promote_run_artifact`, already landed (from FEAT-3309), called from `PersistentExecutor.run()` at `:1103-1118`; branch it on `artifact_mode` for directory promotion, calling `cli/artifact/templatize.py`'s `promote()` via a function-local import (no shared-module lift needed — see `cli/artifact/templatize.py:574-605` below)
- `scripts/little_loops/artifact_templates.py:25-26` — add `produced_by` to `_MANIFEST_OPTIONAL_KEYS` + a non-empty-string check in `load_manifest()` mirroring `source` (`:178-180`)
- `scripts/little_loops/loops/html-anything.yaml` — the pilot generate-prompt variant

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation/structural_rules.py:30` — imports `KNOWN_TOP_LEVEL_KEYS`
- `scripts/little_loops/cli/artifact/render.py:72` — `cmd_render`; the consumer that must accept the output with no `templatize` step. It resolves via `resolve_template()` (`artifact_templates.py:67-82`), which is path-first but resolves *by name* only under `templates_dir` — the reason for the destination-directory decision above.
- `scripts/little_loops/config/features.py:391,393` — `templates_dir` (`artifacts/templates`) vs `promotion_dir` (`.loops/artifacts`); template mode defaults to the former
- `scripts/little_loops/cli/loop/_helpers.py:1899-1901` — prints `Promoted artifact: <relativized path>` from `fsm.context["promoted_artifact"]`. Verified to need **no change**: it stringifies and relativizes whatever path it is handed, so a directory prints correctly. Listed for awareness only — deliberately not an AC
- `scripts/little_loops/cli/artifact/lockfile.py:26-28` — `lock_path_for`; the sibling `{name}.llat.lock` that survives a `promote()` swap and must be unlinked on a successful promotion (see § Default destination)

### Similar Patterns
- `cli/artifact/templatize.py:893-927` — writes `template.{suffix}.j2` + `data.json` + `manifest.yaml` into a temp dir then promotes; the exact output shape a `template`-mode loop must produce
- `fsm/validation/structural_rules.py:load_and_validate()` (~1713-1723) — the unknown-top-level-key WARNING, gated by `KNOWN_TOP_LEVEL_KEYS`; this, not `meta_rules.py`'s `_validate_artifact_overwrite` (MR-5, `:268-355`, which never scans the top-level key set), is the check a new `artifact_mode` value must not trip

### Tests
- `scripts/tests/test_fsm_schema.py:3788+` — `artifact_mode` field coverage
- `scripts/tests/test_fsm_validation_meta_rules.py:843-860` — pattern for confirming `artifact_mode` doesn't trip the "Unknown top-level" warning
- `scripts/tests/test_fsm_validation_structural.py` — 30+ existing `test_*_rejected` methods already exercise the "validator rejects a bad config" shape (e.g. `test_unknown_type_rejected` `:500-505`, `test_non_positive_exit_code_is_rejected` `:1463-1483`); the new `artifact_mode` rejection test should follow this existing pattern, not invent a new one.
- `scripts/tests/test_fsm_persistence.py:1326-1342,1430+` — E2E templates for the runtime gate; also the home for the promotion-edge tests: a bad `data.json` (all three `DataValidationError` shapes), a Jinja-syntax-error and an undefined-name body (the render-check cases), a pre-existing foreign-`produced_by` destination plus a same-loop re-promotion with a changed `source` (must not warn), a stale sibling lockfile, a relative `templates_dir` under a non-cwd `project_root`, and a simulated concurrent `{dest.name}.tmp-<other-pid>` sibling that must survive promotion
- Round-trip test: a `template`-mode run's output feeds `ll-artifact render` and produces the expected artifact with no `templatize` invocation
- `scripts/tests/test_builtin_loops.py` — conformance for `html-anything.yaml`

### Documentation
- `docs/reference/API.md:5520-5573` — hand-maintained `FSMLoop` field reproduction; add `artifact_mode`
- `docs/reference/API.md:6312` and `docs/reference/CLI.md:870` — MR-rule prose lives in **two** near-duplicate places with no shared source; both need updating **only if** the static gate is framed as a new numbered MR rule (recommend: don't — it is an ordinary validation rule, not a meta-rule)
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop header fields

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- Corrected `schema.py` anchors for the `artifact_output` pattern (superseding the `:1498`/`:1624` anchors above, which are stale): `ArtifactOutput` dataclass at `schema.py:1308-1356`, `FSMLoop.artifact_output` field at `schema.py:1446`, serialize in `to_dict()` at `schema.py:1583-1584`, parse in `from_dict()` at `schema.py:1710-1714`.
- `KNOWN_TOP_LEVEL_KEYS` spans `_base.py:81-144`; the existing `artifact_output` entry is at line 116 (not `:113`).
- `meta_rules.py:268-355` (`_validate_artifact_overwrite`, MR-5) does not scan the top-level key set at all — it only reads `fsm.artifact_versioning`/`fsm.artifact_versioning_ok`/`fsm.category`/`fsm.states`. It cannot be "confused" by a new field; the check that actually matters for an unrecognized `artifact_mode` value is the unknown-top-level-key WARNING in `structural_rules.py:load_and_validate()` (~1713-1723), gated by `KNOWN_TOP_LEVEL_KEYS`.
- Tests: contrary to "no precedent exists," `scripts/tests/test_fsm_validation_structural.py` already has 30+ `test_*_rejected` methods exercising exactly this "validator rejects a bad config" shape — e.g. `test_unknown_type_rejected` (500-505), `test_non_positive_exit_code_is_rejected` (1463-1483). The new `artifact_mode` rejection test should follow this existing pattern rather than invent a new test shape.
- Import direction: `cli/artifact/templatize.py` has no `fsm` import at module level, and no import-cycle risk was found for `fsm.persistence -> cli.artifact.templatize`. No lift to a shared module is needed. The existing convention for `fsm/` reaching into `cli/` (`fsm/executor.py:917`, a function-local import of `cli.loop._helpers`) is a deferred/function-local import, not a module-level one — `templatize.promote()` should follow that same convention rather than a top-of-file import.

## Implementation Steps

1. Add `artifact_mode` to `FSMLoop` + `KNOWN_TOP_LEVEL_KEYS`, including `to_dict()`/`from_dict()` round-trip coverage (`test_fsm_schema.py` convention).
2. Add the static gate — a **template-capable** loop (`_is_template_capable`: effective mode is `"template"`, *or* `artifact_mode` appears as a `context:` key at any value) requires `artifact_output is not None` — at ERROR severity with no `_ok` flag, plus the WARNING when its `artifact_output.to` is set and does not end in `.llat`. Register it by an `errors.extend(...)` call site in `validate_fsm()` (`structural_rules.py:910+`). The rejection test must assert `ll-loop validate` actually rejects — not that a symbol appears in `__all__` — and must cover the `context: {artifact_mode: file}` shape, which is what `html-anything` will actually declare.
3. Branch `promote_run_artifact` (`fsm/persistence.py:727-786`) on the effective `artifact_mode` for directory promotion: unlink our own stale `{dest.name}.tmp-{os.getpid()}` (**not** `_sweep_stale_siblings(dest)` — it would rmtree a concurrent run's live staging dir) → `shutil.copytree` to `{dest.name}.tmp-{os.getpid()}` under the destination parent → stamp `manifest.produced_by` on the temp → runtime gate on the temp (step 5) → foreign-`produced_by` clobber WARNING if `dest` exists → `templatize.promote(..., force=True)` → `lock_path_for(dest).unlink(missing_ok=True)`, the whole block wrapped so it degrades to a logged warning. `templatize` imported function-locally (following `fsm/executor.py:917`'s convention for `fsm/` reaching into `cli/`; no shared-module lift needed). An effective mode outside `{"file","template"}` logs a warning naming the value and skips promotion.
4. Default the destination to `<templates_dir>/{loop_name}.llat/` — stable per loop, not run-stamped — always appending `.llat` rather than deriving it from `source.suffix`, with `templates_dir` anchored to `config.project_root` when relative (it is, by default). An explicit `artifact_output.to` is honoured verbatim; no suffix is appended to it. Add `produced_by` to `_MANIFEST_OPTIONAL_KEYS` (+ non-empty-string validation, mirroring `source`) and stamp it with the producing loop **on the staged temp, before the runtime gate** — never repurpose `source`, which carries the source-document path (see § Default destination). 
5. Add the runtime gate via `load_manifest`/`find_template_body`/`validate_top_level_data` **plus a discarded `render_template()` call** (a loaders-only gate passes a Jinja syntax error or an undefined-name mismatch that then fails at `ll-artifact render`), run **on the staged temp, after the `produced_by` stamp and before the swap**, catching `(ManifestError, DataValidationError)` — both, they are sibling `ValueError` subclasses — plus the explicit source-is-a-file rejection, with the non-failing-the-run disposition.
6. Round-trip test through `ll-artifact render` against a hand-written `.llat/` fixture (no LLM); docs.
7. *(Split out to **FEAT-3320**)* the `html-anything` template-emitting generate-prompt variant, selected by the `artifact_mode` context var. Not in scope here.

## Acceptance Criteria

- [ ] `ll-loop validate` rejects, at ERROR severity, a loop declaring `artifact_mode: template` with no `artifact_output` block. The test asserts the *rejection* (via `load_and_validate` / `ll-loop validate` exit status), not that a symbol appears in `__all__`. No `artifact_mode_ok` suppression flag exists.
- [ ] That rejection also fires when the mode is declared as a `context:` var rather than the top-level field — for **both** `context: {artifact_mode: template}` and `context: {artifact_mode: file}`. The latter is the shape `html-anything` will actually ship (default-unchanged, flipped per-run by `--context`), and a gate keyed only on the effective *value* is blind to it.
- [ ] A template-capable loop whose `artifact_output.to` does not end in `.llat` produces a WARNING (not an ERROR) naming the destination — it renders by path but cannot be resolved by bare name.
- [ ] An effective `artifact_mode` outside `{"file","template"}` (reachable only via `--context`) logs a warning naming the bad value and skips promotion, rather than silently degrading to a normal-looking file-mode run.
- [ ] A `template`-mode loop's promoted directory contains `manifest.yaml`, exactly one `template.*.j2`, and a `data.json` valid against `manifest.data_schema` — verified by the existing `artifact_templates.py` loaders, not by a reimplementation, and verified **on the staged temp before the swap**, so a malformed shape never lands under `templates_dir`.
- [ ] The runtime gate also proves the template **renders**: a `template.*.j2` with a Jinja syntax error, or an undefined-name mismatch against `data.json`, fails the gate at promotion time (via a discarded `render_template()` call) rather than landing under `templates_dir` and failing later at `ll-artifact render`.
- [ ] The promoted directory is accepted directly by `ll-artifact render` with no `templatize` step, **resolvable by bare name** (i.e. it lands under `artifacts.templates_dir` — anchored to `config.project_root`, so the destination is independent of the invocation cwd — and is suffixed `.llat`), not only by full path. The default name is stable per loop (`{loop_name}.llat`), so a second run of the same loop overwrites rather than accumulating a new run-stamped directory.
- [ ] A malformed/missing shape on a non-failure terminal surfaces the loader's error text and marks promotion failed **without** changing the run's exit status; a failure terminal is a silent no-op. `artifact_output.from` resolving to a file (not a directory) under `template` mode produces an explicit "requires a directory" message, not a misleading `ManifestError`.
- [ ] The gate reports the diagnostic text for a bad **`data.json`** — unparseable JSON, a reserved top-level `ll` key, and a `manifest.data_schema` mismatch — not just for a bad `manifest.yaml`. (`DataValidationError` is a sibling of `ManifestError`, not a subclass; catching only the latter drops all three.)
- [ ] Directory promotion is atomic (temp + rollback), reusing `templatize.promote()` rather than a second implementation — and **the declared source survives in `run_dir`** (promotion copies; `promote()`'s bare `os.replace` would move it). A second run over an existing destination overwrites it via the backup/restore path, and a crash between `copytree` and the swap leaves only a `{dest.name}.tmp-<pid>` sibling, reclaimed by the next same-pid promotion.
- [ ] Two concurrent promotions of the same loop to the same stable destination do not destroy each other's staging directory: the outcome is last-writer-wins on `dest`, never a half-copied template or a promotion that dies mid-`copytree`. (Specifically: `_sweep_stale_siblings(dest)` is **not** called — its prefix match would rmtree the other run's live `{dest.name}.tmp-<pid>`.)
- [ ] Promotion stamps `manifest.produced_by` (a new `_MANIFEST_OPTIONAL_KEYS` entry with `source`-style non-empty-string validation) with the producing loop, on the staged temp **before** the runtime gate — so the stamped manifest is what gets validated — and leaves `manifest.source` untouched (it carries the source-document path, `templatize`'s settled semantics). Promoting over a destination whose `produced_by` differs or is absent — a hand-authored or `templatize`-created template of the same name — logs a WARNING naming both before proceeding; a re-promotion by the same loop over its own prior output (even with a different input document in `source`) does **not** warn. The clobber may happen; it is never silent. A successful promotion also unlinks the sibling `{dest.name}.lock`, so `ll-artifact status` reports NO-LOCK rather than classifying the new template against the old one's render records.
- [ ] `promote_run_artifact` still never raises and never changes the run's exit status in `template` mode, including when the destination already exists (`promote()` raises `SpliceError` unless `force=True`) and when the destination is on another filesystem.
- [ ] `artifact_mode` survives a `to_dict()`/`from_dict()` round-trip and does not trip the unknown-top-level-key WARNING in `structural_rules.py::load_and_validate()`.
- [ ] `artifact_mode` defaults to `"file"`; every loop that declares nothing behaves exactly as today, and the `artifact_versioning_ok` MR-5 tests stay green.
- [ ] *(Split out to **FEAT-3320** — not an AC of this issue)* `html-anything` runs in both `file` (default, unchanged) and `template` mode, selected per-run via the existing `ll-loop run --context artifact_mode=template`.

## Impact

- **Priority**: P2 — the lossless half of the epic's fan-out story; without it, every loop→template route runs through a lossy LLM extraction.
- **Effort**: Medium — new field, two gates in two subsystems, a copytree+promote wrapper, and a round-trip test. No shared-module lift is needed (retracted by the import-direction finding), and the prompt rewrite is split out per § Generate-prompt variant. Large if the pilot stays in scope.
- **Risk**: Low as scoped (steps 1–4 are deterministic and fixture-testable end to end, and the default is unchanged). Medium if the generate-prompt pilot stays in scope — its reliability is unproven until it runs.
- **Breaking Change**: No — `artifact_mode` defaults to `"file"`.

## Related Key Documentation

- `.issues/features/P2-FEAT-3309-loop-to-artifact-handoff-promote-a-run-artifact-to-a-durable-path.md` — Part A; supplies `promote_run_artifact`, `artifact_output`, and `promotion_dir`
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design principle 1
- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — the lossy fallback path (**done**)

## Status

**Open** | Created: 2026-08-24 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-08-25T17:29:12 - `f8fad891-fb12-4a0c-8abb-8d32e08edbbf.jsonl`
- Pre-implementation review (4th pass) - 2026-08-25 - re-verified all load-bearing claims against code (all held); replaced the `manifest.source` clobber-guard stamp with a new `produced_by` optional manifest key after finding `source` already carries the source-document path per `templatize`'s settled semantics (repurposing it destroys loop-emitted provenance and makes same-loop/different-input re-promotions warn spuriously); widened the runtime gate with a discarded `render_template()` call (loaders alone pass a Jinja syntax error or undefined-name mismatch that then fails at `ll-artifact render`); pinned stamp ordering (staged temp, before the gate, so the stamped manifest is what's validated); confirmed `--context` merges before run-time validation so the static gate also fires at `ll-loop run` time.
- `/ll:confidence-check` - 2026-08-25T17:20:32 - `3e64b7dd-cbc1-426d-840e-8059b3a2dfd1.jsonl`
- Pre-implementation review (3rd pass) - 2026-08-25 - closed the static gate's remaining blind spot (it must key on template-*capability* — `artifact_mode` present as a `context:` key at any value — not on the effective value, since `html-anything` will ship `context: {artifact_mode: file}`); replaced `_sweep_stale_siblings(dest)` with a self-pid-only unlink after finding its prefix match rmtrees a concurrent same-loop run's live staging dir (a hazard the stable-name decision introduced); added a `manifest.source` clobber guard for overwriting a hand-authored/`templatize`d template of the same name in tracked space; widened the runtime gate to catch `DataValidationError` alongside `ManifestError` (siblings, not a subclass pair — a malformed `data.json` would have escaped); pinned `templates_dir` anchoring to `project_root` and `to:` as honoured verbatim (+ a non-`.llat` WARNING); required unlinking the stale sibling lockfile; verified `_helpers.py`'s promoted-artifact print needs no change; retired the now-settled severity question from the research findings.
- Pre-implementation review (2nd pass) - 2026-08-25 - corrected the rule-registration mechanism (`__all__` is a re-export list, not the registry; `_validate_artifact_output_subloop_reachability` is the live counter-example), closed the static gate's blind spot on `context:`-declared modes, added a disposition for an invalid context value, replaced the run-stamped default destination with a stable `{loop_name}.llat` (four consequences: unbounded growth in tracked space, `ll-artifact status` pollution, no cheap-refresh target, and dead swap/sweep machinery), moved the runtime gate before the swap, pinned the temp-dir name to the sweep's prefix, and ruled lockfile emission out of scope.
- Pre-implementation review - 2026-08-25 - resolved four blockers (promote() moves rather than copies and raises; mode selection via `--context`; default destination `templates_dir` not `promotion_dir`; "declared deliverable" = `artifact_output`), settled the static-gate severity, corrected four stale statements (`Violation`→`ValidationError`, `promoted`→`promoted_artifact`, retracted shared-module lift, `_sweep_stale_siblings` is caller-invoked), and split the `html-anything` prompt variant out of scope.
- `/ll:reconcile-issue` - 2026-08-25T16:16:48 - `c4f85c08-09d9-48a9-8402-4bb54b80d902.jsonl`
- `/ll:refine-issue` - 2026-08-25T16:12:50 - `2e6f3378-789f-46dc-8b61-adf0fc625fd4.jsonl`
- Split out of FEAT-3309 (Part B) - 2026-08-24
