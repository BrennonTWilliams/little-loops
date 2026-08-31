---
id: BUG-3364
type: BUG
priority: P2
status: open
captured_at: '2026-08-30T23:30:00Z'
discovered_date: 2026-08-30
discovered_by: audit-loop-run
relates_to:
- ENH-2601
- ENH-2631
- BUG-2614
depends_on:
- ENH-3365
decision_needed: false
---

# BUG-3364: `verify` and `merge_epic_branch` swallow a python3 crash as an empty verdict, not `failed`/`not_run`

## Summary

In `scripts/little_loops/loops/auto-refine-and-implement.yaml`, the `verify`
state (line 392) captures its Python heredoc's stdout directly into
`VERIFY_VERDICT` (`VERIFY_VERDICT=$(... python3 << 'PYEOF' ... PYEOF)`, line
527) and the `merge_epic_branch` state redirects its heredoc's stdout
straight into `epic-merge-verdict.txt` (line 570) — neither checks the
python3 subprocess's own exit code. When that subprocess crashes with an
uncaught exception (traceback to stderr, empty stdout), both states still
`echo`/redirect the empty string to their verdict file and complete with
`exit_code: 0`. `finalize`'s fallback (`cat verify-verdict.txt 2>/dev/null ||
echo "not_run"`, lines 966/987) only triggers on file *absence* — the crash
leaves the file present but empty, so the fallback never fires and
`summary.json` ends up with `verify_verdict: ""` / `epic_merge_verdict: ""`,
neither of which matches any documented enum value
(`passed/failed/collection_error/config_error/skipped/not_run`).

## Current Behavior

`verify` (line 392) captures its python3 heredoc's stdout directly into
`VERIFY_VERDICT` via command substitution, and `merge_epic_branch` (line 570)
redirects its heredoc's stdout straight into `epic-merge-verdict.txt` — in
both cases only the heredoc's *stdout* is used as the verdict; neither state
checks the python3 subprocess's own exit code. A crash mid-heredoc (e.g.
`ModuleNotFoundError`) prints a traceback to stderr, leaves stdout empty, and
both states still write the empty string to their verdict file with the
outer shell action reporting `exit_code: 0`. `finalize`'s fallback (lines
966/987: `cat verify-verdict.txt 2>/dev/null || echo "not_run"`) only
substitutes `"not_run"` when the file is *absent* — a present-but-empty file
short-circuits `cat`'s success and the fallback never fires, so
`summary.json` ends up with `verify_verdict: ""` / `epic_merge_verdict: ""`.

## Steps to Reproduce

1. Run `auto-refine-and-implement.yaml` against an `EPIC-*` scope so the
   `verify` and `merge_epic_branch` states take the epic-branch code path
   (the one that imports `little_loops.worktree_utils` / `little_loops.config`
   inside the heredoc).
2. Force the heredoc's python3 subprocess to crash instead of running
   normally — e.g. invoke the loop with a `PYTHONPATH` that shadows/hides the
   `little_loops` package for just that subprocess (matching the machine
   conditions [[ENH-3365]] documents: multiple Python installs on `PATH`,
   only one with `little_loops` importable).
3. Let the run reach `finalize` and inspect `summary.json`.
4. Observe: `verify_verdict` and `epic_merge_verdict` are both `""` (empty
   string) — not `"passed"`, `"failed"`, `"skipped"`, `"collection_error"`,
   `"config_error"`, or `"not_run"` — while the run's own terminal `verdict`
   still reads `"success"`.

## Root Cause

- **File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- **Anchor**: in `verify`'s embedded python3 heredoc (`classify()` at line 428,
  `emit()` at line 441, invoked via `VERIFY_VERDICT=$(... python3 <<'PYEOF'
  ... PYEOF)` at line 410) and in `merge_epic_branch`'s heredoc (`python3
  <<'PYEOF' > "$RUN_DIR/epic-merge-verdict.txt"` at line 570)
- **Cause**: Every code path either heredoc's author wrote reaches `emit()`
  (which always ends in `print(verdict)` + `raise SystemExit(0)`) or a bare
  `print(...)` followed by `SystemExit(0)` — so on every *intentional*
  branch the python3 process's own exit code is 0. The bug is specifically
  an *uncaught* exception (e.g. `ModuleNotFoundError` for
  `little_loops.worktree_utils`/`little_loops.config`) that never reaches
  `emit()`/`print()`: Python writes nothing to stdout, a traceback to
  stderr, and exits non-zero. Note that in `merge_epic_branch` the shell
  performs the `> "$RUN_DIR/epic-merge-verdict.txt"` redirection *before*
  python3 runs, so a crash still leaves a present-but-empty verdict file
  behind — a state-side exit-code check alone (without rewriting the file)
  does not stop `finalize` from reading the empty file; the state-side RC
  handling and `finalize`'s `[ -s ]` guard are a required pairing, not
  alternatives. Because each state's action script ends with
  an unconditional `echo` after the heredoc, the wrapping `bash -c`
  invocation always exits 0 regardless of the nested heredoc's own exit
  code — `DefaultActionRunner.run()` (`scripts/little_loops/fsm/runners.py`)
  reports exactly one `ActionResult.exit_code` for the whole action string,
  with no visibility into the nested heredoc's own exit status. This is why
  `on_error` (declared on both states) is unreachable for this failure mode.
  `finalize`'s subsequent read (`cat "$RUN_DIR/verify-verdict.txt"
  2>/dev/null || echo "not_run"`, lines 966/987) only substitutes
  `"not_run"` on file *absence*; a present-but-empty file (the crash's
  actual output) passes through as the literal empty string into
  `summary.json`.

## Evidence

Observed via `/ll:audit-loop-run sprint-refine-and-implement
.loops/runs/sprint-refine-and-implement-20260830T172734/`
(archived at `.loops/.history/2026-08-30T222734-sprint-refine-and-implement/`):

```
{"event": "action_complete", ..., "exit_code": 0, "duration_ms": 36,
 "output_preview": "verify: verdict=",
 "stderr_preview": "Traceback (most recent call last):\n  File \"<stdin>\", line 58, in <module>\nModuleNotFoundError: No module named 'little_loops.worktree_utils'",
 "state": "verify"}

{"event": "action_complete", ..., "exit_code": 0, "duration_ms": 41,
 "output_preview": "merge_epic_branch: verdict=",
 "stderr_preview": "Traceback (most recent call last):\n  File \"<stdin>\", line 24, in <module>\nModuleNotFoundError: No module named 'little_loops.config'",
 "state": "merge_epic_branch"}
```

`summary.json` for the run:
```
{"verdict":"success","closed":3,...,"verify_verdict":"","epic_merge_verdict":"",...}
```

The run's actual test/lint gate (`project.test_cmd`) never executed, and the
epic-to-base merge check never ran — yet the run's terminal state and
`ll-loop`'s own success rendering read as green because `finalize` only
diverts to the failure terminal on `phantom`/`incomplete-abandoned`
(`case "$VERDICT" in phantom|incomplete-abandoned) exit 1 ;; esac`), which
this run's `VERDICT=success` (closed=3, no skips/errors/not-closed) never hits.

## Expected Behavior

A python3 subprocess crash inside `verify` or `merge_epic_branch` should
produce a verdict that the existing classification machinery can act on —
either `"error"` (a new class distinct from `failed`/`config_error`) or, at
minimum, `"not_run"` — never a bare empty string that passes silently through
`finalize`'s formatting and lands unexplained in `summary.json`.

## Proposed Solution

1. In both states, capture the python3 subprocess's own exit code alongside
   its stdout (e.g. `VERIFY_VERDICT=$(python3 <<'PYEOF' ... PYEOF); PY_RC=$?`)
   and treat a non-zero `PY_RC` as an explicit `error` verdict rather than
   trusting stdout.
2. In `finalize`, change the fallback from `cat file 2>/dev/null || echo
   not_run` to also treat an empty-but-present file as `not_run`/`error`
   (e.g. `[ -s file ] && cat file || echo not_run`).
3. Add regression coverage: simulate a python3 heredoc crash (e.g. via a
   `PYTHONPATH` that hides `little_loops`) inside `verify`/`merge_epic_branch`
   and assert `summary.json` reports a non-empty, documented verdict token —
   not `""`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_builtin_loops.py` — add a `PYTHONPATH`-override
  `subprocess.run(env=...)` regression case to `TestVerifyStateConfigReadShell`
  / `TestMergeEpicBranchConfigReadShell`, and add an `epic_merge_verdict`
  seeding parameter to `_run_finalize()` (currently absent) so the
  `epic-merge-verdict.txt` read path gets end-to-end coverage alongside
  `verify-verdict.txt`
- Update `docs/development/MERGE-COORDINATOR.md` (lines 159-163) — mention
  the new `"error"` verdict token alongside the existing
  `passed`/`collection_error`/`config_error`/`failed`/`skipped` vocabulary
  it already documents

## Program Design

### Signatures

- `emit(verdict, returncode=None, detail='')` (`auto-refine-and-implement.yaml:439`) — must also receive the heredoc's own subprocess exit code from its caller, not just trust stdout being non-empty.
- `classify(returncode, stderr='')` (`auto-refine-and-implement.yaml:428`) — unchanged; the caller must invoke it (or emit `"error"` directly) when the heredoc itself crashed, instead of only calling it on a clean run.

### Call Path

`verify` -> heredoc's `classify()` / `emit()` -> `VERIFY_VERDICT` -> `verify-verdict.txt` -> `finalize` -> `summary.json`'s `verify_verdict` field. Same shape for `merge_epic_branch` -> `epic-merge-verdict.txt` -> `finalize` -> `summary.json`'s `epic_merge_verdict` field.

### Decision Rules

- New verdict token: the fix introduces a value (e.g. `"error"`) distinct
  from the existing `classify()` taxonomy (`passed`/`collection_error`/
  `config_error`/`failed`) and from `finalize`'s `"not_run"` fallback.
- Exact trigger: the heredoc's own python3 subprocess exit code (captured
  via `$?` immediately after the heredoc, before any later command resets
  it — no existing statement in either state does this today) is non-zero
  **and** the heredoc printed no verdict to stdout (i.e. `emit()`/`print()`
  was never reached). This is a different signal from `classify()`'s
  `returncode` parameter, which is the *inner* `test_cmd`/
  `worktree_utils` result and must keep flowing through `emit()` unchanged.
- Escape hatch / precedence: this classification must fire only when the
  heredoc process itself crashed before emitting a verdict — it must never
  override a verdict the heredoc legitimately printed.
- **Scope decision — `finalize`'s pass/fail gate stays blind to the new
  token.** `verify_verdict`/`epic_merge_verdict` are documented as "advisory
  only, not folded into `verdict`" (`docs/guides/LOOPS_REFERENCE.md`), and a
  legitimate `failed` verdict already does not fail the run; making the new
  `"error"` token divert `finalize` to the failure terminal would give an
  infra crash *more* gating power than an actual test failure. This fix
  keeps the advisory contract: `"error"` must land in `summary.json` (where
  `audit-loop-run`'s documented enum check catches it) but must NOT change
  `finalize`'s `case "$VERDICT" in phantom|incomplete-abandoned)` gate.
  Wiring verify/merge verdicts into the composite gate is a separate,
  deliberate design change if ever wanted — out of scope here.
- Companion change: `finalize`'s two file reads (lines 966, 987) must
  resolve a present-but-empty verdict file to `"not_run"` (or the new
  token), not the empty string that reaches `summary.json` today — no
  existing idiom in this codebase combines a `[ -s file ]` non-empty guard
  with `cat file || echo <default>` (confirmed absent repo-wide by
  pattern-finder research).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- The FSM executor has no built-in mechanism to surface a nested heredoc's exit code separately from the wrapping `bash -c` action's own exit code: `DefaultActionRunner.run()` (`scripts/little_loops/fsm/runners.py`) always executes the full multi-line action string as one `subprocess.Popen(["bash", "-c", action], ...)` and returns a single `ActionResult.exit_code = process.returncode` for the whole script; `executor.py`'s un-annotated shell-state default (`evaluate_exit_code(action_result.exit_code)`) and the `shell_exit` fragment (`scripts/little_loops/fsm/fragments.py`) share this same single-exit-code contract. Any fix must manually capture `$?` immediately after the heredoc and propagate it (e.g. a final `exit "$RC"`), since any command executed afterward resets `$?`.
- Precedent for this exact idiom already exists elsewhere in this codebase: `workflow-generator.yaml`'s `validate_intent` state runs its heredoc directly (not via `$(...)`), captures `RC=$?` on the next line, and ends with `exit "$RC"` plus `evaluate: {type: exit_code}` — the shape that lets a heredoc's own crash reach the FSM's exit-code check. `general-task.yaml`'s `summarize_success` state instead appends `2>/dev/null || echo 0` on the heredoc's opening line inside the command substitution, substituting a safe numeric default on a non-zero exit. Neither idiom is used today in `verify`/`merge_epic_branch`.
- `finalize`'s composite `$VERDICT` (`success`/`partial`/`partial-with-errors`/`phantom`/`incomplete-abandoned`/`no-op`) is computed independently of `verify_verdict`/`epic_merge_verdict` — both states' own header comments say this is "advisory only." A fix to these two tokens does not by itself change `finalize`'s pass/fail gate; that gate stays blind to this crash mode unless separately wired.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `verify`
  state (heredoc + post-heredoc `echo`, ~lines 392-527), `merge_epic_branch`
  state (heredoc + post-heredoc `echo`, ~lines 543-570), `finalize` state
  (verdict file reads, ~lines 966, 987)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()`
  executes the full action string as one `bash -c` subprocess and reports a
  single `ActionResult.exit_code` for it; this is why the nested heredoc's
  own crash is invisible today
- `scripts/little_loops/fsm/executor.py` — `_evaluate()` /
  `evaluate_exit_code()` route on that single exit code; the `on_error`
  decisions for `verify`/`merge_epic_branch` derive from it
- `docs/guides/LOOPS_REFERENCE.md` — documents the `verify_verdict` enum
  (`passed`/`failed`/`collection_error`/`config_error`/`skipped`/`not_run`)
  as "advisory only, not folded into `verdict`"
- `skills/audit-loop-run/SKILL.md` (Step 6a) — documents the same
  six-token enum for a human/LLM auditor reading `summary.json`; does not
  account for an empty-string value

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — sub-loop
  caller: its `read_outcome` state invokes `loop: auto-refine-and-implement`
  (line 31) and its `done` state `cat`s the child's `summary.json` verbatim
  for display (lines 45-46) — confirmed it does not branch on the literal
  value of `verify_verdict`/`epic_merge_verdict` (it gates only on the
  separate `subloop_outcome_auto-refine-and-implement.txt` token), so no
  code change is required here; noted only because a new `"error"` token
  will flow through into what this state echoes [Agent 1 finding, confirmed
  via direct read]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/MERGE-COORDINATOR.md` (lines 159, 161, 163) — documents
  `verify-verdict.txt`/`verify-sha.txt` and the `merge_epic_branch` state's
  verdict-reuse logic ("skips its own `verify_epic_branch_before_merge`
  call... when the verdict is `passed` and the recorded SHA matches");
  the reuse guard already correctly falls back to a fresh check for any
  non-`passed` verdict (including a future `"error"` token), so no logic
  change is implied here, but the new token should be mentioned alongside
  the existing verdict vocabulary for a reader tracing this file [Agent 1
  finding, confirmed via direct read]

### Conventions in Force
- Loop YAML states that capture a plain shell/test/build command's exit
  code do so via an immediate `RC=$?` on the next line, avoiding any
  command-substitution ambiguity — evidence: `code-run-gate.yaml:266-267`,
  `general-task.yaml`'s `INSTALL_RC=$?`/`PYTEST_RC=$?`. No occurrence of
  this idiom in the codebase is applied to a `$(python3 <<'PYEOF' ...)`
  heredoc-in-command-substitution — that exact combination does not exist
  anywhere in `scripts/little_loops/loops/` today.
- The `cat file 2>/dev/null || echo <default>` idiom used throughout the
  loops tree (including `finalize`'s two verdict reads) always treats
  file-absence as the only failure signal; no variant elsewhere adds a
  `[ -s file ]` non-empty guard before the fallback.
- BUG-2594 (closed) is the closest prior precedent for a loop state
  silently mis-signaling by trusting untrusted/failure-mode output; its
  resolution added `set -o pipefail` around a teed subprocess, `on_error`
  routes for callers, and a regression test that executes the real action
  string against adversarial/crash input via `subprocess.run(["bash", "-c",
  script], ...)`.

### Tests
- `scripts/tests/test_builtin_loops.py::TestVerifyStateConfigReadShell`
  (~line 5530) and `::TestMergeEpicBranchConfigReadShell` (~line 5653)
  already extract-substitute-execute-assert the real `verify`/
  `merge_epic_branch` action strings via `subprocess.run(["bash", "-c",
  action], ...)` and read the resulting `verify-verdict.txt`/
  `epic-merge-verdict.txt`/`verify-returncode.txt` — the established
  harness for exercising these two states.
- Existing cases in that harness vary the *inner* `test_cmd`'s behavior
  (e.g. exit 2 → `collection_error`, a missing-script stderr string →
  `config_error`); none forces the heredoc's own python3 interpreter to
  crash (e.g. via an `ImportError`), so there is no existing regression
  coverage for this bug's exact failure mode.
- `test_finalize_surfaces_verify_verdict`,
  `test_finalize_verify_verdict_defaults_to_not_run`, and the
  `_run_finalize()` helper's `verify-verdict.txt` seeding never seed a
  *present-but-empty* file — the crash-to-empty-string path is untested
  end-to-end as well.

_Wiring pass added by `/ll:wire-issue`:_
- New crash-injection technique for `TestVerifyStateConfigReadShell`/
  `TestMergeEpicBranchConfigReadShell` (`test_builtin_loops.py:5530-5941`):
  neither class's existing `subprocess.run(["bash", "-c", action], ...)`
  calls pass `env=`, so a new regression case should follow
  `TestFinalizeDone`'s `env={**os.environ, "PATH": ...}` override pattern
  (`test_builtin_loops.py` ~line 6829) but override `PYTHONPATH` with a
  **shadow package**. NOTE: an empty-dir `PYTHONPATH` does NOT work —
  `PYTHONPATH` prepends to `sys.path` and never hides site-packages, so
  `import little_loops.config` still succeeds (verified 2026-08-30 on this
  machine). The verified technique: create
  `tmp_path / "shadow" / "little_loops" / "__init__.py"` (empty file), then
  pass `env={**os.environ, "PYTHONPATH": str(tmp_path / "shadow")}` — the
  shadow regular package wins module resolution and
  `import little_loops.worktree_utils` / `little_loops.config` raises
  `ModuleNotFoundError`, exactly this bug's failure mode. Because
  [[ENH-3365]] lands first, the heredocs will invoke
  `$${LL_PYTHON:-python3}`; the test env must also account for `LL_PYTHON`
  (leave it pointing at a real interpreter — the shadow-package trick
  crashes the import regardless of which interpreter runs, which is why it
  is preferred over a PATH-stub `python3`) [Agent 3 finding, corrected
  during review]
- `_run_finalize()` (`test_builtin_loops.py:4598-4719`) has **no**
  `epic_merge_verdict`/`epic-merge-verdict.txt` seeding parameter at all —
  unlike `verify_verdict`, finalize's read of `epic-merge-verdict.txt` has
  zero end-to-end test coverage today (present, absent, or empty-file
  cases). The new regression coverage in item 3 of Proposed Solution should
  add this parameter to `_run_finalize()` alongside the fix, not only cover
  `verify_verdict` [Agent 3 finding, confirmed via direct read of
  `_run_finalize`]
- Passing `verify_verdict=""` through `_run_finalize()`'s existing
  `if verify_verdict is not None:` guard already writes a present-but-empty
  file today (the guard is `is not None`, not truthiness) — the
  present-but-empty regression case may not need a harness change, just a
  new call site; verify this against the fixed `finalize` behavior once
  landed [Agent 3 finding]

## Sequencing

Implement **after [[ENH-3365]]** (`depends_on` declared in frontmatter).
ENH-3365 changes the same heredocs to invoke `$${LL_PYTHON:-python3}`;
landing this bug's regression test first would require rewriting it when
the interpreter-selection change lands. The shadow-package crash injection
(see Tests wiring) works under either interpreter, so the test written
after ENH-3365 needs no further changes.

## Impact

- **Priority**: P2 — mirrors BUG-2614's severity class: a config'd gate
  (test/lint verification, epic-branch merge) silently no-ops for an entire
  run and the run still reports `success`, with the miscue currently visible
  only via a stray empty-string field a human has to notice.

## Status

**Open** | Created: 2026-08-30 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-08-31T02:36:16 - `b1737911-44d2-40e3-9bd5-5d8a15c8f475.jsonl`
- `/ll:refine-issue` - 2026-08-31T02:24:08 - `80c0d0f5-6988-4121-a3c7-d08dabaee7ea.jsonl`
- `/ll:format-issue` - 2026-08-31T02:10:25 - `816b6544-6e69-4192-a4ac-f797f3d82975.jsonl`
