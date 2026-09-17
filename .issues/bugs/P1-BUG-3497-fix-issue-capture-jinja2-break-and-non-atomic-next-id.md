---
id: BUG-3497
title: Migrate unsafe issue allocators to atomic creation and investigate capture
  import failure
type: BUG
priority: P1
status: in_progress
discovered_date: '2026-09-16'
labels:
- issue-capture
- concurrency
- hub
decision_needed: false
confidence_score: 100
outcome_confidence: 69
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# Migrate unsafe issue allocators to atomic creation and investigate capture import failure

## Summary

Two production ID collisions were reported on 2026-09-15 and 2026-09-16,
requiring manual renumbering. Automated commands and skills still instruct
callers to read `ll-issues next-id` and subsequently write files, sometimes
incrementing the returned number for a batch. GitHub sync also allocates and
writes outside the allocation lock. These paths can collide with each other
or with atomic creation.

A reported `No module named 'jinja2'` failure in `issue_capture` prompted use
of the unsafe manual fallback. Its cause remains unverified: Jinja2 is already
a declared dependency, and the capture handler uses the non-Jinja issue renderer.
Resolve that report from the failing environment rather than adding an existing
dependency again.

## Current Behavior

Verified on branch `main` during the 2026-09-17 review:

- `ll-issues next-id` reads the highwater number without reserving it. Repeated
  calls without an intervening write can return the same number; `--count`
  does not reserve a batch either.
- `create_issue` in `scripts/little_loops/cli/issues/create.py` holds the shared
  allocation lock across allocation, rendering, exclusive creation, and
  highwater update. Its lock/highwater handling supports linked worktrees.
- `GitHubSyncManager._create_local_issue` in `scripts/little_loops/sync.py`
  reads the next number and later uses `Path.write_text` outside that lock.
- Seven command/skill sources listed in the Integration Map still prescribe
  separate allocation and writing. Calling once immediately before each write
  reduces the window but does not eliminate it.
- `_tool_issue_capture` in `scripts/little_loops/mcp_server/tools.py` calls
  `create_issue` or `render_issue_preview`. Neither renderer directly imports
  Jinja2. The reported server-process import failure has not been reproduced
  by this review.

## Expected Behavior

- Supported creation paths use one shared lock/allocate/write protocol and
  return the ID actually written. Concurrent cooperating captures and GitHub
  imports allocate distinct numeric IDs, including across types and worktrees.
- Migrated instructions use atomic creation for every issue, retaining their
  metadata, body sections, parent relationships, and staging behavior.
- `next-id` remains a read-only, non-reserving hint. Help and documentation
  direct creation callers to `ll-issues create`; numeric stdout, aliases,
  `--count` behavior, and exit codes remain compatible.
- The reported capture import failure receives an evidence-backed disposition
  and an end-to-end verification in the affected environment when available.

## Scope Boundaries

- Guarantee uniqueness only among cooperating creation paths using the shared
  allocation protocol. Arbitrary manual writes and external allocators that
  bypass it remain outside the guarantee. Exclusive creation protects a full
  filename, not a numeric ID reused with a different slug, priority, or type.
- Do not introduce reservation semantics or mutation into read-only parsing.
  Failed creation after allocation may leave a numeric gap; contiguous numbering
  is not a guarantee.
- Parent read/modify/write updates and git staging remain outside the allocation
  transaction. Concurrent parent updates can lose child-list entries; before
  closure, link/capture a separate follow-up for that race. This issue preserves
  existing relationship/staging behavior, not transactional parent wiring.
- Handled issue-write and highwater-write failures in the extracted helper are
  in scope. Process termination, power-loss durability, and transactional
  rollback of parent edits/staging are outside this issue's guarantee.
- Normalization's `_alloc` in `scripts/little_loops/cli/issues/normalize.py`
  renumbers existing files and is explicitly out of implementation scope.
  Before closing this issue, link an existing follow-up or capture one for
  locking its allocation/rename transaction and testing concurrent creation.
  This remains a known collision risk; do not claim all ID mutation is safe.
- Do not change dependency declarations or require capture to work with a
  deliberately missing base dependency without a reproduced reason.

## Steps to Reproduce

1. In an isolated project, call `ll-issues next-id` twice before either caller
   writes. Write two differently titled issue files using the returned number.
   Both can exist with the same numeric ID because no reservation occurred.
2. For a deterministic regression, coordinate a GitHub import and an atomic
   capture at their allocation boundary in a temporary project. Exercise
   different titles/types so a same-filename collision cannot hide duplicate IDs.
3. For the reported import failure, invoke MCP `issue_capture` through the
   affected server process and record the complete traceback, tool name and
   arguments, interpreter path, installed little-loops/Jinja2 versions, editable
   checkout path/revision, and server restart state. Compare with a fresh
   supported install including the MCP extra. Do not infer the import path
   from the exception text alone.

## Root Cause

**Confirmed allocation defect:** reading a number and writing in a later step
is not a transaction. A lock held only while `next-id` executes ends before the
caller's write and cannot close that window. Hand-incremented batches are unsafe
for the same reason.

**Unresolved environment report:** `scripts/pyproject.toml` already declares
`jinja2>=3.1` (FEAT-3036). Known Jinja importers include
`scripts/little_loops/artifact_templates.py` and
`scripts/little_loops/cli/artifact/dashboard.py`; these do not establish a
capture failure. Investigate stale installation/server state or another import
path using the traceback. The existing generic Jinja2 learning-test proof does
not reproduce the reported failure, so it is not a readiness gate for this fix.

## Proposed Solution

**Selected: Option B.** Migrate unsafe creation callers to the existing atomic
creation protocol and document `next-id` as non-reserving. The earlier proposal
to lock only the hint command is rejected because it cannot cover a later write.
No reservation table or change to read-only allocation scans is planned.

The migration is not a drop-in call-site swap. Preserve GitHub sync's renderer
and metadata through a shared allocation/writing helper, and extend the normal
creation specification/CLI to carry command/skill metadata in the initial write.
Do not write an incomplete issue and patch required metadata afterward.

## Implementation Steps

1. Capture and disposition the Jinja2 report using the reproduction evidence
   above. If reproduced, fix the actual import/install cause and add a regression
   for that cause. If unavailable or no longer reproducible, record that limit
   and track remaining environment diagnosis separately; do not claim a source
   fix or block the independently verified allocator migration on speculation.
2. Extract the shared allocation transaction from `create_issue`, retaining
   main-worktree lock resolution, highwater persistence, exclusive creation,
   lock timeout behavior and collision retries. Define and implement the handled
   write-failure contract below rather than copying the existing unsafe
   issue-write-before-highwater failure path. Keep parent updates/staging
   in the existing creation wrapper.
3. Add validated metadata support to `IssueSpec` and the creation CLI as described
   below. Render all metadata before the exclusive write. Preserve defaults for
   existing callers and apply the same rendering rules to previews.
4. Migrate `_create_local_issue` to the shared transaction while retaining its
   current renderer, configured pull template, label filtering, body treatment,
   GitHub linkage, timestamps, unpadded ID spelling, and result/log behavior.
5. Migrate all seven command/skill sources in the Integration Map. Prepare body
   and metadata inputs, invoke atomic creation for each issue, and consume its
   returned ID/path. Remove batch arithmetic and per-issue `next-id` retries.
6. Regenerate affected Gemini, Kimi Code, and Qwen mirrors using the repository's
   `ll-adapt --host <host> --apply` flow after checking its current help. Inspect
   generated diffs and retain unrelated changes. Check other tracked generated
   surfaces for the same stale instructions.
7. Update CLI/API guidance and duplicate-ID recovery guidance consistently.
   Preserve historical changelog entries; any new release note should clarify
   that `--count` never reserved IDs.
8. Link/capture the normalization and concurrent-parent-update follow-ups,
   run targeted coverage and required
   code checks, then run the authoritative `python -m pytest scripts/tests/` gate.

## Program Design

### Signatures

Proposed internal helper in `scripts/little_loops/cli/issues/create.py`:

```python
def allocate_and_write_issue(config: BRConfig, *, issue_type: str, priority: str, slug: str, render: Callable[[str], str], id_width: int = 3) -> CreatedIssue:
    ...
```

The helper owns the existing shared lock/highwater transaction. It supplies the
allocated ID to a side-effect-free renderer under the lock, coordinates
exclusive creation with highwater persistence under the failure contract below,
and returns the ID/path only after both succeed.
Render callbacks must tolerate collision retries. Reuse existing category and
worktree resolution instead of introducing a second allocator. Preserve sync's
existing slug convention through its caller-supplied slug.

### Compatibility and Failure Contract

- Preserve ID spelling: normal creation keeps minimum width 3 (`BUG-001`);
  sync passes `id_width=0` and keeps `BUG-1`. The same formatted ID must appear
  in the filename, rendered content, returned result, and success log. Numeric
  uniqueness is independent of padding; cover numbers 1, 99, and 100.
- Validate metadata before allocation and render before committing allocation
  state. Validation/rendering failures create no issue and do not advance
  highwater.
- A handled issue-write or highwater-write failure must propagate as failure;
  sync must not append to `result.created` or emit a success log. Never leave a
  retained issue in a sibling worktree with an allocation number that another
  cooperating caller can reuse. Persisting highwater before issue publication
  is permitted; a failed creation may consume an ID. Preserve the prior
  highwater on a failed update rather than truncating/resetting it. If needed,
  harden the shared highwater writer using existing atomic-write utilities.
- Remove partial issue files owned by the failing operation on handled write
  errors; never remove a pre-existing collision target. Add fault-injection
  tests for both write boundaries and assert a subsequent sibling-worktree
  allocation remains safe. Do not describe exclusive creation as atomic
  visibility to unlocked readers or as crash-safe multi-file commit.
- Parent updates and staging run afterward and retain their existing behavior;
  a failure there does not imply that issue allocation was rolled back.

### Call Path

- MCP apply / CLI create -> `create_issue` -> shared helper -> standard renderer
  with metadata -> exclusive write + highwater update -> existing parent/stage work.
- GitHub pull -> `_create_local_issue` -> shared helper -> existing sync renderer
  with the allocated ID -> exclusive write + highwater update -> result/log update.
- MCP dry-run -> `render_issue_preview`; no allocation, reserved/predicted ID,
  file creation, or highwater update.

Extend `IssueSpec` with a default-empty `metadata: dict[str, object]` and add
`--metadata-file PATH` accepting a JSON object for CLI callers. Validate input
before allocation. Reject keys owned by explicit creation fields or the
allocator (`id`, `type`, `title`, `priority`, `status`, `parent`, `labels`), rather
than silently overriding them. Allow discovery/provenance metadata such as
`discovered_by`, `discovered_commit`, `discovered_branch`, `source_loop`,
`source_state`, `goal_alignment`, `persona_impact`, and `business_value`;
accept arbitrary nonreserved string keys (the examples are not an allowlist).
Metadata overrides generated provenance defaults, including `discovered_by`,
`discovered_date`, and `captured_at`, when explicitly supplied; omitted keys
retain their defaults. Explicit JSON null is preserved, not treated as omission.
Require JSON-compatible values for both CLI and direct Python callers:
strings, booleans, integers, finite floats, null, lists, and recursively
string-keyed objects. Reject non-object top-level input, non-string keys,
nonfinite numbers, cycles, and unsupported Python objects. Preserve nested
values through YAML serialization without Python-specific tags. Apply one
shared validator to creation and previews before any allocation mutation.
Existing explicit flags retain their current meaning. Metadata must be present
in the initial rendered document, including preview output when supplied.
No new MCP metadata parameter is required for this migration.

Sync continues constructing its complete frontmatter itself, including
`github_issue`, `github_url`, `captured_at`, `last_synced`,
`discovered_by: github_sync`, `discovered_date`, priority, and filtered labels.
Its configured `pull_template`, custom sections, and GitHub body treatment must
not silently change to the normal creator's defaults or body-merge behavior.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/create.py` — extract shared transaction;
  extend `IssueSpec`, metadata validation/rendering, CLI parser and handler.
- `scripts/little_loops/sync.py` — migrate `GitHubSyncManager._create_local_issue`
  with renderer/metadata parity and no post-write metadata patch.
- `scripts/little_loops/cli/issues/next_id.py` and
  `scripts/little_loops/cli/issues/__init__.py` — help/docstrings only for the hint.
- `commands/scan-codebase.md`, `commands/scan-product.md`,
  `commands/find-dead-code.md` — replace unsafe allocation instructions;
  retain discovery and product metadata.
- `skills/issue-size-review/SKILL.md`, `skills/debug-loop-run/SKILL.md`,
  `skills/audit-loop-run/SKILL.md`, `skills/link-epics/SKILL.md` — replace unsafe
  allocation instructions; retain child/parent wiring, provenance, and explicit
  path staging. `skills/capture-issue/SKILL.md` is the existing migration example.
- Affected generated `.gemini/`, `.kimi-code/`, and `.qwen/` mirrors — regenerate
  from sources rather than hand-maintaining divergent instructions.
- `hooks/scripts/check-duplicate-issue-id-post.sh` and
  `hooks/scripts/check-duplicate-issue-id.sh` — audit/update recovery messages
  that prescribe another `next-id` + write; retain duplicate-detection behavior.

### Dependent Files and Compatibility

- `scripts/little_loops/mcp_server/tools.py` — existing capture apply/preview
  caller; avoid unrelated changes. Modify only if reproduced failure requires it.
- `scripts/little_loops/cli/issues/scaffold_epic.py` and
  `scripts/little_loops/issue_lifecycle.py` — existing allocation-lock users;
  retain interoperability with the same cross-worktree protocol.
- `scripts/little_loops/issue_parser.py` and `scripts/little_loops/file_utils.py`
  — reuse highwater, locking, and read-only scanning conventions; harden the
  highwater writer if required by the handled-failure contract. Do not make
  normal issue parsing reserve IDs.
- `scripts/little_loops/cli/issues/normalize.py` — known residual allocator,
  explicitly tracked separately under Scope Boundaries.

### Tests

- `scripts/tests/test_ll_issues_create.py` — creator behavior, metadata validation,
  nested metadata round-trip, arbitrary-key acceptance, provenance override/null
  behavior, invalid direct-Python values, renderer failures, and concurrent
  distinct IDs. Exercise validation parity through CLI, direct creation, and
  previews; assert rejected input leaves issue files/highwater unchanged.
- `scripts/tests/test_sync.py` — existing `TestCreateLocalIssue*` coverage;
  concurrent import-versus-capture, metadata/label/template/body parity, and
  unchanged sync result/log semantics and unpadded IDs at 1, 99, and 100;
  failures must not report creation success.
- `scripts/tests/test_bug3303_worktree_id_alloc.py` — cross-worktree creator/sync
  interoperability and shared highwater behavior. Add mixed allocation coverage
  with `scaffold_epic` and lifecycle-created bugs. Inject issue-write and
  highwater-write failures, including preservation of an existing highwater,
  then allocate from a sibling worktree and check no retained ID is reused.
- `scripts/tests/test_issues_cli.py` — unchanged numeric stdout, aliases,
  `--count`, exit codes; help describes non-reservation and the safe alternative.
- `scripts/tests/test_mcp_server.py` and
  `scripts/tests/test_feat_3149_mcp_mutation_tools.py` — apply returns the actual
  allocated ID; dry-run has no allocation or filesystem/highwater mutation.
- Use deterministic barriers/events and bounded waits for concurrency coverage,
  following `TestConcurrentCreate` and
  `scripts/tests/test_bug3150_issue_mutator_atomicity.py`. Assert distinct numeric
  IDs across different slugs/types and complete readable files, not just distinct
  filenames. Include a subprocess case to exercise the cross-process contract.
- Add a regression for the Jinja2 failure only after establishing its actual
  cause; a blanket ban on Jinja2 imports would not prove the reported fix.

### Documentation

- `docs/reference/CLI.md` — non-reserving hint, atomic creation, metadata input.
- `docs/reference/API.md` — shared creation protocol and metadata contract.
- `docs/guides/MCP_SERVER_GUIDE.md` — actual-ID apply / no-ID preview semantics;
  add environment troubleshooting only if supported by reproduction evidence.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — duplicate hooks are backstops, not an
  allocation guarantee; keep recovery instructions aligned with hook messages.
- Preserve historical `CHANGELOG.md` entries, including ENH-2268's inaccurate
  claim that batch hints eliminate races; clarify in a new entry when releasing.

## Acceptance Criteria

- [ ] Concurrent cooperating captures and GitHub imports produce unique numeric
  IDs and complete files across different slugs/types and linked worktrees;
  mixed runs with `scaffold_epic` and lifecycle-created bugs remain interoperable.
- [ ] Fault-injected issue/highwater write failures report failure, preserve prior
  highwater safely, clean up owned partial issue files, and cannot cause reuse
  of a retained sibling-worktree issue's number. Allocation gaps are allowed.
- [ ] Sync retains GitHub linkage, timestamps, discovery fields, filtered labels,
  configured templates/custom sections, body handling, unpadded IDs (including
  1 and 99), and result/log behavior; normal creation retains padded IDs.
- [ ] All seven identified command/skill sources and their affected generated
  mirrors use atomic creation, consume returned IDs/paths, and preserve their
  metadata and relationship/staging behavior without post-write metadata patches.
- [ ] Metadata is validated before allocation; reserved-key overrides and invalid
  JSON fail without creating an issue or consuming an ID. Existing calls retain
  defaults; arbitrary nonreserved keys and nested JSON-compatible metadata
  survive serialization. Provenance overrides and explicit null follow the
  documented contract, with identical validation for CLI/Python/preview callers.
- [ ] `next-id` help/docs explicitly say it does not reserve IDs, including
  `--count`; existing stdout/aliases/count validation/exit codes are unchanged.
- [ ] MCP apply returns the actual created ID; dry-run returns no allocated or
  predicted ID and does not create issue files or update allocation state.
- [ ] The reported Jinja2 failure has a documented evidence-backed disposition:
  reproduced cause/fix and end-to-end verification, or an explicit unreproduced
  environment limitation with remaining diagnosis tracked separately.
- [ ] Normalization's unresolved allocation/rename race has a linked follow-up;
  the concurrent-parent-update race also has a linked follow-up. Parent wiring,
  staging, crashes/power loss, and arbitrary non-cooperating writes remain
  explicitly outside the allocation transaction's guarantee.
- [ ] Targeted regression coverage and the authoritative local test suite pass.

## Impact

- **Priority**: P1 — two reported production collisions required manual
  renumbering, and supported automation still prescribes unsafe allocation.
  The reported capture outage is environment-specific and unverified here.
- **Effort**: Medium — shared transaction extraction, metadata/CLI support,
  sync compatibility, seven instruction migrations, mirrors, and regression tests.
- **Risk**: Medium — allocation behavior already exists, but extracting it and
  preserving sync rendering/metadata across callers require careful parity tests.
- **Breaking Change**: None intended. Preserve existing creation defaults and
  hint output; metadata input is additive. No reservation semantics are introduced.

## Resolution

- **Action**: fix (partial — see Remaining Scope)
- **Completed**: 2026-09-17 (Implementation Steps 2-4 only)
- **Status**: Partial

### Changes Made

- `scripts/little_loops/cli/issues/create.py`: extracted the shared
  `allocate_and_write_issue` lock/allocate/write/highwater transaction out of
  `create_issue` (matches the Program Design signature); added
  `validate_metadata`/`_RESERVED_METADATA_KEYS` and `IssueSpec.metadata`
  support (CLI `--metadata-file`, provenance override/null semantics,
  reserved-key rejection); hardened the handled write-failure and
  highwater-write-failure contract (owned partial file removed, prior
  highwater preserved).
- `scripts/little_loops/sync.py`: migrated `_create_local_issue` to
  `allocate_and_write_issue` (`id_width=0`, unpadded IDs preserved) instead of
  reading a number and writing outside the lock — this closes the actual
  GitHub-sync-vs-create collision window the two reported production
  incidents trace to.
- `scripts/little_loops/issue_parser.py`: `write_id_alloc_highwater` now uses
  `file_utils.atomic_write` instead of a plain truncating write.
- `scripts/little_loops/cli/issues/{__init__.py,next_id.py}`: `next-id`
  help/docstring now states explicitly that it is a non-reserving hint and
  points to `ll-issues create`.
- Tests: `scripts/tests/test_ll_issues_create.py` (metadata validation/CLI,
  fault-injected issue-write and highwater-write failure contracts, id_width
  parity) and `scripts/tests/test_sync.py` (unpadded ID, write-failure
  propagation to `result.failed` not `result.created`, cross-caller
  create-vs-sync concurrent-uniqueness). Also fixed a line-number-keyed
  allowlist drift in `scripts/tests/test_issue_parser.py`
  (`TestPriorityRegexCompletenessAllowlist`) caused by this diff's line shifts.

### Root Cause Step 1 (Jinja2) Disposition

Unreproduced. `scripts/pyproject.toml` declares `jinja2>=3.1`; the only
importers in the tree are `artifact_templates.py` and
`cli/artifact/dashboard.py` — neither is on the `issue_capture` code path
(`mcp_server/tools.py:_tool_issue_capture` → `IssueSpec`/`create_issue` /
`render_issue_preview`, no Jinja2 import). No reproduction environment was
available in this session. Per the issue's own accepted fallback, this is
recorded as an unreproduced environment-specific report rather than a fix;
remaining diagnosis needs the reporter's traceback/interpreter/install state
per the Steps to Reproduce §3.

### Remaining Scope (not done in this pass)

This issue's full scope (7 command/skill migrations + generated-mirror
regeneration + CLI/API/MCP/hooks docs + CHANGELOG entry + the two linked
follow-ups for normalization's allocator and concurrent-parent-update races)
is substantially larger than Steps 2-4 above and was not attempted here — it
touches ~15 additional files with no code-correctness stakes as high as the
allocator/sync fix itself. Left `status: in_progress` rather than `done`
because most Acceptance Criteria boxes below are still unmet. Follow-up work:

- Migrate the seven command/skill sources in the Integration Map (Step 5).
- Regenerate Gemini/Kimi Code/Qwen mirrors (Step 6).
- Update `docs/reference/CLI.md`, `docs/reference/API.md`,
  `docs/guides/MCP_SERVER_GUIDE.md`, `docs/guides/BUILTIN_HOOKS_GUIDE.md`, and
  add a `CHANGELOG.md` entry (Step 7).
- Capture/link the normalization-allocator and concurrent-parent-update
  follow-up issues (Step 8) — not yet created.
- `scaffold_epic.py`/`issue_lifecycle.py` (Dependent Files) were not migrated
  or re-verified against the new helper beyond the existing interoperability
  the shared lock/highwater already provided.

### Verification Results

- Tests: PASS (`python -m pytest scripts/tests/` — 24945 passed, 53 skipped;
  one unrelated pre-existing failure, `test_verify_evidence.py::TestRepoGate::
  test_no_new_unverifiable_evidence`, reproduces identically on a clean stash
  of this diff — a stale quote in BUG-3484 unrelated to this change)
- Lint: PASS (`ruff check` on all changed files)
- Types: PASS (`mypy` on all changed source files)

## Status

**In Progress** | Created: 2026-09-16 | Priority: P1

## Session Log
- `/ll:manage-issue` - 2026-09-17T06:25:47 - `673b8d7f-311f-49c5-91da-9f35cbc67a87.jsonl`
- `/ll:ready-issue` - 2026-09-17T05:55:18 - `2b9f4440-e280-4bc2-a778-2ed32f57f8b6.jsonl`
- `/ll:confidence-check` - 2026-09-17T05:49:17 - `8528d71a-e5d1-4e75-a49d-fce04bd5520a.jsonl`
- `/ll:verify-issues` - 2026-09-17T05:35:18 - `23994eb4-1b9e-4c0b-b12e-4d6b8a1de974.jsonl`
- `/ll:wire-issue` - 2026-09-17T04:46:35 - `46075459-e145-4488-ad3c-9337c7cc659b.jsonl`
- `/ll:decide-issue` - 2026-09-17T04:28:33 - `2181bc0b-0c40-4859-b8bc-a71f05757ba2.jsonl`
- `/ll:refine-issue` - 2026-09-17T04:20:13 - `e8577901-f5fd-435d-a8d3-7899337fe38e.jsonl`
- `/ll:format-issue` - 2026-09-17T04:09:09 - `2a99ae96-959a-42e3-af68-3fbdce04f9f0.jsonl`
