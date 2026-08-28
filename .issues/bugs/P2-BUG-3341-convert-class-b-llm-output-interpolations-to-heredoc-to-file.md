---
id: BUG-3341
type: BUG
title: Convert class-B LLM-output interpolations to heredoc-to-file
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
completed_at: '2026-08-28T22:01:07Z'
parent: EPIC-3336
blocked_by:
- ENH-3337
- ENH-3338
- BUG-3339
- BUG-3340
blocks:
- ENH-3347
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 77
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
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
therefore covers only sites this issue converts. **Grandfathering covers only
those already-clean data-sink shapes, not the files** — `loop-composer.yaml`
still carries 2 live class-B entries (`finalize_present_result`:
`captured.chain_review.output`, `captured.user_plan_decision.output`) and
`brainstorm.yaml` one (`dedup_novelty`), all of which this issue does
convert. The "uniformity with the
shipped precedent" rationale for rejecting env-var binding is acknowledged
as weakened — the corpus now ships both remedies — but Option B stands for
new conversions on its file-based auditability and the per-site guidance
already written here.

## Integration Map

### Files to Modify

The authoritative list is ENH-3338's baseline filtered to `class == "B"`. The
confirmed per-file breakdown of the 82 entries (2026-08-28, from
`loop_interpolation_baseline.json`): `sft-corpus.yaml` (13),
`mechanize-skills.yaml` (8), `workflow-generator.yaml` (8),
`goal-cluster.yaml` (6), `rn-implement.yaml` (6), `loop-router.yaml` (5),
`recursive-refine.yaml` (5), `learning-tests-audit.yaml` (4),
`refine-to-ready-issue.yaml` (4), `assumption-firewall.yaml` (3),
`apply-research.yaml` (2), `loop-composer.yaml` (2),
`loop-composer-adaptive.yaml` (2), `migrate-sdk-version.yaml` (2),
`rn-build.yaml` (2), and one each in `autodev.yaml`, `brainstorm.yaml`,
`cli-anything-bootstrap.yaml`, `proof-first-task.yaml`, `lib/composer.yaml`,
`lib/policy-router.yaml`, `lib/rubric-router.yaml`,
`oracles/enumerate-and-prove.yaml`, `oracles/generator-evaluator.yaml`,
`oracles/generator-evaluator-flux.yaml`. Earlier drafts under-named this list
by ~24 entries (omitting `workflow-generator.yaml`, `rn-implement.yaml`,
`refine-to-ready-issue.yaml`, `loop-composer.yaml`, `autodev.yaml`,
`brainstorm.yaml`, `cli-anything-bootstrap.yaml`, `proof-first-task.yaml`) —
always re-derive from the baseline, not from any prose list including this
one. Note `brainstorm.yaml` — the precedent file itself — still carries one
live B entry (`dedup_novelty`, `captured.run_dir.output` ×3), a Decision
Rule 0 case. `general-task.yaml`
needs no further edits under this issue — BUG-3339 already converted its one
class-B site with the canonical sentinel and it has zero remaining class-B
baseline entries.

Known `if`-nested targets requiring the hoist: `recursive-refine.yaml:82-83`,
`loop-composer-adaptive.yaml:744`, and
`mechanize-skills.yaml:606-629` (`revert_changes`, two `python3 << 'PYEOF'`
heredocs nested inside `if [ -f "$MANIFEST" ]; then`). The `rn-build.yaml:728-729`
citation is stale anchor drift (review, 2026-08-28): those lines now land on
`check_harness_name`, which has no class-B site; rn-build's two actual B
sites — `write_epic_id` (`:523`, `captured.scope_project.output`) and
`read_harness_name` (`:621`, `captured.harness_plan.output`) — are both
top-level `python3 << 'PYEOF'` heredocs needing no hoist.

- `scripts/tests/data/loop_interpolation_baseline.json` — already exists
  (created by ENH-3338, 82 `class: "B"` entries as of this pass) — shrink
  class-B entries in the same commit as each conversion.
- **Relies on ENH-3338's data-sink heredoc rule** (its 2026-08-28 review
  fix, now shipped and confirmed live — `interp_sweep.py`'s `scan_action()`
  gates a heredoc as a Python body only when its opener line also contains
  `python3`, so a `cat > … << 'MARKER'` write scans as a data sink, not a
  Python body): without this rule, every conversion here would *add* a
  class-B baseline entry instead of removing one, and AC 1 would be
  unreachable. ENH-3338 is `done`; this dependency is satisfied.

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
- `scripts/tests/test_interp_sweep.py` — unit-tests `classify_site()`/
  `scan_action()`, the classifier AC 1's baseline shrink and the data-sink
  heredoc rule (see Files to Modify) depend on.
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

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- `scripts/tests/data/loop_interpolation_baseline.json` already exists (created by ENH-3338, landed 2026-08-28T16:03:35Z, after this issue's last refine) with 82 `class: "B"` entries as of this pass — it is not "new." See the `⚠ Superseded` marker on the Files to Modify line below.
- `general-task.yaml` requires no further edits under this issue: BUG-3339 already converted its one class-B site (`summarize_success`'s `captured.final_counts.output`) using the exact canonical `LL_RAW_9F3C1A7E_EOF` sentinel (`general-task.yaml:895-898`, confirmed via `grep -rn LL_RAW_9F3C1A7E_EOF scripts/little_loops/loops/`), validated by `test_general_task_loop.py:2114-2135`. It has zero remaining class-B baseline entries (both its baseline entries are `class: "C"`, `context.run_dir`). This is the first live use of the canonical sentinel, and a working exemplar of this issue's own Canonical block shape.
- `cua-agent-desktop.yaml` (cited in Similar Patterns) has zero baseline entries of any class — its `execute_action` state (`:408-423`) already writes `${captured.plan_output.output}` to a file via a `cat >` data-sink heredoc (bespoke sentinel `PLANEOF`) before reading it back, so it already scans clean as Option-B-equivalent and needs no conversion under this issue.
- A fourth nested-`if` class-B target exists beyond the three this issue names: `mechanize-skills.yaml:606-629` (`revert_changes` state, `captured.run_dir.output`, baseline entry at `loop_interpolation_baseline.json:770-777`) — two `python3 << 'PYEOF'` heredocs nested inside `if [ -f "$MANIFEST" ]; then`, terminators already at column 0. See the `⚠ Superseded` marker on AC 3.
- `scripts/little_loops/fsm/interp_sweep.py` is the scanner/classifier the baseline is generated/verified against and is not currently named anywhere in this issue. `classify_site()` (`:59-82`) is the single source of truth for the A/B/C rule (ENH-3342 imports it to widen MR-11 without duplicating the rule); `scan_action()`'s `_PYTHON3_WORD_RE` gate is what makes a `cat > file << 'MARKER'` data-sink heredoc scan clean — the exact "data-sink heredoc rule" this issue's Files to Modify note already depends on. `scripts/tests/test_interp_sweep.py` unit-tests `classify_site()`/`scan_action()` directly and is not currently in this issue's Tests list.
- Authoritative site count as of this pass: the baseline has 82 `class: "B"` entries (grep/JSON-confirmed), not the Summary/Impact sections' provisional ~67 — noted here since those sections are outside this command's editable scope, but the implementer should plan against 82, not 67 (already inclusive of the one site BUG-3339 converted).

## Program Design

### Signatures

No Python API change; this is a per-site edit inside loop YAML action strings.

- `interpolate(template, ctx)`
  (`scripts/little_loops/fsm/interpolation.py:209`) — substitutes the captured
  value into the `cat >` heredoc body. Unchanged.
- `_run_action(...)` (`scripts/little_loops/fsm/executor.py:2153`, write site at
  `:2425-2434`) — populates `self.captured[state.capture]`. **Unchanged** — this
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
   capture somewhere else before swapping. 21 of the 82 baseline entries are
   `captured.run_dir.output`, so this rule covers roughly a quarter of the
   work. **Known trap: `mechanize-skills.yaml` (all 8 of its entries are this
   var) captures the *absolutized* run dir** — its `init` state does
   `case "$DIR" in /*) RUN_DIR="$DIR";; *) RUN_DIR="$(pwd)/$DIR";; esac`
   (`mechanize-skills.yaml:64-67`) — so a naive swap to `${context.run_dir}`
   changes relative→absolute semantics for every consumer. There, either
   keep Option B or substitute `${context.run_dir}` and absolutize in the
   Python consumer (`os.path.abspath`); check each consumer before choosing.
   `workflow-generator.yaml`'s `capture: run_dir` similarly stores the
   state's *entire stdout* by design (comment at
   `workflow-generator.yaml:50-57`) — confirm the captured value is exactly
   the runner's run dir before swapping there too.
1. Derive the filename `<state>-<capture>.txt` from the state name and the
   capture variable name. Two captures in one state get two files. Two
   extensions of the rule (review decision, 2026-08-28): a `.stderr` site
   uses `<state>-<capture>-stderr.txt` so a capture whose `.output` and
   `.stderr` are both interpolated cannot collide (one `.stderr` site exists:
   `refine-to-ready-issue.yaml`, `check_scores_from_file`,
   `captured.check_scores_from_file.stderr`); a dotted capture path keeps its
   dots verbatim in the filename (one exists:
   `proof-first-task.yaml:59`, `${captured.gate.extracted.output}` →
   `check_gate_blocked-gate.extracted.txt`).
2. Place the `cat >` block at the action body's top level, above any `if`/`for`,
   even when the reading Python is nested.
3. Replace the in-literal interpolation with a read of that file.
4. Decide per site whether the consumer is newline-sensitive; add
   `.rstrip("\n")` where it is.
5. Preserve `:default=` semantics — `${captured.x.output:default=}` guards a
   capture from a state that never ran. Dropping it converts a graceful default
   into a loop failure. Under ENH-3337 the composed suffix is legal; keep it on
   the heredoc-body interpolation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- Anchors have drifted since this issue's last refine (intervening BUG-3339, BUG-3340, ENH-3337 commits shifted line numbers; substitution mechanics themselves are unchanged): `InterpolationContext.resolve()` is now at `interpolation.py:78` (was cited as part of `:209`); `interpolate()` is now at `interpolation.py:274` (issue's Signatures cited `:209`); `_run_action()` now starts at `executor.py:2153` (issue previously cited `:2097`, then `:2110` — both stale); the capture write-back (`self.captured[state.capture] = {...}`) is now at `executor.py:2425-2434` (issue previously cited `:2370-2391`, then `:2381-2403` — both stale); MR-11's `_UNSAFE_CONTEXT_INTERP_RE` is now at `scripts/little_loops/fsm/validation/shell_safety.py:34-36` (issue's Current Behavior section cited `:33-35`, confirmed current — no further drift). The substitution order (`resolve()` → `interpolate()` → `bash -c` argv) and `:default=`/`:shell` suffix composition are confirmed unchanged. (Re-verified 2026-08-28 by `/ll:ready-issue`; Signatures section updated to match.)
- `classify_site()` (`interp_sweep.py:59-82`) classifies any namespace it has no explicit verdict for as `"B"` as a safe-direction fallback. This means some baseline `class: "B"` entries are not `captured.*`/`prev.output`/`prev.stderr` sites at all but unrecognized namespaces caught by this fallback — e.g. `loops/oracles/generator-evaluator-flux.yaml`'s `synthesize` state has a class-B baseline entry for `state.iteration` via this rule, not the captured/prev rule Decision Rule 0 through 5 are written against. Decision Rule 0's `${context.run_dir}` substitution check does not cover this case — a per-site judgment is needed on whether an unrecognized-namespace B entry is genuinely LLM/command output requiring Option B, or a different kind of site the fallback is only guarding against defensively.

## Implementation Steps

1. Filter ENH-3338's baseline to `class == "B"`; the baseline holds 82 such
   entries (confirmed count, already inclusive of BUG-3339's one conversion),
   against the Summary's provisional ~67 — reconcile the divergence and note
   it in EPIC-3336. Pre-partition the 82 by Decision Rule 0: ~21 are
   `captured.run_dir.output` Rule-0 candidates (each still needs the
   point-elsewhere check, see the mechanize-skills trap), leaving ~61
   Option-B conversions.
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
   `<state>-<capture>.txt` filename (`<state>-<capture>-stderr.txt` for
   `.stderr` sites);
   `grep -rn LL_RAW_9F3C1A7E_EOF scripts/little_loops/loops/` enumerates them and
   the count matches the converted-site count.
3. Every `cat >` heredoc terminator sits at column 0, above any enclosing
   `if`/`for` — verified specifically at `recursive-refine.yaml:82-83`,
   `loop-composer-adaptive.yaml:744`, and
   `mechanize-skills.yaml:606-629` (`revert_changes`), the known nested
   targets (`rn-build.yaml:728-729` was stale anchor drift — its two B sites
   are top-level; see Files to Modify). For `mechanize-skills.yaml` (and any other site resolved via
   Decision Rule 0's `${context.run_dir}` substitution) "converted" reads as
   "converted or Rule-0-substituted" — a Rule-0 swap leaves no `cat >` block
   to hoist, and that satisfies this criterion.
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

## Resolution

Converted all 82 class-B baseline entries across 25 loop YAML files:

- **21 `captured.run_dir.output` sites** (Decision Rule 0): substituted
  `os.path.abspath("${context.run_dir}")` for the raw capture, wrapped in
  `os.path.abspath()` uniformly (including the two files with an
  absolutize-guard init state — `mechanize-skills.yaml`,
  `workflow-generator.yaml` — where Rule 0's own trap warning applies) so
  path semantics hold regardless of whether `context.run_dir` is relative or
  absolute at that state. `brainstorm.yaml`, `cli-anything-bootstrap.yaml`,
  and `rn-implement.yaml`'s three sites needed no init-state changes.
- **58 remaining sites**: converted to the canonical Option B
  heredoc-to-file block (`LL_RAW_9F3C1A7E_EOF` sentinel,
  `<state>-<capture>.txt` filename, `check_gate_blocked-gate.extracted.txt`
  for the one dotted-path site), preserving `:default=` semantics on the
  `finalize_present_result` sites shared by `loop-composer.yaml`,
  `loop-composer-adaptive.yaml`, and `goal-cluster.yaml`.
- **3 comment-only false positives** (`lib/composer.yaml`,
  `refine-to-ready-issue.yaml`, `generator-evaluator-flux.yaml`): the
  scanner matched a `${captured.*}`/`${state.*}` token inside prose
  explaining why that interpolation is *not* used live; reworded rather than
  converted, since there was no real interpolation to fix.

ENH-3338's baseline (`loop_interpolation_baseline.json`) now holds zero
class-B entries across all 151 scanned sites (AC 1). No loop sets
`unsafe_context_interpolation_ok`. Updated the handful of unit tests that
hand-substitute `${captured.run_dir.output}` / `${captured.*.output}`
tokens directly (they needed the new `${context.run_dir}` token added to
their replacement chains) and one narrow AC-7 test
(`test_mechanize_skills_validate_diagnosis_is_one_site`) whose pinned site
is now `context.run_dir`/class C by design.

`python -m pytest scripts/tests/` is green except three pre-existing
failures already present on `main` before this issue
(`test_no_new_unverifiable_evidence`, `test_readme_matches_repo_root`,
`test_no_prose_dependency_drift_in_repo`) — confirmed via `git stash`
against the unmodified tree.

## Status

**Done** | Created: 2026-08-27 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-08-28T22:00:10 - `b3e06a3f-a711-4aff-b397-97e241557980.jsonl`
- `/ll:ready-issue` - 2026-08-28T20:45:40 - `443665d2-f01e-4ae2-b4d2-6cfb947bc5ba.jsonl`
- `/ll:confidence-check` - 2026-08-28T20:41:45 - `bee584c2-5fe3-4187-93b9-2e213fdcc96f.jsonl`
- `/ll:confidence-check` - 2026-08-28T20:21:57 - `46a8948d-5f27-4b55-9948-2076e278ec4c.jsonl`
- `/ll:reconcile-issue` - 2026-08-28T19:54:53 - `80a08f28-6a5c-42b2-8c75-c8e70076692b.jsonl`
- `/ll:refine-issue` - 2026-08-28T19:48:46 - `32717b3b-863a-49e0-9597-080f0b40cfce.jsonl`
- `/ll:refine-issue` - 2026-08-28T03:15:16 - `21c2bc4e-6e06-47c6-a164-ddb166a7cfff.jsonl`
- `/ll:format-issue` - 2026-08-28T03:03:20 - `486b558c-b1c6-4706-9fa1-9c30566c1e36.jsonl`
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
