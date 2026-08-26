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

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the gate, and its one-shot window
  limit stated plainly so it is not mistaken for whole-pipeline enforcement

### Configuration
- N/A

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
