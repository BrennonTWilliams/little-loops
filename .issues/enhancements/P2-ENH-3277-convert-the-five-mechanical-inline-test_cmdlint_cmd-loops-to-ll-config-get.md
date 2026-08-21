---
id: ENH-3277
type: ENH
title: Convert the five mechanical inline test_cmd/lint_cmd loops to ll-config get
  (6 conversions)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T02:25:17Z'
labels:
- loops
- config
- test-cmd
- refactor
- follow-up
blocked_by: []
relates_to:
- BUG-3269
- ENH-3288
- BUG-3276
- ENH-2244
- ENH-3281
reconcile_attempted: true
decision_needed: false
confidence_score: 90
outcome_confidence: 63
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 10
score_change_surface: 25
---

# ENH-3277: Convert the five mechanical inline test_cmd/lint_cmd loops to ll-config get (6 conversions)

_Rescoped 2026-08-21: split at the risk boundary. The two loops whose conversion is a
control-flow redesign (`dead-code-cleanup`, `test-coverage-improvement`) moved to **ENH-3288**,
along with the `_PENDING_CONVERSION` teardown. This issue is now **5 files / 6 conversions**, all
mechanical — see the counts table below. Earlier "nine remaining sites" and "7 files / 8
conversions" framings are both superseded._

## Summary

Split out of **BUG-3269** (fourth-pass design review, 2026-08-20). BUG-3269 fixes the P0: the
three sites that emit a literal `None` on a present-but-null `project.test_cmd`
(`general-task.yaml:37`, `rl-coding-agent.yaml:60,68`), plus `general-task`'s baseline
sentinel and the mirror-drift gate.

This issue converts the **mechanical** "correct-but-guessing" reads from hand-rolled inline
`.ll/ll-config.json` parsing to `ll-config get project.<key>`, and shrinks BUG-3269's
`_PENDING_CONVERSION` exemption list from nine entries to four. **ENH-3288 empties and deletes
it** after converting the two structural loops.

**Counts.** `_PENDING_CONVERSION` ships with **nine** entries. Two (`rn-refine.yaml`,
`auto-refine-and-implement.yaml`) are **permanently exempted, not converted** — see *DECIDED
(Option A)* below. Two more (`dead-code-cleanup.yaml`, `test-coverage-improvement.yaml`) are
**ENH-3288's**. That leaves:

| | Count | Detail |
|---|---|---|
| Files converted here | **5** | `fix-quality-and-tests`, the three `harness-*`, `evaluation-quality` |
| Inline reads converted | **5** | one each — `fix-quality-and-tests.yaml:66`, `harness-single-shot.yaml:66`, `harness-multi-item.yaml:95`, `harness-plan-research-implement-report.yaml:126`, `evaluation-quality.yaml:58` |
| Hardcoded commands converted | **1** | `evaluation-quality.yaml:63`'s `ruff check scripts/` — a *different* defect class (step 5), not an inline read |
| **Total conversions here** | **6** | 5 inline reads + 1 hardcode |
| `_PENDING_CONVERSION` after this issue | **4** | `dead-code-cleanup`, `test-coverage-improvement` (ENH-3288) + the two permanently exempt |
| Deferred to ENH-3288 | **2 files / 2 reads** | one converted, one (`test-coverage-improvement.yaml:45`) deleted as dead |
| Sites permanently exempted | **3** | `oracles/code-run-gate.yaml` + the two above |

The read/hardcode distinction matters: they are handled by different steps (4 vs 5) and only the
reads are visible to the mirror-drift gate.

**Why this is not part of the P0.** None of these sites can produce BUG-3269's failure: they are
shaped `raw if raw else 'pytest'` and never emit `None`. They are wrong in a milder way — they
override an explicit `test_cmd: null` with a `pytest` guess, and they bypass `.ll/ll.local.md`
(§1b there).

**Why the other two are not here.** `dead-code-cleanup` and `test-coverage-improvement` gate an
`on_yes: commit` edge on the test suite, so a naive conversion commits unverified work — the
sharpest behavior change in the family, and a control-flow redesign rather than a substitution.
That analysis must not gate this pass any more than it should have gated the P0. It is **ENH-3288**.

All design work already exists in BUG-3269 and is not repeated here — read it there:
its §1 (`ll-config get`'s verified three-way contract), §1b (the `ll.local.md` bypass),
§1d (`oracles/code-run-gate.yaml`'s permanent exemption), §1f (why a non-zero exit is
unroutable at `evaluate: exit_code` states), §2 (per-site precedence — **config-first bare
at all five sites here**), and especially **§2b (the per-site empty-`CMD` table)**.

## Current Behavior

Nine files parse `.ll/ll-config.json` inline. Seven of them resolve a present-but-null
`test_cmd` to a guessed `pytest` via `raw if raw else 'pytest'`, gating on a test suite the
project deliberately opted out of. The other two (`rn-refine.yaml`,
`auto-refine-and-implement.yaml`) use a falsy-*skip* shape instead and are correct on
present-null today — see the *DECIDED (Option A)* block, which is the entire reason they are not
mechanical and are now exempted rather than converted. All nine additionally ignore `.ll/ll.local.md`, the mechanism `.claude/CLAUDE.md`
documents *specifically* for overriding `project.test_cmd`.

`evaluation-quality.yaml:63` is a related pre-inlined case: a hardcoded `ruff check scripts/`
with no config read at all, sitting five lines below a site in this list.

BUG-3269's mirror-drift gate red-lists all of these in a `_PENDING_CONVERSION` constant, so
they are blocked from growing but not yet fixed.

## Expected Behavior

Every site resolves through `ll-config get project.<key>`, honoring the three-way contract
(absent → `ProjectConfig` field default; present-and-null → opt out; value → value) and
`.ll/ll.local.md`. `_PENDING_CONVERSION` is empty and the constant is deleted.

## Motivation

**The duplication is the defect class.** BUG-3269 proved that hand-rolled config resolution
diverges: `general-task.yaml` resolved the same key two different ways *inside one file*, and
one of them spun a run for 4h58m. Fixing only the three sites that emit `None` leaves nine
copies that are one careless edit from the same failure — the fourteenth copy is stopped by the
mirror-drift gate BUG-3269 shipped, but the existing nine are grandfathered in by its
`_PENDING_CONVERSION` list.
This issue removes the grandfathering.

**Two live (non-P0) defects close with it.** Seven of the nine override an explicit
`test_cmd: null` with a guessed `pytest` — so a docs or diagram project that deliberately
opted out still gets gated on a suite it does not have — and all nine bypass
`.ll/ll.local.md`, the mechanism `.claude/CLAUDE.md` documents *specifically* for overriding
`project.test_cmd`. Every one of these loops is live in every `local-editable` consuming
project on this machine with no reinstall step.

**Deferred deliberately, not incidentally.** The cost of *not* splitting was shipping a
commit-of-deletions behavior change on `dead-code-cleanup` inside a P0 hotfix. The cost of
splitting is that `_PENDING_CONVERSION` exists until this lands. That is the right trade, but
the list is technical debt with a name, and this issue is its payoff.

## Proposed Solution

Convert one file at a time, applying BUG-3269 §2's precedence shape and §2b's empty-`CMD` row
for that specific site. After each file: `ll-loop validate`, the scoped `grep` from step 6 (which
must exclude the two permanently-exempt files), and BUG-3269's gate with one entry removed from
`_PENDING_CONVERSION`.

### Behavior Parity

What the inline `.ll/ll-config.json` parse is replaced by, per input:

| `.ll/ll-config.json` state | Inline parse today | `ll-config get project.<key>` | Parity? |
|---|---|---|---|
| Key set to a value | that value | that value | **identical** |
| Key absent | `'pytest'` literal (per call site) | `ProjectConfig` field default — `pytest` / `ruff check .` | **identical for `test_cmd`**; `lint_cmd` widens from the hardcoded `ruff check scripts/` to `ruff check .` at `evaluation-quality.yaml:63` only |
| Key present-and-null | `'pytest'` guess (`raw if raw else`) — except `fix-quality-and-tests`, which prints `true` | empty string → that site's §2b branch | **intended change**: the opt-out is honored instead of overridden. `fix-quality-and-tests` is already-equivalent (`eval "true"` and `eval ""` both exit 0 → `done`) |
| File absent entirely | `'pytest'` | `pytest` (rc 0) | **identical** |
| `.ll/ll.local.md` overrides the key | ignored | honored (deep-merged in `_load_config`) | **intended change**: the documented override mechanism starts working |
| `ll-config` binary missing | n/a | empty `CMD` → §2b branch | **new failure mode**, accepted — see *Risk accepted* under *Impact* |

Not in parity scope: exit codes (`ll-config get` returns 0 in every row above, verified
empirically under *Codebase Research Findings*), routing (unchanged at all five sites), and
`evaluate_code`'s own exit status (must stay 0 — *EXIT-CODE CORRECTION*).

### DECIDED (Option A) — `rn-refine` and `auto-refine` are permanently exempt

**Resolved 2026-08-21 via `/ll:decide-issue`; scoring in *Decision Rationale* below.** Both files
keep their inline `.ll/ll-config.json` parse and move from `_PENDING_CONVERSION` to
`_PERMANENT_EXEMPTIONS`. Nothing in this issue is blocked by this any longer — step 3b is a
two-line test-constant edit, not a conversion. The finding that forced the decision is retained
below because it is the exemption's rationale.

**The finding.** Two of the eleven call sites do *not* use the `raw if raw else 'pytest'` shape
this issue's original framing assumed. They use a falsy-skip shape, and for them **conversion introduces
a guess rather than removing one**:

| Site | Current shape | Absent key today | Absent key after conversion |
|---|---|---|---|
| `rn-refine.yaml:991` | `.get('test_cmd') or ''` → `[ -z ]` → `exit 0` | **skip** (comment at `:983-984` says so verbatim: *"absent file/key just skips the gate"*) | `pytest` runs; a failure writes `RECOVERY_NEEDED` into `plan-rubric.md` |
| `auto-refine-and-implement.yaml:433-436` | `if not test_cmd: emit('skipped')`; `lint_cmd` falsy → `continue` at `:449-450` | **skip** — `verify_verdict: "skipped"` | `pytest` runs; `lint_cmd` absent → `ruff check .` runs; the state stops emitting `skipped` |

The defaults come from `ProjectConfig` (`config/core.py:191-192`): `test_cmd: str = "pytest"`,
`lint_cmd: str = "ruff check ."`.

**Why §2b doesn't cover it.** The §2b table axes on *"empty `CMD` → what happens"*. For these two
the change isn't at the empty branch — it's that **the empty branch stops being reached**. Both
already handle empty correctly today.

**The root constraint.** `ll-config get` collapses *absent* and *defaulted* into one output: an
absent key prints the `ProjectConfig` field default, indistinguishable from a config that set that
exact value. The three-way contract is therefore a superset of `raw if raw else 'pytest'` but is
**lossy against an absent≡skip contract**. This is precisely BUG-3269 §1d's rationale for
`oracles/code-run-gate.yaml`'s permanent exemption — *absent ≡ null ≡ skip, never guess* — and it
applies verbatim to these two sites.

**Where the lossiness actually lives — verified 2026-08-21.** It is one method call, not a
structural property. `resolve_variable` walks `self.to_dict()` (`config/core.py:1039-1044`),
which is *post-dataclass*: by the time it runs, `ProjectConfig.from_dict`'s
`data.get("test_cmd", "pytest")` (`core.py:214`) has already substituted the field default for an
absent key. But `BRConfig` **also retains the pre-dataclass merged dict** as `self._raw_config`
(`core.py:262`), assigned from `_load_config()` — which already deep-merges `.ll/ll.local.md`
frontmatter on top of `.ll/ll-config.json` (`core.py:265-293`, BUG-3123). A read that walks
`_raw_config` instead of `to_dict()` distinguishes absent from defaulted **and stays
`ll.local.md`-aware**. This materially lowers Option C's cost — see below.

**Options:**

> **Selected:** Option A — permanently exempt both. Smallest, lowest-risk change; matches the
> `oracles/code-run-gate.yaml` precedent exactly and touches no production code. See Decision
> Rationale below.

**Option A — permanently exempt both. SELECTED.** Move `rn-refine.yaml` and
`auto-refine-and-implement.yaml` from `_PENDING_CONVERSION` to `_PERMANENT_EXEMPTIONS` with the
§1d rationale. Preserves both contracts exactly; costs the `.ll/ll.local.md` fix at those two
sites and leaves two inline parses alive. `_PENDING_CONVERSION` still empties and deletes (step
6 unaffected in shape).

**Option B — accept the guess. REJECTED.** Convert as drop-ins and accept that unconfigured projects start
running `pytest` / `ruff check .` at these two gates. Requires updating
`skills/audit-loop-run/SKILL.md:~277`'s `verify_verdict: "skipped"` documentation as a real
semantic change, not a sanity check — and note `rn-refine`'s gate writes `RECOVERY_NEEDED` into
a user-facing artifact on failure.

**Option C — add a no-default read mode. REJECTED (retained as the documented fallback).**
`ll-config get --raw project.test_cmd`, printing
nothing when the key is absent from the merged config rather than falling back to the
`ProjectConfig` field default. Fixes the class rather than the two instances, makes both sites
genuine drop-ins **and** `ll.local.md`-aware, and is the only option that could later retire
`oracles/code-run-gate.yaml`'s permanent exemption. Breaks this issue's "No new production code"
boundary (`cli/config.py` gains a flag) and needs its own resolution-semantics tests.

*Cost, re-estimated against the tree:* smaller than the original framing assumed. Per **Where the
lossiness actually lives** above, `--raw` is a dot-walk over the already-merged
`BRConfig._raw_config` instead of `to_dict()` — roughly fifteen lines in `cli/config.py` plus a
`get_parser.add_argument("--raw", action="store_true")`. It introduces **no new resolution
machinery and no new merge order**: same file, same `.ll/ll.local.md` deep-merge, same never-raise
contract. The only new semantics to test is "absent key under `--raw` prints nothing", which is
exactly what the two blocked sites' `[ -z ]` branches already test for. It is also §1f-compatible
by construction: `main_config` returns `0` unconditionally by documented contract (`cli/config.py`
docstring and `--help` epilog, `:36-40`), so empty stdout stays the sole signal and no non-zero
exit is introduced at an `evaluate: exit_code` state.

**Accepted cost of Option A.** Both files keep bypassing `.ll/ll.local.md` and stay on inline
`.ll/ll-config.json` parsing indefinitely, and the path to eventually retiring
`oracles/code-run-gate.yaml`'s exemption via `--raw` is deferred rather than taken. Option C
remains the documented fallback should a future issue need `ll.local.md` support at these two
sites specifically — its groundwork (the `_raw_config` distinction, verified above) exists and
works as described, so it can be picked up without re-deriving the analysis. Option B is not a
fallback under any circumstance: it is the only option that changes behavior in unconfigured
consuming projects, which is the exact failure mode this issue family exists to close.

`oracles/code-run-gate.yaml` stays out of scope regardless of option — its alias-pair resolution
(`typecheck_cmd|type_cmd`) is a separate unmet requirement that `--raw` would not have addressed.

### Hard prerequisite — pick a §2b row per site before writing any shell

This is the reason the family was split, not an afterthought to it. Under `fragment: shell_exit`,
`eval ""` exits **0**, so an empty `CMD` makes the gate silently **pass** against an empty
artifact.

**Two distinct hazards, not one — the sites split by state kind.** Four of this issue's five read
sites sit in a `fragment: shell_exit` state where the false-pass applies:
`fix-quality-and-tests.check-tests` and the three `harness-*.check_concrete` states. All four are
nonetheless **pass-on-empty**, because their `on_yes` leads either to `done` on an
already-equivalent routing (`fix-quality-and-tests`, verified in the table below) or to a further
LLM gate that still runs.

The fifth — `evaluation-quality.evaluate_code` (`action_type: shell`, `capture: code_results`,
`next: score`) — has **no gate to falsely pass**. Its hazard is different and narrower: an empty
`CMD` produces an empty *artifact* that a downstream scorer consumes as if it were a real test
signal. That is why it is this issue's one explicit-skip site. Do not go looking for an `on_yes`
edge there — there isn't one.

_(The sites where an empty `CMD` could reach an irreversible `commit` — `dead-code-cleanup` and
`test-coverage-improvement` — are **ENH-3288's**. That asymmetry is the split.)_

Per BUG-3269 §2b:

| Site | `on_yes` | Decision |
|---|---|---|
| `fix-quality-and-tests.yaml:58-78` | `done` | pass-on-empty; drop-in — **verified**: its three-way body prints `true` on present-null → `eval "true"` → exit 0 → `done`; post-conversion an empty `CMD` → `eval ""` → exit 0 → `done`. Identical routing. Delete the three-way python body, do not generalize it |
| `harness-single-shot.yaml:61-72` | `check_semantic` | pass-on-empty (LLM gate still runs) |
| `harness-plan-research-implement-report.yaml:121-132` | `check_semantic` | pass-on-empty |
| `harness-multi-item.yaml:90-100` | `check_mcp` | pass-on-empty |
| `evaluation-quality.yaml:58` (`test_cmd`) | **none — `next: score`, ungated** | **explicit skip required.** Emit a "no test signal" marker **on stdout** (see *CAPTURE CORRECTION* below) — **not** by rerouting; `evaluate_code` has no `on_yes`/`on_no` edges |
| `evaluation-quality.yaml:63` (`lint_cmd`) | **none — same state** | **explicit skip required.** Same hazard, same state, separate branch: post-conversion an empty `LINT_CMD` makes `eval "" \| tee eval-lint-results.txt` write an empty file *and* contribute nothing to stdout, which `score` reads as *clean lint*. Emit a "no lint signal" marker on stdout instead. The existing `\|\| true` makes this non-gating, so the risk is a falsified artifact, not a false pass |
| `dead-code-cleanup.yaml:71-81`, `test-coverage-improvement.yaml:45` and `:143-158` (read at `:152`) | `commit` / ungated | **SPLIT OUT — ENH-3288.** All three need explicit-skip handling on an `on_yes: commit` edge, which requires a `harness_exit` fragment switch and new states. Not this issue's work; do not convert them here |
| `rn-refine.yaml:986-994` | advisory only | **NOT CONVERTED — permanently exempt (Option A).** Its absent≡skip contract inverts under `ll-config get`. Left exactly as-is, including the already-correct `[ -z "$TEST_CMD" ]` branch at `:995-997` |
| `auto-refine-and-implement.yaml:433-436` | `emit('skipped')` | **NOT CONVERTED — permanently exempt (Option A).** It treats falsy *and absent* `test_cmd` as skipped, and absent stops being falsy after conversion |

**Rule:** a site whose `on_yes` edge performs an irreversible action (`commit`) or feeds a
score must handle `[ -z "$CMD" ]` explicitly. A site whose `on_yes` leads to another gate may
pass on empty.

#### CAPTURE CORRECTION (2026-08-21) — `capture:` reads **stdout**, not the `tee` target

**Verified against the tree; supersedes the earlier parenthetical "`eval-test-results.txt`
(what `capture: code_results` reads)" wherever it survives.**

`capture: code_results` (`evaluation-quality.yaml:64`) captures `evaluate_code`'s **stdout**.
The downstream consumer is `score`, which interpolates `${captured.code_results.output}`
(`:77`) — it never opens `eval-test-results.txt` or `eval-lint-results.txt`. Those files exist
only as a side-effect of `tee` and are read by nothing in this loop.

Consequence for both skip branches: a marker written with a plain file redirect —
`echo "..." > ${context.run_dir}/eval-test-results.txt` — satisfies the letter of the §2b row
and still hands `score` a blank "Code quality results" block. That is precisely the falsified
signal the row exists to prevent, reintroduced by the remedy.

**Required shape at both branches:** the marker must reach stdout. Either

```bash
echo "NO TEST SIGNAL — project.test_cmd is null; no suite ran" \
  | tee ${context.run_dir}/eval-test-results.txt
```

or a bare `echo` (the file is optional; the capture is not). Do not use `>`.

A regression test for this state must assert on the state's **captured stdout**, not on file
contents, or it will pass against the broken shape.

#### EXIT-CODE CORRECTION (2026-08-21) — `evaluate_code` exits 0 only by accident today

**Verified against the tree.** `evaluate_code` declares `action_type: shell` with **no
`evaluate:` block and no `fragment:`**, so `_evaluate` falls through to its shell default —
`evaluate_exit_code(action_result.exit_code)` (`fsm/executor.py:2608-2610`) — and a non-zero
exit produces a `no` verdict at a state whose only edge is `next: score`.

Today that never fires, but only as a side-effect: `set -o pipefail` is in force and the test
line carries **no** `|| true`, so a failing suite *does* leave a non-zero status — it is
overwritten purely because the last line of the action is `ruff check scripts/ … || true`,
which forces the script's exit status to 0. The state's benign exit code is therefore load-bearing
behavior resting on statement order, not on anything declared.

**Steps 4 and 5 restructure both branches of exactly that action.** A natural rewrite —
`if [ -z "$CMD" ]; then echo … | tee …; else eval "$CMD" 2>&1 | tee …; fi` as the final
statement, with the lint branch above it — makes a **failing test suite** set this state's exit
code non-zero for the first time. That is a control-flow change smuggled into an issue whose
*Impact* section explicitly promises "no control-flow edits anywhere."

**Required:** `evaluate_code` must exit 0 unconditionally after conversion, in all four
combinations of (`test_cmd` set / empty) × (suite passes / fails). The simplest shape that
preserves this is to keep a trailing `|| true` on whichever statement ends the action, or to end
the action with an explicit `exit 0`. Pin it with a test (see *Tests*); do not rely on statement
order surviving a future edit.

### Structural sites — split out to ENH-3288

**`dead-code-cleanup.yaml` and `test-coverage-improvement.yaml` are no longer this issue's
work.** Both gate an `on_yes: commit` edge on the test suite, so converting them requires a
`fragment: shell_exit` → `fragment: harness_exit` switch, an exit-code normalization, four new
states, and `initial:`/`max_steps:` edits — a control-flow redesign, not a shell substitution.
All of that analysis moved verbatim to **ENH-3288** (`blocked_by: [ENH-3277]`), which also carries
the *Dead site* decision, the MECHANISM / EXIT-CODE COLLISION / TERMINAL-ACTION corrections, and
the final `_PENDING_CONVERSION` teardown.

This issue keeps the six conversions that are pure find-and-replace, and shrinks
`_PENDING_CONVERSION` from nine entries to four. Do not touch either structural loop here.

### The gate file's own prose is falsified by this issue

**Verified against the tree 2026-08-21.** `scripts/tests/test_bug3269_test_cmd_resolution_gate.py`
asserts in **three** places that *this* issue empties and deletes `_PENDING_CONVERSION`. The split
moved that to ENH-3288, so all three become false the moment this issue lands, in the file that is
the family's own source of truth:

| Anchor | Current text | Required |
|---|---|---|
| Module docstring `:23-27` | *"populated with the nine sites deferred to ENH-3277 … **ENH-3277's definition of done is that `_PENDING_CONVERSION` is empty and can be deleted.**"* | Nine → four; the definition-of-done sentence reassigned to **ENH-3288** |
| `_PENDING_CONVERSION` comment `:52-55` | *"sites deferred to ENH-3277 (blocked_by: [BUG-3269]) … ENH-3277's definition of done is emptying this set and deleting it."* | Same reassignment |
| `test_pending_conversion_sites_still_exist` assertion message `:155` | *"shrink the exemption list (ENH-3277)"* | → ENH-3288 |

**And the set's name becomes a lie for two of its four members.** Option A made `rn-refine.yaml`
and `auto-refine-and-implement.yaml` **permanent** exemptions, but ENH-3288 owns the move into
`_PERMANENT_EXEMPTIONS` (its step 5). So between this issue and that one, a set literally named
`_PENDING_CONVERSION`, under a docstring promising it will be emptied, lists two files that will
never be converted. Annotate both entries in place with a one-line `# Permanently exempt per
ENH-3277 Option A — moves to _PERMANENT_EXEMPTIONS in ENH-3288 step 5` comment so the gap is
documented rather than merely survived.

This is prose-only — no assertion logic changes, no test breaks. It is in scope precisely because
leaving it is worse than not splitting: the next reader of the gate is told the wrong issue owns
the teardown.

### The three `harness-*` sites are user-facing templates

Not a footnote to their "pass-on-empty, low-risk" §2b rows. All three `check_concrete` states are
explicitly authored as copy-me scaffolds — `harness-single-shot.yaml:57-60` reads *"# EXAMPLE:
Cheapest gate first — run the project's configured test suite. / # Reads test_cmd from
.ll/ll-config.json; falls back to 'pytest' if absent. / # Replace the Python snippet with a direct
command if you prefer"*, with near-identical text at `harness-multi-item.yaml:88` and
`harness-plan-research-implement-report.yaml:120`.

These are the loops a user clones when authoring their own. The stale comments are therefore not
documentation drift to tidy alongside the code — **they actively teach the inline-parse
anti-pattern that BUG-3269's mirror-drift gate exists to stop from reaching a fourteenth copy.**
The comment rewrite at those three anchors is load-bearing, and it is a further argument for
step 3's ordering (these convert first).

#### Pinned replacement text — use this verbatim at all three anchors

"Rewrite to stop teaching the inline parse" is not a specification; three implementers would
write three different comments into three copy-me scaffolds. Use exactly this, adjusting only
the trailing `# Replace ...` line where the current file already has one
(`harness-single-shot.yaml:59-60`) and omitting it where it does not:

```yaml
    # EXAMPLE: Cheapest gate first — run the project's configured test suite.
    # Resolves project.test_cmd via `ll-config get`, which honors .ll/ll.local.md
    # and the three-way contract: key absent → ProjectConfig default (`pytest`);
    # present-and-null → empty, meaning the project opted out of a test suite;
    # value set → that value.
    # NOTE: an opted-out project yields an empty CMD, `eval ""` exits 0, and this
    # gate PASSES. That is deliberate here (the next state is a further gate). If
    # you clone this into a loop whose on_yes performs an irreversible action, add
    # an explicit `[ -z "$CMD" ]` branch — see ENH-3288.
```

The second paragraph is the load-bearing half: a cloner who copies a pass-on-empty gate onto an
`on_yes: commit` edge reproduces exactly the hazard that forced this issue's split. The comment
is where that warning has to live, because the shell body no longer shows the fallback.

### Precedence — config-first bare at all five sites

Only three loops declare a `context.test_cmd` key at all (`general-task.yaml:23`,
`test-coverage-improvement.yaml:23`, `rl-coding-agent.yaml:17`), and **none of them is a target
of this issue** — `test-coverage-improvement` moved to ENH-3288. So every site here is
config-first bare, with no exceptions. **Do not paste the context-first shape into any of them**
— an undeclared `${context.test_cmd}` raises `InterpolationError: Path 'test_cmd' not found in
context` at interpolation time, turning a mechanical conversion into a hard loop breakage.
BUG-3269's gate assertion (ii), `test_context_references_are_declared`, catches this statically.

All five sites — `fix-quality-and-tests`, the three `harness-*`, and `evaluation-quality`'s
`test_cmd` **and** `lint_cmd`:

```bash
CMD=$(ll-config get project.test_cmd)
```

**Do NOT add a `|| { ...; exit N; }` guard** — BUG-3269 §1f: at `evaluate: exit_code` states a
non-zero exit routes to `on_no`, and `ll-config get` exits 0 in every case anyway (verified
empirically under *Codebase Research Findings*), so the guard is unreachable code that changes
routing if it ever does fire.


### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- The three sites BUG-3269 already converted establish two coexisting precedent shapes, both
  confirmed live in the codebase today:
  - **Config-first bare** (no context override declared): `rl-coding-agent.yaml:56-63` —
    `TEST_CMD=$(ll-config get project.test_cmd)` / `LINT_CMD=$(ll-config get project.lint_cmd)`,
    with an in-file comment explaining that a context key here would never be reachable since
    `ll-config get` always wins under this shape.
  - **Context-first with an exit-code check** (only where `context.test_cmd` is declared):
    `general-task.yaml:54-63` and `incremental-refactor.yaml:36-44,78-86` share this exact
    shape — context wins if non-empty; otherwise `CMD=$(ll-config get project.test_cmd);
    RC=$?; if [ "$RC" != "0" ]; then CMD=""; fi`. This captures `$?` into a named variable and
    forces `CMD=""` on a nonzero exit, rather than the `|| { ...; exit N; }` guard this issue's
    Proposed Solution says not to add — the two are different mechanisms with different routing
    consequences at an `evaluate: exit_code` state. `test-coverage-improvement.yaml` is this
    issue's one target site that already declared `context.test_cmd` (line 23) — **but it moved
    to ENH-3288**, and its `measure` branch is dead anyway (the resolved `CMD` is never used; only
    `$COV_CMD` is eval'd at `:62`). Neither shape is a model to copy here: **no site in this issue
    declares the key**, so context-first is unavailable at all five. Retained only as orientation
    for the two coexisting precedents in the tree.
- Skip-on-empty has four coexisting variants in the codebase, disagreeing on mechanism. Only the
  first is relevant to this issue's one explicit-skip site (`evaluation-quality`, which has no
  gate to route away from); the other three are **ENH-3288's** and are retained here only so the
  precedent survey stays intact:
  - **Pass-through**: `rl-coding-agent.yaml:68-75,79-85` — empty `TEST_CMD`/`LINT_CMD` sets the
    corresponding score to `0.0` and continues in the same state, no transition.
  - **Route-away via exit code**: `incremental-refactor.yaml` `check_preconditions:46-49` —
    empty `CMD` writes a failure artifact and `exit 1`, caught by that state's `on_no: failed`
    edge.
  - **Reserved exit code**: `incremental-refactor.yaml` `verify_tests:99-128` — `[ -z "$CMD" ] &&
    exit 3` (`:120`), routed via a dedicated `on_cannot_judge: failed` edge (`:127`) kept
    distinct from a real test failure's `on_no: revert`. **Anchor + mechanism correction
    (2026-08-21):** the earlier `:87` citation is stale post-BUG-3276, and the routing works
    only because that state is **`fragment: harness_exit`** — `abstain_on_exit_3: true` is what
    turns `exit 3` into `cannot_judge`. Copying the shell body onto a `shell_exit` state without
    the fragment switch silently routes `exit 3` to `on_error`. See ENH-3288's *MECHANISM
    CORRECTION* — that hazard applies only to its two structural sites, not to anything here.
  - **Entry precondition (added 2026-08-21, post-BUG-3276)**: `incremental-refactor.yaml`
    `check_preconditions:20-86` also *refuses to start* when `test_cmd` is unresolvable,
    unrunnable (exit 127), or already red, writing `precondition-failure.txt` and `exit 1` →
    `on_no: failed`. A fourth variant, and ENH-3288's pinned shape for `dead-code-cleanup`.
- **`ll-config get`'s contract re-verified empirically (2026-08-21)**, in a scratch project
  outside this repo: `test_cmd: null` → rc 0, empty stdout; key absent → rc 0, `pytest`;
  value set → rc 0, the value; no `.ll/ll-config.json` at all → rc 0, `pytest`. **It exits 0 in
  every case**, so the `RC=$?; if [ "$RC" != "0" ]; then CMD=""; fi` half of the context-first
  shape is inert-but-harmless defensive code today. Keep it for consistency with the three
  already-converted sites; do not treat a non-zero exit as a reachable branch when writing tests.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s "Resolving a Project Command Inside a Loop"
  section is at lines 516-569, with the absent/null/value contract table at lines 528-532 and
  an explicit note naming this issue: "A handful of other loops are a temporary exemption
  pending ENH-3277's conversion pass."
- `dead-code-cleanup.yaml`'s current inline resolution (the site whose `on_yes: commit` this
  issue calls the sharpest change in the family) guesses `'pytest'` for both an absent and a
  present-and-null `test_cmd` via `raw if raw else 'pytest'` — `None` and `''` are both falsy in
  Python, so today a present-and-null config still runs the guessed default and can reach
  `on_yes: commit`.

### Decision Rationale

_Added by `/ll:decide-issue` — 2026-08-21:_

**Selected: Option A — permanently exempt `rn-refine.yaml` and `auto-refine-and-implement.yaml`.**
Move both from `_PENDING_CONVERSION` to `_PERMANENT_EXEMPTIONS` in
`scripts/tests/test_bug3269_test_cmd_resolution_gate.py`, reusing `oracles/code-run-gate.yaml`'s
existing exemption rationale (BUG-3269 §1d: absent ≡ null ≡ skip, never guess). Parallel agents
gathered independent codebase evidence for all three options; Option A scored highest on
consistency, simplicity, and risk, despite the issue's own text recommending Option C.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| **A — permanent exemption (selected)** | 3 | 3 | 2 | 2 | **10/12** |
| B — accept the guess | 0 | 3 | 2 | 0 | 5/12 |
| C — add `--raw` read mode | 3 | 1 | 2 | 1 | 7/12 |

**Key evidence:**
- **A is a clean precedent match, not a novel exemption.** `_PERMANENT_EXEMPTIONS = {"oracles/code-run-gate.yaml"}` (`test_bug3269_test_cmd_resolution_gate.py:49`) already documents exactly this rationale; adding two entries is the same shape, not a new one. The move is a ~2-line edit with zero test breakage: `test_pending_conversion_sites_still_exist` only iterates the shrunken set, `test_general_task_and_rl_coding_agent_are_not_exempt` is unaffected, and no other test file references either set.
- **B reintroduces the defect this issue exists to close.** Confirmed by direct read of both sites: converting `rn-refine.yaml:986-997` and `auto-refine-and-implement.yaml:430-437` to bare `ll-config get` reads means an *unconfigured* project's `test_cmd`/`lint_cmd` resolve to the schema default (`"pytest"` / `"ruff check ."`, `config-schema.json:30-39`) instead of skipping — `rn-refine`'s gate would then write a real `RECOVERY_NEEDED` line into the user-facing `plan-rubric.md`, and `auto-refine-and-implement`'s verify state would actually run pytest/ruff instead of emitting `"skipped"`. This is precisely the "guess a default for an absent key" failure class BUG-3269/ENH-3277 exist to eliminate.
- **C is real but costs shared production surface for a 2-site problem.** Confirmed: `cli/config.py` currently has zero optional flags (only positional `key`), so `--raw` is a new pattern, not a drop-in extension — and it dot-walks `BRConfig._raw_config`, machinery every other config consumer also depends on. The `_raw_config` lossiness claim was independently verified (`config/core.py:265-294` builds it pre-dataclass; `ProjectConfig.from_dict:215-216` is where the default gets injected; `resolve_variable:1039-1061` walks the post-dataclass `to_dict()` and can never see the distinction again) — so C is real and closes the defect *class*. But it is disproportionate cost for exactly two call sites, needs its own resolution-semantics test class, and touches config-loading code shared by every already-converted site in this issue family.
- **Trade-off accepted:** both files keep bypassing `.ll/ll.local.md` and stay on inline `.ll/ll-config.json` parsing indefinitely, and Option C's path to eventually retiring `oracles/code-run-gate.yaml`'s exemption is foreclosed. If a future issue needs `.ll/ll.local.md` support at these two sites specifically, Option C is the fallback — its groundwork (the `_raw_config` distinction) is already verified to exist and work as described.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/fix-quality-and-tests.yaml:58-78` — three-way body deleted
- `scripts/little_loops/loops/evaluation-quality.yaml:58` — and `:63`'s hardcoded
  `ruff check scripts/` → `ll-config get project.lint_cmd`
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:126` — and its
  template comment at `:120` (load-bearing; see *The three `harness-*` sites are user-facing
  templates*)
- `scripts/little_loops/loops/harness-multi-item.yaml:95` — and its template comment at `:88`
- `scripts/little_loops/loops/harness-single-shot.yaml:66` — and its template comment at `:57-60`
- The `_PENDING_CONVERSION` constant landed by BUG-3269
  (`scripts/tests/test_bug3269_test_cmd_resolution_gate.py:55-65`) — **shrunk from nine entries
  to four**, one per converted file. Not emptied and not deleted here: that is ENH-3288's step 6,
  and `test_pending_conversion_sites_still_exist` keeps the remaining four honest in the meantime.
- **The same file's prose, in three places** — see *The gate file's own prose is falsified by this
  issue* below. Not optional cleanup: all three currently assert something this issue makes false.

Out of scope: `dead-code-cleanup.yaml` and `test-coverage-improvement.yaml` (**ENH-3288**);
`rn-refine.yaml` and `auto-refine-and-implement.yaml` (permanently exempt, Option A — the
constant move is ENH-3288's step 5); `oracles/code-run-gate.yaml` (permanent exemption, BUG-3269
§1d); `incremental-refactor.yaml` (BUG-3276).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rl-coding-agent.yaml:62-63` and
  `scripts/little_loops/loops/general-task.yaml:57` and
  `scripts/little_loops/loops/incremental-refactor.yaml:62-63` — the three **already-converted**
  precedent sites (BUG-3269/BUG-3276); confirmed to have exactly one `ll-config get project.<key>`
  call site each (no second unconverted call site in `rl-coding-agent.yaml` — verified directly;
  an earlier wiring-agent lead claiming a second inline `get_value` helper at lines 133-181 did
  not reproduce on read and is a false positive). Model the nine conversions on these shapes, not
  new ones. [Agent 1 finding, confirmed]
- `scripts/little_loops/loops/oracles/code-run-gate.yaml:247,325` — reads `test_cmd`/`lint_cmd`
  from a pre-built `commands.json`, a related-but-distinct resolution point that feeds some of the
  harness loops upstream; already covered by this issue's permanent out-of-scope note but the
  read sites themselves were not previously anchored. [Agent 1 finding]

### Tests

- **Per-site subprocess resolution tests**, driven through **`bash -c`**
  (`subprocess.run(["bash", "-c", body])`, matching `runners.py:297` — under `dash`,
  `set -o pipefail` is unavailable and `rc=$?` becomes `tee`'s status, so an `sh`-driven test
  reports a passing gate for a failing suite). *Scope note:* only three of the five sites actually
  carry `set -o pipefail` + a `tee` pipe — `fix-quality-and-tests`, `harness-multi-item`, and
  `evaluation-quality`. `harness-single-shot` and `harness-plan-research-implement-report` are bare
  `eval "$CMD" 2>&1` with no pipe at all. Use `bash -c` uniformly anyway (one harness, matches the
  runner), but do not infer from this rule that those two are pipefail-dependent — they are not,
  and a conversion must not introduce a pipe to make them so. Assert three cases each: present-and-set,
  present-and-null (opts out, not literal `"None"`), and absent (falls back to `ll-config get`'s
  own `ProjectConfig` default). Closest template:
  `TestRlCodingAgentObserveTestCmdResolution` (`test_builtin_loops.py:10747-10799`) — extract the
  `action` string, substitute `${context.run_dir}`, run against a scratch `.ll/ll-config.json`.
  **No context-first fourth case applies at any site here** — none of the five declares
  `context.test_cmd`. [Agent 3 finding]
- **`evaluation-quality` skip markers must be asserted on captured stdout, not file contents.**
  `score` reads `${captured.code_results.output}`; a test that opens `eval-test-results.txt`
  passes against the broken `>`-redirect shape (*CAPTURE CORRECTION*).
- **Parametrize the three `harness-*.yaml` `check_concrete` sites as one test class** rather than
  triplicating one subprocess test, following
  `test_bug3269_test_cmd_resolution_gate.py`'s own `pytest.mark.parametrize`-over-file-list
  pattern. They have zero existing coverage of their shell body today. [Agent 3 finding]
- **Pin `evaluate_code`'s exit code at 0** across all four combinations of (`test_cmd` set /
  present-null) × (suite passes / fails) — per *EXIT-CODE CORRECTION*. Today this holds only
  because the action's last statement carries `|| true`; steps 4 and 5 rewrite that statement, and
  a non-zero exit at this state produces a `no` verdict (`evaluate_exit_code`,
  `fsm/executor.py:2608-2610`) on a state whose only edge is `next: score`. Same `bash -c`
  subprocess harness as the resolution tests, asserting `returncode == 0`.
- **Pin the three `harness-*` scaffold comments** with a structural guard, so the one AC that
  protects against the anti-pattern propagating has a verifier like every other row:
  parametrized over the three files, assert `"falls back to 'pytest'" not in text` **and** that
  the `check_concrete` comment block mentions `ll-config get`. Without this, the comment rewrite
  is the only load-bearing change in the issue with nothing holding it in place.
- **Pin the hardcoded-`ruff` removal** with a structural guard mirroring
  `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path` — assert
  `"ruff check scripts/" not in action` post-conversion. `evaluation-quality.yaml`'s
  `evaluate_code` has zero resolution-level coverage today; no test matches
  `code_results`/`eval-test-results`. [Agent 3 finding]
- **BUG-3269's mirror-drift gate**, with `_PENDING_CONVERSION` shrinking by one entry per
  converted file — nine down to four. `test_pending_conversion_sites_still_exist` (`:148-156`)
  asserts every remaining listed filename exists on disk, so an entry cannot be removed without
  the conversion actually landing. Deleting the constant is **ENH-3288's** step 6, not this
  issue's.

_Existing coverage, for orientation:_ every current test over these loops is structural only
(state-set membership, `fragment:` field, routing-edge shape via `test_builtin_loops.py`'s
per-loop classes — `TestEvaluationQualityLoop` L884). None will break from the conversion (they
check supersets, not exact shell content); none gives resolution-level coverage either. Each site
needs a new subprocess-level test. [Agent 3 finding]

### Documentation

- `docs/guides/LOOPS_REFERENCE.md:979,1305,1327` — the `project.test_cmd`/`lint_cmd` rows;
  re-verify against final behavior
- `docs/guides/EVALUATION_GUIDE.md:393` — prose reads *"runs your configured `test_cmd` plus
  `ruff`"*, describing exactly the hardcoded `ruff check scripts/` step 5 converts to
  `ll-config get project.lint_cmd`; update to describe the configured `lint_cmd` instead.
  [Agent 2 finding, confirmed]
- In-YAML comments inside three already-listed primary files — `harness-single-shot.yaml:57-60`,
  `harness-multi-item.yaml:88`, `harness-plan-research-implement-report.yaml:120` — currently
  read "Reads test_cmd from .ll/ll-config.json; falls back to 'pytest' if absent" and describe
  the exact fallback being removed. **Load-bearing, not cosmetic**: these are `# EXAMPLE:`
  scaffolds users clone, so the comments propagate the inline-parse anti-pattern into new loops.
  Update alongside each state's action body. [Agent 2 finding]

_Deferred to ENH-3288 (they describe the exemption list or the structural loops):_
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:569`'s "temporary exemption pending ENH-3277's
conversion pass" sentence (still true while `_PENDING_CONVERSION` survives this issue — it
becomes false only when ENH-3288 deletes the constant); `LOOPS_REFERENCE.md:1347`
(`test-coverage-improvement`'s `test_cmd` row); `scripts/little_loops/loops/README.md:33` and
`skills/audit-loop-run/SKILL.md:~277` (both `auto-refine-and-implement`, permanently exempt —
sanity check only, no edit expected under Option A).


### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- The `_PENDING_CONVERSION` mirror-drift gate (referenced throughout this issue) lives in
  `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:55-65` — a nine-entry `set` literal
  matching this issue's nine target files exactly (the `auto-refine-and-implement.yaml` entry
  covers both its `:433-436` and `:679-680` references as one file-level exemption).
  `PROJECT_COMMAND_KEYS = ("test_cmd", "lint_cmd", "type_cmd", "format_cmd", "build_cmd",
  "run_cmd")` and `_PERMANENT_EXEMPTIONS = {"oracles/code-run-gate.yaml"}` are unioned into
  `_EXEMPT` in the same module. Two guard tests key directly off `_PENDING_CONVERSION`:
  `test_pending_conversion_sites_still_exist` (:148-156) asserts every listed filename still
  exists on disk — so removing a site's exemption string without also finishing its conversion
  fails this test — and `test_general_task_and_rl_coding_agent_are_not_exempt` guards against
  re-adding the three already-converted sites to either exemption set. A third assertion,
  `test_context_references_are_declared` (:120-145), checks every `${context.test_cmd}` /
  `${context.lint_cmd}` interpolation in every loop YAML against that loop's declared
  `context:`/`parameters:` block — it has no exemption list, already passes today, and is the
  mechanism that fails a naive context-first paste onto any of the eight sites that don't
  declare the key (per BUG-3269 §1f's `InterpolationError` hazard cited in this issue's
  Proposed Solution).
- Anchor correction: `evaluation-quality.yaml`'s hardcoded `ruff check scripts/` is at line 63,
  not 64 as cited above.
- Anchor correction: `rn-refine.yaml`'s inline `python3 -c` resolution block spans lines
  986-994, not 988-994. Its existing `[ -z "$TEST_CMD" ]` skip guard (`exit 0`, routing to
  `next: finalize` rather than any `on_no` edge — this state has no yes/no gate at all) is at
  lines 995-997, itself wrapped by an outer `if [ "${context.stepwise:default=0}" = "0" ]; then
  exit 0; fi` guard.
- `auto-refine-and-implement.yaml`'s target block sits inside a `python3 << 'PYEOF'` heredoc in
  the `verify` state (state starts line 370, heredoc starts line 388); the `test_cmd`/`lint_cmd`
  extraction and `if not test_cmd: emit('skipped')` branch is at lines 430-437 and already
  implements the present-null-skips semantics — only the resolution mechanism (not the skip
  logic) needs to change.
- Two existing test shapes in `scripts/tests/test_builtin_loops.py` cover the two concerns the
  Tests subsection above calls for, without an execution-based FSM run existing for either:
  `TestIncrementalRefactorLoop.test_revert_has_exactly_one_inbound_edge` (:11999-12006) asserts
  a destructive state's inbound edges by static structural check over the parsed YAML
  `states` dict (`for key in ("on_yes","on_no","on_error","on_cannot_judge","next")`), the
  shape available for asserting a state's routing target (e.g. that nothing but
  `verify_tests.on_no` reaches a revert/commit state). `TestRlCodingAgentObserveTestCmdResolution`
  (:10742-10789) executes the extracted shell prefix via `subprocess.run(["bash", "-c", ...])`
  against a scratch `.ll/ll-config.json`, the shape available for asserting a *resolved value*
  (e.g. that `test_cmd: null` resolves to an empty `CMD`, not a guessed default).

## Acceptance Criteria

_Every row is verified by a named test or a named command. Structural-state, exit-collapse, and
gate-teardown criteria live in **ENH-3288**._

**Conversions (6)**

- [ ] `fix-quality-and-tests.yaml` `check-tests` reads `ll-config get project.test_cmd`; the
      three-way `python3 -c` body at `:58-78` is deleted, not generalized
- [ ] `harness-single-shot.yaml:66`, `harness-multi-item.yaml:95`,
      `harness-plan-research-implement-report.yaml:126` converted, **and** their `# EXAMPLE:`
      scaffold comments (`:57-60`, `:88`, `:120`) rewritten to stop teaching the inline parse
- [ ] `evaluation-quality.yaml:58` (`test_cmd`) converted, with a no-test-signal marker emitted
      **on stdout** (`| tee`, never a bare `>`)
- [ ] `evaluation-quality.yaml:63`'s hardcoded `ruff check scripts/` → `ll-config get
      project.lint_cmd`, with a no-lint-signal marker on stdout
- [ ] `evaluate_code` still exits **0 unconditionally** — all four combinations of (`test_cmd`
      set / present-null) × (suite passes / fails). Today this is guaranteed only by the trailing
      `|| true` that steps 4–5 rewrite (*EXIT-CODE CORRECTION*)
- [ ] All five sites use the **config-first bare** shape — no `${context.test_cmd}` reference
      anywhere (none of the five declares the key; an undeclared reference is an
      `InterpolationError` and fails gate assertion (ii))
- [ ] No `|| { ...; exit N; }` guard added at any site (BUG-3269 §1f)

**Gate**

- [ ] `_PENDING_CONVERSION` shrinks from nine entries to exactly four
      (`dead-code-cleanup.yaml`, `test-coverage-improvement.yaml`, `rn-refine.yaml`,
      `auto-refine-and-implement.yaml`)
- [ ] The constant, `test_pending_conversion_sites_still_exist`, and `_EXEMPT` all still exist —
      deleting them is ENH-3288's step 6
- [ ] `_PERMANENT_EXEMPTIONS` is **unchanged** at one entry — the Option A move is ENH-3288's
      step 5
- [ ] `test_no_inline_project_command_config_read`, `test_context_references_are_declared`, and
      `test_general_task_and_rl_coding_agent_are_not_exempt` all remain and pass
- [ ] All three "ENH-3277 empties/deletes this set" claims in
      `test_bug3269_test_cmd_resolution_gate.py` reassigned to **ENH-3288** — module docstring
      (`:23-27`), `_PENDING_CONVERSION` comment (`:52-55`), and
      `test_pending_conversion_sites_still_exist`'s assertion message (`:155`). Verified by
      `grep -c 'ENH-3277' scripts/tests/test_bug3269_test_cmd_resolution_gate.py` returning only
      the Option-A annotation hits below
- [ ] The `rn-refine.yaml` and `auto-refine-and-implement.yaml` entries in `_PENDING_CONVERSION`
      each carry an inline comment marking them permanently exempt per Option A and pointing at
      ENH-3288 step 5 for the move

**Tests** (each is new; none exists today)

- [ ] Per-site subprocess resolution tests driven through `bash -c`, all three config cases
      (set / present-null / absent); the three `harness-*` sites parametrized as one class
- [ ] `evaluation-quality` skip markers asserted on the state's **captured stdout**, not on
      `eval-test-results.txt` / `eval-lint-results.txt`
- [ ] Structural guard asserting `"ruff check scripts/" not in action` at
      `evaluation-quality.evaluate_code`
- [ ] Structural guard over the three `harness-*.yaml` asserting `"falls back to 'pytest'"` is
      absent and the `check_concrete` comment names `ll-config get` — the verifier for the Docs
      row below
- [ ] `evaluate_code` exit-0 test, four combinations (see *Conversions*)

**Docs**

- [ ] `EVALUATION_GUIDE.md:393` describes the configured `lint_cmd`, not `ruff`
- [ ] The three `harness-*` in-YAML scaffold comments match the **pinned replacement text** under
      *Proposed Solution* — including the clone-hazard note ("if your `on_yes` is irreversible,
      add an explicit `[ -z "$CMD" ]` branch"). Verified by the structural guard above, not by
      inspection
- [ ] `LOOPS_REFERENCE.md:979,1305,1327` re-verified against final behavior

**Exit gates**

- [ ] `ll-loop validate` passes for all five touched loops
- [ ] The scoped grep from step 6 returns only the four still-pending / exempt files
- [ ] `python -m pytest scripts/tests/` exits 0

## Implementation Steps

1. **BUG-3269 has landed** (status: done) and `_PENDING_CONVERSION` exists in
   `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:55-65` with its nine entries.
   The `ll-config get` convention, the `HARNESS_OPTIMIZATION_GUIDE.md` write-up
   (`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:516-569`), and both mirror-drift gate assertions
   were BUG-3269's deliverables, not this one's.
2. **Pick a §2b row for every site before writing any shell.** The table under *Proposed
   Solution* is a hard prerequisite, not advisory. Four of the five sites here are pass-on-empty;
   `evaluation-quality` is the one that needs an explicit skip.

2b. **Write the subprocess resolution tests before converting, not alongside.** Both of this
   issue's named outcome risks reduce to "no execution-level coverage exists for any of the five
   sites today" — which is exactly why `outcome_confidence` (63) sits below this project's
   `outcome_threshold` (65). Written first, each test is a red-then-green check on that site's §2b
   row; written alongside, it is a description of whatever shell was just typed and clears
   nothing. Order: the parametrized `harness-*` class, then `fix-quality-and-tests`, then
   `evaluation-quality` (both branches, plus the exit-0 test), then steps 3–5 turn them green.
3. **Convert the four pass-on-empty sites first** — `fix-quality-and-tests.yaml`
   (delete its three-way python body outright), `harness-single-shot.yaml`,
   `harness-plan-research-implement-report.yaml`, `harness-multi-item.yaml`. These are
   drop-ins or route to a further gate. Config-first bare for all four — none declares a
   `context.test_cmd` key. Rewrite the three `harness-*` template comments (`:57-60`, `:88`,
   `:120`) in the same edit — they are copy-me scaffolds teaching the anti-pattern, not
   incidental docs. Remove each file's `_PENDING_CONVERSION` entry as it lands.
4. **Convert `evaluation-quality.yaml:58`** (`test_cmd`), the one explicit-skip site here. Both
   branches of `evaluate_code` emit their own "no signal" marker **on stdout** (`| tee`, never a
   bare `>`), because `score` reads `${captured.code_results.output}` and not the files — see
   *CAPTURE CORRECTION*. Do **not** reroute; `evaluate_code` has no `on_yes`/`on_no` edges.
5. **Convert `evaluation-quality.yaml:63`'s hardcoded `ruff check scripts/`** to
   `ll-config get project.lint_cmd` — the same defect, pre-inlined. Keep the action exiting 0
   unconditionally (*EXIT-CODE CORRECTION*). Then remove `evaluation-quality.yaml` from
   `_PENDING_CONVERSION`, bringing it to four entries.

5b. **Correct the gate file's prose.** Reassign all three "ENH-3277 empties/deletes this set"
   claims to ENH-3288 (module docstring `:23-27`, `_PENDING_CONVERSION` comment `:52-55`,
   `test_pending_conversion_sites_still_exist`'s assertion message `:155`) and annotate the two
   Option-A entries in place — see *The gate file's own prose is falsified by this issue*.
   Prose-only; no assertion logic changes and no test breaks.
6. **Verify.** After each file: `ll-loop validate`, a scoped `grep` for the old
   `.get('test_cmd'` / `.get('lint_cmd'` pattern, and the gate with one fewer entry.

   The grep must exclude the files that legitimately still match — the two permanently exempt
   under Option A, `oracles/code-run-gate.yaml`, and (until ENH-3288 lands) the two structural
   loops:

   **The grep must cover the bracket form too.** `_INLINE_ACCESS_RE` alternates on
   `['project']['test_cmd']` as well as `.get('project'…).get('test_cmd'`, and
   `fix-quality-and-tests.yaml:69` uses **the bracket form** (`'test_cmd' in cfg['project']`)
   inside the three-way body step 3 deletes. A `.get(`-only grep therefore reports clean against a
   *partial* deletion that leaves that line behind, while the gate test still fails. Include both:

   ```bash
   grep -rnE "\.get\('(test_cmd|lint_cmd)'|\['project'\]\['(test_cmd|lint_cmd)'\]" \
     scripts/little_loops/loops/ --include='*.yaml' \
     | grep -v -e 'rn-refine.yaml' -e 'auto-refine-and-implement.yaml' \
               -e 'oracles/code-run-gate.yaml' \
               -e 'dead-code-cleanup.yaml' -e 'test-coverage-improvement.yaml'
   ```

   Expected output at the end of this issue: empty. (ENH-3288 drops the last two exclusions and
   expects empty again.)

   **`test_no_inline_project_command_config_read` is authoritative, not this grep** — the grep is
   a fast per-file convenience during step 3/4/5 and matches a narrower pattern than the gate.
   A clean grep is never sufficient evidence that a file converted; the gate passing is.

   At the end: `python -m pytest scripts/tests/` exits 0.

7. **Hand off to ENH-3288**, which converts the two structural loops, executes the Option A
   exemption move, empties and deletes `_PENDING_CONVERSION`, widens `_INLINE_ACCESS_RE`, and
   corrects `HARNESS_OPTIMIZATION_GUIDE.md:569`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation. Structural-loop touchpoints moved to **ENH-3288**._

- Update `docs/guides/EVALUATION_GUIDE.md:393` — replace "runs your configured `test_cmd` plus
  `ruff`" once step 5 converts `evaluation-quality.yaml:63`'s hardcoded `ruff check scripts/` to
  `ll-config get project.lint_cmd`
- Update the stale fallback-description comments inside `harness-single-shot.yaml:57-60`,
  `harness-multi-item.yaml:88`, `harness-plan-research-implement-report.yaml:120` alongside each
  state's action body — they currently describe the guessed-`'pytest'` fallback being removed.
  **Load-bearing, not cosmetic**: these are `# EXAMPLE:` scaffolds users clone, so the comments
  propagate the inline-parse anti-pattern into new loops
- Write new subprocess-level resolution tests per site (no existing test exercises shell content
  at the value-resolution level for any of the converted sites) — model on
  `TestRlCodingAgentObserveTestCmdResolution` (`test_builtin_loops.py:10747-10799`); parametrize
  the three `harness-*.yaml` `check_concrete` sites as one test class rather than tripling it,
  and drive them through `bash -c`, not `sh`
- Model the five conversions on the three **already-converted** precedent sites
  (`rl-coding-agent.yaml:62-63`, `general-task.yaml:57`, `incremental-refactor.yaml:62-63`), not
  on new shapes — specifically the **config-first bare** variant, since none of the five here
  declares `context.test_cmd`

**Rollback seam:** independent per-file edits. If one conversion misbehaves in a consuming
project, revert that file and re-add its `_PENDING_CONVERSION` entry — the constant still exists
throughout this issue, so the seam is intact until ENH-3288 deletes it.

## Scope Boundaries

### SPLIT EXECUTED (2026-08-21) — ENH-3288 carries the structural half

This issue originally covered all seven convertible files plus the gate teardown. It was split at
the risk boundary: the six conversions here are pure find-and-replace, while
`dead-code-cleanup` and `test-coverage-improvement` gate an `on_yes: commit` edge and need a
`fragment: harness_exit` switch, an exit-code normalization, four new states, and
`initial:`/`max_steps:` edits. Those, plus the `_PENDING_CONVERSION` teardown, are **ENH-3288**
(`blocked_by: [ENH-3277]`).

The split puts exactly **one** handoff of the shared `_PENDING_CONVERSION` set literal between the
two issues — this one shrinks it nine → four, ENH-3288 takes it four → zero and deletes it — and
splits the cross-cutting corrections cleanly: *CAPTURE CORRECTION* stays here (it is
`evaluation-quality`-only); MECHANISM / EXIT-CODE COLLISION / TERMINAL-ACTION / *Dead site* /
*Terminality* / *Step budget* all moved wholesale. Nothing is duplicated across the two files.

**In scope:** the five mechanical inline resolution sites listed under *Files to Modify* — five
files, five inline reads, all converted — plus `evaluation-quality.yaml:63`'s hardcoded lint
command as the sixth conversion, shrinking `_PENDING_CONVERSION` from nine entries to four, and
the doc rows describing those sites.

**Out of scope — belongs to ENH-3288:** `dead-code-cleanup.yaml` and
`test-coverage-improvement.yaml` in full (both `verify_tests` states, the dead `measure` block,
the `harness_exit` switches, the exit collapse, `check_preconditions`, `revert_unverifiable`,
both `unverifiable` states, `initial:`/`max_steps:`); moving `rn-refine.yaml` and
`auto-refine-and-implement.yaml` into `_PERMANENT_EXEMPTIONS`; emptying and deleting
`_PENDING_CONVERSION`; widening `_INLINE_ACCESS_RE`; and
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:569`.

**Out of scope — belongs to BUG-3269:** the three defective sites
(`general-task.yaml:37`, `rl-coding-agent.yaml:60,68`); `general-task`'s `SKIP` sentinel,
§3b reader-side normalization, and §3c resolve-once handoff; the `cli/config.py` stderr
warning; the mirror-drift gate itself (both assertions); the
`HARNESS_OPTIMIZATION_GUIDE.md` convention write-up; `config-schema.json` and
`CONFIGURATION.md`'s absent-vs-null note.

**Out of scope — permanently:** `oracles/code-run-gate.yaml`. It resolves from
`${context.project_root}` rather than `Path.cwd()`, resolves **alias pairs**
(`typecheck_cmd|type_cmd`, `start_cmd|run_cmd`) that `ll-config get` has no support for, and
its contract is deliberately *absent ≡ null ≡ skip, never guess* — converting it would make a
project that never configured `type_cmd` start running `mypy`. Full rationale in BUG-3269
§1d. It stays a documented gate exemption.

**Out of scope — permanently (the Option A decision):** `rn-refine.yaml` and
`auto-refine-and-implement.yaml:433-436`. Same §1d rationale — an absent≡skip contract that
`ll-config get` cannot express. Both keep their inline parse; **the constant move that records
this is ENH-3288's step 5**, not this issue's. Accepted cost: both continue to bypass
`.ll/ll.local.md`.

**Out of scope — split separately:** generalizing BUG-3276's this-repo-hardcode gate over all
built-in loops → **ENH-3281** (was step 6b). Converting `evaluation-quality.yaml:63`'s
`ruff check scripts/` stays here as step 5; gating the *class* does not.

**Out of scope — split separately:** `incremental-refactor.yaml:12,33` → BUG-3276 (landed).

**Explicitly not a call site:** `auto-refine-and-implement.yaml:679-680` reads
`cfg.project.test_cmd` / `cfg.project.lint_cmd` off a real `BRConfig` instance inside an
embedded Python block. It already resolves through `ProjectConfig` **and** already honors
`.ll/ll.local.md`. Do not "convert" it.

**No new production code.** Settled by Option A — this issue touches loop YAMLs, tests, and docs
only. `ll-config get`'s resolution is unchanged and no CLI surface is added. In particular
`cli/config.py` is **not** modified: `--raw` belonged to the rejected Option C.


## Program Design

### Signatures

- `main_config() -> int` — **existing**, unchanged (`cli/config.py:54`); invoked from shell as
  `ll-config get project.test_cmd`. The single resolution path every converted site delegates
  to. Takes no parameters — the key arrives as `args.key` from `parser.parse_args()`.
- `resolve_variable(var_path: str) -> str` — **existing**, unchanged (`config/core.py:1044`);
  returns `None` for a present-and-null key, which is the load-bearing opt-out signal each
  site's `[ -z "$CMD" ]` branch tests for.
- `ProjectConfig.from_dict(data: dict) -> ProjectConfig` — **existing**, unchanged
  (`config/core.py:208`); its field defaults (`:188-195`) become the only authority for the
  absent-key fallback, replacing nine per-call-site `'pytest'` literals. Its
  `data.get("test_cmd", "pytest")` (`:214`) is precisely where absent and defaulted collapse.
  That lossiness is why `rn-refine` and `auto-refine` are exempted rather than converted.

**No new signatures.** Option A adds no production surface. `BRConfig._raw_config`
(`config/core.py:262`) and a `--raw` flag on `main_config` appeared here only as Option C's
design; both are struck. `cli/config.py` is untouched by this issue.

### Call Path

- each converted state → `ll-config get project.<key>` → `main_config` → `BRConfig(Path.cwd())`
  → `_load_config` (deep-merges `.ll/ll.local.md`, `:265-280`) → `ProjectConfig.from_dict`
  → `resolve_variable` → `print` only when non-`None`.
- `[ -z "$CMD" ]` → that site's §2b branch: **pass-on-empty at four sites**
  (`fix-quality-and-tests` plus the three `harness-*`), or an **explicit skip** at
  `evaluation-quality` (a "no signal" marker on stdout — it has no gate to reroute).
- non-empty `CMD` → `eval "$CMD"` → the site's existing gate, unchanged — a
  `fragment: shell_exit` gate at four of the five read sites, and a plain `next: score` with a
  downstream `capture:` consumer at `evaluation-quality.evaluate_code` (see *Two distinct
  hazards* under *Proposed Solution*).

**Precondition — cwd must be the project root.** `main_config` constructs
`BRConfig(Path.cwd())` with no upward walk, so a state invoked from a subdirectory loses the
opt-out. Safe for every converted site today: FSM shell actions run at
`FSMExecutor.working_dir` (`fsm/executor.py:2482`), the project or worktree root. Not a
regression — the inline snippets open the same relative path — but not fixed here either.

## Impact

- **Behavior change under `test_cmd: null`**: these five sites stop gating on a guessed `pytest`.
  For the four pass-on-empty sites that is a clean opt-out; for `evaluation-quality` it means
  handing `score` an empty capture unless the §2b marker is applied.
- **`.ll/ll.local.md` overrides of `test_cmd`/`lint_cmd` start taking effect** inside these
  loops (they never did).
- **`evaluation-quality.yaml:63` lint scope widens**: `ruff check scripts/` →
  `ruff check .` in a project that never set `lint_cmd`. Already non-gating (`|| true`), so
  this affects the captured artifact, not control flow. No change in this repo, which sets
  `lint_cmd`.
- **The three `harness-*` scaffolds stop teaching the anti-pattern.** Their `# EXAMPLE:` comments
  are what users clone when authoring new loops, so this is the change that stops a fourteenth
  inline read from being written in the first place.
- **Risk accepted**: these gates join the three from BUG-3269 in depending on a single
  fail-open binary (§1e there). Unlike `general-task`, they have no §3c equivalent mapping
  the malformed-config door to a sentinel — each falls back to its §2b row. At the four
  pass-on-empty sites a missing `ll-config` yields an empty `CMD` and the gate passes; three of
  those four route to a further LLM gate, and the fourth (`fix-quality-and-tests`) routes to
  `done`.
- **`_PENDING_CONVERSION` shrinks but survives.** The gate keeps blocking new inline reads
  throughout, and the four remaining entries stay honest via
  `test_pending_conversion_sites_still_exist`. The list is not debt this issue closes — that is
  ENH-3288.
- **Rollback seam**: independent per-file edits; revert one file and re-add its
  `_PENDING_CONVERSION` entry. Nothing shared to unwind — no new states, no fragment changes, no
  control-flow edits anywhere in this issue. **The one way to violate that promise accidentally**
  is to let `evaluate_code` start exiting non-zero on a failing suite while restructuring its two
  branches (*EXIT-CODE CORRECTION*); the exit-0 test exists to catch it.

## Related Key Documentation

- **ENH-3288** — the structural half split from this issue; owns both `verify_tests` redesigns,
  the *Dead site* decision, the MECHANISM / EXIT-CODE COLLISION / TERMINAL-ACTION corrections,
  and the `_PENDING_CONVERSION` teardown. `blocked_by: [ENH-3277]`
- **BUG-3269** — the P0 this splits from; all baseline design analysis lives there (§1, §1b,
  §1d, §1f, §2, §2b)
- BUG-3276 — `incremental-refactor.yaml`'s hardcoded `test_cmd`, split out separately
- ENH-3281 — the sibling hardcode defect class (generalizing the this-repo-hardcode gate)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the `ll-config get` convention, written up by
  BUG-3269


## Status

**Open** | Created: 2026-08-21 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-21. Re-run against the trimmed six-conversion scope
(this issue's own split) — supersedes the prior pre-split notes below._

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE (below the 65 `outcome_threshold`)

Readiness Criterion 4 (issue well-specified) is capped at 10/20 by `missing_behavior_parity`
(`format-check`: no `### Behavior Parity` subsection describing what `.ll/ll-config.json`'s
inline parse is replaced by) — advisory only, does not gate the PROCEED verdict. Outcome
Criterion C (ambiguity) is capped at 10/25 by `unapplied_decision` — `format-check` flags ~19
terms from the rejected Option B/C prose (`ll-config get`, `pytest`, `_raw_config`,
`RECOVERY_NEEDED`, `oracles/code-run-gate.yaml`, etc.) as still present in directive sections.
Direct read confirms these are all inside explicitly `REJECTED` option blocks or the
deliberately-retained "documented fallback" rationale for Option C, not stray unresolved
prose — a likely false positive against the same pattern the prior pre-split run already noted,
but the cap is mechanical and doesn't distinguish structured-rejected-option text from genuine
drift.

### Pre-implementation review addendum — 2026-08-21

_Manual design review against the tree; six changes applied to this issue. Scores below are from
the prior `/ll:confidence-check` run and are **stale** — re-run before treating the 63 as current._

1. **`missing_behavior_parity` was a true positive, now closed** — a `### Behavior Parity` table
   was added under *Proposed Solution*.
2. **Outcome Criterion C's `unapplied_decision` re-confirmed as a false positive** on a second
   direct read: every flagged term sits inside a labeled `REJECTED` block or Option C's
   deliberately-retained fallback rationale.
3. **New in-scope work found:** the gate file's own docstring, set comment, and assertion message
   all assert that *this* issue empties `_PENDING_CONVERSION` — false after the split. Added to
   *Files to Modify*, step 5b, and the Gate ACs.
4. **New hazard found:** `evaluate_code`'s exit code is 0 today only because its last statement
   carries `|| true`, and steps 4–5 rewrite that statement (*EXIT-CODE CORRECTION*).
5. **Step 6's grep was weaker than the gate it stood in for** — it missed the bracket access form
   that `fix-quality-and-tests.yaml:69` actually uses. Widened, and the gate declared authoritative.
6. **Two unverified ACs given verifiers** — the `harness-*` comment rewrite (now pinned to
   verbatim replacement text plus a structural guard) and the exit-0 invariant. The AC preamble's
   "every row is verified by a named test or command" now holds.

Anchors spot-checked and confirmed accurate: all six conversion sites, the "none of the five
declares `context.test_cmd`" claim, and the `fix-quality-and-tests` identical-routing proof.
One anchor corrected: `test-coverage-improvement.yaml`'s second read is at `:152` within a
`:143-158` state (was cited `:148-158`) — ENH-3288's scope, fixed here since it was quoted.

### Outcome Risk Factors

- No execution-level test coverage exists today for any of the five target read sites — only
  structural checks (state-set membership, edge shape) cover them. A subprocess-level resolution
  test is needed per site (per *Tests*) **before** each conversion — not alongside it — to catch a
  bad `[ -z "$CMD" ]` routing choice. Sequencing pinned as step 2b.
- `format-check`'s `unapplied_decision` gate (19 hits) drives the ambiguity cap above; worth one
  skim of *Proposed Solution* / *Program Design* before starting to confirm no genuinely stale
  rejected-option text survives outside the labeled `REJECTED` blocks.
- `format-check` also flagged `missing_behavior_parity` on `.ll/ll-config.json` and
  `unmarked_superseded_directive` on the issue's own filename (the "Rescoped 2026-08-21" note at
  the top) — both read as false positives on direct inspection (the supersession is already
  explicit in prose), but neither has been re-verified against the checker's exact matching
  rules.

## Session Log
- `/ll:confidence-check` - 2026-08-21T18:59:48 - `de2bc4f7-6272-4f52-a9cb-998af08752f1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T17:52:58 - `f27d8342-f3ba-42ea-95ca-41ad79008fbf.jsonl`
- `/ll:confidence-check` - 2026-08-21T17:18:53 - `03a5de0d-b8b9-470c-a7c9-e3445c858ad8.jsonl`
- `/ll:confidence-check` - 2026-08-21T16:27:41 - `e55ad46d-5b7e-43e8-8452-c0861f23904f.jsonl`
- `/ll:confidence-check` - 2026-08-21T16:05:16 - `31b75f64-db6a-4a60-b5e4-21ce3b3efbc5.jsonl`
- `/ll:decide-issue` - 2026-08-21T15:37:47 - `fd963709-cda9-4223-bed4-b0ecd04d5d50.jsonl`
- `/ll:confidence-check` - 2026-08-21T15:19:04 - `36629249-e029-4d46-add2-34299614a223.jsonl`
- `/ll:confidence-check` - 2026-08-21T14:55:55 - `e03958cc-36c6-4afa-b441-77f5795b84f4.jsonl`
- `/ll:wire-issue` - 2026-08-21T14:53:20 - `3839fe9f-8271-4a8b-8a20-9a93191e33bc.jsonl`
- `/ll:reconcile-issue` - 2026-08-21T14:29:42 - `08bd38ec-d985-4ff9-b92f-3e3223f35d2e.jsonl`
- `/ll:refine-issue` - 2026-08-21T14:00:56 - `6686f401-b52b-45b3-a364-e4c7f0616eb7.jsonl`
- `/ll:refine-issue` - 2026-08-21T14:00:48 - `6686f401-b52b-45b3-a364-e4c7f0616eb7.jsonl`
