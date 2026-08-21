---
id: BUG-3269
type: BUG
title: 'Loop test_cmd resolution: present-but-null yields literal "None", poisoning
  the no-regression gate into an infinite final_verify cycle'
priority: P0
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T22:48:59Z'
completed_at: '2026-08-21T02:59:11Z'
labels:
- bug
- loops
- general-task
- config
- test-cmd
- postmortem
relates_to:
- ENH-3277
- ENH-2244
- BUG-3270
- BUG-3271
- ENH-3272
- BUG-3274
- BUG-3276
confidence_score: 98
outcome_confidence: 79
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 25
---

# BUG-3269: Loop test_cmd resolution: present-but-null yields literal "None", poisoning the no-regression gate into an infinite final_verify cycle

## Summary

Every loop that resolves `project.test_cmd` from `.ll/ll-config.json` hand-rolls its own
inline `python3 -c` snippet. There are ~10 such copies and they do not agree. Two of them
(`general-task.yaml:37`, `rl-coding-agent.yaml:60`) use `dict.get(key, default)`, which
returns the default only when the key is **absent** — when the key is present with value
`null`, they return `None` and `print(None)` emits the literal string `None`, which the
shell then tries to execute.

Exactly one copy (`fix-quality-and-tests.yaml:66-72`) implements the correct
present-vs-absent semantics — but the existing `ll-config get` CLI already implements those
semantics *and* honors `.ll/ll.local.md`, which all 13 inline copies silently ignore. This
issue routes the **three defective sites** through `ll-config get project.<key>`, hardens
`general-task`'s baseline sentinel, and lands a static mirror-drift gate so the fourteenth
copy cannot reintroduce the defect.

> **SCOPE — REVISED 2026-08-20 (fourth pass). The bulk conversion is split out.**
> The nine "correct-but-guessing" sites **cannot produce this P0**: `raw if raw else
> 'pytest'` never emits `None`. Only `general-task.yaml:37` and `rl-coding-agent.yaml:60,68`
> do. Converting the other nine carries the sharpest behavior changes in the original plan —
> `dead-code-cleanup` moving from `revert_and_scan` to `commit` on an **auto-deletion** path,
> `evaluation-quality` feeding an empty capture to a scorer — and bundling them delays a P0
> spin fix that is live in every local-editable consuming project *right now*.
>
> This is the same argument this issue already accepted for splitting out
> `incremental-refactor.yaml` (BUG-3276): a P0 spin fix must not wait behind an unrelated
> destructive-default fix. See **Deferred to follow-up** below for the exact split. The §4
> mirror-drift gate **stays here**, with the ten unconverted sites as a documented,
> shrinking exemption list — so no *fourteenth* copy can land while the follow-up is open.

Discovered by forensic audit of `general-task` run `2026-08-20T121448` in
an external docs-oriented project with `test_cmd: null`, which spun for
2h37m / 45 identical laps on a task that had already succeeded. Postmortem:
`postmortems/general-task-final-verify-spin-2026-08-20.md` (§2, §5).

## Current Behavior

**Divergent resolution inside a single loop.** `general-task.yaml` resolves the same
config key two different ways:

`general-task.yaml:37` — `check_baseline_tests`:

```python
print(cfg.get('project',{}).get('test_cmd','pytest'))
```

`general-task.yaml:613-618` — `run_final_tests`:

```python
raw = cfg.get('project', {}).get('test_cmd')
print(raw if raw else 'pytest')
```

Reproduction of the divergence:

```
$ python3 -c "cfg={'project':{'test_cmd':None}}; print(repr(cfg.get('project',{}).get('test_cmd','pytest')))"
None
$ python3 -c "cfg={'project':{'test_cmd':None}}; raw=cfg.get('project',{}).get('test_cmd'); print(repr(raw if raw else 'pytest'))"
'pytest'
```

**Observed failure chain (verified against the run's artifacts):**

1. `check_baseline_tests` runs `eval "None"` → `bash: line 1: None: command not found`
   → writes **`127`** to `baseline-exit.txt`. Both artifacts survive in the run dir:
   `baseline-test-output.txt` = `bash: line 1: None: command not found` (38 bytes),
   `baseline-exit.txt` = `127`.
2. The state has `on_error: define_done`, so the garbage baseline is silently accepted.
3. `run_final_tests` resolves the *same* config to `pytest`, which exits **2**
   (12 pre-existing `ModuleNotFoundError` collection errors, unrelated to the task).
4. The ENH-2244 no-regression gate evaluates `[ "2" = "0" ] || [ "2" = "127" ]` →
   **false** → `on_no: continue_work`.
5. `continue_work` re-asks the model, which correctly answers `WORK_COMPLETE` →
   `final_verify` → `run_final_tests` → step 4. Forever. 45 laps until SIGKILL.

The gate logic in step 4 is correct. Its input was poisoned at second 0 and nothing
downstream could recover.

**Second, independent instance of the same defect.** `rl-coding-agent.yaml:60`:

```python
print(cfg.get('project', {}).get('test_cmd', '${context.test_cmd}'))
```

Same shape — present-but-null returns `None`, not the context override. This one feeds a
**reward signal**: `observe` computes `TEST_SCORE` from the output of `eval "$TEST_CMD"`,
so under a null config every rollout is scored against `command not found` output, yielding
`PASSED=0` and a silently meaningless composite reward. No spin, no crash — just wrong
numbers. The `lint_cmd` resolution two lines below (`:67`) has the identical shape.

**The correct semantics already exist here.** `fix-quality-and-tests.yaml:66-72`:

```python
raw = cfg.get('project', {}).get('test_cmd')
# None/null means 'no tests configured' — skip with success
# Missing key means 'not configured yet' — default to pytest
if 'project' in cfg and 'test_cmd' in cfg['project']:
    print(raw if raw else 'true')
else:
    print(raw if raw else 'pytest')
```

This is the only site out of ~10 that distinguishes present-and-null from absent.

## Steps to Reproduce

**Minimal — the resolution divergence itself:**

```
$ python3 -c "cfg={'project':{'test_cmd':None}}; print(repr(cfg.get('project',{}).get('test_cmd','pytest')))"
None
$ python3 -c "cfg={'project':{'test_cmd':None}}; raw=cfg.get('project',{}).get('test_cmd'); print(repr(raw if raw else 'pytest'))"
'pytest'
```

The first is `general-task.yaml:37`; the second is `general-task.yaml:617`. Same config,
same loop, two answers.

**Full — the infinite cycle:**

1. Create a scratch project with `.ll/ll-config.json` containing
   `{"project": {"test_cmd": null}}`. The key must be **present and null** — omitting it
   does not reproduce.
2. Ensure a bare `pytest` in that project exits non-zero (e.g. any collection error). A
   docs or diagram project with no test suite satisfies this naturally.
3. Run `general-task` with any task that will actually complete.
4. Observe `${run_dir}/baseline-test-output.txt` = `bash: line 1: None: command not found`
   and `${run_dir}/baseline-exit.txt` = `127` — written at second 0, before any work.
5. Let the run reach `final_verify`. It cycles
   `continue_work → final_verify → run_final_tests → continue_work` indefinitely, with
   `done_counts.total == 0` and `continue_result == WORK_COMPLETE` on every lap.
6. The run only ends at `max_iterations` or by manual SIGKILL.

**Frequency**: deterministic. Every run of an affected loop in a project with an explicit
`test_cmd: null` and a failing bare `pytest`.

**Observed in**: `general-task` v1.156.0, run `2026-08-20T121448`. 356 iterations,
~4h58m wall clock, terminated by user SIGKILL.

## Expected Behavior

One resolution path, three outcomes:

| Config state | Resolved command | Rationale |
|---|---|---|
| `test_cmd` absent | `pytest` | Not configured yet — the existing guess is a reasonable default. |
| `test_cmd: null` (explicit) | **no test gate** | The project deliberately opted out. Do not guess. |
| `test_cmd: "<cmd>"` | `<cmd>` | Explicit. |

For `general-task` specifically:

- `check_baseline_tests` must never write a garbage exit code. When there is no runnable
  baseline — resolved command is the opt-out sentinel, **or** the command exits 127,
  **or** `baseline-test-output.txt` matches `command not found` — write
  `baseline-exit.txt` = `SKIP`.
- `run_final_tests` must treat `baseline-exit.txt` = `SKIP` as "no baseline to compare
  against", never as a numeric exit code to match. A baseline that never ran must never be
  compared against. **"Pass on non-crash" is defined precisely as: pass when
  `FINAL_EXIT` is `0` *or* `127`.** The `127` arm is load-bearing — see below.
- **`test_cmd` may be present, non-null, and still unrunnable** (e.g. `"make test"` in a
  project without `make`). Then the baseline exits 127 → `SKIP`, and `run_final_tests`
  exits 127 too. If `SKIP` meant only "require `FINAL_EXIT = 0`", that run spins on the
  exact BUG-3269 cycle with a *non-null* config — this fix would close only the
  `test_cmd: null` path. Admitting `127` under `SKIP` closes it: an unrunnable command
  never gates. A command that runs and genuinely fails (exit 1, 2, …) still gates
  normally. BUG-3270's spin guard remains the backstop for any residual cycle, but this
  issue must not rely on it to be correct.
- **`FINAL_EXIT = 127` must also be non-gating on the *numeric*-baseline branch — otherwise a
  residual spin path survives this fix.** The `SKIP` rule above hardens the baseline side
  only. Consider a run whose baseline executes cleanly (say exit `2`, pre-existing failures,
  so `baseline-exit.txt` = `2`, a valid digit run that §3b's normalization deliberately does
  *not* rewrite to `SKIP`) and whose command then becomes unrunnable before
  `run_final_tests` — a worktree without the tool on PATH, a PATH change mid-run, `make`
  absent in the isolated checkout. Then `[ "127" = "0" ] || [ "127" = "2" ]` is false →
  `on_no: continue_work` → the BUG-3269 cycle, with a valid `test_cmd` **and** a valid
  baseline. Low probability, but it is the same defect and this issue explicitly does not
  get to lean on BUG-3270 for correctness. Fix: treat `FINAL_EXIT = 127` as pass on both
  branches, not just under `SKIP`.
- **`126` is deliberately excluded from the pass-set — do not "fix" this later.** Exit `126`
  is *found but not executable* (a test script checked in without the executable bit, a
  permission problem), which is
  a stable property of the tree rather than a transient environment gap: the baseline and the
  final run both produce `126`, and the ENH-2244 equality arm already passes them. Admitting
  `126` alongside `127` would additionally mask a genuinely broken test runner in the case
  where the baseline ran fine. The asymmetry is intentional.
- Under explicit `test_cmd: null`, `run_final_tests` runs nothing and passes. (It is a
  `shell_exit` state evaluated by exit code, so "route to `count_final`" means the action
  exits 0 without invoking a command — not a distinct routing edge.)

Note the opt-out must be declared in `.ll/ll-config.json`. An explicit `null` in
`.ll/ll.local.md` frontmatter means *remove this override* under the documented local-merge
semantics, which resolves to the absent-default (`pytest`), not to opt-out — verified
below. That asymmetry is expected, not a second defect, but it must be documented.

## Motivation

**This is live in every consuming project right now.** Per `.claude/CLAUDE.md`, all
little-loops projects on this machine are `local-editable` against this checkout, so the
defect ships with no reinstall step — and so does the fix. Any project with
`test_cmd: null` (the common shape for docs, diagram, config, and non-Python projects)
that runs `general-task` will burn its full iteration budget on a task that already
succeeded. The observed cost was ~4h58m wall clock, 356 iterations, 1.72M output tokens,
of which 331 iterations produced no deliverable change.

**Fixing line 37 in place is not sufficient.** The duplication *is* the bug: nine other
sites are one careless edit from the same failure, and `rl-coding-agent` already has it.

## Proposed Solution

> **Revised 2026-08-20 after design review.** The original plan proposed a
> `resolve_test_cmd` fragment in `lib/common.yaml`. That mechanism cannot express this
> fix (see *Rejected approach* below), and it also missed an existing helper that already
> implements the required semantics correctly. The plan now routes every site through
> `ll-config get`.

### 1. Delegate to the existing `ll-config get` CLI

`ll-config get project.test_cmd` (`scripts/little_loops/cli/config.py`) **already
implements the exact three-way contract** from Expected Behavior. Verified empirically:

| `.ll/ll-config.json` | `ll-config get project.test_cmd` |
|---|---|
| `{"project":{"test_cmd":null}}` | *(empty)* — opt-out |
| `{"project":{}}` | `pytest` |
| `{"project":{"test_cmd":"make test"}}` | `make test` |
| file absent entirely | `pytest` |

`project.lint_cmd` behaves identically (absent-default `ruff check .`) — checked, **no
gap**. So the same call serves `rl-coding-agent.yaml:68`.

The three-way split arises because `ProjectConfig.from_dict` uses
`data.get("test_cmd", "pytest")` (`config/core.py:215`) — absent yields the default
string, present-and-null yields `None` — and `BRConfig.resolve_variable` returns `None`
for a null value (`config/core.py:1056-1057`), which `main_config` prints as nothing
(`cli/config.py:75-76`). This is correct but **load-bearing and unpinned**: the field is
annotated `str` while holding `None`, exactly the BUG-3274 defect shape. A future
type-correctness cleanup that coerces `None → "pytest"` would silently destroy the opt-out.
Step 5 pins it with a regression test.

**Each call site collapses to one line:**

```bash
CMD=$(ll-config get project.test_cmd)
[ -z "$CMD" ] && { : "no test command configured — skip"; }
```

> **Do NOT add a `|| { ...; exit N; }` guard to this shape at an exit-code-gated site.**
> An earlier revision of this issue specified exactly that, to catch a missing `ll-config`
> binary (bash's 127). **It is actively harmful and must not be reintroduced** — see the
> routing analysis in §1f. The missing-binary door is closed in `check_baseline_tests`
> instead (§3c), where branching is free.

`ll-config` is on PATH for `ll-loop`-driven runs by construction: the loop is being executed
by `ll-loop` from the same installed package, and every converted site runs inside such a
run. But that is an inherited property, not an enforced one — a project whose
`install_source` is `global-claude-code` / `project-claude-code` has the plugin without
necessarily having the pip package's `ll-*` entry points, and unlike the `python3 -c`
snippets being replaced, a missing binary fails **silently and fail-open across all 13 gates
at once**. §3c closes it at the one site that can safely detect it.

**This is a new convention, not an established one.** No loop YAML currently invokes
`ll-config` — verified by grep over `scripts/little_loops/loops/**`; every existing
reference is either a prose comment or an inline `.ll/ll-config.json` read. There is no
in-repo precedent to copy, which is why the harness-guide documentation in Step 6's wiring
list is part of the deliverable rather than a nicety.

**Cost per call**: ~0.17s wall (measured: `0.168s total`), and each invocation opens a
`cli_event_context` against `history.db` (`cli/config.py:60`), so under
`analytics.capture.cli_commands: ["*"]` every resolution writes an event row. Negligible for
`general-task` (2 calls/run), but `rl-coding-agent`'s `observe` fires 2 calls **per
rollout**, and an `ll-parallel` run multiplies that by the worker count against the same
`history.db`. Acceptable — the inline `python3 -c` it replaces costs the same order — but it
should not be pushed into a tighter inner loop without re-measuring.

**Caveat on that measurement — it is probably the wrong branch.** The opt-out path
(`value is None`, `cfg is not None`) falls into `_warn_if_unknown_section`
(`cli/config.py:77-78`), which imports `little_loops.init.core` and reads
`config-schema.json` off disk (`:93-97`) before concluding that `project` is a known root and
printing nothing. That branch is taken **only** when resolution is empty — i.e. exactly the
`test_cmd: null` case the 0.168s figure most likely did not cover. Re-measure the null path
before accepting the cost paragraph, and consider short-circuiting
`_warn_if_unknown_section` when the root segment is already in `cfg.to_dict()` (a two-line
guard) so the opt-out path does not pay for schema loading. This matters most for
`rl-coding-agent`, where it is 2 calls per rollout.

### 1e. Structural problem being inherited: `ll-config get` is fail-open, and this issue converts 13 gates onto it

**This is the one design decision worth making before any shell is written.**

`main_config` is `never-raise / always-exit-0 / print-nothing-on-anything-unexpected`
(`cli/config.py:54-80`, and the contract is written into the `--help` epilog at `:34-39`).
That is a reasonable contract for the interactive `ll-config get history.foo.bar` use it was
built for. It is the **wrong shape for a gate resolver**, because every failure mode collapses
to the same byte-identical signal as a deliberate opt-out:

| Door | stdout | exit | Meaning under the §3 contract | Status |
|---|---|---|---|---|
| `test_cmd: null` | empty | 0 | opt out | **intended** |
| malformed `.ll/ll-config.json` | empty | 0 | opt out | **wrong** — closed by §3c |
| ~~exception inside `resolve_variable`~~ | — | — | — | **not a real door, see below** |
| `ll-config` not on PATH | empty | **127** | opt out | **wrong** — closed by §3c |

**Row 3 is struck: `resolve_variable` cannot raise.** `config/core.py:1039-1061` is a pure
dict walk that `return None`s on any miss, then `str(value)` — there is no parse, no I/O, and
no call that can throw for any realistic value. The `except Exception` at `cli/config.py:69-73`
is therefore only ever entered from the `BRConfig(Path.cwd())` **construction** on line 71.
That collapses the table to two live doors, both of which §3c closes at
`check_baseline_tests` without new CLI surface.

**DECISION — RESOLVED 2026-08-20 (third pass). Do NOT add a strict mode to `ll-config get`.**
A previous revision of this section proposed a `--strict` flag that would exit non-zero on
non-null resolution failure, and recommended it. That recommendation is **withdrawn** for two
independent reasons:

1. **It covers one door, not a class.** With row 3 struck, `--strict` and the plain stderr
   warning discriminate exactly the same single condition — construction failure — using the
   same `cfg is None` signal. The "closes the class rather than one instance" argument for it
   was simply wrong.
2. **Its output is unroutable at the sites that need it.** See §1f. Turning a resolution
   failure into a non-zero exit at an `evaluate: exit_code` state routes to `on_no`, which for
   `run_final_tests` is `continue_work` — the BUG-3269 spin. Making `--strict` useful would
   require swapping those states to `fragment: harness_exit` and designing an
   `on_cannot_judge` edge for each, which is a new routing outcome in three gating states on
   an already 11-file P0.

**What lands instead:** §1e's original stderr warning, kept as a **pure diagnostic** with no
behavioral role, plus §3c's resolve-once design, which routes both live doors through the
`SKIP` sentinel that §3/§3b already build. No new CLI surface, no new routing edge.

**Verify the warning is actually visible before relying on it.** §1e's original
text asserts the stderr warning lands "in the loop's captured state output where a run
forensic would find it." That is **unverified**. In `check_baseline_tests` the warning fires
*before* the `eval "$CMD" > ... 2>&1` redirect, so it does not reach
`baseline-test-output.txt`; it reaches the FSM executor's own stream for that state. If
`FSMExecutor` does not persist per-state shell **stderr** to the run dir, the warning is
written to nowhere and the remedy delivers literally nothing. Confirm this before Step 3a;
if stderr is not persisted, write the marker into a run-dir artifact instead.

---

_Original §1e text, retained — the ambiguity it documents is real and its analysis of the
`cfg is None` discriminator is correct and still load-bearing under either option:_

`main_config` swallows **every** exception into `value = None` (`cli/config.py:69-73`) and
then prints nothing with exit 0. So an unparseable `.ll/ll-config.json` produces byte-identical
output to an explicit `test_cmd: null`. Verified:

```
$ cat .ll/ll-config.json
{"project": {"test_cmd": "make test",,,}
$ ll-config get project.test_cmd
                      # empty stdout, empty stderr, exit 0
```

Under the §3 contract that resolves to `[ -z "$CMD" ]` → **opt out of the test gate
entirely**. A project whose config file is broken silently loses its no-regression gate — the
same defect class this issue exists to close (a garbage resolution disabling the gate at
second 0), just arriving through a different door.

**This is not a regression.** All 13 inline snippets already behave this way: `json.loads`
raises inside `python3 -c`, the subshell dies, `CMD` is empty, and `eval ""` exits 0. But the
conversion must not enshrine it as correct-by-omission. Required:

- Implementation Step 1 pins it with a test: malformed `.ll/ll-config.json` → empty stdout,
  exit 0. The test documents the ambiguity so a future change to `cli/config.py`'s
  `except Exception` is a deliberate act.
- **Remedy — DECIDED 2026-08-20: lands in this issue, not deferred. Confirmed by the third
  pass as the form that ships** — the strict-mode alternative above is withdrawn, so this
  warning is the whole of the CLI-side remedy, with §3c carrying the behavioral half.
  Make `main_config`
  distinguish the two. When `BRConfig(Path.cwd())` construction itself raises, emit a stderr
  warning (mirroring the existing `_warn_if_unknown_section` shape at `cli/config.py:83-101`)
  before returning 0. Stdout and exit code stay unchanged, so no call site's `$(...)` capture
  or the never-raise/always-0 contract is affected — the signal is purely diagnostic, visible
  in the loop's captured state output where a run forensic would find it. This is the one
  place the "no new production code" property of the plan is worth spending.

  **The discriminator is confirmed to exist.** A malformed config yields empty output
  *because construction raises* — if the parse failure were swallowed inside `BRConfig`, the
  call would return the `ProjectConfig` default `pytest`, not nothing. Verified: malformed →
  empty, absent-file → `pytest`. So `cfg is None` at `cli/config.py:70` is exactly the
  signal, and the existing `elif cfg is not None:` branch (`:77-78`) already has the shape.

  **Implementation caveat:** the current `except Exception` (`cli/config.py:69-73`) wraps
  *both* the `BRConfig(...)` construction and the `resolve_variable(...)` call, so it cannot
  tell a broken config from an unresolvable key. Split it into two `try` blocks — construct
  in the first (on failure: warn, `return 0`), resolve in the second (on failure: `value =
  None`, existing behavior). ~5 lines.

### 1f. Why a resolution failure must NOT be signalled by a non-zero exit — verified against the executor

**This is the constraint that shapes §3c, and it is easy to get backwards.** A guard like

```bash
CMD=$(ll-config get project.test_cmd) || { echo "FATAL" >&2; exit 3; }
```

looks like an obvious safety improvement. At an **exit-code-gated** state it is the opposite:
it converts a silent fail-open into an infinite loop.

`fsm/executor.py:2015-2037`: for a state with `evaluate: type: exit_code`, `on_error` is
reached **only** for classified failure types — `TRANSIENT` / api-server-error
(`:2015-2023`), `INFRA_RETRY` (`:2024-2030`), and `NON_RECOVERABLE` auth
(`:2031-2037`). Anything else falls through to ordinary verdict routing, where a non-zero
exit is a **`no` verdict**. (The `if result.exit_code != 0 and state.on_error` branch at
`:1835-1848` — which *does* prefer `on_error` — is in the **`next:`-routing** path, i.e. for
states with no `evaluate:` block. It does not apply to `shell_exit` states.)

Consequences at the three gating sites:

| State | Fragment | `on_no` | Effect of `exit 3` on a missing `ll-config` |
|---|---|---|---|
| `general-task` `run_final_tests` | `shell_exit` | `continue_work` | **the exact BUG-3269 spin**, now triggered by a missing binary instead of a null config |
| `dead-code-cleanup` `:71-81` | `shell_exit` | `revert_and_scan` | reverts valid work on every lap |
| `test-coverage-improvement` `:148-158` | `shell_exit` | (per §2b) | gate fails permanently |

So at an exit-code-gated state the only expressible outcomes are `0` → `on_yes` and non-zero
→ `on_no`. There is no third channel — unless the state opts into
`fragment: harness_exit`'s ABSTAIN contract (`lib/common.yaml:23-36`: 0=pass, 1=fail,
3=abstain, requires `on_cannot_judge`), which is a genuine third outcome but also a new edge
to design per state. **This issue does not do that.** It resolves in the one state that is
free to branch (§3c).

**`check_baseline_tests` is that state.** It is `next: define_done` with no `evaluate:` block
(`general-task.yaml:35-43`), so its exit code is not a verdict — it can test `$?`, branch, and
write whatever sentinel it likes with zero routing risk. That asymmetry is the whole reason
§3c works.

### 3c. Resolve once in `check_baseline_tests`; `run_final_tests` reads the result

**Supersedes the "both states must end up with byte-identical resolution shell" requirement
in §2.** That requirement is a synchronization invariant with no enforcement — the two copies
drift the moment someone edits one, which is *literally the bug this issue exists to fix*,
reintroduced one level up. Replace it with a single resolution:

- `check_baseline_tests` resolves the command **once** — applying §2's context-first
  precedence — and writes the resolved value to `${context.run_dir}/resolved-test-cmd.txt`.
- On any unresolvable condition it writes an **empty** `resolved-test-cmd.txt` and `SKIP` to
  `baseline-exit.txt`. Unresolvable means: `[ -z "$CMD" ]` (explicit null **or** malformed
  config, §1e rows 1–2), **or** `ll-config` not found (`$?` = 127 from the substitution,
  §1e row 4 — safe to test here, and only here). It is also free to log which of the three it
  was into the run dir, which is the diagnostic §1e's stderr warning was reaching for, in a
  location known to survive.
- `run_final_tests` **reads** `resolved-test-cmd.txt` instead of resolving again. It never
  calls `ll-config`. For what empty-or-missing means, see the 2×2 immediately below — **not**
  "the `SKIP` path §3/§3b already specify", which is a different signal.

**⚠ "The `SKIP` path" names two different things — do not conflate them.**
An earlier revision routed an empty `resolved-test-cmd.txt` to "the `SKIP` path §3/§3b
already specify". But §3b's `SKIP` is a property of **`baseline-exit.txt`** and gates on
`FINAL_EXIT ∈ {0,127}`, which presupposes that a command actually *ran*. Emptiness of
`resolved-test-cmd.txt` means no command runs at all, so there is no `FINAL_EXIT` to gate on.
These are **orthogonal signals** and row 2 below is genuinely reachable — a baseline that
exited 127 (unrunnable command) while `resolved-test-cmd.txt` is non-empty. The authoritative
contract for `run_final_tests` is this table; it supersedes any prose reading of "the `SKIP`
path" elsewhere in this issue:

| `resolved-test-cmd.txt` | `baseline-exit.txt` (after §3b normalization) | `run_final_tests` behavior |
|---|---|---|
| empty / missing | *any* | run nothing, exit 0 → `count_final` |
| non-empty | `SKIP` | run it; pass iff `FINAL_EXIT ∈ {0, 127}` |
| non-empty | a run of digits | run it; pass iff `FINAL_EXIT ∈ {0, 127}` **or** `FINAL_EXIT = BASELINE_EXIT` |

`126` is not admitted in any row (see Expected Behavior). Each of the three rows needs its own
regression test.

Why this is better than two synchronized resolutions:

1. **Both live §1e doors close** through the `SKIP` path that §3b already builds — no new CLI
   flag, no new routing edge, no `harness_exit` swap.
2. **§2's byte-identical requirement dissolves.** Baseline and final gate compare the same
   command by construction, so the ENH-2244 equality comparison is sound by construction too.
   This also subsumes the "`check_baseline_tests` gains an override it does not have today"
   fix in §2 — there is now exactly one place the override is read.
3. **One `ll-config` call per run instead of two**, which moots the `_warn_if_unknown_section`
   cost question (§1) for `general-task`.
4. **Resume/handoff composes for free** — §3b's read-side normalization already maps a
   missing/empty file to `SKIP`, so a `run_final_tests` reached without a preceding
   `check_baseline_tests` degrades safely rather than re-resolving into a different answer.

Applies to `general-task` only. The other converted loops have a single resolution site each,
so there is nothing to synchronize and they keep the plain §2 shape.

### 1b. Second bug this closes: local overrides are ignored today

All 13 inline snippets parse `.ll/ll-config.json` raw, bypassing `BRConfig`'s
`.ll/ll.local.md` merge (`config/core.py:272-276`, BUG-3123) — the mechanism
`.claude/CLAUDE.md` documents *specifically* for overriding `project.test_cmd`. Verified:

```
.ll/ll-config.json: "from-json"   .ll/ll.local.md: "from-local-md"
ll-config get   → from-local-md
inline snippet  → from-json          ← today's behavior in all 13 loops
```

A shared YAML fragment that still parsed raw JSON would have frozen this defect into a
single blessed implementation. Delegating to `ll-config` fixes it everywhere at once.

### 1c. Rejected approach: a `lib/common.yaml` fragment

Recorded so it is not re-proposed. Fragments cannot express a *substring* of a shell
action, for three independent reasons:

1. **Fragments merge whole state-level keys, not fragments of an action.**
   `resolve_fragments` deep-merges the fragment body into the state with **state keys
   winning** (`fsm/fragments.py:139-147`). Every call site embeds the snippet *inside* a
   larger action (resolve → `eval` → write artifacts); a fragment's `action:` would be
   clobbered by the state's own `action:`. There is no splice primitive.
2. **One `fragment:` key per state.** `run_final_tests` already declares
   `fragment: shell_exit` (`general-task.yaml:605`) and cannot also declare
   `resolve_test_cmd`.
3. **Some states need two resolutions.** `rl-coding-agent.yaml`'s `observe` resolves
   `test_cmd` *and* `lint_cmd` in one action; a parameterized fragment binds once per state.

### 1d. Explicitly out of scope: `oracles/code-run-gate.yaml`

Its `get_value()` convention (`:143-154`) reads the same file but is **not** convertible,
and converting it would be a regression:

- It resolves the config path from `${context.project_root}` (`:134`), whereas
  `ll-config get` resolves from `Path.cwd()` with no upward walk
  (`config/core.py:256`). Behavior would change whenever cwd ≠ project root.
- It resolves **alias pairs** (`typecheck_cmd|type_cmd`, `start_cmd|run_cmd`, per
  ARCHITECTURE-123). `ll-config get` has no alias support, and `typecheck_cmd`/`start_cmd`
  are not `ProjectConfig` fields at all.
- Its contract is deliberately *absent ≡ null ≡ skip, never guess*. Under `ll-config`,
  absent `type_cmd` resolves to the dataclass default `mypy` and absent `lint_cmd` to
  `ruff check .` — so a project that never configured them would suddenly start running
  them. Verified: `ll-config get project.type_cmd` → `mypy` on `{"project":{}}`.

Leave it as-is and register it as a documented exemption in the mirror-drift gate (§4).

### 2. Convert all call sites

| File | Line | Current shape |
|---|---|---|
| `general-task.yaml` | 37 | **buggy** — `.get('test_cmd','pytest')` |
| `general-task.yaml` | 617 | correct-but-guessing |
| `rl-coding-agent.yaml` | 60 | **buggy** — `.get('test_cmd', '${context.test_cmd}')` |
| `rl-coding-agent.yaml` | 67 | **buggy** — same shape for `lint_cmd` |
| `fix-quality-and-tests.yaml` | 66 | reference implementation |
| `evaluation-quality.yaml` | 58 | correct-but-guessing |
| `dead-code-cleanup.yaml` | 76 | correct-but-guessing |
| `harness-plan-research-implement-report.yaml` | 126 | correct-but-guessing |
| `harness-multi-item.yaml` | 95 | correct-but-guessing |
| `harness-single-shot.yaml` | 66 | correct-but-guessing |
| `test-coverage-improvement.yaml` | 45, 152 | correct-but-guessing |
| `rn-refine.yaml` | 991 | already null-safe (`or ''`) — verify semantics match, then convert |

"correct-but-guessing" = null-safe (won't emit `None`) but still overrides an explicit
`null` with a `pytest` guess. Those are not blockers, but they are the BUG-3269 behavior and
should move to `ll-config get` in the same pass. All of them additionally ignore
`.ll/ll.local.md` today (§1b).

**Precedence is NOT uniform across call sites — there is no single snippet.** `ll-config
get` knows nothing about loop context, so the ordering must be written explicitly in shell,
and the correct ordering differs per loop:

| Site | Context default | Documented precedence today | Required shell |
|---|---|---|---|
| `general-task.yaml:610-616` (`run_final_tests`) | `""` (`:23`) | context override → config → `pytest` | context-first |
| `general-task.yaml:36-40` (`check_baseline_tests`) | **no override at all** | config only | context-first (**new** — see below) |
| `test-coverage-improvement.yaml:38-48`, `:149-155` | `""` (`:23`) | context override → config → `pytest` | context-first |
| `rl-coding-agent.yaml:60,68` | **non-empty** (`:17-18`) | **config → context → default** (`:55` comment) | **config-first** |
| **all 8 remaining files** (below) | **key not declared at all** | config only | **config-first (bare)** |

**Only three loops declare a `context.test_cmd` key at all** — `general-task.yaml:23`,
`test-coverage-improvement.yaml:23`, `rl-coding-agent.yaml:17`. Verified by grep over
`scripts/little_loops/loops/*.yaml`. The other eight convert-targets
(`evaluation-quality`, `dead-code-cleanup`, `harness-plan-research-implement-report`,
`harness-multi-item`, `harness-single-shot`, `rn-refine`, `auto-refine-and-implement`,
`fix-quality-and-tests`) have **no such key**.

**Consequence — do not paste the context-first shape into those eight.** FSM actions are
interpolated in full *before* bash sees them, so `${context.test_cmd}` against an undeclared
key raises at interpolation time, turning a mechanical conversion into a hard loop breakage.

**Corrected failure mode (the original citation here was wrong).** It is **not** the
"expected namespace.path" error — that branch (`fsm/interpolation.py:261-264`) fires only for
a reference containing **no dot** (bare `${foo}`). `${context.test_cmd}` has a dot, so it
resolves the namespace fine and then dies one level deeper, in
`InterpolationContext._get_nested` (`fsm/interpolation.py:138-140`):

```
InterpolationError: Path 'test_cmd' not found in context
```

That is the string to grep for when a converted loop breaks. The guidance below is unchanged
— only the diagnostic was misidentified. Two acceptable shapes there:

- **Config-first (bare, preferred)** — matches those loops' documented behavior today
  ("Reads test_cmd from `.ll/ll-config.json`; falls back to 'pytest' if absent"), adds no
  new surface:

  ```bash
  CMD=$(ll-config get project.test_cmd)
  ```

- If a loop genuinely should gain an override, **declare the context key first**
  (`test_cmd: ""` in its `context:` block) and then use the context-first shape. Do not rely
  on `${context.test_cmd:default=}` as a substitute for declaring it — an undeclared key with
  a `:default=` guard silently hides the fact that the override is unreachable by any caller.

This is the single highest-risk axis in Step 5: eight of the eleven files need the
**opposite** shape from the two worked examples in this issue.

Context-first sites:

```bash
if [ -n "${context.test_cmd}" ]; then
  CMD="${context.test_cmd}"
else
  CMD=$(ll-config get project.test_cmd)
fi
```

In `general-task` this shape appears **once**, in `check_baseline_tests`, per §3c —
`run_final_tests` reads `resolved-test-cmd.txt` rather than repeating it.

**The context-first shape is wrong for `rl-coding-agent.yaml` and must not be pasted
there.** Its context defaults are non-empty literals (`test_cmd: "python -m pytest"`,
`lint_cmd: "ruff check"`, `:17-18`), so `[ -n "${context.test_cmd}" ]` is *always* true,
`ll-config get` would never execute, and the two buggy sites would silently stop reading
`project.test_cmd` altogether — trading an emitted `None` for a total loss of project
configuration. Use config-first there:

```bash
CMD=$(ll-config get project.test_cmd)
[ -z "$CMD" ] && SKIP_TESTS=1   # explicit null → opt out of test scoring
```

**Decision required before implementation (rl-coding-agent only).** `ll-config get` collapses
absent and null into "empty vs the field default", so config-first cannot fall back to the
context override on *absent* — absent resolves to `pytest` / `ruff check .` from
`ProjectConfig`, and the `${context.test_cmd}` / `${context.lint_cmd}` defaults at `:17-18`
become dead. Two options: **(a)** accept that, delete the two context defaults, and document
`ProjectConfig`'s field defaults as the only fallback (recommended — one authority, matches
§1); or **(b)** keep the overrides by testing them separately with a second probe. Pick (a)
unless a consumer is known to rely on those context values.

Behavior change for `rl-coding-agent.yaml` under option (a): with the key **absent** it
resolves to `pytest` / `ruff check .` rather than the context literal; with the key
**present and null** it now skips test/lint scoring instead of scoring against
`command not found`.

**`check_baseline_tests` gains an override it does not have today.** `general-task.yaml:37`
reads config directly with no `${context.test_cmd}` check, while `run_final_tests:610-616`
checks the override first. That is a *second* divergence axis inside the same file, distinct
from the null-handling one: with `context.test_cmd` set, the baseline and the final gate
resolve to different commands, and the ENH-2244 equality comparison then compares two
different test suites. Converting only the null semantics leaves this intact.

~~Both states must end up with byte-identical resolution shell.~~ **Superseded by §3c.**
"Keep two copies byte-identical" is an unenforced synchronization invariant — the copies
drift the moment one is edited, which is precisely this issue's defect reintroduced one
level up. Instead `check_baseline_tests` resolves once (using the context-first shape above)
and writes `resolved-test-cmd.txt`; `run_final_tests` reads that file and does not resolve at
all. The divergence is then impossible by construction rather than by convention.

### 2b. Empty-`CMD` contract for the "correct-but-guessing" sites — REQUIRED, per site

The Proposed Solution specifies opt-out behavior precisely for `general-task` (the `SKIP`
sentinel, §3) and `rl-coding-agent` (skip test/lint scoring, §2). It says nothing for the
other sites beyond "convert" — but conversion **changes their behavior under `test_cmd: null`**
and the change is not uniform. Every one of them has the shape:

```bash
set -o pipefail
eval "$CMD" 2>&1 | tee ${context.run_dir}/<artifact>.txt
```

under `fragment: shell_exit`, i.e. gated on the action's exit code. With `CMD=""`,
`eval ""` exits **0** and the gate silently **passes** against an empty artifact.

Today those sites resolve `test_cmd: null` to `pytest` and gate on its real exit code. After
conversion they gate on nothing. That is the intended semantic of an opt-out — but it is a
per-site safety decision, not a mechanical edit:

| Site | `on_yes` | Effect of pass-on-empty | Decision |
|---|---|---|---|
| `fix-quality-and-tests.yaml:58-78` | `done` | Already the behavior today — its three-way body prints `true` (a real command, exits 0) on present-and-null. **This is the reference semantic.** | pass-on-empty; drop-in |
| `harness-single-shot.yaml:61-72` | `check_semantic` | Falls through to the LLM quality gate, which still runs | pass-on-empty |
| `harness-plan-research-implement-report.yaml:121-132` | `check_semantic` | Same — LLM gate still runs | pass-on-empty |
| `harness-multi-item.yaml:90-100` | `check_mcp` | Same — MCP gate still runs | pass-on-empty |
| `evaluation-quality.yaml:50-66` | **none — `next: score`, ungated** (see correction below) | `capture: code_results` captures an **empty** results file; the scorer then scores a rollout against nothing. Not a crash, a **silently meaningless score** — the same failure mode §"Current Behavior" describes for `rl-coding-agent`'s reward | **explicit skip required**: branch on `[ -z "$CMD" ]` and record "no test signal" rather than an empty capture |
| `test-coverage-improvement.yaml:148-158` | `commit` | Commits coverage work with no test verification | **explicit skip required** or route away from `commit` |
| `dead-code-cleanup.yaml:71-81` | `commit` / `on_no: revert_and_scan` | **Auto-commits dead-code deletions with zero verification.** Today `pytest` exits non-zero in exactly the project shape this bug was found in (docs project, no suite) → `revert_and_scan`. After conversion → `commit`. This is the sharpest behavior change in the whole issue and it is a *deletion* path | **explicit skip required**: `[ -z "$CMD" ]` must route to a non-committing edge, not pass |
| `rn-refine.yaml:988-994` | advisory only | Already branches on `[ -z "$TEST_CMD" ]`; no gate | drop-in (see §3) |
| `auto-refine-and-implement.yaml:433-436` | `emit('skipped')` | Already treats falsy `test_cmd` as skipped | drop-in |

**Rule for Step 5:** a site whose `on_yes` edge performs an irreversible action (`commit`) or
feeds a score must handle `[ -z "$CMD" ]` explicitly. A site whose `on_yes` edge leads to
another gate may pass on empty. Do not convert any of the nine without picking a row.

**Correction — `evaluation-quality.yaml`'s `evaluate_code` has no gate at all.** The row above
originally read "`on_yes`: `score` (via `next:`)", which implies an exit-code gate that does
not exist. Verified against the current file (`:50-66`): the state is `action_type: shell`
with `capture: code_results` and `next: score`, and has **no `evaluate:` block and no
`on_yes`/`on_no` edges**. Its exit code is not consulted by anything. The *decision* for the
row is unchanged — the risk is the empty capture feeding the scorer, not a lost gate — but an
implementer must not go looking for an `on_yes` edge to reroute. The skip must be expressed
by writing an explicit "no test signal" marker into `eval-test-results.txt` (which `capture:`
reads), not by changing routing.

**Second correction — the same state's hardcoded lint is already non-gating, and converting
it changes scope, not just source.** `evaluation-quality.yaml:64` is
`ruff check scripts/ 2>&1 | tee ... || true` — the `|| true` means it never affected control
flow even before this issue. Converting it to `ll-config get project.lint_cmd` (§4) is still
correct, but note the resolved value in a project that never set `lint_cmd` is
`ruff check .` — a **broader lint scope** than the hardcoded `scripts/`. That is the intended
direction (the loop should lint what the project says to lint), but it is a behavior change
for this repo specifically and belongs in Impact rather than being discovered at runtime.

**Correction to the wiring pass:** `auto-refine-and-implement.yaml:679-680` is **not** a call
site and needs no conversion. It reads `cfg.project.test_cmd` / `cfg.project.lint_cmd` off a
real `BRConfig` instance inside an embedded Python block (the same block calls
`cfg.get_worktree_base()`), so it already resolves through `ProjectConfig` **and** honors
`.ll/ll.local.md`. Only `:433-436` — the raw `json.loads(Path('.ll/ll-config.json'))` read —
is in scope in that file.

### 3. Baseline sentinel in `general-task`

`check_baseline_tests` writes `SKIP` instead of an exit code when the baseline is
unrunnable; `run_final_tests` branches on `SKIP` before its numeric comparison. With
`ll-config get`, the opt-out signal is an **empty string**, tested with `[ -z "$CMD" ]` —
not a `SKIP` command string that could collide with a real command. `SKIP` remains the
sentinel written to `baseline-exit.txt`, where it cannot collide with an exit code.

This also removes the `rn-refine.yaml:988-994` conversion caveat: that site already
branches on `[ -z "$TEST_CMD" ]`, so it becomes a drop-in.

### 3b. The sentinel must be the *reader's* default, not a value the writer must get right

**A residual spin path that the `SKIP` contract as originally written does not close.**
`general-task.yaml:623` reads the baseline as:

```bash
BASELINE_EXIT=$(cat "${context.run_dir}/baseline-exit.txt" 2>/dev/null || echo "0")
```

The `|| echo "0"` covers a **missing** file only. If the file **exists but is empty** — the
`echo $?` at `:39` never ran because `check_baseline_tests` was killed mid-action, the disk
filled, or `on_error: define_done` (`:43`) fired after the shell redirect had already created
the file — then `cat` *succeeds* with empty output, `BASELINE_EXIT` is `""`, the comparison
`[ "$FINAL_EXIT" = "" ]` is false, and the run enters the exact BUG-3269 cycle **with a
perfectly valid `test_cmd`**. Branching on the literal string `SKIP` does not help: nothing
wrote `SKIP` in that scenario, because nothing wrote anything.

**Required: normalize on read.** Anything that is not a run of digits becomes `SKIP`, which
makes the safe interpretation the default rather than something the writer has to remember:

```bash
BASELINE_EXIT=$(cat "${context.run_dir}/baseline-exit.txt" 2>/dev/null || echo "")
case "$BASELINE_EXIT" in ''|*[!0-9]*) BASELINE_EXIT=SKIP ;; esac
```

One line, and it subsumes missing, empty, truncated, and garbage in addition to the explicit
`SKIP` written by `check_baseline_tests`. Note this replaces the `|| echo "0"` fallback: see
the behavior change below.

**Behavior change — a missing baseline stops meaning "require final == 0".** Today the
`|| echo "0"` fallback makes an absent baseline resolve to `0`, i.e. the *strictest possible*
gate applied on the *least* information. Under the normalization above it resolves to `SKIP`,
i.e. pass on `FINAL_EXIT` in `{0, 127}`. This is deliberate and is the same argument as the
rest of §3 — a baseline that never ran must never be compared against — but it is a real
loosening for the missing-file case and belongs in Impact.

**Also harden the writer.** `check_baseline_tests` keeps `on_error: define_done`, which is
the silent-swallow that let the garbage `127` through in the first place. Have its error path
write `SKIP` to `baseline-exit.txt` explicitly rather than leaving whatever the file happens
to contain. That is redundant with the reader-side normalization by design — the whole class
of defect here is a garbage value being trusted, and it is worth closing on both ends.

### 4. Mirror-drift gate (regression test)

Delegating to a CLI alone does not stop the fourteenth copy — nothing forces a new loop to
use it. Because there is now a single canonical call, the gate becomes **static** rather
than snippet-extracting-and-executing:

- Scan every `scripts/little_loops/loops/**/*.yaml`; assert none contains an inline
  `.ll/ll-config.json` read for a project command key outside an explicit exemption list.
- **Cover all `ProjectConfig` command fields, not just `test_cmd`/`lint_cmd`.** The defect
  shape is `.get(key, default)` against a raw JSON parse; it is not specific to the two keys
  that happen to be buggy today. Gate the full set from `config/core.py:188-195`:
  `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`, `build_cmd`, `run_cmd`. A gate scoped to
  two keys lets the fourteenth copy land tomorrow against `type_cmd` and calls it clean.
- **Semantic trap the six-key gate invites — document it in the §6 guide text.** The
  three-way contract in Expected Behavior holds only for keys whose `ProjectConfig` field
  default is non-`None`. `build_cmd` and `run_cmd` both default to `None`
  (`config/core.py:194-195`), so for those two `ll-config get` collapses **absent ≡ null ≡
  empty** — two-way, not three-way, and there is no "not configured yet" guess to fall back
  on. No current call site reads them, but a gate that names all six keys is an invitation to
  convert one, and a future author would reasonably assume the table applies. State in
  `HARNESS_OPTIMIZATION_GUIDE.md` that the absent-vs-null distinction exists only for
  `test_cmd`, `lint_cmd`, `type_cmd`, and `format_cmd`.
- **Match on the `get('<key>'` / `["<key>"]` access pattern, not on the literal string
  `.ll/ll-config.json`.** Several files mention that path in *prose comments*
  (`general-task.yaml:618`, `harness-multi-item.yaml:88`,
  `harness-plan-research-implement-report.yaml:120`, `harness-single-shot.yaml:58`) — a
  path-substring gate would false-positive on all of them. Those comments are stale after
  conversion and must be rewritten in the same pass regardless, but the gate must not depend
  on that having happened.
- **Also gate hardcoded project commands.** `evaluation-quality.yaml:64` runs a literal
  `ruff check scripts/` — a project lint command inlined with no config read at all, sitting
  two lines below a site this issue converts. No config-read gate would ever see it. Convert
  it to `ll-config get project.lint_cmd` in the same pass (it is the same bug, pre-inlined),
  and decide whether the gate should flag bare `ruff check` / `mypy` / `pytest` literals in
  loop actions or whether that is too noisy to enforce. If too noisy, say so here rather than
  leaving it silently uncovered.
- **Exemption list — two kinds, kept distinct.**
  - *Permanent*: `oracles/code-run-gate.yaml`, with the §1d rationale as a comment.
  - *Temporary (`_PENDING_CONVERSION`)*: the ten sites deferred to ENH-3277 (see
    **Deferred to follow-up**). The gate lands **now**, red-listing them explicitly, so the
    fourteenth copy cannot land while the follow-up is open. The follow-up's definition of
    done is that this list is empty and the constant is deleted. A gate that is permanently
    red on ten known sites cannot be enforced; an exemption list that shrinks to zero can.
- Pair it with behavioral tests on `ll-config get` itself (Implementation Step 1), which
  are ordinary Python tests rather than bash-extraction gymnastics.

**Second assertion — undeclared `${context.<key>}` references. This is the gate that covers
the risk §2 calls "the single highest-risk axis", and nothing covers it today.**

§2 establishes that eight of eleven files need the **opposite** precedence shape, and that
pasting `${context.test_cmd}` into a loop that does not declare the key raises
`InterpolationError: Path 'test_cmd' not found in context` — at **runtime**, potentially deep
into a run. The mirror-drift gate as specified above scans for *inline JSON reads*, so it
would pass a file converted wrong in exactly this way.

**Verified: there is no static validation of undeclared context keys.**
`fsm/validation/shell_safety.py`'s MR-7 (`_validate_bash_default_interpolation`) catches only
the unsupported bash `${ns.path:-value}` form; nothing walks `${context.*}` references against
the loop's declared `context:` block. Grep over `fsm/validation/` confirms no such rule exists.

Add it as a second assertion in the same test module: **every `${context.<key>}` reference in
any `scripts/little_loops/loops/**/*.yaml` must resolve against that loop's declared
`context:` block.** Cheap, catches the named risk before a run rather than during one, and is
generally valuable well beyond this issue. Scope is small — only four loops declare
`test_cmd`/`lint_cmd` today (`general-task.yaml:23`, `incremental-refactor.yaml:12`,
`rl-coding-agent.yaml:17-18`, `test-coverage-improvement.yaml:23`), verified by grep.

Note this assertion must tolerate the engine-native `${context.x:default=y}` form (strip the
`:default=` suffix before resolving the key) and the escaped `$${...}` shell form.

This is strictly stronger than the originally-proposed execute-each-snippet gate: it also
catches the `ll.local.md` bypass, which an execute-the-snippet check cannot see.

Follow the registry-parametrize pattern from `scripts/tests/test_wiring_skills_and_commands.py:376-424`
(a `GATED_*` constant plus `@pytest.mark.parametrize`) — see the correction in Codebase
Research Findings; commit `fb747a60`'s pattern lives there, not in `test_builtin_loops.py`.

## Integration Map

### Files to Modify

_Revised: no `lib/common.yaml` fragment is added. `ll-config get`'s **resolution** already
behaves correctly and is not changed; the only production-code edit is §1e's stderr warning
(below). Everything else is loop YAMLs plus tests/docs._

> **SCOPE FILTER (fourth pass).** Only the first three loop-YAML entries below —
> `general-task.yaml` and `rl-coding-agent.yaml` — are in scope for BUG-3269. Every other
> loop file in this list, and the corresponding entries under *Wiring Phase*, moved to the
> follow-up issue; see **Deferred to follow-up**. They are retained here unedited because the
> per-file analysis is the follow-up's input, not because this issue touches them.

- `scripts/little_loops/cli/config.py:69-73` — split the single `except Exception` into
  construction and resolution blocks; warn on stderr when `BRConfig(Path.cwd())` itself
  raises (§1e, Step 3a). Stdout and the always-0 exit contract are unchanged. **No
  `--strict` flag** — withdrawn, see §1e/§1f. Optionally also short-circuit
  `_warn_if_unknown_section` (`:77-78`) when the root segment is already in `cfg.to_dict()`,
  so the opt-out path stops paying for `_load_schema()` (§1 cost caveat)

- `scripts/little_loops/loops/general-task.yaml:37` — **buggy site** (`check_baseline_tests`)
- `scripts/little_loops/loops/general-task.yaml:617` — `run_final_tests`; also add `SKIP` handling
- `scripts/little_loops/loops/rl-coding-agent.yaml:60,68` — **buggy sites** (`test_cmd` + `lint_cmd`)
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:58-78` — reference impl; the
  three-way python body is deleted outright
- `scripts/little_loops/loops/evaluation-quality.yaml:58`
- `scripts/little_loops/loops/dead-code-cleanup.yaml:76`
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:126`
- `scripts/little_loops/loops/harness-multi-item.yaml:95`
- `scripts/little_loops/loops/harness-single-shot.yaml:66`
- `scripts/little_loops/loops/test-coverage-improvement.yaml:45,152`
- `scripts/little_loops/loops/rn-refine.yaml:991` — verify semantics before converting

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:433-436,679-680` — a **13th
  call site** not enumerated in the original ~12-site table: `test_cmd = project.get('test_cmd')`
  / `lint_cmd = project.get('lint_cmd')` / `if not test_cmd:` in its own post-implementation
  verify pass. Not currently buggy — it already treats a falsy `test_cmd` as "skipped" (comment
  `:375-376`) — but is in scope for the Proposed Solution's "convert all call sites" mandate for
  consistency with the shared fragment. [Agent 1 finding]

### Dependent Files (Callers/Importers)
- ~~`scripts/little_loops/fsm/` — fragment resolution~~ — **no longer touched**; no fragment
  is added, so no executor or `${param.x}` binding concern
- `scripts/little_loops/config/core.py` — `ProjectConfig` field defaults (`:188-195`) become
  the single authority for absent-key defaults; `resolve_variable` (`:1044-1060`) is the
  null→opt-out path. Read-only for this issue, but pinned by Step 1's tests
- Any consuming project's `.ll/ll-config.json` and `.ll/ll.local.md` supplying
  `project.test_cmd` / `project.lint_cmd`

_Wiring pass added by `/ll:wire-issue` — partly superseded by the design review:_
- ~~`scripts/little_loops/cli/loop/info.py` — `cmd_fragments` listing~~ — **not applicable**;
  no new fragment to surface
- ~~ENH-2858 — in-flight sibling plans a `baseline-ref.txt` capture inside
  `check_baseline_tests`; sequencing risk~~ — **stale, resolved.** That
  capture has already landed: `general-task.yaml:39` is
  `git rev-parse HEAD > "${context.run_dir}/baseline-ref.txt" ...`. No sequencing risk
  remains; just preserve that line when rewriting the action. [Agent 2 finding, superseded]

### Similar Patterns
- ~~`lib/common.yaml:15` `shell_exit` / `:38` `retry_counter` — fragment `parameters:`
  convention~~ — **not the model**; see Proposed Solution §1c for why fragments cannot
  express this fix
- `scripts/little_loops/loops/incremental-refactor.yaml:12,33` — **DECIDED 2026-08-20: out of
  scope for BUG-3269; split to its own issue (BUG-3276).** It declares
  `test_cmd: "python -m pytest scripts/tests/"` as a context default (`:12`) and runs it bare
  at `verify_tests` (`:31-36`, `action: "${context.test_cmd}"`, exit-code gated,
  `on_no: revert`). In any consuming project that path does not exist, so the command fails
  every lap and the loop **reverts each refactoring step** — destructive, not merely
  ineffective. Real defect, but deliberately not this issue's:
  - **Different mechanism.** It performs no config read, so the §4 mirror-drift gate does not
    cover it whether or not this issue converts it.
  - **It needs its own §2b-style safety analysis** on a *revert* edge — the same class of
    judgment as `dead-code-cleanup`'s commit edge, and not something to append to a list of
    nine as a mechanical edit.
  - **Independently shippable**, and bundling it delays a P0 spin fix behind an unrelated
    destructive-default fix.

  The line against `evaluation-quality.yaml:64` (which this issue **does** convert) is
  **proximity, not principle**: that literal sits two lines below a site already being
  rewritten in the same state, so converting it is nearly free and leaving it would be
  conspicuous. `incremental-refactor.yaml` has no other reason to be opened in this pass.

### Tests
- New: mirror-drift gate parametrized over every `scripts/little_loops/loops/**/*.yaml`
  (see Proposed Solution §4), covering all six `ProjectConfig` command keys
- New: per-site regression tests for the three `[ -z "$CMD" ]` branches required by §2b —
  in particular `dead-code-cleanup.yaml` must not reach `commit` under `test_cmd: null`
- New: `ll-config get` malformed-config test (§1e)
- `scripts/tests/test_builtin_loops.py` — existing built-in-loop validation; the new gate
  belongs alongside it
- Pattern reference: commit `fb747a60` (`test(adapters): parametrize mirror-drift gate over
  _EMITTER_MAP hosts`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py` — **assertions will break, but the structural
  problem the wiring pass flagged does not arise.** Because no fragment is introduced, the
  `raw_data` fixture (`:26-31`) and `_load_state_script()` (`:439-443`) keep working as-is —
  no `resolve_fragments`/`load_and_validate` rewrite is needed.
  `TestENH2225FinalOnlyGate.test_run_final_tests_resolves_test_cmd` (`:1430-1435`) asserts
  the literal substrings `${context.test_cmd}` / `ll-config.json` / `pytest`; after
  conversion `${context.test_cmd}` survives (override precedence is preserved) but
  `ll-config.json` and `pytest` do not — retarget at `ll-config get project.test_cmd`.
  Same for `TestRunFinalTestsShellAction` (`:1447-1484`), including
  `test_falls_back_to_config_test_cmd` (`:1477-1484`). [Agent 2 finding, revised]
- `scripts/tests/test_builtin_loops.py::TestGeneralTaskLoop` — `data` fixture (`:14650-14653`)
  has the same raw-YAML bypass backing `test_check_baseline_tests_writes_baseline_exit_to_run_dir`
  (`:14679-14685`), `test_run_final_tests_reads_baseline_exit` (`:14727-14733`), and
  `test_run_final_tests_compares_final_to_baseline` (`:14735-14744`). Lower risk than the
  file above — the `BASELINE_EXIT`/`FINAL_EXIT` substrings likely survive since that
  comparison logic stays inline — but verify after conversion. [Agent 2 finding]
- ~~`scripts/tests/test_fsm_fragments.py`~~ — **drops out entirely.** No fragment is added,
  so `migration_targets` (`:992`) needs no extension and `TestWithRateLimitHandling` /
  `TestWithThrottleFragment` (`:615-781`) are not a pattern to copy. [Agent 1 + Agent 3
  findings, superseded]
- `scripts/tests/test_builtin_loops.py::TestVerifyStateConfigReadShell` (`:4938-5038`) — the
  closest existing shell-execution end-to-end pattern (writes a real `.ll/ll-config.json`,
  extracts the resolved action, runs it via `subprocess.run(["bash", "-c", ...])`). Its
  `test_cmd=None` case covers only the key-**absent** path — Step 1's tests must add the
  key-**present-with-JSON-`null`** case explicitly, since that is the axis this bug is on.
  [Agent 3 finding]
- `scripts/tests/` — locate the existing `ll-config` CLI tests (if any) and extend them
  rather than starting a new module; Step 1's contract tests belong with them.
- `scripts/tests/test_builtin_loops.py::TestCodeRunGateOptionalParams` (`~12270-12520`) —
  already exercises the "key present, value JSON null" scenario for `code-run-gate.yaml`
  (`commands.json` with `"test_cmd": null`); use as the reference for closing this gap
  elsewhere. [Agent 3 finding]

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document the fragment as the required way to
  resolve a project command inside a loop
- `scripts/little_loops/config-schema.json` — confirm `project.test_cmd` documents `null` as
  the explicit opt-out, not merely "unset"

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — documents `baseline-exit.txt` (`:105`) and
  `project.test_cmd`/`lint_cmd` (`:979`, `:1305`, `:1327`); needs updating for the `SKIP`
  sentinel and the corrected absent/null/value semantics [Agent 1 finding]
- `scripts/little_loops/loops/README.md:33` — describes `auto-refine-and-implement`'s own
  `test_cmd`/`lint_cmd` row [Agent 1 finding]
- `docs/reference/loops.md:829-833` — documents `code-run-gate.yaml`'s distinct `get_value()`
  resolution convention ("null skips run_test/run_build/run_lint"); review wording if that
  file converts to the shared fragment in this pass, since its `null_value` semantics differ
  from emitting a sentinel/no-op command [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:298-310,1846-1850` — `project.test_cmd` config table
  doesn't currently distinguish absent-vs-null; candidate for a clarifying note alongside the
  `config-schema.json` update [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` → `project.test_cmd` — the key whose present-vs-absent-vs-null
  semantics this issue defines

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Newly discovered site — now scoped OUT of conversion by the design review; see Proposed
  Solution §1d. It gets a mirror-drift-gate exemption, not a rewrite.**
  `scripts/little_loops/loops/oracles/code-run-gate.yaml:143-154` implements a *fifth*, distinct resolution convention — a `get_value()` bash function that treats an absent key and an explicit `null` identically (both print nothing, no `pytest` guess), feeding a `resolve_commands` state whose per-command consumers (`run_build`, etc.) self-skip and can emit `GATE_SKIP` (`:108-122`, comment `:114-115`, `:192-193`). This file should be added to the mirror-drift gate's coverage (Proposed Solution §4) and considered for conversion in the same pass, since the gate as specified ("every `scripts/little_loops/loops/**/*.yaml`") already covers it.
- ~~**No existing shared Python helper to delegate to**~~ — **RETRACTED 2026-08-20 by design
  review; this finding was wrong and drove the rejected fragment design.** The research pass
  examined `ProjectConfig` (`scripts/little_loops/config/core.py:184-230`, `test_cmd` field
  `:191`, populated via `data.get("test_cmd", "pytest")` at `:215`) and its consumer
  `verify_epic_branch_before_merge` (`scripts/little_loops/worktree_utils.py:480-609`), but
  never checked for a **CLI wrapper**. `ll-config get` (`scripts/little_loops/cli/config.py`,
  entry point `scripts/pyproject.toml:100`) exposes exactly this resolution to shell and
  implements the required three-way semantics correctly today — verified empirically for both
  `test_cmd` and `lint_cmd`. See Proposed Solution §1. The still-valid part of the original
  finding: `ProjectConfig.test_cmd` is annotated `str` while holding `None` on the opt-out
  path, which is load-bearing and must be pinned by a test (Implementation Step 5).

## Program Design

### Signatures

- `main_config() -> int` — **existing** CLI entry point (`cli/config.py:54`), invoked from
  shell as `ll-config get project.test_cmd`; the single resolution path replacing the
  hand-rolled inline snippets. **Takes no parameters** — the key arrives as `args.key` from
  `parser.parse_args()` inside the function (`:63`), not as an argument. (An earlier revision
  wrote `main_config(key: str) -> int`, which does not exist.) Signature is unchanged by this issue — no
  `--strict` parameter is added (§1e/§1f). Prints the value, the absent-default, or nothing
  (opt-out) on stdout, always returns 0, and gains only a stderr warning when
  `BRConfig(Path.cwd())` construction raises.
- `resolve_variable(var_path: str) -> str` — **existing** (`config/core.py:1044`); returns
  `None` for a present-and-null key, which is the load-bearing opt-out signal.
- `check_baseline_tests(test_cmd: str) -> str` — writes the returned value to
  `baseline-exit.txt`; return type widens from a numeric exit-code string to that plus the
  new no-runnable-baseline sentinel `SKIP`.
- `run_final_tests(baseline_exit: str, final_exit: int) -> bool` — gates on `final_exit`
  alone when `baseline_exit` is `SKIP`, on the ENH-2244 equality comparison otherwise; in
  both cases `final_exit` values `0` and `127` pass unconditionally, and `126` does not.

No fragment, no `parameters:` block, no executor change. The `config_key` /
`absent_default` / `null_value` parameters from the original design are all subsumed: the
key is the dot-path argument, and the absent-default comes from `ProjectConfig`'s field
defaults (`config/core.py:188-195`), which is where a project-command default *should*
live — one authority instead of a per-call-site literal.

### Call Path

- `check_baseline_tests` → `ll-config get project.test_cmd` — the **only** resolution in
  `general-task` (§3c); writes `resolved-test-cmd.txt` and `baseline-exit.txt`. Currently
  the buggy site at `general-task.yaml:37`.
- `check_baseline_tests` → `define_done` → `plan` → … → `final_verify` → `run_final_tests`
  — the poisoned `baseline-exit.txt` travels this far before anything reads it.
- `run_final_tests` → reads `resolved-test-cmd.txt` + `baseline-exit.txt` — **no second
  `ll-config` call** (§3c); branches on `SKIP` before the numeric comparison.
- `run_final_tests` → `count_final` — the opt-out path; taken directly, running nothing,
  when the key is explicitly null.
- `run_final_tests` → `continue_work` — the gate-failed edge; the entry point of the
  infinite cycle when the baseline is garbage.
- `observe` → `ll-config get project.test_cmd` + `ll-config get project.lint_cmd` (in
  `rl-coding-agent.yaml`) — the second and third buggy sites; the result feeds `TEST_SCORE`
  in the composite reward. Two calls in one state, which the rejected fragment design could
  not express.
- Inside `ll-config get`: `main_config` (`cli/config.py:54`) → `BRConfig(Path.cwd())` →
  `_load_config` (deep-merges `.ll/ll.local.md` frontmatter, `:265-280`) →
  `ProjectConfig.from_dict` (`:208`) → `resolve_variable` (`:1044-1060`) → `print` only
  when non-`None` (`:75-76`).

### Resolution contract

**Resolution order at each call site** (shell, two lines):

1. Non-empty `${context.<key>}` shell-level override → use it verbatim.
2. Otherwise `ll-config get project.<key>`, which internally distinguishes:
   - config file missing, or `project` absent, or key absent → the `ProjectConfig` field
     default (`pytest` / `ruff check .`);
   - key present and `null` → empty output (opt-out);
   - key present and truthy → its value.
3. Empty result → skip; the state must not run or gate on anything.

**Precondition — cwd must be the project root.** `main_config` constructs
`BRConfig(Path.cwd())` (`cli/config.py:71`) and `resolve_config_path` (`config/core.py:157`)
is a flat candidate probe with **no upward walk**. From a subdirectory of a project with
`test_cmd: null`, the opt-out silently degrades to the absent-default — verified:

```
$ cd <proj>/sub/deep && ll-config get project.test_cmd
pytest          # ← opt-out lost, no error, exit 0
```

This is **not a regression** — the 13 inline snippets open the relative path
`.ll/ll-config.json` and fall back identically — but converting does not fix it either, and
it must be stated rather than assumed away. FSM shell actions run at
`FSMExecutor.working_dir` (`fsm/executor.py:2482`), which is the project root for ordinary
runs and the worktree root (which carries its own checked-in `.ll/`) for worktree-isolated
runs, so every converted site is safe today. Note this also means §1d's first exemption
bullet for `oracles/code-run-gate.yaml` (`${context.project_root}` vs `Path.cwd()`) argues a
difference that the other 13 sites never relied on; the alias-pair and never-guess bullets
are the load-bearing reasons for that exemption.

`ll-config get` never raises and always exits 0, so no call site needs `|| true` or a
`try/except`. Note that per BUG-3274's family, resolution is **whole-dataclass**: an
unrelated malformed key in `project` does not silently poison this read, but a future
coercion of `ProjectConfig.test_cmd`'s `None` to satisfy its `str` annotation would.

**Not needed:** the `fix-quality-and-tests.yaml:66-72` three-way python body. It stays the
reference for *what the semantics are*, but it is deleted rather than generalized — the
semantics now live in `ProjectConfig` + `resolve_variable`.

**`general-task.yaml` — baseline sentinel contract**

- `check_baseline_tests` writes `baseline-exit.txt` = `SKIP` when the resolved command is
  the opt-out sentinel, **or** `ll-config` itself was not found (`$?` = 127 from the
  substitution — testable here and only here, §1f), **or** the command exits `127`, **or**
  `baseline-test-output.txt` matches `command not found`. Otherwise it writes the numeric
  exit code as today. Its `on_error` path writes `SKIP` explicitly rather than leaving the
  file as-is (§3b). It also writes `resolved-test-cmd.txt` for `run_final_tests` (§3c).
- `run_final_tests` **normalizes before branching**: any `baseline-exit.txt` content that is
  not a run of digits — missing, empty, truncated, garbage, or the literal `SKIP` — is
  treated as `SKIP` (§3b). The old `|| echo "0"` fallback is removed; it made a missing
  baseline mean "require `FINAL_EXIT = 0`".
- `run_final_tests` then branches **before** its numeric comparison: `SKIP` → pass when
  `[ "$FINAL_EXIT" = "0" ] || [ "$FINAL_EXIT" = "127" ]`, never on equality with the
  baseline. This preserves the ENH-2244 comparison for every run that has a real baseline,
  and prevents a present-but-unrunnable `test_cmd` from reproducing the BUG-3269 cycle (see
  Expected Behavior).
- On the **numeric**-baseline branch, the comparison becomes
  `[ "$FINAL_EXIT" = "0" ] || [ "$FINAL_EXIT" = "127" ] || [ "$FINAL_EXIT" = "$BASELINE_EXIT" ]`
  — the `127` arm is the same "an unrunnable command never gates" rule, applied to the case
  where the baseline *did* run and the final command could not (see Expected Behavior). `126`
  is not admitted on either branch, by design.
- Under the opt-out, `run_final_tests` routes straight to `count_final` without running
  anything.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Confirmed current anchors (line numbers below reflect the file as it stands today; the issue's original citations have drifted)**:
  - `scripts/little_loops/loops/general-task.yaml:37` — **buggy site**, `check_baseline_tests` (state header `:35`): `print(cfg.get('project',{}).get('test_cmd','pytest'))` — emits literal `None` on present-but-null.
  - `scripts/little_loops/loops/general-task.yaml:613-620` (state header `run_final_tests` `:596`) — the correct-but-guessing sibling: `raw = cfg.get('project', {}).get('test_cmd')` / `print(raw if raw else 'pytest')`. Within this one file the two sites already disagree with each other.
  - `scripts/little_loops/loops/rl-coding-agent.yaml:60` (`test_cmd`) and `:68` (`lint_cmd`) — both **buggy sites**, state `observe` (header `:53`): `print(cfg.get('project', {}).get('<key>', '${context.<key>}'))`.
  - `scripts/little_loops/loops/fix-quality-and-tests.yaml:58-78` — reference implementation, state `check-tests`. `raw = cfg.get('project', {}).get('test_cmd')` at `:66`; three-way branch (`'project' in cfg and 'test_cmd' in cfg['project']` → `raw if raw else 'true'`, else `raw if raw else 'pytest'`) at `:69-72`.
  - Correct-but-guessing sites confirmed at current lines: `evaluation-quality.yaml:58` (raw, snippet `55-61`); `dead-code-cleanup.yaml:76` (snippet `73-79`); `harness-plan-research-implement-report.yaml:126` (snippet `122-129`); `harness-multi-item.yaml:95` (snippet `91-98`); `harness-single-shot.yaml:66` (snippet `63-69`); `test-coverage-improvement.yaml` two sites — `38-48` (override-guarded, raw at `45`) and `149-155` (raw at `152`).
  - `rn-refine.yaml:988-994` is a **distinct third fallback convention**, not the raw/if-else idiom: `print(cfg.get('project', {}).get('test_cmd') or '')` wrapped in `try/except`, degrading to `''` (not `'pytest'`) on any error. Converting this site must account for a different downstream contract than the other sites.
- **Fragment mechanism** (`scripts/little_loops/loops/lib/common.yaml`): top-level key is `fragments:` (`:14`); a fragment supplies state-level keys merged into the caller. Parameterized fragments declare `parameters:` (each entry has `type` + `required` or `default`) and are referenced via `${param.<name>}` inside the fragment body; the caller supplies values via a `with:` block at the `fragment: <name>` call site. Reference example: `retry_counter` (`lib/common.yaml:38-60`) — `counter_key` (required string) and `max_retries` (default 3). Unparameterized fragments (`shell_exit`, etc.) take no `with:` block. Resolution is implemented in `scripts/little_loops/fsm/fragments.py` (`resolve_fragments`, imported at `scripts/tests/test_builtin_loops.py:18`).
- **Call path, `baseline-exit.txt`**: `check_baseline_tests` (`:35-43`) writes `${context.run_dir}/baseline-test-output.txt` and `${context.run_dir}/baseline-exit.txt` via `eval "$CMD" > ... 2>&1; echo $? > baseline-exit.txt` (`:38-39`); `on_error: define_done` (`:43`) means even a shell-level failure still proceeds. `run_final_tests` (`:596-627`) later reads `baseline-exit.txt` (`:623`) and gates on `[ "$FINAL_EXIT" = "0" ] || [ "$FINAL_EXIT" = "$BASELINE_EXIT" ]` (`:624`) — `on_no: continue_work` (`:626`).
- **Mirror-drift gate precedent — correction to the Proposed Solution's citation**: the `fb747a60` pattern actually lives in `scripts/tests/test_wiring_skills_and_commands.py:376-424` (`GATED_HOSTS` list + `@pytest.mark.parametrize("host", GATED_HOSTS)` over `resolve_emitter`'s own registry), not in `test_builtin_loops.py`'s generic `builtin_loops` fixture (`:34-40`). A new mirror-drift gate for `test_cmd`/`lint_cmd` resolution should follow the `test_wiring_skills_and_commands.py` registry-parametrize shape — a `GATED_LOOPS` constant plus one assertion per site that it delegates to ~~`fragment: resolve_test_cmd`~~ **`ll-config get project.<key>`** (corrected: no fragment is added, see §1c) rather than an inline snippet — while `builtin_loops` remains the right fixture if a blanket scan-every-loop-file approach is preferred instead.

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Fragment parameter mechanism, confirmed against current code** (verifies the proposed `resolve_test_cmd(config_key, absent_default, null_value)` fragment is directly implementable with no executor changes): `resolve_fragments` (`scripts/little_loops/fsm/fragments.py:66-153`) is a parse-time expansion only — it does not substitute `${param.x}` text. It captures the fragment's `parameters:` block (`:141`), deep-merges the fragment body into the calling state (`:142`), and renames the state's `with:` block to `fragment_bindings` while stashing declared params as `fragment_parameters` (`:144-148`). The actual `${param.x}` substitution happens at runtime in `FSMExecutor._build_context` (`scripts/little_loops/fsm/executor.py:3283-3325`): it interpolates `fragment_bindings` against the run context (`:3307`), fills declared defaults for unbound optional params (`:3308-3315`), raises `ValueError` on an unbound required param (`:3317-3322`), and assigns the result to `ctx.param` (`:3323`). Static validation of `with:` bindings against the fragment's declared contract runs separately in `_validate_fragment_bindings` (`scripts/little_loops/fsm/validation/structural_rules.py:334-403`), invoked from `load_and_validate` (`:1755`).
- **`rn-refine.yaml:988-994` conversion caveat**: this site's `try/except` degrades to an empty string `''` on any resolution failure (missing config, present-null, or exception alike), and the consuming state branches only on `[ -z "$TEST_CMD" ]` (`:995-997`) — it is gated as advisory only (`on_yes`/`on_no` are not set; failure only appends a `RECOVERY_NEEDED` note to `plan-rubric.md`, `:998-1002`). No other state or test reads this state's output. Converting it to the shared fragment's `SKIP`/`true` sentinel values is low-risk but not a drop-in: the site's `-z "$TEST_CMD"` skip check must be preserved rather than assumed to already match a `SKIP`/`true` shape, since `SKIP` and `true` are both non-empty strings.

### Design review — second pass, 2026-08-20

_Claims re-verified empirically against the working tree. Recorded so the next pass does not
re-derive them._

**Confirmed as written:**

- The `ll-config get project.test_cmd` three-way table in §1 — all five rows reproduced:
  present-null → empty; absent → `pytest`; value → value; file absent → `pytest`;
  malformed → empty. All exit 0.
- `ProjectConfig` field defaults (`config/core.py:188-195`) and `from_dict`'s
  `data.get("test_cmd", "pytest")` (`:215`); `resolve_variable`'s `if value is None: return
  None` (`:1056-1057`) walking `to_dict()`, whose `project` block passes the dataclass fields
  through unchanged (`:724-735`).
- §1's "this is a new convention" claim: **zero** `ll-config` invocations in any loop YAML
  today; 57 inline `.ll/ll-config.json` mentions across `scripts/little_loops/loops/`.
- `ll-config get` stdout is byte-clean under `LL_AUTOMATION=1` (no banner, no analytics
  chatter, nothing on stderr) — safe for `CMD=$(...)` capture inside a loop.

**Checked and found to need no change (recorded to stop re-investigation):**

- The opt-out path does **not** poison the next state. `count_final`
  (`general-task.yaml:628-650`) reads `dod.md`, not `verify-output.txt`, so
  "`run_final_tests` runs nothing and passes" leaves nothing downstream to misparse.
- The cwd precondition in the Resolution contract holds for this repo: `.ll/ll-config.json`
  is git-tracked (only `.ll/ll.local.md`, `history.db`, and transient state are gitignored),
  so worktree-isolated runs carry it. Note this is a property of *this* repo, not a
  guarantee for consuming projects — but in a project where the file is untracked, the
  baseline and final gate both resolve to the same absent-default and the ENH-2244 equality
  comparison still holds, so no spin results.

## Implementation Steps

1. **Pin the contract first — no production code yet.** Add tests for `ll-config get`
   covering, for **both** `project.test_cmd` and `project.lint_cmd`: key present-and-null →
   empty stdout; key absent → the `ProjectConfig` default; key present with a value → that
   value; config file entirely absent → the default; and a `.ll/ll.local.md` frontmatter
   value overriding `.ll/ll-config.json`. These pass today — they exist to stop a future
   BUG-3274-style type cleanup from silently deleting the opt-out. Model the shell-execution
   half on `TestVerifyStateConfigReadShell` (`test_builtin_loops.py:4938-5038`), which
   currently covers only the key-**absent** path.
   Also add the negative case: `test_cmd: null` in `ll.local.md` resolves to the
   absent-default, **not** opt-out (documented asymmetry, see Expected Behavior).
   Add the malformed-config case from §1e, asserting **current** behavior: unparseable
   `.ll/ll-config.json` → empty stdout, exit 0, **nothing on stderr**. (This step is labeled
   "no production code yet", so it must pin what exists today; §1e's stderr warning flips
   this assertion in Step 3a, which is where the new expectation belongs. The original text asked Step 1 to assert a warning that does not
   exist until Step 3a, which cannot pass.)
   **These belong in `scripts/tests/test_config_cli.py`** — the existing `ll-config` CLI test
   module. Extend it; do not start a new one.
2. **Make the genuine design decisions before writing any shell.** None of these are
   mechanical, and each one is wrong-by-default if skipped:
   - a. The `rl-coding-agent` precedence question (§2, options (a)/(b)). **Still in scope** —
     `rl-coding-agent.yaml:60,68` are two of the three defective sites.
   - b. ~~Per-site empty-`CMD` handling for the nine converted sites (§2b table).~~
     **MOVED to ENH-3277** along with the conversions themselves — see **Deferred
     to follow-up**. §2b's table stays in this issue as the analysis the follow-up must act
     on; it is a hard prerequisite *there*, not here. Nothing in Steps 3–5 converts any of
     those nine sites, so no §2b row needs picking to ship this P0.
   - ~~c. Whether §1e's stderr warning lands now or is deferred to Impact.~~ **DECIDED: it
     lands now.** See §1e — the `cfg is None` discriminator is confirmed to exist, and the
     work is a ~5-line split of `cli/config.py:69-73` into two `try` blocks. No longer a
     decision; it is Step 3a below.
   - ~~c'. `--strict` vs. the stderr warning (§1e).~~ **DECIDED 2026-08-20 (third pass): no
     `--strict`.** Row 3 of §1e's table was not real (`resolve_variable` cannot raise), so
     the flag covered one door rather than a class; and a non-zero exit is unroutable at the
     states that need it (§1f). The stderr warning lands as a pure diagnostic and §3c closes
     both live doors. No longer a decision.
   - ~~c''. Confirm the executor persists per-state shell stderr.~~ **RESOLVED 2026-08-20
     (fourth pass) — it does. No longer a blocker; do not re-investigate.** `FSMExecutor`
     captures shell stderr into `stderr_chunks` (`fsm/executor.py:2497-2553`), surfaces the
     last 2000 chars as `stderr_preview` on the state record (`:2299-2306`, ENH-2469), and
     persists the full `result.stderr` at `:2373`. So §1e's stderr warning **is** visible to a
     run forensic, exactly as §1e originally asserted, and the fallback plan (write the
     diagnostic into a run-dir artifact instead) is unnecessary. §3c still writes its
     which-door marker into the run dir, but as a convenience rather than a rescue.
3a. **Land the §1e stderr warning as a diagnostic.** Split `cli/config.py:69-73`'s single
   `except Exception` into two `try` blocks — construction failure → warn on stderr,
   `return 0`; resolution failure → `value = None` as today (note this second arm is
   currently unreachable, since `resolve_variable` cannot raise; keep it for shape). Stdout
   and the always-0 exit contract are unchanged, so no call site is affected. Optionally
   short-circuit `_warn_if_unknown_section` when the root segment is already in
   `cfg.to_dict()` (§1 cost caveat). Retarget Step 1's malformed-config assertion here.
   **Do NOT add a `|| { ...; exit N; }` guard to any converted call site** — see §1f; at the
   three exit-code-gated sites it routes to `on_no` and creates a spin. This is the only
   production-code change in the issue.

3. **Fix the three blockers.** Convert `general-task.yaml:37` and
   `rl-coding-agent.yaml:60,68` to `ll-config get` — the sites that emit literal `None`
   today. Use the **per-site** precedence from §2's table: context-first for
   `general-task`, config-first for `rl-coding-agent`. Do not paste one shape into both.
   In the same edit, give `check_baseline_tests` the `${context.test_cmd}` override it
   lacks today; preserve the existing `baseline-ref.txt` capture at `:39`.
   **Per §3c this is the *only* resolution in `general-task`** — do not add a second one to
   `run_final_tests` and then try to keep the two byte-identical.
3b. **Implement §3c's resolve-once handoff.** `check_baseline_tests` writes the resolved
   command to `${context.run_dir}/resolved-test-cmd.txt` (empty when unresolvable) and,
   because it is `next:`-routed rather than exit-code-gated, is the one state that may
   safely test `$?` — use it to distinguish `ll-config` not found (127) from an explicit
   opt-out, writing both to `SKIP` but logging which into the run dir. `run_final_tests`
   reads `resolved-test-cmd.txt` and no longer invokes `ll-config`.
   **Preserve `run_final_tests`'s existing `on_error: diagnose` edge** (`general-task.yaml:627`)
   through the rewrite — same class of omission as the `baseline-ref.txt` capture, which this
   issue does call out explicitly. Losing it silently reroutes shell-level failures.
   Implement the three rows of §3c's 2×2 table, one regression test each. Tests: (i) a run whose
   `context.test_cmd` override is set produces the *same* command in the baseline and the
   final gate; (ii) `resolved-test-cmd.txt` empty → `run_final_tests` takes the `SKIP` path;
   (iii) `ll-config` absent from PATH (shadow it in the test env) → `baseline-exit.txt` is
   `SKIP` and the run reaches `count_final` rather than `continue_work`.
4. **Add the baseline sentinel.** Implement the `SKIP` contract in `check_baseline_tests` +
   `run_final_tests`, with the opt-out detected as `[ -z "$CMD" ]`. The `SKIP` branch in
   `run_final_tests` passes on `FINAL_EXIT` in `{0, 127}` — the `127` arm is required to
   close the present-but-unrunnable `test_cmd` spin (see Expected Behavior), not optional
   defensiveness. Add a regression test for that case specifically: `test_cmd` set to a
   command that does not exist, asserting `run_final_tests` reaches `count_final`.
   **Include §3b's reader-side normalization** — replace the `|| echo "0"` fallback at
   `general-task.yaml:623` with the `case` statement that maps any non-digit content to
   `SKIP`, and write `SKIP` from `check_baseline_tests`'s `on_error` path. Add regression
   tests for the two cases the literal-`SKIP` branch alone misses: `baseline-exit.txt`
   **empty** and `baseline-exit.txt` **absent**, each with `FINAL_EXIT = 2`, asserting
   `count_final` rather than `continue_work`. Without these two the fix leaves a live spin
   path open for a project with a perfectly valid `test_cmd`.
   **Also add the `127` arm to the numeric-baseline branch** (Expected Behavior): with
   `baseline-exit.txt` = `2` and `FINAL_EXIT = 127`, `run_final_tests` must reach
   `count_final`, not `continue_work`. Add that regression test alongside; without it a
   baseline that ran plus a final command that became unrunnable still spins. Do **not**
   admit `126` — add a test pinning that `baseline=0`, `FINAL_EXIT=126` still routes to
   `continue_work`, so the exclusion is deliberate rather than incidental.
5. **Land the mirror-drift gate — with a shrinking exemption list.** Two assertions per §4:
   (i) no loop YAML contains an inline `.ll/ll-config.json` read for any of the six
   `ProjectConfig` command keys (access-pattern match, not path-substring); (ii) every
   `${context.<key>}` reference resolves against its loop's declared `context:` block — the
   assertion that covers §2's "single highest-risk axis", which nothing covers today.
   Exemptions: `oracles/code-run-gate.yaml` permanently (§1d), plus a
   `_PENDING_CONVERSION` constant listing the ten deferred sites. Green on the three sites
   fixed in step 3, red-listing the rest explicitly — so the fourteenth copy cannot land
   while the follow-up is open. Assertion (ii) applies to **every** loop with no exemptions;
   it should be green on the tree as it stands and stay green.
6. ~~**Convert the remaining sites.**~~ **DEFERRED — see *Deferred to follow-up*.** Nothing
   in this issue converts the nine correct-but-guessing copies or
   `auto-refine-and-implement.yaml:433-436`.
7. **Verify.** `python -m pytest scripts/tests/` exits 0; `ll-loop validate` clean on
   `general-task.yaml` and `rl-coding-agent.yaml`; manual smoke of `general-task` in a
   scratch project with `test_cmd: null` reaching a terminal state instead of cycling, plus a
   second smoke with `test_cmd` set to a nonexistent command (the 127 path from step 4).

**Rollback seam:** steps 3–5 are independent per-file edits behind a contract pinned in
step 1. If a conversion misbehaves in a consuming project, revert that one file — there is
no shared artifact to unwind, which is a further advantage over the fragment design.

### Deferred to follow-up

**The follow-up is [ENH-3277] — "Convert the nine remaining inline `test_cmd`/`lint_cmd`
resolution sites to `ll-config get`" (P2), `blocked_by: [BUG-3269]`.**

_Split out 2026-08-20 (fourth pass). Rationale in the SCOPE note under Summary: the nine
"correct-but-guessing" sites cannot produce this P0, and three of them carry behavior changes
on irreversible edges that must not gate a live spin fix._

**Stays in BUG-3269 (the P0):**

- Steps 1, 2a, 3a, 3, 3b, 4, 5, 7.
- The three defective sites: `general-task.yaml:37`, `rl-coding-agent.yaml:60,68`.
- `general-task`'s `SKIP` sentinel, §3b reader-side normalization, §3c resolve-once handoff,
  and the §3c 2×2 contract.
- §1e's `cli/config.py` stderr warning (the only production-code edit).
- The §4 mirror-drift gate, both assertions, with `_PENDING_CONVERSION` populated.
- Docs limited to what this issue changes: `HARNESS_OPTIMIZATION_GUIDE.md` (the `ll-config
  get` convention, both precedence shapes, the cwd precondition, §4's `build_cmd`/`run_cmd`
  semantic trap), `LOOPS_REFERENCE.md`'s `baseline-exit.txt` / `SKIP` sentinel, and
  `config-schema.json` + `CONFIGURATION.md`'s absent-vs-null note.

**Moves to ENH-3277 (consistency refactor, not a P0):**

- Converting the nine correct-but-guessing sites: `fix-quality-and-tests.yaml:58-78`,
  `evaluation-quality.yaml:58` **and** its hardcoded `ruff check scripts/` at `:64`,
  `dead-code-cleanup.yaml:76`, `harness-plan-research-implement-report.yaml:126`,
  `harness-multi-item.yaml:95`, `harness-single-shot.yaml:66`,
  `test-coverage-improvement.yaml:45,152`, `rn-refine.yaml:991`, plus
  `auto-refine-and-implement.yaml:433-436` (**not** `:679-680`, §2b correction).
- **Step 2b — picking a §2b empty-`CMD` row per site — is that issue's hard prerequisite.**
  The three marked *explicit skip required* (`dead-code-cleanup`,
  `test-coverage-improvement`, `evaluation-quality`) change from "gate on pytest" to "pass
  unverified" if converted naively, and `dead-code-cleanup`'s `on_yes` edge commits
  deletions. That analysis is the reason for the split, not an afterthought to it.
- Emptying `_PENDING_CONVERSION` and deleting the constant — the follow-up's definition of
  done.
- Docs for those sites: `scripts/little_loops/loops/README.md:33`, and the
  `LOOPS_REFERENCE.md` `project.test_cmd`/`lint_cmd` rows at `:979`, `:1305`, `:1327`.
- The §2b `evaluation-quality.yaml` marker-into-`eval-test-results.txt` design, and the
  `evaluation-quality.yaml:64` lint-scope widening (`ruff check scripts/` → `ruff check .`
  in projects that never set `lint_cmd`).

Out of scope for both, already split: `incremental-refactor.yaml` → BUG-3276 (§Similar
Patterns), `oracles/code-run-gate.yaml` → permanent exemption (§1d).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation._

> **SCOPE FILTER (fourth pass).** Bullets below that convert one of the nine
> correct-but-guessing sites, `auto-refine-and-implement.yaml`, or
> `evaluation-quality.yaml:64` — and the §2b row-picking bullet — belong to the **follow-up**,
> not BUG-3269. In-scope here: the `general-task` / `rl-coding-agent` bullets, the
> `ll-config get` contract tests, the `test_general_task_loop.py` /
> `test_builtin_loops.py` retargeting, the §1e `cli/config.py` warning, the §3c
> resolve-once implementation, the `127`/`126`/empty/absent `run_final_tests` regression
> tests, the `HARNESS_OPTIMIZATION_GUIDE.md` convention write-up, and the two mirror-drift
> gate assertions. See **Deferred to follow-up** for the authoritative split.

- Convert `scripts/little_loops/loops/auto-refine-and-implement.yaml:433-436` — the
  13th call site, not in the original ~12-site table; not currently buggy but in scope for
  the "convert all call sites" mandate. **`:679-680` is NOT a call site** — it reads
  `cfg.project.test_cmd` off a real `BRConfig`, already correct and already `ll.local.md`-aware
  (§2b correction)
- Pick a §2b empty-`CMD` row for each of the nine converted sites; `dead-code-cleanup.yaml`,
  `test-coverage-improvement.yaml`, and `evaluation-quality.yaml` require an explicit
  `[ -z "$CMD" ]` branch rather than pass-on-empty
- Use the **config-first bare** shape for the eight loops that declare no `context.test_cmd`
  key; do not paste the context-first shape there (§2 — it raises at interpolation time)
- Convert `scripts/little_loops/loops/evaluation-quality.yaml:64`'s hardcoded
  `ruff check scripts/` to `ll-config get project.lint_cmd` (§4)
- Update `scripts/tests/test_general_task_loop.py` — retarget the `test_cmd` substring
  assertions in `TestENH2225FinalOnlyGate` and `TestRunFinalTestsShellAction` at
  `ll-config get project.test_cmd` (no load-path rewrite needed)
- Update `scripts/tests/test_builtin_loops.py::TestGeneralTaskLoop` — verify the raw-YAML
  fixture's baseline/final-test substring assertions still hold after conversion
- ~~Extend `test_fsm_fragments.py`'s `migration_targets`~~ — not applicable, no fragment
- Add `ll-config get` contract tests per Implementation Step 1, covering
  key-present-with-JSON-`null` for both `test_cmd` and `lint_cmd` (not just key-absent),
  the `ll.local.md` override, and the `ll.local.md`-null asymmetry
- Update `docs/guides/LOOPS_REFERENCE.md`, `scripts/little_loops/loops/README.md`, and
  `docs/reference/CONFIGURATION.md` to reflect the corrected absent/null/value semantics and
  the `SKIP` sentinel. `docs/reference/loops.md:829-833` (`code-run-gate.yaml`) needs **no
  change** — that loop is out of scope (§1d)
- Document in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` that `ll-config get` is the
  required way to read a project command inside a loop, and that inline
  `.ll/ll-config.json` parsing is prohibited (it bypasses `ll.local.md`). Include both
  precedence shapes from §2's table and the cwd precondition — no other loop uses this
  call today, so the guide is the only precedent a future author will find. Include §4's
  semantic trap: the absent-vs-null three-way distinction holds only for `test_cmd`,
  `lint_cmd`, `type_cmd`, and `format_cmd`; `build_cmd`/`run_cmd` default to `None` and
  collapse absent ≡ null
- When converting `evaluation-quality.yaml:64`, express the `[ -z "$CMD" ]` skip by writing
  an explicit "no test signal" marker into `eval-test-results.txt` (the file `capture:
  code_results` reads) — **not** by rerouting, since `evaluate_code` has no `on_yes`/`on_no`
  edges to reroute (§2b correction)
- Add the `${context.test_cmd}` override to `general-task.yaml`'s `check_baseline_tests`
  (it has none today) so baseline and final gate resolve identically
- Add a `run_final_tests` test for `baseline-exit.txt = SKIP` with `FINAL_EXIT = 127`
  routing to `count_final`, not `continue_work`
- Add `run_final_tests` tests for `baseline-exit.txt` **empty** and **absent** with
  `FINAL_EXIT = 2`, both routing to `count_final` (§3b — the cases the literal-`SKIP`
  branch alone does not cover)
- Land the §1e stderr warning in `scripts/little_loops/cli/config.py` (Step 3a) — the
  issue's only production-code edit; update the `Files to Modify` note that says this file
  needs no change
- **Do NOT add a `|| { ...; exit N; }` guard to converted call sites.** A previous revision
  of this issue required one at every site to catch a missing `ll-config` binary; it is
  withdrawn as **harmful** — at the three `evaluate: exit_code` sites a non-zero exit routes
  to `on_no`, which for `run_final_tests` is `continue_work`, i.e. the BUG-3269 spin (§1f).
  The missing-binary case is handled once, in `check_baseline_tests` (§3c)
- Implement §3c in `general-task.yaml`: `check_baseline_tests` resolves once and writes
  `${context.run_dir}/resolved-test-cmd.txt`; `run_final_tests` reads it and does not call
  `ll-config`. This replaces the withdrawn "both states must be byte-identical" requirement
  in §2 and subsumes the separate `${context.test_cmd}`-override fix for `check_baseline_tests`
- Add the `127` arm to `run_final_tests`'s **numeric**-baseline comparison, not just the
  `SKIP` branch (Expected Behavior), with a regression test for `baseline=2` / `FINAL_EXIT=127`
  → `count_final`, and a pinning test that `FINAL_EXIT=126` still routes to `continue_work`
- Decide `incremental-refactor.yaml:12`'s hardcoded `python -m pytest scripts/tests/` in or
  out of scope explicitly (see Similar Patterns) rather than leaving it as a "confirm"

## Impact

- **Severity**: P0. Silently burns a full iteration budget and the user's tokens on
  already-completed work; requires manual SIGKILL to stop. Corrupts RL reward signal in a
  second loop.
- **Blast radius**: `general-task` is the most-used built-in loop and is live in every
  local-editable consuming project.
- **Risk of the fix**: low, and **lower after the fourth-pass scope split**. Almost no new
  production code — `ll-config get`'s resolution already exists and behaves correctly; the
  sole production edit is §1e's ~5-line `except` split, which leaves the stdout and exit-code
  contract untouched and so cannot affect any existing `ll-config` caller. The risk is
  otherwise confined to **three call sites in two loop files** (`general-task.yaml`,
  `rl-coding-agent.yaml`) plus `general-task`'s sentinel rework, each mechanically checkable
  by the new gate and independently revertible. The ten remaining conversions — which carried
  the behavior changes on a commit edge and a scoring edge — are deferred, so none of that
  risk ships with the P0.
- **Risk being *accepted* by the fix**: the three converted gates now depend on a single
  binary whose contract is fail-open (§1e). That is a real concentration of risk relative to
  independent inline snippets. It is fully mitigated in `general-task`, where §3c maps both
  live failure doors to `SKIP`. `rl-coding-agent`'s two sites still fail open on a malformed
  config, per §2's config-first shape — accepted, since the alternative there is the status
  quo of scoring a reward against `command not found`. The ten unconverted loops keep their
  present inline behavior (which also fails open) until the follow-up lands.
- **Backward compatibility**: projects with a non-null `test_cmd` see no behavior change.
  Projects with `test_cmd: null` change from "guess pytest" to "no test gate" — that is
  the intended fix, and matches what `fix-quality-and-tests.yaml` already does. Two smaller
  intended changes: (a) `.ll/ll.local.md` overrides of `test_cmd`/`lint_cmd` now take effect
  inside loops (they never did); (b) `rl-coding-agent.yaml` with the key **absent** resolves
  to `pytest` / `ruff check .` instead of the context literal, and its `:17-18` context
  defaults become dead under §2 option (a). Two further intended changes: (c) a
  present-but-unrunnable `test_cmd` (exit 127) no longer gates `general-task`'s
  `run_final_tests`; (d) `general-task`'s `check_baseline_tests` starts honoring
  `${context.test_cmd}`, which it silently ignored before.
- ~~**Behavior changes at the nine non-`general-task` sites**~~ — **DEFERRED to the follow-up;
  no such change ships with this issue.** Retained for that issue's Impact: under
  `test_cmd: null` those sites would stop gating on a guessed `pytest`. For six that is a
  clean opt-out; for `dead-code-cleanup`, `test-coverage-improvement`, and
  `evaluation-quality` it would mean committing or scoring unverified work unless handled
  explicitly — the §2b table is a hard prerequisite *there*, not advisory. This bullet is
  precisely why the split exists.
- **Not fixed by this issue**: `ll-config get` resolves from `Path.cwd()` with no upward
  walk, so a loop state invoked from a subdirectory still loses the opt-out. Safe for all
  13 converted sites today (FSM shell actions run at the project or worktree root) and no
  worse than the snippets being replaced — see the precondition in the Resolution contract.
- **Additional intended changes from §3b (baseline normalization)**: (e) a **missing** or
  **empty** `baseline-exit.txt` now resolves to `SKIP` (pass on `FINAL_EXIT` in `{0, 127}`)
  instead of the old `|| echo "0"` fallback's "require `FINAL_EXIT = 0`". This is a
  deliberate loosening — the old fallback applied the strictest possible gate on the least
  information, and was itself a live spin path for a project with a valid `test_cmd`.
  (f) `check_baseline_tests`'s `on_error` path now writes `SKIP` rather than leaving the file
  untouched.
- **Behavior change at `evaluation-quality.yaml:64` — DEFERRED to the follow-up**: the hardcoded `ruff check scripts/`
  becomes `ll-config get project.lint_cmd`, which resolves to `ruff check .` in a project
  that never configured `lint_cmd` — a broader lint scope than before. Already non-gating
  (`|| true`), so this affects the captured lint artifact, not control flow.
- **§1e closed, without new CLI surface.** An unparseable `.ll/ll-config.json` still resolves
  to empty output (the stdout contract is deliberately unchanged) but now emits a stderr
  warning distinguishing it from a genuine `test_cmd: null`. In `general-task` it no longer
  merely warns: §3c's `check_baseline_tests` maps *both* live doors — malformed config and a
  missing `ll-config` binary — to `SKIP`, so the run degrades to "no baseline to compare
  against" instead of silently opting out of the gate. At the other converted sites the
  behavior is the §2b row for that site.
  - **A strict mode for `ll-config get` was considered and rejected** (§1e/§1f): with
    `resolve_variable` unable to raise, it discriminated the same single condition as the
    warning, and its non-zero exit is unroutable at `evaluate: exit_code` states without a
    `harness_exit`/`on_cannot_judge` swap in three gating states.
- **§3c changes `general-task`'s internal structure, not just its resolution.**
  `run_final_tests` stops resolving the test command and reads
  `${context.run_dir}/resolved-test-cmd.txt` written by `check_baseline_tests`. Consequence:
  the two states can no longer disagree, the ENH-2244 equality comparison is sound by
  construction, and `general-task` makes one `ll-config` call per run instead of two. A
  `run_final_tests` reached without a preceding `check_baseline_tests` (resume, handoff) sees
  a missing file, which §3b's normalization already maps to `SKIP`.
- **Additional intended change (g)**: `general-task`'s `run_final_tests` stops gating on
  `FINAL_EXIT = 127` on the numeric-baseline branch as well as under `SKIP` — a command that
  became unrunnable between the baseline and the final gate no longer spins. `126` is
  deliberately still gating (see Expected Behavior).

## Related Key Documentation

- ENH-3277 — the follow-up this issue splits the bulk conversion into; `blocked_by: [BUG-3269]`
- `postmortems/general-task-final-verify-spin-2026-08-20.md` — full forensic audit
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop design rules
- ENH-2244 — the baseline-comparison gate whose null-config failure mode this is
- ENH-2225 — final-only whole-suite gate (`run_final_tests`)

## Status

**Open** | Created: 2026-08-20 | Priority: P0


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-20_

**Readiness Score**: 88/100 → PROCEED (blocked by hard override — see below)
**Outcome Confidence**: 77/100 → Good

### Gaps to Address
- ~~**Program Design gate (hard override)**~~ — **RESOLVED 2026-08-20 by design review.**
  The `### Signatures` bullets were rewritten as strict `name(params: Type) -> Type` lines
  with bare-token types; `ll-issues check-design BUG-3269` now exits 0 and
  `format-check --format json` reports an empty `program_design_nonspecific`. The
  remaining `stale_file_ref` entries (`.ll/ll.local.md`, `postmortems/...`) are expected —
  both paths are gitignored. Original text retained below for context:
- **Program Design gate (hard override, `ll-issues check-design` exits 1)**: none of the
  three `### Signatures` bullets are regex-matchable as signature-shaped by
  `scripts/little_loops/issues/program_design.py` (`_SIG_CALL`/`_SIG_FIELD`), even though a
  human reader can see they are precise. Two distinct causes: (1) `` `ll-config get
  project.<key> -> str` `` has no `(...)` call syntax, so `_SIG_CALL` never matches it; (2)
  `` `check_baseline_tests() -> writes baseline-exit.txt: int | "SKIP"` `` and `` `run_final_tests(baseline_exit: int | "SKIP") -> bool` ``
  both have return/param type text (`writes baseline-exit.txt: int | "SKIP"`,
  `int | "SKIP"` with an embedded quoted string literal) that doesn't fit `_TYPE`'s
  `[\w.]+` token grammar. Remedy: rephrase as strict `name(params: Type) -> Type` lines with
  a bare token type — e.g. replace the `"SKIP"` string-literal type with a plain identifier
  like `SkipSentinel` or `str` in the signature, and give the `ll-config get` line a
  call-shaped form such as `` `get(key: str) -> str | None` `` — then move the CLI-invocation
  prose after the em-dash description. Verify with `ll-issues format-check BUG-3269 --format
  json` and confirm `program_design_nonspecific` is empty, then `ll-issues check-design
  BUG-3269` exits 0, before implementation.

### Outcome Risk Factors
- Broad enumeration across ~13 call sites in 11 loop files — each conversion is mechanical
  and independently revertible (per the issue's own rollback seam), but the sheer count
  raises the odds that one site's precedence shell (`${context.*}` override before
  `ll-config get`) gets pasted wrong. The mirror-drift gate (Implementation Step 5) is the
  intended catch for this, but it lands *after* all conversions in Step 4 rather than
  per-file — consider running `ll-loop validate` (already planned) plus a scoped `grep` for
  the old `.get('test_cmd'` pattern after each file, not just at the end.

## Session Log
- `/ll:manage-issue` - 2026-08-21T02:58:38 - `ce9c37b0-9b57-4f5a-80f2-0ab7308622ed.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T02:37:32 - `c4d0cb49-2d47-43ee-bd0a-5286b5885739.jsonl`
- `/ll:confidence-check` - 2026-08-21T02:27:16 - `fb32bf22-991c-4d52-a0d3-c79ca31f1f78.jsonl`
- `/ll:confidence-check` - 2026-08-21T00:48:05 - `e0ced191-faba-4adf-9e21-fe9bb9babc29.jsonl`
- `/ll:confidence-check` - 2026-08-21T00:22:27 - `8fa51734-384b-46a2-a10c-bd13c601a684.jsonl`
- `/ll:confidence-check` - 2026-08-20T23:39:55 - `bae4c657-9e53-457d-bcc4-db4ed042c8fb.jsonl`
- `/ll:wire-issue` - 2026-08-20T23:37:01 - `f8d1ceb8-b964-4281-915c-bc7d008244e2.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:29:35 - `8838a661-0444-4cad-a5d2-117e364de078.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
