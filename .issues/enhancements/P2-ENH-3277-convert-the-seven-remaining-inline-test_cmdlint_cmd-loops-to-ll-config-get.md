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
outcome_confidence: 68
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 15
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
for that specific site. After each file: `ll-loop validate`, the scoped `grep` from step 7 (which
must exclude the two permanently-exempt files), and BUG-3269's gate with one entry removed from
`_PENDING_CONVERSION`.

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

This is the reason for the split, not an afterthought to it. Under `fragment: shell_exit`,
`eval ""` exits **0**, so an empty `CMD` makes the gate silently **pass** against an empty
artifact.

**Two distinct hazards, not one — the sites split by state kind.** Only six of the eleven read
sites sit in a `fragment: shell_exit` state where the false-pass applies:
`fix-quality-and-tests.check-tests`, `dead-code-cleanup.verify_tests`,
`test-coverage-improvement.verify_tests`, and the three `harness-*.check_concrete` states. The
other sites — `evaluation-quality.evaluate_code` (`action_type: shell`, `capture: code_results`,
`next: score`), `test-coverage-improvement.measure` (`action_type: shell`, `next:
extract_percentage`), and `rn-refine`'s full-suite gate (`action_type: shell`, `next: finalize`)
— have **no gate to falsely pass**. Their hazard is different and narrower: an empty `CMD`
produces an empty *artifact* that a downstream scorer or LLM state consumes as if it were a real
test signal. The §2b remedies below are unchanged by this; the rationale is. Do not go looking for
an `on_yes` edge at the three ungated sites — there isn't one.

Per BUG-3269 §2b:

| Site | `on_yes` | Decision |
|---|---|---|
| `fix-quality-and-tests.yaml:58-78` | `done` | pass-on-empty; drop-in — **verified**: its three-way body prints `true` on present-null → `eval "true"` → exit 0 → `done`; post-conversion an empty `CMD` → `eval ""` → exit 0 → `done`. Identical routing. Delete the three-way python body, do not generalize it |
| `harness-single-shot.yaml:61-72` | `check_semantic` | pass-on-empty (LLM gate still runs) |
| `harness-plan-research-implement-report.yaml:121-132` | `check_semantic` | pass-on-empty |
| `harness-multi-item.yaml:90-100` | `check_mcp` | pass-on-empty |
| `evaluation-quality.yaml:58` (`test_cmd`) | **none — `next: score`, ungated** | **explicit skip required.** Emit a "no test signal" marker **on stdout** (see *CAPTURE CORRECTION* below) — **not** by rerouting; `evaluate_code` has no `on_yes`/`on_no` edges |
| `evaluation-quality.yaml:63` (`lint_cmd`) | **none — same state** | **explicit skip required.** Same hazard, same state, separate branch: post-conversion an empty `LINT_CMD` makes `eval "" \| tee eval-lint-results.txt` write an empty file *and* contribute nothing to stdout, which `score` reads as *clean lint*. Emit a "no lint signal" marker on stdout instead. The existing `\|\| true` makes this non-gating, so the risk is a falsified artifact, not a false pass |
| `dead-code-cleanup.yaml:71-81`, `test-coverage-improvement.yaml:45` and `:148-158` | `commit` / ungated | **SPLIT OUT — ENH-3288.** All three need explicit-skip handling on an `on_yes: commit` edge, which requires a `harness_exit` fragment switch and new states. Not this issue's work; do not convert them here |
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

### Precedence — config-first bare for seven of the eight live converted sites

Only three loops declare a `context.test_cmd` key at all (`general-task.yaml:23`,
`test-coverage-improvement.yaml:23`, `rl-coding-agent.yaml:17`). Of this issue's targets, only
`test-coverage-improvement.yaml` does — and today that declaration reaches nothing but dead code
(*Dead site* above), so context-first is legitimate at exactly one site: `verify_tests`, under the
now-pinned decision (a). **Do not paste the context-first shape into the
others** — an undeclared `${context.test_cmd}` raises `InterpolationError: Path 'test_cmd' not
found in context` at interpolation time, turning a mechanical conversion into a hard loop
breakage. BUG-3269's gate assertion (ii) now catches this statically.

Config-first bare — seven sites: `fix-quality-and-tests`, the three `harness-*`,
`evaluation-quality`'s `test_cmd` **and** `lint_cmd`, and `dead-code-cleanup`:

```bash
CMD=$(ll-config get project.test_cmd)
```

**Do NOT add a `|| { ...; exit N; }` guard** — BUG-3269 §1f: at `evaluate: exit_code` states a
non-zero exit routes to `on_no`, which is `revert_and_scan` for `dead-code-cleanup`.

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
    issue's one target site that already declares `context.test_cmd` (line 23); its `measure`
    state (context-first, lines 31-59) already uses the context-check half of this shape for one
    branch, without the `RC` check on the `ll-config get` fallback. **Correction (2026-08-21):
    that `measure` branch is dead — the resolved `CMD` is never used; only `$COV_CMD` is eval'd
    (`:62`). It is not a model to copy and not a site to convert. See *Dead site* under
    *Proposed Solution*.**
- Skip-on-empty already has three coexisting variants in the codebase, disagreeing on mechanism
  — relevant to picking a shape for the three explicit-skip sites this issue names:
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
    the fragment switch silently routes `exit 3` to `on_error`. See *MECHANISM CORRECTION* under
    *Pinning the two explicit-skip gate edges*.
  - **Entry precondition (added 2026-08-21, post-BUG-3276)**: `incremental-refactor.yaml`
    `check_preconditions:20-86` also *refuses to start* when `test_cmd` is unresolvable,
    unrunnable (exit 127), or already red, writing `precondition-failure.txt` and `exit 1` →
    `on_no: failed`. A fourth variant, and the recommended one for `dead-code-cleanup`.
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
- `scripts/little_loops/loops/dead-code-cleanup.yaml:76` — plus three edits outside the read
  itself: **`:7` `initial: scan` → `initial: check_preconditions`** (without it the new entry gate
  is never entered — see constraint 4 under *DECIDED — `dead-code-cleanup` gets a
  `check_preconditions` entry gate*), **`:108` `max_steps: 15` → `18`** (*Step budget*), and the
  two new states `revert_unverifiable` / `unverifiable` (*Terminality*)
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:126` — and its
  template comment at `:120` (load-bearing; see *The three `harness-*` sites are user-facing
  templates*)
- `scripts/little_loops/loops/harness-multi-item.yaml:95` — and its template comment at `:88`
- `scripts/little_loops/loops/harness-single-shot.yaml:66` — and its template comment at `:57-60`
- `scripts/little_loops/loops/test-coverage-improvement.yaml:45,152` — `:45` (with its enclosing
  `CMD` block, `:37-48`) is **deleted, not converted**; `:152` is the only live read. The
  `test_cmd` declaration at `:23` **stays** and becomes functional per the pinned decision (a)
  under *Dead site*
- `scripts/little_loops/loops/rn-refine.yaml:991`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:433-436` — **not** `:679-680`,
  which reads `cfg.project.test_cmd` off a real `BRConfig` and is already correct and already
  `ll.local.md`-aware
- The `_PENDING_CONVERSION` constant landed by BUG-3269 — emptied, then deleted

Out of scope: `oracles/code-run-gate.yaml` (permanent exemption, BUG-3269 §1d);
`incremental-refactor.yaml` (BUG-3276).

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

- Per-site regression tests for the three `[ -z "$CMD" ]` branches — in particular
  `dead-code-cleanup.yaml` must **not** reach `commit` under `test_cmd: null`
- BUG-3269's mirror-drift gate, with `_PENDING_CONVERSION` shrinking per file and finally
  removed

_Three test requirements added 2026-08-21 by the corrections above — each pins a hazard that
every existing structural assertion passes straight through:_

- **Exit-3 collision case at both `verify_tests` states.** With `test_cmd` set to a command that
  exits 3 (e.g. `sh -c 'exit 3'`), the state must exit **1**, not 3 — proving the non-zero
  collapse is present and that pytest's own internal-error code cannot reach
  `on_cannot_judge` (*EXIT-CODE COLLISION*). Also assert `[ -z "$CMD" ]` still exits 3.
- **`evaluation-quality` skip markers must be asserted on captured stdout, not file contents.**
  `score` reads `${captured.code_results.output}`; a test that opens
  `eval-test-results.txt` passes against the broken `>`-redirect shape (*CAPTURE CORRECTION*).
- **Dedicated assertions for the four new/changed states** — `unverifiable` in both loops plus
  `dead-code-cleanup`'s `check_preconditions` and `revert_unverifiable` — since
  `test_required_states_exist` at L11688 / L11722 are subset checks. Assert each state's
  `terminal`/`failure` flags, its absence of a `next:`, and its inbound edge (the
  `TestIncrementalRefactorLoop.test_revert_has_exactly_one_inbound_edge` shape, `:11999-12006`).
- **Assert that neither `unverifiable` state carries an action**, and that
  `revert_unverifiable` is non-terminal with `next: unverifiable`. This is the executable form of
  the *TERMINAL-ACTION CORRECTION*: an `action` on a terminal state is silently dead
  (`fsm/executor.py:601-636`), so nothing else in the suite would catch someone "simplifying" the
  two states back into one.
- **Assert `dead-code-cleanup`'s `initial == "check_preconditions"` and `max_steps == 18`.**
  Both are one-line scalars that a future edit can revert without breaking any state-set or
  edge-shape assertion, and either reversion silently disables the entry gate or silently cuts a
  cleanup lap.
- **Drive every new resolution test through `bash`, not `sh`** —
  `subprocess.run(["bash", "-c", body])`, matching `runners.py:297`. Under `dash`,
  `set -o pipefail` is unavailable and `rc=$?` becomes `tee`'s status (always 0), so an
  `sh`-driven test would report a passing gate for a failing suite.

_Wiring pass added by `/ll:wire-issue`:_
- No existing test in `scripts/tests/` executes the shell/heredoc body of any of the nine sites
  at the value-resolution level — every current test is structural only (state-set membership,
  `fragment:` field, routing-edge shape via `test_builtin_loops.py`'s per-loop classes:
  `TestDeadCodeCleanupLoop` L11688, `TestTestCoverageImprovementLoop` L11722,
  `TestEvaluationQualityLoop` L884). None of these will break from the conversion (they check
  supersets, not exact shell content), but none give resolution-level coverage today either —
  each site needs a new subprocess-level test. [Agent 3 finding]
- Closest template to follow per site: `TestRlCodingAgentObserveTestCmdResolution`
  (`test_builtin_loops.py:10747-10799`) — extract the `action` string, substitute
  `${context.run_dir}`/other refs, run via `subprocess.run(["bash","-c", ...])` against a scratch
  `.ll/ll-config.json`, asserting three cases: present-and-set, present-and-null (opts out, not
  literal `"None"`), and absent (falls back to `ll-config get`'s own `ProjectConfig` default).
  For the two context-override branches (`test-coverage-improvement.yaml`'s `measure` state),
  add a fourth case per `TestIncrementalRefactorLoop.test_verify_tests_resolves_context_first_then_ll_config`
  (L11983): context wins over `ll-config get`. [Agent 3 finding]
  **Correction (2026-08-21):** the fourth case does **not** belong at `measure` — that branch is
  dead (*Dead site*). Per the pinned decision (a) it attaches to `verify_tests` (`:148-158`)
  instead. Additionally, add a guard asserting no state in
  `test-coverage-improvement.yaml` resolves a `CMD` it never evaluates — the defect that made
  `:45` dead in the first place would otherwise be reintroducible.
- The three near-identical `harness-*.yaml` `check_concrete` states have zero existing coverage
  of their shell body (`grep check_concrete` only turns up unrelated eval-harness and
  wizard-fixture tests) — a single parametrized test class over the three loop files, following
  `test_bug3269_test_cmd_resolution_gate.py`'s own `pytest.mark.parametrize`-over-file-list
  pattern, avoids triplicating one subprocess test three times. [Agent 3 finding]
- `rn-refine.yaml`'s only existing test, `TestFullSuiteGate.test_full_suite_gate_noops_when_stepwise_unset`
  (`test_rn_refine.py:1951-1961`), exercises only the `stepwise=0` early-`exit 0` guard — it will
  not break from the conversion but gives zero coverage of the resolution logic underneath; a new
  test is needed for the actual `ll-config get` read. [Agent 3 finding]
- `evaluation-quality.yaml`'s `evaluate_code` state and `auto-refine-and-implement.yaml`'s
  `verify` heredoc (lines 430-437) both have zero resolution-level test coverage today — no test
  matches `code_results`/`eval-test-results` or drives the `verify` state's Python body. A
  structural guard mirroring `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path`
  (asserting `"ruff check scripts/" not in action` post-conversion) is the closest existing
  pattern for pinning the hardcoded-`ruff` removal specifically. [Agent 3 finding]
- If a new intermediate state is introduced for `dead-code-cleanup.yaml`'s or
  `test-coverage-improvement.yaml`'s explicit-skip §2b handling, note that
  `TestDeadCodeCleanupLoop.test_required_states_exist` (L11688) and
  `TestTestCoverageImprovementLoop.test_required_states_exist` (L11722) use subset checks
  (`required - actual`) — they will silently pass without validating the new state, so the new
  state needs its own dedicated assertion rather than relying on these tests to catch it.
  [Agent 2 finding]

### Documentation

- `scripts/little_loops/loops/README.md:33` — `auto-refine-and-implement`'s
  `test_cmd`/`lint_cmd` row
- `docs/guides/LOOPS_REFERENCE.md:979,1305,1327` — the `project.test_cmd`/`lint_cmd` rows
- `docs/guides/LOOPS_REFERENCE.md:1347` — `test-coverage-improvement`'s `test_cmd` context-variable
  row, currently documenting an inert knob (*Dead site*). Per the pinned decision (a) it **stays**
  and becomes true — no edit needed, but re-verify the wording matches `verify_tests`'s new
  context-first behavior
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:569` — **required edit at step 6, previously
  unlisted.** The sentence *"A handful of other loops are a temporary exemption pending
  ENH-3277's conversion pass"* (inside the "Resolving a Project Command Inside a Loop" section,
  `:516-569`) becomes false the moment `_PENDING_CONVERSION` is deleted. Rewrite it to name the
  three **permanent** exemptions (`oracles/code-run-gate.yaml`, `rn-refine.yaml`,
  `auto-refine-and-implement.yaml`) and their shared §1d rationale — absent ≡ null ≡ skip, never
  guess. Cited under *Codebase Research Findings* below but omitted from this list until now;
  leaving it stale would leave the guide pointing at a closed issue as pending work

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/EVALUATION_GUIDE.md:393` — prose reads *"runs your configured `test_cmd` plus
  `ruff`"*, describing exactly the hardcoded `ruff check scripts/` this issue converts to
  `ll-config get project.lint_cmd`; becomes stale once step 5 of Implementation Steps lands and
  needs updating to describe the configured `lint_cmd` instead. [Agent 2 finding, confirmed]
- In-YAML comments inside three already-listed primary files — `harness-single-shot.yaml:58`,
  `harness-multi-item.yaml:88`, `harness-plan-research-implement-report.yaml:120` — currently
  read "Reads test_cmd from .ll/ll-config.json; falls back to 'pytest' if absent" and describe
  the exact fallback being removed; update alongside each state's action body (sibling edit
  within files already in Files to Modify, not a new file). [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md:~277` — documents `verify_verdict: "skipped"` semantics for
  `auto-refine-and-implement`'s post-implementation verify step; the issue's plan for
  `auto-refine-and-implement.yaml:433-436`. **No edit needed under Option A** — the file is not
  converted, so its `verify_verdict: "skipped"` semantics are preserved byte-for-byte and this doc
  stays accurate as written. (It would have become a required edit under the rejected Option B,
  which is why an earlier pass upgraded it from a sanity check to a decision input.)
  [Agent 2 finding, resolved by the decision]

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

_Added 2026-08-21. Previously the done-condition lived only as prose inside step 6; this is that
condition made checkable. Every row is verified by a named test or a named command._

**Conversions (8)**

- [ ] `fix-quality-and-tests.yaml` `check-tests` reads `ll-config get project.test_cmd`; the
      three-way `python3 -c` body at `:58-78` is deleted, not generalized
- [ ] `harness-single-shot.yaml:66`, `harness-multi-item.yaml:95`,
      `harness-plan-research-implement-report.yaml:126` converted, **and** their `# EXAMPLE:`
      scaffold comments (`:57-60`, `:88`, `:120`) rewritten to stop teaching the inline parse
- [ ] `evaluation-quality.yaml:58` (`test_cmd`) converted, with a no-test-signal marker emitted
      **on stdout** (`| tee`, never a bare `>`)
- [ ] `evaluation-quality.yaml:63`'s hardcoded `ruff check scripts/` → `ll-config get
      project.lint_cmd`, with a no-lint-signal marker on stdout
- [ ] `test-coverage-improvement.yaml:37-48` (the dead `CMD` block in `measure`) **deleted**, and
      `verify_tests` (`:148-158`) given the context-first shape so the `:23` `test_cmd`
      declaration becomes live
- [ ] `dead-code-cleanup.yaml:76` converted, config-first bare

**Structural changes**

- [ ] Both `verify_tests` states are `fragment: harness_exit` with a declared `on_cannot_judge:`
- [ ] Both converted bodies collapse every non-zero exit to `1` (`rc=$?; [ "$rc" = 0 ] && exit 0;
      exit 1`) and keep their `tee` log; `[ -z "$CMD" ] && exit 3` is the only path to exit 3
- [ ] `unverifiable` exists in both loops as a **bare** `terminal: true` + `failure: true` state —
      no `action`, no `next:`
- [ ] `dead-code-cleanup.revert_unverifiable` exists as `action_type: prompt` with
      `next: unverifiable`, and is `verify_tests.on_cannot_judge`'s only target
- [ ] `dead-code-cleanup.check_preconditions` exists (config-first bare), and
      `dead-code-cleanup.yaml:7` is `initial: check_preconditions`
- [ ] `dead-code-cleanup.yaml:108` is `max_steps: 18`

**Gate teardown**

- [ ] `_PERMANENT_EXEMPTIONS` holds exactly three entries (`oracles/code-run-gate.yaml`,
      `rn-refine.yaml`, `auto-refine-and-implement.yaml`) with the §1d rationale in its comment
- [ ] `_PENDING_CONVERSION` and `test_pending_conversion_sites_still_exist` are deleted;
      `_EXEMPT = _PERMANENT_EXEMPTIONS`
- [ ] `_INLINE_ACCESS_RE` matches the two-step `project = cfg.get('project', {})` /
      `project.get('test_cmd')` binding shape, and the only hits across
      `scripts/little_loops/loops/**` are the three permanent exemptions
- [ ] `rn-refine.yaml` and `auto-refine-and-implement.yaml` are **byte-for-byte unchanged**

**Tests** (each is a new test; none exists today)

- [ ] Per-site subprocess resolution tests driven through **`bash -c`**, asserting all three
      config cases (set / present-null / absent); the three `harness-*` sites parametrized as one
      class
- [ ] Exit-3 collision case at both `verify_tests` states: `test_cmd: "sh -c 'exit 3'"` → state
      exits **1**; empty `CMD` → exits **3**
- [ ] `evaluation-quality` skip markers asserted on the state's **captured stdout**, not on
      `eval-test-results.txt` / `eval-lint-results.txt`
- [ ] Dedicated assertions for all four new/changed states, plus `initial` and `max_steps`
- [ ] Guard asserting no state in `test-coverage-improvement.yaml` resolves a `CMD` it never
      evaluates (the defect that made `:45` dead)

**Docs**

- [ ] `HARNESS_OPTIMIZATION_GUIDE.md:569` no longer calls the exemptions "temporary pending
      ENH-3277" and names the three permanent ones
- [ ] `EVALUATION_GUIDE.md:393` describes the configured `lint_cmd`, not `ruff`
- [ ] `loops/README.md:33` and `LOOPS_REFERENCE.md:979,1305,1327,1347` re-verified against final
      behavior

**Exit gates**

- [ ] `ll-loop validate` passes for every touched loop
- [ ] The scoped `grep` from step 7 (excluding the three permanent exemptions) returns empty
- [ ] `python -m pytest scripts/tests/` exits 0
- [ ] Manual smoke: `dead-code-cleanup` in a scratch project with `test_cmd: null` does **not**
      reach `commit`

## Implementation Steps

1. **BUG-3269 has landed** (status: done) and `_PENDING_CONVERSION` exists in
   `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:55-65` with its nine entries.
   The `ll-config get` convention, the `HARNESS_OPTIMIZATION_GUIDE.md` write-up
   (`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:516-569`), and both mirror-drift gate assertions
   were BUG-3269's deliverables, not this one's.
2. **Pick a §2b row for every site before writing any shell.** The table under *Proposed
   Solution* is a hard prerequisite, not advisory. The three marked *explicit skip required*
   (`dead-code-cleanup`, `test-coverage-improvement`, `evaluation-quality`) are the reason
   this work was split out of a P0.
3. **Convert the four unblocked pass-on-empty sites first** — `fix-quality-and-tests.yaml`
   (delete its three-way python body outright), `harness-single-shot.yaml`,
   `harness-plan-research-implement-report.yaml`, `harness-multi-item.yaml`. These are
   drop-ins or route to a further gate. Config-first bare shape for all four — none declares a
   `context.test_cmd` key. Rewrite the three `harness-*` template comments (`:57-60`, `:88`,
   `:120`) in the same edit — they are copy-me scaffolds teaching the anti-pattern, not
   incidental docs.
3b. **`rn-refine.yaml` and `auto-refine-and-implement.yaml` are never converted** (Option A, see
   *DECIDED* under *Proposed Solution*). Both YAMLs are left byte-for-byte unchanged. The only
   edit is in `scripts/tests/test_bug3269_test_cmd_resolution_gate.py`: move both filenames from
   `_PENDING_CONVERSION` into `_PERMANENT_EXEMPTIONS` (`:49`), which grows from one entry to
   three, and extend that constant's comment to carry the §1d rationale (absent ≡ null ≡ skip,
   never guess) for all three. Do **not** build `ll-config get --raw` — Option C was rejected.
4. **Convert the explicit-skip sites, one at a time, each with its regression test.**
   `evaluation-quality.yaml` first — its `:58` read (`test_cmd`) here, and its `:63` hardcode
   (`lint_cmd`) in step 5; both branches of `evaluate_code` emit their own "no signal" marker
   **on stdout** (`| tee`, never a bare `>`), because `score` reads
   `${captured.code_results.output}` and not the files — see *CAPTURE CORRECTION*. Do **not**
   reroute; `evaluate_code` has no `on_yes`/`on_no` edges.
   Then `test-coverage-improvement.yaml` — **delete the dead `CMD` block at `:37-48` rather than
   converting `:45`**, and apply *Dead site* decision **(a)**: `verify_tests` (`:148-158`) gets
   the context-first shape, the `:23` declaration stays, `LOOPS_REFERENCE.md:1347` stays. Then
   `dead-code-cleanup.yaml` last, since its `on_yes` commits deletions — and it carries the most
   added surface: the `check_preconditions` entry gate plus the `unverifiable` terminal state.
   Both `verify_tests` skip edges are pinned under *Pinning the two explicit-skip gate edges* —
   apply them, **including the non-zero exit collapse** (*EXIT-CODE COLLISION*), before writing
   any shell.
5. **Convert `evaluation-quality.yaml:63`'s hardcoded `ruff check scripts/`** to
   `ll-config get project.lint_cmd` — the same defect, pre-inlined.
6. **Empty `_PENDING_CONVERSION` and delete the constant.** Four coupled edits in
   `scripts/tests/test_bug3269_test_cmd_resolution_gate.py`, not one — deleting the constant
   alone is a `NameError`:
   - grow `_PERMANENT_EXEMPTIONS` (`:49`) from one entry to three, adding `rn-refine.yaml` and
     `auto-refine-and-implement.yaml` per step 3b (this must land *before* the set below is
     deleted, or the gate fails on those two files);
   - delete the `_PENDING_CONVERSION` set (`:55-65`);
   - delete `test_pending_conversion_sites_still_exist` (`:148-156`), which dereferences it;
   - collapse `_EXEMPT = _PERMANENT_EXEMPTIONS | _PENDING_CONVERSION` (`:67`) to
     `_EXEMPT = _PERMANENT_EXEMPTIONS`.

   Plus one doc edit in the same step: **`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:569`**'s
   "temporary exemption pending ENH-3277's conversion pass" sentence must be rewritten to name
   the three permanent exemptions — deleting the constant without it leaves the guide advertising
   this issue as pending work forever.

   Leave `test_no_inline_project_command_config_read`,
   `test_context_references_are_declared`, and
   `test_general_task_and_rl_coding_agent_are_not_exempt` in place. The inline-read assertion
   then holds with exactly three permanent exemptions. This is the definition of done.

   **Also widen `_INLINE_ACCESS_RE` (`:71-84`) — a verified blind spot.** The regex matches only
   a *chained* access (`get('project', {}).get('test_cmd')` or `['project']['test_cmd']`). It does
   **not** match the two-step binding shape:

   ```python
   project = cfg.get('project', {})
   test_cmd = project.get('test_cmd')
   ```

   That is precisely `auto-refine-and-implement.yaml:432-434` — **both** keys, `test_cmd` at
   `:433` and `lint_cmd` at `:434`; an earlier version of this step cited only `:432-433`. So its
   `_PENDING_CONVERSION` entry has been vacuous all along — the gate never detected it.

   **Why widen it at all, precisely.** Widening changes *nothing* for the two exempted files:
   they sit in `_PERMANENT_EXEMPTIONS` and are skipped before the regex runs either way. The
   value is entirely forward-looking — Option A leaves `auto-refine-and-implement.yaml` in the
   tree permanently as a **copyable precedent for a shape the gate cannot see**, so the next loop
   that clones it lands an undetected fourteenth inline read. Treat this as hardening the gate,
   not as part of this issue's correctness.

   Add an alternation for a `project`-bound local followed by `.get('<key>')`, then confirm the
   exempted files are the only hits.

   **Pre-verified (2026-08-21) — the confirmation step will pass.** Enumerated every loop YAML
   under `scripts/little_loops/loops/**` containing `get('project'`: `auto-refine-and-implement`,
   `dead-code-cleanup`, `evaluation-quality`, `fix-quality-and-tests`, the three `harness-*`,
   `rn-refine`, `test-coverage-improvement` (all converted or exempt by then),
   `oracles/code-run-gate.yaml` (permanently exempt), and **`lib/composer.yaml:133`** — the only
   non-exempt survivor. That one is `catalog.get('project', []) + catalog.get('builtin', [])`
   over a *loop catalog*, with no command key following, so the widened alternation does not
   match it. No new exemption is needed. Recorded here so this is not re-derived at
   implementation time.
   *(Step 6b — generalizing BUG-3276's this-repo-hardcode gate over all built-in loops — was
   **split out to ENH-3281**. It is a sibling defect class with its own exemption-discovery cost,
   and this issue's estimate of that cost was wrong: a naive gate hits five files, not the two
   claimed. Converting `evaluation-quality.yaml:63` stays here as step 5; generalizing the gate
   does not.)*

7. **Verify.** After each file: `ll-loop validate`, a scoped `grep` for the old
   `.get('test_cmd'` / `.get('lint_cmd'` pattern, and the gate with one fewer entry.

   **The grep must exclude `rn-refine.yaml` and `auto-refine-and-implement.yaml`** — under Option A
   they keep their inline parse permanently, so they will match forever. An unscoped grep reads as
   a failed conversion at every checkpoint:

   ```bash
   grep -rn "\.get('test_cmd'\|\.get('lint_cmd'" scripts/little_loops/loops/ \
     --include='*.yaml' \
     | grep -v -e 'rn-refine.yaml' -e 'auto-refine-and-implement.yaml' -e 'oracles/code-run-gate.yaml'
   ```

   Expected output at the end: empty.

   At the end: `python -m pytest scripts/tests/` exits 0, and a manual smoke of
   `dead-code-cleanup` in a scratch project with `test_cmd: null` confirming it does **not**
   reach `commit`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/EVALUATION_GUIDE.md:393` — replace "runs your configured `test_cmd` plus
  `ruff`" once step 5 converts `evaluation-quality.yaml:63`'s hardcoded `ruff check scripts/` to
  `ll-config get project.lint_cmd`
- Update the stale fallback-description comments inside `harness-single-shot.yaml:57-60`,
  `harness-multi-item.yaml:88`, `harness-plan-research-implement-report.yaml:120` alongside each
  state's action body — they currently describe the guessed-`'pytest'` fallback being removed.
  **Load-bearing, not cosmetic**: these are `# EXAMPLE:` scaffolds users clone, so the comments
  propagate the inline-parse anti-pattern into new loops
- Delete `test-coverage-improvement.yaml:37-48` (the dead `CMD` block in `measure`) rather than
  converting `:45`, and apply the pinned *Dead site* decision (a) across `:23` + `:152` +
  `LOOPS_REFERENCE.md:1347` together — they are one change, not three
- Apply the pinned empty-`CMD` targets for **both** `verify_tests` gates before writing shell
  (*Pinning the two explicit-skip gate edges*). `dead-code-cleanup`'s `on_error:
  revert_and_scan` and `test-coverage-improvement`'s `on_no/on_error: fix_tests` are each
  reachable but each mis-frames a no-signal skip as a test failure against an empty log
- **Switch both `verify_tests` states from `fragment: shell_exit` to `fragment: harness_exit`**
  as part of that edit — an `on_cannot_judge:` edge without the fragment switch is inert and
  routes `exit 3` to `on_error` instead (*MECHANISM CORRECTION*). Add an assertion pinning
  `evaluate.abstain_on_exit_3` / the `harness_exit` fragment at both states, so a future edit
  that reverts the fragment to `shell_exit` while leaving the `exit 3` body in place fails
  loudly rather than silently re-routing
- **Collapse every non-zero exit to `1` in both converted bodies** — `rc=$?; [ "$rc" = 0 ] &&
  exit 0; exit 1` after the `pipefail`/`tee` pipeline, so the state's own `[ -z "$CMD" ] && exit
  3` is the only path to `on_cannot_judge`. **pytest itself exits 3** on internal error, and
  without the collapse a real test failure is reported as "no signal" — deletions unreverted at
  `dead-code-cleanup`, `fix_tests` skipped at `test-coverage-improvement`
  (*EXIT-CODE COLLISION*). Keep the `tee`; `incremental-refactor`'s template omits it but both
  downstream prompt states read the log
- **A terminal state's action never executes** (`fsm/executor.py:601-636` returns
  `_finish("terminal")` before dispatch; the only fall-through is the `on_max_steps` cap-handler
  carve-out). So `unverifiable` is a **bare** `terminal: true` + `failure: true` marker with no
  action and no `next:` in **both** loops, and any revert/report work must live in a preceding
  non-terminal state. At `dead-code-cleanup` that is a new `action_type: prompt` state
  **`revert_unverifiable`** (`verify_tests.on_cannot_judge:` → it, `next: unverifiable`) which
  reverts the removal and writes `ll-dead-code-unverifiable.txt`; at
  `test-coverage-improvement` there is nothing to do, so `on_cannot_judge: unverifiable` goes
  straight to the bare terminal. **Never `next: scan`** on either — that re-deletes code every lap
  to `max_steps`. Do not reuse either loop's existing `failed` state
  (*TERMINAL-ACTION CORRECTION*, *Terminality of the two new states*, *State names*)
- **Required (pinned, was "recommended"): add an `incremental-refactor`-style
  `check_preconditions` entry gate to `dead-code-cleanup`** (`incremental-refactor.yaml:20-86`)
  so the loop refuses to start rather than deleting code it cannot verify — **but config-first
  bare, not the template's context-first shape**: `dead-code-cleanup`'s `context:` block
  (`:13-14`) declares only `commit_message`, so `${context.test_cmd}` would raise
  `InterpolationError` and fail gate assertion (ii). Routes `exit 1` → `on_no: unverifiable`
  (the bare terminal, not `revert_unverifiable` — nothing is deleted yet at loop start)
- **Move `dead-code-cleanup.yaml:7` from `initial: scan` to
  `initial: check_preconditions`** in the same edit. Adding the gate state without moving
  `initial` leaves it unreachable — `scan` still runs first, the gate never fires, and every
  structural assertion still passes. Assert `fsm.initial` explicitly
- **Raise `dead-code-cleanup.yaml:108` `max_steps: 15` → `18`** to absorb the entry gate and
  `revert_unverifiable` without silently cutting the loop from three cleanup laps to two
  (*Step budget*)
- Write new subprocess-level resolution tests per site (no existing test exercises shell content
  at the value-resolution level for any of the converted sites) — model on
  `TestRlCodingAgentObserveTestCmdResolution` (`test_builtin_loops.py:10747-10799`); parametrize
  the three `harness-*.yaml` `check_concrete` sites as one test class rather than tripling it
- If a new intermediate state is introduced for `dead-code-cleanup.yaml` or
  `test-coverage-improvement.yaml`'s explicit-skip handling, add a dedicated assertion for it —
  `test_required_states_exist` in both loops' test classes uses a subset check and will not
  catch a missing/misrouted new state
- Post-edit sanity check `skills/audit-loop-run/SKILL.md:~277`'s `verify_verdict: "skipped"`
  documentation against `auto-refine-and-implement.yaml:433-436`'s preserved skip semantics

**Rollback seam:** independent per-file edits. If one conversion misbehaves in a consuming
project, revert that file and re-add its exemption — as a `_PENDING_CONVERSION` entry if step 6
has not yet run, or as a `_PERMANENT_EXEMPTIONS` entry (with a rationale comment) if it has,
since step 6 deletes the former.

## Scope Boundaries

### RECOMMENDED SPLIT (2026-08-21) — not yet actioned

**This issue is EPIC-shaped at P2 and should probably ship as four.** As pinned it touches seven
loop YAMLs, performs eight conversions, switches two fragments, adds four states, edits two
one-line scalars, performs four coupled gate-constant edits, and requires roughly six new test
classes plus five doc edits. `outcome_confidence: 68` reflects that spread.

The seam already exists — the issue's own *Rollback seam* is per-file, and Implementation Steps
are already ordered by risk. The natural split concentrates the risk instead of spreading it:

| | Content | Risk |
|---|---|---|
| **(a)** | the four pass-on-empty drop-ins (`fix-quality-and-tests`, three `harness-*`) + their scaffold comments + four `_PENDING_CONVERSION` entries removed | mechanical; lands immediately |
| **(b)** | `evaluation-quality` — both branches, stdout markers, the `:63` hardcode | contained to one ungated state |
| **(c)** | `test-coverage-improvement` + `dead-code-cleanup` — fragment switches, exit collapse, entry gate, four new states, `initial`/`max_steps` | **all of the irreversible-edge risk in the family** |
| **(d)** | step 6 teardown + `_INLINE_ACCESS_RE` widening + the five doc edits | trivial once (a)–(c) land |

Splitting also makes (c) reviewable on its own, which is the part that commits code deletions.
**Left as a recommendation rather than executed** — the counts table, `_PENDING_CONVERSION`'s
definition of done, and the step ordering all assume a single issue, so a split needs those
rewritten across four files rather than one. Decide before starting implementation, not during.

**In scope:** the correct-but-guessing inline resolution sites listed under *Files to Modify* —
**seven files, eight inline reads, seven of them converted** per the counts table under *Summary*
(`test-coverage-improvement.yaml` has two, `:45` and `:152`, of which `:45` is dead and deleted;
`evaluation-quality.yaml` has one read at `:58`, not two) — plus
`evaluation-quality.yaml:63`'s hardcoded lint command as the eighth conversion, plus the two new
bare `unverifiable` terminal states, `dead-code-cleanup`'s `revert_unverifiable` prompt state and
its `check_preconditions` entry gate (with the accompanying `initial:` and `max_steps:` edits),
plus emptying and deleting
`_PENDING_CONVERSION` (moving two entries to `_PERMANENT_EXEMPTIONS` and widening
`_INLINE_ACCESS_RE`), plus the two doc files whose rows describe those sites.

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

**Out of scope — permanently (added by the Option A decision):** `rn-refine.yaml` and
`auto-refine-and-implement.yaml:433-436`. Same §1d rationale — an absent≡skip contract that
`ll-config get` cannot express. Both keep their inline parse and join
`oracles/code-run-gate.yaml` in `_PERMANENT_EXEMPTIONS`, bringing it to three entries. Accepted
cost: both continue to bypass `.ll/ll.local.md`.

**Out of scope — split separately:** generalizing BUG-3276's this-repo-hardcode gate over all
built-in loops → **ENH-3281** (was step 6b). Converting `evaluation-quality.yaml:63`'s
`ruff check scripts/` stays here as step 5; gating the *class* does not.

**Out of scope — split separately:** `incremental-refactor.yaml:12,33` → BUG-3276. It
performs no config read at all, so no gate covers it either way, and its destructive
`on_no: revert` edge needs its own safety analysis.

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
- `[ -z "$CMD" ]` → that site's §2b branch: pass-on-empty (four sites —
  `fix-quality-and-tests` plus the three `harness-*`) or an explicit skip (three sites —
  `evaluation-quality`'s marker file, `test-coverage-improvement` and `dead-code-cleanup`
  routing away from `commit`).
- non-empty `CMD` → `eval "$CMD"` → the site's existing gate, unchanged — a
  `fragment: shell_exit` gate at six of the read sites, and a plain `next:` with a downstream
  `capture:` consumer at `evaluation-quality.evaluate_code`, `test-coverage-improvement.measure`,
  and `rn-refine`'s full-suite gate (see *Two distinct hazards* under *Proposed Solution*).

**Precondition — cwd must be the project root.** `main_config` constructs
`BRConfig(Path.cwd())` with no upward walk, so a state invoked from a subdirectory loses the
opt-out. Safe for every converted site today: FSM shell actions run at
`FSMExecutor.working_dir` (`fsm/executor.py:2482`), the project or worktree root. Not a
regression — the inline snippets open the same relative path — but not fixed here either.

## Impact

- **Behavior change under `test_cmd: null`**: these sites stop gating on a guessed `pytest`.
  For four that is a clean opt-out; for `dead-code-cleanup`, `test-coverage-improvement`, and
  `evaluation-quality` it means committing or scoring unverified work unless the §2b row is
  applied.
- **`test-coverage-improvement`'s `context.test_cmd` becomes functional** (pinned decision (a)) —
  today it is declared, documented, and wired to nothing (*Dead site*). A user-visible change to a
  documented knob: a loop invocation that passes `test_cmd` starts having an effect at
  `verify_tests` where it previously had none.
- **`.ll/ll.local.md` overrides of `test_cmd`/`lint_cmd` start taking effect** inside these
  loops (they never did).
- **`evaluation-quality.yaml:63` lint scope widens**: `ruff check scripts/` →
  `ruff check .` in a project that never set `lint_cmd`. Already non-gating (`|| true`), so
  this affects the captured artifact, not control flow. No change in this repo, which sets
  `lint_cmd`.
- **Risk accepted**: these gates join the three from BUG-3269 in depending on a single
  fail-open binary (§1e there). Unlike `general-task`, they have no §3c equivalent mapping
  the malformed-config door to a sentinel — each falls back to its §2b row.
- **`dead-code-cleanup` gains a startup cost and refuses to run in more cases** (pinned entry
  gate): it now runs the test suite once before scanning, and a project with an unresolvable,
  unrunnable, or already-red suite gets a terminal `unverifiable` instead of a scan. That is the
  intended trade — the loop's `on_yes` deletes code and commits — but it is a user-visible
  behavior change beyond the resolution refactor. Note it also makes an **already-red** suite a
  refusal-to-start, which is a broader condition than "no `test_cmd` configured" and the main
  source of surprise for existing users of this loop.
- **`dead-code-cleanup`'s `max_steps` rises 15 → 18 and its `initial` moves to
  `check_preconditions`.** The step bump is not a behavior change users asked for; it exists to
  keep the loop at three cleanup laps after the entry gate and `revert_unverifiable` each claim a
  step (*Step budget*). A run that previously exhausted its budget mid-lap will now get slightly
  further.
- **Both `verify_tests` states stop distinguishing a command's exit code beyond pass/fail.** The
  mandated collapse to `exit 1` (*EXIT-CODE COLLISION*) means a runner that exits 2/3/5 now
  routes identically to a plain test failure. That is deliberate — it is what keeps pytest's
  internal-error code out of `on_cannot_judge` — but any future need to route on a specific
  runner exit code must claim a code the state normalizes *before* the collapse.
- **Rollback seam**: independent per-file edits; revert one file, nothing shared to unwind. The
  two structural additions (`check_preconditions`, `unverifiable`) are confined to
  `dead-code-cleanup.yaml` and `test-coverage-improvement.yaml` respectively.

## Related Key Documentation

- **BUG-3269** — the P0 this splits from; all design analysis lives there (§1, §1b, §1d, §1f,
  §2, §2b)
- BUG-3276 — `incremental-refactor.yaml`'s hardcoded `test_cmd`, split out separately
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the `ll-config get` convention, written up by
  BUG-3269

## Status

**Open** | Created: 2026-08-21 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-21_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- No execution-level test coverage exists today for any of the 9 target read sites — only structural checks (state-set membership, edge shape) cover them; a subprocess-level resolution test is needed per site (per Tests section) before/alongside each conversion to catch a bad `[ -z "$CMD" ]` routing choice.
- Two of the sites (`dead-code-cleanup.verify_tests`, `test-coverage-improvement.verify_tests`) require a `fragment: shell_exit` → `fragment: harness_exit` switch plus a new terminal `failure: true` state — this is deeper than the mechanical config-first substitution at the other seven sites, so treat those two as the highest-risk steps in the sequence and land them last, per Implementation Steps' own ordering.
- `format-check`'s `unapplied_decision` gate flagged a large number of terms from the issue's *rejected* Option B/C prose (e.g. `ll-config get`, `pytest`, `_raw_config`) as potentially unapplied — this reads as a likely false positive given the issue has an explicit `Decision Rationale` section scoring Option A as selected, but is worth a quick manual skim of the Proposed Solution/Program Design sections before implementing to confirm no genuinely-stale rejected-option text survives.
- `format-check` also flagged `stale_cli_flag: "ll-config get --raw (no such flag)"` and a missing `Behavior Parity` subsection — both expected given Option C's `--raw` flag was explicitly rejected and never built; confirm `cli/config.py` still has zero optional flags before starting, since a code drift there would invalidate the "No new production code" scope boundary.

## Session Log
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
