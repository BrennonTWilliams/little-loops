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
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
decision_needed: false
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

> ⚠ Correction (remediation pass): the space-separated example above — `` `/ll:refine-issue --gap-analysis` `` — does **not** satisfy the regex constraint documented under Codebase Research Findings below. None of the three governing regexes (`session_log.py:25`, `session_log.py:28-30`, `program_design.py:130-132`) permit a space before the closing backtick; a space-separated form is silently dropped by `count_session_commands()` rather than counted separately. Any implementation must use a discriminator built from `[\w:-]+` instead — see Program Design → Decision Rules below for the two candidate forms, their exact downstream consequences, and the recommendation.

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
- `scripts/little_loops/cli/issues/search.py:279` — inside `_sort_issues()`'s nested `key()` closure (`_sort_issues` defined at `:232`, `key()` at `:239`; `cmd_search()` itself is defined later, at `:287`, and only calls `_sort_issues()` — the sort-field logic does not live in `cmd_search()`). The `"refinement"` branch (`:271-280`) sums `session_command_counts` across a fixed set that includes `/ll:refine-issue`; an undifferentiated gap-analysis entry inflates this sort score too. [Agent 1 finding; citation corrected during remediation pass — see Codebase Research Findings]

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

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Correction to the "refine_status.py display-layer coupling" finding above (remediation pass)**: direct reads of `refine_status.py:339,364` (`session_command_counts.get("/ll:refine-issue", 0)`), `next_action.py:58` (same `.get("/ll:refine-issue", 0)` pattern), and `search.py:271-279` (`_sort_issues`'s nested `key()`, frozenset-membership sum) show all three are exact-key/exact-membership lookups. None require new filter/aggregate logic once the stored string differs from the literal `/ll:refine-issue` key — each already excludes a differently-keyed entry by construction. The only site that genuinely needs new recognition logic is `program_design.py`'s `_REFINE_ENTRY` (an exact-literal match that must instead keep matching gap-analysis entries), and optionally `refine_status.py`'s human-facing table column derivation (`:39-58`, `:293-306` — cosmetic, does not affect `refine_count`'s JSON value). See Program Design → Decision Rules for the full per-site trace.
- **Test-coverage gap — no existing case covers the two wiring-pass consumer sites**: `scripts/tests/test_next_action.py::test_graduates_after_refine_cap` (~line 228) fixtures five literal `/ll:refine-issue` Session Log entries and pins the exact undifferentiated-count behavior `next_action.py:58` reads; it would need a new case (not just extension) proving a gap-analysis-discriminated entry does not count toward `refine_cap`. `scripts/tests/test_issues_search.py` has **no existing test at all** for the `"refinement"` sort field (confirmed: no `'refinement'`/`"refinement"` string appears anywhere in that file; the `/ll:refine-issue` Session Log fixtures it does contain, at lines ~581 and ~636, feed `TestSearchDateFieldUpdated`'s `"updated"` sort-field tests, not `"refinement"`) — this fix needs a brand-new test in that file, not an extension of one.
- **`recursive-refine.yaml`'s `check_attempt_budget` audited — confirmed unaffected**: `check_attempt_budget` (`scripts/little_loops/loops/recursive-refine.yaml:167-208`) is the second enforcer of `max_refine_count` named in the `config-schema.json` quote in Expected Behavior. It reads a separate per-run counter — `${context.run_dir}/recursive-refine-attempts.txt` — incrementing it once per issue's entry into the `run_refine` sub-loop (line 201), not `session_command_counts`. It is entirely independent of the Session Log entry format this bug's fix changes and needs no code change; `scripts/tests/test_loops_recursive_refine.py` (e.g. `test_exactly_max_refine_count_attempts_then_budget_skip`, `test_budget_line_shows_budget_ids`) exercises this mechanism and should pass unmodified as a regression check.

## Program Design

### Types

N/A — no new data shape; the existing `dict[str, int]` session-command-count mapping keyed by literal command string is reused.

### Signatures

- `count_session_commands(content: str) -> dict[str, int]` — existing (`session_log.py:96`); counts `_COMMAND_RE` matches verbatim, so a `--gap-analysis` run and a normal run both increment the same `/ll:refine-issue` key today.
- `append_session_log_entry(issue_path: Path, command: str, session_jsonl: Path | None = None) -> bool` — existing (`session_log.py:275`); `command` is written into the entry verbatim, so the caller controls what string gets counted.
- `cmd_append_log(config: BRConfig, args: object) -> int` — existing (`cli/issues/append_log.py:13`); passes `args.log_command` through to `append_session_log_entry` unmodified.
- `cmd_next_action(config: BRConfig, args: object) -> int` — existing (`cli/issues/next_action.py`); its `NEEDS_REFINE` check at `:58` reads `issue.session_command_counts.get("/ll:refine-issue", 0)` against `refine_cap` — same exact dict-key lookup as `refine_status.py`'s `refine_count`, so it needs no signature change; a discriminated key is excluded by construction (see Decision Rules above).
- `_sort_issues(items: list[tuple], sort_field: str, descending: bool) -> list[tuple]` — existing (`cli/issues/search.py:232`); its nested `key()` closure's `"refinement"` branch (`:271-279`) sums `session_command_counts` over a fixed `refinement_commands` frozenset by membership test — same needs-no-change reasoning as `cmd_next_action` above.

### Call Path

`commands/refine-issue.md` (`--gap-analysis` run) -> `ll-issues append-log` -> `cmd_append_log` -> `append_session_log_entry` (writes an undifferentiated `/ll:refine-issue` entry) -> `count_session_commands` / `IssueInfo.session_command_counts` -> three independent readers of the same map, each keying on the exact literal `/ll:refine-issue` string and each therefore auto-excluding a differently-keyed entry once the fix lands: `refine_status.py`'s `refine_count` (counts the gap-analysis entry toward the cap today), `next_action.py:58`'s `cmd_next_action` `NEEDS_REFINE` gate, and `search.py:279`'s `_sort_issues` `"refinement"` sort-field sum. A fourth, independent reader — `program_design.py`'s `_REFINE_ENTRY` / `issue_design_timestamp()` — must instead keep matching the gap-analysis entry (opposite requirement, see Decision Rules above) or Program Design gate staleness tracking regresses.

### Decision Rules

The discriminator's exact literal shape is an open decision — both candidates below satisfy the `[\w:-]+` regex constraint (see the Expected Behavior correction note above) and every downstream count site examined behaves identically under either, per this pass's direct read of the consuming code (not just the string shape):

1. **Discriminator shape: colon suffix — `/ll:refine-issue:gap-analysis`** — round-trips through `_COMMAND_RE`/`_TIMESTAMPED_ENTRY_RE` (`session_log.py:25,28-30`; `[\w:-]+` permits `:`). Differs from the literal `/ll:refine-issue` dict key, so `refine_status.py`'s `refine_count` (`:339,364`, `session_command_counts.get("/ll:refine-issue", 0)`) and `next_action.py:58`'s `NEEDS_REFINE` gate (same `.get("/ll:refine-issue", 0)` pattern) already exclude it with **zero code change** — both are exact dict-key lookups, not prefix/filter logic. `search.py`'s `"refinement"` sort field (`_sort_issues`'s `key()`, `:271-279`) likewise excludes it for free — `refinement_commands` is a fixed frozenset tested by membership, and a differently-keyed string is simply absent from the sum. Requires `_REFINE_ENTRY` (`program_design.py:130-132`, currently an exact-literal match on `` `/ll:refine-issue` ``) to be broadened to also accept a `:`-suffixed form — otherwise `issue_design_timestamp()` stops treating gap-analysis touches as refine activity and the Program Design gate's staleness clock regresses. In the human-facing `ll-issues refine-status` table (not its `--json` output, which is what `refine_count` above actually is) it sorts after every canonical column and displays as an un-aliased raw-string header until `_CANONICAL_CMD_ORDER`/`_CMD_ALIASES` (`refine_status.py:39-58`) are extended — cosmetic only, does not affect any counted value.

   > **Selected:** (1) — per the stated recommendation
2. **Discriminator shape: dash suffix — `/ll:refine-issue-gap-analysis`** — identical round-trip, count-exclusion, `_REFINE_ENTRY`, and display-table consequences to Option 1 above: every downstream site keys on exact string equality or frozenset membership, not on which non-`/ll:refine-issue` shape the string takes. The only material difference from Option 1 is readability — a dash-suffixed string reads as a distinct command name rather than a mode of the existing one, both in the raw `## Session Log` text and in that same un-aliased table column.

**Recommended**: Option 1 (colon suffix) — reads as a mode of `/ll:refine-issue` rather than a new command name, consistent with `_CMD_ALIASES` (`refine_status.py:50-58`) only ever aliasing bare command names today. No prior mode-suffixed Session Log entry exists in this codebase to establish a stronger precedent either way (see Codebase Research Findings → Conventions in Force below) — the two options are functionally identical everywhere this pass checked.

Independently of which shape is chosen: this is new recognition logic at exactly one site — `_REFINE_ENTRY` gains a second accepted token shape (see Option 1 above) — but it is **not** new branching/filtering logic at `refine_count`, `next_action.py:58`, or `search.py`'s `"refinement"` sort, which already exclude any non-matching key by construction (see Codebase Research Findings → correction below for the full trace).

### Decision Rationale

**Selected**: Option 1 — colon suffix (`/ll:refine-issue:gap-analysis`).

**Reasoning**: Both discriminator shapes are functionally identical at every downstream
count site this issue's own research already traced directly against the code —
`refine_status.py`'s `refine_count`, `next_action.py:58`'s `NEEDS_REFINE` gate, and
`search.py`'s `"refinement"` sort field all exclude a differently-keyed entry by
construction (exact dict-key `.get()` / frozenset membership), and both shapes round-trip
identically through `_COMMAND_RE`/`_TIMESTAMPED_ENTRY_RE` and require the identical
`_REFINE_ENTRY` broadening. The deciding factor is convention fit: a colon suffix reads
as a *mode* of the existing `/ll:refine-issue` command, consistent with how
`_CMD_ALIASES` (`refine_status.py:50-58`) only ever aliases bare command names rather than
minting new ones — the same reasoning already stated as this issue's own **Recommended**
line above. A dash suffix reads as an unrelated new command name, a weaker fit with that
convention.

| Option | Consistency | Simplicity | Testability | Risk | Total |
| --- | --- | --- | --- | --- | --- |
| 1 — colon suffix | 3 | 3 | 3 | 3 | 12/12 |
| 2 — dash suffix | 2 | 3 | 3 | 3 | 11/12 |

**Key evidence**: `refine_status.py:339,364`, `next_action.py:58`, and `search.py:271-279`
are exact-key/frozenset-membership lookups that exclude either shape with zero code
change (per this issue's own Codebase Research Findings correction); `_CMD_ALIASES`
(`refine_status.py:50-58`) aliases only bare command names today, favoring the mode-suffix
reading of Option 1 over the new-command-name reading of Option 2.

## Implementation Steps

1. The Decision Rules discriminator-shape choice (above) is resolved — via `/ll:decide-issue BUG-3356` or an explicit `> **Selected:**` callout on the winning option — before any code changes land. `ll-issues check-flag BUG-3356 decision_needed` reads `false` once resolved.
2. The chosen discriminator string round-trips through `_COMMAND_RE` and `_TIMESTAMPED_ENTRY_RE` (`scripts/little_loops/session_log.py:25`, `:28-30`) unmodified — both key off `[\w:-]+`, so the string must contain no space (see Expected Behavior correction note). Verified by `scripts/tests/test_session_log.py`.
3. `_REFINE_ENTRY` (`scripts/little_loops/issues/program_design.py:130-132`) recognizes both the bare `/ll:refine-issue` and the discriminated form as refine activity, so `issue_design_timestamp()`'s Program Design gate-arming clock keeps advancing on gap-analysis passes exactly as it does today on full-rewrite passes. Verified by `scripts/tests/test_program_design_gate.py`.
4. `research_triage.py`'s `REFINE_COMMAND` staleness check (`scripts/little_loops/issues/research_triage.py:69`) is updated in the same lockstep as step 3 — a `--gap-analysis` pass still counts as recent refine activity for Step 3.0's per-axis triage. Verified by `scripts/tests/test_research_triage.py`.
5. `ll-issues append-log` (or its caller, `commands/refine-issue.md` Step 6.5) writes the bare `/ll:refine-issue` string on a full-rewrite/default run and the chosen discriminated string on a `--gap-analysis` run — the CLI's `append-log` subcommand needs no new flag, since the caller already fully controls the literal string it passes to `append_session_log_entry()`. Verified by `scripts/tests/test_refine_issue_command.py` (including reconciling `test_max_refine_count_exemption_documented`, which currently pins the pre-fix exemption-claim text).
6. `refine_status.py`'s `refine_count` (`:339,364`), `next_action.py`'s `NEEDS_REFINE` gate (`:58`), and `search.py`'s `"refinement"` sort field (`_sort_issues`'s nested `key()`, `:271-279`) each stop counting the discriminated entry — per this pass's research (Program Design → Decision Rules), this already holds true by construction once the stored string differs from the literal `/ll:refine-issue` key, since each site reads via exact dict-key `.get()` or frozenset membership; no filter/aggregate logic is required at these three call sites specifically. Verified respectively by `scripts/tests/test_refine_status.py::TestRefineStatusJson`, a new case in `scripts/tests/test_next_action.py` (extending the fixture shape `test_graduates_after_refine_cap` uses), and a **new** test in `scripts/tests/test_issues_search.py` — no existing case there exercises the `"refinement"` sort field today (see Integration Map → Codebase Research Findings).
7. The three originally-cited exemption claims (`scripts/little_loops/config-schema.json` `commands.max_refine_count` description, `commands/refine-issue.md`, `scripts/little_loops/loops/refine-to-ready-issue.yaml`'s `refine_followup` comment) plus the two `docs/reference/COMMANDS.md` rows and the `docs/reference/CONFIGURATION.md` row all describe the same, now-true behavior — or are edited to stop claiming an exemption that doesn't exist — per whichever Decision Rules option was selected in step 1.
8. `scripts/little_loops/loops/recursive-refine.yaml`'s `check_attempt_budget` state (`:167-208`) needs no change — confirmed by this pass's research (Integration Map → Codebase Research Findings) to use an independent per-run `recursive-refine-attempts.txt` counter incremented once per issue's entry into the `run_refine` sub-loop, not `session_command_counts`. `scripts/tests/test_loops_recursive_refine.py` passes unmodified as a regression check.
9. `python -m pytest scripts/tests/` passes.

## Impact

- **Priority**: P3 - matches the filename prefix; a silently-eroded exemption in a lifetime-budget guardrail, not a user-facing break or data-loss risk.
- **Effort**: Small - a mode-discriminated Session Log entry plus a count filter in `count_session_commands`/`refine_status.py`; no new architecture.
- **Risk**: Low - additive to existing counting logic; `scripts/tests/test_refine_status.py` and `test_session_log.py`-style tests already pin current-count behavior and would catch a regression.
- **Breaking Change**: No - the discriminator is additive to the Session Log entry format; `refine_count`'s JSON shape is unchanged, only which entries it counts.

## Discovered

2026-08-28 review/refactor of `refine-to-ready-issue.yaml` (loop-side comment updated in the same pass; this issue tracks the CLI/command-side fix).

## Status

**Open** | Created: 2026-08-28 | Priority: P3

## Acceptance Criteria

1. Given an issue at `refine_count == commands.max_refine_count - 1`, running `/ll:refine-issue <ID> --gap-analysis` leaves `ll-issues refine-status <ID> --json`'s `refine_count` unchanged (still `max_refine_count - 1`); only a subsequent full-rewrite/default-mode `/ll:refine-issue <ID>` call increments it.
2. The Session Log entry written by a `--gap-analysis` run is distinguishable from a full-rewrite entry's command string, and still parses via `count_session_commands()`/`parse_session_log()` — i.e. it is not silently dropped by `_COMMAND_RE`/`_TIMESTAMPED_ENTRY_RE` the way the space-separated example in this issue's Expected Behavior would be (see the correction note there).
3. `issue_design_timestamp()` (`scripts/little_loops/issues/program_design.py`) treats a `--gap-analysis` Session Log entry as refine activity for Program Design gate-arming purposes, identically to a full-rewrite entry — an issue already past the gate-arming threshold does not un-arm (or re-grandfather) solely because its most recent refine touch was a gap-analysis pass.
4. `ll-issues next-issue`/`next-issues` (via `next_action.py:58`) and `ll-issues search --sort refinement` (via `search.py`'s `_sort_issues`) do not count a `--gap-analysis` Session Log entry toward their respective thresholds/sums, matching the exemption `refine_count` now also honors.
5. `scripts/little_loops/config-schema.json`'s `commands.max_refine_count` description, `commands/refine-issue.md`, `scripts/little_loops/loops/refine-to-ready-issue.yaml`'s `refine_followup` comment, `docs/reference/COMMANDS.md` (both cited rows), and `docs/reference/CONFIGURATION.md` make no claim that contradicts the shipped behavior.
6. `python -m pytest scripts/tests/` exits 0, including new/extended coverage in `test_session_log.py`, `test_refine_status.py`, `test_program_design_gate.py`, `test_research_triage.py`, `test_next_action.py`, `test_issues_search.py`, and `test_refine_issue_command.py`.

## Session Log
- `/ll:confidence-check` - 2026-08-29T19:18:52 - `2c13c55a-19b4-426e-82a9-8daecd5791a5.jsonl`
- `/ll:verify-issues` - 2026-08-29T19:12:46 - `fedec3ab-76ac-4b03-acac-d98d32d4349a.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:08:43 - `0ffc86a7-1497-4d98-b701-beefa90422f4.jsonl`
- `/ll:confidence-check` - 2026-08-29T18:59:15 - `91e591d4-09fb-4f3a-8a30-1b46c4420b97.jsonl`
- `/ll:wire-issue` - 2026-08-29T18:51:10 - `5b08caaf-d6d9-41cd-a302-ae95669f4151.jsonl`
- `/ll:refine-issue` - 2026-08-29T18:45:35 - `237f015b-641f-4613-8e7e-3269af82a4c8.jsonl`
- `/ll:format-issue` - 2026-08-29T18:20:58 - `477f6591-ae32-49d7-bc90-ee1e0759ddc3.jsonl`
