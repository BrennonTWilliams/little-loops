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

The allowlist identifies each entry by a stable anchor (the dotted qualified name of the enclosing function or class such as `IssueParser._parse_type_and_id`, or the top-level assignment target such as `_FILENAME_PRIORITY_RE`) plus an occurrence count, so unrelated edits do not fail the gate. A genuinely new raw priority regex still fails (including a second one inside an already-allowlisted symbol); a removed one still reports a stale entry.

## Motivation

Two tests fail with a misleading "new regex" message on every edit above the pinned lines, costing a manual line-number edit each time and training contributors to update allowlists without reading them.

## Proposed Solution

Change the allowlist keys from line numbers to `(rel_path, qualname)` anchors resolved via `ast` (innermost enclosing `def`/`class` by line span, else top-level assignment target, else `"<module>"`), each mapped to `(count, justification)`. The scan counts matching physical lines per anchor; one exact comparison reports both new and stale keys. See § Design Decisions for the rationale behind each choice.

## Integration Map

### Files to Modify
- `scripts/tests/test_issue_parser.py` (`TestPriorityRegexCompletenessAllowlist`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — `TestPriorityRegexCompletenessAllowlist` class docstring cites `issue_parser.py:272`-ish for `resolve_issue_path`'s `startswith` tiebreaker; a line-number reference of the same kind the re-key removes, so reword it to name the symbol. Also add `import ast` to the module imports (none today; block at lines 5-12) [Agent 1 finding]

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- None. `TestPriorityRegexCompletenessAllowlist`, `_ALLOWLIST` and `_PATTERN` are referenced only inside `scripts/tests/test_issue_parser.py`; no other module, conftest, workflow or doc imports or names them. `test_history_store_chokepoint_gate.py::test_allowlist_entries_still_exist_and_still_have_raw_connects` and `test_host_resolution_chokepoint_gate.py::test_allowlist_entries_still_exist_and_still_read` only share a test-name shape, so this change does not touch them [Agent 1 finding]

### Tests
- The two existing tests fold into one exact-comparison test over the real tree (message names both new and stale keys); add three synthetic-source tests: line-shift invariance, extra hit in an allowlisted symbol (new), and removed hit from a count-2 key (stale). See Implementation Steps.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_usage_selection_chokepoint_gate.py` — model for the new helper: `_enclosing_functions(tree)` (line 41) is the only `ast` enclosing-scope resolver in the suite; extend it to `ClassDef` and multi-line `Assign` spans rather than copying it verbatim [Agent 3 finding]
- `scripts/tests/test_host_resolution_chokepoint_gate.py` — `test_gate_detects_a_stray_site` / `test_gate_ignores_non_reads` are the positive/negative regression-test pattern for the new line-shift, new-regex and removed-regex tests (synthetic source string fed to the shared scanner) [Agent 3 finding]
- No existing test breaks: nothing else consumes the `dict[str, dict[int, str]]` shape of `_ALLOWLIST`. Both existing tests are replaced by the single folded test [Agent 3 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- None. No config key, schema entry, CI workflow, loop YAML, hook or doc references this guard, so nothing outside the test file needs to change [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Detection today is a per-physical-line regex (`_PATTERN`), not `ast`; the current allowlist matches the scan exactly (31 hits, 16 files, no drift). Of those 31, 3 are comment lines (`issue_history/parsing.py:53`, `issue_parser.py:4369`, `sync.py:291`), 3 are docstring lines inside multi-line strings (`issue_parser.py:351`, `session_store/writers.py:3175`, `cli/issues/prioritize.py:61`), and 2 sit inside the ~465-line module-level `_TOOLS` literal (`mcp_server/tools.py:848`, `:1006`) where no `def`/`class` encloses them.
- Comments are not `ast` nodes, so anchors for them can only come from line-span resolution over `FunctionDef`/`ClassDef` `lineno..end_lineno`. All 3 current comment entries sit physically inside a function body, so none resolves to `<module>`.
- Same-symbol collisions (superseded by the re-verified list in § Design Decisions, which found six count-2 groups, not three): `cli/issues/search.py` `_parse_priority_filter::P\d` (lines 114, 120); `hooks/post_tool_use.py` `_maybe_auto_commit::P[0-5]` (98, 108); `mcp_server/tools.py` `_TOOLS::P[0-5]` (848, 1006). The `issue_parser.py` module-level assignments (50, 58, 2116) do *not* collide — each is its own assignment target, and no hit falls back to `<module>`. Two of these pairs carry *different* justification strings, so a single key cannot hold both.
- Methods carry class context: `_parse_type_and_id` and `_generate_id_from_filename` (`IssueParser`), `_extract_issue_id` (`GitHubSyncManager`). A leaf-name anchor is ambiguous across classes. **Resolved**: dotted qualified names.
- Line-pinned drift is a long-standing recurring cost: BUG-3448 was a whole issue for `mcp_server/tools.py` drift, and ~20 other issue files record "allowlist line numbers updated for the resulting shift". The class's own maintenance comment ("Re-derive line numbers…") and the ENH-3623 re-measure comment above the `issue_parser.py` entries are line-number-specific and become obsolete with the re-key.
- Origin: BUG-3286 § Tests / Completeness verification (Implementation Step 10) specified the "frozen set of `path:line` entries, each with a one-line reason".

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Convention held across the suite: allowlist guards are a bidirectional pair — a "new un-allowlisted hit fails" test and a "stale entry fails" test (`test_history_store_chokepoint_gate.py`, `test_host_resolution_chokepoint_gate.py`, `test_builtin_loops.py::TestValidatorWarningBudget`, `test_bug3269_test_cmd_resolution_gate.py`); two guards fold both into one exact-set equality with a message naming both diffs (`TestMr11MarkerSet.test_marker_set_matches_enumeration`, `TestInterpSweepBaseline.test_completeness_guard`). Current staleness check here differs: it re-applies `_PATTERN` at a recorded line rather than re-running the scan and diffing.
- Convention held for keying by enclosing scope: the only precedent is `test_usage_selection_chokepoint_gate.py` (`_enclosing_functions`, `_ALLOWLIST: dict[tuple[str, str], str]` keyed `(rel_path, enclosing_function)`, fallback literal `"<module>"`); it resolves `def`/`async def` only, no classes, and has no multiplicity handling. `scripts/little_loops/issues/anchors.py:resolve_anchor` is a regex backwards scan (no `ast`, display-string output) and no test uses it as an allowlist key.
- Convention held for gate-regression tests: feed a synthetic inline source string (or `tmp_path` file) to the same scanner the gate uses, as a positive/negative pair (`test_host_resolution_chokepoint_gate.py::test_gate_detects_a_stray_site`, `::test_gate_ignores_non_reads`; `test_usage_selection_chokepoint_gate.py::test_gate_detects_a_stray_site`). No test in `scripts/tests` copies a real source file such as `session_store/writers.py` and mutates it. **Resolved**: use synthetic source strings, not a temp copy of `writers.py` (see § Design Decisions).
- Helper placement is mixed: `test_issue_parser.py` uses both module-level private helpers (`_parse_issue_frontmatter`, defined above its class) and class `@staticmethod` helpers; standalone gate modules use module-level private functions. The file has no `import ast` today. `TestPriorityRegexCompletenessAllowlist` has no helper methods and both tests duplicate the repo-root/scan setup inline.
- Failure messages in sibling guards tell the contributor what to do ("add a reasoned allowlist entry", "justify here or convert to resolve_priority"); the existing message here also lists new line numbers for manual update, which the re-key removes.

## Scope Boundaries

- **In scope**: re-keying `_ALLOWLIST` in `TestPriorityRegexCompletenessAllowlist` from line numbers to symbol anchors; adapting the two existing tests; adding one line-shift regression test.
- **Out of scope**: changing which raw priority regexes are allowlisted or their justification text; converting any allowlisted regex to `resolve_priority`; the detection pattern `_PATTERN`; other line-number-pinned allowlists elsewhere in the test suite.

## Design Decisions

_Added after an `/ll:advise` second-opinion review (claude-opus-5-5, confidence 0.85) of the original plan. Verified by an `ast` line-span scan of `scripts/little_loops`: 31 matching lines, 25 distinct `(path, qualname)` keys, zero `<module>` fallbacks._

- **Key is `(rel_path, qualname)` → `(count, justification)`; the pattern text is not part of the key.** `_PATTERN` has only two alternatives (`P[0-5]`, `P\\d`), so `::<pattern>` barely narrows the key and raises an unanswerable question for a line matching both. The count handles every collision. Six count-2 groups exist: `cli/issues/search.py::_parse_priority_filter` (114, 120), `hooks/post_tool_use.py::_maybe_auto_commit` (98, 108), `issue_history/parsing.py::parse_completed_issue` (53, 59), `issue_lifecycle.py::skip_issue` (1425, 1432), `issue_parser.py::IssueParser._parse_type_and_id` (4369, 4373), `mcp_server/tools.py::_TOOLS` (848, 1006).
- **Rejected alternatives**: a per-file total plus a symbol set (a new hit in an allowlisted symbol can hide behind a removal elsewhere in the file); ordinal-within-symbol (breaks when code inside the symbol is reordered); keying on stripped line text (breaks on reformatting); inline `# ll-priority-regex-ok:` suppression markers (would edit ~16 production files and let authors self-approve; revisit only if more line-pinned gates start to hurt).
- **Counting unit is matching physical lines, not `findall` matches.** Today's scan does `set.add(lineno)`; `cli/issues/search.py:114` has two `P\d` on one line and must stay count 1.
- **Merged justifications**: for each count-2 key whose halves have different justifications, write one combined string with per-site wording (e.g. "range parser (`P#-P#`); single-value parser") so a reviewer can tell which hit each part approves.
- **Anchor rules** (`_enclosing_symbol`):
  - Recursive visitor builds a dotted name from `ClassDef`/`FunctionDef`/`AsyncFunctionDef`, descending into `if`/`try`/`with` bodies without adding to the name (so defs under `if TYPE_CHECKING:` / `try:` are found; a flat `ast.walk` or top-level-only search loses the parent chain).
  - A def's span runs from its first decorator line (`min(d.lineno for d in decorator_list)`) to `end_lineno`.
  - The innermost span wins (nested def → `outer.inner`). Lambdas and comprehensions are not anchors, so a hit inside a lambda within `_TOOLS = [...]` still resolves to `_TOOLS`.
  - Class-body lines outside any method resolve to the class name.
  - If no def/class contains the line, use the top-level `Assign`/`AnnAssign` whose span contains it, keyed by its first `Name` target; otherwise `"<module>"`.
- **Scan order**: regex over lines first, then `ast.parse` only files with hits (~16 files, not all ~426), then attribute each hit. `SyntaxError` is a hard failure naming the file (all files parse today).
- **One folded comparison** instead of the two-test pair: a single exact comparison with a message showing both new and stale keys, so a hit that moves to another symbol reads as one move ("new X, stale Y"). The failure message prints paste-ready allowlist keys, and says "justify here or convert to `resolve_priority`" in the sibling-guard style.
- **Regression tests use synthetic source strings**, not a temp copy of `session_store/writers.py` (no precedent in the suite).
- **Known residual risks (accepted)**: a comment above a def or after a block's last statement lies outside the def's span and resolves to the enclosing class/`<module>` — moving such a comment re-keys the hit and fails loudly, never silently (the three current comment hits are all inside function bodies); a hit can now move anywhere within its symbol without review — that is the intended trade.

## Program Design

### Types

- `_ALLOWLIST: dict[tuple[str, str], tuple[int, str]]` — `(rel_path, qualname)` -> `(count, justification)`; `rel_path` is relative to `scripts/little_loops`

### Signatures

- `_enclosing_symbol(tree: ast.AST, lineno: int) -> str` — dotted qualname of the innermost enclosing `def`/`class` span (decorators included), else the top-level assignment target, else `"<module>"`
- `_scan_source(rel_path: str, text: str) -> Counter[tuple[str, str]]` — per-`(rel_path, qualname)` count of physical lines matching `_PATTERN`; pure, takes source text so synthetic tests can feed it
- `_scan_priority_regex_hits(src_root: Path) -> Counter[tuple[str, str]]` — runs `_scan_source` over every `*.py` under `src_root`
- `_diff_against_allowlist(found: Counter[tuple[str, str]], allowlist: dict[tuple[str, str], tuple[int, str]]) -> tuple[list[str], list[str]]` — pure; returns `(new, stale)` as paste-ready key strings, where a count mismatch appears in both directions as appropriate

### Call Path

`TestPriorityRegexCompletenessAllowlist.test_priority_regex_allowlist_matches_scan` -> `_scan_priority_regex_hits` -> `_scan_source` -> `_enclosing_symbol`

`TestPriorityRegexCompletenessAllowlist.test_priority_regex_allowlist_matches_scan` -> `_diff_against_allowlist`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Constraint (resolved by § Design Decisions): a set of anchors collapses same-symbol duplicates, so a *new* raw regex added inside an already-allowlisted symbol (e.g. a third `"pattern": "^P[0-5]$"` in `_TOOLS`) would pass silently and removing one of a colliding pair would report nothing. The scan therefore returns a `Counter` keyed `(rel_path, qualname)` and the allowlist carries a per-key count; the count is compared, not just presence.
- Constraint on `_enclosing_symbol` (resolved by § Design Decisions): it must handle module-level assignment targets that span many lines (`_TOOLS`, lines 826–1290) and comment/docstring lines that `ast` never yields as statements — line-span containment against `FunctionDef`/`ClassDef`/`Assign` nodes (decorators included), not per-node `ast.walk` attribution. Nested defs/methods resolve to the innermost containing span.

## Implementation Steps

1. Add `_enclosing_symbol` (recursive visitor per § Design Decisions: dotted qualnames, decorator-inclusive spans, innermost wins, top-level assignment fallback, else `"<module>"`), `_scan_source(rel_path, text)` (counts matching physical lines per `(rel_path, qualname)`; regex first, `ast.parse` only when a file has hits; `SyntaxError` is a hard failure naming the file), and `_scan_priority_regex_hits(src_root)`.
2. Add pure `_diff_against_allowlist(found, allowlist)` returning `(new, stale)` as paste-ready keys.
3. Re-key every `_ALLOWLIST` entry to `(rel_path, qualname): (count, justification)` — 25 keys covering the current 31 lines; merge the two differing justification pairs into one per-site-worded string each (`_parse_priority_filter`, `_maybe_auto_commit`; also check `parse_completed_issue`, `skip_issue`, `_parse_type_and_id`). Replace the two existing tests with one `test_priority_regex_allowlist_matches_scan` asserting both diffs are empty, with a message that prints both and says "justify here or convert to `resolve_priority`".
4. Add three synthetic-source tests (pattern: `test_host_resolution_chokepoint_gate.py::test_gate_detects_a_stray_site`): (a) `_scan_source(src) == _scan_source("\n" * 20 + src)` with a comment hit and a docstring hit in `src`; (b) an extra hit inside an allowlisted symbol produces a `new` entry; (c) removing one hit from a count-2 key produces a `stale` entry. Also cover a same-line double match counting once, a decorated def, and a nested def resolving to `outer.inner`.
5. Run `python -m pytest scripts/tests/test_issue_parser.py -k PriorityRegexCompleteness` and confirm all pass; re-run the standalone scan and confirm it yields 31 lines / 25 keys with no `<module>` hits.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `import ast` to `scripts/tests/test_issue_parser.py` — the module has none today
- Update the `TestPriorityRegexCompletenessAllowlist` class docstring in `scripts/tests/test_issue_parser.py` — replace the `issue_parser.py:272`-ish line reference with the symbol name (`resolve_issue_path`)
- Remove the `# path -> {line: reason}. Re-derive line numbers…` comment and the ENH-3623 "re-measured after 44 lines" comment above the `issue_parser.py` entries — both are line-number-specific and obsolete after the re-key
- Model `_enclosing_symbol` on `_enclosing_functions` in `scripts/tests/test_usage_selection_chokepoint_gate.py`, extended to `ClassDef`, decorator-inclusive spans, dotted qualnames, and multi-line `Assign` spans
- Write the new line-shift, new-regex and removed-regex tests as synthetic-source positive/negative pairs, following `test_host_resolution_chokepoint_gate.py::test_gate_detects_a_stray_site`
- Scope any formatting to the changed file (`ruff format scripts/tests/test_issue_parser.py`) — a bare `ruff format scripts/` reformats unrelated files
- After landing, delete the now-obsolete memory note `reference_writers_line_number_allowlist.md` and its line in `MEMORY.md` (its premise — line-pinned allowlist breaking on `writers.py` edits — disappears)

## Impact

- **Priority**: P4. Test-maintenance friction only.
- **Effort**: Small (~60–90 lines net, test-only).
- **Risk**: Low.

## Acceptance Criteria

- [ ] A synthetic-source test shows `_scan_source(src) == _scan_source("\n" * N + src)` (inserting lines above allowlisted regexes, including a comment hit and a docstring hit, changes nothing); the real-tree gate passes after inserting or deleting lines above the `session_store/writers.py` entries.
- [ ] A newly added raw priority regex outside the allowlist still fails.
- [ ] A second raw priority regex inside an already-allowlisted symbol (count exceeded) still fails.
- [ ] A removed allowlisted regex — including one hit of a count-2 key — still reports a stale entry.
- [ ] A line containing two matches counts once (`cli/issues/search.py` `_parse_priority_filter` stays at count 2 over two lines).
- [ ] The failure message lists new and stale keys as paste-ready allowlist entries, with no line numbers.
- [ ] `SyntaxError` in a scanned file fails the gate and names the file.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-09-29T04:57:37 - `e175d93c-8c73-4377-9a46-bbada6b9c65d.jsonl`
- `/ll:refine-issue` - 2026-09-29T04:55:38 - `4499f980-478f-43ad-ae6e-d08229ebdabd.jsonl`
- `/ll:format-issue` - 2026-09-29T04:50:00 - `d770577e-1f76-4a53-b5c3-a8661dec6288.jsonl`
- `/ll:capture-issue` - 2026-09-29T04:19:25 - `4d45d755-73ff-4de3-8bd1-bb8e866143f2.jsonl`
