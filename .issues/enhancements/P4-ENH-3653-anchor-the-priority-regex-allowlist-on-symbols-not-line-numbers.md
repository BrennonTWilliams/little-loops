---
id: ENH-3653
type: ENH
title: Anchor the priority-regex allowlist on symbols, not line numbers
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T04:19:19Z'
---

# ENH-3653: Anchor the priority-regex allowlist on symbols, not line numbers

## Summary

`TestPriorityRegexCompletenessAllowlist` in `scripts/tests/test_issue_parser.py` keys its allowlist of raw priority regexes on file line numbers (for example `session_store/writers.py` at lines near 3100). Any edit above those lines shifts them and fails two tests at once (`test_no_unallowlisted_raw_priority_regex` and `test_allowlist_entries_still_exist`), even though nothing about the regex usage changed. It broke three times during FEAT-3535 from unrelated import and helper edits in `writers.py`.

## Current Behavior

The allowlist maps `path -> {line_number: justification}`. Adding or removing lines earlier in the file makes the recorded numbers stale, and the failure message lists the new numbers for a manual update.

## Expected Behavior

The allowlist identifies each entry by a stable anchor (the enclosing symbol name such as `_FILENAME_PRIORITY_RE`, or the enclosing function or class, plus the pattern text) so unrelated edits do not fail the gate. A genuinely new raw priority regex still fails; a removed one still reports a stale entry.

## Motivation

Two tests fail with a misleading "new regex" message on every edit above the pinned lines, costing a manual line-number edit each time and training contributors to update allowlists without reading them.

## Proposed Solution

Change the allowlist keys from line numbers to symbol anchors resolved via `ast` (module-level assignment target or enclosing `def`/`class`), keeping the justification strings. Keep the stale-entry check keyed on the anchor and pattern.

## Integration Map

### Files to Modify
- `scripts/tests/test_issue_parser.py` (`TestPriorityRegexCompletenessAllowlist`)

### Tests
- The same two tests; add one that shifts a line and confirms the gate still passes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Detection today is a per-physical-line regex (`_PATTERN`), not `ast`; the current allowlist matches the scan exactly (31 hits, 16 files, no drift). Of those 31, 3 are comment lines (`issue_history/parsing.py:53`, `issue_parser.py:4369`, `sync.py:291`), 3 are docstring lines inside multi-line strings (`issue_parser.py:351`, `session_store/writers.py:3175`, `cli/issues/prioritize.py:61`), and 2 sit inside the ~465-line module-level `_TOOLS` literal (`mcp_server/tools.py:848`, `:1006`) where no `def`/`class` encloses them.
- Comments are not `ast` nodes, so anchors for them can only come from line-span resolution over `FunctionDef`/`ClassDef` `lineno..end_lineno`. All 3 current comment entries sit physically inside a function body, so none resolves to `<module>`.
- Same-symbol collisions under a `<symbol>::<matched text>` key (verified by an `ast` line-span scan): `cli/issues/search.py` `_parse_priority_filter::P\d` (lines 114, 120); `hooks/post_tool_use.py` `_maybe_auto_commit::P[0-5]` (98, 108); `mcp_server/tools.py` `_TOOLS::P[0-5]` (848, 1006); and `issue_parser.py` module-level assignments (50, 58, 2116) if `<module>` is the fallback. Two of these pairs carry *different* justification strings, so a single key cannot hold both.
- Methods carry class context: `_parse_type_and_id` and `_generate_id_from_filename` (`IssueParser`), `_extract_issue_id` (`GitHubSyncManager`). A leaf-name anchor is ambiguous across classes; the dotted-vs-leaf choice is not fixed by current code.
- Line-pinned drift is a long-standing recurring cost: BUG-3448 was a whole issue for `mcp_server/tools.py` drift, and ~20 other issue files record "allowlist line numbers updated for the resulting shift". The class's own maintenance comment ("Re-derive line numbers…") and the ENH-3623 re-measure comment above the `issue_parser.py` entries are line-number-specific and become obsolete with the re-key.
- Origin: BUG-3286 § Tests / Completeness verification (Implementation Step 10) specified the "frozen set of `path:line` entries, each with a one-line reason".

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Convention held across the suite: allowlist guards are a bidirectional pair — a "new un-allowlisted hit fails" test and a "stale entry fails" test (`test_history_store_chokepoint_gate.py`, `test_host_resolution_chokepoint_gate.py`, `test_builtin_loops.py::TestValidatorWarningBudget`, `test_bug3269_test_cmd_resolution_gate.py`); two guards fold both into one exact-set equality with a message naming both diffs (`TestMr11MarkerSet.test_marker_set_matches_enumeration`, `TestInterpSweepBaseline.test_completeness_guard`). Current staleness check here differs: it re-applies `_PATTERN` at a recorded line rather than re-running the scan and diffing.
- Convention held for keying by enclosing scope: the only precedent is `test_usage_selection_chokepoint_gate.py` (`_enclosing_functions`, `_ALLOWLIST: dict[tuple[str, str], str]` keyed `(rel_path, enclosing_function)`, fallback literal `"<module>"`); it resolves `def`/`async def` only, no classes, and has no multiplicity handling. `scripts/little_loops/issues/anchors.py:resolve_anchor` is a regex backwards scan (no `ast`, display-string output) and no test uses it as an allowlist key.
- Convention held for gate-regression tests: feed a synthetic inline source string (or `tmp_path` file) to the same scanner the gate uses, as a positive/negative pair (`test_host_resolution_chokepoint_gate.py::test_gate_detects_a_stray_site`, `::test_gate_ignores_non_reads`; `test_usage_selection_chokepoint_gate.py::test_gate_detects_a_stray_site`). No test in `scripts/tests` copies a real source file such as `session_store/writers.py` and mutates it — Implementation Step 3's temp-copy approach has no precedent, and a synthetic snippet with a shifted-lines variant would satisfy the same acceptance criterion without coupling the test to `writers.py` content. This is a contested choice for the implementer.
- Helper placement is mixed: `test_issue_parser.py` uses both module-level private helpers (`_parse_issue_frontmatter`, defined above its class) and class `@staticmethod` helpers; standalone gate modules use module-level private functions. The file has no `import ast` today. `TestPriorityRegexCompletenessAllowlist` has no helper methods and both tests duplicate the repo-root/scan setup inline.
- Failure messages in sibling guards tell the contributor what to do ("add a reasoned allowlist entry", "justify here or convert to resolve_priority"); the existing message here also lists new line numbers for manual update, which the re-key removes.

## Scope Boundaries

- **In scope**: re-keying `_ALLOWLIST` in `TestPriorityRegexCompletenessAllowlist` from line numbers to symbol anchors; adapting the two existing tests; adding one line-shift regression test.
- **Out of scope**: changing which raw priority regexes are allowlisted or their justification text; converting any allowlisted regex to `resolve_priority`; the detection pattern `_PATTERN`; other line-number-pinned allowlists elsewhere in the test suite.

## Program Design

### Types

- `_ALLOWLIST: dict[str, dict[str, str]]` — relative path -> `{"<symbol>::<matched pattern text>": justification}`

### Signatures

- `_enclosing_symbol(tree: ast.AST, lineno: int) -> str` — nearest enclosing `def`/`class` name, or the module-level assignment target, else `"<module>"`
- `_scan_priority_regex_hits(src_root: Path) -> dict[str, set[str]]` — relative path -> set of `"<symbol>::<pattern>"` anchors

### Call Path

`TestPriorityRegexCompletenessAllowlist.test_no_unallowlisted_raw_priority_regex` -> `_scan_priority_regex_hits` -> `_enclosing_symbol`

`TestPriorityRegexCompletenessAllowlist.test_allowlist_entries_still_exist` -> `_scan_priority_regex_hits` -> `_enclosing_symbol`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Constraint on `_scan_priority_regex_hits -> dict[str, set[str]]`: a set of `"<symbol>::<pattern>"` anchors collapses same-symbol duplicates (4 collision groups above). Under set semantics a *new* raw regex added inside an already-allowlisted symbol (e.g. a third `"pattern": "^P[0-5]$"` in `_TOOLS`) passes silently, and removing one of a colliding pair leaves the other satisfying the key so no stale entry is reported. This conflicts with the Acceptance Criteria ("newly added raw priority regex still fails"; "removed regex reports a stale entry") unless occurrence multiplicity is preserved in the scan result and the allowlist (e.g. a per-anchor count, or an ordinal within the symbol). Whether an occurrence count or per-hit ordinal is the right key is an implementation judgment; the property required is that the count of hits per anchor is compared, not just presence.
- Constraint on `_enclosing_symbol`: it must handle module-level assignment targets that span many lines (`_TOOLS`, lines 826–1290) and comment/docstring lines that `ast` never yields as statements — line-span containment against `FunctionDef`/`ClassDef`/`Assign` nodes, not per-node `ast.walk` attribution. Nested defs/methods resolve to the innermost containing span.

## Implementation Steps

1. Add `_enclosing_symbol` and `_scan_priority_regex_hits` helpers (via `ast`) that resolve each `_PATTERN` match to a `"<symbol>::<pattern>"` anchor; comment-only lines fall back to the enclosing symbol or `"<module>"`.
2. Re-key every `_ALLOWLIST` entry to its anchor, keeping the justification strings, and point both existing tests at the shared scan helper.
3. Add a regression test that inserts lines above an allowlisted regex in a temp copy of `session_store/writers.py` and confirms the gate still passes, plus checks that a new un-allowlisted regex fails and a removed one reports a stale entry.
4. Run `python -m pytest scripts/tests/test_issue_parser.py -k PriorityRegexCompleteness` and confirm all pass.

## Impact

- **Priority**: P4. Test-maintenance friction only.
- **Effort**: Small.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Inserting or deleting lines above an allowlisted regex in `session_store/writers.py` does not fail the gate.
- [ ] A newly added raw priority regex outside the allowlist still fails.
- [ ] A removed allowlisted regex still reports a stale entry.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-09-29T04:55:38 - `4499f980-478f-43ad-ae6e-d08229ebdabd.jsonl`
- `/ll:format-issue` - 2026-09-29T04:50:00 - `d770577e-1f76-4a53-b5c3-a8661dec6288.jsonl`
- `/ll:capture-issue` - 2026-09-29T04:19:25 - `4d45d755-73ff-4de3-8bd1-bb8e866143f2.jsonl`
