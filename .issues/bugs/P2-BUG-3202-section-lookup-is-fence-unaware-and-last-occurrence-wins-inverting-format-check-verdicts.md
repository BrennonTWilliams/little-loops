---
id: BUG-3202
type: BUG
title: Section lookup is fence-unaware and last-occurrence-wins, inverting format-check
  verdicts
priority: P2
status: open
testable: true
decision_needed: false
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T20:08:15Z'
supersedes: []
confidence_score: 100
outcome_confidence: 61
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
verify_verdict: VALID
---

# BUG-3202: Section lookup is fence-unaware and last-occurrence-wins, inverting format-check verdicts

## Summary

Split out of BUG-3194 (2026-08-15), which filed four `format-check` findings together.
This was that issue's **Finding 4**. It is the only one of the four that *inverts* a
verdict rather than adding noise, and it is the one BUG-3193 actually depends on — so it
is promoted to its own P2 and BUG-3194 keeps Findings 1/2/3 (symbol-index and file-ref
noise) at P3.

`_section_body_with_offset` (`scripts/little_loops/issue_parser.py:239`) resolves a
section heading with a fence-unaware regex and takes the **last** match. Any issue body
that *quotes* markdown containing a `##`-shaped line — routine for issues about issue
formatting, templates, or docs — has that quoted heading silently override its real
section, and separately truncates whichever section encloses the fence. `format-check`
then reports `empty:` and `boilerplate:` for sections that are fully written.

This is not advisory output: `format-check` gates `/ll:confidence-check`,
`/ll:ready-issue`, `/ll:refine-issue`, `/ll:wire-issue`, and `/ll:format-issue`. A false
`empty:`/`boilerplate:` points `format-issue` at rewriting sections that are already
correct.

A second instance of the same mechanism lives in `session_log.py` (see Current Behavior
§ "Second site"), where the in-code comment asserts the fence-awareness the code does not
have.

> **Note for anyone running `format-check` on this issue.** Every quoted markdown heading
> in this file is written with a `>>` prefix rather than a literal `## `, specifically to
> avoid reproducing this bug on the issue that documents it. Do not "clean up" those
> prefixes until this issue is fixed.

## Current Behavior

`_section_body_with_offset` (`scripts/little_loops/issue_parser.py:239`) resolves a
section with

```python
pattern = rf"^##\s+{re.escape(heading)}\s*$"
matches = list(re.finditer(pattern, content, re.MULTILINE))
match = matches[-1]
start = match.end()
next_match = re.search(r"^##\s", content[start:], re.MULTILINE)
```

Three properties combine badly:

- **No fence awareness.** A `## Summary`-shaped line inside a fenced code block is
  indistinguishable from a real heading. Nothing in this function or its callers strips
  fences first.
- **Last occurrence wins** — a deliberate contract (docstring at `:245-248`, to support
  repeatedly-appended `## Confidence Check Notes`), which is load-bearing and must be
  preserved for *genuine* repeats.
- **The end-boundary scan is separately fence-unaware.** The `re.search(r"^##\s", ...)`
  terminator pick (`issue_parser.py:259`) uses the same fence-blind pattern.

Demonstrated on the first draft of BUG-3193, whose Current Behavior section quotes a
rendered template:

```
$ ll-issues format-check 3193
  empty: Summary
  boilerplate: Current Behavior
```

Both false: Summary was written and Current Behavior was several paragraphs. The quoted
block won.

### Second symptom: the enclosing section is truncated

The fence-blind end-boundary scan is a distinct failure from "the quoted heading wins",
and it fires more often. Measured against a synthetic body whose `Current Behavior`
section contains a fenced block quoting a `Summary` heading (headings shown with a `>>`
prefix here so this issue does not reproduce the bug on itself):

```
content:
  >> ## Summary            (real)
  >> Real summary.
  >> ## Current Behavior   (real)
  >> Prose before the fence.
  >> ```
  >> ## Summary            (quoted, inside the fence)
  >> placeholder junk
  >> ```
  >> More prose after the fence.
  >> ## Impact             (real)

_section_body(content, "Current Behavior")
  -> '\nProse before the fence.\n\n```\n'          <-- truncated at the fence

_section_body(content, "Summary")
  -> '\nplaceholder junk\n```\n\nMore prose after the fence.\n\n'
```

The second line is the which-heading-wins symptom. The first is separate and wider:
`Current Behavior` is cut off at the opening fence, because the quoted heading terminates
it. This fires **even when the quoted heading is not itself a checked section** — any
fenced `##`-shaped line truncates whatever section encloses it, and short-truncated
sections are what `boilerplate:` and `empty:` actually grade.

Both halves are fixed by the same fence-aware pass, but a fix that only disambiguates
*which* heading match wins, without also making the terminator scan fence-aware, leaves
this half firing.

### Second site: `append_session_log_entry` has the same defect, with a comment claiming otherwise

Found during the 2026-08-15 review of the BUG-3192/3193/3194 set. Not part of the
original Finding 4 write-up, same mechanism, different module
(`append_session_log_entry`, `scripts/little_loops/session_log.py:264-266`):

```python
if "## Session Log" in content:
    # Insert entry after the last ## Session Log header (real section, not a fake in code block)
    idx = content.rfind("## Session Log\n")
```

The comment asserts a property the code does not have: `rfind` is exactly the
fence-unaware last-occurrence-wins pattern. An issue whose body quotes a
`## Session Log`-shaped line inside a fence gets its session entries **injected into the
code block** rather than into the real section.

The `rfind` is also not line-anchored: `"## Session Log\n"` is a substring of an
`### Session Log` H3 line, so an H3 of the same name matches too. The fence-aware rewrite
should anchor the heading at line start (`^## Session Log$`), which fixes this for free —
do not faithfully reproduce the substring match.

This is in scope here because it is the same fix (locate the real heading, ignoring
fenced spans) and because leaving it would leave a comment in the tree actively asserting
a false invariant. It is not covered by any change to `_section_body_with_offset` —
`append_session_log_entry` does its own string scan and never calls it.

Two more spots in the same module share the exposure:

- The fallback branch anchors on `"\n---\n\n## Status"` (`session_log.py:271-274`), though
  `str.replace` takes the *first* match there rather than the last.
- `_SESSION_LOG_SECTION_RE` (`session_log.py:17-19`),
  `r"^## Session Log\s*\n+(.*?)(?:\n##|\n---|\Z)"`, terminates on the first `\n##` with no
  fence awareness — the same end-boundary defect as `_section_body_with_offset`'s
  terminator scan, on the read side. Its `\n---` alternative is equally fence-blind, and
  fenced YAML frontmatter examples containing `---` lines are routine in this repo's
  issue bodies — if the `\n##` half is made fence-aware, the `---` half must be too (or
  the same left-alone rationale covers both). It backs `parse_session_log`,
  `count_session_commands`, and `last_command_timestamp`.

### Downstream: relationship to BUG-3193 — two distinct inversion classes

BUG-3193 (`ll-issues create` appends a duplicate empty template scaffold) also inverts
`format-check` verdicts, but through a **different mechanism**: its appended scaffold
consists of *real, unfenced* placeholder headings landing last in the file, and
last-occurrence-wins — which this fix deliberately preserves — picks the placeholder.
**This fix does not remove that harm.** Fence-awareness rescues only the
quoted-inside-a-fence class; BUG-3193's victim files keep their inverted verdicts until
BUG-3193 itself lands. (BUG-3193's *own issue file* will grade clean after this fix,
because its duplicate headings sit inside a fenced heredoc — do not mistake that for the
victim-file class being fixed.)

The `depends_on: [BUG-3202]` edge on BUG-3193 holds for the helper, not the harm:
BUG-3193's full-body detector must call the fence-span helper this issue exports rather
than adding a fifth idiom.

## Steps to Reproduce

Write any issue whose body quotes a markdown block containing a `## Summary`-shaped line
inside a code fence, then:

```bash
ll-issues format-check <id>
```

It reports `empty: Summary` even though the real Summary is written, because the fenced
heading is the last match.

For the truncation half, use the synthetic body in Current Behavior § "Second symptom" and
call `_section_body` directly:

```bash
python -c "
from little_loops.issue_parser import _section_body
body = open('/tmp/synthetic.md').read()
print(repr(_section_body(body, 'Current Behavior')))
"
```

For the `session_log` site, append a session entry to an issue whose body quotes a
`## Session Log`-shaped line inside a fence and observe the entry landing inside the
fence.

## Program Design

Change site is `_section_body_with_offset` (`scripts/little_loops/issue_parser.py:239`).
Fence-stripping goes there so every section-resolving caller inherits the fix, plus the
independent scan in `append_session_log_entry`.

### Signatures

```python
def _section_body_with_offset(content: str, heading: str) -> tuple[str, int] | None
def _section_body(content: str, heading: str) -> str | None
def append_session_log_entry(...) -> bool  # session_log.py:227
```

### Implementation constraint — the returned body must be sliced from the original content

`_section_body_with_offset` returns `(body, start_offset)` where *body* is a slice of the
input. If the fix blanks fences and then slices the *blanked* text, every section whose
content is predominantly a code block comes back near-empty, and `check_format_gaps`
reports `empty:` on it — trading one systematic false positive for another, on exactly the
issue-about-tooling bodies this fix is meant to rescue.

Use the fence-blanked text **only to locate the heading offset and the terminator
offset**, then slice `content` (the original) at those offsets.

### Deliverable: one shared fence-span helper, exported

There are already four non-interchangeable fence idioms in the tree, and BUG-3193's
full-body detector will need a fifth unless this fix exports one:

| Idiom | Location | Offset behavior |
|---|---|---|
| `_CODE_FENCE` + `_in_fence(start, end, spans)` span-exclusion | `text_utils.py:25`, reimplemented in `issues/symbol_claims.py:102-103` and `issues/prose_deps.py` | preserves offsets |
| `_CODE_FENCE` duplicate literal | `dependency_mapper/analysis.py:28` | preserves offsets |
| `IssueParser._strip_code_fences` line-blanking | `issue_parser.py:2369-2392` | preserves offsets and line numbers |
| `text_utils.strip_code_fences` | `text_utils.py:58-65` | **shifts offsets** — unusable here |

Only the first three are offset-preserving and therefore compatible with
`_section_body_with_offset`'s `(body, start_offset)` contract.

**This fix must land a single named, exported fence-span helper** (natural home:
`text_utils`, alongside the existing `_CODE_FENCE`) that `_section_body_with_offset`,
`append_session_log_entry`, and BUG-3193's detector all call. Without that as an explicit
deliverable, BUG-3193 adds a fifth idiom. Collapsing the existing duplicates
(`dependency_mapper/analysis.py:28`, `symbol_claims.py:102`, `prose_deps.py`) onto it is
optional and can follow.

### Unterminated and non-backtick fences — pin the behavior

`_CODE_FENCE` is `re.compile(r"```[\s\S]*?```", re.MULTILINE)`. Two shapes fall outside
it, and issue bodies are hand-authored so both will occur:

- **`~~~` fences** are not matched at all.
- **An odd number of fence markers** leaves the trailing block unmatched, so everything
  after the last unpaired fence is treated as unfenced.
- **Delimiters are not line-anchored.** `_CODE_FENCE` has no `^` anchor, so an inline
  mention of three backticks in prose pairs with the next real fence opener and inverts
  fenced/unfenced classification for the rest of the document. Markdown-correct fence
  delimiters are line-start-anchored; the new exported helper can anchor its own regex
  (recommended) without touching `_CODE_FENCE`'s existing consumers.

None of these is a regression this fix introduces, but all three determine whether the
fix is predictable. **Pin the fail-open choice**: an unterminated fence is treated as
*not* fenced (preserving today's behavior for the tail of the document) rather than
swallowing the remainder of the file. **Pin the anchoring choice** by a test either way.
Whether to extend the pattern to `~~~` is a separate, smaller call — decide it explicitly
rather than by omission.

### Call Path

- `cmd_format_check` → `check_format_gaps` → `_section_body` → `_section_body_with_offset`
  — the primary gated path.
- `_symbol_claim_scope_text()` (`issue_parser.py:952-959`, feeds
  `stale_symbol_ref`/`mislocated_symbol_ref`) and `_behavior_parity_scope_text()`
  (`:930-940`, feeds `missing_behavior_parity`) both concatenate sections via the same
  fence-unaware `_section_body`, so this fix affects those gap classes too.
- `locate_enumerable_options` / `_locate_directive_alternatives` /
  `count_enumerable_options` (`issue_parser.py:1251,1319,1328`) — consumed by
  `cli/issues/check_decidable.py`, `cli/issues/locate_options.py`, and
  `issues/fold_research_findings.py`. Option-counting/location behavior changes for any
  issue whose `## Proposed Solution` quotes a fenced block containing `##`-shaped lines.
- Direct `_section_body` importers beyond `format-check`:
  `cli/issues/normalize.py:195,205`, `cli/issues/check_acceptance_criteria.py:59,61`,
  `cli/issues/size.py:82,85`.
- `check_format_gaps` consumers beyond the five named skills:
  `cli/issues/check_design.py:31,38` and `cli/issues/sequence.py:18`.
- `append_session_log_entry` (`session_log.py:227,264-274`) — independent scan, second
  change site. `_SESSION_LOG_SECTION_RE` (`:17-19`) is the read-side counterpart.

### Types

`FormatGaps` (`scripts/little_loops/issue_parser.py:276`) is unchanged — this fix changes
what populates the gap lists, not their shape.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- `_in_fence(start, end, spans)` is already reimplemented identically twice: `any(fs <= start and end <= fe for fs, fe in fence_spans)` (`scripts/little_loops/issues/symbol_claims.py:151-152`, `scripts/little_loops/issues/prose_deps.py:83-84`). Contract: takes a match's `(start, end)` in **original-content offsets** plus a `list[tuple[int, int]]` of fence spans built once per call via `_CODE_FENCE.finditer(body)` against the original string (`symbol_claims.py:198`, `prose_deps.py:109-110`); callers skip a match when `_in_fence(...)` is True and slice from the original string. This is the closest existing model for the shared fence-span helper this fix must export.
- `_CODE_FENCE` (`text_utils.py:25`) is already imported directly (not redefined) by `symbol_claims.py:23` and `prose_deps.py:19`, and locally imported inline at `issue_parser.py:710` — collapsing the `dependency_mapper/analysis.py:28` duplicate literal onto the shared import follows an established pattern, not a new one.
- `IssueParser._strip_code_fences` (`issue_parser.py:2369-2392`) is line-based (splits on `\n`, blanks fence-delimiter and fenced-content lines), preserving line count but not per-line character offsets, and is a private method on `IssueParser` — not callable as a free function from the module-level `_section_body_with_offset`.
- `text_utils.strip_code_fences` (`text_utils.py:58-65`) is the one existing public, module-level helper with no leading underscore; codebase convention for exporting a cross-module helper in this file is: no leading underscore, module-level function, docstring stating the reuse rationale. No `__all__` in the file — visibility is by naming convention only.

## Expected Behavior

Strip (or exclude) fenced code blocks before resolving section headings, for **both** the
heading match and the end-boundary scan. Keep the last-occurrence-wins contract for real
headings — it is load-bearing for `## Confidence Check Notes` — and only exclude fenced
matches.

Same treatment for `append_session_log_entry`'s `rfind`, and correct its comment either way.

## Impact

- **Priority**: P2 — inverts a gate's verdict rather than adding noise. `format-check`
  gates `/ll:confidence-check`, `/ll:ready-issue`, `/ll:refine-issue`, `/ll:wire-issue`,
  and `/ll:format-issue`; a false `empty:`/`boilerplate:` points `format-issue` at
  rewriting correct sections. Promoted from BUG-3194's P3 bundle, where it would have been
  scheduled as noise alongside three cosmetic findings.
- **Effort**: Small — a fence-aware offset lookup reusing existing machinery, plus the
  `session_log` sites, the `search.py` regex swap, and one exported helper. Seven tests.
- **Risk**: Low — narrows what is reported. The stated risks are (a) returning
  fence-blanked text instead of a slice of the original, which trades one false positive
  for another, and (b) losing last-occurrence-wins for genuine repeats.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] A `##`-shaped line inside a fenced code block does not win section resolution over a
      real heading of the same name — `_section_body_with_offset` returns the real one.
- [ ] A fenced `##`-shaped line does not terminate the section that encloses it: the
      enclosing section's body extends past the fence to the next *real* heading.
- [ ] The returned body is sliced from the original content, not from fence-blanked text —
      a section whose content is entirely a code fence is not reported `empty:`.
- [ ] A heading that appears **only** inside fences resolves as absent —
      `_section_body_with_offset` returns None and `check_format_gaps` reports `missing:`,
      not `empty:` — pinned by a test (a behavior change from today, where the fenced copy
      was graded).
- [ ] Last-occurrence-wins is preserved for genuine repeated headings
      (`## Confidence Check Notes`).
- [ ] `append_session_log_entry` locates the real `## Session Log` heading — line-anchored,
      so an `### Session Log` H3 no longer substring-matches — not one quoted inside a
      fence, and its inline comment (`session_log.py:265`) matches the shipped behavior.
      `_SESSION_LOG_SECTION_RE`'s read-side terminator is fence-aware too — **both** the
      `\n##` and `\n---` alternatives (fenced YAML frontmatter examples containing `---`
      are routine) — or the issue records explicitly why it is left alone.
- [ ] A **single named, exported fence-span helper** exists and is called by
      `_section_body_with_offset`, `append_session_log_entry`, and (later) BUG-3193's
      detector.
      No new fifth idiom.
- [ ] Unterminated-fence behavior is pinned by a test: an odd number of fence markers
      leaves the trailing text treated as unfenced (fail-open), not swallowed. The
      delimiter-anchoring choice (line-start-anchored vs `_CODE_FENCE`'s unanchored
      semantics) is likewise pinned by a test.
- [ ] `cli/issues/search.py`'s local duplicate of the session-log terminator regex
      (`:60-87`) is made fence-aware via the shared helper (or replaced with an import of
      the fence-aware `session_log` counterpart) — no surviving fence-blind copy of that
      regex.
- [ ] A follow-up ENH is filed for `research_triage.py:124-137` `_section_text` (an
      independent third reimplementation of the same fence-unaware lookup, deliberately
      out of scope here to contain blast radius) before this issue is closed, and its ID
      recorded here.
- [ ] `ll-issues format-check` on BUG-3192, BUG-3193, and BUG-3194 reports no
      `empty:`/`boilerplate:` gap for a section that is in fact written.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/set_flags.py:263,273` — `_section_body(content, "Confidence Check Notes")`. This is the exact load-bearing last-occurrence-wins case this issue's Current Behavior/AC names by section title; not previously listed in Call Path.
- `scripts/little_loops/cli/issues/append_log.py:26` — `ll-issues append-log` CLI command calls `append_session_log_entry` directly.
- `scripts/little_loops/issue_lifecycle.py:1137` — `ll-auto` completion path calls `append_session_log_entry`.
- `scripts/little_loops/parallel/orchestrator.py:1807` — `ll-parallel` completion path calls `append_session_log_entry`.
- `hooks/scripts/issue-completion-log.sh:70` (registered via `hooks/hooks.json:137` `PostToolUse`) — shells out and calls `append_session_log_entry` when an issue is written with `status: done`.
- `scripts/little_loops/mcp_server/tools.py:467` (`_tool_issue_append_log`) — MCP mutation tool wraps `append_session_log_entry`.
  All five call sites above benefit from the fix (entries stop landing inside fenced blocks) but require no code change themselves.
- `scripts/little_loops/cli/issues/search.py:60-87` — defines its own local, character-for-character duplicate of the session-log terminator regex (`_SESSION_LOG_RE`, used with `.search()`/first-match rather than `session_log.py`'s `finditer`/last-match) to back `ll-issues search`'s last-activity-date sort. It is **not** an import of `session_log.py`. **Pulled into scope by the 2026-08-15 pre-implementation review**: swap it onto the shared fence-span helper (or an import of the fence-aware `session_log` counterpart) so the no-surviving-old-idiom deliverable isn't undercut the day it lands. See the dedicated AC bullet.
- `scripts/little_loops/issues/research_triage.py:124-137` (`_section_text`) — an independent third reimplementation of the same fence-unaware, last-occurrence-wins heading-resolution pattern found in `_section_body_with_offset` (same regex shape, same `matches[-1]` pick, same fence-blind terminator scan), followed by a call to the offset-shifting `text_utils.strip_code_fences` variant this issue's Deliverable table already flags as unusable for this purpose. Not one of the four fence idioms cataloged in "Deliverable: one shared fence-span helper" — an undocumented occurrence of the same defect class, outside this issue's stated file list. Backs `triage_research_axes`'s `_axis_refs` (`:157-168`). **Deliberately left out of scope to contain blast radius — file a follow-up ENH for it before closing this issue** (see the dedicated AC bullet).
- `scripts/little_loops/issues/research_triage.py:322-354` (`_program_design_unmet`) — calls `issue_parser._section_body` specifically *because* it must not strip fences (own comment at `:343-346` states this explicitly: fence-stripping would read a correctly-designed fenced Program Design section as empty and re-spawn the analyzer agent forever). This is a concrete, already-tested production instance of this issue's own "Implementation constraint" section — regression-tested by `scripts/tests/test_research_triage.py:434-441` `test_gate_active_specific_fenced_section_leaves_analyzer_covered`.
- `scripts/little_loops/cli/issues/show.py:358-366` — uses `count_session_commands`/`parse_session_log` (session_log.py read-side helpers) to render `/ll:*` command counts in `ll-issues show`. Post-fix, counts will change (correctly) for issues whose body fence-quotes a `## Session Log`-shaped line.
- `scripts/little_loops/issues/research_triage.py:46,299` — uses `last_command_timestamp` for refine-staleness detection (`triage_research_axes`). Post-fix, the staleness verdict may change for issues whose body fence-quotes a `## Session Log`-shaped line, since a phantom timestamp is no longer picked up.

### Tests

- `scripts/tests/test_issue_parser.py::test_with_offset_returns_start_of_last_match`
  (~4352-4363) — shows the direct-import call shape
  (`from little_loops.issue_parser import _section_body_with_offset`) to reuse. New tests:
  a fenced `## Summary`-shaped line plus a real one, asserting the real one wins; a
  companion confirming last-occurrence-wins for genuine un-fenced repeats
  (`## Confidence Check Notes`).
- A third test: a section whose body is entirely a fenced code block must not be reported
  `empty:` — this is what catches a fix returning the fence-blanked body instead of
  slicing the original.
- A fourth: the *enclosing* section is not truncated at a fenced `##`-shaped line (the
  end-boundary half), separate from the which-heading-wins assertion.
- A fifth: the unterminated-fence fail-open case.
- A sixth: a heading that appears *only* inside fences returns None — graded `missing:`,
  not `empty:`.
- New `session_log` test: `append_session_log_entry` on an issue quoting a
  `## Session Log`-shaped line inside a fence lands the entry in the real section.
- `scripts/tests/test_ll_issues_format_check.py::test_clean_issue_json_output`
  (lines 302-362) — exact-dict-equality fixture over all `FormatGaps` keys; unaffected by
  this fix (no key or shape change), confirmed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_text_utils.py` — no existing test class covers `strip_code_fences`/`_CODE_FENCE`; the file's convention (one `Test*` class per function) is the natural home for a new class testing the new exported fence-span helper.
- `scripts/tests/test_session_log.py::TestSessionLogHostAware::test_ignores_fake_session_log_heading_in_code_block`
  (~line 318) — currently documents/asserts the *old* last-match-wins strategy as correct for a fixture where the fake fenced heading happens to precede the real section (passes by fixture-ordering coincidence, not fence-awareness). Review and reword its rationale comment once the read-side terminator's fence-awareness status is decided (see `_SESSION_LOG_SECTION_RE` AC bullet).
- `scripts/tests/test_research_triage.py:434-441` `test_gate_active_specific_fenced_section_leaves_analyzer_covered` — existing regression test protecting `_program_design_unmet`'s reliance on `_section_body` not stripping fences (see Dependent Files entry above). Must continue passing after the fix; direct check of this issue's own "Implementation constraint" section.
- Confirmed: no existing `scripts/tests/test_ll_issues_format_check.py` fixture or `scripts/tests/fixtures/issues/*.md` file (other than `feature-with-code-fence.md`, parser-level not format-check) quotes a fenced markdown heading — the new fence-aware end-to-end fixture this issue's AC calls for is genuinely net-new coverage, not an update to existing fixtures.

### Documentation

- `docs/reference/API.md` (`#### check_format_gaps` prose block) — the
  `stale_symbol_ref`/`mislocated_symbol_ref` bullets say "matched by H2 span — BUG-3063
  A1" with no fence-awareness caveat; update.
- `scripts/little_loops/issue_parser.py:943-949` — the `_STALE_SYMBOL_SCOPE_H2_SECTIONS`
  allowlist comment asserts the pre-fix, fence-unaware framing; update alongside.
- `scripts/little_loops/session_log.py:265` — the inline comment asserting "real section,
  not a fake in code block" must become true or be corrected.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- Existing fence-exclusion test convention (`scripts/tests/test_symbol_claims.py:99-101` `test_no_claim_inside_fenced_code_block`, `scripts/tests/test_prose_deps.py:87,100`) uses a minimal inline triple-backtick string fixture for unit-level fence assertions.
- `scripts/tests/test_issue_parser.py:1731` `test_parse_skips_code_fenced_sections` uses a dedicated fixture file (`scripts/tests/fixtures/issues/feature-with-code-fence.md`) for parser-level/integration fence tests — the new tests this issue calls for can follow either pattern depending on whether they exercise `_section_body_with_offset` directly (inline string) or the full parse path.
- The existing last-occurrence-wins regression tests live in `scripts/tests/test_issue_parser.py:4318-4363`, class `TestSectionBodyLastMatchWins` (BUG-2985): `test_returns_last_occurrence_of_stacked_heading`, `test_single_occurrence_unaffected`, `test_with_offset_returns_start_of_last_match` — the new fence-aware tests should live alongside this class since they extend the same contract.

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py:239-258`
- **Cause**: `_section_body_with_offset` was written against the assumption that `^##\s`
  lines in an issue body are headings. That holds for ordinary issues and fails for issues
  *about* markdown tooling, which quote template and rendered-output fragments. The
  last-occurrence-wins contract (added deliberately for repeatedly-appended
  `## Confidence Check Notes`) makes the failure mode "the quoted copy wins" rather than
  "the real one wins", and the independently fence-blind terminator scan truncates the
  enclosing section even when no heading collision occurs.
- **Second site**: `append_session_log_entry` (`scripts/little_loops/session_log.py:266`)
  reimplements the same last-match scan with `str.rfind` and documents at `:265` the
  fence-awareness it lacks.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-issues format-check` gap-class list.
- `docs/reference/API.md` — `check_format_gaps` prose.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-15_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 61/100 → MODERATE

### Outcome Risk Factors
- Very wide blast radius on Change Surface (0/25): the Integration Map enumerates 20+ distinct
  consumers of the affected lookups (`check_format_gaps`'s five gated skills plus
  `check_design.py`/`sequence.py`, direct `_section_body` importers, the
  `locate_enumerable_options` family, five `append_session_log_entry` call sites,
  `symbol_claim_scope_text`/`behavior_parity_scope_text`, `research_triage.py`'s two
  independent sites, and `show.py`'s session-log readers). Mitigation: the issue's own test
  plan is unusually thorough (six new tests plus the existing
  `test_gate_active_specific_fenced_section_leaves_analyzer_covered` regression that already
  guards the one site that must *not* change), and the final AC bullet requires
  `python -m pytest scripts/tests/` to exit 0 — lean on that full-suite run rather than manual
  spot-checks across the fanout.

## Status

**Open** | Created: 2026-08-15 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-08-15T22:42:21 - `5b787d7c-ce7f-4c39-846b-91ffb9301e56.jsonl`
- `/ll:confidence-check` - 2026-08-15T22:28:40 - `bc89bcc0-eb97-47e0-8163-6068b7178c7a.jsonl`
- `/ll:verify-issues` - 2026-08-15T22:26:09 - `1eb905c7-fbac-4cdc-aee9-c9a14060af93.jsonl`
- `/ll:wire-issue` - 2026-08-15T22:22:42 - `c12d529f-8109-4b47-835e-094d7c7e814f.jsonl`
- `/ll:refine-issue` - 2026-08-15T22:15:16 - `9542590b-ca48-47d6-ae7d-b40a1732dc40.jsonl`
- `/ll:confidence-check` - 2026-08-15T20:37:36 - `3bed080b-17e6-4060-904f-398efef7735c.jsonl`
