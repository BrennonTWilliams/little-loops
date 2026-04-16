---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
---

# ENH-1122: Frozen-Boundary Convention (`<!-- ll:mutable -->` / `<!-- ll:frozen -->` Markers)

## Summary

Formalize autoagent's editable-section-vs-adapter-boundary idea. Mark sections of `CLAUDE.md`, skills, agents, and commands with `<!-- ll:mutable -->` and `<!-- ll:frozen -->` HTML-comment markers so `harness-optimize` (FEAT-1120) and any future mutating loops only touch regions the author has explicitly opted in as mutable.

## Current Pain Point

Once FEAT-1120 lands, any loop that auto-mutates a prompt/skill/command risks clobbering sections the author considers load-bearing (entry points, tool lists, integration wiring, legal notices, safety instructions). autoagent addresses this by having a single-file harness with a clear editable section and a frozen adapter boundary. little-loops optimizes across many files and has no such convention, so a mutation loop would have to guess — or mutate the entire file — both of which are bad.

## Motivation

This enhancement would:
- Give authors an explicit guardrail against auto-mutation corrupting critical sections.
- Make `harness-optimize` (and any future mutating loop) safe to run on files that mix creative prose with load-bearing wiring.
- Establish a small, grep-friendly convention that non-Claude tooling can also respect.

This is only meaningful once FEAT-1120 exists. Capture now so we don't forget; defer implementation until harness-optimize proves out.

## Expected Behavior

- Authors wrap mutable regions with HTML comment pairs that survive markdown rendering:

  ```markdown
  <!-- ll:mutable:start name="examples" -->
  ...content that loops may rewrite...
  <!-- ll:mutable:end -->
  ```

- Everything outside `ll:mutable` blocks is considered frozen. An explicit `<!-- ll:frozen:start -->` / `<!-- ll:frozen:end -->` pair is also supported for documenting intent in files that are mostly mutable.
- Mutating loops (initially `harness-optimize`, FEAT-1120) MUST refuse to emit an edit that touches bytes outside a mutable region. Violations are rejected at the `apply` state and the mutation is discarded.
- A helper API — `scripts/little_loops/fsm/mutable_regions.py` — parses a file and returns `[(start_line, end_line, name)]` mutable spans.
- Default policy for files with no markers at all: treat the whole file as mutable (preserves current behavior for loops that don't care about the convention) — but `harness-optimize` can be configured to flip this default to "no markers = frozen" for safety.

## Use Case

**Who**: Skill/agent author who wants to expose one section of their prompt to auto-tuning without risking the rest

**Context**: A skill has a carefully-worded front matter, a fixed tool list, and a `## Examples` section that they're happy to let the harness optimize against a benchmark

**Goal**: Wrap just the examples section in `ll:mutable` markers; run `harness-optimize` without worrying about the rest getting overwritten

**Outcome**: Only the marked region changes across accepted iterations; diffs are small and auditable

## Proposed Solution

### New: `scripts/little_loops/fsm/mutable_regions.py`

- `parse(path: Path) -> list[MutableRegion]` returning `(start_line, end_line, name)`
- `validate_edit(original: str, edited: str, regions: list[MutableRegion]) -> bool` — returns True only if byte-diffs fall inside declared mutable regions
- Unit-testable pure function; no FS coupling beyond the parse entry point.

### Integration with FEAT-1120

`harness-optimize.yaml` gains an `apply` gate: before accepting a mutation, call `validate_edit`. Reject if the diff escapes mutable regions; log the violation to the trajectory.

### Docs & conventions

- `docs/reference/mutable-regions.md` — the marker syntax, examples, defaults
- Optional lint: `ll-verify-*` tool (existing pattern) can warn if a file uses malformed marker pairs
- Seed markers into the most-mutated project files over time (not in this issue — follow-up)

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | Where the validation hook sits in the FSM executor |
| `.claude/CLAUDE.md` | Candidate consumer — sections could be marked mutable once harness-optimize is proven |

## Acceptance Criteria

- [ ] `mutable_regions.py` parses both marker styles (`ll:mutable` and `ll:frozen`) and returns correct spans
- [ ] `validate_edit` rejects diffs outside mutable regions; accepts diffs inside
- [ ] Handles no-markers default (configurable: mutable-all vs frozen-all) with explicit opt-in in the loop config
- [ ] `harness-optimize` wires `validate_edit` into its `apply` state; rejected edits do not commit and are logged
- [ ] Unit tests cover: nested-markers error, unterminated-marker error, diff partly inside / partly outside region, no-markers default
- [ ] Docs published at `docs/reference/mutable-regions.md`

## Dependencies

Blocked by: FEAT-1120 (harness-optimize) — this convention is only meaningful once a mutating loop exists. Keep this issue deferred until FEAT-1120 lands and we have signal on whether the convention is actually needed (maybe authors are fine with whole-file mutation; maybe they're not).

## Session Log
- `/ll:capture-issue` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`

---

## Status

Open
