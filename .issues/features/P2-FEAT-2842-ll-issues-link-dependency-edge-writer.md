---
id: FEAT-2842
type: FEAT
priority: P2
status: open
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

## Implementation Steps

1. Add `scripts/little_loops/cli/issues/link.py` with `add_link_parser()` /
   `cmd_link()`, following the shape of `set_status.py`.
2. Reuse `show._resolve_issue_id()` for both source and target ID resolution
   (accepts `2842`, `FEAT-2842`, `P2-FEAT-2842`).
3. Implement a frontmatter read-modify-write helper that preserves unrelated
   keys and formatting — check whether `issue_parser` already exposes one before
   writing a new one.
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

## Use Case

As a skill author wiring a dependency between two issues, I run
`ll-issues link FEAT-110 --blocked-by FEAT-109` and get a guaranteed-correct
frontmatter edge — instead of instructing a model to hand-edit YAML and hoping
it neither duplicates the key nor invents the target ID. As a backlog owner
re-running `/ll:audit-issue-conflicts` weekly, I get the same result every time
rather than watching earlier edges silently disappear.

## Acceptance Criteria

- [ ] `ll-issues link A --blocked-by B` twice produces exactly one list entry and
      one `blocked_by:` key.
- [ ] Unknown target exits non-zero without modifying the file.
- [ ] An edge that would create a cycle is refused with a non-zero exit.
- [ ] Unrelated frontmatter keys and body content are byte-identical after a
      write.
- [ ] `skills/audit-issue-conflicts/SKILL.md` contains no `Edit`-the-frontmatter
      instruction for dependency fields.
- [ ] Tests in `scripts/tests/` cover all of the above and pass under
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

---

## Status

open
