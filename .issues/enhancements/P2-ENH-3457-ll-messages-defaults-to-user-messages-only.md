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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

### Files to Modify (additions)

- `scripts/little_loops/cli/messages.py` — three concrete edits (from `codebase-analyzer`, anchored):
  - **Line 47** (epilog): update `%(prog)s --skip-cli` example to `%(prog)s --include-cli`.
  - **Line 109-113**: flip `--skip-cli` argparse default from `False` to `True` and update its `help=` text from `"Exclude CLI commands from output (included by default)"` to something matching the new default.
  - **Line 114-118**: leave `--commands-only` as-is.
  - **Add** `--include-cli` argparse entry adjacent to `--skip-cli` (action=`store_true`, default `False`, help mentioning the merged-stream opt-in).
  - **Line 200**: leave `if not args.commands_only:` as-is — it gates `extract_user_messages`, not commands.
  - **Line 209**: invert the guard `if not args.skip_cli or args.commands_only:` to `if args.include_cli or args.commands_only:` (literal substitution; no other call site).
  - **Lines 14-21** (`main_messages` docstring): note "defaults to user messages only; pass `--include-cli` to merge in assistant bash commands."
- `scripts/little_loops/user_messages.py` — docstring updates at `:723-743` (`extract_user_messages`) and `:896-911` (`extract_commands`) noting that the CLI surface flag defaults to user-only.
- `scripts/tests/test_cli_messages.py:118` — `TestMessagesCommandsOnly` (no change to behavior tests, but the class name/header comment about "excludes user" still holds).
- `scripts/tests/test_cli_messages.py:172` — `TestMessagesSkipCli` class needs to be renamed/repurposed as `TestMessagesIncludeCli`, because what it currently asserts ("`extract_commands` is NOT called") becomes the **default** after the flip. The new test must assert the inverse — that `--include-cli` is the flag that triggers `extract_commands`.
- `scripts/tests/test_user_messages.py:2204-2232` — `test_skip_cli_default` becomes tautological (default `True`); parallel `test_include_cli_default` / `test_include_cli_flag` must be added. `test_skip_cli_flag` (passing `--skip-cli` explicitly to set `True`) becomes redundant after the flip.
- `scripts/tests/test_user_messages.py:2248` — composite parser test (`args.skip_cli is True` after the flip is now the default, not a flag assertion); needs parallel coverage for `--include-cli`.
- `scripts/tests/test_cli.py:696` — `test_main_messages_default_args` does not currently lock in the merged-stream default (only mocks `extract_user_messages`); it remains correct after the flip. Add a regression assertion that `extract_commands` is **not** called under the default argv, mirroring the new `TestMessagesIncludeCli` shape.
- `scripts/tests/test_cli.py:1922` — `test_empty_messages_returns_zero` (mocks `extract_user_messages -> []`, asserts `result == 0`): after the flip, `extract_commands` is no longer called by default; this test still passes but the `mock_cmds.assert_not_called()` invariant should be added as a regression assertion.
- `CHANGELOG.md` — add an entry under the next concrete release header (per `.claude/CLAUDE.md` policy: no `[Unreleased]`; latest concrete header is `## [1.163.0] - 2026-09-11` at `CHANGELOG.md:8`, next release will be assigned by `ll-manage-release`).

### Dependent Files (Callers/Importers) — consumers affected by the breaking change

- `scripts/little_loops/loops/lib/cli.yaml:93` — `ll_messages` fragment runs `ll-messages --stdout` with no skip/commands flag. Today's emitted stream includes commands; after the flip it emits user messages only. The fragment's description (lines 87-91: "Extract user messages from session logs") already matches the new default; no edit needed, but the behavioral change applies.
- `scripts/little_loops/loops/examples-miner.yaml:38` — `harvest` action calls `ll-messages --skill ... --examples-format ... --stdout`. The `--examples-format` branch at `scripts/little_loops/cli/messages.py:234-249` only consumes `messages` (calls `build_examples(messages, ...)` at line 238), but it still passes through the line 209 guard for `extract_commands`. **After the flip, the harvested corpus shrinks — command-derived examples no longer appear in the output.** This is the most impactful internal-consumer change.
- `scripts/little_loops/loops/sft-corpus.yaml:41-53` — `stage` action calls `ll-messages --sft-format ${context.sft_format}`. The `--sft-format` branch at `scripts/little_loops/cli/messages.py:252-275` only calls `extract_conversation_turns`; `extract_commands` is not consumed there. **Not affected.**
- `skills/ll-loop-suggester/SKILL.md:31` and `:49` — bare `ll-messages --include-response-context -n 200 --stdout` invocations. Affected: today's output includes commands; after flip, user-only. The skill's purpose (loop suggestion from user prompts) is unchanged; may want to add `--include-cli` if downstream analysis benefits.
- `commands/loop-suggester.md` and the host mirrors `.qwen/commands/ll/loop-suggester.md:17/35`, `.kimi-code/skills/ll-loop-suggester/SKILL.md:31/49`, `.gemini/commands/loop-suggester.toml:16/34` — same `ll-messages --include-response-context -n 200 --stdout` invocation; same flip-affected behavior. These are mirrors of the same skill; updating the source skill updates all.
- `docs/generalized-fsm-loop.md:2153` and `:2163` — `ll-messages --include-response-context -n 200 -o messages.jsonl` (skill description); affected.
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:10`, `:85`, `:88`, `:91`, `:94`, `:97`, `:100`, `:228-229`, `:374`, `:384`, `:407`, `:419`, `:423` — bare `ll-messages` invocations in the guide; narrative at line 81 ("extract user messages") already matches the new default.
- `docs/guides/EXAMPLES_MINING_GUIDE.md:113`, `:142`, `:146`, `:355`, `:405`, `:421`, `:443`, `:461`, `:467`, `:574`, `:588` — references to `ll-messages --skill ... --examples-format ... --stdout`; affected (corpus shrinks to user-only).
- `scripts/little_loops/init/writers.py:157` — `"Bash(ll-messages:*)"` allowed-tools entry; not an invocation.
- `agents/`, `hooks/` — no `ll-messages` invocations found.

### Conventions in Force (none yet established for this kind of change)

- The repository has **no existing precedent** in `scripts/little_loops/cli/` for a CLI that flips a default flag and adds an `--include-*` mirror flag as a paired breaking change. All existing `--include-*` flags (`--include-response-context` at `scripts/little_loops/cli/messages.py:104-108`, `--include-messages` at `scripts/little_loops/cli/session.py:296-302`, `--include-summary` / `--include-completed` / `--include-orphans` / `--include-blocked` under `scripts/little_loops/cli/issues/__init__.py:265-271`, `:370-376`, `:504-507`, `:670-672`) are independent opt-ins whose base default (`False`) has been the default since introduction. **This change establishes the new convention** — there is no earlier rule to cite.
- The closest semantic sibling is `--include-response-context` at `scripts/little_loops/cli/messages.py:104-108`: same CLI, same `--help` shape (`action="store_true"`, default `False`), same module-level location. The new `--include-cli` should follow the same argparse entry shape as evidence for "opt-in flags on this CLI are formatted this way."

### Tests (additions)

- `scripts/tests/test_cli_messages.py` — see Files to Modify above (rename `TestMessagesSkipCli` → `TestMessagesIncludeCli`; the new class asserts the inverse of what the old one did).
- `scripts/tests/test_user_messages.py` — see Files to Modify above (parser unit tests at `:2204-2232` and `:2248`).
- `scripts/tests/test_cli.py` — add regression assertion at `:696` (`test_main_messages_default_args`) and `:1922` (`test_empty_messages_returns_zero`) that `extract_commands` is NOT called under the default argv.

### Documentation (additions)

- `docs/reference/CLI.md:3663` — `### ll-messages` section heading (existing).
- `docs/reference/CLI.md:3690-3705` — example block (update: replace `--skip-cli` example with `--include-cli`; add `ll-messages --include-cli` example; update the description above the block to state "defaults to user messages only").
- `docs/reference/API.md:4892` — `main_messages` entry-point quote (sourced from `scripts/little_loops/cli/messages.py:14-21`); docstring update propagates here.
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:413` — section heading `"Filter messages by type (--skip-cli / --commands-only)"`; reword to reflect new default (e.g. "Filter messages by type (--include-cli / --commands-only)").
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:419` and `:423` — flag examples; the `--skip-cli` line becomes the default and should be reworded; add `--include-cli` line.
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:85-100` — `## Prerequisites: Extracting Messages (ll-messages)` block; bare `ll-messages` example now emits user-only (matches the narrative); no prose change strictly required, but consider adding a one-line note.

### Behavior Parity

| Artifact | Today (pre-flip) | Post-flip | Disposition |
|---|---|---|---|
| `ll-messages` (no flags) | `{user + commands}` merged stream | `{user}` only | **CHANGED** — primary fix; mirror via `--include-cli` |
| `ll-messages --skip-cli` | `{user}` only | `{user}` only (default now; flag redundant) | **PRESERVED** (behavior unchanged; flag becomes default) |
| `ll-messages --include-cli` | (does not exist) | `{user + commands}` merged stream | **CHANGED** — new mirror flag restoring pre-flip default |
| `ll-messages --commands-only` | `{commands}` only | `{commands}` only | **PRESERVED** — unchanged |
| `ll-messages --skip-cli --commands-only` | `{commands}` only (OR short-circuit at line 209) | `{commands}` only (the new `args.include_cli` would be `False`, so this path drops to the no-commands case if `--include-cli` is not also passed — note the literal guard `if args.include_cli or args.commands_only:` will still resolve `True` for `--commands-only`) | **PRESERVED** — verified by guard semantics |
| `extract_user_messages` (`scripts/little_loops/user_messages.py:717`) | returns user-message records | unchanged signature/behavior; docstring updated | **PRESERVED** |
| `extract_commands` (`scripts/little_loops/user_messages.py:889`) | returns command records | unchanged signature/behavior; docstring updated | **PRESERVED** |
| `_save_combined` (`scripts/little_loops/cli/messages.py:302`) | writes JSONL | unchanged signature/behavior | **PRESERVED** |
| `_SFTItem.to_dict` (`scripts/little_loops/cli/messages.py:332`) | emits the SFT shape | unchanged | **PRESERVED** |
| `CommandRecord.to_dict` (`scripts/little_loops/user_messages.py:145`) | `"type": "command"` discriminator | unchanged | **PRESERVED** |

## Implementation Steps

1. Flip `--skip-cli` default to `True` and add `--include-cli` (default `False`) in `main_messages`; invert the CLI-commands branch guard so the new opt-in is the trigger.
2. Update argparse `help=` strings and epilog examples so the documented happy path reflects the new default.
3. Update docstrings on `extract_user_messages` and `extract_commands` in `scripts/little_loops/user_messages.py`.
4. Update `docs/reference/CLI.md` and `docs/reference/API.md` to flag the default flip.
5. Adjust any test asserting default output includes CLI commands; add a regression test asserting the default emits user messages only and that `--include-cli` restores the merged stream.
6. Add a changelog entry under a concrete release header.
8. Verify with `python -m pytest scripts/tests/` and a manual `ll-messages -n 5 --stdout | pbcopy` smoke test confirming only user prompts land on the clipboard.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- **Outcome 1 (parse_args contract preserved):** `main_messages()` accepts `--skip-cli`, `--include-cli`, and `--commands-only`; post-flip defaults are `skip_cli=True`, `include_cli=False`, `commands_only=False`. The argparse entry shape mirrors `--include-response-context` at `scripts/little_loops/cli/messages.py:104-108` (same module, same action/default convention). Verified by `python -m pytest scripts/tests/test_user_messages.py::TestArgs -v` (the parser unit tests at `:2204-2232` and `:2248` are the contract test surface).
- **Outcome 2 (decision-logic invariant):** the line 209 guard inverts from `if not args.skip_cli or args.commands_only:` to `if args.include_cli or args.commands_only:`. Verified by `python -m pytest scripts/tests/test_cli_messages.py -v` (`TestMessagesCommandsOnly` at `:118` and `TestMessagesIncludeCli` (renamed from `TestMessagesSkipCli` at `:172`) are the contract test surface).
- **Outcome 3 (call-site default behavior):** `main_messages(["ll-messages"])` invokes `extract_user_messages(...)` only; `extract_commands(...)` is not called. Verified by adding `mock_cmds.assert_not_called()` to `test_main_messages_default_args` at `scripts/tests/test_cli.py:696` and `test_empty_messages_returns_zero` at `:1922`.
- **Outcome 4 (documentation parity):** `docs/reference/CLI.md:3690-3705` example block reflects the new default and demonstrates `--include-cli`; `docs/reference/API.md:4892` propagates the docstring update from `scripts/little_loops/cli/messages.py:14-21`; `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:413/419/423` rewords the `--skip-cli / --commands-only` heading to use `--include-cli / --commands-only`. Verified by `grep -rn "skip-cli\|include-cli" docs/` and visual inspection.
- **Outcome 5 (consumer transparency):** the affected internal consumers (`scripts/little_loops/loops/examples-miner.yaml:38`, `skills/ll-loop-suggester/SKILL.md:31/49` and host mirrors) are aware that the harvested/analyzed stream is now user-only; the implementer may either accept the change (corpus shrinks for `--examples-format`, output is user-only for `--include-response-context`) or pass `--include-cli` to restore the prior behavior. This is a judgment call — `examples-miner` may want `--include-cli` added (the loop description suggests it harvests command examples too); the loop-suggester skill is fine without it.
- **Outcome 6 (changelog entry under concrete release header):** an entry is added to `CHANGELOG.md` under the next concrete `## [X.Y.Z] - DATE` header (assigned by `ll-manage-release` during release prep; current latest is `## [1.163.0] - 2026-09-11` at `CHANGELOG.md:8`). Per `.claude/CLAUDE.md` policy: no `[Unreleased]`. Format matches existing entries: `**ENH-3457**: <description>` under a `### Changed` subsection (breaking change) or `### Added` (for the new `--include-cli` flag).
- **Outcome 7 (suite passes):** `python -m pytest scripts/tests/` exits 0 with the new defaults.
- **Outcome 8 (manual smoke test):** `ll-messages -n 5 --stdout | pbcopy` lands only user prompts on the clipboard (confirmed by paste into a JSON-agnostic editor).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

### Signatures (concrete anchors from analyzer)

- `main_messages() -> int` — `scripts/little_loops/cli/messages.py:14`. Entry point. Three args change: `skip_cli` default flips from `False` to `True`; new `include_cli` (default `False`); `commands_only` unchanged.
- `extract_user_messages(handles, limit=None, since=None, include_agent_sessions=True, include_response_context=False) -> list[UserMessage]` — `scripts/little_loops/user_messages.py:717`. Default behavior: returns user messages from all `handles`, dispatching per host (`_CLAUDE_SHAPED_HOSTS` at line 692; `codex` and `kimi-code` short-circuits at lines 751-757). Unchanged by this issue; docstring updated.
- `extract_commands(handles, limit=None, since=None, include_agent_sessions=True, tools=["Bash"]) -> list[CommandRecord]` — `scripts/little_loops/user_messages.py:889`. Default behavior: parses assistant `tool_use` blocks for the named tools (default `["Bash"]`) and emits one `CommandRecord` per match. Unchanged; docstring updated.
- `_save_combined(items, output_path=None) -> Path` — `scripts/little_loops/cli/messages.py:302`. Writes one JSON object per line. Unchanged.
- `_SFTItem.to_dict(self) -> dict` — `scripts/little_loops/cli/messages.py:332`. Unchanged.

### Call Path (literal, from analyzer)

```
argparse.parse_args(argv)  # scripts/little_loops/cli/messages.py:109-118 (post-flip)
  ├─ args.skip_cli      = (True by default; True if --skip-cli passed)
  ├─ args.include_cli   = (False by default; True if --include-cli passed)
  └─ args.commands_only = (False by default; True if --commands-only passed)

if not args.commands_only:                                        # line 200
    messages = extract_user_messages(...)                         # line 201
if args.include_cli or args.commands_only:                        # line 209 (post-flip; was `if not args.skip_cli or args.commands_only:`)
    commands = extract_commands(...)                              # line 210

# Merge + sort + output (UNCHANGED, lines 277-297)
combined = messages + commands; combined.sort(key=timestamp, reverse=True)
if args.limit: combined = combined[:args.limit]
stdout: print(json.dumps(r.to_dict())) for r in combined
else: output_path = _save_combined(combined, args.output)
```

### Decision Rules

- **`--skip-cli` default flips to `True`; `--include-cli` is the explicit opt-in for the merged stream.** The new guard at line 209 reads `if args.include_cli or args.commands_only:` — equivalent in result to today's `if not args.skip_cli or args.commands_only:` after the default flip, but expressed positively to match the `--include-*` opt-in shape used elsewhere on this CLI (e.g. `--include-response-context` at line 104-108).
- **`--commands-only` retains its semantics:** `extract_user_messages` is gated off (line 200 unchanged), `extract_commands` runs. The literal `or args.commands_only:` clause on line 209 short-circuits the include-cli check, so `--commands-only` works regardless of `--include-cli`.
- **`--skip-cli` becomes redundant with the new default** but is retained for backward compatibility on the CLI surface (no removal; just default change). The argparse help should say "Deprecated; default behavior. Use `--include-cli` to restore the merged stream." or similar — the implementer's call on the exact wording.

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
- `/ll:refine-issue:gap-analysis` - 2026-09-12T05:32:50 - `8cba1b7b-b038-42bd-b3ac-4fa2936a6614.jsonl`
- `/ll:format-issue` - 2026-09-12T03:46:55 - `d4cc78b3-7b01-4dfe-9c49-d8730730c0cd.jsonl`
- `/ll:capture-issue` - 2026-09-12T03:43:54 - `9c967725-d34b-4768-bd95-ced00b928d94.jsonl`