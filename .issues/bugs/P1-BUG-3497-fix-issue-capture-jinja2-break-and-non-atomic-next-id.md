---
id: BUG-3497
title: 'Fix issue capture: issue_capture jinja2 break and non-atomic next-id'
type: BUG
priority: P1
status: open
discovered_date: '2026-09-16'
labels:
- issue-capture
- concurrency
- hub
decision_needed: true
learning_tests_required:
- jinja2
---

# Fix issue capture: issue_capture jinja2 break and non-atomic next-id

## Summary

Two defects make the issue-filing path unsafe, and together they have caused
two ID collisions in production use: on 2026-09-15 an operator filed three
issues by hand while concurrent automated processes allocated the same IDs
(the files had to be renumbered afterward), and on 2026-09-16 a second
collision occurred between two concurrent automated allocators, again forcing
renumbering.

1. **`issue_capture` is broken.** The atomic capture path returns
   `No module named 'jinja2'` and cannot run, forcing callers onto the manual
   `next-id` + write path.
2. **`ll-issues next-id` + manual write is non-atomic.** `next-id` reads the
   highest ID, but nothing locks or reserves that ID between the read and the
   file write. Concurrent automated processes (research mining, reconcile
   sweeps) allocate in the same window, so any gap is a collision window.

## Current Behavior

- The issue_capture MCP tool is reported to fail with
  `No module named 'jinja2'`, forcing callers onto the manual
  `ll-issues next-id` + hand-written file path instead. Its handler is
  `_tool_issue_capture` in `little_loops/mcp_server/tools.py`, which calls
  `create_issue` in `little_loops/cli/issues/create.py`.
- `ll-issues next-id` (`cmd_next_id` in `little_loops/cli/issues/next_id.py`,
  which calls `get_next_issue_number` in `little_loops/issue_parser.py`) only
  reads the current highwater ID; nothing reserves it. Two callers on that
  manual path (or a manual write racing an
  automated allocator) can read the same number and write colliding files,
  as happened twice in production on 2026-09-15 and 2026-09-16.

## Expected Behavior

- `issue_capture` files an issue with a fresh, unique ID end-to-end without
  raising an import error.
- Two concurrent captures, or a capture racing a manual `next-id` + write,
  can never produce the same ID.
- `next-id` is either made atomic or clearly documented as a read-only hint
  that must not be used for allocation.

## Steps to Reproduce

1. Call the `issue_capture` MCP tool (or invoke it via whatever harness path
   currently reaches `_tool_issue_capture`) from the environment where the
   failure was observed (the MCP server process) — observe
   `No module named 'jinja2'` instead of a created issue.
   **Verification note (added during formatting):** `create_issue` and its
   `_render_issue_content` helper have no `jinja2` import in the current
   codebase (`little_loops/cli/issues/create.py` uses
   `little_loops.issue_template.assemble_issue_body`, not a Jinja renderer),
   and `scripts/pyproject.toml` already declares `jinja2>=3.1` as of
   2026-09-15 (FEAT-3036) — one commit before this issue's discovery date.
   Reproduce this step fresh before implementing; the failing import may be
   coming from a different call path (e.g. `ll-artifact render`, which does
   import `jinja2` in `artifact_templates.py`) or from a stale environment
   rather than a missing dependency declaration.
2. Run `ll-issues next-id` twice in quick succession from two separate
   processes (or race one `next-id` call against an automated allocator that
   calls `create_issue` directly) and write issue files by hand using each
   returned number — observe both processes reporting the same number.

## Root cause (confirmed 2026-09-16)

- **jinja2:** `little_loops/cli/artifact/templatize.py` and `dashboard.py`
  import jinja2 and render the `.j2` templates under `little_loops/templates/`,
  but jinja2 is NOT declared in `pyproject.toml`. So `issue_capture` works where
  jinja2 is transitively present (the Hermes venv) and fails with
  `No module named 'jinja2'` in a leaner environment (the MCP server). Fix: add
  `jinja2` to the `pyproject.toml` dependencies.
- **next-id:** `little_loops/cli/issues/__init__.py` (the `ll-issues next-id`
  subcommand) reads the max ID with no lock or reservation before the file
  write. Fix: reserve-then-write under a lock, or an ID-reservation table, so
  two concurrent allocators can never hand out the same ID.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- Confirmed via repo-wide search: zero hits for `No module named 'jinja2'` or `ModuleNotFoundError.*jinja2` anywhere in the source tree (the only matches are unrelated lines inside a recorded test fixture transcript, `scripts/tests/fixtures/codex/rollout-interactive.jsonl`).
- Confirmed: `jinja2` is imported only in `little_loops/artifact_templates.py:22-23` and `little_loops/cli/artifact/dashboard.py:368` (both back `ll-artifact render`); `create_issue`, `_render_issue_content` (`little_loops/cli/issues/create.py`), and `_tool_issue_capture` (`little_loops/mcp_server/tools.py:258-268`) import neither `jinja2` nor those two modules.
- Confirmed: no `except ImportError`/`except ModuleNotFoundError` guard exists anywhere for `jinja2` — it is declared unconditionally in `[project].dependencies` (`scripts/pyproject.toml`), not gated as an optional extra. Compare `mcp`/`otel`, which ARE gated as extras with a lazy import plus an actionable error message (`little_loops/mcp_server/__init__.py`; `little_loops/transport.py:1627-1644`) — the codebase does have a convention for optional-dependency gating, and jinja2 does not use it.
- Together these corroborate rather than resolve the "Open question" already recorded under Program Design → Call Path: nothing in the current call path can raise `No module named 'jinja2'` for `issue_capture`. Reproduce Steps to Reproduce #1 fresh before implementing — if it no longer reproduces, this half of the bug is likely already resolved by FEAT-3036's `pyproject.toml` change (2026-09-15) and the stated fix ("add jinja2 to pyproject.toml") should be dropped rather than re-applied.

## Acceptance

- `issue_capture` files an issue with a fresh, unique ID end-to-end.
- Two concurrent captures (or a capture racing a manual write) can never produce
  the same ID.
- `next-id` is either atomic or clearly documented as a read-only hint.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

**Option A**: Make `get_next_issue_number`/`cmd_next_id` (`little_loops/issue_parser.py`, `little_loops/cli/issues/next_id.py`) acquire `.id-alloc.lock` before reading, mirroring `create_issue`'s existing lock-then-allocate-then-exclusive-write pattern (`little_loops/cli/issues/create.py:406-499`, `acquire_lock` in `little_loops/file_utils.py:87`). This directly revisits an approach `.issues/bugs/P2-BUG-1364-duplicate-issue-id-hook-toctou-race-condition.md` (done) evaluated as its "Option C" and rejected, for two stated reasons: `IssueParser._generate_id_from_filename()`'s read-only fallback calls `get_next_issue_number()` during ordinary parsing (e.g. every `ll-issues list`), which would spuriously create reservations under a naive lock-and-reserve scheme; and a "batch-increment pattern documented across five commands" was said to defeat atomicity regardless. Neither objection has been re-evaluated against `create_issue`'s lock design, which already resolves the first concern (its lock is held only around the allocate-and-write, not around read-only parsing) — but the second (batch-increment callers) has not been checked against this issue's scope.

**Option B**: Leave `next-id` unlocked and explicitly document it as a read-only hint (the wording this issue's own Expected Behavior already allows), and instead close the collision window by migrating every automated allocator currently doing "next-id read + hand-written file" (the manual/hook path this issue's Current Behavior describes) onto the already-atomic `create_issue()` (`little_loops/cli/issues/create.py`). This requires identifying and migrating those callers rather than changing `next_id.py`/`issue_parser.py` at all.

> **Selected:** Option B — reuses `create_issue()`'s already-proven lock design; Option A cannot actually close the race it targets. See Decision Rationale below.

**Recommended**: Option B — it reuses `create_issue`'s already-proven lock design (matches Impact → Risk: Low) without reopening BUG-1364's rejected reservation semantics, and satisfies the Expected Behavior bullet that already accepts "next-id ... clearly documented as a read-only hint" as a valid resolution. Option A is viable but is not the "direct fix" the current Impact → Effort estimate assumes — it requires re-litigating BUG-1364's objections, not just copying `create_issue`'s lock pattern.

### Decision Rationale

**Selected:** Option B — leave `next-id` unlocked and documented as a read-only hint; migrate automated allocators onto `create_issue()`.

**Reasoning:** Option A's lock can only span `cmd_next_id`'s own process lifetime — it prints and exits before the caller's separate file write happens, so it cannot close the actual "next-id read + hand-written file" race this issue describes, and it reopens BUG-1364's rejected reservation semantics while leaving the still-unremediated batch-increment instruction in `commands/scan-codebase.md` untouched. Option B reuses `create_issue()`'s already-proven `.id-alloc.lock` pattern (lock-then-allocate-then-exclusive-write) without touching the shared, hot-path `get_next_issue_number`/`_generate_id_from_filename` read path. It is not fully complete — `little_loops/cli/issues/normalize.py`'s `_alloc()` helper reassigns IDs on existing files via an unlocked `get_next_issue_number()` call and is structurally incompatible with `create_issue()`'s from-a-spec creation shape — but that residual gap is bounded and known, versus Option A's structural non-fix of the primary collision window.

**Scoring:**

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 1 | 3 |
| Simplicity | 2 | 1 |
| Testability | 1 | 2 |
| Risk | 1 | 1 |
| **Total** | **5/12** | **7/12** |

**Key evidence:**
- Option A: `cmd_next_id` (`little_loops/cli/issues/next_id.py:23-38`) is a separate CLI invocation that prints and exits — a lock held for its duration cannot span into a later, separate file write, so it doesn't close the race it targets. The hand-increment batch instruction BUG-1364 flagged for removal is still present verbatim in `commands/scan-codebase.md:230` (and mirrored in `.gemini/`, `.kimi-code/`, `.qwen/` copies).
- Option B: `create_issue()` (`little_loops/cli/issues/create.py:406-499`) is the only clean drop-in migration target found — `scripts/little_loops/sync.py:_create_local_issue()` (line 660/681/753) is a genuine unlocked "read-then-hand-write" caller with a `BRConfig` already in scope. `little_loops/cli/issues/normalize.py`'s `_alloc()` (lines 302-309, 461) is a second unlocked caller but reassigns IDs on existing files rather than creating from a spec, so it is out of scope for a `create_issue()`-shaped migration and remains a residual gap to track separately.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

**Files to Modify**
- `little_loops/cli/issues/next_id.py` — `cmd_next_id()` (line 23) calls `get_next_issue_number` outside any lock; candidate target for Option A (add locking) or for a doc-only change under Option B.
- `little_loops/issue_parser.py` — `get_next_issue_number()` is the shared read-only highwater scan called by both the locked (`create_issue`) and unlocked (`cmd_next_id`) paths; also called by `IssueParser._generate_id_from_filename()`'s fallback during ordinary read-only parsing (e.g. every `ll-issues list`) — this is the call site BUG-1364 flagged as the reason a naive reserve-on-read scheme over-reserves.
- `little_loops/cli/issues/__init__.py` — imports `cmd_next_id` (line 83) and dispatches `ll-issues next-id` to it (line 1011); the CLI help/docstring here is where a "read-only hint" warning would land under Option B.
- `little_loops/cli/issues/create.py` — `create_issue()` (lines 406-499) is the existing atomic path; unmodified under Option B except as the target callers migrate onto.

**Dependent Files (Callers/Importers)**
- `scripts/tests/test_ll_issues_create.py:17` — imports and exercises `create_issue` directly.
- `little_loops/cli/issues/scaffold_epic.py:19,84-88` — a second, independent caller of `.id-alloc.lock` for epic scaffolding, outside `create_issue`.
- `little_loops/issue_lifecycle.py:826-831` — acquires the same cross-tree `.id-alloc.lock` as `create_issue()` for a different mutation path.
- `little_loops/mcp_server/tools.py:258-268,811` — `_tool_issue_capture` calls `create_issue`/`render_issue_preview`; this is the atomic path the bug report says currently fails with the jinja2 import error.

**Conventions in Force**
- ID allocation in this codebase follows a lock-then-allocate-then-exclusive-write shape: hold `.id-alloc.lock` (`file_utils.py:acquire_lock`) around both the highwater read and an exclusive-create write (`open(path, "x")`), retrying on `FileExistsError` — evidence: `create_issue` (`little_loops/cli/issues/create.py:406-499`).
- Issue-tree mutation locking is deliberately kept on a lock file distinct from ID allocation — evidence: `issue_lock_path()`'s docstring (`little_loops/file_utils.py:60-84`) states it is "deliberately distinct from `.id-alloc.lock`"; used by `set_status.py:123,134` and `link.py:160,178`, paired with `atomic_write` rather than `Path.write_text`.
- Optional third-party dependencies are gated as `pyproject.toml` extras with a lazy import and an actionable error message, not left as unconditional base dependencies — evidence: `mcp` extra (`little_loops/mcp_server/__init__.py`), `otel` extra (`little_loops/transport.py:1627-1644`). `jinja2` does not follow this convention (unconditional base dependency); contested only in the sense that it's a base dep only because FEAT-3036 chose to make it one, not because the convention was violated.
- In-process concurrency tests in this codebase use `threading.Thread`/`threading.Barrier`/`ThreadPoolExecutor` against `acquire_lock`, not `multiprocessing` — evidence: `test_file_utils.py::TestAcquireLock`, `test_bug3150_issue_mutator_atomicity.py::TestConcurrency` (rationale stated at lines 264-268: flock contends within a process the same way it does across processes).
- Disagreement to flag: BUG-1364 (done) evaluated and rejected locking `get_next_issue_number`/`cmd_next_id` directly ("Option C") before `create_issue`'s lock design existed; FEAT-2947 then implemented that same lock shape but scoped only to `create_issue()`, leaving `cmd_next_id` unlocked. BUG-1364's rejection reasoning has not been re-evaluated against FEAT-2947's design — see Proposed Solution → Option A.

**Tests**
- `scripts/tests/test_issues_cli.py` — `TestNextId`-style coverage: `test_next_id_empty_project`, `test_next_id_with_existing_issues`, `test_next_id_count_batch`, `test_next_id_count_one_matches_default`, `test_next_id_count_zero_exits_2`, `test_next_id_count_negative_exits_2` (lines 16-136) — all single-process, no concurrent variant.
- `scripts/tests/test_ll_issues_create.py` — exercises `create_issue` directly.
- `scripts/tests/test_bug3303_worktree_id_alloc.py` — `create_issue` and cross-tree `.id-alloc.lock` behavior.
- `scripts/tests/test_bug3150_issue_mutator_atomicity.py` — concurrency-test pattern to model a `next-id` race test after (`threading.Barrier`, asserts no lost/corrupted writes).
- `scripts/tests/test_issue_parser.py::TestGetNextIssueNumber` — no concurrent variant exists, despite BUG-1364's wiring pass explicitly calling for one.
- `scripts/tests/test_mcp_server.py`, `scripts/tests/test_feat_3149_mcp_mutation_tools.py` — reference `issue_capture` tool registration/behavior.
- No subprocess-level integration test exists for the `ll-issues next-id` CLI binary — flagged as a gap by BUG-1364's own wiring pass and never closed since.

**Documentation**
- `docs/guides/MCP_SERVER_GUIDE.md` — documents `issue_capture` as a write tool (dry-run behavior, no-predicted-ID note).
- `docs/reference/CLI.md` — documents `ll-issues next-id`/`ni` and `issue_capture` tool parameters; the section to update if `next-id` is documented as read-only under Option B.
- `docs/reference/API.md` — documents `get_next_issue_number` and `acquire_lock`.

## Program Design

### Signatures

- `create_issue(config: BRConfig, spec: IssueSpec, now: datetime | None = None) -> CreatedIssue`
  (`little_loops/cli/issues/create.py`) — already atomic: allocates under
  `acquire_lock(lock_path, timeout=10.0)` on `.issues/.id-alloc.lock` and
  writes with exclusive-create (`open(path, "x")`), retrying up to 5 times on
  collision.
- `get_next_issue_number(config: BRConfig, category: str | None = None) -> int`
  (`little_loops/issue_parser.py`) — read-only highwater scan, no lock.
- `cmd_next_id(config: BRConfig, count: int = 1) -> int`
  (`little_loops/cli/issues/next_id.py`) — calls `get_next_issue_number`
  directly, outside any lock; this is the unsafe path when combined with a
  manual file write.

### Call Path

`ll-issues next-id` (`cmd_next_id`) -> `get_next_issue_number` (unlocked) —
vs. — `issue_capture` (`_tool_issue_capture`) -> `create_issue` ->
`acquire_lock(.id-alloc.lock)` -> `get_next_issue_number` (locked).

**Open question, not yet resolved by this formatting pass:** the stated
jinja2 root cause does not match the current call path — `create_issue` and
its `_render_issue_content` helper (`little_loops/cli/issues/create.py`) have
no `jinja2` import, and `scripts/pyproject.toml` already declares
`jinja2>=3.1` (added 2026-09-15, FEAT-3036), one day before this issue's
discovery date. The actual `jinja2` importers in the tree are
`little_loops/artifact_templates.py` and `cli/artifact/dashboard.py`, which
back `ll-artifact render`, not `issue_capture`. Confirm the real failing
import path (fresh env vs. stale editable install vs. a different tool)
before treating "add jinja2 to pyproject.toml" as the fix — see the
Steps to Reproduce verification note above.

## Impact

- **Priority**: P1 - two confirmed production ID collisions in two days
  (2026-09-15, 2026-09-16), each requiring manual file renumbering; the
  atomic `issue_capture` path is currently unusable, forcing every caller
  onto the unsafe manual path.
- **Effort**: Small - the next-id race has a direct fix by reusing the
  existing `.id-alloc.lock` pattern from `create_issue`; the jinja2 piece may
  already be resolved pending the verification above.
- **Risk**: Low - the fix follows an already-proven locking pattern in the
  same module; no schema or public API changes.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-16 | Priority: P1


## Session Log
- `/ll:refine-issue` - 2026-09-17T04:20:13 - `e8577901-f5fd-435d-a8d3-7899337fe38e.jsonl`
- `/ll:format-issue` - 2026-09-17T04:09:09 - `2a99ae96-959a-42e3-af68-3fbdce04f9f0.jsonl`
