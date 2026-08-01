---
id: BUG-2954
title: Non-FSM tamper guard baseline spans implement phase, false-positives on TDD-mode
  test edits
type: BUG
priority: P2
captured_at: '2026-08-01T00:26:29Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2854
- ENH-2935
- ENH-2933
- BUG-2957
- ENH-2958
- BUG-2959
confidence_score: 98
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-2954: Non-FSM tamper guard baseline spans implement phase, false-positives on TDD-mode test edits

## Summary

`work_verification.py`'s non-FSM tamper guard (ENH-2935) rejects legitimate
test-file edits made during Phase 2 (implement) as "tampering" whenever an
issue's own required scope includes editing an *existing* test file. On a
`tdd_mode: true` project with the default `tamper_guard.policy: fail`, this
makes Phase 3 verification refuse to close any `ll-auto`/`ll-parallel`/
`ll-sprint`-driven issue that touches an existing test file — even when the
implementation is fully correct and all tests pass.

## Current Behavior

`issue_manager.py:921-926` captures `_baseline_sha` at the **start of Phase 2
(implement)** — before any code or tests are written — for an older, unrelated
purpose (detecting commits made since that point as evidence of work).
ENH-2935 reused this same `baseline_sha` as the tamper guard's "before"
snapshot reference (`work_verification.py:_run_non_fsm_tamper_guard`, via
`snapshot_test_paths_at_ref(repo_root, baseline_sha or "HEAD", ...)`). As a
result the guard's diff window spans the *entire implement+verify run*, not
just a dedicated verification step.

Observed failure: `ll-loop run autodev ENH-2937` — Phase 2 (`manage-issue`)
correctly implemented ENH-2937, including adding ~10 new tests to the
already-existing `scripts/tests/test_reconcile_issue_command.py` (in scope;
all 21 tests in that file passed). Phase 3 then logged:

```
Tamper guard (fail) failed: ['scripts/tests/test_reconcile_issue_command.py'] not resolved
REFUSING to mark ENH-2937 as completed: no code changes detected despite returncode 0
```

The second log line is also misleading: real changes existed
(`_detect_meaningful_changes` had already confirmed 5 changed files); the
tamper guard, not "no changes," is what vetoed the completion. The issue was
left `open` with uncommitted work, and autodev's finalize step reported it as
`inflight_at_finalize` / `unverified`, failing the run.

## Expected Behavior

Legitimate test-file edits made during Phase 2 implementation (required by
the issue's own scope, or written per `tdd_mode`) must not trip the guard,
while a genuine test weakening made anywhere in the same run still must.

ENH-2854's design constraint states the intended remedy as a *timing* fix:

> "Scope the guard to the verification step, not the whole issue run. With
> `commands.tdd_mode: true`, the implement phase legitimately writes tests
> before code. The snapshot is taken at verify-step start, never at issue
> start — otherwise every TDD run trips the guard."

**That remedy is only available to the FSM adapter, and does not transfer to
this path** (see Codebase Research Findings — "No bracketable verify step
exists on the non-FSM path"). The non-FSM orchestrators have exactly one
agent-executing phase, so no snapshot window can separate legitimate test
writes from tampering. The behavioral requirement above therefore has to be
met by changing *what counts as a finding*, not *when the snapshot is taken*:
a test-file edit is a tamper finding only when it **weakens** the suite
(assertions removed, test functions deleted, skip/xfail markers added, file
deleted), not merely because its bytes changed.

## Motivation

This silently blocks any TDD-mode `ll-auto`/`ll-parallel`/`ll-sprint`-driven
issue that legitimately requires editing an existing test file — the common
case for most feature/enhancement work, not an edge case. Every such run
burns a full implement cycle, then fails at the finalize step with a
misleading "no code changes detected" message, masking the true cause and
wasting the run's iteration budget diagnosing a phantom failure.

## Proposed Solution

**Keep** the Phase-2-start `baseline_sha` window and make the guard's
finding classifier content-aware, so hash-equality is no longer the
discriminator on this path.

Today `compare_snapshots` (`test_tamper_guard.py:127-146`) is a pure sha256
diff: *any* byte change to a candidate test file becomes a `modified`
finding, and the default `fail` policy rejects it. Adding tests and gutting
assertions are indistinguishable to it. The fix is to classify findings by
whether the edit reduced test strength:

- Add a strength metric over a test file's source (assertion count, test
  function count, skip/xfail marker count) and an `is_weakening(before,
  after)` predicate over two revisions of the same file.
- Add an optional `finding_filter` hook to `run_tamper_guard`, applied after
  `compare_snapshots` and `is_config` tagging but **before**
  `apply_tamper_policy`. The FSM adapter passes nothing and is bit-for-bit
  unaffected — its window is already correct by construction, so it keeps
  full byte-level strictness.
- `_run_non_fsm_tamper_guard` passes a weakening filter bound to the same
  `baseline_sha or "HEAD"` ref it already uses. Findings surviving the
  filter: `deleted` (always), `modified` where strength dropped, and any
  `is_config: true` finding (a `pytest.ini` / `pyproject.toml` edit changes
  which tests run at all and is not measurable by source strength, so it
  stays content-agnostic). `added` findings are filtered out — a new test
  file cannot weaken the suite, and added-file review is ENH-2853's
  pre-patch check's job, per `apply_tamper_policy`'s own docstring.
- Because `baseline_sha` keeps its current meaning, **no signature change
  reaches `verify_work_was_done`, `issue_manager.py`, or the Phase 2/Phase 3
  boundary.** The blast radius collapses to `test_tamper_guard.py` +
  `work_verification.py`.

Two independent defects ride along and must be fixed in the same change:

- `worker_pool.py` never passes `baseline_sha` at all, so its "before" is the
  worktree's `HEAD` *at verification time*. When Phase 2 committed inside the
  worktree, `before == after` and the guard is silently blind — a masked
  true positive that content-awareness does not fix. Capture the worktree's
  HEAD before Step 5 (`manage_result = self._run_with_continuation(...)`,
  `worker_pool.py:537`) and thread it through `_verify_work_was_done` as
  `baseline_sha`.
- `issue_manager.py:1125`'s `"no code changes detected despite returncode 0"`
  message fires when the tamper guard vetoed a run that *did* have changes
  (`_detect_meaningful_changes` already returned True). Distinguish the two
  rejection causes so the log names the real one.

### Alternatives considered

- *Re-scope the snapshot to the Phase 2/Phase 3 boundary* (the original
  proposal): rejected — Phase 3 executes no agent, so `before == after`
  unconditionally and the guard becomes inert. See Codebase Research
  Findings.
- *Add a real post-implement agent verify step to bracket*: faithful to
  ENH-2854's intent, but adds a phase and per-issue run cost to all three
  orchestrators. Captured separately as **ENH-2958**.
- *Default the non-FSM policy to `allow`*: concedes ENH-2935's enforcement
  on the CLI orchestrators entirely.
- *Flag test edits only when unaccompanied by source changes*: the motivating
  threat (weaken tests **and** edit source to "fix" them) slips straight
  through.

## Integration Map

### Files to Modify

_Rescoped after the design correction below — the original entries assumed a
new snapshot parameter threaded through both orchestrators, which the chosen
approach does not require._

- `scripts/little_loops/test_tamper_guard.py` — **primary change.** Add
  `TestStrength`, `measure_test_strength`, `is_weakening`,
  `read_paths_at_ref`, and `filter_weakening_findings`; add the optional
  `finding_filter` parameter to `run_tamper_guard`. Note this is the tamper-
  guard *core module*, not a test file, despite the `test_` prefix.
- `scripts/little_loops/work_verification.py` (`_run_non_fsm_tamper_guard`) —
  pass the weakening filter into `run_tamper_guard`. `verify_work_was_done`'s
  signature is **unchanged**; `baseline_sha` keeps its current meaning.
- `scripts/little_loops/parallel/worker_pool.py` — capture the worktree HEAD
  before Step 5 (~L537) and pass it through `_verify_work_was_done` (~L1212)
  into the `verify_work_was_done` call (~L1242-1244) as `baseline_sha`, which
  it currently omits entirely. _Wiring pass correction (`/ll:wire-issue`): the
  original path `scripts/little_loops/worker_pool.py` is wrong — the file
  lives under `scripts/little_loops/parallel/`._
- `scripts/little_loops/issue_manager.py` (~L1125) — split the
  `"no code changes detected despite returncode 0"` message so a tamper-guard
  veto is not reported as an absence of changes. **No Phase 2/Phase 3
  boundary change needed** under the chosen design.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/git_operations.py` (re-exports `verify_work_was_done`)
- `scripts/tests/test_subprocess_mocks.py` (patches `verify_work_was_done`
  via the `git_operations` re-export)

### Similar Patterns
- FSM adapter (`scripts/little_loops/fsm/executor.py`) already snapshots at
  guarded-state entry and compares at exit — same before/after shape, just
  scoped correctly by construction since it brackets a single state.

### Tests
- `scripts/tests/test_test_tamper_guard.py` — **primary new coverage.** Unit
  tests for `measure_test_strength` / `is_weakening` (added tests, removed
  assertions, deleted test function, added `skip`/`xfail`, unparseable-source
  conservative fallback) and for `run_tamper_guard` with vs. without
  `finding_filter`. _Supersedes the earlier wiring-pass note calling this file
  "confirmed unaffected" — that held only under the rejected snapshot-window
  design._
- `scripts/tests/test_work_verification.py` — extend the ENH-2935
  tamper-guard tests with the false-positive regression (legitimate additive
  edit to an existing test file passes) and keep the true-positive control.
  `TestVerifyWorkWasDoneBaselineSha` is **unaffected** — no signature change.
- `scripts/tests/test_issue_manager.py` — `mock_verify.assert_called_once_with(...)`
  at L2797 is **unaffected**; `verify_work_was_done`'s signature does not
  change. L2854's end-to-end control must pass unmodified (Step 7).
- `scripts/tests/test_worker_pool.py` — the five `_verify_work_was_done`
  tests (L1316-L1352) don't hardcode internal kwargs, so the new
  `baseline_sha` parameter won't break them;
  `test_verify_work_was_done_tamper_guard_trips` is the true-positive control
  and must keep passing. Add the additive-edit false-positive sibling and a
  worktree-committed-weakening true-positive case.
- `scripts/tests/test_fsm_executor.py:10865`
  (`test_tdd_mode_does_not_trip_guard_on_separate_verify_state`) — must pass
  unmodified; it proves the FSM path's byte-level strictness survived the
  `finding_filter` addition.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py` — `_verify_work_was_done` (
  `scripts/little_loops/parallel/worker_pool.py:1212`) is directly exercised
  here (`test_verify_work_was_done_accepts_code_changes` L1316,
  `test_verify_work_was_done_rejects_no_changes` L1325,
  `test_verify_work_was_done_rejects_excluded_only` L1334,
  `test_verify_work_was_done_respects_config` L1343,
  `test_verify_work_was_done_tamper_guard_trips` L1352). None hardcode the
  internal call's kwargs (unlike `test_issue_manager.py`'s
  `mock_verify.assert_called_once_with(...)`), so they won't break on a
  signature change alone, but `test_verify_work_was_done_tamper_guard_trips`
  is `worker_pool.py`'s true-positive control case and must keep passing.
  Also add the `worker_pool.py`-side sibling of the new "legitimate Phase 2
  edit to an existing test file does not trip the guard" regression test
  here (Implementation Step 3a currently only names the `issue_manager.py`
  path).
- `scripts/tests/test_test_tamper_guard.py` — confirmed **unaffected**: it
  tests `snapshot_test_paths`/`snapshot_test_paths_at_ref` as isolated
  primitives against paths/refs it constructs itself, not the boundary at
  which callers invoke them. No edit needed; noted so an implementer doesn't
  have to re-derive this.
- `scripts/tests/test_fsm_executor.py:10865`
  (`test_tdd_mode_does_not_trip_guard_on_separate_verify_state`) — existing
  FSM-side test covering the equivalent correct behavior; use as the pattern
  for the new non-FSM regression test. Note it covers a **newly added** test
  file, while this bug's reproduction is an edit to an **existing** test
  file (`compare_snapshots`'s "modified" finding kind, not "added") — the
  new non-FSM test should cover the modified case to match the actual
  reproduction.

### Documentation
- N/A for `docs/reference/CONFIGURATION.md` (`tamper_guard.policy` describes
  policy semantics only, unaffected) and `docs/guides/LOOPS_GUIDE.md`
  (FSM/non-FSM independence prose stays accurate) — spot-check only, no
  forced edit.

_Wiring pass added by `/ll:wire-issue`, **superseded** by the design
correction below:_ the wiring pass predicted `docs/reference/API.md`
(`### verify_work_was_done`, ~L2339-2387) would go stale in three places —
the signature block, the "before is reconstructed from git history via
`baseline_sha`" prose, and the `baseline_sha` parameter description. Under
the chosen design **all three stay accurate**: the signature is unchanged,
"before" is still reconstructed from git history at `baseline_sha`, and
`baseline_sha` remains the tamper guard's "before" reference. The only
API.md edit needed is a sentence noting that non-FSM findings are now
filtered to weakening edits. Do not perform the three rewrites the wiring
pass described.

### Configuration
- N/A — no new config key; `tamper_guard.policy` semantics are unchanged,
  only the snapshot window.

### Codebase Research Findings

_Added by `/ll:reconcile-issue` on 2026-07-31 — this finding invalidated the
issue's original Proposed Solution and rescoped the Integration Map:_

- **No bracketable verify step exists on the non-FSM path — the original
  "move the snapshot to the Phase 2/Phase 3 boundary" fix would make the
  guard permanently inert.** Phase 3 in `issue_manager.py:1049-1136`
  executes no agent: it is `verify_issue_completed` → `check_content_markers`
  → `verify_work_was_done` → `complete_issue_lifecycle`, with no
  `run_claude_command`, no `run_with_continuation`, and no subprocess that
  could modify a file (verified by grep over that range). A snapshot taken at
  the boundary is therefore compared against byte-identical on-disk state, so
  `compare_snapshots` returns zero findings on every run.
  - The FSM adapter works precisely because it brackets *a separate verify
    state's own action dispatch* (`fsm/executor.py:1407-1420`) — a genuine
    post-implement agent invocation. The non-FSM orchestrators have exactly
    one agent-executing phase (Phase 2), and it is where both legitimate TDD
    test writes and genuine tampering occur. The asymmetry is structural, not
    an oversight in the call site.
  - The guard's whole discriminating power on this path is the window:
    `test_tamper_guard.py:127-146` is a pure sha256 diff with no semantic
    weakening detection. Removing the window removes the guard.
  - This directly contradicts the pre-existing note below that
    `test_issue_manager.py:2854` "must keep passing under any fix." Under the
    original proposal it **cannot** pass: that test weakens `tests/test_x.py`
    uncommitted *before* `process_issue_inplace` runs with Phase 2 mocked, so
    a boundary snapshot already contains the weakened bytes. An implementer
    following the original steps would hit a flat contradiction and most
    likely resolve it by deleting the control test — silently reverting
    ENH-2935. The content-aware design keeps it passing: a gutted assertion
    is a strength drop and still trips.

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`snapshot_test_paths()` already exists and is directly reusable** —
  `scripts/little_loops/test_tamper_guard.py:60` hashes live on-disk bytes
  for a given path list (`snapshot_test_paths(paths, repo_root) ->
  TamperSnapshot`). This is exactly the in-memory snapshot mechanism the
  Proposed Solution speculates would need to be built — it doesn't need to
  be written, only called at the new Phase 2/Phase 3 boundary in
  `issue_manager.py` and `worker_pool.py` instead of reconstructing from git
  via `snapshot_test_paths_at_ref` (`test_tamper_guard.py:68`).
- **`scripts/little_loops/test_tamper_guard.py` is the tamper-guard core
  implementation module, not a test file** despite its `test_` prefix (it
  lives in `scripts/little_loops/`, not `scripts/tests/`). The actual pytest
  suite for it is `scripts/tests/test_test_tamper_guard.py`. The Integration
  Map's "Files to Modify" bullet for `test_tamper_guard.py` should be read as
  this core module, not a test suite — worth calling out explicitly to avoid
  an implementer skipping it as "just a test file."
- **FSM adapter's exact snapshot-on-entry/compare-on-exit bracket** (the
  pattern to model the fix after) is `scripts/little_loops/fsm/executor.py:1407-1474`:
  `_tamper_before = snapshot_test_paths(...)` is captured immediately before
  `state.action` dispatch (not at any earlier phase/state), and
  `run_tamper_guard(_tamper_before, ...)` runs right after `_evaluate()`. The
  inline comment at lines 1407-1411 states the rationale in nearly the same
  words as this issue's Expected Behavior section.
- **`worker_pool.py`'s gap is structurally different from `issue_manager.py`'s,
  not just "the same fix twice"**: `_verify_work_was_done` (`worker_pool.py:1212`)
  never passes `baseline_sha` at all (`work_verification.py` call at
  `worker_pool.py:1242-1244` omits it), so `_run_non_fsm_tamper_guard` always
  falls back to the worktree's `"HEAD"` at verification-call time
  (`worker_pool.py:596`, right after Phase 2's `manage_result` returns around
  line 537-541). Whether this false-positives depends on whether Phase 2 already
  committed its test edits in the worktree: if committed, `before == after`
  (masks a genuine tamper rather than false-positiving); if uncommitted
  (equally common), it false-positives the same way `issue_manager.py` does.
  `worker_pool.py` has no existing secondary reference to repurpose —
  `baseline_head_sha` (`worker_pool.py:361`, via `_get_main_head_sha()`) is
  captured against the **main repo** before the worker starts and is used
  only for `_detect_committed_leaks`/`_recover_committed_leaks`
  (`worker_pool.py:580-591`, `1500`, `1538`) — an unrelated "did the agent
  commit to main instead of the worktree" concern. Do not conflate it with
  the new verify-boundary snapshot.
- **Existing tests with call-signature/behavior dependencies on the fix**:
  - `scripts/tests/test_issue_manager.py:2797`
    (`test_baseline_sha_passed_to_verify_work_was_done`) asserts
    `mock_verify.assert_called_once_with(mock_logger, baseline_sha=test_sha,
    config=mock_config)` — will need updating once a new parameter threads
    through this call.
  - `scripts/tests/test_issue_manager.py:2854`
    (`test_tamper_guard_trips_end_to_end_no_fsm_involved`) is the existing
    genuine-tampering control case (real git repo, test committed before
    `process_issue_inplace` runs, then weakened uncommitted during simulated
    Phase 2) — mechanically identical to the false-positive scenario this bug
    describes except for *intent*. This test must keep passing under any fix;
    it's the regression guard against over-correcting into "the guard never
    trips."
  - `scripts/tests/test_work_verification.py`'s
    `TestVerifyWorkWasDoneBaselineSha` (lines 429-509) exercises only
    `_detect_meaningful_changes`'s BUG-1538 commit-detection semantics, not
    `config`/the tamper guard — unaffected by a tamper-guard-specific second
    parameter as long as `baseline_sha`'s original meaning is preserved for
    that path.

### Codebase Research Findings (2026-08-01)

_Added by `/ll:refine-issue`:_

- **BUG-2959 duplicates this issue's own Implementation Step 4 / worker_pool.py
  fix — now cross-linked in `relates_to`.** BUG-2959 ("worker_pool drops
  baseline_sha from verify_work_was_done") describes the exact same defect
  and the exact same remedy as this issue's Step 4 and Integration Map entry
  for `scripts/little_loops/parallel/worker_pool.py`: capture the worktree's
  pre-implement `HEAD`/commit and thread it into `_verify_work_was_done` →
  `verify_work_was_done` as `baseline_sha`, which the call at
  `worker_pool.py:1242-1244` currently omits entirely. BUG-2959 already listed
  this issue in its own `relates_to` but the link wasn't reciprocated here.
  **Implementer note**: fixing Step 4 in this issue's PR will very likely
  close BUG-2959 as a side effect (or vice versa) — check BUG-2959's status
  before starting Step 4 to avoid double implementation, and close whichever
  issue doesn't end up carrying the actual commit.
- **`fsm/executor.py`'s tamper-guard bracket has grown since this issue's
  Program Design/Codebase Research Findings sections were last written** —
  commit `9b5991dc` (BUG-2962, already landed on `main`) added a second
  compare-on-exit call site for `next:`-chained routing. The bracket now
  spans `_execute_state` (`L1408`) through a new `_check_tamper_guard` call
  at `L1484-1488` (routing-chain path) and the original compare-on-exit call
  now at `L1537-1541` (on_yes/on_no/on_error path), not `L1407-1474` as
  previously cited. The shared logic was extracted into a `_check_tamper_guard`
  helper (`L1336-1384+`). This drift is incidental to BUG-2954's own fix (the
  FSM path stays byte-strict either way, `finding_filter` is never passed to
  it) — noted only so a future citation of "the FSM bracket" points at the
  right lines.
- **In-repo precedents for the Program Design's proposed AST-parsing
  functions** — `measure_test_strength` doesn't need to invent its `ast`
  error-handling shape from scratch:
  - `scripts/little_loops/codequery/fallback.py:_parse_ast()` is the closest
    precedent: `ast.parse(source)` wrapped in `try/except SyntaxError: return
    None`, with `OSError` on file-read handled as a separate, earlier
    `try/except`. Its callers (`defines()`, `callees_of()`) treat `None` as
    "skip this file" — the same conservative-fallback contract this issue's
    Program Design already specifies for `measure_test_strength`.
  - `scripts/little_loops/observability/audit.py:_ast_extract_event_types()`
    and `_audit_python_file()` show the sibling shape for a source-string
    (not path) entry point, with the explicit documented convention: "Errors
    (file unreadable, `ast.parse` failure) are silently swallowed — a single
    bad file must not abort the whole audit."
  - No existing code detects `pytest.mark.skip`/`xfail` decorators anywhere
    in the codebase (`decorator_list` inspection for `skip_markers` is a
    pattern novel to this fix) — but `fallback.py`'s `defines()` already
    walks `ast.FunctionDef` node attributes (`node.name`, `node.lineno`) in
    the same access style `node.decorator_list` would use.
  - `TamperFinding`/`TamperReport` in this same file (`test_tamper_guard.py`)
    are the style precedent for the new `TestStrength` dataclass: flat
    `int`/`str`/`Literal` fields, `field(default_factory=...)` only for
    mutable-container fields, one-line docstring, module-level (not nested).
  - `FindingFilter`'s `Callable[[...], ...] | None = None` typing matches the
    house convention (`fsm/runners.py`'s `on_output_line`,
    `worker_pool.py`'s `on_complete`/`on_usage`) — modern union syntax, not
    `Optional[Callable[...]]`. No existing hook in the codebase *filters a
    list* before a downstream enforcement step the way `finding_filter` will
    (it's a novel shape here), but the typing/naming convention to match is
    established.
  - No test in the codebase currently exercises the unparseable-but-readable
    (`SyntaxError`, as opposed to unreadable/`OSError`) branch of an
    ast-parsing helper — `test_des_audit.py`'s
    `test_unreadable_file_does_not_crash` only covers the `OSError` case (a
    directory disguised as a `.py` file). The new
    `measure_test_strength`/unparseable-source test in
    `test_test_tamper_guard.py` will be the first in-repo test of that
    specific fallback path; follow `test_test_tamper_guard.py`'s existing
    `tmp_path` + `write_text(...)` fixture convention
    (`TestSnapshotTestPaths.test_hashes_existing_file_content`).

## Program Design

### Types

- `TestStrength: dataclass` — `assertions: int`, `test_functions: int`,
  `skip_markers: int`
- `FindingFilter: TypeAlias = Callable[[list[TamperFinding]], list[TamperFinding]]`

### Signatures

In `scripts/little_loops/test_tamper_guard.py`:

- `measure_test_strength(source: str, path: str) -> TestStrength | None` —
  `ast`-parses Python sources, counting `ast.Assert` nodes plus
  `self.assert*` / `pytest.raises` calls, `FunctionDef`s named `test*`, and
  `skip`/`xfail` decorators or `pytest.skip(...)` calls. Returns `None` for a
  non-Python path or an unparseable source, which callers must treat
  conservatively (finding kept).
- `is_weakening(before_src: str, after_src: str, path: str) -> bool` — True
  when assertions or test functions decreased, or skip markers increased, or
  either side is unmeasurable.
- `read_paths_at_ref(repo_root: Path, ref: str, paths: list[str]) -> dict[str, str | None]`
  — the text-returning sibling of the existing `snapshot_test_paths_at_ref`
  (which hashes); factor the shared `git show {ref}:{path}` call so there is
  one implementation.
- `filter_weakening_findings(findings: list[TamperFinding], repo_root: Path, ref: str) -> list[TamperFinding]`
  — keeps every `deleted` finding, every `is_config` finding, and each
  `modified` finding whose `is_weakening(...)` is True; drops `added`.
- `run_tamper_guard(before, changed_files, config, policy, repo_root, finding_filter: FindingFilter | None = None) -> TamperReport`
  — applies `finding_filter` after `compare_snapshots` and `is_config`
  tagging, before `apply_tamper_policy`. Defaults to `None` so the FSM
  adapter's behavior is unchanged.

In `scripts/little_loops/parallel/worker_pool.py`:

- `_verify_work_was_done(self, changed_files, issue_id, issue_filename="", worktree_path=None, baseline_sha: str | None = None) -> tuple[bool, str]`
  — new trailing keyword-only-by-convention parameter, forwarded to
  `verify_work_was_done`.

`verify_work_was_done` and `_run_non_fsm_tamper_guard` keep their current
signatures.

### Call Path

Non-FSM (new filter applied):

`issue_manager.process_issue_inplace` / `worker_pool._process_issue`
→ `work_verification.verify_work_was_done`
→ `work_verification._run_non_fsm_tamper_guard`
→ `test_tamper_guard.run_tamper_guard(..., finding_filter=partial(filter_weakening_findings, repo_root=..., ref=baseline_sha or "HEAD"))`
→ `filter_weakening_findings` → `read_paths_at_ref` + `measure_test_strength`
→ `apply_tamper_policy`

FSM (unchanged — no `finding_filter`, full byte-level strictness):

`fsm.executor._run_state` → `snapshot_test_paths` → `run_tamper_guard`
→ `apply_tamper_policy`

## Implementation Steps

1. In `test_tamper_guard.py`, add `TestStrength`, `measure_test_strength`,
   `is_weakening`, and `read_paths_at_ref` (factoring the shared
   `git show {ref}:{path}` call out of `snapshot_test_paths_at_ref` rather
   than duplicating it).
2. Add `filter_weakening_findings` and the optional `finding_filter`
   parameter to `run_tamper_guard`, applied after `is_config` tagging and
   before `apply_tamper_policy`. Verify the FSM path passes nothing and is
   byte-for-byte unaffected.
3. In `work_verification._run_non_fsm_tamper_guard`, pass the weakening
   filter bound to the same `baseline_sha or "HEAD"` ref already in use.
   No signature change to `verify_work_was_done`.
4. In `worker_pool.py`, capture the worktree HEAD before Step 5 (~L537) and
   thread it through `_verify_work_was_done` (~L1212) into the
   `verify_work_was_done` call (~L1242-1244) as `baseline_sha`, closing the
   masked-true-positive gap where a worktree-committed weakening is invisible.
5. In `issue_manager.py:1125`, split the rejection message so a tamper-guard
   veto is not reported as `"no code changes detected"`.
6. Add regression tests (see Tests below):
   (a) unit coverage for `measure_test_strength` / `is_weakening` — added
   tests, removed assertions, deleted test function, added `skip`, and the
   unparseable-source conservative fallback;
   (b) `run_tamper_guard` with and without `finding_filter`, proving the FSM
   default is unchanged;
   (c) the false-positive regression: legitimate Phase 2 edits **adding**
   cases to an existing test file do not trip the guard — for both the
   `issue_manager.py` path (`test_work_verification.py`) and the
   `worker_pool.py` path (`test_worker_pool.py`);
   (d) the true-positive controls still trip, including the new
   worktree-committed-weakening case for `worker_pool.py`.
7. Confirm `test_issue_manager.py:2854`
   (`test_tamper_guard_trips_end_to_end_no_fsm_involved`) passes **unmodified**
   — it is the primary guard against over-correcting into an inert guard, and
   under this design it must not need editing.
8. Run the full suite and confirm no regression in existing tamper-guard
   coverage from ENH-2933/ENH-2934/ENH-2935.

### Wiring Phase (added by `/ll:wire-issue`, rescoped)

9. Update `docs/reference/API.md`'s `### verify_work_was_done` section
   (~L2339-2387) with a sentence noting non-FSM findings are filtered to
   weakening edits. The signature block, the "before"-reconstruction prose,
   and the `baseline_sha` parameter description all remain accurate under
   this design and must **not** be rewritten as the original wiring pass
   predicted.

## Impact

- **Priority**: P2 - Silently blocks completion of any TDD-mode issue that
  legitimately edits an existing test file; affects the default
  configuration of every project using `ll-auto`/`ll-parallel`/`ll-sprint`
  with `tdd_mode: true` and no explicit `tamper_guard.policy` override.
- **Effort**: Medium - requires re-threading a new snapshot reference through
  two orchestrators (`issue_manager.py`, `worker_pool.py`) and the shared
  `work_verification.py` hook, plus test updates in the ENH-2935 coverage.
- **Risk**: Medium - touches the shared Phase 3 verification chokepoint used
  by all three orchestrators; must not weaken the guard's actual tamper
  detection (post-implementation test weakening) while fixing the false
  positive.
- **Breaking Change**: No

## Steps to Reproduce

1. Set `commands.tdd_mode: true` (or use a project where it's already set)
   and leave `tamper_guard.policy` unset (default `fail`).
2. Create/select an issue whose correct implementation requires adding or
   modifying test cases in an *existing* test file (not a brand-new file).
3. Run `ll-loop run autodev <ISSUE-ID>` (or `ll-auto`) and let it implement
   the issue correctly, including the test-file edit.
4. Observe Phase 3 verification log a `Tamper guard (fail) failed: [...]`
   line naming the legitimately-edited test file, followed by "REFUSING to
   mark ... as completed: no code changes detected despite returncode 0"
   even though real changes are present. The issue stays `open`/uncommitted
   and the run reports the issue as `inflight_at_finalize` / `unverified`.

## Root Cause

- **File**: `scripts/little_loops/work_verification.py`
- **Anchor**: in function `_run_non_fsm_tamper_guard()`, called from
  `verify_work_was_done()`
- **Cause**: The guard's finding classifier is a pure sha256 diff
  (`test_tamper_guard.compare_snapshots`), so *any* byte change to a
  candidate test file becomes a `modified`/`added` finding that the default
  `fail` policy rejects. The FSM adapter tolerates that bluntness because its
  snapshot window brackets a single post-implement verify state, where no
  legitimate test writing occurs. The non-FSM path reuses the same classifier
  with a window spanning Phase 2 (`baseline_sha`, `issue_manager.py:921-926`)
  — the one phase where legitimate, in-scope, TDD-mode test writes happen —
  so legitimate work and tampering are indistinguishable to it.
- **Why the obvious fix does not apply**: narrowing the window is not
  available here, because the non-FSM path has no agent-executing
  verification step to bracket (see Codebase Research Findings). The
  classifier, not the window, has to carry the discrimination.

## Error Messages

```
Tamper guard (fail) failed: ['scripts/tests/test_reconcile_issue_command.py'] not resolved
REFUSING to mark ENH-2937 as completed: no code changes detected despite returncode 0
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-31_

**Readiness Score**: 95/100 → STOP — ADDRESS GAPS (Program Design gate override)
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- ~~`## Program Design` section is missing~~ — **RESOLVED 2026-07-31.** The
  section now specifies the strength-metric types, the `finding_filter` hook,
  and both call paths at the identifier level.
- ~~Proposed Solution re-scopes the snapshot to the Phase 2/Phase 3
  boundary~~ — **RESOLVED 2026-07-31.** A design review found that remedy
  makes the guard inert on this path (Phase 3 executes no agent) and
  contradicts the issue's own "`test_issue_manager.py:2854` must keep
  passing" invariant. Replaced with the content-aware weakening classifier;
  the reasoning is recorded in Codebase Research Findings so the rejected
  approach is not re-proposed.

_The original gate remedy suggested populating Program Design against
`verify_work_was_done`'s "new verify-step-start snapshot parameter." That
parameter no longer exists in the design — there is no signature change to
`verify_work_was_done`._

## Session Log
- `/ll:ready-issue` - 2026-08-01T05:11:28 - `89aac650-126a-40ba-aa5b-740691da5de0.jsonl`
- `/ll:confidence-check` - 2026-08-01T05:09:38 - `56dd8eba-fb22-4538-a2cd-28267172bda3.jsonl`
- `/ll:refine-issue` - 2026-08-01T05:01:58 - `dbb7143c-aaa2-4903-aa2e-cc981ada388b.jsonl`
- `/ll:confidence-check` - 2026-07-31T12:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec700af2-9c25-4180-8af6-ec476533987d.jsonl`
- `/ll:reconcile-issue` - 2026-07-31 - design review: rejected the
  snapshot-window remedy as structurally inert on the non-FSM path, adopted
  the content-aware weakening classifier, added `## Program Design`
- `/ll:confidence-check` - 2026-07-31T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3430647f-ce57-4391-9e90-cb2655c780ff.jsonl`
- `/ll:wire-issue` - 2026-08-01T00:53:00 - `7d8448a2-403a-404b-bcac-da3a2291f6a2.jsonl`
- `/ll:refine-issue` - 2026-08-01T00:46:57 - `1f083837-7a7f-488c-81ba-a13b0bc651b7.jsonl`
- `/ll:capture-issue` - 2026-08-01T00:26:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6fbac205-468a-44ce-b7fb-4626b0ac42e4.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
