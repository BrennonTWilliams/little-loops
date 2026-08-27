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
cases"; successive review passes raised it to eleven, then fourteen, then
**nineteen** when the never-counted mandatory negative partners were included and
the tracked-dirty and deletion cases added. The 2026-08-27 **third** review pass
adds two more — (vii-c) for the subdirectory-launch run dir and (xiv) for the
falsy-`{}` baseline — giving **twenty-one**: (i)–(xiv) plus the seven `-b`/`-c`
partners (iv-b, vi-b, vii-b, vii-c, viii-b, xii-b, xii-c). The 2026-08-27
**fifth** pass adds (xv) for the sibling-named-path prefix filter — **twenty-two**
total. See Integration Map → Tests.)

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

**One limit of this placement, to state rather than silently accept:**

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
BUG-3327 has landed (`status: done`, commit `34c3ecac9`) and bounded
`validate_intent`'s `on_no` edge with `count_intent_retry`
(`workflow-generator.yaml:119`, default `context.max_intent_retries: "3"`,
mirroring `count_emit_retry`). An earlier draft listed that unbounded edge as a
second limit of this placement; it is resolved, with no residual work for this
issue.

## Use Case

A little-loops maintainer runs `ll-loop run workflow-generator` from a
subdirectory of the repo, with a working tree that already holds a few
untracked scratch files **and a couple of half-finished edits to tracked source
files**, to generate a new loop from a natural-language brief.
Partway through `capture_intent`, the LLM state decides it needs to "do some
research first" and writes notes to `research/` at the repo root — outside the
run directory, into the maintainer's actual source tree.

Today nothing notices: the run continues, the loop is emitted, and the stray
files are discovered later by `git status` (or not at all, if the path happens
to be gitignored) with no record of which run produced them. With
`check_intent_scope`, the run stops at the gate immediately after
`validate_intent`, `${run_dir}/.scope_violations.txt` names `research/…`, and
`diagnose` reports a containment violation rather than a retry-exhaustion
story. The maintainer's pre-existing untracked scratch files and dirty tracked
sources do not trip the gate, and legitimate `run_dir`, `.loops/tmp/scratch/` and `.ll/` harness writes
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

**(a) Baseline the entire changed-file set at `init` — tracked *and* untracked —
don't assume a clean tree.** A developer's working tree routinely holds
pre-existing untracked files *and* pre-existing modifications to tracked files.
Without a baseline the gate fires on the *first* pass of every run in a dirty repo
— and since the offending files are not the loop's to remove, the failure is
permanent.

**Revised 2026-08-27 (second review pass): the baseline is one unified
`path -> content-hash` map covering both sides, not an untracked-only snapshot.**
The previous formulation baselined only the untracked set and compared tracked
files via a bare `git diff --name-only "$BASELINE_REF"` with **no baseline
subtraction at all**. That is the same permanent-false-positive failure this
requirement exists to prevent, applied asymmetrically: a maintainer with any dirty
tracked file — the normal state of a working repo — failed the gate on the first
pass of every run. It also directly contradicted the live-verification acceptance
criterion, which requires a red-gate run "from a repo subdirectory with a dirty
working tree": as previously written, that run failed for the wrong reason.

Note this is *not* the case requirement (h) accepts. (h) covers a human editing a
file **concurrently with** an in-flight run; this is the state of the tree **at
launch**, which is fully knowable at `init` and must be subtracted.

The unified construct. Define one changed-set function used byte-identically at
both sites (see (c)):

```
EXCL  = ':(exclude,glob)**/.loops/**' ':(exclude,glob)**/.ll/**'
paths = (git -C "$ROOT" diff --name-only -z "$REF" -- $EXCL)
      ∪ (git -C "$ROOT" ls-files -o --exclude-standard -z -- $EXCL)
map   = { p: hash(p) if p exists else DELETED  for p in paths }
```

where `DELETED` is a sentinel for a path git reports but which is absent from the
worktree. `init` writes this map; `check_intent_scope` recomputes it and flags
**any path whose entry is new, whose value differs, or whose baseline key is
absent from the current map** — the comparison is symmetric, not a one-way scan
of the current map. The third clause is load-bearing (added 2026-08-27, fourth
review pass): `git ls-files -o` enumerates the filesystem, so a deleted
pre-existing *untracked* file appears in **neither** current-side enumeration and
the `DELETED` sentinel can never fire for it — the sentinel only fires on the
tracked side, where `git diff` still reports the path. Without the
baseline-key-absent clause the rule as previously written could not catch case
(xii-c), the exact case the sentinel was added for. At `init` the `$REF` side
is a no-op against a freshly-read `HEAD`, so the map at that moment is exactly
"what the maintainer already had dirty."

**Hashing is `hashlib` over the file bytes inside the `python3` body — DECIDED
2026-08-27 (fourth review pass), superseding the earlier batched
`git hash-object --stdin-paths` instruction.** `--stdin-paths` has no `-z` mode
(verified against git 2.52: it is newline-delimited only), so feeding it the
NUL-split path list reintroduces exactly the embedded-newline breakage (e)'s
NUL-everywhere decision exists to prevent — a path containing a newline splits
into two bogus lines and misaligns the hash column. `hashlib` is stdlib,
delimiter-free, one fewer subprocess (satisfying (b)'s stdout-purity for free),
and byte-exact with no CRLF-filter surprises. Git-blob-compatible hashes buy
nothing: the map is only ever compared against itself. A per-path
`subprocess.run(["git","hash-object",p])` remains prohibited — it spawns N
processes per run at both sites.

**Hash reads must tolerate two failure modes (added 2026-08-27, fifth review
pass), mapping both to the `DELETED`/unreadable sentinel rather than raising:**
(1) `FileNotFoundError` — a path can vanish between enumeration and hashing
(TOCTOU; live during real runs, where an agent writes and removes files
concurrently with the gate); (2) `IsADirectoryError` — `git diff --name-only`
reports a dirty **submodule** entry as its path, which is a directory on disk.
The failure is not loud if unhandled: an uncaught exception in `init`'s body
lands in the `|| : > "$DIR/baseline-changed-set.json"` fallback, truncating the
baseline to zero bytes — which the gate then reads as "no usable baseline" and
**skips with a warning**. A crash in the hasher silently disables the gate.
Catch `OSError` around the read; sentinel and continue.

**The exclusion pathspecs are depth-agnostic globs, not root-anchored prefixes** —
see requirement (f), where the reason is spelled out. `':(exclude).loops/'` matches
only `<root>/.loops/`, which is the wrong set.

This single construct subsumes three previously separate requirements and closes a
fourth hole that was never written down:

- **(d)** in-place overwrite of a pre-existing *untracked* file — a value change in
  the map.
- **(i)** cover untracked and tracked — the union is the point.
- the new tracked-dirty case above — a value change, not a bare name match.
- **deletions, previously unhandled and silently green.** A path-set difference
  that only looks for newly-appeared entries never notices an agent *deleting* a
  pre-existing untracked file outside `run_dir`: the set gets smaller, and the gate
  passes. A *tracked* deletion is caught by the `DELETED` sentinel (`git diff`
  still reports the path; the worktree file is gone). An *untracked* deletion is
  caught by the symmetric comparison's baseline-key-absent clause — the sentinel
  cannot fire for it, since no current-side enumeration reports the path at all.

`init` (lines 44-61) must first resolve the repo root — it currently has no
`ROOT`, only `DIR`, so this is net-new and is a precondition of every other git
invocation in the state:

```sh
# HARNESS: repo root for every git call in init and check_intent_scope. The
# two sites are a matched pair (see requirement (c)); keep them identical.
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=""
```

then capture the ref and the unified map:

```sh
if [ -n "$ROOT" ]; then
  git -C "$ROOT" rev-parse HEAD > "$DIR/baseline-ref.txt" 2>/dev/null || : > "$DIR/baseline-ref.txt"
  # HARNESS: unified changed-set baseline (tracked ∪ untracked, path -> hash).
  # Matched pair with check_intent_scope (requirement (c)) — keep identical.
  python3 -c '<changed-set map, argv: ROOT, REF>' "$ROOT" "$(cat "$DIR/baseline-ref.txt")" \
    > "$DIR/baseline-changed-set.json" 2>/dev/null || : > "$DIR/baseline-changed-set.json"
else
  : > "$DIR/baseline-ref.txt"
  : > "$DIR/baseline-changed-set.json"
fi
```

The map is emitted as JSON so the gate loads it with `json.load` rather than
re-parsing a NUL stream; per (e) both sides are Python, so this costs nothing and
removes a second parsing surface.

**The escape condition is a property of the *file*, not the truthiness of the
loaded value.** The gate takes (j)'s skip-with-warning escape when
`baseline-changed-set.json` is **missing, zero bytes, or raises
`json.JSONDecodeError`** — a corrupt baseline must not read as "the tree was
clean." It must **not** escape on a falsy *value*: a genuinely clean tree
serializes as `{}`, which is falsy in Python, so `if not baseline: skip` silently
disables the gate on exactly the runs where it is most likely to catch something.
Write the check as a file-level test (`os.path.getsize(...) == 0`, `FileNotFoundError`,
`JSONDecodeError`) and let `{}` flow through as a valid empty baseline. Behavioral
case (xiv) is the guard.

**(a1) Ordering inside `init` is a three-way constraint, not just "keep the
`case`/`echo` block last."** `init`'s existing body creates run-dir state before
anything else — `mkdir -p "$DIR"`, `mkdir -p "$DIR/probes"`,
`: > "$DIR/.emit_errors.txt"`, `: > "$DIR/.intent_errors.txt"`. **The baseline
capture must run after that block.** Captured before it, those files are absent
from the baseline and read as newly-appeared untracked writes — so in any project
that does not gitignore the run dir (exactly behavioral case (v)) the gate fires
on the loop's own scaffolding, permanently, on every run. The required order in
`init` is:

1. existing `mkdir` / truncate / `rm -f` block (creates run-dir state), **extended
   with `: > "$DIR/.scope_violations.txt"`** — see below
2. `ROOT` resolution, `baseline-ref.txt`, and the unified changed-set map
   (this requirement and (a))
3. the `case "$DIR" in /*) … esac` stdout block, last and alone (requirement (b))

**`.scope_violations.txt` is truncated in step 1, not created first by the gate.**
`init` already pre-truncates `.emit_errors.txt` and `.intent_errors.txt`; the
violation report is the same class of artifact and gets the same treatment, so the
run-dir contract is uniform and a file left behind by an earlier run sharing the
directory cannot be read as this run's finding. `diagnose`'s read list is phrased
"whichever of these exist," so absence is already tolerated — this is about
staleness, not absence. Being part of step 1, it is also inside the baseline per
this requirement's ordering.

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

**This obligation extends *inside* the `python3` body, not just to the shell
level.** The `changed_set` construct shells out to git several times; a
`subprocess.run(...)` or `subprocess.call(...)` without `capture_output=True` (or
an explicit `stdout=PIPE, stderr=DEVNULL`) **inherits `init`'s stdout**, so a git
advisory — a `detached HEAD` notice, a `safe.directory` warning —
lands in `capture: run_dir` even though the shell-level redirect looks correct.
Every git call inside the body captures both streams; nothing but the final
`case`/`echo` block reaches fd 1.

**(c) `init`'s baseline and the gate's current-set capture are a matched pair,
not two independent captures.** The set difference is meaningful only if both
sides were produced by the *identical* invocation — same `-C "$ROOT"`, same
pathspec (including both exclusions), same `--exclude-standard`, same `-z`, same
hashing rule and same `DELETED` sentinel. Any drift between the two sites (e.g.
adding an exclusion to one only) makes previously-baselined files read as
newly-appeared, i.e. a permanent false positive. Write the two commands as a
deliberate pair and say so in a `# HARNESS:` comment at both sites.

**Made structural by (a)'s revision.** Because both sides now compute the *same*
unified `path -> hash` map, the pair is one function invoked twice rather than two
hand-matched command lines — the strongest available form of this requirement.
Emit that function as a single shared literal (the `python3 -c '…'` body from (e),
identical text at both sites, differing only in argv) so drift requires editing two
visibly identical blocks rather than two superficially different ones.

The exclusion pathspec belongs on **both** sides, not gate-side only. An earlier
draft of (a) sketched the baseline without it; that happened to work by accident
(the difference cancels) but left the pair asymmetric, so any later edit to one
side would silently break it.

**Enforced by test, not only by comment convention (added 2026-08-27, fifth
review pass):** a structural test extracts the `action` strings of `init` and
`check_intent_scope` from the parsed YAML, slices the single-quoted
`python3 -c '…'` body out of each, and asserts **byte equality**. That converts
this requirement from reviewable to enforced — the strongest available drift
guard for the construct the entire comparison depends on. See Integration Map →
Tests.

**(d) In-place overwrite of an untracked file — DECIDED: content-hash the
baseline. SUBSUMED BY (a); implement (a) and (d) falls out.**

A path-name-only set difference flags only *newly appeared* untracked paths, so an
agent that clobbers a **pre-existing** untracked file outside `run_dir` leaves the
path set unchanged and the gate passes green. (a)'s unified `path -> hash` map
closes this as one value-change among several. Precedent:
`general-task.yaml:424-429`'s `untracked()` diffs by both path and content hash
(`xargs -0 git hash-object`), and `test_untracked_file_content_edit_resets_counter`
(`test_builtin_loops.py:3081-3096`) exists to assert a name-only listing is
insufficient. Consequences that are still live: behavioral case (xii) is
**required, not conditional**, and this hole does **not** appear in the guide's
limits list.

**Cost note.** The map hashes every changed-or-untracked file twice per run (once
at `init`, once at the gate). `--exclude-standard` bounds this in practice — build
output and vendored trees are gitignored in any sane project — but a project with a
large *non-ignored* untracked tree pays real I/O. This is two in-process `hashlib`
passes per run, not two-times-N process spawns — see (a). Not a design change; it
is the fifth entry on the guide's limits list (see Documentation).

**(e) Delimiter and implementation language — DECIDED: NUL-delimited git output,
consumed by `python3`.** `general-task`'s `untracked()` uses `git ls-files -o -z`
so paths containing spaces or newlines survive. `comm` is line-oriented and has no
NUL mode on any platform (BSD or GNU), so a bash `sort`/`comm` formulation would
have forced either a newline-delimited set (losing embedded-newline paths) or a
hand-rolled `sort -z` substitute.

**Decision (2026-08-27 review pass): the gate body is `python3 -c`, and git
output is NUL-delimited throughout.** Precedent is `validate_intent` in this same
loop — `action_type: shell` + `python3 -c` + `evaluate: {type: exit_code}` — so
the shape test in Expected Behavior reason (3) is satisfied without change.

**Amended 2026-08-27 (second review pass): single-quoted body, values passed as
`sys.argv`.** `validate_intent` uses a *double*-quoted `-c "…"` body, but it has no
shell locals to inject — its only substitutions are FSM-side
`${captured.run_dir.output}` refs. This gate does: `$ROOT`, `$BASELINE_REF`, and the
run dir all have to reach the Python body. Copying the double-quoted shape means
bash expands anything `$`-shaped **inside the Python source** — a `$` in a regex or
string literal, a `` ` ``, a `\` — and every embedded `"` needs hand-escaping. That
is an escaping class the gate's predecessors never had to face, in the code the
Impact section already names as the most dangerous surface.

Use a single-quoted body with values as arguments:

```sh
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=""
BASELINE_REF=$(cat "${captured.run_dir.output}/baseline-ref.txt" 2>/dev/null || echo "")
python3 -c '
import sys, os, json, subprocess
root, ref, run_dir = sys.argv[1], sys.argv[2], sys.argv[3]
...
' "$ROOT" "$BASELINE_REF" "${captured.run_dir.output}"
```

FSM interpolation runs over the **entire** action string regardless of shell
quoting (`interpolation.py:209-287`), so `${captured.run_dir.output}` still
resolves inside single quotes exactly as it does inside double quotes — only
*bash* expansion is suppressed, which is the point. The single constraint the form
adds: the Python body may not itself contain a literal `'`; use `"` throughout it.

This also discharges requirement (l) **completely** rather than leaving it as a
residual check — a single-quoted body cannot contain a bash-visible `${…}` at all,
and the surrounding preamble uses the bare-`$VAR` idiom.

The `python3` decision is load-bearing for four other requirements and is why they
are cheap rather than risky:

- **(d)** becomes a `dict` set-difference over `path -> hash`, not an `xargs`
  pipeline.
- **this requirement** dissolves: Python splits on `\0` natively; no `comm`
  substitute needed and no embedded-newline caveat to document.
- **(k)(3)** symlink normalization becomes `os.path.realpath`, instead of a
  hand-rolled bash prefix comparison. It also sidesteps `ARCHITECTURE-087`
  cleanly — that decision governs the *capture* of `run_dir` as absolute in
  shell, not a comparison-time normalization inside a Python body.
- **(l)** dissolves entirely under the single-quoted form above: a single-quoted
  body cannot contain a bash-visible `${` at all.

It is also the largest available reduction in the surface area the Impact
section calls out as the dangerous one — the path-space code, which the corrected
(k) scope note establishes runs on every subdirectory launch rather than almost
never.

**(f) Exclude harness state by explicit pathspec, not by ambient gitignore —
exclude `.loops/` and `.ll/` as wholes rather than just `run_dir`, and exclude them
at *any depth*, not only at the repo root.** This repo happens to gitignore
`.loops/runs/` (`.gitignore:88`), so `--exclude-standard` hides `run_dir` here *by
accident*. A consuming project without those entries would see every legitimate
run-dir artifact as an out-of-scope write. Exclude explicitly, adapting
`general-task.yaml`'s `final_verify_spin_gate` idiom
(`git diff "$BASELINE_REF" -- . ':(exclude).loops/'`).

**The pathspecs must be `':(exclude,glob)**/.loops/**'` and
`':(exclude,glob)**/.ll/**'`, not the root-anchored `':(exclude).loops/'` form the
precedent uses.** This is the correction the 2026-08-27 *third* review pass made,
and it is load-bearing rather than cosmetic:

- `ll-loop run` derives `run_dir` from the **launch directory**, not the project
  root. `cli/loop/__init__.py:57` takes the raw relative config string
  (`Path(config.loops.loops_dir)`, i.e. `".loops"` — note it does **not** call
  `config.get_loops_dir()`, which would anchor to `project_root`), and
  `cli/loop/run.py:102` resolves it with a bare `.resolve()`, i.e. against `$(pwd)`.
  `run.py:199` then builds `run_dir = <cwd>/.loops/runs/<instance>/`.
- Shell states inherit that same cwd: `ExecutorState.working_dir` defaults to
  `None` and the action subprocess runs with `cwd=self.working_dir`
  (`fsm/executor.py:2482`).
- So a run launched from `scripts/` writes its run dir to
  `<repo>/scripts/.loops/runs/…`. A root-anchored `':(exclude).loops/'` — which
  `-C "$ROOT"` deliberately anchors to `<repo>/.loops/` — does not cover it, and
  `.gitignore:88` (`.loops/runs/`, leading-slash-anchored) does not either.

Without the glob form the gate therefore **fires on its own run-dir scaffolding on
every subdirectory launch** — the exact scenario in the Use Case, in behavioral case
(vii), and in the live "launched from a repo subdirectory" acceptance criterion.
Verified against git 2.52: `':(exclude,glob)**/.loops/**'` excludes both
`<root>/.loops/` and `<subdir>/.loops/` while leaving `<subdir>/other.txt` visible;
the root-anchored form leaves `<subdir>/.loops/w.txt` in the result set.

Case (vii-c) is the guard.

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

**(i) Cover untracked *and* tracked changes. SUBSUMED BY (a).** The source
incident's `research/*.md` files were untracked, so a tracked-only
`git diff --name-only` misses the exact failure mode this issue targets; an
untracked-only check misses an in-place overwrite of a tracked file. (a)'s unified
map *is* the union of both sides, baselined symmetrically. Retained as a lettered
requirement because it is cited by ID elsewhere.

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

**The escape warning is a pinned marker string, not improvised prose (added
2026-08-27, fifth review pass).** Three tests couple to the warning's exact text
— (vi)/(vi-b) assert its presence, (xiv) asserts its absence — and nothing else
distinguishes "skipped" from "always-green." Emit a stable grep-able token,
`check_intent_scope: SKIPPED`, optionally followed by the reason, and have all
three cases assert on that token rather than on sentence prose that a later
wording tweak would silently decouple.

**`init`'s body must tolerate an empty ref explicitly** — when `$REF` is empty
(zero-commit repo), skip the `git diff` side and build the map from the
untracked listing alone, rather than letting the diff call crash into the
`|| : >` fallback. Otherwise the zero-byte-file escape and the empty-ref escape
become accidentally load-bearing for each other: the gate skips for the right
reason only because `init` failed for a different one.

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

**Scope note — CORRECTED 2026-08-27 (third review pass). Relativization is on the
common path, not a rare fallback.**

_(This note previously read: "relativization is the fallback path, not the main
mechanism … the code most likely to be wrong is also the code that almost never
executes," on the reasoning that the default `run_dir` is `.loops/runs/<loop>-<ts>/`
(`fsm/validation/meta_rules.py:194`) and is therefore subsumed by requirement (f)'s
`.loops/`-wide exclusion. That reasoning silently assumed `run_dir` is anchored to
the repo root. It is not — see (f): it is anchored to the **launch directory**
(`cli/loop/run.py:102`'s bare `.resolve()`, states inheriting cwd via
`executor.py:2482`). The conclusion drawn from it — implement (k)(1)/(k)(3) as a
guarded branch — was therefore wrong, and is reversed below.)_

Two independent things follow from the cwd-anchoring:

1. Requirement (f)'s **glob** exclusions (`':(exclude,glob)**/.loops/**'`) restore
   the subsumption the old note claimed: with them, a default `run_dir` at any
   depth is excluded. Root-anchored exclusions do not.
2. Requirement (k)(1)'s relativization is nonetheless exercised on **every
   subdirectory launch**, because `${captured.run_dir.output}` is
   `$(pwd)`-absolute (`init`'s `case` block) while git reports root-relative paths.
   Relativizing `<repo>/scripts/.loops/runs/x/` against `<repo>` is not an exotic
   configuration; it is what happens whenever a maintainer runs the loop from
   anywhere but the repo root — which the Use Case and the live acceptance
   criterion both require.

**Implement (k)(1) and (k)(3) as unconditional machinery on the main path, not as
a guarded branch.** The guarded-branch instruction previously carried in
Implementation Step 2 is withdrawn. (k)(2)'s run-dir-outside-the-worktree
configuration needs no branch either under the post-filter form of (k)(1) — the
filter simply never matches an in-repo path — but keeps its own test cases
((viii)/(viii-b)) because the superseded skip-with-warning reading fails only
there.

Requirements:

1. Compute the repo root once (`git rev-parse --show-toplevel`) and subtract the
   run dir as a **post-enumeration filter inside the `python3` body** — an
   `os.path.realpath` prefix comparison of `<root>/<reported path>` against the
   run dir — **not** as a gate-side `':(exclude)'` pathspec. Decided 2026-08-27
   (fourth review pass), resolving a three-way conflict in the previous text: a
   gate-side run-dir pathspec would make the two `changed_set` invocations
   differ, violating (c)'s byte-identical requirement, while omitting it
   entirely flags a custom in-worktree `--run-dir` outside `.loops/` on its own
   artifacts. The post-filter keeps `changed_set(root, ref)` identical at both
   sites (its signature carries no run-dir argument by design) and lives next to
   (k)(3)'s normalization, which it shares. Note `$(pwd)` is not necessarily the
   repo root — the loop can be invoked from a subdirectory, so cwd-relative ≠
   repo-relative.
   Precedent: `incremental-refactor.yaml:58,159`
   (`ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT="."`).

   **The filter applies to the final flagged set — equivalently to both maps —
   not to the current-side enumeration alone (pinned 2026-08-27, fifth review
   pass).** Under (a)'s symmetric comparison, a current-side-only filter makes
   every run-dir path present in the *baseline* — `init`'s own scaffolding
   (`.emit_errors.txt`, `baseline-ref.txt`, …), in any project that does not
   gitignore the run dir — read as a baseline key absent from the current map,
   and flag. That recreates case (v)'s permanent false positive by a new route.
   The rule: a path is a violation **iff** it is flagged by the symmetric
   comparison **and** its realpath is not under the run dir.
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

   Correct behavior: gate normally. Under (k)(1)'s post-enumeration filter this
   needs no dedicated branch at all — an out-of-worktree run dir simply never
   prefix-matches any in-repo path, the `.loops/`/`.ll/` exclusions stay, and the
   diff is evaluated exactly as normal. Reserve the skip-with-warning escape for
   (j)'s two genuine cases — no repo, and no commits — where there is truly no
   baseline to diff against.

   This matters disproportionately because the discarded configuration fails
   *green*: a run with `--run-dir /tmp/foo` would report containment it never
   checked, which Impact names as the more dangerous of the two misfire
   directions.
3. Normalize both sides (resolve symlinks, strip trailing `/`) before the prefix
   comparison. macOS's `/tmp` → `/private/tmp` symlink makes this a live concern
   for the `tmp_path`-based tests, not a theoretical one. Per (e) this is
   `os.path.realpath` in the `python3` body, not a shell construction.

   **The comparison itself must be separator-safe (added 2026-08-27, fifth
   review pass):** `p == run_dir or p.startswith(run_dir + os.sep)` (or
   `os.path.commonpath`), never a bare `startswith(run_dir)`. The bare form
   filters `/repo/output/x` when the run dir is `/repo/out` — an always-green
   hole for custom `--run-dir` values, in exactly the misfire direction Impact
   names as the more dangerous one. Case (xv) is the guard.

**(l) Escape bash brace-expansions — DISCHARGED BY (e), not managed.** The FSM
interpolates the entire action text before `bash -c` sees it, so a bare `${VAR}` is
parsed as a namespace reference and raises `expected namespace.path` (escape is
`$${VAR}`; precedent `common.yaml:459-460`). (e)'s single-quoted body contains no
bash-visible `${…}` by construction, and the preamble (`ROOT`, `BASELINE_REF`) plus
the `init` additions use the bare-`$VAR` idiom. **No `$${VAR}` escape should appear
anywhere in this issue's code.** Kept as a lettered requirement so a later edit
reintroducing a braced local — or reverting the body to double quotes — is
recognized as reopening a closed hazard.

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
- Add a matched-pair structural test enforcing requirement (c): extract the
  `action` strings of `init` and `check_intent_scope` from the parsed YAML,
  slice the single-quoted `python3 -c '…'` body out of each, and assert byte
  equality. Any drift between the two `changed_set` embeddings — the failure
  (c) exists to prevent — then fails a test instead of waiting for review.
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
  - (iv-b) **a pre-existing *modified tracked* file, dirty before `init` → exit 0.**
    The tracked-side analogue of (iv) and the guard for the defect (a)'s revision
    fixes: with an untracked-only baseline this case fails permanently, on every run,
    in any repo with a dirty tracked file. It is also the unit-level stand-in for the
    live "dirty working tree" acceptance criterion, which as previously specified
    would have failed for this reason rather than for the planted violation.
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
  - (vii-c) **loop invoked from a repo subdirectory with the run dir at
    `<subdir>/.loops/runs/<instance>/` — the real default for that launch — and
    only run-dir files written** → exit 0. This is the guard for requirement (f)'s
    glob exclusions and the corrected (k) scope note. Case (vii) as previously
    written does **not** cover it: a test that plants the run dir under the *root*
    `.loops/` while merely running `bash -c` from a subdirectory passes against the
    root-anchored `':(exclude).loops/'` form, which fires on every real
    subdirectory launch. The run dir must be built at `<subdir>/.loops/…`, and the
    repo's `.gitignore` must not cover it (mirroring `.gitignore:88`'s
    leading-anchored `.loops/runs/`, which does not match at depth).
  - (viii) **run dir outside the worktree, clean repo** (an absolute path under
    `tmp_path`, not under the repo) → exit 0, per the corrected (k)(2). The
    run-dir post-filter matches nothing, the `.loops/`/`.ll/` exclusions stay,
    and the gate finds nothing.
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
  - (xiv) **a clean tree at `init` (baseline map is exactly `{}`) with an
    out-of-scope file planted during the run** → non-zero, and **not** the
    skip-with-warning escape. The guard for (a)'s file-level escape condition: `{}`
    is falsy, so a gate written as `if not baseline: skip` passes this run green
    while announcing that it skipped. Assert both the non-zero exit *and* the
    absence of the escape warning on stdout — cases (vi)/(vi-b) assert that warning
    is present, and nothing else distinguishes the two readings. This is the
    always-green variant with the widest blast radius, since it fires on the
    cleanest repos.
  - (xv) **an out-of-scope file planted in a sibling-named path of the run dir**
    — custom in-worktree run dir `<repo>/out/`, violation written to
    `<repo>/output/x.txt` (the custom run dir matters: with the default
    `.loops/runs/…` dir the glob exclusion masks the defect) → non-zero. Guard
    for (k)(3)'s separator-safe prefix comparison: a bare `startswith(run_dir)`
    filters the sibling path as if it were inside the run dir and passes green.
- Three cases for the unified map in (a) — (xii) unconditional given (d)'s
  decision, (xii-b) and (xii-c) added by the 2026-08-27 second review pass. Each
  is a *value* change the corresponding name-only formulation passes green:
  - (xii) **a pre-existing untracked file (present in the baseline) overwritten in
    place, outside the run dir** → non-zero. This is the case a name-only set
    difference passes green, and the direct analogue of
    `test_untracked_file_content_edit_resets_counter`
    (`test_builtin_loops.py:3081-3096`).
  - (xii-b) **a tracked file already dirty before `init`, modified *again* during
    the run** → non-zero. (iv-b)'s mandatory negative partner: a fix for (iv-b) that
    subtracts the dirty-tracked set *by path* passes (iv-b) and fails only here, so
    without this case the naive fix ships as a new always-green hole on the tracked
    side.
  - (xii-c) **a pre-existing untracked file outside the run dir, deleted during the
    run** → non-zero. The symmetric comparison's baseline-key-absent clause — the
    `DELETED` sentinel cannot fire here, since `git ls-files -o` never reports a
    nonexistent file and `git diff` does not cover untracked paths. A set
    difference that looks only for newly-appeared paths sees the set get *smaller*
    and passes green; this case is the only thing that distinguishes the two.
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
  5. the hashing cost (d) — the changed-or-untracked set is hashed twice per run
     (`init` and gate). Bounded by `--exclude-standard` in practice; a project with
     a large non-ignored untracked tree pays for it.

  The in-place-overwrite hole is **not** on this list: requirement (d) closes it
  by decision. Neither is the tracked-dirty false positive or the untracked-deletion
  blind spot: (a)'s unified changed-set map closes both.

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
- [ ] The gate body is a **single-quoted** `python3 -c '…'` script per (e), with
      `$ROOT`, `$BASELINE_REF` and the run dir passed as `sys.argv` — not a
      double-quoted body with shell-expanded values. No `$${VAR}` escape appears
      anywhere in the state (requirement (l) is discharged, not managed).
- [ ] `validate_intent.on_yes` targets `check_intent_scope`;
      `validate_intent.on_no` is still `count_intent_retry`.
- [ ] `init` resolves `ROOT` via `git rev-parse --show-toplevel` and writes
      `baseline-ref.txt` plus the **unified changed-set map** (tracked ∪ untracked,
      `path -> hash`, `DELETED` sentinel), all git calls via `git -C "$ROOT"`, and
      its stdout contract (`capture: run_dir`) is unchanged.
- [ ] A **tracked file already modified before `init`** does not trip the gate
      (case (iv-b)), and modifying it *again* during the run does (case (xii-b)).
      A path-only subtraction of the dirty-tracked set does not satisfy this pair.
- [ ] **Deleting** a pre-existing untracked file outside the run dir trips the gate
      (case (xii-c)) — the changed-set comparison is **symmetric**: baseline keys
      absent from the current map are flagged, so a shrinking path set is not
      silently green. A one-way scan of the current map does not satisfy this
      criterion, since neither current-side enumeration reports a deleted
      untracked file.
- [ ] `init` pre-truncates `.scope_violations.txt` alongside `.emit_errors.txt` and
      `.intent_errors.txt`, inside the step-1 block that precedes the baseline
      capture (requirement (a1)).
- [ ] A **missing, zero-byte, or unparseable** `baseline-changed-set.json` takes
      the skip-with-warning escape — it must not read as "the tree was clean."
      The condition is file-level; a successfully-parsed `{}` (a genuinely clean
      tree) is a **valid baseline** and must gate normally, not escape
      (case (xiv)). `if not baseline:` does not satisfy this criterion.
- [ ] `init`'s statement order is: existing `mkdir`/truncate block → `ROOT` +
      baseline capture → the `case`/`echo` stdout block last (requirement (a1)).
      Case (v) is the regression guard.
- [ ] `init` emits **exactly one line** on stdout — asserted in a git repo and in
      a non-repo, where all three git commands fail (requirement (b), case (xiii)).
      Every git call **inside** the `python3` body captures its own stdout and
      stderr; none inherits fd 1 (requirement (b)).
- [ ] `init`'s baseline capture and the gate's current-set capture carry matching
      `# HARNESS:` comments identifying them as a deliberate matched pair, and use
      byte-identical invocations including both `':(exclude)'` pathspecs
      (requirement (c)).
- [ ] The baseline is **content-hashed** (`path -> hash`), not name-only, on both
      the tracked and untracked sides, and cases (xii)/(xii-b)/(xii-c) pass
      (requirements (a), (d)). Hashing is **`hashlib` over the file bytes inside
      the `python3` body** — not `git hash-object --stdin-paths` (no `-z` mode;
      breaks on embedded-newline paths) and not one git spawn per path. An
      unreadable path (vanished mid-run, or a dirty submodule directory entry)
      maps to the sentinel, never an uncaught exception — a crash in `init`'s
      hasher truncates the baseline via the `|| :` fallback and silently
      disables the gate.
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
- [ ] The exclusions are **depth-agnostic globs**
      (`':(exclude,glob)**/.loops/**'`, `':(exclude,glob)**/.ll/**'`), not
      root-anchored prefixes. A run launched from a repo **subdirectory** — whose
      default run dir is `<subdir>/.loops/runs/…`, not `<root>/.loops/…` — passes
      with only run-dir files written (case (vii-c)).
- [ ] The run-dir subtraction from (k)(1) is a **post-enumeration
      `os.path.realpath` prefix filter inside the `python3` body**, not a
      gate-side `':(exclude)'` pathspec — the two `changed_set` sites stay
      byte-identical per (c). It and (k)(3)'s normalization are on the **main
      path**, not behind a non-default-`--run-dir` guard; (k)(2)'s
      outside-the-worktree case gates normally through the same filter, with no
      dedicated branch and no skip. The filter applies to the **final flagged
      set** (equivalently both maps), not the current-side enumeration alone —
      a current-side-only filter re-flags `init`'s baselined run-dir
      scaffolding as "absent" under the symmetric comparison — and is
      **separator-safe** (`run_dir + os.sep`, not bare `startswith`; case (xv)).
- [ ] On violation the gate exits non-zero, prints the offending paths, and
      writes them to `${run_dir}/.scope_violations.txt`; on pass that file exists
      and is empty.
- [ ] `diagnose` reads `.scope_violations.txt`, names the scope-violation failure
      path, and carries the BUG-3327 no-stray-writes fence clause.
- [ ] Non-git directory and zero-commit repo both exit 0 **with a warning on
      stdout**, and the warning is the pinned marker token
      `check_intent_scope: SKIPPED` (a bare exit 0 is indistinguishable from
      the always-green bug). Cases (vi)/(vi-b) assert the token present;
      case (xiv) asserts it absent. Run-dir-outside-the-worktree
      is **not** in this set — see the criterion above.
- [ ] A pre-existing untracked file present before `init` does not trip the gate.
- [ ] All **twenty-two** behavioral cases pass — (i)–(xv) plus the `-b`/`-c`
      partners (iv-b), (vi-b), (vii-b), (vii-c), (viii-b), (xii-b), (xii-c) —
      including the mandatory negative partners (vii-b), (viii-b), (ix), (xii-b),
      (xii-c), (xiv) and (xv).
- [ ] The matched-pair structural test passes: the single-quoted `python3 -c`
      bodies extracted from `init`'s and `check_intent_scope`'s actions are
      **byte-identical** (requirement (c)).
- [ ] **The gate has been observed red** against a deliberately planted
      out-of-scope write in a live `workflow-generator` run, launched from a repo
      subdirectory with a dirty working tree — not merely green in CI.
- [ ] `ll-loop validate` clean; full `python -m pytest scripts/tests/` exits 0
      (including `TestValidatorWarningBudget`, with any new `ALLOWLIST` entry
      justified by this issue ID — `partial-route` is the category to watch;
      `no-scope` is a non-risk since the loop already declares `scope:`).
- [ ] `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` documents the gate and all
      **five** limits: the one-shot window, the gitignored-write blind spot (g),
      the human-concurrent-edit false positive (h), the wholesale `.loops/` /
      `.ll/` exclusion (f), and the double-hash cost (d). The in-place-overwrite,
      tracked-dirty and untracked-deletion holes are not among them — requirements
      (d) and (a) close them. `docs/reference/loops.md`'s state-graph diagram
      includes the new state and its `on_no -> diagnose` branch.

## Program Design

### Signatures

- `changed_set(root: str, ref: str) -> dict[str, str]` — the shared construct from
  (a): union of `git diff --name-only -z <ref>` and `git ls-files -o
  --exclude-standard -z`, both root-scoped (`-C "$ROOT"`) and both carrying the
  depth-agnostic `':(exclude,glob)**/.loops/**'` / `':(exclude,glob)**/.ll/**'`
  exclusions, mapped to `path -> content-hash` via `hashlib` over the file bytes,
  with a `DELETED` sentinel for paths git reports that are absent from the
  worktree — the same sentinel covering paths that are unreadable at hash time
  (vanished mid-run, dirty submodule directory entries), caught via `OSError`
  rather than raised. The comparison over two such maps is **symmetric**: new
  keys, changed values, and baseline keys absent from the current map all flag.
  Run-dir subtraction is deliberately **not** part of this function — it is the
  gate's post-enumeration realpath filter per (k)(1), applied to the **final
  flagged set** (both maps, not the current enumeration alone) and
  separator-safe per (k)(3) — which is what lets the two call
  sites stay byte-identical. That byte identity is itself test-enforced
  (requirement (c), matched-pair structural test). Every internal git call captures its
  own stdout and stderr (requirement (b)). Emitted as one identical
  single-quoted `python3 -c` literal at **both** call sites — `init` and
  `check_intent_scope` — differing only in argv (requirement (c)).
- `init.action: str` — additionally resolves `ROOT` and writes `baseline-ref.txt`
  plus `baseline-changed-set.json` (the `changed_set` map above), and pre-truncates
  `.scope_violations.txt` in its existing step-1 block; its stdout contract
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

0. Write the shared `changed_set(root, ref)` body from (a) first — it is the one
   construct both `init` and the gate embed verbatim, and every other step depends
   on its shape. Union of tracked-diff and untracked-listing, root-scoped, both
   **glob** `':(exclude,glob)'` pathspecs from (f), `path -> hash` with a `DELETED`
   sentinel, hashed via `hashlib` over the file bytes per (a) — with unreadable
   paths (TOCTOU-vanished files, submodule directory entries) caught and mapped
   to the sentinel, never raised — compared
   symmetrically (new keys, changed values, and baseline keys absent from the
   current map all flag), tolerating an empty ref (skip the diff side) per (j),
   with every internal git call capturing its own
   stdout/stderr per (b).
1. Add `ROOT` resolution and the baseline captures to `init` (lines 44-61),
   following `general-task.yaml:76`'s `git rev-parse HEAD > baseline-ref.txt`
   idiom plus `changed_set` serialized to `baseline-changed-set.json` per (a)/(d)
   — all via `git -C "$ROOT"` per (k)(1b), written as an explicitly-commented
   matched pair with the gate per (c). Extend the existing truncate block with
   `: > "$DIR/.scope_violations.txt"` per (a1). **Placement matters twice**: the
   baseline goes after that `mkdir`/truncate block per (a1), and before the
   `case`/`echo` block, which stays last and alone. Redirect every new command's
   stdout to a file (or into `$(…)`) and stderr to `/dev/null` so `init` stays the
   sole stdout writer per (b).
2. Add the `check_intent_scope` state as a **single-quoted** `python3 -c '…'` body
   with `sys.argv`-passed values per (e) — it recomputes `changed_set` and flags
   any entry that is new or whose value differs. Plus the depth-agnostic
   `':(exclude,glob)**/.loops/**'` / `':(exclude,glob)**/.ll/**'` exclusions from
   (f) as the primary mechanism, the root-scoped enumeration from (k)(1b), the
   non-repo/zero-commit escape from (j) — extended to cover a **missing, zero-byte
   or unparseable** `baseline-changed-set.json` per (a), with a parsed `{}`
   explicitly *not* escaping, and emitting the pinned
   `check_intent_scope: SKIPPED` marker on every escape — and the bare-`$VAR`
   preamble idiom from (l).
   Add the run-dir subtraction as (k)(1)'s **post-enumeration realpath prefix
   filter** — applied to the final flagged set, separator-safe
   (`run_dir + os.sep`), not a gate-side pathspec: the two `changed_set` sites
   must stay byte-identical per (c) — and (k)(3)'s `os.path.realpath`
   normalization, both
   **on the main path** — every subdirectory launch exercises them, per the
   corrected scope note in (k). Outside-the-worktree gates normally per the
   corrected (k)(2) — **not** by escaping; under the post-filter it needs no
   dedicated branch, the filter simply never matches an in-repo path.
3. Retarget `validate_intent`'s `on_yes` (line 118) to it. Leave
   `on_no: count_intent_retry` (line 119) untouched.
4. Have the gate write `${run_dir}/.scope_violations.txt` per (n) — truncated to
   empty on a pass, mirroring `validate_intent`'s `.intent_errors.txt`; add that
   file to `diagnose`'s read list and add the scope-violation path to
   `diagnose`'s failure enumeration.
5. Add the fence clause to `diagnose`'s prompt per (o).
6. Verify `max_steps` is 45 per (m) — expected to be a no-op.
7. Add the tests above (all twenty-two cases — (i)–(xv) plus (iv-b), (vi-b),
   (vii-b), (vii-c), (viii-b), (xii-b), (xii-c) — plus the state-set,
   exit_code-shape, routing-edge, matched-pair byte-identity, `run_dir`-usage
   and `diagnose`-text test
   updates). Case (xiii) targets `init`, not the gate; case (v) doubles as the (a1)
   ordering guard; case (vii-c) must build its run dir under `<subdir>/.loops/`,
   not the root one, or it does not test what it claims; case (xv) must use a
   custom in-worktree run dir, or the `.loops/` glob masks the defect.
8. Verify with `ll-loop validate`, plus a re-run of `workflow-generator` **from a
   deliberately dirty working tree and from a repo subdirectory**, confirming that
   pre-existing untracked files do not trip the gate and that the gate still fires
   on a deliberately planted out-of-scope write **placed outside the invocation
   subdirectory**. **A green gate proves nothing until you have seen it go red.**
9. Document the gate and its five limits: the one-shot window, the
   gitignored-write blind spot (g), the human-concurrent-edit false positive (h),
   the wholesale `.loops/`/`.ll/` exclusion (f), and the double-hash cost (d).

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
- **Effort**: Medium — one new state, `ROOT` resolution plus the shared
  `changed_set` construct and its `init` baseline, root-scoped enumeration, a
  relativization on the main path, one escape path (no repo / no commits / no
  usable baseline), a violation report artifact plus `diagnose` edits, and
  twenty-two behavioral test cases plus a matched-pair structural test
- **Risk**: Medium — the gate can misfire in **both** directions: a false positive
  routes to `diagnose` and fails the run, while a path-space mismatch
  (requirement (k)) yields a gate that is permanently green and reports safety it
  is not checking. The second failure is the more dangerous one because nothing
  surfaces it. That is why the dirty-tree baseline (a), the `init` ordering (a1)
  and stdout-purity (b) constraints, the escape path (j), the relativization (k),
  and the red-gate test case are requirements, not polish — and why the gate must
  not route back to `capture_intent`.

  Seven of the always-green variants are pinned by mandatory negative test
  partners rather than left to review: (vii-b) for cwd-scoped enumeration,
  (viii-b) for the outside-the-worktree escape, (ix) for the exclusion pathspec,
  (xii-b) for a path-only subtraction of the dirty-tracked set, (xii-c) for
  untracked deletions, (xiv) for a falsy-`{}` baseline escaping on a clean
  tree, and (xv) for a separator-unsafe run-dir prefix filter. Each of their
  positive partners passes trivially against the corresponding
  broken gate, so the pairs are not optional.

  The false-positive direction gained a real instance in the 2026-08-27 second
  review pass: the tracked side had no baseline at all, so any repo with a dirty
  tracked file failed the gate permanently. (a)'s unified changed-set map fixes it
  and, in the same construct, closes the untracked-deletion always-green hole.

  One decision lowers this risk relative to the original framing: requirement
  (e)'s `python3` body, which turns the set difference, content hashing, and
  symlink normalization into library calls instead of hand-rolled shell — where the
  subtle always-green failures were most likely to originate.

  A second claimed mitigation was **withdrawn by the 2026-08-27 third review
  pass**. It read: "the default `run_dir` (`.loops/runs/…`) is covered by the
  `.loops/` exclusion alone, so the relativization code most likely to be subtly
  wrong is also the code that almost never runs." Both halves are false, and in
  opposite directions: `run_dir` is anchored to the **launch directory**
  (`cli/loop/run.py:102`, `executor.py:2482`), so a root-anchored `.loops/`
  exclusion misses it entirely on subdirectory launches — a permanent false
  positive — and the relativization path runs on every such launch rather than
  almost never. Requirement (f)'s glob exclusions restore the first half; the
  corrected (k) scope note fixes the second. The risk rating stays Medium, but it
  no longer rests on that argument.
- **Breaking Change**: No

## Scope

`workflow-generator`-only. The gate depends on that loop's `init`/`run_dir`
structure, and the other four loops BUG-3327 fences are not all meta-loops with the
same artifact-isolation contract. Generalizing it is a separate question.

## Notes

Split from BUG-3327 on 2026-08-26 (Proposed Solution §2 and its associated
requirements, tests, and Impact analysis moved here verbatim). BUG-3327 retains the
brief-fencing work.

### Review history

Five pre-implementation review passes have run against this issue. The current
spec is the body above; this is only the record of what changed and why, so a
reader who remembers an earlier version can see what moved.

- **2026-08-27, first pass.** Added `ROOT` resolution to `init` as an explicit
  precondition; added (a1) (baseline capture must follow `init`'s `mkdir`/truncate
  block, or the loop's own scaffolding reads as out-of-scope writes); made (a)'s
  exclusion pathspec symmetric across both sites per (c); resolved the two open
  decisions — content-hashed baselines (d) and NUL-delimited git output consumed by
  a `python3 -c` body (e) — rather than deferring them to implementation; added
  `.ll/` to the exclusion set (f).
- **2026-08-27, second pass.** Rewrote (a): the baseline had covered only the
  untracked set, so any repo with a pre-existing dirty *tracked* file failed the
  gate permanently on every run — the exact failure (a) exists to prevent, applied
  to one side only. The replacement is one unified `path -> content-hash` map over
  tracked ∪ untracked, which subsumes (d) and (i) and closes a never-recorded hole:
  **deletion** of a pre-existing untracked file was silently green. Amended (e) to
  a *single-quoted* body with `sys.argv`-passed values, discharging (l) outright.
  Added cases (iv-b), (xii-b), (xii-c); corrected the case count to nineteen.
  Pre-truncated `.scope_violations.txt` in `init`.
- **2026-08-27, third pass.** Four changes, all recorded in place above:
  1. **(f) exclusions are depth-agnostic globs.** `run_dir` is anchored to the
     **launch directory**, not the repo root (`cli/loop/__init__.py:57` takes the
     raw relative config string, `cli/loop/run.py:102` resolves it against `$(pwd)`,
     `run.py:199` builds `<cwd>/.loops/runs/…`, and states inherit that cwd via
     `executor.py:2482`). A root-anchored `':(exclude).loops/'` therefore misses
     `<subdir>/.loops/`, and `.gitignore:88` does not cover it either — so the gate
     fired on its own scaffolding on every subdirectory launch, which is the Use
     Case, case (vii), and the live acceptance criterion. Case (vii-c) added.
  2. **(k)'s scope note reversed.** Relativization is on the main path, exercised by
     every subdirectory launch — not a rare guarded branch. Implementation Step 2
     and the Impact risk rationale both corrected; the withdrawn mitigation is
     recorded in Impact rather than deleted.
  3. **(a)'s escape condition is file-level.** A clean tree serializes as `{}`,
     which is falsy, so `if not baseline: skip` disabled the gate on the cleanest
     repos while announcing that it skipped. Case (xiv) added.
  4. **Hashing is one batched `git hash-object --stdin-paths` call per site**, and
     (b)'s sole-stdout-writer obligation extends *inside* the `python3` body — an
     uncaptured `subprocess.run` there inherits `init`'s fd 1 and corrupts
     `capture: run_dir`.
  Requirements (d), (i) and (l) were compacted to pointers at their own labels,
  since (a) and (e) now carry their mechanisms; they are retained as lettered
  requirements only because they are cited by ID elsewhere.
- **2026-08-27, fourth pass.** Three fixes, all recorded in place above:
  1. **(a)'s comparison rule made symmetric.** As written ("new or value
     differs") it could not catch case (xii-c): a deleted pre-existing untracked
     file appears in neither current-side enumeration, so the `DELETED` sentinel
     — which only fires on the tracked side, where `git diff` still reports the
     path — never fires for it. Baseline keys absent from the current map now
     flag.
  2. **Hashing switched from batched `git hash-object --stdin-paths` to
     `hashlib`.** `--stdin-paths` has no `-z` mode (verified, git 2.52), so the
     third pass's batching instruction conflicted with (e)'s NUL-everywhere
     decision on embedded-newline paths.
  3. **Run-dir subtraction pinned as a post-enumeration realpath filter in the
     gate's Python body.** The previous text was three-way inconsistent: the
     `changed_set(root, ref)` signature carries no run-dir argument, (c) demands
     byte-identical call sites, yet (k)(1) said to use the run dir "in a
     pathspec." The post-filter resolves all three, and dissolves (k)(2)'s
     dedicated branch (the filter never matches an in-repo path); cases
     (viii)/(viii-b) are retained.
- **2026-08-27, fifth pass.** Six changes, all recorded in place above:
  1. **(k)(1)'s post-filter pinned to the final flagged set**, not the
     current-side enumeration — under the symmetric comparison a current-side
     filter re-flags `init`'s baselined run-dir scaffolding as "absent,"
     recreating case (v)'s permanent false positive by a new route.
  2. **(k)(3)'s prefix comparison made separator-safe** (`run_dir + os.sep`) —
     a bare `startswith` filters sibling-named paths (`/repo/output` under run
     dir `/repo/out`), an always-green hole for custom `--run-dir`. Case (xv)
     added; count is twenty-two.
  3. **(a)'s hasher tolerates unreadable paths** — `FileNotFoundError` (TOCTOU)
     and `IsADirectoryError` (dirty submodule entry) map to the sentinel; an
     uncaught exception in `init` truncates the baseline via the `|| :`
     fallback and silently disables the gate.
  4. **(c)'s matched pair is now test-enforced** — a structural test asserts
     the two embedded `python3 -c` bodies are byte-identical.
  5. **(j)'s escape warning is a pinned marker** (`check_intent_scope: SKIPPED`)
     since three tests couple to its presence/absence.
  6. **(j)/`init` tolerate an empty ref explicitly** (skip the diff side)
     rather than relying on the crash-into-`|| : >` fallback producing the
     zero-byte escape by accident.

Requirement labels were renumbered sequentially to (a)–(p) in an earlier pass. If
you are holding a reference from before that, re-read the requirement by its text
rather than its letter.

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
