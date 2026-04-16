---
discovered_date: 2026-04-16
discovered_by: capture-issue
---

# ENH-1123: Configurable ll-issues next-issue Selection Behavior

## Summary

`ll-issues next-issue` currently uses a hardcoded sort key to pick the top active issue. There is no configuration surface in `config-schema.json` or `.ll/ll-config.json` to change the selection strategy, so projects that prefer priority-first ordering, different tie-breakers, or alternative signals must patch Python source.

## Current Behavior

At `scripts/little_loops/cli/issues/next_issue.py:33-39`, issues are sorted by a fixed tuple:

```python
issues.sort(
    key=lambda i: (
        -(i.outcome_confidence if i.outcome_confidence is not None else -1),
        -(i.confidence_score if i.confidence_score is not None else -1),
        i.priority_int,
    )
)
```

`config-schema.json` exposes `issues.priorities` (the allowed priority list) but has no `issues.next_issue` section. The only user-facing controls are the `--skip`, `--json`, and `--path` CLI flags.

## Expected Behavior

`.ll/ll-config.json` should support a `issues.next_issue` block that lets projects:

- choose an ordered list of sort keys (e.g., `priority`, `outcome_confidence`, `confidence_score`, `age`, `size`)
- set direction per key (asc/desc)
- optionally preset a named strategy (e.g., `"priority_first"`, `"confidence_first"` — current default)

The CLI continues to accept the existing flags; config provides the default when no flag overrides it.

## Motivation

Teams working in strict priority order (P0 before anything else) currently get surprised when a P3 issue with high outcome_confidence is returned ahead of an unready P1. Forcing a code edit to change this is a poor fit for a per-project workflow toolkit whose other selection knobs (priorities list, categories, duplicate thresholds) are already config-driven. One schema addition unblocks several downstream adopters without changing default behavior.

## Proposed Solution

1. Extend `config-schema.json` under `issues` with a `next_issue` object:
   - `strategy`: enum of named presets (default `"confidence_first"` preserves today's behavior)
   - `sort_keys`: array of `{key, direction}` objects for custom ordering (overrides `strategy` when present)
2. Add a resolver in `little_loops/config.py` (or a small helper module) that turns the config into a sort-key function.
3. Replace the hardcoded lambda in `cli/issues/next_issue.py` with that resolver, defaulting to the `confidence_first` preset when config is absent.
4. Validate unknown keys/strategies up front and surface a clear config error instead of failing silently at sort time.

Keep `--skip`, `--json`, `--path` unchanged. Consider a future `--strategy` CLI flag for one-off overrides, but that can be a follow-up.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/next_issue.py` — replace hardcoded sort with config-driven resolver
- `scripts/little_loops/config.py` — add config parsing for `issues.next_issue`
- `config-schema.json` — add `issues.next_issue` block with strategy/sort_keys
- `docs/reference/API.md` — document new config keys

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — wires `next-issue` subcommand; verify no assumptions about sort order
- `scripts/little_loops/loops/*.yaml` — loops that shell out to `ll-issues next-issue` (e.g., `refine-to-ready-issue.yaml`, `auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`) should keep working under the default strategy

### Similar Patterns
- `scripts/little_loops/cli/issues/next_issues.py` — plural variant; consider applying the same strategy resolver for consistency
- Existing config-driven resolvers for priorities and duplicate thresholds in `config.py` as prior art

### Tests
- `scripts/tests/` — add coverage for default strategy, `priority_first` preset, and a custom `sort_keys` config
- Regression test that no-config behavior matches today's hardcoded order

### Documentation
- `docs/reference/API.md` (CLI reference for `ll-issues next-issue`)
- `config-schema.json` descriptions must explain each strategy

### Configuration
- `.ll/ll-config.json` gains optional `issues.next_issue` block; no migration needed for existing configs

## Implementation Steps

1. Design the `issues.next_issue` schema (strategies + custom `sort_keys`) and add it to `config-schema.json` with descriptions.
2. Implement the config parser and sort-key resolver; default preset reproduces today's tuple.
3. Refactor `next_issue.py` (and `next_issues.py` for parity) to use the resolver.
4. Add unit tests covering defaults, each named preset, and a custom `sort_keys` override.
5. Update `docs/reference/API.md` with the new config block and examples.

## Impact

- **Priority**: P3 - Quality-of-life improvement; no user is blocked, but the hardcoded behavior has already produced friction in loops that select by priority.
- **Effort**: Small - Isolated change: one CLI module, one config section, and tests. Existing patterns (priorities, duplicate thresholds) provide a template.
- **Risk**: Low - Default preset preserves current behavior; no schema field is required. Breakage limited to misconfigured `sort_keys`, caught by validation.
- **Breaking Change**: No

## API/Interface

```jsonc
// .ll/ll-config.json (excerpt)
{
  "issues": {
    "next_issue": {
      "strategy": "priority_first",
      // Optional custom order overrides strategy:
      "sort_keys": [
        {"key": "priority", "direction": "asc"},
        {"key": "outcome_confidence", "direction": "desc"},
        {"key": "confidence_score", "direction": "desc"}
      ]
    }
  }
}
```

## Scope Boundaries

- Out of scope: new sort signals beyond fields already parsed on issues (e.g., git age, sprint membership). Those can be added incrementally once the resolver exists.
- Out of scope: CLI flag for ad-hoc strategy override (`--strategy`). Track separately if demand emerges.
- Out of scope: changing `ll-issues next-issues` (plural) selection logic beyond mirroring the same resolver.

## Related Key Documentation

| Document | Category | Why relevant |
|----------|----------|--------------|
| `docs/reference/API.md` | architecture | CLI reference for `ll-issues` subcommands; must document new config keys |
| `.claude/CLAUDE.md` | guidelines | Mentions `ll-issues` as the issue management CLI; keep command surface description accurate |

## Labels

`enhancement`, `cli`, `config`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/783ff1cd-1bba-41de-abf8-cb667d74e9da.jsonl`

---

**Open** | Created: 2026-04-16 | Priority: P3
