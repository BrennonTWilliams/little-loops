---
id: BUG-3356
type: BUG
title: gap-analysis refine passes consume max_refine_count despite documented exemption
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T23:26:59Z'
---

# BUG-3356: gap-analysis refine passes consume max_refine_count despite documented exemption

## Summary

`--gap-analysis` refine passes consume the `commands.max_refine_count` lifetime budget, contradicting three places that document them as exempt.

## Current Behavior

`"refine_count"` (read by `ll-issues refine-status --json`, `scripts/little_loops/cli/issues/refine_status.py`) is a raw occurrence count of `/ll:refine-issue` lines in `## Session Log` (`session_log.py` / `issue_parser.py` `session_command_counts`). `ll-issues append-log` (`cli/issues/append_log.py`) takes no mode discriminator, and `commands/refine-issue.md` appends the Session Log entry unconditionally — including on `--gap-analysis` runs (its own text says "Still append the Session Log entry").

Consequence: `refine-to-ready-issue.yaml`'s `refine_followup` state (`--auto --gap-analysis`) silently burns lifetime budget, and `check_lifetime_limit` decomposes issues earlier than the documented contract allows.

## Steps to Reproduce

1. Pick an issue file that already has a `## Session Log` section (or run any `/ll:*` command against it once to create one).
2. Note its current `refine_count`: `ll-issues refine-status <ID> --json`.
3. Run `/ll:refine-issue <ID> --gap-analysis` (or let `refine-to-ready-issue.yaml`'s `refine_followup` state do it).
4. Re-check `ll-issues refine-status <ID> --json` — observe `refine_count` incremented by the gap-analysis pass, contradicting the exemption documented in `config-schema.json`'s `commands.max_refine_count` description, `commands/refine-issue.md`, and `refine-to-ready-issue.yaml`'s `refine_followup` comment.

## Expected Behavior

Contradicted documentation (all three claim the exemption):
- `scripts/little_loops/config-schema.json` `commands.max_refine_count` description: "Gap-analysis runs (`--gap-analysis` flag) are exempt from this cap"
- `commands/refine-issue.md` (cap discussion)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` `refine_followup` comment (now corrected to note the bug)

Either implement the exemption (e.g. append a mode-discriminated Session Log entry like `/ll:refine-issue --gap-analysis` and have `session_command_counts` / `refine-status` count only non-gap entries toward `refine_count`) or drop the exemption claim from all three documents. Implementing the discriminator is preferred: the gap-analysis pass is additive-only and was deliberately designed not to consume budget (ENH-2247).

## Program Design

### Types

N/A — no new data shape; the existing `dict[str, int]` session-command-count mapping keyed by literal command string is reused.

### Signatures

- `count_session_commands(content: str) -> dict[str, int]` — existing (`session_log.py:96`); counts `_COMMAND_RE` matches verbatim, so a `--gap-analysis` run and a normal run both increment the same `/ll:refine-issue` key today.
- `append_session_log_entry(issue_path: Path, command: str, session_jsonl: Path | None = None) -> bool` — existing (`session_log.py:275`); `command` is written into the entry verbatim, so the caller controls what string gets counted.
- `cmd_append_log(config: BRConfig, args: object) -> int` — existing (`cli/issues/append_log.py:13`); passes `args.log_command` through to `append_session_log_entry` unmodified.

### Call Path

`commands/refine-issue.md` (`--gap-analysis` run) -> `ll-issues append-log` -> `cmd_append_log` -> `append_session_log_entry` (writes an undifferentiated `/ll:refine-issue` entry) -> `count_session_commands` / `IssueInfo.session_command_counts` -> `refine_status.py`'s `refine_count` (counts the gap-analysis entry toward the cap).

### Decision Rules

N/A — no new decision logic; the fix adds a discriminator to an existing count rather than new branching behavior.

## Impact

- **Priority**: P3 - matches the filename prefix; a silently-eroded exemption in a lifetime-budget guardrail, not a user-facing break or data-loss risk.
- **Effort**: Small - a mode-discriminated Session Log entry plus a count filter in `count_session_commands`/`refine_status.py`; no new architecture.
- **Risk**: Low - additive to existing counting logic; `scripts/tests/test_refine_status.py` and `test_session_log.py`-style tests already pin current-count behavior and would catch a regression.
- **Breaking Change**: No - the discriminator is additive to the Session Log entry format; `refine_count`'s JSON shape is unchanged, only which entries it counts.

## Discovered

2026-08-28 review/refactor of `refine-to-ready-issue.yaml` (loop-side comment updated in the same pass; this issue tracks the CLI/command-side fix).

## Status

**Open** | Created: 2026-08-28 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-08-29T18:20:58 - `477f6591-ae32-49d7-bc90-ee1e0759ddc3.jsonl`
