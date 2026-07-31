---
id: ENH-2943
title: "ll-loop rename and ll-loop cleanup: loop lifecycle mechanics out of markdown"
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- loops
- lifecycle
---

# ENH-2943: `ll-loop rename` + `ll-loop cleanup` — lifecycle mechanics out of markdown

## Summary

Three lifecycle files are near-100% mechanical: `skills/rename-loop/SKILL.md` (261 lines), `skills/cleanup-loops/SKILL.md` (398 lines), `commands/cleanup-worktrees.md` (64 lines). Move the mechanics into `ll-loop` subcommands.

## Current Behavior

- **rename-loop**: 9 steps, zero judgment — strip `.yaml`/kebab-case validation (L41–46), 2-path file location (L52–62), destination-exists + running-loop guards via `ls .loops/.running/<old>-*.pid` (L68–88), Grep for `loop:\s+<old>` refs across loops/tests/docs (L108–149), fixed-format dry-run and results tables (L155–180, L221–243), `replace_all` Edits (L206–218).
- **cleanup-loops**: deterministic 6-way classification (stuck-running / stale-interrupted / stale-interrupted-aged / abandoned-handoff / terminal / healthy) driven purely by `status` × `kill -0` pid-liveness × age thresholds (L108–195), including an inline `python3 -c` age computation the LLM is told to run (L99–106) and archive moves with string-sliced `run_id` (L281–295). Only Step 7 (L327–344) — root-cause narration from `tail -20 events.jsonl` — needs an LLM.
- **cleanup-worktrees**: 64 lines wrapping a single boolean: `ll-parallel --cleanup-orphans [--dry-run]`.

## Expected Behavior

- `ll-loop rename <old> <new> [--dry-run] [--yes]` — validates, guards (destination exists, loop running), renames the YAML, rewrites `loop:` references across loops/tests/docs, reports a summary. Skill → ~30 lines.
- `ll-loop cleanup [--dry-run] [--threshold <days>] [--interrupted-age <hours>] --json` — performs the 6-way classification, stops/archives per class, emits JSON per run. Skill keeps only the LLM hook: narrate root causes for interrupted/anomalous runs from the JSON + event tails.
- `commands/cleanup-worktrees.md` → a direct `ll-parallel --cleanup-orphans` invocation (a few lines).

## Proposed Solution

Reuse `ll-loop list/status --json` internals (state files, pid checks in `cli/loop/`), the psutil identity-checked liveness pattern from `ll-loop queue` (FEAT-2684), and `ll-parallel`'s existing cleanup flag. rename's reference rewrite can reuse the static `loop:` ref resolution logic in `fsm/validation.py`.

## Implementation Steps

1. `ll-loop rename` + tests (guards, dry-run parity with apply, ref rewriting).
2. `ll-loop cleanup` + tests (classification table as fixtures: status × pid × age).
3. Slim the three markdown files.

## Program Design

### Types

- `RenameReport: dataclass` — `old: str`, `new: str`, `yaml_moved: bool`, `refs_rewritten: list[tuple[Path, int]]`, `dry_run: bool`
- `RunClass: Enum` — `STUCK_RUNNING | STALE_INTERRUPTED | STALE_INTERRUPTED_AGED | ABANDONED_HANDOFF | TERMINAL | HEALTHY`
- `CleanupEntry: dataclass` — `run_id: str`, `loop: str`, `cls: RunClass`, `pid_alive: bool`, `age_minutes: float`, `action_taken: str`

### Signatures

- `rename_loop(old: str, new: str, dry_run: bool) -> RenameReport` — guards: destination exists, `.loops/.running/<old>-*.pid`
- `classify_run(status: str, pid_alive: bool, age_minutes: float, thresholds: CleanupThresholds) -> RunClass` — the skill's 6-way table as pure function
- `cleanup(dry_run: bool, thresholds: CleanupThresholds) -> list[CleanupEntry]`

### Call Path

- `main_loop()` (existing, `cli/loop/__init__.py`) -> `rename_loop()`
- `main_loop()` -> `cleanup()` -> `read_queue_entries()` (existing pid-marker pattern, `cli/loop/_helpers.py`)

## Scope Boundaries

- In scope: the two `ll-loop` subcommands, slimming the three markdown files, pid-liveness reuse from the FEAT-2684 pattern.
- Out of scope: changing classification semantics, `ll-parallel` internals (cleanup-worktrees just calls the existing flag), loop archival format changes.

## Impact

- **Priority**: P2 - ~660 lines of lifecycle prose removed; cleanup becomes safely re-runnable by automation
- **Effort**: Medium - Two subcommands, well-specified behavior
- **Risk**: Low - `--dry-run` parity tested; rename guards prevent destructive mistakes

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-loop rename --dry-run` output matches what `--yes` then performs
- [ ] `ll-loop cleanup --json` classification reproduces the skill's 6-way decision table
- [ ] `skills/rename-loop/SKILL.md` ≤ ~40 lines; `skills/cleanup-loops/SKILL.md` retains only invocation + root-cause narration
- [ ] `commands/cleanup-worktrees.md` is a direct `ll-parallel` invocation
- [ ] pytest coverage in `scripts/tests/`

## Notes

If oversized, `rename` is the natural standalone split.
