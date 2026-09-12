---
id: ENH-3457
type: ENH
title: ll-messages defaults to user messages only
priority: P2
status: open
verify_verdict: VALID
discovered_by: ll-issues-create
discovered_date: '2026-09-12'
captured_at: '2026-09-12T03:43:46Z'
confidence_score: 95
outcome_confidence: 86
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 19
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

Make user-only the default and introduce a new `--include-cli` flag as the explicit opt-in to the merged-stream behavior. `--skip-cli` stays on the CLI surface as a deprecated no-op (its `store_true` default is left at `False`; flipping a `store_true` default to `True` would make the flag unsettable and the new guard never reads it anyway). Concretely:

- In `scripts/little_loops/cli/messages.py` (`main_messages`), add `--include-cli` (action=`store_true`, default=`False`) and rewrite the existing `if not args.skip_cli or args.commands_only:` guard as `if args.include_cli or args.commands_only:`. Put `--skip-cli` and `--include-cli` in an argparse mutually exclusive group so the contradictory pair errors instead of silently picking one.
- Update the argparse `help=` strings (`--skip-cli`: "Deprecated no-op; user-only is now the default. Use --include-cli to merge in assistant commands.") and epilog examples (`%(prog)s --skip-cli` → `%(prog)s --include-cli`) so the documented happy path matches the new default.
- Update docstrings on `extract_user_messages` and `extract_commands` in `scripts/little_loops/user_messages.py` to note that the CLI surface defaults to user-only.
- Update `docs/reference/CLI.md` (the `ll-messages` section) and any cross-references in `docs/reference/API.md` to flag the default flip.
- Changelog: no per-issue entry. Release notes are generated at release time (`docs(release): add changelog for vX.Y.Z` commits); the `Breaking Change: Yes` line below is what `ll-manage-release` picks up.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — add `--include-cli` (mutually exclusive with the now-deprecated `--skip-cli`), rewrite the CLI-commands branch guard to key on `include_cli`, update argparse `help=`/epilog, update the `%(prog)s --skip-cli` example to `%(prog)s --include-cli`.
- `scripts/little_loops/user_messages.py` — update docstrings on `extract_user_messages` / `extract_commands` to mention the CLI surface flag default.
- `docs/reference/CLI.md` — update the `ll-messages` reference section.
- `docs/reference/API.md` — flag the default flip in any section referencing `extract_user_messages` / `extract_commands`.

### Dependent Files (Callers/Importers)
- Any project-local script or test that invokes `main_messages()` and asserts on the default output stream — search with `grep -rn "main_messages\|ll-messages" scripts/`.
- Any consumer that shells out to `ll-messages` without flags and relies on the merged stream — N/A inside this repo but documented as a breaking change.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:77, :138` — re-exports `main_messages` and lists in `__all__`; signature unchanged, no edit required [Agent 1 finding].
- `scripts/little_loops/init/writers.py:157, :223, :283` — `ll-init` writes `Bash(ll-messages:*)` allowlist + tool-catalog descriptions ("Extract user messages from Claude Code logs") into settings.json/CLAUDE.md/AGENTS.md/GEMINI.md; descriptions already match new default [Agent 1 finding].
- `scripts/little_loops/workflow_sequence/__init__.py:92, :171, :211` — docstring/help/logger references to `ll-messages`; describes the default extraction path, consistent with new default [Agent 1 finding].
- `scripts/little_loops/sft_formatter.py:1` — module docstring `"""SFT training format converters for ll-messages --sft-format output."""`; unaffected by flag flip [Agent 1 finding].

### Similar Patterns
- No existing CLI in `scripts/little_loops/cli/` flips a default flag with an `--include-*` mirror; the `--commands-only` / `--skip-cli` pair is the closest analog (mutually exclusive modes selected by flag).

### Tests
- `scripts/tests/` — adjust any test that asserts the default output includes CLI commands. Likely candidates under `scripts/tests/test_messages*.py` or `scripts/tests/cli/test_messages*.py` (verify via `grep -rln "skip_cli\|include_cli\|commands_only" scripts/tests/`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_messages_save.py:11` — `from little_loops.cli.messages import _save_combined`; confirmed invariant to the flag flip (pure unit test of the helper, no argparse coupling) [Agent 3 finding].
- `scripts/tests/test_init_core.py:1838, :1997` — `for tool in ("ll-auto", "ll-loop", "ll-issues", "ll-logs", "ll-messages"):` asserts `ll-messages` string appears in CLAUDE.md/GEMINI.md install lines; tool name unchanged, unaffected [Agent 1 finding].

### Documentation
- `docs/reference/CLI.md` — `ll-messages` reference section.
- `docs/reference/API.md` — cross-references on `extract_user_messages` / `extract_commands`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:3212, :3578` — `ll_messages` fragment table row quotes `ll-messages --stdout` verbatim; narrative ("Extract user messages from session logs") already consistent with new default [Agent 2 finding].
- `docs/reference/loops.md:427, :476, :491` — sft-corpus state graph + artifacts table + CLI tool callout referencing `ll-messages --sft-format` and `--reader db`; unaffected (the `--sft-format` branch at `messages.py:252-275` calls `extract_conversation_turns` and never reads `commands`) [Agent 2 finding].
- `docs/reference/COMMANDS.md:738-741` — `loop-suggester` Arguments block: "Path to ll-messages JSONL file (runs extraction if omitted)"; the run-on-omission now emits user-only, consistent with the new default [Agent 2 finding].
- `docs/reference/CLI.md:3513-3537` — workflow-sequence analyzer section referencing `ll-messages --output .ll/workflow-analysis/step1-patterns.jsonl`; path-default behavior consistent with new default [Agent 2 finding].
- `docs/reference/API.md:8968, :12050` — module-level doc paragraphs referencing `ll-messages --sft-format`; unaffected [Agent 2 finding].
- `docs/development/USER_GUIDE_AUDIT_REPORT.md:51, :117, :129, :171, :207` — historical audit-report rows enumerating `ll-messages` flag coverage against `--help` output; flag-parity check must be re-run after flip. Advisory only — these are historical audit snapshots, not live docs [Agent 2 finding].

### Configuration
- N/A

### Codebase Research Findings

### Files to Modify (additions)

- `scripts/little_loops/cli/messages.py` — three concrete edits (from `codebase-analyzer`, anchored):
  - **Line 47** (epilog): update `%(prog)s --skip-cli` example to `%(prog)s --include-cli`.
  - **Line 109-113**: keep `--skip-cli` as `store_true` / default `False` (do NOT flip the default — a `store_true` flag with default `True` can never be unset, and the new guard does not read it). Update its `help=` text from `"Exclude CLI commands from output (included by default)"` to a deprecation note ("Deprecated no-op; user-only is the default. Use --include-cli to merge in assistant commands.").
  - **Line 114-118**: leave `--commands-only` as-is.
  - **Add** `--include-cli` argparse entry (action=`store_true`, default `False`, help mentioning the merged-stream opt-in) in a `parser.add_mutually_exclusive_group()` together with `--skip-cli`, so `--skip-cli --include-cli` is a parse error.
  - **Line 200**: leave `if not args.commands_only:` as-is — it gates `extract_user_messages`, not commands.
  - **Line 209**: invert the guard `if not args.skip_cli or args.commands_only:` to `if args.include_cli or args.commands_only:` (literal substitution; no other call site).
  - **Lines 14-21** (`main_messages` docstring): note "defaults to user messages only; pass `--include-cli` to merge in assistant bash commands."
- `scripts/little_loops/user_messages.py` — docstring updates at `:723-743` (`extract_user_messages`) and `:896-911` (`extract_commands`) noting that the CLI surface flag defaults to user-only.
- `scripts/tests/test_cli_messages.py:118` — `TestMessagesCommandsOnly` (no change to behavior tests, but the class name/header comment about "excludes user" still holds).
- `scripts/tests/test_cli_messages.py:172` — `TestMessagesSkipCli` class needs to be renamed/repurposed as `TestMessagesIncludeCli`, because what it currently asserts ("`extract_commands` is NOT called") becomes the **default** after the flip. The new test must assert the inverse — that `--include-cli` is the flag that triggers `extract_commands`. Keep one case asserting `--skip-cli` still parses and still yields user-only (deprecated no-op), and add a case asserting `--skip-cli --include-cli` exits with an argparse error (mutually exclusive group). **This file is the real contract surface** — it drives `main_messages()` through the production parser.
- `scripts/tests/test_user_messages.py:2195-2232` — `_parse_messages_args` is a **hand-copied replica** of the production parser, not the CLI itself; tests here only check the replica. Update it for parity (add `--include-cli`, keep `--skip-cli` default `False`) and add `test_include_cli_default` / `test_include_cli_flag`, but do not treat this class as proof the CLI behaves correctly.
- `scripts/tests/test_user_messages.py:2248` — composite parser test on the replica; `args.skip_cli is True` after passing `--skip-cli` remains valid (flag still parses); add parallel coverage for `--include-cli`.
- `scripts/tests/test_cli.py:696` — `test_main_messages_default_args` does not currently lock in the merged-stream default (only mocks `extract_user_messages`); it remains correct after the flip. Add a regression assertion that `extract_commands` is **not** called under the default argv, mirroring the new `TestMessagesIncludeCli` shape.
- `scripts/tests/test_cli.py:1922` — `test_empty_messages_returns_zero` (mocks `extract_user_messages -> []`, asserts `result == 0`): after the flip, `extract_commands` is no longer called by default; this test still passes but the `mock_cmds.assert_not_called()` invariant should be added as a regression assertion.
- `CHANGELOG.md` — **no edit.** Changelog sections are written at release time by the `docs(release): add changelog for vX.Y.Z` commits (`git log -- CHANGELOG.md`); per-issue entries are not the convention here.

### Dependent Files (Callers/Importers) — consumers affected by the breaking change

- `scripts/little_loops/loops/lib/cli.yaml:93` — `ll_messages` fragment runs `ll-messages --stdout` with no skip/commands flag. Today's emitted stream includes commands; after the flip it emits user messages only. The fragment's description (lines 87-91: "Extract user messages from session logs") already matches the new default; no edit needed, but the behavioral change applies.
- `scripts/little_loops/loops/examples-miner.yaml:38` — `harvest` action calls `ll-messages --skill ... --examples-format ... --stdout`. The `--examples-format` branch at `scripts/little_loops/cli/messages.py:234-249` only consumes `messages` (calls `build_examples(messages, ...)` at line 238); `commands` is extracted today but never enters the output. **Not affected** — the harvested corpus is identical before and after the flip; the only change is that the wasted `extract_commands` pass is skipped. Do not add `--include-cli` here.
- `scripts/little_loops/loops/sft-corpus.yaml:41-53` — `stage` action calls `ll-messages --sft-format ${context.sft_format}`. The `--sft-format` branch at `scripts/little_loops/cli/messages.py:252-275` only calls `extract_conversation_turns`; `extract_commands` is not consumed there. **Not affected.**
- `skills/ll-loop-suggester/SKILL.md:31` and `:49` — bare `ll-messages --include-response-context -n 200 --stdout` invocations. Affected: today's output includes commands; after flip, user-only. The skill's purpose (loop suggestion from user prompts) is unchanged; leave as-is.
- `commands/loop-suggester.md` and the host mirrors `.qwen/commands/ll/loop-suggester.md:17/35`, `.kimi-code/skills/ll-loop-suggester/SKILL.md:31/49`, `.gemini/commands/loop-suggester.toml:16/34` — same `ll-messages --include-response-context -n 200 --stdout` invocation; same flip-affected behavior. These are mirrors of the same skill; updating the source skill updates all (and any skill edit trips the mirror gate — regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply`).
- `docs/generalized-fsm-loop.md:2153` and `:2163` — `ll-messages --include-response-context -n 200 -o messages.jsonl` (skill description); affected.
- **`/ll:analyze-workflows` pipeline — REAL behavior change.** `agents/workflow-pattern-analyzer.md:76-95` classifies records with `"type": "command"` as the `cli_command` category ("raw CLI/shell command execution"). The pipeline's documented input is a bare `ll-messages` run (`docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:85-100`), so after the flip that category goes empty silently. Fix in this issue: change the guide's pipeline invocations to `ll-messages --include-cli` (lines `:10`, `:85`, `:88`, `:91`, `:94`, `:97`, `:100`, `:228-229`, `:374`, `:384`, `:407`) and add a one-line note under the Prerequisites block that `--include-cli` is required for `cli_command` classification. `commands/analyze-workflows.md` should get the same flag in any `ll-messages` invocation it documents.
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
| `ll-messages --skip-cli` | `{user}` only | `{user}` only (deprecated no-op; flag still parses) | **PRESERVED** (behavior unchanged; flag becomes a no-op) |
| `ll-messages --include-cli` | (does not exist) | `{user + commands}` merged stream | **CHANGED** — new mirror flag restoring pre-flip default |
| `ll-messages --skip-cli --include-cli` | (n/a) | argparse error (mutually exclusive group) | **CHANGED** — new, deliberate |
| `ll-messages --commands-only` | `{commands}` only | `{commands}` only | **PRESERVED** — unchanged |
| `ll-messages --skip-cli --commands-only` | `{commands}` only (OR short-circuit at line 209) | `{commands}` only (`or args.commands_only` still short-circuits the guard) | **PRESERVED** — verified by guard semantics |
| `ll-messages --skill X --examples-format` (examples-miner) | examples from `messages` only | identical output; skips the unused `extract_commands` pass | **PRESERVED** |
| bare `ll-messages` feeding `/ll:analyze-workflows` | `cli_command` category populated | `cli_command` category empty unless `--include-cli` | **CHANGED** — guide/command docs updated to pass `--include-cli` |
| `extract_user_messages` (`scripts/little_loops/user_messages.py:717`) | returns user-message records | unchanged signature/behavior; docstring updated | **PRESERVED** |
| `extract_commands` (`scripts/little_loops/user_messages.py:889`) | returns command records | unchanged signature/behavior; docstring updated | **PRESERVED** |
| `_save_combined` (`scripts/little_loops/cli/messages.py:302`) | writes JSONL | unchanged signature/behavior | **PRESERVED** |
| `_SFTItem.to_dict` (`scripts/little_loops/cli/messages.py:332`) | emits the SFT shape | unchanged | **PRESERVED** |
| `CommandRecord.to_dict` (`scripts/little_loops/user_messages.py:145`) | `"type": "command"` discriminator | unchanged | **PRESERVED** |

## Implementation Steps

1. Add `--include-cli` (default `False`) in `main_messages`, mutually exclusive with the now-deprecated no-op `--skip-cli` (default stays `False`); rewrite the CLI-commands branch guard as `if args.include_cli or args.commands_only:`.
2. Update argparse `help=` strings (deprecation note on `--skip-cli`) and epilog examples so the documented happy path reflects the new default.
3. Update docstrings on `extract_user_messages` and `extract_commands` in `scripts/little_loops/user_messages.py`.
4. Update `docs/reference/CLI.md` and `docs/reference/API.md` to flag the default flip; switch the `/ll:analyze-workflows` pipeline invocations in `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` and `commands/analyze-workflows.md` to `ll-messages --include-cli` (the pattern analyzer's `cli_command` category depends on command records).
5. Adjust any test asserting default output includes CLI commands; add regression tests in `scripts/tests/test_cli_messages.py` asserting the default emits user messages only, `--include-cli` restores the merged stream, `--skip-cli` still parses as a no-op, and `--skip-cli --include-cli` is a parse error. Update the replica parser in `scripts/tests/test_user_messages.py` for parity.
6. Verify with `python -m pytest scripts/tests/` and a manual `ll-messages -n 5 --stdout | pbcopy` smoke test confirming only user prompts land on the clipboard.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- **Outcome 1 (parse_args contract preserved):** `main_messages()` accepts `--skip-cli` (deprecated no-op), `--include-cli`, and `--commands-only`; post-flip defaults are `skip_cli=False`, `include_cli=False`, `commands_only=False`; `--skip-cli --include-cli` is a parse error. The argparse entry shape mirrors `--include-response-context` at `scripts/little_loops/cli/messages.py:104-108` (same module, same action/default convention). Verified by `python -m pytest scripts/tests/test_cli_messages.py -v` (drives the production parser). The parser unit tests at `scripts/tests/test_user_messages.py:2204-2232` and `:2248` exercise a hand-copied replica, not the CLI — update them for parity only.
- **Outcome 2 (decision-logic invariant):** the line 209 guard inverts from `if not args.skip_cli or args.commands_only:` to `if args.include_cli or args.commands_only:`. Verified by `python -m pytest scripts/tests/test_cli_messages.py -v` (`TestMessagesCommandsOnly` at `:118` and `TestMessagesIncludeCli` (renamed from `TestMessagesSkipCli` at `:172`) are the contract test surface).
- **Outcome 3 (call-site default behavior):** `main_messages(["ll-messages"])` invokes `extract_user_messages(...)` only; `extract_commands(...)` is not called. Verified by adding `mock_cmds.assert_not_called()` to `test_main_messages_default_args` at `scripts/tests/test_cli.py:696` and `test_empty_messages_returns_zero` at `:1922`.
- **Outcome 4 (documentation parity):** `docs/reference/CLI.md:3690-3705` example block reflects the new default and demonstrates `--include-cli`; `docs/reference/API.md:4892` propagates the docstring update from `scripts/little_loops/cli/messages.py:14-21`; `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:413/419/423` rewords the `--skip-cli / --commands-only` heading to use `--include-cli / --commands-only`. Verified by `grep -rn "skip-cli\|include-cli" docs/` and visual inspection.
- **Outcome 5 (consumer transparency):** `examples-miner.yaml:38` is unaffected (the `--examples-format` branch never reads `commands`); `skills/ll-loop-suggester/SKILL.md:31/49` and mirrors emit user-only, which matches the skill's purpose — leave both alone. The one consumer that loses data is `/ll:analyze-workflows` (`agents/workflow-pattern-analyzer.md:76-95` classifies `"type": "command"` records as `cli_command`); its documented invocations in `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` and `commands/analyze-workflows.md` are switched to `ll-messages --include-cli` in this issue.
- **Outcome 6 (suite passes):** `python -m pytest scripts/tests/` exits 0 with the new defaults.
- **Outcome 7 (manual smoke test):** `ll-messages -n 5 --stdout | pbcopy` lands only user prompts on the clipboard (confirmed by paste into a JSON-agnostic editor).

## Impact

- **Priority**: P2 - Quality-of-life default that affects every `ll-messages` user on the clipboard workflow; not blocking, but high-frequency surprise surface.
- **Effort**: Small - One argparse flip, one new flag, docstring/help/doc updates, one test adjustment.
- **Risk**: Medium - Documented breaking change for any user/script relying on today's default merged stream; mitigated by `--include-cli` mirror flag and prominent changelog note.
- **Breaking Change**: Yes - Default output stream changes from `{user + commands}` to `{user only}`.

## Program Design

### Types

- `Args` (argparse namespace in `main_messages`): `skip_cli: bool` (default `False`, deprecated no-op, mutually exclusive with `include_cli`), `include_cli: bool` (default `False`, new), `commands_only: bool` (unchanged).

### Signatures

- `main_messages() -> int` — entry point; flipped default + new flag.
- `extract_user_messages(db: SessionDB, limit: int) -> list[UserMessage]` — unchanged behavior; docstring updated.
- `extract_commands(db: SessionDB, limit: int, tools: list[str]) -> list[CommandRecord]` — unchanged behavior; docstring updated.
- `CommandRecord.to_dict() -> dict` — unchanged; `"type": "command"` discriminator stays for JSONL consumers that parse it.

### Call Path

`main_messages()` → `argparse.parse_args()` (defaults: `skip_cli=False`, `include_cli=False`, `commands_only=False`) → `if not args.commands_only:` branch → `extract_user_messages(...)` → `if args.include_cli or args.commands_only:` branch → `extract_commands(...)` → `_save_combined(...)` JSONL emit.

### Codebase Research Findings

### Signatures (concrete anchors from analyzer)

- `main_messages() -> int` — `scripts/little_loops/cli/messages.py:14`. Entry point. Arg changes: new `include_cli` (default `False`); `skip_cli` keeps default `False` but is no longer read (deprecated no-op, mutually exclusive with `include_cli`); `commands_only` unchanged.
- `extract_user_messages(handles, limit=None, since=None, include_agent_sessions=True, include_response_context=False) -> list[UserMessage]` — `scripts/little_loops/user_messages.py:717`. Default behavior: returns user messages from all `handles`, dispatching per host (`_CLAUDE_SHAPED_HOSTS` at line 692; `codex` and `kimi-code` short-circuits at lines 751-757). Unchanged by this issue; docstring updated.
- `extract_commands(handles, limit=None, since=None, include_agent_sessions=True, tools=["Bash"]) -> list[CommandRecord]` — `scripts/little_loops/user_messages.py:889`. Default behavior: parses assistant `tool_use` blocks for the named tools (default `["Bash"]`) and emits one `CommandRecord` per match. Unchanged; docstring updated.
- `_save_combined(items, output_path=None) -> Path` — `scripts/little_loops/cli/messages.py:302`. Writes one JSON object per line. Unchanged.
- `_SFTItem.to_dict(self) -> dict` — `scripts/little_loops/cli/messages.py:332`. Unchanged.

### Call Path (literal, from analyzer)

```
argparse.parse_args(argv)  # scripts/little_loops/cli/messages.py:109-118 (post-flip)
  ├─ args.skip_cli      = (False by default; True if --skip-cli passed — deprecated, never read)
  ├─ args.include_cli   = (False by default; True if --include-cli passed; exclusive with --skip-cli)
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

- **User-only is the default; `--include-cli` is the explicit opt-in for the merged stream.** The new guard at line 209 reads `if args.include_cli or args.commands_only:` — expressed positively to match the `--include-*` opt-in shape used elsewhere on this CLI (e.g. `--include-response-context` at line 104-108). `args.skip_cli` is no longer read anywhere.
- **`--commands-only` retains its semantics:** `extract_user_messages` is gated off (line 200 unchanged), `extract_commands` runs. The literal `or args.commands_only:` clause on line 209 short-circuits the include-cli check, so `--commands-only` works regardless of `--include-cli`.
- **`--skip-cli` is a deprecated no-op**, retained on the CLI surface for backward compatibility (its `store_true` / default `False` shape is unchanged — do not flip the default, which would make the flag unsettable). It sits in a mutually exclusive group with `--include-cli`. Help text: "Deprecated no-op; user-only is the default. Use --include-cli to merge in assistant commands."

## Scope Boundaries

In scope:

- New `--include-cli` flag (mutually exclusive with the deprecated no-op `--skip-cli`), branch-guard rewrite in `main_messages`.
- Docstring/help/epilog/doc updates for `ll-messages`, including switching the `/ll:analyze-workflows` pipeline docs to `--include-cli`.
- Test adjustments + regression tests covering the new default, the `--include-cli` opt-in, the `--skip-cli` no-op, and the exclusive-group error.

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
- `/ll:confidence-check` - 2026-09-12T05:45:02 - `09c7a8e4-700a-4350-bc8d-28c537752571.jsonl`
- `/ll:wire-issue` - 2026-09-12T05:40:55 - `3d61b218-f593-4f08-a0e1-ad219e9f3ed8.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-12T05:32:50 - `8cba1b7b-b038-42bd-b3ac-4fa2936a6614.jsonl`
- `/ll:format-issue` - 2026-09-12T03:46:55 - `d4cc78b3-7b01-4dfe-9c49-d8730730c0cd.jsonl`
- `/ll:capture-issue` - 2026-09-12T03:43:54 - `9c967725-d34b-4768-bd95-ced00b928d94.jsonl`