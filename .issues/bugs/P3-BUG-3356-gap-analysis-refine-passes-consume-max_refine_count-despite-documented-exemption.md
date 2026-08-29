---
id: BUG-3356
type: BUG
title: gap-analysis refine passes consume max_refine_count despite documented exemption
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T23:26:59Z'
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
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

## Integration Map

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/append_log.py:26` — `cmd_append_log()` calls `append_session_log_entry(issue_path, args.log_command)`; this is the only call site the CLI wraps, but `append_session_log_entry()` itself has three direct callers that would each need the discriminated string threaded through if they ever start writing gap-analysis-style entries:
  - `scripts/little_loops/issue_lifecycle.py:1161` — `complete_issue_lifecycle()`
  - `scripts/little_loops/parallel/orchestrator.py:1832` — `ParallelOrchestrator._complete_issue_lifecycle_if_needed()`
  - `scripts/little_loops/mcp_server/tools.py:468` — `_tool_issue_append_log()` (MCP tool; passes `command` through verbatim, same as the CLI)
- `scripts/little_loops/cli/issues/show.py:242` — `_parse_card_fields()` calls `count_session_commands()`; a display path that reads the same counts `refine_count` derives from.
- `scripts/little_loops/issue_parser.py:3689` — `IssueParser.parse_file()` calls `count_session_commands()` to populate `IssueInfo.session_command_counts`, the field `refine_status.py:339,364` reads to compute `refine_count`.
- `scripts/little_loops/cli/issues/__init__.py:618-624` — registers the `append-log`/`al` subparser; `log_command` is a single required positional with no mode flag today.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/next_action.py:58` — `cmd_next_action()` reads `issue.session_command_counts.get("/ll:refine-issue", 0)` against `refine_cap` to decide whether an issue still `NEEDS_REFINE`; consumes the same undifferentiated count as `refine_count` and has the same gap-analysis-inflation exposure this bug describes. [Agent 1 finding]
- `scripts/little_loops/cli/issues/search.py:279` — `cmd_search()`'s `"refinement"` sort-field key sums `session_command_counts` across a command set that includes `/ll:refine-issue`; an undifferentiated gap-analysis entry inflates this sort score too. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:17` — `--gap-analysis` flag table row states "exempt from `max_refine_count`"; a fourth place (beyond the three named in Expected Behavior) asserting the currently-false exemption claim. [Agent 2 finding]
- `docs/reference/COMMANDS.md:241` — `refine-issue` Arguments prose: "`--gap-analysis` (additive-only gap fill, does not count toward `max_refine_count`)"; same claim, different location. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:436` — `max_refine_count` config table row: "Gap-analysis runs (`--gap-analysis`) are exempt."; same claim in the config reference. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py::test_max_refine_count_exemption_documented` (line 199-202) — pins the exemption claim text in `commands/refine-issue.md` Section 5c; whichever fix option is chosen (implement the discriminator or drop the claim), this test's expectation must be reconciled with the new behavior or it will start asserting a lie (implement) or fail outright (drop). [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Files implicated in the fix, beyond the three already named in Program Design**:
  - `scripts/little_loops/session_log.py` — `_COMMAND_RE` (line 25) and `_TIMESTAMPED_ENTRY_RE` (line 28-30) are the two regexes that turn a raw `## Session Log` entry into a counted/dated command; both must keep matching whatever discriminated string the fix writes.
  - `scripts/little_loops/issues/program_design.py` — `_REFINE_ENTRY` (line 130-132) is a **third**, independent regex over the same entries, used by `issue_design_timestamp()` (line 486-507) to find "the most recent `/ll:refine-issue` entry" for Program Design gate arming/grandfathering. It is not named in this issue's existing Program Design section and must be updated in lockstep with `_COMMAND_RE`/`_TIMESTAMPED_ENTRY_RE` or gap-analysis passes will silently stop refreshing the gate's staleness clock.
  - `scripts/little_loops/issues/research_triage.py` — `REFINE_COMMAND = "/ll:refine-issue"` (line 69) is passed to `last_command_timestamp()` for the Step 3.0 staleness check (per research axis); it consumes the same entry shape and has the same exposure.

- **Regex-format constraint (the load-bearing finding)**: all three regexes above key off the character class `[\w:-]+` inside backticks — `` `(/[\w:-]+)` `` (`session_log.py:25`), `` `(/[\w:-]+)`\s*-\s*(...) `` (`session_log.py:28-30`), and `` `/ll:refine-issue`[^\n]*?(?P<ts>...) `` (`program_design.py:130-132`, which is a literal-string match, not even parameterized). None of these classes include a space. Concretely: appending the literal string this issue's own Expected Behavior proposes as an example — `` `/ll:refine-issue --gap-analysis` `` — does **not** match `_COMMAND_RE` or `_TIMESTAMPED_ENTRY_RE` at all (the closing backtick never follows a `[\w:-]` character once a space is present), so `count_session_commands()`/`parse_session_log()`/`last_command_timestamp()` would silently drop that entry rather than bucket it separately. It also does not match `_REFINE_ENTRY` (an exact-string match on `` `/ll:refine-issue` ``), so `issue_design_timestamp()` would stop treating gap-analysis passes as refine activity for gate-arming purposes. A discriminator built from the same allowed class instead (e.g. a colon or dash suffix — `/ll:refine-issue:gap-analysis` or `/ll:refine-issue-gap`) round-trips through all three regexes unmodified; a space-separated flag suffix does not, at any of the three call sites.

- **`ll-issues append-log` today has no discriminator surface**: `cmd_append_log()` (`scripts/little_loops/cli/issues/append_log.py:13-30`) takes the command string verbatim from a single positional CLI arg, `log_command` (`scripts/little_loops/cli/issues/__init__.py:618-624`), and passes it straight through to `append_session_log_entry()` — there is no `--mode`/`--gap-analysis` flag on the CLI today. The caller (`commands/refine-issue.md` Step 6.5, `ll-issues append-log <path> /ll:refine-issue`) fully controls the string; no CLI schema change is required if the fix is scoped to changing what string gets passed for a `--gap-analysis` run.

- **`refine_status.py` display-layer coupling**: `_CANONICAL_CMD_ORDER` and `_CMD_ALIASES` (`scripts/little_loops/cli/issues/refine_status.py:38-58`) key the human-facing table columns off the exact literal `/ll:refine-issue` string. If the discriminator changes the stored command string, `refine_count` (line 339, 364 — `issue.session_command_counts.get("/ll:refine-issue", 0)`) must filter/aggregate rather than naively re-keying, or a gap-analysis entry becomes an unrecognized column instead of silently folding into (or correctly excluding itself from) the existing `/ll:refine-issue` column.

- **Conventions in Force**: no existing Session Log entry in this codebase carries a flag/mode suffix — every `ll-issues append-log` call site (`commands/*.md`, `skills/*/SKILL.md`) passes a bare `/ll:<command>` string with no arguments. This fix would be the first mode-discriminated entry; there is no established suffix convention to reuse, and the space-separated example in this issue's own Expected Behavior text is the one shape confirmed **not** to work (see regex-format constraint above).

- **Tests that pin current behavior and would need extending**:
  - `scripts/tests/test_session_log.py::TestParseSessionLog`, `TestAppendSessionLogEntry` — exercise `_COMMAND_RE`/`_TIMESTAMPED_ENTRY_RE` against literal `/ll:refine-issue` entries.
  - `scripts/tests/test_refine_status.py::TestRefineStatusJson` — builds fixture issues via a `session_commands=[...]` list (see `_make_issue` helper) and asserts on the resulting `refine_count`; a new gap-analysis-exempt case would extend this fixture shape.
  - `scripts/tests/test_program_design_gate.py`, `scripts/tests/test_research_triage.py` — cover `issue_design_timestamp()`/`_REFINE_ENTRY` and the Step 3.0 staleness check respectively; both need a case proving a gap-analysis-discriminated entry still (or deliberately doesn't) count as refine activity for gate-arming purposes.

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
- `/ll:confidence-check` - 2026-08-29T18:59:15 - `91e591d4-09fb-4f3a-8a30-1b46c4420b97.jsonl`
- `/ll:wire-issue` - 2026-08-29T18:51:10 - `5b08caaf-d6d9-41cd-a302-ae95669f4151.jsonl`
- `/ll:refine-issue` - 2026-08-29T18:45:35 - `237f015b-641f-4613-8e7e-3269af82a4c8.jsonl`
- `/ll:format-issue` - 2026-08-29T18:20:58 - `477f6591-ae32-49d7-bc90-ee1e0759ddc3.jsonl`
