---
id: BUG-3341
type: BUG
title: Convert class-B LLM-output interpolations to heredoc-to-file
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
blocked_by: [ENH-3337, ENH-3338, BUG-3339, BUG-3340]
blocks: [ENH-3347]
---

# BUG-3341: Convert class-B LLM-output interpolations to heredoc-to-file

## Summary

Convert every **class-B** site — `${captured.*}` (always untrusted: LLM or
command output) interpolated into a Python string literal inside a shell action —
to **Option B**: write the captured value to a run-dir file via its own quoted
heredoc, then `open()` it from the Python body. Sentinel is the fixed
`LL_RAW_9F3C1A7E_EOF`; filename is `<state>-<capture>.txt`; the `cat >` heredoc
is **hoisted above any enclosing `if`/`for`**.

The authoritative site list is ENH-3338's baseline class-B entries; the survey's
provisional figure was 67 (56 heredoc + 11 `-c "`).

## Current Behavior

`${captured.x.output}` is substituted as raw text into a Python string literal
before `bash -c` runs, so the model's own output is parsed as Python source:

- a `"""` anywhere in the response terminates a triple-quoted literal and breaks
  the state
- a newline breaks a single-quoted literal
- prompt-injected content in the model's output becomes **executed Python**

This is the sharper class: unlike class A, nothing constrains the value — it is
generated, not typed by the operator.

Representative sites: `loop-router.yaml:127, 141, 185, 245, 338, 472`;
`apply-research.yaml:168, 306`; `assumption-firewall.yaml:66, 128, 158`;
`goal-cluster.yaml:207, 436, 566, 639`; `learning-tests-audit.yaml:114-116, 225`;
`migrate-sdk-version.yaml:171, 183`. The 11 `-c "` class-B sites
(`sft-corpus.yaml:118, 139, 160, 181, 202, 223, 244, 265, 322`;
`general-task.yaml:898`, plus `harness-optimize.yaml:164` — which BUG-3339
determined is `action_type: prompt` and therefore not a live site) get BUG-3339's
heredoc conversion first. Note: under BUG-3339's structural carve-out (its
Implementation Step 8), `general-task.yaml:895-902` may land in its final
Option B form during BUG-3339 — check before re-converting it here.

**MR-11 does not see any of this today** — its regex matches `${context.*}` only,
with no `captured` alternation at all (`shell_safety.py:33-35`). Class B is
entirely outside the existing lint's reach; ENH-3342 closes that.

## Expected Behavior

Every class-B value reaches the Python body through `open()`, never through the
parser. A `"""`, a newline, or an injection payload in model output is inert: the
quoted heredoc hands bash the bytes verbatim, the file holds them verbatim, and
Python reads them as data.

ENH-3338's baseline holds **zero class-B entries** when this issue closes.

## Steps to Reproduce

1. Run any class-B state whose model response contains a `"""` — e.g.
   `loop-router`'s review states, where the model is asked to quote code.
2. `InterpolationContext.resolve()` substitutes `${captured.review_result.output}`
   into the action text before bash runs (`fsm/interpolation.py`,
   `fsm/runners.py:297`).
3. The `"""` in the response terminates the enclosing triple-quoted Python
   literal.
4. Observe: `SyntaxError`, the state dies. A newline in a single-quoted-literal
   site produces the same result. This is the exact failure BUG-2468 fixed for
   `brainstorm.yaml`'s `dedup_novelty` state and left unfixed everywhere else.

For the injection variant, an upstream prompt injection causing the model to emit
`""" ; import os; os.system(...) ; """` executes as Python.

## Motivation

BUG-2468 is the same failure mode, already shipped and tested for one state:
`brainstorm.yaml`'s `dedup_novelty` (`brainstorm.yaml:160-169`,
`scripts/tests/test_brainstorm.py::TestBug2468ErrorRouting`, status `done`). This
issue applies that proven fix to the remaining ~67 sites.

## Settled decisions

Inherited from EPIC-3336; do not re-litigate.

**Option B — per-site heredoc-to-file — selected** over Option A (a runner-side
`${captured.x.path}` accessor) and Option C (defer class B). Option A is cleaner
in principle and permanently fixes the class, but it is a runner change plus a
schema addition — untested, higher risk — where Option B has a shipped in-repo
precedent and needs no runner or schema change. Option C leaves the sharpest
class open.

**Fixed improbable sentinel `LL_RAW_9F3C1A7E_EOF`** — selected over a
sentinel-plus-length-check. Randomizing the marker is not workable: bash matches
the closing line literally, so interpolating it (`<< "RAW_${loop.run_id}"`) makes
the heredoc **double-quoted**, which re-enables expansion and defeats the entire
mechanism. Residual risk is a line of LLM prose reading exactly
`LL_RAW_9F3C1A7E_EOF`; that is not a realistic failure.

**Env-var binding is not the remedy for class B.** Not for injection reasons —
`${captured.x.output:shell}` does shlex-quote a multi-line value safely — but for
uniformity with the shipped precedent and reviewability across 67 sites.
Note for the record: **the ARG_MAX argument that once justified this is wrong**
and must not be reused. The interpolated value rides inside the single
`bash -c <action>` argv element (`runners.py:297`) under *both* shapes, so both
hit the same ceiling at the same exec boundary.

## Canonical block

```bash
cat > "${context.run_dir}/<state>-<capture>.txt" << 'LL_RAW_9F3C1A7E_EOF'
${captured.<name>.output}
LL_RAW_9F3C1A7E_EOF
# ... any if/for wrapping goes here ...
LL_ARG_RUN_DIR=${context.run_dir:shell} python3 << 'PYEOF'
import os
run_dir = os.environ["LL_ARG_RUN_DIR"]
with open(os.path.join(run_dir, "<state>-<capture>.txt")) as f:
    value = f.read()
PYEOF
```

Four constraints on this block, each of which an earlier draft got wrong:

1. **The `LL_ARG_RUN_DIR=` binding is load-bearing.** An earlier revision read
   `os.environ["RUN_DIR"]` without ever setting it, which raises `KeyError` at
   every copy-paste site. The accepted alternative is to raw-interpolate the path
   (`open("${context.run_dir}/<state>-<capture>.txt")`) — `run_dir` is a trusted
   class-C key — but then **drop the `os.environ` line**. Do not ship the
   half-and-half form.
2. **Hoist the `cat >` above any enclosing `if`/`for`.** Bash matches a `<<`
   terminator **only at column 0** (`<<-` relaxes it for *tabs* only, which this
   repo's space-indented YAML block scalars cannot supply). Several targets nest
   their Python inside an `if` — `recursive-refine.yaml:82-83`,
   `rn-build.yaml:728-729`, `loop-composer-adaptive.yaml:744`. Writing the block
   in place there produces an **unterminated heredoc that swallows the rest of
   the action**. The file write is unconditional and harmless; only the read is
   conditional. `brainstorm.yaml:161-164` works precisely because its `cat >`
   sits at the action body's top level.
3. **The heredoc appends a trailing newline the captured value did not have.**
   `.strip()` or `.rstrip("\n")` at the read site if the consumer is
   newline-sensitive. `brainstorm.yaml` gets away without it because it strips
   per line.
4. **The filename must be unique per capture per state.** `>` truncates, and a
   re-entered state legitimately overwrites its own file. `<state>-<capture>.txt`
   is an **enforced rule**, not a suggestion — ENH-3338's sweep asserts it.

`grep -rn LL_RAW_9F3C1A7E_EOF scripts/little_loops/loops/` is the canonical way to
enumerate completed conversions.

**Shipped divergent shapes are grandfathered, not normalized** (decided
2026-08-28, resolving the tension flagged in Codebase Research Findings).
`loop-router.yaml:512-513`'s env-var class-B conversion (BUG-3349) and the
bespoke-sentinel data-sink writes in `brainstorm.yaml` (`RAWEOF`) and
`loop-composer.yaml` / `loop-composer-adaptive.yaml` (`LL_PLAN_RAW_EOF`,
`LL_STEP_OUTPUT_EOF`, `LL_REASSESS_EOF`) all scan clean under ENH-3338 and
stay as they are; this issue does not rewrite them, and AC 2's grep-count
therefore covers only sites this issue converts. The "uniformity with the
shipped precedent" rationale for rejecting env-var binding is acknowledged
as weakened — the corpus now ships both remedies — but Option B stands for
new conversions on its file-based auditability and the per-site guidance
already written here.

## Integration Map

### Files to Modify

The authoritative list is ENH-3338's baseline filtered to `class == "B"`. From
the provisional survey, the class-B-bearing files: `sft-corpus.yaml`,
`loop-router.yaml`, `recursive-refine.yaml`, `goal-cluster.yaml`,
`loop-composer-adaptive.yaml`, `apply-research.yaml`,
`assumption-firewall.yaml`, `learning-tests-audit.yaml`,
`migrate-sdk-version.yaml`, `general-task.yaml`, `rn-build.yaml`, plus the
`lib/` and `oracles/` files carrying `${captured.*}` sites.

Known `if`-nested targets requiring the hoist: `recursive-refine.yaml:82-83`,
`rn-build.yaml:728-729`, `loop-composer-adaptive.yaml:744`.

- `scripts/tests/data/loop_interpolation_baseline.json` (new) — created by ENH-3338 — shrink class-B entries in the same commit as each conversion.
- **Depends on ENH-3338's data-sink heredoc rule** (its 2026-08-28 review
  fix): the scanner must treat a `${captured.*}` inside a
  `cat > … << 'MARKER'` write as clean (data sink, not a Python body).
  Without it, every conversion here *adds* a class-B baseline entry instead
  of removing one, and AC 1 is unreachable.

**File contention:** runs strictly after BUG-3339 and BUG-3340; do not dispatch
to a parallel epic branch.

### Dependent Files (Callers/Importers)

- N/A — loops are invoked by ID via the FSM runner, not imported.

### Similar Patterns

- `scripts/little_loops/loops/brainstorm.yaml:160-169` — the shipped BUG-2468
  fix; the exact shape to copy.
- `scripts/little_loops/loops/cua-agent-desktop.yaml:415-423` — shell-only
  sibling of the same pattern.

### Tests

- `scripts/tests/test_brainstorm.py::TestBug2468ErrorRouting` — the precedent's
  own coverage; the model for ENH-3347's `"""`-capture case.
- `scripts/tests/test_builtin_loops.py` — ENH-3338's baseline-equality test stays
  green at every commit.
- `ll-loop validate` per converted file.

### Documentation

- N/A here — the idiom is documented by ENH-3342.

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Four additional heredoc-to-file (`cat > file << 'SENTINEL'`) sites exist beyond the two cited in Similar Patterns**, each already writing a `${captured.*.output}` class-B value to a run-dir file before reading it back with `open()`, but each using its own bespoke sentinel (not the mandated `LL_RAW_9F3C1A7E_EOF`): `loop-composer.yaml` — `parse_plan` (`plan-raw.txt` / `LL_PLAN_RAW_EOF`) and `write_step_success`/its failure sibling (`current-step-output.jsonl` / `LL_STEP_OUTPUT_EOF`, 2 occurrences); `loop-composer-adaptive.yaml` — the same two shapes plus `parse_reassess_decision` (`reassess-decision.txt` / `LL_REASSESS_EOF`). These files/sites are not currently named in this issue's Files to Modify or Similar Patterns lists and should be reconciled against ENH-3338's baseline alongside the rest.
- A repo-wide search confirms `LL_RAW_9F3C1A7E_EOF` has zero occurrences in any `.yaml` file today (hits are confined to issue markdown) — the four additional sites above predate this issue's sentinel choice with their own bespoke conventions, they don't pre-empt it.
- **A shipped precedent already applies env-var binding (not heredoc-to-file) to two class-B sites.** Commit d8d3476a1 (BUG-3349, status done, landed after this issue's parent survey) converted `loop-router.yaml`'s `finalize_present_result` state's two `${captured.*.output}` sites (`new_loop_proposal`, `review_result`) using `LL_PROPOSAL_OUT=${captured.new_loop_proposal.output:shell:default=} \` / `LL_REVIEW_OUT=${captured.review_result.output:shell:default=} \` bound to the `python3` invocation line, read via `os.environ.get(..., '')` — structurally the same env-var-binding mechanism this issue's own Settled Decisions section rejects for class B ("uniformity with the shipped precedent and reviewability," not correctness). BUG-3349's own research notes this exact combination ("`:shell` applied to a `captured.*` reference") had "no direct precedent confirming the combination works" at the time it was written — that precedent now exists, and it uses the opposite remedy from Option B. This does not change this issue's own two listed sites (`finalize_present_result`'s lines were never in this issue's site list), but the "uniformity with the shipped precedent" rationale for rejecting env-var binding is weaker than when written: the codebase now ships both conventions for the same defect class, not one.

## Program Design

### Signatures

No Python API change; this is a per-site edit inside loop YAML action strings.

- `interpolate(template, ctx)`
  (`scripts/little_loops/fsm/interpolation.py:209`) — substitutes the captured
  value into the `cat >` heredoc body. Unchanged.
- `_run_action(...)` (`scripts/little_loops/fsm/executor.py:2097`, write site at
  `:2370-2391`) — populates `self.captured[state.capture]`. **Unchanged** — this
  is where Option A would have added a `path` key, and Option B is what avoids
  touching it.

### Call Path

Before: `resolve()` substitutes model output → `bash -c` → quoted heredoc →
**`python3` parses model output as source**.

After: `resolve()` substitutes model output into a `cat >` quoted-heredoc body →
bash writes it to a run-dir file **verbatim, no expansion** → the `python3`
heredoc body contains no interpolation → Python `open()`s the file and reads it
as data.

### Decision Rules

Per class-B site:

0. **First check whether the site needs Option B at all** (review decision,
   2026-08-28). Many class-B entries are `${captured.run_dir.output}` — a
   captured run-dir path for which the runner-constructed
   `${context.run_dir}` (class C, set at `executor.py:903`) is a one-token
   substitution: e.g. `brainstorm.yaml:169, 186, 213`,
   `mechanize-skills.yaml:286`. Where the captured value is just the
   runner's own run dir, substitute `${context.run_dir}` instead of building
   an Option B block — verify the loop doesn't deliberately point the
   capture somewhere else before swapping. This likely shrinks the ~67-site
   estimate materially.
1. Derive the filename `<state>-<capture>.txt` from the state name and the
   capture variable name. Two captures in one state get two files.
2. Place the `cat >` block at the action body's top level, above any `if`/`for`,
   even when the reading Python is nested.
3. Replace the in-literal interpolation with a read of that file.
4. Decide per site whether the consumer is newline-sensitive; add
   `.rstrip("\n")` where it is.
5. Preserve `:default=` semantics — `${captured.x.output:default=}` guards a
   capture from a state that never ran. Dropping it converts a graceful default
   into a loop failure. Under ENH-3337 the composed suffix is legal; keep it on
   the heredoc-body interpolation.

## Implementation Steps

1. Filter ENH-3338's baseline to `class == "B"`; reconcile any divergence from
   the survey's 67 and note it in EPIC-3336.
2. Convert loop by loop, one commit per file (or small group), running
   `ll-loop validate` on each.
3. For each site, verify the `cat >` terminator lands at **column 0** in the
   rendered action string — this is the failure that silently swallows the rest
   of the action.
4. Shrink the baseline's class-B entries in the same commit as each conversion.
5. Treat any new MR-11 warning as a failed conversion; **do not set
   `unsafe_context_interpolation_ok`**. (MR-11 does not match `captured.*` until
   ENH-3342, so it will not catch a missed class-B site for you — the baseline
   is the guard here.)
6. `python -m pytest scripts/tests/` exits 0 at every commit.

## Acceptance Criteria

1. ENH-3338's baseline has **zero** class-B entries.
2. Every conversion uses the `LL_RAW_9F3C1A7E_EOF` sentinel and a
   `<state>-<capture>.txt` filename;
   `grep -rn LL_RAW_9F3C1A7E_EOF scripts/little_loops/loops/` enumerates them and
   the count matches the converted-site count.
3. Every `cat >` heredoc terminator sits at column 0, above any enclosing
   `if`/`for` — verified specifically at `recursive-refine.yaml:82-83`,
   `rn-build.yaml:728-729`, and `loop-composer-adaptive.yaml:744`, the three
   known nested targets.
4. No site ships the half-and-half form (an `os.environ["LL_ARG_RUN_DIR"]` read
   with no corresponding binding, or a binding with a raw-interpolated path).
5. Newline sensitivity is decided per site; the trailing newline the heredoc
   appends does not change any consumer's behavior.
6. `ll-loop validate` clean on every touched file; no loop sets
   `unsafe_context_interpolation_ok`.
7. `python -m pytest scripts/tests/` exits 0 at every commit of this issue.
8. `:default=` guards on class-B captures are preserved, not dropped into Python.

## Impact

- **Priority**: P2 — inherited from EPIC-3336. The sharpest class: model-generated
  text parsed as Python, with no constraint on its content.
- **Effort**: Medium–Large — ~67 sites, each a multi-line block rather than
  BUG-3340's token swap, plus per-site judgment on hoisting and newline
  sensitivity.
- **Risk**: Medium — the column-0 hoist is the sharp edge. A terminator that
  fails to match swallows the remainder of the action, and like BUG-3339's
  failures it is invisible until the state runs. AC 3 pins the three known nested
  targets for that reason.
- **Breaking Change**: No — internal to loop action bodies.

## Notes

Each converted site writes an extra file into the run dir. That is consistent
with the `brainstorm.yaml` precedent and with run-dir artifact isolation (MR
rule: write under `${context.run_dir}/`, never bare `.loops/tmp/`). No cleanup
step is added — run dirs are already managed as a unit.

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-08-28T03:15:16 - `21c2bc4e-6e06-47c6-a164-ddb166a7cfff.jsonl`
- `/ll:format-issue` - 2026-08-28T03:03:20 - `486b558c-b1c6-4706-9fa1-9c30566c1e36.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
