---
id: FEAT-3485
type: FEAT
title: Decision-record to open-code-review rule exporter
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T04:15:42Z'
learning_tests_required:
  - open-code-review
---

# FEAT-3485: Decision-record to open-code-review rule exporter

## Summary

Export little-loops decision records into open-code-review's (OCR, https://github.com/alibaba/open-code-review) rule format, so OCR's own shipped review plugins enforce little-loops decisions mechanically at review time. Decisions are currently recorded but only enforced via `.claude/CLAUDE.md` prose — nothing closes that loop mechanically.

This is piece 1 of a two-piece OCR integration; piece 2 (a delegate-mode review loop that runs `ocr delegate preview` / `ocr delegate rule` as FSM shell states) is planned separately, so the exported rule format must stay consumable by both.

## Current Behavior

Decisions are recorded via `ll-issues decisions` (`.ll/decisions.yaml` / `.ll/decisions.d/`), but enforcement is prose-only: an agent must read and follow the corresponding guidance in `.claude/CLAUDE.md` at implementation time. Nothing consumes the decision records programmatically during code review.

## Expected Behavior

Running the exporter emits open-code-review (OCR) rule file(s) covering all active (non-superseded) decisions, so OCR's own shipped review plugins enforce those decisions mechanically at review time — no agent has to notice and apply the prose.

## Motivation

- Closes the loop between recording a decision and enforcing it: today a required rule only affects future work if an agent reads and follows `.claude/CLAUDE.md` prose.
- Removes reliance on agent recall for mechanical, checkable rules.
- Establishes the rule format that piece 2 (a delegate-mode `ocr delegate preview`/`ocr delegate rule` review loop) will also consume, so the two pieces stay compatible.

## Proposed Solution

- Reuse `resolve_active()` (`scripts/little_loops/decisions.py:495`) to select active decisions. The analysis that prompted this misattributed it to `decisions_sync.py`, which is a separate module.
- Split the exporter into two layers instead of one OCR-coupled function, mirroring the existing little-loops pattern of a canonical form plus thin per-target adapters (`host_runner.py`'s `resolve_host()`, `ll-adapt --host <gemini|kimi-code|qwen>`):
  1. `decisions_to_rules()` — target-agnostic. Maps `resolve_active()`'s output to a small generic `RuleRecord` IR (id, description, severity, path filters, source decision id). No knowledge of OCR's file format.
  2. `export_ocr_rules()` — the only OCR-specific piece. Maps `RuleRecord`s to OCR's actual rule file(s)/schema.
- Rationale: piece 2 (the delegate-mode review loop) and any future second rule-engine target can consume the same IR without caring how OCR formats it; if OCR's schema turns out different than expected once verified, only the adapter changes. Not building a multi-target registry/plugin system now — no second target is named, and that would be over-scoped for a P4/few-dozen-line issue.

## Verify First

Unverified claims from the prompting analysis:

- OCR's actual rule/config format and how rules are consumed (file path, schema, path filters). Check the OCR repo (https://github.com/alibaba/open-code-review) docs before finalizing the export shape.

## Integration Map

### Files to Modify
- `scripts/little_loops/decisions.py` — no changes expected; consumed via `resolve_active()`
- New module(s) under `scripts/little_loops/` (name TBD) holding `decisions_to_rules()` (generic IR) and `export_ocr_rules()` (OCR-specific adapter) — either one file or split, sized to the "few dozen lines" estimate — or a CLI subcommand under `ll-issues decisions`

### Dependent Files (Callers/Importers)
- None yet — this is a new export path with no existing callers. Piece 2 (delegate-mode review loop) will call it once the rule format is finalized.

### Similar Patterns
- `decisions_sync.py`'s `sync_to_local_md` for the pattern of rendering decision entries to an external artifact
- `host_runner.py`'s `resolve_host()` / `ll-adapt --host <gemini|kimi-code|qwen>` for the canonical-form-plus-per-target-adapter split this issue reuses

### Tests
- New unit test with a fixture decision set covering active/superseded filtering (Acceptance Criteria #3)

### Documentation
- `docs/reference/API.md`, `docs/reference/CLI.md` — document the new exporter once implemented

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- This codebase holds two competing canonical-form-plus-adapter conventions, not one, for the pattern the issue cites: `host_runner.py`'s `resolve_host()` keeps every per-target class eagerly imported in a single file behind a `dict[str, type[...]]` registry (`host_runner.py:2224`), while `ll-adapt`'s `adapters/core.py` keeps one file per target with lazy `importlib` registration specifically to avoid a circular import with its shared core module (`adapters/core.py:53`, `:63`). The issue names only the first; the second is an equally established precedent for the opposite file-layout choice.
- A frozen `@dataclass` IR consumed by several per-target modules is an established shape in this codebase — `HostCapabilityEntry` (`adapters/capabilities.py:57`), one instance per target held in a module-level dict — consistent with the issue's proposed `RuleRecord`.
- The one existing function matching `export_ocr_rules`'s `(rules, output_dir) -> list[Path]` write-and-report-paths shape is `generate_schemas()` (`scripts/little_loops/generate_schemas.py:950`): it iterates a source collection, writes one file per item, and accumulates/returns the written paths. Other `-> list[Path]` functions in this codebase (`_tracked_py_files`, `list_workspaces`, etc.) are read/discovery functions, not write-and-report ones.
- `sync_to_local_md()` (`scripts/little_loops/decisions_sync.py:31`) — the issue's cited rendering precedent — narrows to `RuleEntry` instances with `enforcement == "required"` *before* calling `resolve_active()` (`decisions_sync.py:42-45`), renders only the `.rule` free-text field (no id/category/severity), writes via `atomic_write`, and returns `None` (a single fixed-path file) rather than `list[Path]`.
- CLI wiring convention for a new `ll-issues decisions` subcommand: subparser registration in `add_decisions_parser()`, dispatch in `cmd_decisions()`, and a private `_cmd_*(path) -> int` helper that lazily imports the implementation module and translates exceptions to a printed error plus exit code (see `_cmd_sync`, `scripts/little_loops/cli/issues/decisions.py:550`).
- Test conventions: `TestResolveActive` (`scripts/tests/test_decisions.py:395`) tests the filter itself via inline-constructed dataclass fixtures, no external fixture file. `TestSyncToLocalMd` (`scripts/tests/test_decisions.py:491`) tests a decisions-log-consuming renderer via a `tmp_path`-backed `.ll/decisions.yaml`, then asserts on the written artifact's content — the closer precedent for testing an end-to-end exporter. `TestGenerateSchemas` (`scripts/tests/test_generate_schemas.py:122`) tests idempotency of a write-and-report-paths function by calling it twice into `tmp_path` and comparing file contents — direct precedent for Acceptance Criteria #2.

## Program Design

### Types

- Reuses the existing decision entry types from `scripts/little_loops/decisions.py` for input.
- New: `RuleRecord` — the target-agnostic IR (id, description, severity, path filters, source decision id) that `decisions_to_rules()` emits and `export_ocr_rules()` consumes.

### Signatures

- `decisions_to_rules(decisions: list[AnyEntry]) -> list[RuleRecord]` — target-agnostic mapping, no OCR-specific knowledge.
- `export_ocr_rules(rules: list[RuleRecord], output_dir: Path) -> list[Path]` — the only OCR-specific function; maps `RuleRecord`s to OCR's rule file(s)/schema.

### Call Path

`resolve_active()` (`scripts/little_loops/decisions.py:495`) -> `decisions_to_rules()` -> `export_ocr_rules()` -> OCR rule file(s) on disk

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- Neither `severity` nor a path/glob filter field exists anywhere on the four decision entry types in `scripts/little_loops/decisions.py` (`RuleEntry`, `DecisionEntry`, `ExceptionEntry`, `CouplingEntry`). The closest analogs are `enforcement` (`RuleEntry`/`CouplingEntry`, a 2-3 value string — `advisory`/`required` — not a graded severity) and `CouplingEntry.if_changed` (a glob path filter, but scoped to the separate coupling/audit entry type, not `RuleEntry`). The proposed `RuleRecord` IR's `severity` and `path filters` fields therefore have no direct source on `RuleEntry`, the type this exporter is expected to operate on — a mapping decision (e.g. derive `severity` from `enforcement`, and treat an absent path filter as "applies repo-wide") is needed before `decisions_to_rules()`'s body can be written.
- `resolve_active()` (`decisions.py:495`) operates on the full `AnyEntry` union and returns a mix of `RuleEntry`/`DecisionEntry`/`ExceptionEntry`/`CouplingEntry` when called on an unfiltered list. The issue's stated Call Path (`resolve_active() -> decisions_to_rules()`) implies feeding its raw output directly in, but the one existing caller that renders to an external artifact (`sync_to_local_md`) pre-filters to `RuleEntry` with `enforcement == "required"` *before* calling `resolve_active()`, while the other caller (`_cmd_list`) isinstance-branches per entry type *after* calling it. `decisions_to_rules()` needs to decide which entry types map to a rule (at minimum `RuleEntry`; possibly `CouplingEntry`, which also carries `enforcement`/`supersedes`) and how to handle the rest (skip vs. raise) — the issue's Program Design section as written does not decide this.

## Implementation Steps

1. Confirm OCR's rule/config format (file path, schema, path filters) per Verify First.
2. Implement `decisions_to_rules()` (generic IR, no OCR knowledge) and `export_ocr_rules()` (the OCR-specific adapter), feeding the former's output into the latter.
3. Wire it up as a command or script per the Proposed Solution.
4. Add the fixture-based unit test (Acceptance Criteria #3) and confirm idempotency (Acceptance Criteria #2).

## Acceptance Criteria

1. Running the exporter emits rule file(s) covering all active (non-superseded) decisions; superseded ones are excluded via `resolve_active` semantics.
2. Idempotent: re-running over an unchanged decision set produces identical output.
3. Unit test with a fixture decision set covering active/superseded filtering.

## Priority Rationale

P4 — small, unblocked, and recommended as the first of the two OCR pieces.

## Impact

- **Priority**: P4 - small, unblocked, first of two planned OCR integration pieces
- **Effort**: Small - expected a few dozen lines; reuses existing `resolve_active()`
- **Risk**: Low - additive export path; doesn't change existing decision recording or consumption
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-16 | Priority: P4

## Use Case

**Who**: A little-loops maintainer running OCR-based code review on this repo.

**Context**: A decision has been recorded (e.g. a required rule via `ll-issues decisions`) but today is only enforced through `.claude/CLAUDE.md` prose.

**Goal**: Run the exporter to regenerate OCR rule file(s) from the active decision set so OCR's shipped plugins check the rule automatically.

**Outcome**: Code review flags violations of active decisions without a human or agent needing to recall the prose rule.

## API/Interface

```python
def decisions_to_rules(decisions: list[AnyEntry]) -> list[RuleRecord]:
    """Map active decisions to a target-agnostic rule IR."""

def export_ocr_rules(rules: list[RuleRecord], output_dir: Path) -> list[Path]:
    """Emit OCR rule file(s) from the rule IR. The only OCR-specific function."""
```

## Edge Cases

## UI/UX Details


## Session Log
- `/ll:refine-issue` - 2026-09-16T04:29:14 - `3cab3e66-607f-42d5-a4a3-fd8f1228edab.jsonl`
- `/ll:format-issue` - 2026-09-16T04:19:47 - `6c5fb4c3-b655-4820-8bf8-9f99b327e9fc.jsonl`
- `/ll:capture-issue` - 2026-09-16T04:15:49 - `b650788f-edb5-4a45-abe3-046c38ae23e3.jsonl`
