---
id: ENH-3457
type: ENH
title: ll-messages defaults to user messages only
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-12'
captured_at: '2026-09-12T03:43:46Z'
---

# ENH-3457: ll-messages defaults to user messages only

## Summary

`ll-messages` currently emits both user prompts and assistant bash commands by default. When the JSONL output is piped into `pbcopy` (or any non-JSON-aware sink), the two record kinds become indistinguishable in the paste — a copy of pasted text looks like "all user messages" but actually mingles assistant-issued commands with user prompts. The on-the-wire JSONL has a `"type": "command"` discriminator (set by `CommandRecord.to_dict()` in `scripts/little_loops/user_messages.py`), but it is invisible without parsing.

## Current Behavior

`ll-messages` defaults to including both user prompts and assistant CLI commands in a single JSONL stream. The flag `--skip-cli` is required to exclude commands; `--commands-only` is required to get commands in isolation. The current default is biased toward the merged-stream case, which surprises the clipboard workflow `ll-messages -n 100 --stdout | pbcopy` — pasted text mingles user prompts and bash invocations with no on-paste visual boundary.

## Expected Behavior

`ll-messages` defaults to **user messages only**. Running `ll-messages` with no flags, or `ll-messages -n 100 --stdout | pbcopy`, emits only user-prompt records. A new `--include-cli` opt-in flag restores today's merged-stream behavior. `--commands-only` continues to work as a high-level convenience for "commands only."

## Motivation

Power users triaging their session history expect `ll-messages` to surface user prompts, not bash invocations. Today the only way to get just user messages is `ll-messages --skip-cli`, which is one extra flag away from the obvious outcome. The current default biases toward surprise on the clipboard workflow (`ll-messages -n 100 --stdout | pbcopy`) that prompted the investigation.

## Proposed Solution

Flip the default of `--skip-cli` from `False` to `True` and introduce a new `--include-cli` flag as the explicit opt-in to the merged-stream behavior. Concretely:

- In `scripts/little_loops/cli/messages.py` (`main_messages`), change the `--skip-cli` argparse default to `True`, add `--include-cli` (action=`store_true`, default=`False`), and invert the existing `if not args.skip_cli or args.commands_only:` guard so it reads `if args.include_cli or args.commands_only:`.
- Update the argparse `help=` strings and epilog examples (`%(prog)s --skip-cli` → `%(prog)s --include-cli`) so the documented happy path matches the new default.
- Update docstrings on `extract_user_messages` and `extract_commands` in `scripts/little_loops/user_messages.py` to note that the CLI surface defaults to user-only.
- Update `docs/reference/CLI.md` (the `ll-messages` section) and any cross-references in `docs/reference/API.md` to flag the default flip.
- Add a changelog entry under a concrete release header (per project policy — no `[Unreleased]`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — flip `--skip-cli` default to `True`, add `--include-cli`, invert the CLI-commands branch guard, update argparse `help=`/epilog, update the `%(prog)s --skip-cli` example to `%(prog)s --include-cli`.
- `scripts/little_loops/user_messages.py` — update docstrings on `extract_user_messages` / `extract_commands` to mention the CLI surface flag default.
- `docs/reference/CLI.md` — update the `ll-messages` reference section.
- `docs/reference/API.md` — flag the default flip in any section referencing `extract_user_messages` / `extract_commands`.

### Dependent Files (Callers/Importers)
- Any project-local script or test that invokes `main_messages()` and asserts on the default output stream — search with `grep -rn "main_messages\|ll-messages" scripts/`.
- Any consumer that shells out to `ll-messages` without flags and relies on the merged stream — N/A inside this repo but documented as a breaking change.

### Similar Patterns
- No existing CLI in `scripts/little_loops/cli/` flips a default flag with an `--include-*` mirror; the `--commands-only` / `--skip-cli` pair is the closest analog (mutually exclusive modes selected by flag).

### Tests
- `scripts/tests/` — adjust any test that asserts the default output includes CLI commands. Likely candidates under `scripts/tests/test_messages*.py` or `scripts/tests/cli/test_messages*.py` (verify via `grep -rln "skip_cli\|include_cli\|commands_only" scripts/tests/`).

### Documentation
- `docs/reference/CLI.md` — `ll-messages` reference section.
- `docs/reference/API.md` — cross-references on `extract_user_messages` / `extract_commands`.

### Configuration
- N/A

## Implementation Steps

1. Flip `--skip-cli` default to `True` and add `--include-cli` (default `False`) in `main_messages`; invert the CLI-commands branch guard so the new opt-in is the trigger.
2. Update argparse `help=` strings and epilog examples so the documented happy path reflects the new default.
3. Update docstrings on `extract_user_messages` and `extract_commands` in `scripts/little_loops/user_messages.py`.
4. Update `docs/reference/CLI.md` and `docs/reference/API.md` to flag the default flip.
5. Adjust any test asserting default output includes CLI commands; add a regression test asserting the default emits user messages only and that `--include-cli` restores the merged stream.
6. Add a changelog entry under a concrete release header.
8. Verify with `python -m pytest scripts/tests/` and a manual `ll-messages -n 5 --stdout | pbcopy` smoke test confirming only user prompts land on the clipboard.

## Impact

- **Priority**: P2 - Quality-of-life default that affects every `ll-messages` user on the clipboard workflow; not blocking, but high-frequency surprise surface.
- **Effort**: Small - One argparse flip, one new flag, docstring/help/doc updates, one test adjustment.
- **Risk**: Medium - Documented breaking change for any user/script relying on today's default merged stream; mitigated by `--include-cli` mirror flag and prominent changelog note.
- **Breaking Change**: Yes - Default output stream changes from `{user + commands}` to `{user only}`.

## Program Design

### Types

- `Args` (argparse namespace in `main_messages`): `skip_cli: bool` (default `True`, post-flip), `include_cli: bool` (default `False`, new), `commands_only: bool` (unchanged).

### Signatures

- `main_messages() -> int` — entry point; flipped default + new flag.
- `extract_user_messages(db: SessionDB, limit: int) -> list[UserMessage]` — unchanged behavior; docstring updated.
- `extract_commands(db: SessionDB, limit: int, tools: list[str]) -> list[CommandRecord]` — unchanged behavior; docstring updated.
- `CommandRecord.to_dict() -> dict` — unchanged; `"type": "command"` discriminator stays for JSONL consumers that parse it.

### Call Path

`main_messages()` → `argparse.parse_args()` (defaults: `skip_cli=True`, `include_cli=False`, `commands_only=False`) → `if args.commands_only:` branch → `extract_user_messages(...)` → `if args.include_cli or args.commands_only:` branch → `extract_commands(...)` → `_save_combined(...)` JSONL emit.

## Scope Boundaries

In scope:

- Argparse default flip, new `--include-cli` flag, branch-guard inversion in `main_messages`.
- Docstring/help/epilog/doc updates for `ll-messages`.
- Test adjustments + a regression test covering the new default and the `--include-cli` opt-in.
- Changelog entry under a concrete release header.

Out of scope:

- Codex / kimi synthetic-user filtering on Claude-shaped hosts. Related but separate: `_CODEX_EXCLUDED_USER_TEXT_PREFIXES` (`scripts/little_loops/user_messages.py`) is already applied to non-Claude-shaped hosts.
- A short-term `LL_MESSAGES_INCLUDE_CLI=true` env-var fallback — noted as a gentler bridge but deferred unless asked for.

## Use Case

User runs `ll-messages -n 100 --stdout | pbcopy` expecting to triage their recent prompts in another tool. Today they get an interleaved blob; after the flip, they get just user messages.

## Backward Compatibility

This is a breaking change for anyone scripting against the current default. Mitigation:

- Document prominently in the changelog.
- Keep `--include-cli` as the literal mirror of the old default.
- A short-term `LL_MESSAGES_INCLUDE_CLI=true` env-var fallback would be a gentler bridge — defer unless asked for.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-12 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-12T03:46:55 - `d4cc78b3-7b01-4dfe-9c49-d8730730c0cd.jsonl`
- `/ll:capture-issue` - 2026-09-12T03:43:54 - `9c967725-d34b-4768-bd95-ced00b928d94.jsonl`