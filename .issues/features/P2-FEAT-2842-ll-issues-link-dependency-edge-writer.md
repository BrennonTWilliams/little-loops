---
id: FEAT-2842
type: FEAT
priority: P2
status: done
completed_at: '2026-07-27T02:04:13Z'
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- issues-cli
- dependency-graph
- idempotency
relates_to:
- BUG-2848
- BUG-2844
- ENH-2845
confidence_score: 98
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 22
---

# FEAT-2842: `ll-issues link` — idempotent dependency-edge writer

## Summary

Add an `ll-issues link <ID> --blocked-by <ID> | --depends-on <ID> | --relates-to
<ID>` subcommand that writes dependency edges into issue frontmatter
idempotently, list-aware, with existence validation — so skills stop hand-editing
YAML frontmatter with the `Edit` tool.

Every dependency edge in the system is currently written by an LLM performing a
free-form `Edit` on a YAML frontmatter block. There is no primitive for "add this
edge" the way `ll-issues set-status` is the primitive for "change this status".

## Current Behavior

`skills/audit-issue-conflicts/SKILL.md:370` (the `add_dependency` branch) says:

> Append either `blocked_by: [ISSUE-B]` (hard stop — must complete first) or
> `depends_on: [ISSUE-B]` (soft ordering — preferred when no hard dependency
> exists) to the frontmatter of the dependent issue file using Edit

Consequences observed by inspection:

1. **No idempotency guard.** The sibling branches in the same phase both have
   explicit "check whether already present" guards — `merge/deprecate` (steps 3
   and 4) and `split/update_scope` (guard 2). `add_dependency` has only the
   active-set guard. Re-running the audit over the same backlog appends a
   **second `blocked_by:` key** to the frontmatter. YAML duplicate-key resolution
   keeps the last mapping, so the first list is silently discarded — a
   dependency-*losing* failure mode.
2. **Append-vs-extend is left to model judgment.** Whether to create the key or
   append an entry to an existing list is unspecified; both shapes are plausible
   `Edit` outputs.
3. **No target validation.** Nothing checks that the referenced ID resolves to a
   file on disk, so a hallucinated or mistyped ID lands in frontmatter and
   surfaces later only as a `DependencyGraph.from_issues()` logger warning
   (`dependency_graph.py:104-108`), which nothing reads.
4. **No post-write verification.** No `ll-issues format-check` or re-read
   confirms the frontmatter still parses after the edit.

`skills/audit-issue-conflicts/` is not the only consumer — `/ll:wire-issue` and
`/ll:map-dependencies` face the same problem.

There is no test coverage for this path: `scripts/tests/test_audit_issue_conflicts_skill.py`
has `test_phase4b_idempotency_guard_present` and `test_phase4b_write_side_guard_present`,
but neither exercises `add_dependency`.

## Expected Behavior

```bash
ll-issues link FEAT-110 --blocked-by FEAT-109
ll-issues link FEAT-110 --blocked-by FEAT-109   # second run: no-op, exit 0
```

- **Idempotent**: re-running is a no-op that reports `unchanged`, never a
  duplicate key and never a duplicate list entry.
- **List-aware**: creates the key when absent, appends to the existing list when
  present, preserving ordering and the rest of the frontmatter byte-for-byte.
- **Validating**: the target ID must resolve to an existing issue file; exit
  non-zero with a clear message otherwise. `--force` to override.
- **Reciprocal-aware**: `--blocked-by A` on B optionally writes the matching
  `blocks: [B]` on A (`--reciprocal`). Note `from_issues()` already honours
  one-sided `blocks:` declarations (`dependency_graph.py:113-128`), so this is a
  convenience, not a correctness requirement.
- **Cycle-safe**: refuse an edge that would introduce a cycle in the blocking
  graph (`topological_sort` raises `ValueError` on cycles, which
  `cli/issues/sequence.py:47-49` degrades to unordered priority output).
- `--json` and `--dry-run` for skill/automation consumption.
- Also supports removal: `--unlink` / `--remove`.

## Root Cause

Dependency edges were never given a CLI primitive. `ll-issues` grew
`set-status`, `set-scores`, `skip`, `append-log`, and `anchor-sweep` as
deterministic writers, but edge writes stayed in skill markdown as `Edit`
instructions.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/link.py` — new file, `add_link_parser()` / `cmd_link()`
- `scripts/little_loops/cli/issues/__init__.py` — register `link` subcommand (mirror the `set-status` wiring at lines ~154-851 for parser registration and ~902-903 for dispatch)
- `skills/audit-issue-conflicts/SKILL.md:366-385` — repoint `add_dependency` branch at `ll-issues link`
- `skills/audit-issue-conflicts/interactive-prompts.md:19-20,23-37` — repoint "Add dependency instead" option and `add_dependency` questions

### Reusable Primitives (no new helper needed)
- `scripts/little_loops/frontmatter.py:243-266` — `update_frontmatter(content: str, updates: dict) -> str` **already exists** and is exactly the preserving read-modify-write helper Implementation Step 3 asked to confirm. It round-trips via `yaml.safe_load()`/`yaml.dump(sort_keys=False)`, preserves field order, and creates the frontmatter block if missing. Used today by `set_status.py:127` as `update_frontmatter(content, _status_updates(args.status))` — `link.py` should call it the same way with a dict built from the existing list plus the new target ID.
- `scripts/little_loops/frontmatter.py:30-95` — `parse_frontmatter(content, *, coerce_types=False)` — read the current `blocked_by`/`depends_on`/`relates_to` list before merging (mirrors `set_status.py:126` reading old status before update).
- `scripts/little_loops/cli/issues/show.py:40-150` — `_resolve_issue_id(config, user_input) -> Path | None`, confirmed to accept `"2842"`, `"FEAT-2842"`, `"P2-FEAT-2842"` and prefer exact frontmatter `id:` match over filename substring (BUG-2806 fix).
- `scripts/little_loops/dependency_graph.py:56-145` — `DependencyGraph.from_issues(issues, completed_ids=None, all_known_ids=None)` builds `blocked_by`/`blocks`/`depends_on_edges` dicts.
- `scripts/little_loops/dependency_graph.py:301-371` — `topological_sort()` raises `ValueError("Dependency graph contains cycles: ...")` on cycles — use as the cycle-refusal check in Step 4.
- `scripts/little_loops/issue_parser.py:653-772` — `IssueInfo` dataclass fields `blocked_by`/`blocks`/`depends_on`/`relates_to`/`duplicate_of`/`supersedes` (lines 695-702) and `find_issues()` (line 1307) to load all issues for the cycle check.
- `_resolve_issue_id` import convention: import it lazily *inside* `cmd_link()`, matching every existing caller — `set_status.py:46`, `set_scores.py:27`, `skip.py:29`, `check_decidable.py:26`, `check_flag.py:23`, `check_readiness.py:28`, `check_open_questions.py:47`, `format_check.py:41`, `path_cmd.py:24`. It stays a private (`_`-prefixed), non-exported helper by established convention (`.issues/enhancements/P2-ENH-1422-decouple-status-ll-issues-cli.md:114-118`) — do not promote/export it for this issue.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — dispatch table wiring (import + parser registration + dispatch), same file already listed above; no additional caller files found that `import` link.py symbols directly (it's new).
- **Step 8 re-verification**: a targeted grep found no confirmed literal "hand-edit `blocked_by`/`depends_on`/`relates_to` frontmatter" instruction in `skills/wire-issue/SKILL.md`, `skills/wire-issue/static-coupling-layer.md`, or `skills/map-dependencies/SKILL.md` — `map-dependencies` already delegates dependency *writes* to `ll-deps fix`/`apply` (see Semantic Overlap note below), not to a raw `Edit`. Re-verify the full skill bodies at implementation time before repointing; Step 8 may be a no-op for these two skills, unlike the confirmed `skills/audit-issue-conflicts/SKILL.md:370` and `interactive-prompts.md:19-20,23-37` hits.

### Semantic Overlap — Existing Section-Based Writer

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/dependency_mapper/operations.py` (`apply_proposals`, lines 21-63) is a **pre-existing** dependency-edge writer, invoked by `ll-deps fix`/`ll-deps apply`, that writes `blocked_by`/`blocks`/`depends_on`/`relates_to` as **markdown body sections** (`## Blocked By`, etc.) rather than frontmatter keys. `scripts/little_loops/issue_parser.py:962-1019` merges both representations when an issue has both, with **frontmatter taking precedence**. The new `link` command must not silently diverge in reciprocal-write semantics from this existing writer: `operations.py` treats `depends_on` as one-directional (matching `dependency_graph.py:129-130`'s comment "one-directional — no reverse edge is built here") and `relates_to` as bidirectional. `link.py`'s `--reciprocal` flag should match this convention rather than inventing a new one.
- `docs/reference/CLI.md:1876-1965` documents `ll-deps fix`/`ll-deps apply` right next to where the new `ll-issues link` entry will land — add a one-line doc cross-reference distinguishing "frontmatter-key writer" (`link`) from "markdown-section writer" (`ll-deps fix`/`apply`) so users don't find two competing "write a dependency edge" tools with no stated relationship.
- Cycle-refusal error message: `link.py`'s except-clause text should match the phrasing already surfaced by `cli/issues/sequence.py:47-49` for the same underlying `ValueError("Dependency graph contains cycles: ...")`, so users hitting both paths see one consistent message.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1134-1138` — the `### ll-issues` subcommand section; add a new `#### \`ll-issues link <issue_id>\`` block in the same style as the other `#### \`ll-issues <name>\`` entries (pattern at lines 1140, 1149, 1171, 1183), with a flag table for `--blocked-by`/`--depends-on`/`--relates-to`/`--unlink`/`--remove`/`--reciprocal`/`--force`/`--json`/`--dry-run`.
- `.claude/CLAUDE.md` § CLI Tools — the `ll-issues` bullet enumerates subcommands inline (`next-id, list, show, path, sequence, ..., decisions (...)`); append `link` to this list. (Already called out generically as Implementation Step 6; this is the exact anchor.)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_frontmatter.py` (`TestUpdateFrontmatter`, from line 368) — **gap**: no existing test exercises `update_frontmatter()` with a `list[str]` value (append-to-existing-list vs. create-new-list-key); every current test passes scalar/nested-dict values. Add `test_update_appends_to_existing_list` / `test_update_creates_new_list_key` here — `link.py`'s core append-vs-create behavior is otherwise untested at the utility layer.
- `scripts/tests/test_dependency_graph.py` (`TestCycleDetection` line 504, `TestTopologicalSort.test_cycle_raises_value_error` line 441) — cycle-detection correctness is already exhaustively proven at the `DependencyGraph` unit level; `test_link_cli.py` only needs 1-2 CLI-level tests proving the check is *wired in* (construct two issues with a would-become-cyclic edge, call `ll-issues link`, assert exit 1 + "cycle" in stderr), not re-prove `detect_cycles()` itself.
- `scripts/tests/test_show.py` (`TestResolveIssueId`, line 74) — alias resolution (`"2842"`/`"FEAT-2842"`/`"P2-FEAT-2842"`, nonexistent → `None`, frontmatter-id-wins-over-filename-substring) is already exhaustively covered; `test_link_cli.py` needs at most one sanity call using a bare-numeric ID, not a full matrix.
- `scripts/tests/test_audit_issue_conflicts_skill.py` — **no existing test currently guards the `add_dependency` section's "using Edit" text** (the closest existing test, `test_phase4b_supersession_uses_cancelled_not_done` at line 104, checks unrelated superseded-status prose). Repointing `SKILL.md:371-375` at `ll-issues link` will not break anything today, but add a new `test_add_dependency_uses_ll_issues_link` asserting the `add_dependency` section contains `"ll-issues link"` and not `"using Edit"`, so the repoint is enforced going forward.

## Implementation Steps

1. Add `scripts/little_loops/cli/issues/link.py` with `add_link_parser()` /
   `cmd_link()`, following the shape of `set_status.py`.
2. Reuse `show._resolve_issue_id()` for both source and target ID resolution
   (accepts `2842`, `FEAT-2842`, `P2-FEAT-2842`).
3. Read the existing list via `parse_frontmatter()` and write the merged list
   via `frontmatter.update_frontmatter()` (`scripts/little_loops/frontmatter.py:243-266`)
   — this preserving read-modify-write helper already exists; no new helper is
   needed.
4. Cycle check: build `DependencyGraph.from_issues()` with the prospective edge
   and confirm `topological_sort()` does not raise.
5. Register in `cli/issues/__init__.py` and in the `ll-issues` help text.
6. Update `.claude/CLAUDE.md`'s `ll-issues` subcommand list.
7. Repoint `skills/audit-issue-conflicts/SKILL.md` `add_dependency` (and the
   `merge/deprecate` "Add dependency instead" option in
   `interactive-prompts.md:19-20`) at the new CLI; add `Bash(ll-issues:*)` is
   already in `allowed-tools`, so no permission change is needed for this part.
8. Repoint `/ll:wire-issue` and `/ll:map-dependencies` where they write edges.
9. Tests: idempotent re-run, list-append vs. key-create, unknown target,
   cycle refusal, frontmatter preservation, `--json` shape.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Add `docs/reference/CLI.md:1134-1138` area — new `#### \`ll-issues link <issue_id>\`` block with flag table; add a one-line cross-reference note distinguishing it from `ll-deps fix`/`ll-deps apply`'s markdown-section writer (`docs/reference/CLI.md:1876-1965`).
11. Match `--reciprocal` semantics to the existing `dependency_mapper/operations.py` convention: `depends_on` one-directional, `relates_to` bidirectional — do not invent new semantics for fields the section-based writer already defines.
12. Match the cycle-refusal error message to the phrasing already used by `cli/issues/sequence.py:47-49`.
13. Add `test_update_appends_to_existing_list` / `test_update_creates_new_list_key` to `scripts/tests/test_frontmatter.py` (`TestUpdateFrontmatter`) — this behavior is untested at the utility layer today.
14. Add `test_add_dependency_uses_ll_issues_link` to `scripts/tests/test_audit_issue_conflicts_skill.py` to enforce the `SKILL.md:371-375` repoint.
15. Before repointing `/ll:wire-issue` or `/ll:map-dependencies` (Step 8), re-verify their full skill bodies — a targeted grep found no confirmed literal frontmatter-hand-edit instruction in either; `map-dependencies` already delegates writes to `ll-deps fix`/`apply`. Step 8 may be a no-op for these two.

## Use Case

As a skill author wiring a dependency between two issues, I run
`ll-issues link FEAT-110 --blocked-by FEAT-109` and get a guaranteed-correct
frontmatter edge — instead of instructing a model to hand-edit YAML and hoping
it neither duplicates the key nor invents the target ID. As a backlog owner
re-running `/ll:audit-issue-conflicts` weekly, I get the same result every time
rather than watching earlier edges silently disappear.

## Acceptance Criteria

- [x] `ll-issues link A --blocked-by B` twice produces exactly one list entry and
      one `blocked_by:` key.
- [x] Unknown target exits non-zero without modifying the file.
- [x] An edge that would create a cycle is refused with a non-zero exit.
- [x] Unrelated frontmatter keys and body content are byte-identical after a
      write.
- [x] `skills/audit-issue-conflicts/SKILL.md` contains no `Edit`-the-frontmatter
      instruction for dependency fields.
- [x] Tests in `scripts/tests/` cover all of the above and pass under
      `python -m pytest scripts/tests/`.

## Impact

- **Users**: dependency edges written by automation become trustworthy. Today a
  second audit run can silently drop the edges the first one added.
- **Risk**: Low. Additive CLI; the skill repoint is the only behavior change.
- **Effort**: Medium. The CLI itself is small; the frontmatter-preserving
  read-modify-write and the skill repoints are the bulk.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/cli/issues/set_status.py` | Shape to follow for a deterministic frontmatter writer |
| `scripts/little_loops/dependency_graph.py:56-146` | How edges are consumed; one-sided `blocks:` handling |
| `skills/audit-issue-conflicts/SKILL.md:366-380` | The `add_dependency` branch being replaced |
| `.claude/CLAUDE.md` § CLI Tools | `ll-issues` subcommand list to update |

## Context

Found while auditing `/ll:audit-issue-conflicts` for reliable frontmatter
writing, after `ll-issues sequence` reported a blocked issue as
`[P2, no blockers]`.

## Session Log
- `/ll:manage-issue` - 2026-07-27T02:03:27 - `1bde6182-2eb9-48b7-a3f4-597c625c7971.jsonl`
- `/ll:ready-issue` - 2026-07-27T01:48:28 - `10e8afff-6279-41be-a344-efa619481b05.jsonl`
- `/ll:confidence-check` - 2026-07-26T00:00:00 - `fb56b746-9f10-4780-864f-9497240e812f.jsonl`
- `/ll:wire-issue` - 2026-07-27T01:45:32 - `d15d948e-4fc0-47fe-a2a2-008abce10c0c.jsonl`
- `/ll:refine-issue` - 2026-07-27T01:40:47 - `34d4fdbc-81ad-4b2d-836c-2daca74975c0.jsonl`

---

## Status

open
