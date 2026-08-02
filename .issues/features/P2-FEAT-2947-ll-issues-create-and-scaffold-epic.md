---
id: FEAT-2947
title: "ll-issues create and scaffold-epic: atomic issue/epic creation"
type: FEAT
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- issues
- scaffolding
---

# FEAT-2947: `ll-issues create` + `scaffold-epic` — atomic issue/epic creation

## Summary

There is no `ll-issues create`: `next-id` + `sections` provide the pieces, but file assembly — ID allocation with duplicate-retry, slugging, path selection, frontmatter, template body, staging — is narrated in prose in every creating skill. This is why `skills/scope-epic/SKILL.md` (484 lines) and `skills/capture-issue/SKILL.md` (497 lines) are so heavy. Add the write path and an epic-scaffolding composition.

## Current Behavior

- scope-epic Phase 4 (L284–380): `next-id` immediately-before-each-Write, three filename templates with slugification (L299, L338, L363), a duplicate-ID retry loop (L324); Phase 5 (L384–420) wires `parent:`/`## Children` both directions; Phase 6 stages.
- capture-issue Phase 4 (L249–333): the same dance independently restated.

## Expected Behavior

- `ll-issues create --type FEAT|BUG|ENH|EPIC --title "..." [--priority P2] [--body-file PATH|-] [--parent EPIC-N] [--labels a,b] [--stage] --json` — atomic: allocates ID (retry on collision), slugs, selects the type dir, writes frontmatter + template body (from `ll-issues sections`), optionally wires `parent:` both directions, optionally `git add`s. Returns `{id, path}`.
- `ll-issues scaffold-epic --title "..." --children <json|@file> [--priority P2] [--stage] --json` — composes `create`: EPIC + pre-wired child stubs (`parent:`, EPIC `## Children`), staged atomically.
- `skills/scope-epic/SKILL.md` shrinks to: decompose the theme into child titles/scopes (real reasoning), emit children JSON, call the CLI.
- **capture-issue is a named adopter**: it is the highest-traffic creation path and ENH-2941 already slims its dedup phase; its Phase 4 must switch to `create` (in this issue or an explicit follow-up AC) — do not land the CLI with scope-epic as its only consumer.

## Proposed Solution

Reuse `issue_parser.get_next_issue_number` + `slugify`, `frontmatter.py`, `ll-issues sections` templates, and the `finalize-decomposition` staging pattern. `create` lands first inside the issue; `scaffold-epic` composes it.

## Implementation Steps

1. `create` (all types) + tests (ID collision retry, template body, parent wiring, `--stage`).
2. `scaffold-epic` + tests (both-direction wiring, atomicity on partial failure).
3. Slim scope-epic Phases 4–6 and capture-issue Phase 4.

## Use Case

`/ll:capture-issue` mines a conversation, drafts title/body, then calls `ll-issues create --type BUG --title "..." --body-file - --stage` and gets back `{id, path}` — no ID-collision retry dance, no filename templating in prose. `/ll:scope-epic` decomposes a theme, emits children JSON, and one `scaffold-epic` call writes the fully wired EPIC + stubs.

## Program Design

### Types

- `IssueSpec: dataclass`
  - `type: str`
  - `title: str`
  - `priority: str`
  - `body: str | None`
  - `parent: str | None`
  - `labels: list[str]`
  - `stage: bool`
- `CreatedIssue: dataclass`
  - `id: str`
  - `path: Path`
- `ChildSpec: dataclass`
  - `type: str`
  - `title: str`
  - `priority: str`
  - `summary: str`

### Signatures

- `create_issue(spec: IssueSpec, issues_dir: Path) -> CreatedIssue` — `get_next_issue_number` + collision retry, `slugify`, template body from `ll-issues sections`, parent wiring both directions
- `scaffold_epic(title: str, children: list[ChildSpec], priority: str, stage: bool) -> tuple[CreatedIssue, list[CreatedIssue]]` — composes `create_issue`; atomic staging

### Call Path

- `create_issue()` -> `get_next_issue_number()` (existing) -> `slugify()` (existing, `issue_parser.py`)
- `create_issue()` -> `update_frontmatter()` (existing, `frontmatter.py`)
- `scaffold_epic()` -> `create_issue()`

## Impact

- **Priority**: P2 - Fills the biggest primitive gap; two ~490-line skills depend on the prose it deletes
- **Effort**: Medium - `create` simple; scaffold-epic atomicity needs care
- **Risk**: Medium - Write path with staging; mitigated by collision-retry tests + `epic-consistency`/`format-check` gates on output

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues create` never produces a colliding ID under concurrent calls (retry loop tested)
- [ ] `scaffold-epic` output passes `ll-issues epic-consistency` and `format-check`
- [ ] scope-epic and capture-issue contain no ID/slug/filename templating prose
- [ ] pytest coverage in `scripts/tests/`

## Notes

Split `scaffold-epic` out if atomic-staging/rollback semantics get involved; `create` alone is independently shippable and valuable.

## Related Key Documentation

- `.claude/CLAUDE.md` — adds `ll-issues create`/`scaffold-epic` to the documented `ll-issues` CLI catalog and directly touches the issue file format (frontmatter, template body, `parent`/`## Children` wiring) rules this doc defines.
- `docs/reference/API.md` — new `create_issue`/`scaffold_epic` functions belong alongside the documented `cli/*` entry points and `issue_parser`/`frontmatter` module reference.
