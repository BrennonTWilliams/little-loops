---
id: ENH-3277
type: ENH
title: Convert the nine remaining inline test_cmd/lint_cmd resolution sites to ll-config
  get
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
- BUG-3276
- ENH-2244
reconcile_attempted: true
---

# ENH-3277: Convert the nine remaining inline test_cmd/lint_cmd resolution sites to ll-config get

## Summary

Split out of **BUG-3269** (fourth-pass design review, 2026-08-20). BUG-3269 fixes the P0: the
three sites that emit a literal `None` on a present-but-null `project.test_cmd`
(`general-task.yaml:37`, `rl-coding-agent.yaml:60,68`), plus `general-task`'s baseline
sentinel and the mirror-drift gate.

This issue finishes the job: convert the **nine remaining "correct-but-guessing" call sites**
plus `auto-refine-and-implement.yaml:433-436` from hand-rolled inline `.ll/ll-config.json`
parsing to `ll-config get project.<key>`, and empty the `_PENDING_CONVERSION` exemption list
that BUG-3269's gate ships with.

**Why this is not part of the P0.** These nine sites *cannot* produce BUG-3269's failure:
their shape is `raw if raw else 'pytest'`, which never emits `None`. They are wrong in a
milder way — they override an explicit `test_cmd: null` with a `pytest` guess, and they all
bypass `.ll/ll.local.md` (§1b there). But converting them carries the sharpest behavior
changes in the original plan, on **irreversible edges**: `dead-code-cleanup` moves from
`revert_and_scan` to `commit` on an auto-deletion path, and `evaluation-quality` feeds an
empty capture to a scorer. That analysis must not gate a live spin fix.

All design work already exists in BUG-3269 and is not repeated here — read it there:
its §1 (`ll-config get`'s verified three-way contract), §1b (the `ll.local.md` bypass),
§1d (`oracles/code-run-gate.yaml`'s permanent exemption), §1f (why a non-zero exit is
unroutable at `evaluate: exit_code` states), §2 (per-site precedence — **config-first bare
for eight of the eleven**), and especially **§2b (the per-site empty-`CMD` table)**.

## Current Behavior

Nine sites parse `.ll/ll-config.json` inline and resolve a present-but-null `test_cmd` to a
guessed `pytest`, gating on a test suite the project deliberately opted out of. All of them
additionally ignore `.ll/ll.local.md`, the mechanism `.claude/CLAUDE.md` documents
*specifically* for overriding `project.test_cmd`.

`evaluation-quality.yaml:64` is a related pre-inlined case: a hardcoded `ruff check scripts/`
with no config read at all, sitting two lines below a site in this list.

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

**Two live (non-P0) defects close with it.** These sites override an explicit
`test_cmd: null` with a guessed `pytest` — so a docs or diagram project that deliberately
opted out still gets gated on a suite it does not have — and all of them bypass
`.ll/ll.local.md`, the mechanism `.claude/CLAUDE.md` documents *specifically* for overriding
`project.test_cmd`. Every one of these loops is live in every `local-editable` consuming
project on this machine with no reinstall step.

**Deferred deliberately, not incidentally.** The cost of *not* splitting was shipping a
commit-of-deletions behavior change on `dead-code-cleanup` inside a P0 hotfix. The cost of
splitting is that `_PENDING_CONVERSION` exists until this lands. That is the right trade, but
the list is technical debt with a name, and this issue is its payoff.

## Proposed Solution

Convert one file at a time, applying BUG-3269 §2's precedence shape and §2b's empty-`CMD` row
for that specific site. After each file: `ll-loop validate`, a scoped `grep` for the old
`.get('test_cmd'` pattern, and BUG-3269's gate with one entry removed from
`_PENDING_CONVERSION`.

### Hard prerequisite — pick a §2b row per site before writing any shell

This is the reason for the split, not an afterthought to it. Under `fragment: shell_exit`,
`eval ""` exits **0**, so an empty `CMD` makes the gate silently **pass** against an empty
artifact. Per BUG-3269 §2b:

| Site | `on_yes` | Decision |
|---|---|---|
| `fix-quality-and-tests.yaml:58-78` | `done` | pass-on-empty; drop-in (already the behavior — its three-way body prints `true`). Delete the three-way python body, do not generalize it |
| `harness-single-shot.yaml:61-72` | `check_semantic` | pass-on-empty (LLM gate still runs) |
| `harness-plan-research-implement-report.yaml:121-132` | `check_semantic` | pass-on-empty |
| `harness-multi-item.yaml:90-100` | `check_mcp` | pass-on-empty |
| `evaluation-quality.yaml:50-66` | **none — `next: score`, ungated** | **explicit skip required.** Express it by writing a "no test signal" marker into `eval-test-results.txt` (what `capture: code_results` reads) — **not** by rerouting; `evaluate_code` has no `on_yes`/`on_no` edges |
| `test-coverage-improvement.yaml:148-158` | `commit` | **explicit skip required** or route away from `commit` |
| `dead-code-cleanup.yaml:71-81` | `commit` / `on_no: revert_and_scan` | **explicit skip required.** `[ -z "$CMD" ]` must route to a non-committing edge. Today `pytest` fails in exactly the project shape BUG-3269 was found in → `revert_and_scan`; after a naive conversion → **commits dead-code deletions with zero verification.** Sharpest change in the whole family |
| `rn-refine.yaml:988-994` | advisory only | drop-in; preserve its existing `[ -z "$TEST_CMD" ]` branch |
| `auto-refine-and-implement.yaml:433-436` | `emit('skipped')` | drop-in; already treats falsy `test_cmd` as skipped |

**Rule:** a site whose `on_yes` edge performs an irreversible action (`commit`) or feeds a
score must handle `[ -z "$CMD" ]` explicitly. A site whose `on_yes` leads to another gate may
pass on empty.

### Precedence — config-first bare for eight of the eleven

Only three loops declare a `context.test_cmd` key at all (`general-task.yaml:23`,
`test-coverage-improvement.yaml:23`, `rl-coding-agent.yaml:17`). Of this issue's targets, only
`test-coverage-improvement.yaml` does. **Do not paste the context-first shape into the
others** — an undeclared `${context.test_cmd}` raises `InterpolationError: Path 'test_cmd' not
found in context` at interpolation time, turning a mechanical conversion into a hard loop
breakage. BUG-3269's gate assertion (ii) now catches this statically.

Config-first bare (eight sites):

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
    branch, without the `RC` check on the `ll-config get` fallback.
- Skip-on-empty already has three coexisting variants in the codebase, disagreeing on mechanism
  — relevant to picking a shape for the three explicit-skip sites this issue names:
  - **Pass-through**: `rl-coding-agent.yaml:68-75,79-85` — empty `TEST_CMD`/`LINT_CMD` sets the
    corresponding score to `0.0` and continues in the same state, no transition.
  - **Route-away via exit code**: `incremental-refactor.yaml` `check_preconditions:46-49` —
    empty `CMD` writes a failure artifact and `exit 1`, caught by that state's `on_no: failed`
    edge.
  - **Reserved exit code**: `incremental-refactor.yaml` `verify_tests:87` — `[ -z "$CMD" ] &&
    exit 3`, routed via a dedicated `on_cannot_judge: failed` edge kept distinct from a real
    test failure's `on_no: revert`.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s "Resolving a Project Command Inside a Loop"
  section is at lines 516-569, with the absent/null/value contract table at lines 528-532 and
  an explicit note naming this issue: "A handful of other loops are a temporary exemption
  pending ENH-3277's conversion pass."
- `dead-code-cleanup.yaml`'s current inline resolution (the site whose `on_yes: commit` this
  issue calls the sharpest change in the family) guesses `'pytest'` for both an absent and a
  present-and-null `test_cmd` via `raw if raw else 'pytest'` — `None` and `''` are both falsy in
  Python, so today a present-and-null config still runs the guessed default and can reach
  `on_yes: commit`.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/fix-quality-and-tests.yaml:58-78` — three-way body deleted
- `scripts/little_loops/loops/evaluation-quality.yaml:58` — and `:63`'s hardcoded
  `ruff check scripts/` → `ll-config get project.lint_cmd`
- `scripts/little_loops/loops/dead-code-cleanup.yaml:76`
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:126`
- `scripts/little_loops/loops/harness-multi-item.yaml:95`
- `scripts/little_loops/loops/harness-single-shot.yaml:66`
- `scripts/little_loops/loops/test-coverage-improvement.yaml:45,152`
- `scripts/little_loops/loops/rn-refine.yaml:991`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:433-436` — **not** `:679-680`,
  which reads `cfg.project.test_cmd` off a real `BRConfig` and is already correct and already
  `ll.local.md`-aware
- The `_PENDING_CONVERSION` constant landed by BUG-3269 — emptied, then deleted

Out of scope: `oracles/code-run-gate.yaml` (permanent exemption, BUG-3269 §1d);
`incremental-refactor.yaml` (BUG-3276).

### Tests

- Per-site regression tests for the three `[ -z "$CMD" ]` branches — in particular
  `dead-code-cleanup.yaml` must **not** reach `commit` under `test_cmd: null`
- BUG-3269's mirror-drift gate, with `_PENDING_CONVERSION` shrinking per file and finally
  removed

### Documentation

- `scripts/little_loops/loops/README.md:33` — `auto-refine-and-implement`'s
  `test_cmd`/`lint_cmd` row
- `docs/guides/LOOPS_REFERENCE.md:979,1305,1327` — the `project.test_cmd`/`lint_cmd` rows

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
3. **Convert the six pass-on-empty sites first** — `fix-quality-and-tests.yaml` (delete its
   three-way python body outright), `harness-single-shot.yaml`,
   `harness-plan-research-implement-report.yaml`, `harness-multi-item.yaml`,
   `rn-refine.yaml` (preserve its existing `[ -z "$TEST_CMD" ]` branch),
   `auto-refine-and-implement.yaml:433-436`. These are drop-ins or route to a further gate.
   Config-first bare shape for all six — none declares a `context.test_cmd` key.
4. **Convert the three explicit-skip sites, one at a time, each with its regression test.**
   `evaluation-quality.yaml` (write a "no test signal" marker into `eval-test-results.txt`;
   do **not** reroute — `evaluate_code` has no `on_yes`/`on_no` edges), then
   `test-coverage-improvement.yaml:45,152` (context-first — it *does* declare the key at
   `:23`), then `dead-code-cleanup.yaml` last, since its `on_yes` commits deletions.
5. **Convert `evaluation-quality.yaml:63`'s hardcoded `ruff check scripts/`** to
   `ll-config get project.lint_cmd` — the same defect, pre-inlined.
6. **Empty `_PENDING_CONVERSION` and delete the constant.** The gate's inline-read assertion
   then holds with only the permanent `oracles/code-run-gate.yaml` exemption. This is the
   definition of done.
7. **Verify.** After each file: `ll-loop validate`, a scoped `grep` for the old
   `.get('test_cmd'` / `.get('lint_cmd'` pattern, and the gate with one fewer entry.
   At the end: `python -m pytest scripts/tests/` exits 0, and a manual smoke of
   `dead-code-cleanup` in a scratch project with `test_cmd: null` confirming it does **not**
   reach `commit`.

**Rollback seam:** independent per-file edits. If one conversion misbehaves in a consuming
project, revert that file and re-add its `_PENDING_CONVERSION` entry.

## Scope Boundaries

**In scope:** the nine correct-but-guessing inline resolution sites listed under *Files to
Modify*, plus `auto-refine-and-implement.yaml:433-436`, plus `evaluation-quality.yaml:64`'s
hardcoded lint command, plus emptying and deleting `_PENDING_CONVERSION`, plus the two doc
files whose rows describe those sites.

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

**Out of scope — split separately:** `incremental-refactor.yaml:12,33` → BUG-3276. It
performs no config read at all, so no gate covers it either way, and its destructive
`on_no: revert` edge needs its own safety analysis.

**Explicitly not a call site:** `auto-refine-and-implement.yaml:679-680` reads
`cfg.project.test_cmd` / `cfg.project.lint_cmd` off a real `BRConfig` instance inside an
embedded Python block. It already resolves through `ProjectConfig` **and** already honors
`.ll/ll.local.md`. Do not "convert" it.

**No new production code.** Unlike BUG-3269, this issue touches loop YAMLs, tests, and docs
only — `ll-config get`'s resolution is unchanged and no CLI surface is added.

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
  absent-key fallback, replacing nine per-call-site `'pytest'` literals.

### Call Path

- each converted state → `ll-config get project.<key>` → `main_config` → `BRConfig(Path.cwd())`
  → `_load_config` (deep-merges `.ll/ll.local.md`, `:265-280`) → `ProjectConfig.from_dict`
  → `resolve_variable` → `print` only when non-`None`.
- `[ -z "$CMD" ]` → that site's §2b branch: pass-on-empty (six sites) or an explicit skip
  (`evaluation-quality` marker file, `test-coverage-improvement` and `dead-code-cleanup`
  routing away from `commit`).
- non-empty `CMD` → `eval "$CMD"` → the site's existing `fragment: shell_exit` gate,
  unchanged.

**Precondition — cwd must be the project root.** `main_config` constructs
`BRConfig(Path.cwd())` with no upward walk, so a state invoked from a subdirectory loses the
opt-out. Safe for every converted site today: FSM shell actions run at
`FSMExecutor.working_dir` (`fsm/executor.py:2482`), the project or worktree root. Not a
regression — the inline snippets open the same relative path — but not fixed here either.

## Impact

- **Behavior change under `test_cmd: null`**: these sites stop gating on a guessed `pytest`.
  For six that is a clean opt-out; for `dead-code-cleanup`, `test-coverage-improvement`, and
  `evaluation-quality` it means committing or scoring unverified work unless the §2b row is
  applied.
- **`.ll/ll.local.md` overrides of `test_cmd`/`lint_cmd` start taking effect** inside these
  loops (they never did).
- **`evaluation-quality.yaml:64` lint scope widens**: `ruff check scripts/` →
  `ruff check .` in a project that never set `lint_cmd`. Already non-gating (`|| true`), so
  this affects the captured artifact, not control flow. No change in this repo, which sets
  `lint_cmd`.
- **Risk accepted**: these gates join the three from BUG-3269 in depending on a single
  fail-open binary (§1e there). Unlike `general-task`, they have no §3c equivalent mapping
  the malformed-config door to a sentinel — each falls back to its §2b row.
- **Rollback seam**: independent per-file edits; revert one file, nothing shared to unwind.

## Related Key Documentation

- **BUG-3269** — the P0 this splits from; all design analysis lives there (§1, §1b, §1d, §1f,
  §2, §2b)
- BUG-3276 — `incremental-refactor.yaml`'s hardcoded `test_cmd`, split out separately
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the `ll-config get` convention, written up by
  BUG-3269

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:reconcile-issue` - 2026-08-21T14:29:42 - `08bd38ec-d985-4ff9-b92f-3e3223f35d2e.jsonl`
- `/ll:refine-issue` - 2026-08-21T14:00:56 - `6686f401-b52b-45b3-a364-e4c7f0616eb7.jsonl`
- `/ll:refine-issue` - 2026-08-21T14:00:48 - `6686f401-b52b-45b3-a364-e4c7f0616eb7.jsonl`
