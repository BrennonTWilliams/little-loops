---
id: BUG-3344
type: BUG
title: Port Searched-No-Hits evidence contract to consistency-checker
priority: P3
status: open
discovered_by: review-of-BUG-3333
discovered_date: '2026-08-27'
captured_at: '2026-08-27T00:00:00Z'
---

# BUG-3344: Port Searched-No-Hits evidence contract to consistency-checker

## Summary

BUG-3330 gave `agents/codebase-locator.md` a `### Searched, No Hits` output
group so negative claims carry the same citation discipline as positive ones;
BUG-3333 ports that contract to `agents/codebase-analyzer.md` and
`agents/codebase-pattern-finder.md`. `agents/consistency-checker.md` has the
identical Bash-free tool restriction and is the remaining research-class agent
whose output is *predominantly* negative claims — yet it carries none of the
scope discipline.

## Current Behavior

`agents/consistency-checker.md:14` declares
`tools: ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` — the same Bash-free
restriction as the three agents BUG-3330/BUG-3333 cover. Its
`### Step 2: Validate Each Reference` (lines 111-117) instructs the agent to
"Check if target exists" and "Record status (OK, MISSING, BROKEN)" with no rule
about the scope of the search that produced a `MISSING` verdict. A
`type:`/`glob:`/`path:`-narrowed Glob or Grep that fails to locate a target
therefore becomes a `MISSING` cell with no obligation to state the scope
searched or re-run unfiltered first.

Unlike the other three agents, the negative claim is not an aside — it is the
agent's primary product. `## Output Format` (lines 133-358) is built almost
entirely from `Status` columns whose values are `OK`/`MISSING`/`BROKEN`, plus
dedicated `### Missing References` (lines 309-315) and `### Broken References`
(lines 317-322) tables. `## Severity Levels` (lines 360-364) assigns
**CRITICAL** to "Broken references that will cause failures (missing agents,
scripts)", so a filtered-search false negative does not merely mislead — it
emits a CRITICAL finding.

The existing guardrails are intent-level only and do not constrain search
scope: `## Important Guidelines:368` says "**Check actual file existence** -
don't assume" and `## What NOT to Do:376,379` say "Don't assume references are
valid without checking" / "Don't skip checking because 'it probably exists'".
All three push against *under*-checking; none addresses a check that ran but
covered only a slice of the tree.

## Expected Behavior

`agents/consistency-checker.md` carries the same negative-claim discipline:
every `MISSING` verdict states the scope actually searched, a narrowing filter
makes the result evidence about that slice only, and the search is re-run
unfiltered before `MISSING` is recorded (except where the caller scoped the
question). A matching prohibition bullet lands in `## What NOT to Do`.

## Motivation

This agent has the highest blast radius of the four for the same defect:

- Its negative claims are the deliverable, not a footnote.
- A false `MISSING` is auto-escalated to **CRITICAL** by `## Severity Levels`.
- It is invoked non-interactively as Wave 2 of `/ll:audit-claude-config`
  (`skills/audit-claude-config/SKILL.md:228,268`), so its verdicts land in an
  audit report a human reads as authoritative rather than in a conversational
  answer they can push back on.
- Many of its cross-reference targets live in dot-directories and non-source
  paths (`.claude/rules/`, `~/.claude/`, `.mcp.json`, `managed-settings.json`,
  `.claudeignore`, `.lsp.json` — see the Cross-Reference Matrix, lines 46-77),
  which is exactly the region a default-scoped or convention-scoped search is
  most likely to miss.

## Steps to Reproduce

1. `grep -n "Searched, No Hits" agents/consistency-checker.md` — zero matches
   (contrast `agents/codebase-locator.md:84,135` post-BUG-3330).
2. Ask the `consistency-checker` subagent to validate a reference whose target
   lives outside a conventional source path (e.g. a hook script under a
   dot-directory, or an MCP server defined only in a user-scope config).
3. Observe the `Status` cell recorded as `MISSING` — and, per
   `## Severity Levels`, surfaced as CRITICAL — with no statement of the scope
   searched, since nothing in the prompt requires one.

## Proposed Solution

Port the contract established by BUG-3330 and extended by BUG-3333, adapted to
this agent's reference-validation vocabulary rather than
symbol-location vocabulary:

- Before recording `MISSING` for a reference target, re-run the lookup
  unfiltered — the whole tree, no `glob`/`type`/`path` narrowing — except where
  the caller scoped the audit to a path or file type.
- The row states the scope actually searched; a narrowed miss is evidence about
  that slice only and must never be reported as tree-wide absence.
- Named exclusions carry the hit count inside the excluded path.
- One row per distinct reference target; no aggregate negatives.
- A matching prohibition bullet in `## What NOT to Do`.

The natural shape here differs from the other three agents: this file's output
is already a table-per-check-type structure with a `Status` column, so the
contract is best expressed as (a) a rule governing what may be written in a
`Status` cell, and (b) a **`Scope Searched`** column (or an explicit
`### Searched, No Hits` group) carrying the evidence. Choose one and apply it
consistently — see Open Questions.

## Program Design

### Types
- N/A — no data-shape change; `agents/consistency-checker.md` is an agent-prompt markdown file, not typed code.

### Signatures
- `DOC_STRINGS_PRESENT: list[tuple[str, str, str]]` (`scripts/tests/test_wiring_skills_and_commands.py:253-276`) — the `(doc_path, exact_substring, issue_id)` tuple contract this issue's new pinned strings must follow, same shape as the BUG-3330/BUG-3333 precedent tuples.
- `test_string_present_in_doc(project_root, doc_rel, needle, issue_id)` (`scripts/tests/test_wiring_skills_and_commands.py:289-294`) — the parametrized assertion that consumes each new tuple; no new test function is needed, only new tuples.

**Exact needles depend on Open Question 1.** If the `Scope Searched` column option is chosen, pin a needle on the literal column header (e.g. `"Scope Searched"`); if the `### Searched, No Hits` group option is chosen, pin `"### Searched, No Hits"` as in BUG-3330/BUG-3333. Either way, add one structural needle plus one vocabulary needle drawn from the new prohibition bullet in `## What NOT to Do`, tagged `"BUG-3344"`.

### Call Path
`DOC_STRINGS_PRESENT` list literal -> `pytest.mark.parametrize("doc_rel, needle, issue_id", DOC_STRINGS_PRESENT)` (`test_wiring_skills_and_commands.py:288`) -> `test_string_present_in_doc()` reads `agents/consistency-checker.md` off `project_root` and asserts each `needle` substring is present.

### Decision Rules
- **Negative-claim trigger re-anchoring (same finding as BUG-3333)**: `agents/consistency-checker.md` has no evidence-bearing/inferred partition to anchor a "not cited above" trigger against. Anchor the mandatory-row (or mandatory-cell) trigger to the `Status` column of the Reference Validation tables instead: a row's evidence is mandatory whenever `Status` is recorded as `MISSING`.
- **Scope applies to `MISSING` only** (Open Question 2): `BROKEN` verdicts come from reading a target that was already found, so the filtered-search failure mode does not apply — state this explicitly in the ported rule so it is not over-applied to `BROKEN`.

## Integration Map

### Files to Modify
- `agents/consistency-checker.md` — negative-claim rule near
  `### Step 2: Validate Each Reference` (lines 111-117) and/or `## Output
  Format` (line 133); prohibition bullet in `## What NOT to Do`
  (lines 374-380).

### Dependent Files (Callers/Importers)
- `skills/audit-claude-config/SKILL.md:228,268` — invokes by
  `subagent_type="consistency-checker"` and prompt only; does not restate the
  agent's Output Format contract. Verify whether Wave 2's own report template
  needs a matching column if the `Scope Searched` option is chosen.
- Host mirrors (generated, never hand-edited), all four confirmed present:
  `.codex/agents/consistency-checker.toml`,
  `.gemini/agents/consistency-checker.md`,
  `.kimi-code/agents/consistency-checker.md`,
  `.qwen/agents/consistency-checker.md`. Regenerate with
  `ll-adapt --host <host> --apply` (one host per invocation).
- `docs/reference/API.md:12405` — agent reference-table row; content stays
  accurate for a prose-only change (BUG-3330 precedent).

### Similar Patterns
- `agents/codebase-locator.md:84-101` (negative-claim prose), `:135-139`
  (sample rows inside the fenced template), `:167-169` (prohibition bullet) —
  the proven source shape.
- BUG-3333 — the sibling port to `codebase-analyzer`/`codebase-pattern-finder`,
  including its finding that locator's "not cited in an evidence-bearing group
  above" trigger clause must be **re-anchored** to each target file's own
  output structure rather than copied verbatim. The same applies here: this
  file has no evidence-bearing/inferred partition, so the trigger must be
  anchored to the `Status` cells of the Reference Validation tables.

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` — append
  `DOC_STRINGS_PRESENT` tuples `(doc_path, needle, issue_id)` tagged
  `BUG-3344`, mirroring the BUG-3330 block at lines 262-276; consumed by the
  existing parametrized `test_string_present_in_doc` (lines 288-294). No new
  test function needed.
- **Existing constraint to respect**: `DOC_STRINGS_ABSENT` (lines 318-323,
  ENH-2291) forbids the literal `| hooks/prompts/optimize-prompt-hook.md |` in
  both `agents/consistency-checker.md` and
  `.codex/agents/consistency-checker.toml` (the pre-FEAT-2274 path). Any edit
  near the Hooks → Prompts sample table at line 152 must not reintroduce it.
- Note the ENH-1299 `file:line` prohibition that constrains BUG-3333 does
  **not** apply here — `agents/consistency-checker.md` is absent from that
  `DOC_STRINGS_ABSENT` set and already uses `file:line` at line 370.

### Documentation
- N/A — `docs/ARCHITECTURE.md:74` lists the file in a directory tree only; no
  prose restates the agent's Output Format contract.

### Configuration
- N/A.

## Open Questions

1. **`Scope Searched` column vs. `### Searched, No Hits` group.** The other
   three agents use a standalone group because their output is prose plus a
   fenced template. This agent's output is ~26 tables keyed by check type; a
   standalone group duplicates the target list, while a new column widens every
   table. A third option is to scope the contract to the two aggregate tables
   (`### Missing References`, `### Broken References`, lines 309-322) that
   already collect every negative in one place. Decide before implementing.
2. **Whether the contract extends to `BROKEN`.** `BROKEN` verdicts
   (not-executable, unresolved symlink) come from reading a target that *was*
   found, so the filtered-search failure mode does not apply. Likely scope this
   to `MISSING` only, but state it explicitly so the rule is not over-applied.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- BUG-3333 (the sibling port to `codebase-analyzer.md`/`codebase-pattern-finder.md`) is confirmed still `status: open` and unlanded as of this research pass — a repo-wide grep for `"Searched, No Hits"` returns zero hits in both files. `agents/codebase-locator.md` therefore remains the only landed precedent available to mirror; do not assume the other two files show a second worked example.
- `agents/consistency-checker.md` and its Wave-2 consumer `skills/audit-claude-config/report-template.md` already use a `Scope` (and `Scope 1`/`Scope 2`) column header with an established meaning — configuration precedence scope (project/user/local/managed), e.g. `consistency-checker.md`'s `#### Settings → Scope Conflicts` table (lines 262-266) and `report-template.md` (lines 91-114, 129). A bare `Scope` column for this contract would collide with that existing vocabulary; `Scope Searched` (the issue's own working name) avoids the collision — this is evidence in favor of that naming if Open Question 1 chooses the new-column option.
- `report-template.md` (line 225) carries a `### Missing References` heading but no matching `### Broken References` heading — the report template only partially mirrors `consistency-checker.md`'s own aggregate-table structure. Relevant to Open Question 1's third option (scoping the contract to the two aggregate tables only), since that option's symmetry assumption doesn't hold on the consumer side.

## Impact

- **Priority**: P3 - No reproduction has yet surfaced a harmful output from
  this agent; filed as a known gap in the same mechanism BUG-3330 fixed. Rank
  above BUG-3333 within P3 if sequencing, per the blast-radius argument in
  Motivation.
- **Effort**: Small - Prose-only port of a proven contract into one file, plus
  test tuples and four mirror regenerations. The one design decision is Open
  Question 1.
- **Risk**: Low - Additive prompt instructions; no code path changes.
- **Breaking Change**: No

## Related Issues

- BUG-3330 — origin of the `### Searched, No Hits` contract
  (`codebase-locator.md`)
- BUG-3333 — sibling port to `codebase-analyzer.md` /
  `codebase-pattern-finder.md`; carries the re-anchoring finding this issue
  reuses

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-27 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-27T20:05:46 - `9e4fa033-0b0b-43cd-be66-950ccb670df0.jsonl`
- `/ll:format-issue` - 2026-08-27T19:59:56 - `278ef87b-9267-47eb-b438-15c48011237e.jsonl`
