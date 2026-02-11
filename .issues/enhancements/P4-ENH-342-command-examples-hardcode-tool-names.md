---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-342: Command examples hardcode tool names instead of config values

## Summary

Command templates and examples use literal tool names (`pytest`, `ruff`, `mypy`) instead of referencing the user's configured commands, which could mislead when a project uses different tools.

## Context

Identified during a config consistency audit. Lower priority since these are illustrative examples, but ideally they should reference or note the configurable commands.

## Affected Files

- `commands/create_loop.md` (lines ~81-88, 122, 149, 172-180): template examples hardcode `pytest`, `ruff`, `mypy`
- `commands/iterate_plan.md` (lines ~119-120): examples hardcode `pytest tests/` and `ruff check .`
- `commands/loop-suggester.md` (line ~55): lists hardcoded tools

## Proposed Fix

Either use `{{config.project.test_cmd}}` etc. in templates, or add a note like "uses your configured test command" next to examples.

---

## Status

**Open** | Created: 2026-02-11 | Priority: P4
