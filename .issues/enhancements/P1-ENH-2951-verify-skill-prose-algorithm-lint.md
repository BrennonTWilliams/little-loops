---
id: ENH-2951
title: 'll-verify-skill-prose: lint gate that fails on algorithm-as-prose in skill/command
  markdown'
type: ENH
priority: P1
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- skills
- determinism
- gate
relates_to:
- ENH-2939
- ENH-2941
---

# ENH-2951: `ll-verify-skill-prose` — enforce EPIC-2938's core invariant

## Summary

EPIC-2938's first success criterion — "no skill/command markdown contains a prose
reimplementation of an algorithm that exists in `scripts/little_loops/`" — has no
enforcement mechanism. Every other invariant in this repo has an `ll-verify-*` gate
(`ll-verify-skills`, `ll-verify-decisions`, `ll-verify-cli-allowlist`, …). Without one,
the epic's deletions regress silently.

## Current Behavior

Nothing checks for algorithm-as-prose. The regression is not hypothetical: commit
`5e29c4d4` (ENH-2936) added Pattern E option-detection prose to
`skills/decide-issue/SKILL.md` **three commits after** EPIC-2938 was scoped to delete
exactly that class of content, and simultaneously duplicated it into
`issue_parser.py:449`. `ll-verify-skills` only enforces the 500-line cap, which such
prose can satisfy while still being a duplicated algorithm.

## Expected Behavior

`ll-verify-skill-prose [--json]` scans `skills/*/SKILL.md` + `commands/*.md` and exits 1
on any of a curated marker set, each mapped to the CLI that owns the logic:

| Marker | Owner |
|---|---|
| Jaccard/overlap formula (`intersection / union`, `∩`/`∪` over word sets) | `text_utils.calculate_word_overlap` |
| an inline stop-word list | `text_utils.extract_words` |
| scanning `~/.claude/projects/` for session JSONL | `ll-issues append-log` |
| inline `python3 -c` computation the model is told to run | the owning CLI |
| `git mv` loops over globbed issue filenames | `ll-issues normalize` |
| union-find / cluster-merge instructions | `ll-issues link-epics` |

Findings report `file:line`, the matched marker, and the owning CLI. An
`<!-- ll-prose-ok: reason -->` comment on the preceding line suppresses a checked-in
false positive.

## Proposed Solution

Marker table as module data (regex + owner + rationale), mirroring `fsm/validation.py`'s
MR-rule table shape. Resolve the skill/command dirs via
`skill_expander._find_plugin_root` (the shared helper, per FEAT-2940's registration note)
rather than a `__file__` walk. Register as a pytest test in `scripts/tests/` — the only
CI — and add it to `ll-doctor --full`'s aggregate.

## Implementation Steps

1. Marker table + scanner + `--json`; suppression comment support.
2. Baseline the current tree: every existing hit must map to an EPIC-2938 child that
   deletes it, or get an explicit suppression with a reason. Record the baseline count.
3. Register the entry point (triple registration per BUG-2764: `scripts/pyproject.toml`,
   `skills/configure/areas.md` preset, `init/writers.py::_LL_PERMISSIONS`); add to
   `ll-doctor --full`.
4. Tests: one fixture per marker (positive + negative), suppression-comment behavior,
   and a test asserting the baseline only ever shrinks.

## Program Design

### Types

- `ProseMarker: dataclass`
  - `name: str`
  - `pattern: re.Pattern`
  - `owner_cli: str`
  - `rationale: str`
- `ProseFinding: dataclass`
  - `path: Path`
  - `line: int`
  - `marker: str`
  - `owner_cli: str`
- `PROSE_MARKERS: tuple[ProseMarker, ...]` — the curated table

### Signatures

- `scan_prose(plugin_root: Path) -> list[ProseFinding]`
- `main_verify_skill_prose(argv: list[str] | None = None) -> int`

Exits 1 on any unsuppressed finding, matching the other `ll-verify-*` tools' contract.

### Call Path

- `main_verify_skill_prose()` -> `scan_prose()` -> `parse_skill_frontmatter()` (existing, `little_loops/frontmatter.py`)

## Scope Boundaries

- In scope: the marker table, scanner, suppression mechanism, entry-point registration,
  pytest gate, baseline record.
- Out of scope: deleting the prose itself (that is each sibling child's job), semantic
  detection of *any* duplicated algorithm (the marker table is deliberately curated, not
  general), FSM loop YAML (covered by `ll-loop validate`'s MR rules).

## Impact

- **Priority**: P1 - Wave 1; without it EPIC-2938's headline criterion is unenforceable and demonstrably regresses
- **Effort**: Small - Marker table + scanner, same shape as existing `ll-verify-*` tools
- **Risk**: Low - Read-only lint; suppression escape hatch prevents hard-blocking

## Status

**Open** | Created: 2026-07-31 | Priority: P1

## Acceptance Criteria

- [ ] `ll-verify-skill-prose` exits 1 on each marker with a fixture, 0 on a clean tree
- [ ] Every current-tree hit is either mapped to an EPIC-2938 child or suppressed with a stated reason; the baseline count is recorded
- [ ] A test asserts the baseline count never increases
- [ ] `ll-verify-cli-allowlist` passes with the new entry point (triple registration)
- [ ] Included in `ll-doctor --full`
- [ ] pytest coverage in `scripts/tests/`

## Notes

Deliberately a curated marker list, not a general duplicate-algorithm detector — the
value is catching the six known shapes cheaply, not proving a hard problem.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-01T00:26:02 - `6fbac205-468a-44ce-b7fb-4626b0ac42e4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-01T00:25:50 - `6fbac205-468a-44ce-b7fb-4626b0ac42e4.jsonl`
