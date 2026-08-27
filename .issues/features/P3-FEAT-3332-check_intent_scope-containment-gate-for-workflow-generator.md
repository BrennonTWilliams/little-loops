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
`capture_intent` wrote two files under `research/` (`rsi-sources`,
`rsi-oss-projects`) **outside** `${context.run_dir}` and nothing noticed.

BUG-3327 fixes the *cause* of that specific incident (an unfenced brief that read
as live instructions). This issue adds the *guard*: a `check_intent_scope` state
that fails the run if the changed-file set since `init` is not a subset of
`${captured.run_dir.output}`.

**Split from BUG-3327 on 2026-08-26.** Rationale: the fence is the actual fix —
additive, low-risk, one prompt edit per site. This gate is a new state, two `init`
baselines, repo-root relativization, one escape path, and fourteen behavioral test
cases. It is defense-in-depth against regressions, and bundling it was the single
largest driver of BUG-3327's 63/100 outcome confidence. Land the fence first, then
this with its own budget. (That split sized the work at "nine behavioral test
cases"; a first review pass raised it to eleven, the 2026-08-26 pre-implementation
review to fourteen, and the 2026-08-27 review pass held it at fourteen by making
case (xii) unconditional — see Integration Map → Tests.)

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

1. **A scope violation is not retryable at all, so it must not enter the retry
   path.** The out-of-scope file has already been written; re-running
   `capture_intent` cannot unwrite it. Folding the containment check into
   `validate_intent` would route every true violation through
   `count_intent_retry` (line 119) — burning all three `max_intent_retries`
   attempts on a condition no retry can clear, then arriving at `diagnose`
   several passes late with the retry-exhaustion story rather than the real one.
   The gate must route a violation *directly* to `diagnose`, which requires a
   separate state with its own routing keys.

   _(Historical note: this reason originally rested on `validate_intent`'s
   `on_no` being an **unbounded** edge to `capture_intent`. BUG-3327 landed
   `count_intent_retry` and bounded it, so the oscillate-until-`max_steps`
   hazard no longer exists; the "not retryable" argument above survives that
   change intact.)
2. **The two checks fail for unrelated reasons.** "intent.yaml is malformed" is
   genuinely retryable by `capture_intent`; "the agent wrote outside its sandbox"
   is not. One state cannot carry two different `on_no` targets.
3. **`validate_intent`'s evaluator shape is pinned.**
   `test_validation_gates_are_exit_code` (`test_builtin_loops.py:17793`)
   parametrizes over `"validate_intent"`. A new sibling state takes its own
   `evaluate: {type: exit_code}` and leaves that test untouched.

**Two limits of this placement, to state rather than silently accept:**

- **The gate is one-shot, at one point in a twelve-state pipeline.** It audits the
  window from `init` through `validate_intent` only. `sketch_state_graph`,
  `attach_evaluators`, `resolve_routing`, `emit_artifact` and `diagnose` are all
  prompt states that run *after* it and are equally capable of writing outside
  `run_dir`. This issue does not make the loop scope-safe; it closes the one
  window where the incident occurred. Say so in the guide entry so the gate is not
  mistaken for whole-pipeline enforcement. Generalizing the gate across the
  remaining prompt states is tracked as **FEAT-3335**, which depends on this
  issue. (`diagnose` is the one exception handled here — see requirement (o) —
  because this issue creates the edge into it.)
- ~~**`validate_intent`'s `on_no: capture_intent` edge (line 98) remains
  unbounded.**~~ **Resolved — no residual work.** BUG-3327 bounded that edge with
  `count_intent_retry` (`workflow-generator.yaml:119`,
  `context.max_intent_retries: "3"`). Retained here only so the reasoning above
  is readable against its original form.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **BUG-3327 has landed** (`status: done`, commit `34c3ecac9`): `validate_intent`'s `on_no` is now `count_intent_retry` (`workflow-generator.yaml:119`), a bounded retry state (default `context.max_intent_retries: "3"`, mirroring the pre-existing `count_emit_retry` pattern). Reason (1) above has been rewritten against this current state; nothing further to reconcile.
- The "Two limits of this placement" bullet's second point ("if BUG-3327 recorded 'left alone', pick it up here") is resolved — BUG-3327 did not leave the edge unbounded. No residual work from that bullet remains for this issue.

## Use Case

A little-loops maintainer runs `ll-loop run workflow-generator` from a
subdirectory of the repo, with a working tree that already holds a few
untracked scratch files, to generate a new loop from a natural-language brief.
Partway through `capture_intent`, the LLM state decides it needs to "do some
research first" and writes notes to `research/` at the repo root — outside the
run directory, into the maintainer's actual source tree.

Today nothing notices: the run continues, the loop is emitted, and the stray
files are discovered later by `git status` (or not at all, if the path happens
to be gitignored) with no record of which run produced them. With
`check_intent_scope`, the run stops at the gate immediately after
`validate_intent`, `${run_dir}/.scope_violations.txt` names `research/…`, and
`diagnose` reports a containment violation rather than a retry-exhaustion
story. The maintainer's pre-existing untracked scratch files do not trip the
gate, and legitimate `run_dir`, `.loops/tmp/scratch/` and `.ll/` harness writes
are ignored — so the signal is actionable on the first pass rather than a false
alarm to be disabled.

## Proposed Solution

A new `action_type: shell` / `evaluate: exit_code` state between `validate_intent`
and `sketch_state_graph`, with `on_yes: sketch_state_graph` and `on_no: diagnose`.

**Implementation language — decided 2026-08-27 (review pass), see requirement
(e).** The gate body is a `python3 -c` script inside the `action_type: shell`
action, not a bash pipeline. This is the same shape `validate_intent` already
uses in this loop, so `test_validation_gates_are_exit_code` is satisfied
unchanged, and it is what makes requirements (d), (e), (k)(3) and most of (l)
tractable rather than hand-rolled.

Correctness requirements, each of which the naive
`git ls-files -o --exclude-standard` formulation gets wrong:

**(a) Baseline the untracked set at `init`, don't assume a clean tree.** A
developer's working tree routinely holds pre-existing untracked files. Without a
baseline the gate fires on the *first* pass of every run in a dirty repo — and
since the offending files are not the loop's to remove, the failure is permanent.

`init` (lines 44-61) must first resolve the repo root — it currently has no
`ROOT`, only `DIR`, so this is net-new and is a precondition of every other git
invocation in the state:

```sh
# HARNESS: repo root for every git call in init and check_intent_scope. The
# two sites are a matched pair (see requirement (c)); keep them identical.
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=""
```

then capture both baselines (`$EXCL` is the shared exclusion literal from (f)):

```sh
if [ -n "$ROOT" ]; then
  git -C "$ROOT" rev-parse HEAD > "$DIR/baseline-ref.txt" 2>/dev/null || : > "$DIR/baseline-ref.txt"
  git -C "$ROOT" ls-files -o --exclude-standard -z \
    -- ':(exclude).loops/' ':(exclude).ll/' \
    > "$DIR/baseline-untracked-paths.z" 2>/dev/null
else
  : > "$DIR/baseline-ref.txt"
  : > "$DIR/baseline-untracked-paths.z"
fi
```

`check_intent_scope` then diffs the *current* untracked set against the baseline
(as a `path -> content-hash` map, per (d)) and only considers newly-appeared or
in-place-modified paths, unioned with
`git -C "$ROOT" diff --name-only "$BASELINE_REF"` for modifications to tracked
files.

**(a1) Ordering inside `init` is a three-way constraint, not just "keep the
`case`/`echo` block last."** `init`'s existing body creates run-dir state before
anything else — `mkdir -p "$DIR"`, `mkdir -p "$DIR/probes"`,
`: > "$DIR/.emit_errors.txt"`, `: > "$DIR/.intent_errors.txt"`. **The baseline
capture must run after that block.** Captured before it, those files are absent
from the baseline and read as newly-appeared untracked writes — so in any project
that does not gitignore the run dir (exactly behavioral case (v)) the gate fires
on the loop's own scaffolding, permanently, on every run. The required order in
`init` is:

1. existing `mkdir` / truncate / `rm -f` block (creates run-dir state)
2. `ROOT` resolution and both baseline captures (this requirement and (a))
3. the `case "$DIR" in /*) … esac` stdout block, last and alone (requirement (b))

Note the second and third constraints are independent: (b) pins the tail, this
pins the middle, and neither implies the other.

**(b) `init` must remain the sole writer to its own stdout — this is a stricter
contract than "keep the `case`/`echo` block last."** `capture:` takes the
**entire** stdout of the state, not its last line:
`executor.py:2370-2372` stores `{"output": result.output.rstrip("\n\r")}`. If
any new command leaks a single byte to stdout — a `git` warning, a
`detached HEAD` advisory, the `ls-files` listing itself if a redirect is
mistyped, or `git rev-parse --show-toplevel` if its `$(…)` capture is dropped in
a later edit — `${captured.run_dir.output}` becomes a multi-line garbage path and
**every downstream state silently reads and writes the wrong location**. That is
the same always-green/never-announces-itself failure class requirement (k) exists
to prevent, so it gets the same treatment: every new command redirects stdout to a
file (or into `$(…)`) **and** sends stderr to `/dev/null`, and a test asserts
`init`'s stdout is exactly one line — in a git repo *and* in a non-repo, where all
three git commands fail.

**(c) `init`'s baseline and the gate's current-set capture are a matched pair,
not two independent captures.** The set difference is meaningful only if both
sides were produced by the *identical* invocation — same `-C "$ROOT"`, same
pathspec (including both exclusions), same `--exclude-standard`, same `-z`. Any
drift between the two sites (e.g. adding an exclusion to one only) makes
previously-baselined files read as newly-appeared, i.e. a permanent false
positive. Write the two commands as a deliberate pair and say so in a
`# HARNESS:` comment at both sites.

The exclusion pathspec belongs on **both** sides, not gate-side only. An earlier
draft of (a) sketched the baseline without it; that happened to work by accident
(the difference cancels) but left the pair asymmetric, so any later edit to one
side would silently break it.

**(d) In-place overwrite of an untracked file — DECIDED: content-hash the
baseline.** A path-name-only set difference flags only *newly appeared* untracked
paths. An agent that clobbers a **pre-existing** untracked file outside `run_dir`
leaves the path set unchanged and the gate passes green. The in-repo precedent
already solves this: `general-task.yaml:424-429`'s `untracked()` diffs untracked
files by **both path and content hash** (`xargs -0 git hash-object`), and
`test_untracked_file_content_edit_resets_counter`
(`test_builtin_loops.py:3081-3096`) exists specifically to assert that a name-only
listing is insufficient.

**Decision (2026-08-27 review pass): take the content-hash path.** Baseline
`path -> hash` pairs rather than bare paths, mirroring `untracked()`. Behavioral
case (xii) is therefore **required, not conditional**, and the accepted-limit
variant is off the table — the hole does not appear in the guide's limits list.
Cost is one `hash-object` pass at `init` and one at the gate, which requirement
(e)'s `python3` body makes a three-line `dict` comparison rather than a shell
pipeline.

**(e) Delimiter and implementation language — DECIDED: NUL-delimited git output,
consumed by `python3`.** `general-task`'s `untracked()` uses `git ls-files -o -z`
so paths containing spaces or newlines survive. `comm` is line-oriented and has no
NUL mode on any platform (BSD or GNU), so a bash `sort`/`comm` formulation would
have forced either a newline-delimited set (losing embedded-newline paths) or a
hand-rolled `sort -z` substitute.

**Decision (2026-08-27 review pass): the gate body is `python3 -c`, and git
output is NUL-delimited throughout.** Precedent is `validate_intent` in this same
loop — `action_type: shell` + `python3 -c` + `evaluate: {type: exit_code}` — so
the shape test in Expected Behavior reason (3) is satisfied without change. This
decision is load-bearing for four other requirements and is why they are cheap
rather than risky:

- **(d)** becomes a `dict` set-difference over `path -> hash`, not an `xargs`
  pipeline.
- **this requirement** dissolves: Python splits on `\0` natively; no `comm`
  substitute needed and no embedded-newline caveat to document.
- **(k)(3)** symlink normalization becomes `os.path.realpath`, instead of a
  hand-rolled bash prefix comparison. It also sidesteps `ARCHITECTURE-087`
  cleanly — that decision governs the *capture* of `run_dir` as absolute in
  shell, not a comparison-time normalization inside a Python body.
- **(l)** reduces to a residual check: a `python3 -c` body rarely contains the
  `${` sequence at all.

It is also the largest available reduction in the surface area the Impact
section calls out as the dangerous one — the path-space code that almost never
executes.

**(f) Exclude harness state by explicit pathspec, not by ambient gitignore — and
exclude `.loops/` and `.ll/` as wholes, not just `run_dir`.** This repo happens to
gitignore `.loops/runs/` (`.gitignore:88`), so `--exclude-standard` hides
`run_dir` here *by accident*. A consuming project without those entries would see
every legitimate run-dir artifact as an out-of-scope write. Exclude explicitly,
following `general-task.yaml`'s `final_verify_spin_gate` idiom
(`git diff "$BASELINE_REF" -- . ':(exclude).loops/'`).

The exclusion must cover:

- **`.loops/`** — not merely `${captured.run_dir.output}`. The
  scratch-pad-redirect hook writes `.loops/tmp/scratch/<cmd>-<pid>.txt` during
  prompt states (`scripts/little_loops/subprocess_utils.py:292`), which is outside
  `run_dir` and not the loop's doing. In a consuming project that does not
  gitignore `.loops/`, a `run_dir`-only exclusion therefore fails the run on
  harness scratch files. Excluding `.loops/` wholesale also subsumes the
  `run_dir`-relative case and is the idiom already precedented in this repo.
- **`.ll/`** — this repo's `.gitignore` covers `.ll/` only as a list of individual
  entries (`.gitignore:60-64,107-123`: `history.db`, `queue.db`, `*.lock`,
  `ll-context-state.json`, …), **not** the directory. Harness state written during
  a run that falls outside that list — a `.ll/decisions.d/<uuid>.json` fragment, a
  `.ll/loop-suggestions/` write, an analytics artifact a future version adds — is
  therefore visible to the gate and reads as an out-of-scope write by the loop.
  It is also where `${context.loops_dir}` (`.ll/loops`) lives, which requirement
  (p) already places outside the audited window.

`-C "$ROOT"` is load-bearing for the exclusion, not just the enumeration:
`:(exclude)` pathspecs without a leading `/` resolve relative to the *current
directory*, so a gate invoked from a subdirectory without `-C "$ROOT"` would
exclude `<subdir>/.loops/` rather than the repo's.

**(g) Accepted limit: gitignored out-of-scope writes are invisible.**
`--exclude-standard` means a write to `node_modules/`, `.env`, or any other
ignored path is not reported by this gate at all. That is the correct trade
(without it the gate is unusable in any project with build output), but it is a
real hole in the containment claim and belongs in the guide entry next to the
one-shot-window limit, not left implicit.

**(h) Accepted limit: the gate cannot tell the loop's writes from a human's.**
It audits a *time window*, not an actor. A maintainer who edits a source file in
their editor while the run is in flight — an entirely normal thing to do during a
5400s loop — produces a changed file outside `run_dir` and fails the run. There is
no fix available at this layer (git offers no provenance), and fail-open would
defeat the gate. It is a third entry for the guide's limits list, next to the
one-shot window and the gitignored-write blind spot, so the next person to hit it
recognizes it rather than filing it as a bug.

**(i) Cover untracked *and* tracked changes.** The source incident's `research/*.md`
files were new/untracked, so a tracked-only `git diff --name-only` misses the exact
failure mode this issue targets; conversely an untracked-only check misses an
in-place overwrite of a tracked file. Check both.

**(j) Define the non-repo behavior — and the empty-repo behavior with it.**
`workflow-generator` can be run outside a git repo, where `git rev-parse HEAD`
fails and there is no baseline to diff against. Decide and state it: skip the gate
with a logged warning (exit 0) is the recommended default — a hard failure would
make the loop unusable outside a repo for a guard that is defense-in-depth, not the
primary fix. BUG-3327's fence is what actually prevents the behavior; this gate
catches regressions.

**A git repo with zero commits reaches the same dead end by a different route**
and must take the same escape: `git rev-parse --git-dir` succeeds, so a
`--git-dir`-only check reports "this is a repo," but `git rev-parse HEAD` fails
and `baseline-ref.txt` is written empty, leaving `git diff --name-only ""`
malformed. `check_provisional_markers` (`general-task.yaml:841-864`) already tests
**both** conditions for exactly this reason —
`if [ -z "$BASELINE_REF" ] || ! git rev-parse --git-dir >/dev/null 2>&1` — and
that two-clause form is the one to copy. The empty `ROOT` case from (a)'s sketch
(`|| ROOT=""`) collapses into the same escape. Note that every behavioral case
below builds its temp repo with a baseline commit, so **no proposed test exercises
this path**; case (vi) must be extended or partnered with an empty-repo variant.

**(k) Relativize the run dir before comparing — the two path spaces do not match.**
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

**Scope note — relativization is the fallback path, not the main mechanism.**
The runner's default `run_dir` is `.loops/runs/<loop>-<ts>/`
(`fsm/validation/meta_rules.py:194`), which requirement (f)'s `.loops/`-wide
exclusion **already subsumes**. So in the overwhelmingly common case the gate
needs no relativization at all. Requirement (k)(1) below exists for one specific
configuration: a non-default `--run-dir` that lands *inside* the worktree but
outside `.loops/` and `.ll/`. Requirement (k)(3)'s symlink normalization is likewise
reachable only on that path. Implement (k)(1)/(k)(3) as a guarded branch rather than
as unconditional machinery in front of every run — that is what keeps the Impact
section's Medium risk rating honest, since the code most likely to be wrong is
also the code that almost never executes.

Requirements:

1. Compute the repo root once (`git rev-parse --show-toplevel`) and convert
   `${captured.run_dir.output}` to a root-relative path before using it in a
   pathspec. Note `$(pwd)` is not necessarily the repo root — the loop can be
   invoked from a subdirectory, so cwd-relative ≠ repo-relative.
   Precedent: `incremental-refactor.yaml:58,159`
   (`ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT="."`).
1b. **Enumerate from the repo root, not from cwd — `git -C "$ROOT"`.** This is
   the same defect as (k) in a second place, and the sketches in (a) originally
   had it: both `git ls-files -o --exclude-standard` and
   `git diff --name-only "$BASELINE_REF" -- .` are **scoped to the invocation
   directory**. Run from a subdirectory, they enumerate only that subtree, so
   every out-of-scope write elsewhere in the repo is silently invisible and the
   gate reports green. Every git invocation in both `init` and
   `check_intent_scope` must carry `-C "$ROOT"`, and the tracked-file diff must
   drop the cwd-relative `-- .` pathspec (keep only the `':(exclude)'` exclusions
   from (f), which `-C "$ROOT"` likewise anchors). Test case (vii) does **not**
   catch this — it only proves the absence of a false positive; see case (vii-b).
2. Handle the run dir being **outside the worktree entirely** (an absolute
   `--run-dir` elsewhere on disk, or a symlinked path) — **by gating normally,
   not by escaping.**

   _(Corrected 2026-08-26 review pass. This requirement previously read: "There
   is no valid root-relative form; git will never report those files at all, so
   the correct behavior is the same skip-with-warning escape as (j)." That is
   backwards, and it disables the gate in the one configuration where it is
   easiest to enforce.)_

   The reasoning: when `run_dir` sits outside the worktree, git reports nothing
   about it — which is not a *loss* of information, it is the containment
   assertion already satisfied for free. The allowed set inside the repo collapses
   to `.loops/` and `.ll/` alone (per (f), for the scratch-pad hook and harness
   state), and therefore **every remaining path git reports is by definition an
   out-of-scope write.** Nothing is unknowable here; the check is strictly
   *simpler* than the in-worktree case, not impossible.

   Correct behavior: detect outside-worktree, skip the run-dir pathspec entirely,
   keep the `.loops/`/`.ll/` exclusions, and evaluate the diff exactly as normal.
   Reserve the skip-with-warning escape for (j)'s two genuine cases — no repo, and
   no commits — where there is truly no baseline to diff against.

   This matters disproportionately because the discarded configuration fails
   *green*: a run with `--run-dir /tmp/foo` would report containment it never
   checked, which Impact names as the more dangerous of the two misfire
   directions.
3. Normalize both sides (resolve symlinks, strip trailing `/`) before the prefix
   comparison. macOS's `/tmp` → `/private/tmp` symlink makes this a live concern
   for the `tmp_path`-based tests, not a theoretical one. Per (e) this is
   `os.path.realpath` in the `python3` body, not a shell construction.

**(l) Escape bash brace-expansions — the FSM interpolates the action string
first.** This gate is the first state in the loop to need real shell variables
(`$(git rev-parse --show-toplevel)`, a repo-root prefix, a relativized run dir).
The FSM's interpolation engine runs over the **entire** action text before
`bash -c` ever sees it, so a bare `${VAR}` is parsed as a namespace reference and
raises `expected namespace.path`. Use `$VAR` or escape as `$${VAR}` —
`common.yaml:459-460` (`$${ID}`) is the in-repo precedent. Per (e)'s decision the
gate body is mostly Python, where the `${` sequence rarely appears at all, so this
is a residual check on the surrounding shell preamble (`ROOT`, `BASELINE_REF`)
rather than a pervasive concern. The `init` additions in (a) use bare `$DIR`/`$ROOT`
and sidestep it entirely, matching `general-task.yaml`'s local-variable idiom.

**(m) Step budget — verified, no change needed.** `max_steps` is **already 45**
(`workflow-generator.yaml:32`, bumped by BUG-3327). An earlier research pass
recorded 40; that reading is stale and superseded.

The cost is **+1 step per run, full stop** — not +1 per retry pass.
`check_intent_scope` hangs off `validate_intent`'s `on_yes` only, so the
`count_intent_retry` cycle (`validate_intent -> count_intent_retry ->
capture_intent -> validate_intent`) never traverses it; it is reached exactly once,
on the pass where intent validation finally succeeds. Its own `on_no` goes to
`diagnose`, which is `next: failed` (`workflow-generator.yaml:649`) — terminal, so
no path re-enters the gate either.

_(Corrected 2026-08-26 review pass: this requirement previously claimed the retry
loop "can traverse it up to `max_intent_retries` (3) additional times," implying a
worst case of +4. That is wrong on the graph as written. The conclusion is
unchanged — 45 is sufficient — but the arithmetic is recorded correctly here so a
later reader does not re-derive a budget pressure that does not exist.)_

**(n) The gate must persist its findings, and `diagnose` must read them.**
`on_no: diagnose` lands in a **prompt** state whose read list is a fixed
enumeration (`workflow-generator.yaml:638-642`: `intent.yaml`,
`graph-sketch.yaml`, …, `.intent_errors.txt`) and whose "Most common failure"
paragraph names only the two retry-exhaustion paths. A scope violation currently
arrives there with no artifact and no explanation, so the diagnostic the operator
receives would describe the wrong failure. Required:

- `check_intent_scope` writes the offending paths, one per line, to
  `${captured.run_dir.output}/.scope_violations.txt` (truncated to empty on a
  pass, mirroring `validate_intent`'s `.intent_errors.txt` handling) **and**
  prints them to stdout so they land in the run log.
- `.scope_violations.txt` is added to `diagnose`'s read list, and
  `diagnose`'s failure enumeration gains the scope-violation path.

This promotes the Wiring Phase's "consider extending `diagnose`" item to a
requirement, and gives `test_diagnose_mentions_both_retry_exhaustion_paths`
(`test_builtin_loops.py:18046`) a third path to assert.

**(o) Fence `diagnose` itself.** `diagnose` is an unfenced prompt state, so a
containment violation is currently routed *into* an LLM state that is free to
write anywhere — including more out-of-scope files, after the gate has already
run. Add BUG-3327's clause ("write no file this state does not explicitly ask you
to write") to `diagnose`'s prompt. In scope here because this issue creates the
edge that makes it matter; the other post-gate prompt states named in the
one-shot-window limit are the follow-up issue's business, not this one's.

**(p) `loops_dir` is out of the audited window — for now.** The loop's `scope:`
declares `${context.loops_dir}` (`.ll/loops`) alongside `run_dir`, and
`auto_promote` legitimately writes there. That happens at `promote`, long after
this gate runs, so a run-dir-only subset assertion is correct at this point in the
pipeline. Requirement (f)'s `.ll/`-wide exclusion makes this structurally true
rather than merely temporally true. If the gate is ever generalized to later
states (see the one-shot limit above), `loops_dir` must be handled explicitly or
promotion reads as a violation. Carried forward as an explicit requirement of
**FEAT-3335**.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Additional `$${VAR}` escape precedent sites** beyond `common.yaml:459-460`: `workflow-generator.yaml:607` (`promote` state, `CANDIDATE="$${NAME}-$${SUFFIX}"`), `rn-remediate.yaml` (multiple sites, e.g. `:176`, `:538`, `:542`), `openscad-model-generator.yaml:313`. A second idiom coexists in the codebase: `general-task.yaml`'s `check_provisional_markers`/`final_verify_spin_gate` avoid braces entirely for locals (bare `$VAR`, e.g. `$BASELINE_REF`), sidestepping the escaping question rather than using `$${VAR}`. Both idioms are used elsewhere; neither is marked preferred. **The 2026-08-27 review pass selects the bare-`$VAR` idiom for this issue's shell preamble** — see requirement (l).
- **Second precedent for repo-root resolution** (requirement (k)(1)): `incremental-refactor.yaml:58,159` — `ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT="."` — used for a dirty-tree check and to scope a checkout/clean action to the resolved root rather than `$(pwd)`, with an in-file comment explaining the rationale ("a run launched from a subdirectory can't scope the checkout narrowly").
- **No existing symlink-normalization utility, confirmed independently**: a grep for `realpath|resolve\(|relative_to\(` across `scripts/little_loops/` found only `rn-refine.yaml:93,109` (`realpath "${context.plan_file}" > "$DIR/.source-path"`), which captures a source path rather than resolving symlinks for a containment comparison. `ARCHITECTURE-087` (BUG-2435) governs absolute-path *capture*, not symlink resolution during comparison — requirement (k)(3) must be written fresh, confirming the issue's original claim. Requirement (e)'s `python3` decision satisfies it with `os.path.realpath`.
- **Untracked-set content-hash checking is confirmed test-enforced**: `general-task.yaml:424-429`'s `untracked()` + `git hash-object` pattern is backed by `test_untracked_file_content_edit_resets_counter` (`test_builtin_loops.py:3081-3096`), which asserts a name-only untracked listing is insufficient. This is the precedent requirement (d)'s decision follows.
- **`.ll/` is not gitignored as a directory** (requirement (f)): `.gitignore` covers it as individual entries only — `.ll/ll.local.md` (60), `.ll/loop-suggestions/` (61,120), `.ll/ll-continue-prompt*.md` (63-64,118), `.ll/*.lock` (107), `.ll/ll-context-state.json` (108), `.ll/evidence-verdict-cache.json` (109), `.ll/ll-sync-state.json` (110), `.ll/history.db*` (111-113), `.ll/queue.db*` (114-116), `.ll/ll-update-docs.watermark` (117), `.ll/ll-context-handoff-needed` (119), `.ll/workflow-analysis/` (121), `.ll/user-messages-*.jsonl` (122), `.ll/export*.jsonl` (123). Notably **not** covered: `.ll/decisions.d/` (282 tracked fragments at time of review), `.ll/decisions.yaml`, `.ll/ll-config.json`, `.ll/loops/`. A run that appends a decision fragment would therefore trip a gate without the `.ll/` exclusion.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — `init` (lines 44-61, add
  `ROOT` resolution and both baselines, in the order pinned by (a1)), new
  `check_intent_scope` state, `validate_intent`'s `on_yes` retargeted to it, and
  `max_steps` verification per (m)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document the gate and, explicitly,
  its limits

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
  (def line 17733, `required` set 17734-17760) enumerates a `required` state set —
  add `check_intent_scope`.
- `...::test_validation_gates_are_exit_code` (parametrize 17783-17791, def 17793) —
  add `"check_intent_scope"` to its parametrize list so the new gate is held to the
  same shape.
- `...::test_init_action_guards_against_already_absolute_run_dir` (line 17726)
  asserts `'case "$DIR" in'` and `"/*)"` are present in `init`'s action. The
  additions from (a)/(a1) must not disturb that block; the test passes unchanged
  but is the tripwire if the `case` block is refactored away.
- Add a routing-edge test (dict-lookup shape) pinning
  `check_intent_scope.on_no == "diagnose"`, **not** `capture_intent`. This is the
  regression guard for the unbounded-retry-wedge analysis in Expected Behavior;
  without it a later "simplification" back to `capture_intent` reintroduces the
  hang silently.
- Behavioral test cases, following the
  `TestGeneralTaskFinalVerifySpinGateShellAction` helper shape (class starts line
  2996; helpers `_init_repo` line 3009, `_run_gate` line 3027, `_make_run_dir` line
  3036): build a temp git repo, write both baselines, substitute the run dir in the
  extracted action string, run via `subprocess.run(["bash", "-c", ...])`, assert on
  `returncode`.
  - (i) only run-dir files written → exit 0
  - (ii) an out-of-scope untracked file → non-zero
  - (iii) an out-of-scope *tracked* file modified → non-zero
  - (iv) **a pre-existing untracked file present before `init` → exit 0** (the
    dirty-tree false-positive guard — the case that wedges the loop if the baseline
    snapshot is omitted)
  - (v) run dir not gitignored → exit 0 (proves the explicit pathspec exclusion,
    not ambient gitignore, is doing the work). **This case is also the (a1)
    ordering guard**: it fails if the baseline is captured before `init`'s
    `mkdir`/truncate block, because `init`'s own `.emit_errors.txt` /
    `.intent_errors.txt` then read as newly-appeared untracked writes.
  - (vi) non-git directory → exit 0 with a warning
  - (vi-b) **git repo with zero commits** → exit 0 with a warning, per (j). Every
    other case here builds its temp repo *with* a baseline commit, so without this
    variant the `[ -z "$BASELINE_REF" ]` clause is entirely untested and a
    `--git-dir`-only check would ship looking correct.
- Three further cases for requirement (k), the path-space mismatch — each of which
  the naive absolute-pathspec formulation fails *silently green*, so they cannot be
  skipped:
  - (vii) **loop invoked from a repo subdirectory** (`cwd != repo root`) with only
    run-dir files written → exit 0. Proves the gate relativizes against
    `git rev-parse --show-toplevel` rather than `$(pwd)`.
  - (vii-b) **loop invoked from a repo subdirectory, out-of-scope file written
    *outside* that subdirectory** → non-zero. This is (vii)'s mandatory negative
    partner, per requirement (k)(1b): (vii) alone passes trivially against a gate
    that enumerates only the cwd subtree and therefore sees nothing. Without this
    case the cwd-scoping defect ships silently green.
  - (viii) **run dir outside the worktree, clean repo** (an absolute path under
    `tmp_path`, not under the repo) → exit 0, per the corrected (k)(2). The gate
    drops the run-dir pathspec, keeps the `.loops/`/`.ll/` exclusions, and finds
    nothing.
  - (viii-b) **run dir outside the worktree, out-of-scope file planted inside the
    repo** → non-zero. (viii)'s mandatory negative partner and the regression guard
    for the corrected (k)(2): the superseded skip-with-warning reading passes
    (viii) trivially and fails only here. Without this case the always-green
    variant ships looking tested.
  - (ix) **a deliberate out-of-scope write while the run dir is correctly
    excluded** → non-zero. Pair with case (i) as a positive/negative couple; case
    (i) alone passes trivially against a gate that matches nothing.
- Two further cases for requirements (f) and (n):
  - (x) **a `.loops/tmp/scratch/foo-1234.txt` write and a `.ll/decisions.d/x.json`
    write, in a repo whose `.gitignore` covers neither `.loops/` nor `.ll/`** →
    exit 0. Proves requirement (f)'s directory-wide exclusions, not just a
    `run_dir`-relative one; without the `.loops/` half the scratch-pad hook fails
    every run in a consuming project, and without the `.ll/` half a decision
    fragment written mid-run does the same in *this* repo.
  - (xi) **on a violation, `${run_dir}/.scope_violations.txt` exists and names the
    offending path(s)**; on a pass it exists and is empty. Requirement (n) — the
    artifact `diagnose` reads.
- One case for (d), now **unconditional** given that requirement's decision:
  - (xii) **a pre-existing untracked file (present in the baseline) overwritten in
    place, outside the run dir** → non-zero. This is the case a name-only set
    difference passes green, and the direct analogue of
    `test_untracked_file_content_edit_resets_counter`
    (`test_builtin_loops.py:3081-3096`).
- One case for (b), on `init` rather than the gate:
  - (xiii) **`init`'s stdout is exactly one line**, asserted both in a git repo and
    in a non-repo directory (where all three new git commands fail). Extract
    `init`'s action the same way, run it, and assert
    `len(stdout.strip().splitlines()) == 1` and that the line is the run dir.
    Guards the `capture:` contract per (b); a second line silently redirects every
    downstream state's reads and writes to a garbage path.

  Note macOS resolves `tmp_path` under `/private/var/...` while `$(pwd)` may report
  `/var/...` — normalize both sides in the helper or these cases flake per-platform
  (requirement (k)(3)).

_Wiring pass added by `/ll:wire-issue`:_
- `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`
  (`scripts/tests/test_builtin_loops.py:16206-16218`, class starts 16104) —
  iterates **every** file in `BUILTIN_LOOPS_DIR.rglob("*.yaml")`, including
  `workflow-generator.yaml`, and asserts no new WARNING-severity finding
  appears in any of 10 ratcheted categories unless present in `ALLOWLIST`
  (lines 16138-16177, keyed by `(loop_stem, category) -> {warning_paths}`). No
  `("workflow-generator", ...)` entry currently exists.

  **Narrowed by the 2026-08-27 review pass:** `no-scope` is a non-risk — the
  loop already declares `scope:` (`workflow-generator.yaml:29-31`) covering
  `${context.run_dir}`, and `.scope_violations.txt` is written inside it. The
  live category to watch is **`partial-route`**, if the new state's `on_yes`
  lands before `on_no` is wired. If it trips, either the wiring needs fixing
  or an `ALLOWLIST` entry must be added with this issue ID as justification,
  per the table's own convention.
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

_Test-harness research (relocated 2026-08-26 from a stray trailing `## Tests`
section; `## Tests` is not part of the FEAT template):_
- **No shared FSM shell-action test harness utility exists anywhere in
  `scripts/tests/`.** The "extract action from parsed YAML, substitute
  `${context.*}` via `.replace()`, run via `subprocess.run(['bash','-c',...])`,
  assert `returncode`" pattern is independently duplicated per-file across at
  least 13 test files (`test_builtin_loops.py`, `test_general_task_loop.py`,
  `test_incremental_refactor_loop.py`, and others) — `conftest.py` has no such
  fixture or mixin. The new `check_intent_scope` test class should follow this
  same per-file duplication convention (matching
  `TestGeneralTaskFinalVerifySpinGateShellAction`'s shape), not attempt to
  extract or reuse a shared utility that does not exist.
- **Anchors re-verified 2026-08-26, all current**:
  `TestGeneralTaskFinalVerifySpinGateShellAction` line 2996
  (`_init_repo`/`_run_gate`/`_make_run_dir` at 3009/3027/3036),
  `test_pipeline_states_exist` 17733, `test_validation_gates_are_exit_code`
  17793, `test_run_dir_used_throughout` 17813,
  `test_diagnose_mentions_both_retry_exhaustion_paths` 18046. Earlier passes
  recorded several of these differently; these supersede.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the gate, plus a plainly-stated
  limits list so it is not mistaken for whole-pipeline enforcement:
  1. the one-shot window (Expected Behavior),
  2. the gitignored-write blind spot (g),
  3. the human-concurrent-edit false positive (h),
  4. the wholesale exclusion of the `.loops/` and `.ll/` harness-state
     directories (f) — anything a loop writes there is unaudited by design.

  The in-place-overwrite hole is **not** on this list: requirement (d) closes it
  by decision.

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
  - `init` (lines 44-61): `action_type: shell`, no `evaluate:` block, flows via bare `next: capture_intent`. No existing `git rev-parse HEAD`, `git rev-parse --show-toplevel`, or `git ls-files -o --exclude-standard` — all three must be added fresh. The state currently has no `ROOT` variable at all, only `DIR`.
  - `validate_intent` (lines 99-119): `action_type: shell`, `evaluate: {type: exit_code}`, `on_yes: sketch_state_graph` (line 118), `on_no: count_intent_retry` (line 119). `on_yes` is the exact edge to retarget to `check_intent_scope`.
  - ~~`max_steps` (line 32) is currently **40, not 45**.~~ **Stale — superseded.** Re-verified 2026-08-26 against the current file: `max_steps: 45` at line 32. See Proposed Solution (m).
- **`general-task.yaml` baseline/diff precedent, exact shape**: `check_baseline_tests` (line 76) writes `baseline-ref.txt` via `git rev-parse HEAD > "${context.run_dir}/baseline-ref.txt" 2>/dev/null || echo "" > ...`, action_type shell, no evaluate block (flows via bare `next`). Downstream states read the file rather than re-deriving HEAD. `check_provisional_markers` (lines 841-864) and `final_verify_spin_gate` (lines 377-447) both use this baseline but their evaluators are `output_json` (`.markers_found` eq 0) and `output_numeric` (lt `${context.max_final_verify_spins}`) respectively — **neither uses `evaluate: {type: exit_code}`** as the Integration Map's "Similar Patterns" implies for the exit_code precedent; the `exit_code` evaluator precedent for this new state instead comes from `workflow-generator.yaml`'s own lowering-pass gates (`validate_intent`, `validate_sketch`, etc.), which are already all `action_type: shell` + `evaluate: {type: exit_code}` — and, in `validate_intent`'s case, `action_type: shell` wrapping a `python3 -c` body, which is the precedent requirement (e) follows.
- **Untracked-set exclusion precedent, exact form**: `final_verify_spin_gate`'s `untracked() { git ls-files -o --exclude-standard -z -- . ':(exclude).loops/'; }` (lines 407-439) diffs untracked files by **both path and content hash** (`xargs -0 git hash-object`), not path alone — a name-only untracked listing is called out as insufficient by that state's own tests.
- **No-git escape precedent, exact form**: `check_provisional_markers` (lines 841-864): `if [ -z "$BASELINE_REF" ] || ! git rev-parse --git-dir >/dev/null 2>&1; then printf '...skipped: true...'; exit 0; fi` — confirms the recommended fail-open-with-warning shape for requirement (j). Contrast: `mechanize-skills.yaml`'s `snapshot_baseline` dirty-worktree check (lines 189-217) instead `exit 1`s to a distinct `on_no: record_skip` branch — a different escape shape used because that gate is wrapped by a routing decision, not a direct `exit_code` evaluator. Since `check_intent_scope` uses `evaluate: {type: exit_code}` directly (per `test_validation_gates_are_exit_code`), the `exit 0`-fail-open shape is the applicable precedent, not the `exit 1`/skip-branch shape.
- **No existing symlink-resolution utility**: a codebase-wide grep for `realpath|resolve\(|relative_to\(` under `scripts/little_loops/` found no existing utility for resolving symlinks before a path-containment comparison (the 29 hits found are unrelated: config/artifact/issue paths). Requirement (k)(3)'s `/tmp` vs `/private/tmp` normalization must be written fresh for this gate — as `os.path.realpath` inside the `python3` body, per (e).
- **`realpath` is rejected for absolute-path capture by `.ll/decisions.yaml` `ARCHITECTURE-087` (BUG-2435)**, which selects the `case "$DIR" in /*) ... esac` idiom already used by `workflow-generator.yaml`'s own `init` over `realpath` canonicalization, citing 4 prior consumption-site precedents. This decision governs the *capture* of `run_dir` as absolute in shell, not the *symlink-resolution* step in the comparison itself (previous bullet) — the two are distinct concerns, only the latter is unaddressed by existing convention, and requirement (e)'s Python body keeps them cleanly separated.
- **Exact test anchors**: `test_validation_gates_are_exit_code` (`scripts/tests/test_builtin_loops.py:17783-17791` parametrize, def 17793) lists `["validate_intent", "validate_sketch", "validate_evaluators", "validate_routing", "validate_artifact"]` — add `"check_intent_scope"`. `test_pipeline_states_exist`'s `required` set literal (`scripts/tests/test_builtin_loops.py:17734-17760`, 25 states, already including `count_intent_retry` from BUG-3327) does not include `check_intent_scope` — add it there too.
- **FSM interpolation engine location**: `scripts/little_loops/fsm/interpolation.py`, `interpolate()` (lines 209-287). `ESCAPED_PATTERN = re.compile(r"\$\$\{")` (line 29) is substituted to a placeholder before `VARIABLE_PATTERN` (`\$\{([^}]+)\}`, line 28) resolves real `${namespace.path}` refs, then the placeholder is restored to a literal `${` (line 285) — confirming `$${ID}` survives as literal `${ID}` for bash, and a bare `${LOCAL_VAR}` raises `InterpolationError` ("expected namespace.path", lines 261-264) because it has no `.` separator. The `common.yaml:459-460` `$${ID}` precedent cited in the issue is real.
- **Test harness precedent, exact class**: `TestGeneralTaskFinalVerifySpinGateShellAction` (`scripts/tests/test_builtin_loops.py`, class starts line 2996) extracts `data["states"][name]["action"]` from parsed YAML (never re-typed), substitutes `${context.run_dir}` via plain Python `.replace()` (not the FSM interpolation engine), and runs via `subprocess.run(["bash", "-c", script], cwd=repo, ...)`. Helper `_init_repo` (builds temp repo + baseline commit + `baseline-ref.txt`) at 3009, `_run_gate` (extracts+substitutes+runs) at 3027, `_make_run_dir` at 3036 — this is the shape Implementation Step 7/behavioral test cases should follow.

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Line numbers have drifted since the first 2026-08-27 research pass** (BUG-3327's landing shifted content in both target files):
  - `workflow-generator.yaml`: `init` is now lines 44-61 (ends `capture: run_dir` at 60, `next: capture_intent` at 61); `capture_intent` (63-97) now carries the BUG-3327 fence wrapping `${context.description}`; `validate_intent` is now lines 99-119; `max_steps` is confirmed **already 45** at line 32 — Implementation Step 6 is a verification-only no-op, not a change.
  - `test_builtin_loops.py`: `test_pipeline_states_exist` def line 17733; `test_validation_gates_are_exit_code` parametrize 17783-17791; `TestGeneralTaskFinalVerifySpinGateShellAction` class at 2996 with helpers at 3009/3027/3036.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` gained a new "Fencing a User-Authored Brief/Goal" section (lines 625-676) from BUG-3327, documenting the fence mechanism (`fence.py`) — this is pure net-new prose adjacent to where this issue's gate documentation belongs; it does not mention `check_intent_scope` or runtime containment and requires no reconciliation, only a new adjacent subsection per Implementation Step 9.

## Acceptance Criteria

- [ ] `check_intent_scope` exists as its own `action_type: shell` /
      `evaluate: {type: exit_code}` state, with `on_yes: sketch_state_graph` and
      `on_no: diagnose` — **not** `capture_intent` and not `count_intent_retry`.
- [ ] The gate body is a `python3 -c` script per (e), matching `validate_intent`'s
      existing shape in this loop.
- [ ] `validate_intent.on_yes` targets `check_intent_scope`;
      `validate_intent.on_no` is still `count_intent_retry`.
- [ ] `init` resolves `ROOT` via `git rev-parse --show-toplevel` and writes
      `baseline-ref.txt` and the untracked baseline, all git calls via
      `git -C "$ROOT"`, and its stdout contract (`capture: run_dir`) is unchanged.
- [ ] `init`'s statement order is: existing `mkdir`/truncate block → `ROOT` +
      baseline capture → the `case`/`echo` stdout block last (requirement (a1)).
      Case (v) is the regression guard.
- [ ] `init` emits **exactly one line** on stdout — asserted in a git repo and in
      a non-repo, where all three git commands fail (requirement (b), case (xiii)).
- [ ] `init`'s baseline capture and the gate's current-set capture carry matching
      `# HARNESS:` comments identifying them as a deliberate matched pair, and use
      byte-identical invocations including both `':(exclude)'` pathspecs
      (requirement (c)).
- [ ] The untracked baseline is **content-hashed** (`path -> hash`), not name-only,
      and case (xii) passes (requirement (d)).
- [ ] Git enumeration is NUL-delimited (`-z`) end to end, with the set difference
      computed in Python (requirement (e)).
- [ ] A run dir **outside the worktree** gates normally — clean → exit 0,
      planted out-of-scope write → non-zero (cases (viii)/(viii-b)). It must
      **not** take the skip-with-warning escape.
- [ ] A git repo with **zero commits** takes the skip-with-warning escape
      (case (vi-b)), via the two-clause
      `[ -z "$BASELINE_REF" ] || ! git rev-parse --git-dir` check.
- [ ] Every git invocation in `init` and the gate is root-scoped (`-C "$ROOT"`),
      with no cwd-relative `-- .` pathspec.
- [ ] The gate's exclusions cover `.loops/` **and** `.ll/` as whole directories and
      do not rely on ambient gitignore (requirement (f), case (x)).
- [ ] On violation the gate exits non-zero, prints the offending paths, and
      writes them to `${run_dir}/.scope_violations.txt`; on pass that file exists
      and is empty.
- [ ] `diagnose` reads `.scope_violations.txt`, names the scope-violation failure
      path, and carries the BUG-3327 no-stray-writes fence clause.
- [ ] Non-git directory and zero-commit repo both exit 0 **with a warning on
      stdout**, and the warning text is asserted (a bare exit 0 is
      indistinguishable from the always-green bug). Run-dir-outside-the-worktree
      is **not** in this set — see the criterion above.
- [ ] A pre-existing untracked file present before `init` does not trip the gate.
- [ ] Behavioral cases (i)–(xiii) all pass, including the mandatory negative
      partners (vii-b), (viii-b) and (ix), and (xii).
- [ ] **The gate has been observed red** against a deliberately planted
      out-of-scope write in a live `workflow-generator` run, launched from a repo
      subdirectory with a dirty working tree — not merely green in CI.
- [ ] `ll-loop validate` clean; full `python -m pytest scripts/tests/` exits 0
      (including `TestValidatorWarningBudget`, with any new `ALLOWLIST` entry
      justified by this issue ID — `partial-route` is the category to watch;
      `no-scope` is a non-risk since the loop already declares `scope:`).
- [ ] `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` documents the gate and all
      **four** limits: the one-shot window, the gitignored-write blind spot (g),
      the human-concurrent-edit false positive (h), and the wholesale `.loops/` /
      `.ll/` exclusion (f). The in-place-overwrite hole is not among them —
      requirement (d) closes it. `docs/reference/loops.md`'s state-graph diagram
      includes the new state and its `on_no -> diagnose` branch.

## Program Design

### Signatures

- `init.action: str` — additionally resolves `ROOT` and writes `baseline-ref.txt`
  plus the content-hashed untracked baseline; its stdout contract
  (`capture: run_dir`) is unchanged. Two independent ordering invariants apply:
  **sole stdout writer** (`capture` stores the state's *entire* stdout —
  `executor.py:2370-2372`, `result.output.rstrip("\n\r")` — so every new command
  redirects stdout to a file or into `$(…)`, and stderr to `/dev/null`; see (b) and
  case (xiii)), and **baseline-after-scaffolding** (the capture follows the
  existing `mkdir`/truncate block, or `init`'s own run-dir files read as
  out-of-scope writes; see (a1) and case (v)).
- `check_intent_scope() -> int` — **new** shell state wrapping a `python3 -c`
  body; exits non-zero if the changed-file set since `init` is not a subset of
  `${captured.run_dir.output}`

### Call Path

`init` (resolves `ROOT`, writes both baselines) -> `capture_intent` ->
`validate_intent` (`on_yes: check_intent_scope` / `on_no: count_intent_retry`) ->
`check_intent_scope` (`on_yes: sketch_state_graph` / `on_no: diagnose`)

**Correction (2026-08-26 refine pass):** `validate_intent`'s `on_no` edge is
`count_intent_retry`, not `capture_intent` — BUG-3327 added a bounded retry
state between `validate_intent` and `capture_intent` (default
`context.max_intent_retries: "3"`). This issue's edit retargets only
`on_yes`; `on_no` is left as `count_intent_retry`, unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Confirmed exact current YAML for the insertion boundary (`scripts/little_loops/loops/workflow-generator.yaml`):
  ```yaml
  validate_intent:
    action_type: shell
    action: |
      set -o pipefail
      python3 -c "
      import yaml
      d = yaml.safe_load(open('${captured.run_dir.output}/intent.yaml'))
      assert d.get('name'), 'name is empty'
      ...
      " 2>&1 | tee "${captured.run_dir.output}/.intent_errors.txt"
      RC=$?
      [ "$RC" -eq 0 ] && : > "${captured.run_dir.output}/.intent_errors.txt"
      exit "$RC"
    evaluate:
      type: exit_code
    on_yes: sketch_state_graph   # retarget to check_intent_scope
    on_no: count_intent_retry
  ```
  This is also the direct shape precedent for requirement (e): `action_type: shell`
  wrapping a `python3 -c` body with an `exit_code` evaluator, plus the
  truncate-error-file-on-pass idiom requirement (n) mirrors for
  `.scope_violations.txt`.
- `init` (lines 44-61) currently ends with the `case "$DIR" in /*) ... esac` block as its last action lines, `capture: run_dir`, plain `next: capture_intent` (no evaluate block).
- The `evaluate: {type: exit_code}` shape for `check_intent_scope` matches `workflow-generator.yaml`'s own existing lowering-pass gates (`validate_intent`, `validate_sketch`, `validate_evaluators`, `validate_routing`, `validate_artifact` — all shell+exit_code), not `general-task.yaml`'s `check_provisional_markers`/`final_verify_spin_gate`, which use `output_json`/`output_numeric` respectively despite sharing the same baseline-diff shape. `check_intent_scope`'s escape-hatch behavior (non-repo, zero commits) should therefore signal via the script's own `exit 0`, not a JSON payload field.

## Implementation Steps

1. Add `ROOT` resolution and both baseline captures to `init` (lines 44-61),
   following `general-task.yaml:76`'s `git rev-parse HEAD > baseline-ref.txt`
   idiom plus a content-hashed `git ls-files -o --exclude-standard -z` snapshot
   per (d) — all via `git -C "$ROOT"` per (k)(1b), with both `':(exclude)'`
   pathspecs from (f), written as an explicitly-commented matched pair with the
   gate per (c). **Placement matters twice**: after the existing
   `mkdir`/truncate block per (a1), and before the `case`/`echo` block, which
   stays last and alone. Redirect every new command's stdout to a file (or into
   `$(…)`) and stderr to `/dev/null` so `init` stays the sole stdout writer per
   (b).
2. Add the `check_intent_scope` state as a `python3 -c` body per (e) — the
   `.loops/`/`.ll/`-wide exclusions from (f) as the primary mechanism, the
   root-scoped enumeration from (k)(1b), the non-repo/zero-commit escape from
   (j), and the residual `$VAR` brace handling from (l) in the shell preamble.
   Add the repo-root relativization from (k)(1) and `os.path.realpath`
   normalization from (k)(3) as a **guarded branch** for a non-default
   in-worktree `--run-dir`, per the scope note in (k). Handle
   outside-the-worktree by dropping the run-dir pathspec and gating normally per
   the corrected (k)(2) — **not** by escaping.
3. Retarget `validate_intent`'s `on_yes` (line 118) to it. Leave
   `on_no: count_intent_retry` (line 119) untouched.
4. Have the gate write `${run_dir}/.scope_violations.txt` per (n) — truncated to
   empty on a pass, mirroring `validate_intent`'s `.intent_errors.txt`; add that
   file to `diagnose`'s read list and add the scope-violation path to
   `diagnose`'s failure enumeration.
5. Add the fence clause to `diagnose`'s prompt per (o).
6. Verify `max_steps` is 45 per (m) — expected to be a no-op.
7. Add the tests above (cases i–xiii, plus the state-set, exit_code-shape,
   routing-edge, `run_dir`-usage and `diagnose`-text test updates). Case (xiii)
   targets `init`, not the gate; case (v) doubles as the (a1) ordering guard.
8. Verify with `ll-loop validate`, plus a re-run of `workflow-generator` **from a
   deliberately dirty working tree and from a repo subdirectory**, confirming that
   pre-existing untracked files do not trip the gate and that the gate still fires
   on a deliberately planted out-of-scope write **placed outside the invocation
   subdirectory**. **A green gate proves nothing until you have seen it go red.**
9. Document the gate and its four limits: the one-shot window, the
   gitignored-write blind spot (g), the human-concurrent-edit false positive (h),
   and the wholesale `.loops/`/`.ll/` exclusion (f).

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
  `ALLOWLIST` entry for `("workflow-generator", "partial-route")` only if the
  new state actually trips it. `no-scope` is a non-risk (the loop declares
  `scope:` at lines 29-31).
- **Required (promoted from "consider" by requirement (n)):** extend
  `diagnose`'s action text — read list *and* failure enumeration — to cover
  `check_intent_scope` / `.scope_violations.txt`, and extend
  `test_diagnose_mentions_both_retry_exhaustion_paths`
  (`test_builtin_loops.py:18046-18052`) to assert it. This matches the existing
  convention of `diagnose` enumerating every failure path that routes to it;
  without it an operator hitting a scope violation gets a diagnostic about
  retry exhaustion, which is the wrong story. Rename the test if its
  "both_retry_exhaustion_paths" name no longer describes what it asserts.

## Impact

- **Priority**: P3 — defense-in-depth. BUG-3327's fence removes the cause; this
  catches regressions and the classes the fence does not cover.
- **Effort**: Medium — one new state, `ROOT` resolution plus two `init` baselines,
  root-scoped enumeration, a guarded relativization branch, one escape path (no
  repo / no commits), a violation report artifact plus `diagnose` edits, and
  fourteen behavioral test cases
- **Risk**: Medium — the gate can misfire in **both** directions: a false positive
  routes to `diagnose` and fails the run, while a path-space mismatch
  (requirement (k)) yields a gate that is permanently green and reports safety it
  is not checking. The second failure is the more dangerous one because nothing
  surfaces it. That is why the dirty-tree baseline (a), the `init` ordering (a1)
  and stdout-purity (b) constraints, the escape path (j), the relativization (k),
  and the red-gate test case are requirements, not polish — and why the gate must
  not route back to `capture_intent`.

  Three of the always-green variants are pinned by mandatory negative test
  partners rather than left to review: (vii-b) for cwd-scoped enumeration,
  (viii-b) for the outside-the-worktree escape, and (ix) for the exclusion
  pathspec. Each of their positive partners passes trivially against the
  corresponding broken gate, so the pairs are not optional.

  Two decisions lower this risk relative to the original framing. The (k)-scope
  note: the default `run_dir` (`.loops/runs/…`) is covered by the `.loops/`
  exclusion alone, so the relativization code most likely to be subtly wrong is
  also the code that almost never runs. And requirement (e)'s `python3` body:
  the set difference, content hashing, and symlink normalization become library
  calls instead of hand-rolled shell, which is where the subtle always-green
  failures were most likely to originate.
- **Breaking Change**: No

## Scope

`workflow-generator`-only. The gate depends on that loop's `init`/`run_dir`
structure, and the other four loops BUG-3327 fences are not all meta-loops with the
same artifact-isolation contract. Generalizing it is a separate question.

## Notes

Split from BUG-3327 on 2026-08-26 (Proposed Solution §2 and its associated
requirements, tests, and Impact analysis moved here verbatim). BUG-3327 retains the
brief-fencing work.

**Pre-implementation review pass, 2026-08-27.** Five changes:
1. `init` had no `ROOT` variable, though the ACs mandated `git -C "$ROOT"` —
   added as an explicit precondition in (a).
2. New requirement (a1): the baseline capture must follow `init`'s existing
   `mkdir`/truncate block, or the loop's own scaffolding reads as out-of-scope
   writes in any project that does not gitignore the run dir. Case (v) is the
   guard.
3. The (a) sketch lacked the exclusion pathspec that (c) requires on both sides;
   made symmetric.
4. The two open decisions — content-hash vs name-only (d), and delimiter (e) —
   are resolved rather than deferred to implementation: content-hashed baselines,
   NUL-delimited git output, and a `python3 -c` gate body. That decision also
   discharges (k)(3) and most of (l), and makes case (xii) unconditional.
5. `.ll/` added to the exclusion set (f) — this repo gitignores it only as a list
   of individual entries, so `.ll/decisions.d/` fragments would trip the gate.
   The `no-scope` warning-budget watch is narrowed to `partial-route`.

Requirements were renumbered sequentially (a)–(p) in the same pass; the previous
labels ran `(a) (a1) (a3) (a4) (a2) (b) (b2) (b3) (c) (d) (e) (f) (g) (i) (j) (h)`.
Mapping for anyone holding an older reference: `a1->b`, `a2->c`, `a3->d`, `a4->e`,
`b->f`, `b2->g`, `b3->h`, `c->i`, `d->j`, `e->k`, `f->l`, `g->m`, `i->n`, `j->o`,
`h->p`. The new `(a1)` is net-new content, not the old one.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §4, §5 R5.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-08-27T02:20:19 - `0cce9f36-f0aa-4271-8573-3bd29b6d01a6.jsonl`
- `/ll:wire-issue` - 2026-08-27T01:49:46 - `b4592890-2b63-4442-b15e-89282998dd3d.jsonl`
- `/ll:refine-issue` - 2026-08-27T01:43:27 - `981cfc8c-efe7-4751-8804-dd1eed392dab.jsonl`
- `/ll:refine-issue` - 2026-08-27T01:12:54 - `fb4eed07-2702-4aea-a748-78fa07142d55.jsonl`
