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
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
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

This is in scope here because it is the same fix (locate the real heading, ignoring
fenced spans) and because leaving it would leave a comment in the tree actively asserting
a false invariant. It is not covered by any change to `_section_body_with_offset` —
`append_session_log_entry` does its own string scan and never calls it.

Two more spots in the same module share the exposure:

- The fallback branch anchors on `"\n---\n\n## Status"` (`session_log.py:271-274`), though
  `str.replace` takes the *first* match there rather than the last.
- `_SESSION_LOG_RE` (`session_log.py:17-19`),
  `r"^## Session Log\s*\n+(.*?)(?:\n##|\n---|\Z)"`, terminates on the first `\n##` with no
  fence awareness — the same end-boundary defect as `_section_body_with_offset`'s
  terminator scan, on the read side. It backs `parse_session_log`,
  `count_session_commands`, and `last_command_timestamp`.

### Downstream: this is what makes BUG-3193 verdict-inverting

BUG-3193 (`ll-issues create` appends a duplicate empty template scaffold) is cosmetic on
its own — a trailing block of placeholder sections. It becomes verdict-inverting only
because the trailing placeholder copy wins this lookup, so `format-check` grades the
placeholder instead of the real content. Fixing this issue removes BUG-3193's downstream
harm before BUG-3193 itself is touched. The two are independent but compounding, which is
why BUG-3193 carries `depends_on: [BUG-3202]`.

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

Neither is a regression this fix introduces, but both determine whether the fix is
predictable. **Pin the fail-open choice**: an unterminated fence is treated as *not*
fenced (preserving today's behavior for the tail of the document) rather than swallowing
the remainder of the file. Whether to extend the pattern to `~~~` is a separate, smaller
call — decide it explicitly rather than by omission.

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
  change site. `_SESSION_LOG_RE` (`:17-19`) is the read-side counterpart.

### Types

`FormatGaps` (`scripts/little_loops/issue_parser.py:276`) is unchanged — this fix changes
what populates the gap lists, not their shape.

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
  `session_log` sites and one exported helper. Six tests.
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
- [ ] Last-occurrence-wins is preserved for genuine repeated headings
      (`## Confidence Check Notes`).
- [ ] `append_session_log_entry` locates the real `## Session Log` heading, not one quoted
      inside a fence, and its inline comment (`session_log.py:265`) matches the shipped
      behavior. `_SESSION_LOG_RE`'s read-side terminator is fence-aware too, or the issue
      records explicitly why it is left alone.
- [ ] A **single named, exported fence-span helper** exists and is called by
      `_section_body_with_offset`, `append_session_log_entry`, and (later) BUG-3193's
      detector.
      No new fifth idiom.
- [ ] Unterminated-fence behavior is pinned by a test: an odd number of fence markers
      leaves the trailing text treated as unfenced (fail-open), not swallowed.
- [ ] `ll-issues format-check` on BUG-3192, BUG-3193, and BUG-3194 reports no
      `empty:`/`boilerplate:` gap for a section that is in fact written.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Integration Map

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
- New `session_log` test: `append_session_log_entry` on an issue quoting a
  `## Session Log`-shaped line inside a fence lands the entry in the real section.
- `scripts/tests/test_ll_issues_format_check.py::test_clean_issue_json_output`
  (lines 302-362) — exact-dict-equality fixture over all `FormatGaps` keys; unaffected by
  this fix (no key or shape change), confirmed.

### Documentation

- `docs/reference/API.md` (`#### check_format_gaps` prose block) — the
  `stale_symbol_ref`/`mislocated_symbol_ref` bullets say "matched by H2 span — BUG-3063
  A1" with no fence-awareness caveat; update.
- `scripts/little_loops/issue_parser.py:943-949` — the `_STALE_SYMBOL_SCOPE_H2_SECTIONS`
  allowlist comment asserts the pre-fix, fence-unaware framing; update alongside.
- `scripts/little_loops/session_log.py:265` — the inline comment asserting "real section,
  not a fake in code block" must become true or be corrected.

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

## Status

**Open** | Created: 2026-08-15 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-08-15T20:37:36 - `3bed080b-17e6-4060-904f-398efef7735c.jsonl`
