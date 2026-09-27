---
id: ENH-3632
type: ENH
title: Add `ll-issues advise-consult` helper and shared `parse_lead_word`
priority: P3
status: open
discovered_by: ll-issue-size-review
discovered_date: '2026-09-27'
parent: ENH-3626
relates_to:
- ENH-3623
- ENH-3630
blocks:
- ENH-3633
- ENH-3590
decision_needed: false
---

# ENH-3632: Add `ll-issues advise-consult` helper and shared `parse_lead_word`

## Summary

Build the shared Python entry point `ll-issues advise-consult <ID> --run-dir <dir>` that calls
`little_loops.advisor.consult_for_trigger("refine_ready", ..., manual=True)` in-process,
persists the verdict, and maps it to a single routing token (`PROCEED`/`VETO`/`SKIPPED`).
Also extract a shared public `parse_lead_word` from the `advisor_consult` evaluator. This is
the independently mergeable slice ENH-3590 needs; the loop wiring lives in ENH-3633.

## Parent Issue

Decomposed from ENH-3626: Add opt-in second-model advise readiness consult to refine-to-ready.
Covers parent Implementation Steps 1-2 and the "Shared helper" / "Parser reuse" subsections of
Proposed Solution. Read the parent (status `done`, decomposed) for full rationale, including
"Why in-process instead of spawning `ll-advise`" and "Why not the existing `advisor_consult`
evaluator".

## Motivation

`refine-to-ready-issue` (ENH-3633) and ENH-3590's go-no-go waiver veto both need a
second-model consult with the same budget, replay, and verdict-mapping semantics. One helper
avoids carrying two copies.

## Proposed Solution

**Helper** (`scripts/little_loops/cli/issues/advise_consult.py`, new):

1. **Replay** a prior verdict first: if `<run_dir>/advise-<ID>.verdict` exists, print its token
   and exit 0 without consulting. A replayed PROCEED/SKIPPED is honored only while the recorded
   SHA-256 of the **trimmed consult context** still matches (else discard and consult again). A
   replayed VETO is sticky regardless of edits. Keyed by ID, so it never crosses issues.
2. **Preflight the advisor config without spending budget.** `consult_for_trigger` spends a
   budget unit via `record_consult()` (`advisor.py:541`) before `consult()` raises
   `AdvisorNotConfigured` when `advisor.host` is unset (`advisor.py:256`); `AdvisorConfig.host`
   defaults to `None` (`config/orchestration.py:157`). If `config.advisor.host` is empty: log a
   WARNING, persist `{"skipped_reason": "not_configured", "preflight": true}`, print `SKIPPED`,
   never call `consult_for_trigger`. `floor_violation` stays a post-reservation skip.
3. Otherwise call `consult_for_trigger("refine_ready", question=<q>, context=<trimmed issue
   text>, manual=True)` in-process with `LL_ISSUE_ID=<ID>` set in `os.environ` first so
   `resolve_task_key()` bills the per-issue budget bucket. `manual=True` bypasses
   `advisor.enabled` and `advisor.triggers` (no config entry needed).
   - **Context trimming** (`trim_consult_context`): strip frontmatter and the `## Session Log`,
     `## Confidence Check Notes`, `### Codebase Research Findings`, and `## Advisor Veto`
     sections; cap at a fixed character limit chosen during implementation. The same trimmed
     text is the replay-hash input. The advisor never sees its own earlier veto.
   - **No helper-side timeout**: bounded by `advisor.timeout_seconds` (default 180); returns
     `skipped_reason="timeout"`. A shorter outer timeout would kill consults that would have
     succeeded while still spending budget.
   - **Pinned question text**: _"Is this issue ready to implement as written? Begin your
     recommendation with exactly one word, PROCEED or VETO, then give the reason. VETO only for a
     concrete defect that would make implementation fail or be wasted; otherwise PROCEED."_
     (the word must lead the `recommendation` field of `_VERDICT_SCHEMA`). ENH-3590 overrides via
     `--signal` / `--question`.
4. Write `<run_dir>/advise-<ID>.json` (verdict payload, or `{"skipped_reason": ..., "error":
   ...}`) and `<run_dir>/advise-<ID>.verdict` (token + context hash).
5. **Map** `ConsultOutcome` → PROCEED/VETO/SKIPPED (`map_advise_verdict`, pure). `verdict is
   None` → SKIPPED (log `skipped_reason`; WARNING for `not_configured`/`floor_violation`).
   Unreadable issue file or any helper exception → SKIPPED. Otherwise the **leading word** of
   `recommendation` via `parse_lead_word` decides: `VETO` → VETO, anything else → PROCEED. No
   whole-word fallback ("no reason to VETO" → PROCEED). `confidence`/`dissent` are logged only.
6. **Always exit 0** (catch-all around `main`, including `BRConfig` load failure) and print one
   token, matching the `next-obligation --format token` shape, so executor-side 429 interception
   (non-zero exit only) can never stall a loop.
7. `--write-note`: on VETO replace any `## Advisor Veto` section in the issue file with the
   recommendation; on PROCEED remove a stale one; SKIPPED leaves the file alone.

**Parser reuse:** extract the lead-word step of `_parse_advisor_decision`
(`fsm/evaluators.py:1726`) into public `little_loops.advisor.parse_lead_word(recommendation,
choices) -> str | None`. Also fixes the tokenizer: today's split on `[\s:,.]`
(`evaluators.py:1735`) turns `**VETO**`, `VETO—the…`, `"VETO"` into non-matching words (a silent
false PROCEED). New behavior: skip leading non-word characters, take the first word-character run
(`re.match(r"\W*(\w+)", text)`), compare case-insensitively to `choices`, return the choice as
given. The evaluator keeps its whole-word fallback on top; strictly more permissive.

## Program Design

### Types
- `AdviseVerdict`: `Literal["PROCEED", "VETO", "SKIPPED"]`

### Signatures
- `parse_lead_word(recommendation: str, choices: Iterable[str]) -> str | None` — shared lead-word tokenizer extracted from `_parse_advisor_decision`
- `trim_consult_context(issue_text: str) -> str` — strips frontmatter and the excluded sections, caps length; is both the consult context and the replay-hash input
- `map_advise_verdict(outcome: ConsultOutcome) -> tuple[AdviseVerdict, str]` — pure mapping of a consult outcome to a verdict plus a log reason
- `cmd_advise_consult(config: BRConfig, args: argparse.Namespace) -> int` — replay, preflight, in-process consult, persist, optional note, print token, always returns 0

### Call Path
`cmd_advise_consult` -> `trim_consult_context` -> `consult_for_trigger` -> `map_advise_verdict` -> `parse_lead_word`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/advise_consult.py` (new) — `add_advise_consult_parser` / `cmd_advise_consult` / `map_advise_verdict` / `trim_consult_context`
- `scripts/little_loops/cli/issues/__init__.py` — four registration sites: lazy import, epilog listing (next to `next-obligation`/`run-record`), `add_*_parser(subs)`, `args.command` dispatch. Check overlap with ENH-3630 registration before starting
- `scripts/little_loops/advisor.py` — new public `parse_lead_word()`
- `scripts/little_loops/fsm/evaluators.py` — `_parse_advisor_decision` calls `parse_lead_word()`; whole-word fallback stays

### Dependent Files
- `little_loops.cli.advise.main_advise` — not called; model for the `manual=True` call
- `little_loops.advisor.consult_for_trigger` — reserves budget before the host call; per-issue budget (`max_consults_per_task=3`) shared with `confidence_gate` (`issue_manager.py:849`) and `hooks/pre_done.py`
- Sibling helper modules as shape models: `next_obligation.py`, `check_verify_verdict.py`, `run_record.py`

### Documentation
- `docs/reference/CLI.md` — new `#### \`ll-issues advise-consult\`` section and subcommand-table entry; cross-reference from `### ll-advise`
- `docs/reference/API.md` — new row in the `little_loops.cli.issues.*` table (next to `run-record`)
- `docs/reference/CONFIGURATION.md` `### advisor` — document that `advisor.host` is required for the consult to do anything (this repo's `.ll/ll-config.json` sets only `advisor.model`), and the accepted budget contention with `pre_done`/`confidence_gate` consults (per-issue file `.ll/advisor-budget/issue-<ID>.json` never expires; follow-up would be a `resolve_task_key` budget scope)

### Tests
- New `scripts/tests/test_ll_issues_advise_consult.py` — model on `test_ll_issues_next_obligation.py::TestCli` and `test_run_record.py::TestRecordToken`; monkeypatch `consult_for_trigger`
  - crash (e.g. `BRConfig` load failure) still prints `SKIPPED`, exit 0
  - replay: same ID twice under a shared `run_dir` → one consult; replayed PROCEED discarded after trimmed context changes but kept when only frontmatter/Session Log/Advisor Veto change; replayed VETO sticky; two IDs → two consults
  - preflight: `advisor.host` unset → `SKIPPED`, `consult_for_trigger` never called, no budget file created/incremented
  - `map_advise_verdict` over fixture `ConsultOutcome`s (each `skipped_reason`, PROCEED/VETO lead words, "no reason to VETO", real `_VERDICT_SCHEMA` payload shape)
  - `trim_consult_context`: excluded sections absent, length cap applied
  - `--write-note` writes on VETO, clears on PROCEED; `LL_ISSUE_ID` in `os.environ` at consult time
- `parse_lead_word` tests: `**VETO**`, `VETO—reason`, `"VETO"`, `` `VETO` ``, `veto:` → `VETO`; `PROCEED` variants likewise
- `scripts/tests/test_fsm_evaluators.py`, `scripts/tests/test_advisor.py` — pass unchanged; add one evaluator case showing a bolded decision word matches at the lead-word step
- `scripts/tests/test_wiring_reference_docs.py` — add `("docs/reference/CLI.md", "#### \`ll-issues advise-consult\`", "ENH-3632")` and the `API.md` row

## Implementation Steps

1. Extract `parse_lead_word` into `little_loops.advisor`; have `_parse_advisor_decision` call it (existing evaluator tests pass unchanged).
2. Build and test the helper per Proposed Solution, including `--write-note`, preflight, replay, and the always-exit-0 token contract.
3. Register the subcommand in `cli/issues/__init__.py`; add docs and `test_wiring_reference_docs.py` rows.
4. `ll-issues advise-consult --help` smoke check; run the touched test files and `ruff`/`mypy` on changed files.

## Acceptance Criteria

- [ ] With `advisor.host` unset, the helper prints `SKIPPED` without calling `consult_for_trigger` and without creating or incrementing the per-issue budget file
- [ ] `LL_ISSUE_ID` is set by the helper before calling `consult_for_trigger`, billing the per-issue budget
- [ ] The helper sets no outer timeout; a consult slower than `advisor.timeout_seconds` maps to SKIPPED via `skipped_reason="timeout"`
- [ ] Any consult failure (`budget_exhausted`, `not_configured`, `floor_violation`, `failed`, `timeout`, unreadable issue file, helper exception) prints `SKIPPED` and exits 0
- [ ] A second invocation for the same ID under the same `run_dir` replays the persisted verdict without consulting; a replayed VETO stays VETO
- [ ] Payload (or skip record) and token persist to `<run_dir>/advise-<ID>.{json,verdict}`
- [ ] The consult question text is pinned in the helper; a fixture test maps the real `_VERDICT_SCHEMA` payload shape to PROCEED/VETO; only the lead word counts ("no reason to VETO" → PROCEED)
- [ ] Formatted lead words still veto: `**VETO**`, `VETO—…`, `"VETO"`, `` `VETO` ``
- [ ] `parse_lead_word` is shared by the helper and `_parse_advisor_decision`; existing `advisor_consult` evaluator tests pass unchanged
- [ ] The consult context excludes frontmatter, `## Session Log`, `## Confidence Check Notes`, `### Codebase Research Findings`, `## Advisor Veto`; the replay hash covers that same trimmed context
- [ ] `--write-note` writes `## Advisor Veto` on VETO and removes a stale one on PROCEED
- [ ] ENH-3590 can reuse the helper unchanged (`--signal` / `--question` overrides)

## Scope Boundaries

- **In scope**: helper, `parse_lead_word` extraction, CLI registration, docs, helper tests.
- **Out of scope**: any `refine-to-ready-issue` / caller loop change (ENH-3633); the go-no-go waiver veto (ENH-3590); changing `ll-advise` internals; a separate budget scope for readiness consults.

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:issue-size-review` - 2026-09-27T05:15:41 - `682a095a-efe4-40ac-8619-962c00f444e7.jsonl`
