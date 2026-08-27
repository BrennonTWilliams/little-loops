---
id: FEAT-3332
type: FEAT
title: 'check_intent_scope: runtime containment gate asserting workflow-generator writes
  stay under run_dir'
priority: P3
status: open
discovered_by: split-from-BUG-3327
discovered_date: '2026-08-26'
captured_at: '2026-08-26T21:00:00Z'
depends_on: [BUG-3327]
---

# FEAT-3332: check_intent_scope: runtime containment gate asserting workflow-generator writes stay under run_dir

## Summary

`workflow-generator` documents MR-3 artifact-isolation discipline for itself but
enforces none of it at runtime. In run `2026-08-26T171218-workflow-generator`,
`capture_intent` wrote `research/rsi-sources.md` and `research/rsi-oss-projects.md`
**outside** `${context.run_dir}` and nothing noticed.

BUG-3327 fixes the *cause* of that specific incident (an unfenced brief that read
as live instructions). This issue adds the *guard*: a `check_intent_scope` state
that fails the run if the changed-file set since `init` is not a subset of
`${captured.run_dir.output}`.

**Split from BUG-3327 on 2026-08-26.** Rationale: the fence is the actual fix —
additive, low-risk, one prompt edit per site. This gate is a new state, two `init`
baselines, repo-root relativization, two escape paths, and nine behavioral test
cases. It is defense-in-depth against regressions, and bundling it was the single
largest driver of BUG-3327's 63/100 outcome confidence. Land the fence first, then
this with its own budget.

## Current Behavior

`validate_intent` performs zero file-scope checking — its `python3 -c` body only
asserts `intent.yaml` parses with non-empty `name`/`goal`/`steps`/`success_signal`.

The loop's `scope:` block (`workflow-generator.yaml:29-31`) is unrelated to runtime
enforcement: it is consumed only by `resolve_scope()` in `run.py` to acquire
concurrency locks for parallel runs, not to audit what a prompt-driven state
actually wrote to disk.

The closest existing static check, MR-3 `_validate_artifact_isolation` in
`meta_rules.py`, only scans literal `action:` YAML text for hardcoded `.loops/tmp/`
writes at `ll-loop validate` time — it cannot see runtime writes an LLM agent
improvises (like the incident's `research/*.md` files), since those paths never
appear in the YAML source.

## Expected Behavior

Pipeline becomes `capture_intent -> validate_intent -> check_intent_scope ->
sketch_state_graph`, with `check_intent_scope`'s `on_no` going to `diagnose`.

**The containment check must be its own state, not an extra assertion inside
`validate_intent`.** Three reasons, all load-bearing:

1. **A scope violation is not retryable by `capture_intent`.** The out-of-scope
   file has already been written; re-running the prompt cannot unwrite it.
   `validate_intent`'s `on_no` edge is `capture_intent` (line 98) and is
   **unbounded** — no retry counter guards it — so folding the containment check
   in there means every true violation oscillates `capture_intent ->
   validate_intent -> capture_intent` until `max_steps` is exhausted. The gate
   must route a violation to `diagnose`/`failed`, which requires a separate state
   with its own routing keys.
2. **The two checks fail for unrelated reasons.** "intent.yaml is malformed" is
   genuinely retryable by `capture_intent`; "the agent wrote outside its sandbox"
   is not. One state cannot carry two different `on_no` targets.
3. **`validate_intent`'s evaluator shape is pinned.**
   `test_validation_gates_are_exit_code` (`test_builtin_loops.py:17784`)
   parametrizes over `"validate_intent"`. A new sibling state takes its own
   `evaluate: {type: exit_code}` and leaves that test untouched.

**Two limits of this placement, to state rather than silently accept:**

- **The gate is one-shot, at one point in a twelve-state pipeline.** It audits the
  window from `init` through `validate_intent` only. `sketch_state_graph`,
  `attach_evaluators`, `resolve_routing`, `emit_artifact` and `diagnose` are all
  prompt states that run *after* it and are equally capable of writing outside
  `run_dir`. This issue does not make the loop scope-safe; it closes the one
  window where the incident occurred. Say so in the guide entry so the gate is not
  mistaken for whole-pipeline enforcement.
- **`validate_intent`'s `on_no: capture_intent` edge (line 98) remains
  unbounded.** Bounding it is BUG-3327's Implementation Step 5, not this issue's —
  but if BUG-3327 recorded "left alone", pick it up here, since reason (1) above
  makes the unbounded-edge hazard this gate's own justification.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **BUG-3327 has landed** (`status: done`, commit `34c3ecac9`) and changed the exact edge reason (1) above relies on: `validate_intent`'s `on_no` is now `count_intent_retry` (`workflow-generator.yaml:119`), not `capture_intent` — a bounded retry state (default `context.max_intent_retries: "3"`, mirroring the pre-existing `count_emit_retry` pattern) now sits between `validate_intent`'s failure and `capture_intent`. The "unbounded retry" hazard reason (1) describes no longer exists on that edge; reasons (2) and (3) are independent of it and still require `check_intent_scope` to be its own state.
- The "Two limits of this placement" bullet's second point ("if BUG-3327 recorded 'left alone', pick it up here") is resolved — BUG-3327 did not leave the edge unbounded. No residual work from that bullet remains for this issue.

## Proposed Solution

A new `action_type: shell` / `evaluate: exit_code` state between `validate_intent`
and `sketch_state_graph`, with `on_yes: sketch_state_graph` and `on_no: diagnose`.

Five correctness requirements, each of which the naive
`git ls-files -o --exclude-standard` formulation gets wrong:

**(a) Baseline the untracked set at `init`, don't assume a clean tree.** A
developer's working tree routinely holds pre-existing untracked files. Without a
baseline the gate fires on the *first* pass of every run in a dirty repo — and
since the offending files are not the loop's to remove, the failure is permanent.
`init` (lines 43-56) must capture both:

```sh
git rev-parse HEAD > "$DIR/baseline-ref.txt"
git ls-files -o --exclude-standard | LC_ALL=C sort > "$DIR/baseline-untracked.txt"
```

`check_intent_scope` then diffs the *current* untracked set against
`baseline-untracked.txt` (e.g. `comm -13`) and only considers newly-appeared
paths, unioned with `git diff --name-only "$BASELINE_REF" -- .` for modifications
to tracked files.

**(b) Exclude the run dir by explicit pathspec, not by ambient gitignore.** This
repo happens to gitignore `.loops/runs/` (`.gitignore:88`), so `--exclude-standard`
hides `run_dir` here *by accident*. A consuming project without those entries would
see every legitimate run-dir artifact as an out-of-scope write. Exclude
`${captured.run_dir.output}` explicitly, following `general-task.yaml`'s
`final_verify_spin_gate` idiom (`git diff "$BASELINE_REF" -- . ':(exclude).loops/'`).

**(c) Cover untracked *and* tracked changes.** The source incident's `research/*.md`
files were new/untracked, so a tracked-only `git diff --name-only` misses the exact
failure mode this issue targets; conversely an untracked-only check misses an
in-place overwrite of a tracked file. Check both.

**(d) Define the non-repo behavior.** `workflow-generator` can be run outside a git
repo, where `git rev-parse HEAD` fails and there is no baseline to diff against.
Decide and state it: skip the gate with a logged warning (exit 0) is the
recommended default — a hard failure would make the loop unusable outside a repo
for a guard that is defense-in-depth, not the primary fix. BUG-3327's fence is what
actually prevents the behavior; this gate catches regressions.

**(e) Relativize the run dir before comparing — the two path spaces do not match.**
This is the requirement the naive formulation gets wrong most quietly, because it
produces a gate that is *always green*:

- `git ls-files -o` and `git diff --name-only` emit paths **relative to the
  repository root**.
- `${captured.run_dir.output}` is **absolute**. `init`
  (`workflow-generator.yaml:50-53`) deliberately forces it so, via
  `case "$DIR" in /*) echo "$DIR" ;; *) echo "$(pwd)/$DIR" ;; esac` (the BUG-2435
  double-prefix guard).

An `':(exclude)'` pathspec built from the raw absolute value therefore matches
nothing, and every legitimate run-dir artifact reads as an out-of-scope write — or,
if the exclusion is instead applied as a prefix-strip over git's relative output,
the comparison silently never matches and the gate passes everything. Neither
failure announces itself.

Requirements:

1. Compute the repo root once (`git rev-parse --show-toplevel`) and convert
   `${captured.run_dir.output}` to a root-relative path before using it in a
   pathspec. Note `$(pwd)` is not necessarily the repo root — the loop can be
   invoked from a subdirectory, so cwd-relative ≠ repo-relative.
2. Handle the run dir being **outside the worktree entirely** (an absolute
   `--run-dir` elsewhere on disk, or a symlinked path). There is no valid
   root-relative form; git will never report those files at all, so the correct
   behavior is the same skip-with-warning escape as (d) — not a silent pass that
   looks like a green gate.
3. Normalize both sides (resolve symlinks, strip trailing `/`) before the prefix
   comparison. macOS's `/tmp` → `/private/tmp` symlink makes this a live concern
   for the `tmp_path`-based tests, not a theoretical one.

**(f) Escape bash brace-expansions — the FSM interpolates the action string
first.** This gate is the first state in the loop to need real shell variables
(`$(git rev-parse --show-toplevel)`, a repo-root prefix, a relativized run dir).
The FSM's interpolation engine runs over the **entire** action text before
`bash -c` ever sees it, so a bare `${VAR}` is parsed as a namespace reference and
raises `expected namespace.path`. Use `$VAR` or escape as `$${VAR}` —
`common.yaml:459-460` (`$${ID}`) is the in-repo precedent. Note the sketches above
use `"$DIR"` and happen to sidestep this; the real gate will not.

**(g) Step budget.** This state costs +1 per pass. BUG-3327 sets `max_steps: 45`,
which already includes headroom for it; verify that value is in place rather than
re-deriving a number here. If BUG-3327 shipped without the bump, set `45`.

**(h) `loops_dir` is out of the audited window — for now.** The loop's `scope:`
declares `${context.loops_dir}` (`.ll/loops`) alongside `run_dir`, and
`auto_promote` legitimately writes there. That happens at `promote`, long after
this gate runs, so a run-dir-only subset assertion is correct at this point in the
pipeline. If the gate is ever generalized to later states (see the one-shot limit
above), `loops_dir` must be added to the allowed set or promotion reads as a
violation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Additional `$${VAR}` escape precedent sites** beyond `common.yaml:459-460`: `workflow-generator.yaml:607` (`promote` state, `CANDIDATE="$${NAME}-$${SUFFIX}"`), `rn-remediate.yaml` (multiple sites, e.g. `:176`, `:538`, `:542`), `openscad-model-generator.yaml:313`. A second idiom coexists in the codebase: `general-task.yaml`'s `check_provisional_markers`/`final_verify_spin_gate` avoid braces entirely for locals (bare `$VAR`, e.g. `$BASELINE_REF`), sidestepping the escaping question rather than using `$${VAR}`. Both idioms are used elsewhere; neither is marked preferred.
- **Second precedent for repo-root resolution** (requirement 1): `incremental-refactor.yaml:58,159` — `ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT="."` — used for a dirty-tree check and to scope a checkout/clean action to the resolved root rather than `$(pwd)`, with an in-file comment explaining the rationale ("a run launched from a subdirectory can't scope the checkout narrowly").
- **No existing symlink-normalization utility, confirmed independently**: a grep for `realpath|resolve\(|relative_to\(` across `scripts/little_loops/` found only `rn-refine.yaml:93,109` (`realpath "${context.plan_file}" > "$DIR/.source-path"`), which captures a source path rather than resolving symlinks for a containment comparison. `ARCHITECTURE-087` (BUG-2435) governs absolute-path *capture*, not symlink resolution during comparison — requirement (e)(3) must be written fresh, confirming the issue's original claim.
- **Untracked-set content-hash checking is confirmed test-enforced**: `general-task.yaml:424-429`'s `untracked()` + `git hash-object` pattern is backed by `test_untracked_file_content_edit_resets_counter` (`test_builtin_loops.py:3081-3096`), which asserts a name-only untracked listing is insufficient.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — `init` (lines 43-56, add
  both baselines), new `check_intent_scope` state, `validate_intent`'s `on_yes`
  retargeted to it, and `max_steps` verification per (g)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document the gate and, explicitly,
  its one-shot window limit

### Dependent Files (Callers/Importers)
- N/A — loop is invoked by ID via the FSM runner, not imported

### Similar Patterns
- **Baseline-ref + `git diff --name-only`**: `general-task.yaml`'s
  `check_provisional_markers` captures `git rev-parse HEAD` at `init` into
  `baseline-ref.txt`, then diffs against it later
  (`git diff --name-only "$BASELINE_REF" -- .`) gated via `output_json`. The same
  loop's `final_verify_spin_gate` extends this with an explicit `.loops/` exclusion
  pathspec (`git diff "$BASELINE_REF" -- . ':(exclude).loops/'`) — the same
  directional idea, applied as an exclusion rather than the inverse containment
  assertion this gate needs.
- `rn-refine.yaml`'s `snapshot_leaf_diff` (lines 455-469) repeats the
  baseline-then-diff shape per-leaf, though purely for observability (never gates).
- `mechanize-skills.yaml:206-210` has a `git status --porcelain` dirty-tree check,
  but runs *before* the pass (refusing to start against a dirty tree) — the inverse
  temporal direction from what this gate needs.

No existing gate asserts "changed-file-set ⊆ run_dir" as a subset/containment
check; the closest structural template is `check_provisional_markers`'s
baseline-ref + `git diff --name-only` shape.

### Tests
- `scripts/tests/test_builtin_loops.py::TestWorkflowGeneratorLoop::test_pipeline_states_exist`
  (line 17725) enumerates a `required` state set — add `check_intent_scope`.
- `...::test_validation_gates_are_exit_code` (line 17784) — add
  `"check_intent_scope"` to its parametrize list so the new gate is held to the
  same shape.
- Add a routing-edge test (dict-lookup shape) pinning
  `check_intent_scope.on_no == "diagnose"`, **not** `capture_intent`. This is the
  regression guard for the unbounded-retry-wedge analysis in Expected Behavior;
  without it a later "simplification" back to `capture_intent` reintroduces the
  hang silently.
- Behavioral test cases, following the
  `TestGeneralTaskFinalVerifySpinGateShellAction` helper shape (class starts line
  2988; helpers `_init_repo` line 3001, `_run_gate` line 3019, `_make_run_dir` line
  3028): build a temp git repo, write both baselines, substitute the run dir in the
  extracted action string, run via `subprocess.run(["bash", "-c", ...])`, assert on
  `returncode`.
  - (i) only run-dir files written → exit 0
  - (ii) an out-of-scope untracked file → non-zero
  - (iii) an out-of-scope *tracked* file modified → non-zero
  - (iv) **a pre-existing untracked file present before `init` → exit 0** (the
    dirty-tree false-positive guard — the case that wedges the loop if the baseline
    snapshot is omitted)
  - (v) run dir not gitignored → exit 0 (proves the explicit pathspec exclusion,
    not ambient gitignore, is doing the work)
  - (vi) non-git directory → exit 0 with a warning
- Three further cases for requirement (e), the path-space mismatch — each of which
  the naive absolute-pathspec formulation fails *silently green*, so they cannot be
  skipped:
  - (vii) **loop invoked from a repo subdirectory** (`cwd != repo root`) with only
    run-dir files written → exit 0. Proves the gate relativizes against
    `git rev-parse --show-toplevel` rather than `$(pwd)`.
  - (viii) **run dir outside the worktree** (an absolute path under `tmp_path`, not
    under the repo) → exit 0 *with a warning*, per (e)(2) — and assert the warning
    text, since a bare exit 0 here is indistinguishable from the bug.
  - (ix) **a deliberate out-of-scope write while the run dir is correctly
    excluded** → non-zero. Pair with case (i) as a positive/negative couple; case
    (i) alone passes trivially against a gate that matches nothing.

  Note macOS resolves `tmp_path` under `/private/var/...` while `$(pwd)` may report
  `/var/...` — normalize both sides in the helper or these cases flake per-platform
  (requirement (e)(3)).

_Wiring pass added by `/ll:wire-issue`:_
- `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`
  (`scripts/tests/test_builtin_loops.py:16206-16218`, class starts 16104) —
  iterates **every** file in `BUILTIN_LOOPS_DIR.rglob("*.yaml")`, including
  `workflow-generator.yaml`, and asserts no new WARNING-severity finding
  appears in any of 10 ratcheted categories (`shared-tmp`, `partial-route`,
  `required-inputs`, `unreachable`, `failure-terminal`,
  `artifact-versioning`, `capture-ordering`, `loop-reference`,
  `unsafe-context-interp`, `no-scope`) unless present in `ALLOWLIST` (lines
  16138-16177, keyed by `(loop_stem, category) -> {warning_paths}`). No
  `("workflow-generator", ...)` entry currently exists. If adding
  `check_intent_scope` trips any of these categories (e.g. a missing `scope:`
  declaration -> `no-scope`, an on_yes-only edge before `on_no` is wired ->
  `partial-route`), this test fails at implementation time and either the
  new state's wiring needs fixing or a new `ALLOWLIST` entry must be added
  with this issue ID as justification, per the table's own convention.
- `test_run_dir_used_throughout` (`scripts/tests/test_builtin_loops.py:17813-17822`)
  — iterates a fixed tuple of state names (`capture_intent`, `validate_intent`,
  `sketch_state_graph`, `emit_artifact`, `validate_artifact`) asserting
  `"run_dir" in action`. `check_intent_scope` is architecturally the same
  invariant (it exists specifically to check containment under `run_dir`) but
  is not in this tuple — add it so the test actually covers the new gate.
- `test_diagnose_mentions_both_retry_exhaustion_paths`
  (`scripts/tests/test_builtin_loops.py:18046-18052`) — asserts `diagnose`'s
  action text mentions `"emit_artifact"`, `"capture_intent"`, and
  `"max_intent_retries"`, i.e. `diagnose` enumerates every failure path that
  can route to it. `check_intent_scope.on_no` is a new route into `diagnose`;
  for consistency with that existing pattern, `diagnose`'s prompt text should
  mention the new gate and this test extended to assert it — not required
  for the test to pass as written, but a natural consistency point given
  the established convention.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the gate, and its one-shot window
  limit stated plainly so it is not mistaken for whole-pipeline enforcement

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md` — the `workflow-generator` section's `### State Graph`
  ASCII diagram (~lines 155-175) enumerates the exact edge sequence (`init ->
  capture_intent -> validate_intent -> sketch_state_graph -> ...`) and needs
  `check_intent_scope` inserted between `validate_intent` and
  `sketch_state_graph`, with its `on_no -> diagnose` branch shown. Confirmed by
  `codebase-analyzer`: `docs/guides/LOOPS_REFERENCE.md`,
  `scripts/little_loops/loops/README.md`, and
  `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` describe workflow-generator only
  as pass-level prose and do **not** need updating — only this file has a
  literal state-by-state diagram.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Exact insertion point** — `scripts/little_loops/loops/workflow-generator.yaml`:
  - `init` (lines 43-58): `action_type: shell`, no `evaluate:` block, flows via bare `next: capture_intent`. No existing `git rev-parse HEAD` or `git ls-files -o --exclude-standard` capture — both must be added fresh.
  - `validate_intent` (lines 84-100): `action_type: shell`, `evaluate: {type: exit_code}`, `on_yes: sketch_state_graph`, `on_no: capture_intent`. `on_yes` is the exact edge to retarget to `check_intent_scope`.
  - `max_steps` (line 32) is currently **40, not 45**. The Proposed Solution (g) assumption that BUG-3327 already bumped it does not hold against the current file — Implementation Step 4 ("verify... at least 45") will find 40 and must apply the bump itself.
- **`general-task.yaml` baseline/diff precedent, exact shape**: `check_baseline_tests` (line 76) writes `baseline-ref.txt` via `git rev-parse HEAD > "${context.run_dir}/baseline-ref.txt" 2>/dev/null || echo "" > ...`, action_type shell, no evaluate block (flows via bare `next`). Downstream states read the file rather than re-deriving HEAD. `check_provisional_markers` (lines 841-864) and `final_verify_spin_gate` (lines 377-447) both use this baseline but their evaluators are `output_json` (`.markers_found` eq 0) and `output_numeric` (lt `${context.max_final_verify_spins}`) respectively — **neither uses `evaluate: {type: exit_code}`** as the Integration Map's "Similar Patterns" implies for the exit_code precedent; the `exit_code` evaluator precedent for this new state instead comes from `workflow-generator.yaml`'s own lowering-pass gates (`validate_intent`, `validate_sketch`, etc.), which are already all `action_type: shell` + `evaluate: {type: exit_code}`.
- **Untracked-set exclusion precedent, exact form**: `final_verify_spin_gate`'s `untracked() { git ls-files -o --exclude-standard -z -- . ':(exclude).loops/'; }` (lines 407-439) diffs untracked files by **both path and content hash** (`xargs -0 git hash-object`), not path alone — a name-only untracked listing is called out as insufficient by that state's own tests.
- **No-git escape precedent, exact form**: `check_provisional_markers` (lines 841-864): `if [ -z "$BASELINE_REF" ] || ! git rev-parse --git-dir >/dev/null 2>&1; then printf '...skipped: true...'; exit 0; fi` — confirms the recommended fail-open-with-warning shape for requirement (d)/(e)(2). Contrast: `mechanize-skills.yaml`'s `snapshot_baseline` dirty-worktree check (lines 189-217) instead `exit 1`s to a distinct `on_no: record_skip` branch — a different escape shape used because that gate is wrapped by a routing decision, not a direct `exit_code` evaluator. Since `check_intent_scope` uses `evaluate: {type: exit_code}` directly (per `test_validation_gates_are_exit_code`), the `exit 0`-fail-open shape is the applicable precedent, not the `exit 1`/skip-branch shape.
- **No existing symlink-resolution utility**: a codebase-wide grep for `realpath|resolve\(|relative_to\(` under `scripts/little_loops/` found no existing utility for resolving symlinks before a path-containment comparison (the 29 hits found are unrelated: config/artifact/issue paths). Requirement (e)(3)'s `/tmp` vs `/private/tmp` normalization must be written fresh for this gate.
- **`realpath` is rejected for absolute-path capture by `.ll/decisions.yaml` `ARCHITECTURE-087` (BUG-2435)**, which selects the `case "$DIR" in /*) ... esac` idiom already used by `workflow-generator.yaml`'s own `init` (lines 43-58) over `realpath` canonicalization, citing 4 prior consumption-site precedents. This decision governs the *capture* of `run_dir` as absolute, not the *symlink-resolution* step in the comparison itself (previous bullet) — the two are distinct concerns and only the latter is unaddressed by existing convention.
- **Exact test anchors**: `test_validation_gates_are_exit_code` (`scripts/tests/test_builtin_loops.py:17774-17788`) parametrizes `["validate_intent", "validate_sketch", "validate_evaluators", "validate_routing", "validate_artifact"]` — add `"check_intent_scope"`. `test_pipeline_states_exist`'s `required` set literal (`scripts/tests/test_builtin_loops.py:17726-17751`, 23 states) does not include `check_intent_scope` — add it there too.
- **FSM interpolation engine location**: `scripts/little_loops/fsm/interpolation.py`, `interpolate()` (lines 209-287). `ESCAPED_PATTERN = re.compile(r"\$\$\{")` (line 29) is substituted to a placeholder before `VARIABLE_PATTERN` (`\$\{([^}]+)\}`, line 28) resolves real `${namespace.path}` refs, then the placeholder is restored to a literal `${` (line 285) — confirming `$${ID}` survives as literal `${ID}` for bash, and a bare `${LOCAL_VAR}` raises `InterpolationError` ("expected namespace.path", lines 261-264) because it has no `.` separator. The `common.yaml:459-460` `$${ID}` precedent cited in the issue is real.
- **Test harness precedent, exact class**: `TestGeneralTaskFinalVerifySpinGateShellAction` (`scripts/tests/test_builtin_loops.py`, class starts line 2988) extracts `data["states"][name]["action"]` from parsed YAML (never re-typed), substitutes `${context.run_dir}` via plain Python `.replace()` (not the FSM interpolation engine), and runs via `subprocess.run(["bash", "-c", script], cwd=repo, ...)`. Helper `_init_repo` (builds temp repo + baseline commit + `baseline-ref.txt`), `_run_gate` (extracts+substitutes+runs), `_make_run_dir` all confirmed present at this location — this is the shape Implementation Step 5/behavioral test cases should follow.

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Line numbers have drifted since the 2026-08-27 research pass** (BUG-3327's landing shifted content in both target files):
  - `workflow-generator.yaml`: `init` is now lines 44-61 (ends `capture: run_dir` at 60, `next: capture_intent` at 61); `capture_intent` (63-97) now carries the BUG-3327 fence wrapping `${context.description}`; `validate_intent` is now lines 99-119, with `on_yes: sketch_state_graph` at line 118 (the edge to retarget) and `on_no: count_intent_retry` at line 119 (see Expected Behavior finding — not `capture_intent`); `max_steps` is confirmed **already 45** at line 32 (BUG-3327 bumped it) — Implementation Step 4 is now a verification-only no-op, not a change.
  - `test_builtin_loops.py`: `test_pipeline_states_exist` def is now line 17733, its `required` set spans 17734-17760 and already includes `"count_intent_retry"` (line 17747, added by BUG-3327) but still lacks `check_intent_scope`; `test_validation_gates_are_exit_code`'s parametrize list is now lines 17783-17791 (def line 17793), still `["validate_intent", "validate_sketch", "validate_evaluators", "validate_routing", "validate_artifact"]`; `TestGeneralTaskFinalVerifySpinGateShellAction` class now starts at line 2996 with `_init_repo` at 3009, `_run_gate` at 3027, `_make_run_dir` at 3036.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` gained a new "Fencing a User-Authored Brief/Goal" section (lines 625-676) from BUG-3327, documenting the fence mechanism (`fence.py`) — this is pure net-new prose adjacent to where this issue's gate documentation belongs; it does not mention `check_intent_scope` or runtime containment and requires no reconciliation, only a new adjacent subsection per Implementation Step 7.

## Program Design

### Signatures

- `init.action: str` — additionally writes `baseline-ref.txt` and
  `baseline-untracked.txt`; its stdout contract (`capture: run_dir`) is unchanged —
  write to files only, keep the `case`/`echo` block last
- `check_intent_scope() -> int` — **new** shell state; exits non-zero if the
  changed-file set since `init` is not a subset of `${captured.run_dir.output}`

### Call Path

`init` (writes both baselines) -> `capture_intent` -> `validate_intent`
(`on_yes: check_intent_scope` / `on_no: capture_intent`) -> `check_intent_scope`
(`on_yes: sketch_state_graph` / `on_no: diagnose`)

**Correction (2026-08-26 refine pass):** `validate_intent`'s `on_no` edge is
`count_intent_retry`, not `capture_intent` — BUG-3327 added a bounded retry
state between `validate_intent` and `capture_intent` (default
`context.max_intent_retries: "3"`). This issue's edit retargets only
`on_yes`; `on_no` is left as `count_intent_retry`, unchanged. Corrected call
path: `validate_intent` (`on_yes: check_intent_scope` / `on_no:
count_intent_retry`) -> `check_intent_scope` (`on_yes: sketch_state_graph` /
`on_no: diagnose`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Confirmed exact current YAML for the insertion boundary (`scripts/little_loops/loops/workflow-generator.yaml`):
  ```yaml
  validate_intent:
    action_type: shell
    action: |
      python3 -c "
      import yaml
      d = yaml.safe_load(open('${captured.run_dir.output}/intent.yaml'))
      assert d.get('name'), 'name is empty'
      ...
      "
    evaluate:
      type: exit_code
    on_yes: sketch_state_graph   # retarget to check_intent_scope
    on_no: capture_intent
  ```
  `init` (lines 43-58) currently ends with the `case "$DIR" in /*) ... esac` block as its last action lines, `capture: run_dir`, plain `next: capture_intent` (no evaluate block) — consistent with the Signatures section's note to "keep the case/echo block last."
- The `evaluate: {type: exit_code}` shape for `check_intent_scope` matches `workflow-generator.yaml`'s own existing lowering-pass gates (`validate_intent`, `validate_sketch`, `validate_evaluators`, `validate_routing`, `validate_artifact` — all shell+exit_code), not `general-task.yaml`'s `check_provisional_markers`/`final_verify_spin_gate`, which use `output_json`/`output_numeric` respectively despite sharing the same baseline-diff shape. `check_intent_scope`'s escape-hatch behavior (non-repo, outside-worktree) should therefore signal via the shell script's own `exit 0`/`exit 1`, not a JSON payload field.

## Implementation Steps

1. Add both baseline captures to `init` (lines 43-56), following
   `general-task.yaml:76`'s `git rev-parse HEAD > baseline-ref.txt` idiom, plus the
   `git ls-files -o --exclude-standard` untracked snapshot.
2. Add the `check_intent_scope` state — including the repo-root relativization and
   outside-the-worktree escape from requirement (e), the non-repo escape from (d),
   and the `$${VAR}` brace escaping from (f).
3. Retarget `validate_intent`'s `on_yes` to it.
4. Verify `max_steps` is at least 45 per (g).
5. Add the tests above.
6. Verify with `ll-loop validate`, plus a re-run of `workflow-generator` **from a
   deliberately dirty working tree and from a repo subdirectory**, confirming that
   pre-existing untracked files do not trip the gate and that the gate still fires
   on a deliberately planted out-of-scope write. **A green gate proves nothing
   until you have seen it go red.**
7. Document the gate and its one-shot window limit.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/loops.md` — insert `check_intent_scope` (with its
  `on_no -> diagnose` branch) into the `workflow-generator` section's ASCII
  `### State Graph` diagram, between `validate_intent` and
  `sketch_state_graph`.
- Add `check_intent_scope` to `test_run_dir_used_throughout`'s state tuple
  (`test_builtin_loops.py:17813-17822`).
- Watch `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`
  (`test_builtin_loops.py:16206-16218`) when the new state lands — add an
  `ALLOWLIST` entry for `("workflow-generator", <category>)` only if the new
  state trips one of the 10 ratcheted warning categories.
- Consider extending `diagnose`'s action text and
  `test_diagnose_mentions_both_retry_exhaustion_paths`
  (`test_builtin_loops.py:18046-18052`) to mention `check_intent_scope`,
  matching the existing convention of `diagnose` enumerating every failure
  path that routes to it.

## Impact

- **Priority**: P3 — defense-in-depth. BUG-3327's fence removes the cause; this
  catches regressions and the classes the fence does not cover.
- **Effort**: Medium — one new state, two `init` baselines, repo-root
  relativization, two escape paths, and nine behavioral test cases
- **Risk**: Medium — the gate can misfire in **both** directions: a false positive
  routes to `diagnose` and fails the run, while a path-space mismatch
  (requirement (e)) yields a gate that is permanently green and reports safety it
  is not checking. The second failure is the more dangerous one because nothing
  surfaces it. That is why the dirty-tree baseline (a), the non-repo escape (d),
  the relativization (e), and the red-gate test case are requirements, not polish —
  and why the gate must not route back to `capture_intent`.
- **Breaking Change**: No

## Scope

`workflow-generator`-only. The gate depends on that loop's `init`/`run_dir`
structure, and the other four loops BUG-3327 fences are not all meta-loops with the
same artifact-isolation contract. Generalizing it is a separate question.

## Notes

Split from BUG-3327 on 2026-08-26 (Proposed Solution §2 and its associated
requirements, tests, and Impact analysis moved here verbatim). BUG-3327 retains the
brief-fencing work.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §4, §5 R5.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-08-27T01:49:46 - `b4592890-2b63-4442-b15e-89282998dd3d.jsonl`
- `/ll:refine-issue` - 2026-08-27T01:43:27 - `981cfc8c-efe7-4751-8804-dd1eed392dab.jsonl`
- `/ll:refine-issue` - 2026-08-27T01:12:54 - `fb4eed07-2702-4aea-a748-78fa07142d55.jsonl`

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **No shared FSM shell-action test harness utility exists anywhere in `scripts/tests/`.** The "extract action from parsed YAML, substitute `${context.*}` via `.replace()`, run via `subprocess.run(['bash','-c',...])`, assert `returncode`" pattern is independently duplicated per-file across at least 13 test files (`test_builtin_loops.py`, `test_general_task_loop.py`, `test_incremental_refactor_loop.py`, and others) — confirmed by inspecting `conftest.py` directly, which has no such fixture or mixin. The new `check_intent_scope` test class should follow this same per-file duplication convention (matching `TestGeneralTaskFinalVerifySpinGateShellAction`'s shape), not attempt to extract or reuse a shared utility that does not exist.
- Corrected line anchors (per the Integration Map finding above): `test_pipeline_states_exist` required-set now spans 17734-17760; `test_validation_gates_are_exit_code` parametrize list now spans 17783-17791; `TestGeneralTaskFinalVerifySpinGateShellAction` class now starts at line 2996 with `_init_repo`/`_run_gate`/`_make_run_dir` at 3009/3027/3036.
