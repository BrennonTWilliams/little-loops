---
id: ENH-2950
title: "ll-issues locate-options --json: expose option spans so decide-issue stops re-implementing Patterns 1-5"
type: ENH
priority: P1
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2939
- ENH-2936
- ENH-2443
labels:
- cli
- issues
- determinism
- drift
---

# ENH-2950: `ll-issues locate-options --json` — option spans for decide-issue

## Summary

`skills/decide-issue/SKILL.md` Phase 3 (Patterns 1–4, L150–196) and Phase 3b (Provisional
Patterns A–E, L197–336) specify option detection in prose, while
`issue_parser.locate_enumerable_options` (L527–565) implements the same precedence chain
in Python. ENH-2936 proved the divergence risk is live: it had to land Pattern E in
**both** places in one commit (`5e29c4d4`). Expose the Python locator's full result as
JSON so the skill reads spans instead of re-scanning.

## Current Behavior

- `ll-issues check-decidable <ID>` is exit-code only (`cli/issues/check_decidable.py`);
  its `--help` exposes no output flag.
- `locate_enumerable_options(content) -> tuple[int, str | None]` returns only
  `(count, containing_heading)` — enough for a boolean gate, not enough for a consumer.
- Phase 3b does not merely *detect*: it **materializes** options, writing
  `**Option A**`/`**Option B**` blocks into the issue file before Phase 4–7 scoring.
  A boolean gate therefore cannot replace the skill's pattern prose — which is why
  ENH-2939 (markdown-only) cannot absorb this work.

## Expected Behavior

- `ll-issues locate-options <id> [--json]` → `{id, count, pattern, heading, options: [{label, text, start_line, end_line}]}`,
  where `pattern` names which rule fired (`section_header` | `bold_label` | `numbered` |
  `bullet` | `provisional_a` … `provisional_e`) so the skill can branch on provenance
  without re-deriving it.
- `check-decidable` keeps its exit-code contract unchanged (FSM loops consume it) and is
  reimplemented over the same locator result — one code path, two frontends.
- decide-issue Phase 3/3b becomes: call `locate-options --json`; if `pattern` is a
  provisional (A–E) shape, materialize the returned spans into `**Option N**` blocks;
  proceed to Phase 4. The pattern *definitions* live only in `issue_parser.py`.

## Proposed Solution

Widen `locate_enumerable_options` (or add a sibling returning a richer dataclass) so the
span/label data the patterns already compute internally is returned rather than discarded.
`check_decidable.py` and the new subcommand both consume it. No pattern-semantics changes —
this is a return-shape widening plus a CLI frontend.

## Implementation Steps

1. Introduce `LocatedOptions` dataclass and return it from the locator; adapt
   `count_enumerable_options` / `check-decidable` call sites (behavior-preserving).
2. Add `locate-options` subparser with `--json`.
3. Rewrite decide-issue Phase 3/3b to consume the JSON; delete the pattern regexes and
   their prose restatements (~120 lines). Keep the materialization step and Phase 4–7.
4. Tests: fixture issues per pattern (1–4, A–E) asserting identical `count` to today's
   `check-decidable` exit code, plus span correctness for the provisional shapes.

## Program Design

### Types

- `LocatedOption: dataclass`
  - `label: str`
  - `text: str`
  - `start_line: int`
  - `end_line: int`
- `LocatedOptions: dataclass`
  - `count: int`
  - `pattern: str | None`
  - `heading: str | None`
  - `options: list[LocatedOption]`

### Signatures

- `locate_enumerable_options(content: str) -> LocatedOptions`
- `locate_options(issue_id: str, issues_dir: Path) -> LocatedOptions`

Widened return; existing `(count, heading)` consumers read `.count` / `.heading`. New
`locate-options` subparser wired in `scripts/little_loops/cli/issues/__init__.py`.

### Call Path

- `check_decidable()` (existing, `cli/issues/check_decidable.py`) -> `locate_enumerable_options()` (existing, `issue_parser.py`)
- `locate_options()` (new) -> `locate_enumerable_options()` -> `parse_frontmatter()` (existing, `issue_parser.py`)

## Scope Boundaries

- In scope: locator return-shape widening, the `locate-options` subcommand, decide-issue
  Phase 3/3b prose deletion.
- Out of scope: changing which shapes count as decidable (that is ENH-2936/ENH-2443
  territory), decide-issue Phases 4–7 scoring, `check-decidable`'s exit-code contract.

## Impact

- **Priority**: P1 - Wave 1; removes the epic's most recently-*re-created* prose/Python duplication (ENH-2936 landed Pattern E twice in one commit)
- **Effort**: Small - Return-shape widening plus a thin subcommand
- **Risk**: Low - Behavior-preserving for existing consumers; exit-code contract untouched

## Status

**Open** | Created: 2026-07-31 | Priority: P1

## Acceptance Criteria

- [ ] `ll-issues locate-options <id> --json` returns count, firing pattern, and option spans
- [ ] `check-decidable`'s exit code is unchanged for every existing fixture (parity test)
- [ ] `skills/decide-issue/SKILL.md` contains no option-detection regexes or pattern definitions; it materializes from CLI output
- [ ] Pattern precedence is defined in exactly one place (`issue_parser.py`)
- [ ] pytest coverage in `scripts/tests/`

## Notes

Split out of ENH-2939, whose markdown-only scope could not absorb it: Phase 3b writes
option blocks into the file, so a boolean gate is insufficient.
