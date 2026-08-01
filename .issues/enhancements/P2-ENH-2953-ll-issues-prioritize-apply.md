---
id: ENH-2953
title: "ll-issues prioritize --apply: priority-rename mechanics out of prioritize-issues.md"
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2944
labels:
- cli
- issues
- normalization
---

# ENH-2953: `ll-issues prioritize --apply`

## Summary

`commands/prioritize-issues.md` (233 lines) is discovery + rename bookkeeping around a
single genuine judgment step. Split out of ENH-2944 so it ships independently of
`normalize` (511 lines, the largest file in the epic's scope) rather than waiting on it.

## Current Behavior

- Glob + `^P[0-5]-` regex discovery (L54–67), scripted control-flow gates (L69–83),
  `git mv` renames (L108–112, L169–173), two fixed report tables (L118–139, L177–209),
  and narrated check-mode exit codes (L48–50) — which makes any FSM
  `evaluate: type: exit_code` gate over this command model-dependent.
- Only Step 2 (L145–165) — assigning P0–P5 from impact/severity/effort — is judgment.
- Notably the command uses no `ll-issues` subcommand at all today.

## Expected Behavior

- `ll-issues prioritize [--check] --json` — lists unprioritized issues (discovery +
  report data); `--check` is a deterministic exit-code gate (0 clean / 1 unprioritized
  issues present), per the EPIC convention that no `--check` exit is LLM-narrated.
- `ll-issues prioritize --apply ID=P2,ID2=P1,...` — performs all renames via `git mv`,
  returning `{id, old_path, new_path}` per entry.
- `/ll:prioritize-issues` shrinks to ~60 lines: read the JSON list, judge priorities,
  call `--apply`.

## Proposed Solution

Reuse `issue_parser.find_issues` / `is_normalized` for discovery and the `--apply k=v`
argument syntax already used by `ll-issues set-scores`. Renames go through `git mv` to
preserve history, matching ENH-2944's `apply_normalize` approach — share the rename
helper if ENH-2944 lands first, otherwise ENH-2944 adopts this one.

## Implementation Steps

1. `prioritize` discovery + `--json` + `--check` exit code.
2. `--apply` map parsing and renames.
3. Slim `commands/prioritize-issues.md` (233 → ~60), keeping only the P0–P5 judgment step.
4. Tests: fixture tree of prioritized/unprioritized issues; check-mode exit codes; apply
   idempotency; rename preserves git history.

## Program Design

### Types

- `PrioritizeEntry: dataclass`
  - `id: str`
  - `path: Path`
  - `current_priority: str | None`

### Signatures

- `list_unprioritized(issues_dir: Path) -> list[PrioritizeEntry]`
- `apply_priorities(mapping: dict[str, str], issues_dir: Path) -> list[tuple[Path, Path]]`

`--apply ID=P2,...` is parsed per the `ll-issues set-scores` style; renames go through
`git mv` to preserve history.

### Call Path

- `list_unprioritized()` -> `find_issues()` (existing, `issue_parser.py`)
- `apply_priorities()` -> `slugify()` (existing, `issue_parser.py`) -> `git mv` (subprocess)

## Scope Boundaries

- In scope: the `prioritize` subcommand (`--json`, `--check`, `--apply`) and slimming
  `commands/prioritize-issues.md`.
- Out of scope: the P0–P5 taxonomy itself, priority *judgment* (stays LLM), `normalize`
  (ENH-2944), `ll-issues skip`'s existing priority-bump path.

## Impact

- **Priority**: P2 - Thin, independently shippable, and removes a narrated exit-code gate
- **Effort**: Small - Discovery + a rename map
- **Risk**: Low - `--check` previews; renames are `git mv`

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues prioritize --check` exit code is the FSM-usable gate (0 clean / 1 unprioritized present)
- [ ] `--apply` performs all renames preserving git history; LLM supplies only the map
- [ ] `commands/prioritize-issues.md` contains no glob/regex/table-rendering instructions and no narrated exit codes
- [ ] pytest coverage in `scripts/tests/`
