---
id: ENH-3555
type: ENH
title: format-check flags invisible and control characters in issue bodies
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:27:36Z'
labels:
- issues
- tooling
---

# ENH-3555: format-check flags invisible and control characters in issue bodies

## Summary

`ll-issues format-check` should flag invisible and control characters in issue files: U+2028 LINE SEPARATOR, U+2029 PARAGRAPH SEPARATOR, zero-width characters (U+200B, U+200C, U+200D, U+2060, and U+FEFF anywhere but offset 0), bidirectional controls (U+202A–U+202E, U+2066–U+2069), U+00AD SOFT HYPHEN, DEL (U+007F), C1 controls (U+0080–U+009F), and C0 control characters other than tab, LF and CR. These never belong in an issue file, and they are the one visible trace of a silent corruption that has already broken a spec once.

## Current Behavior

ENH-3540's `script_json` rule needed the literal text of six-character JSON unicode escapes (backslash, `u`, four hex digits). Every committed revision of that file instead held the decoded characters, so the rule read as identity mappings ("replace `<` with `<`") and contained raw U+2028/U+2029 bytes. A manual "repair" recorded in its Session Log never landed. Nothing flagged it; it was found only by reading the raw bytes.

The most likely cause is upstream of little-loops: tool-call arguments are JSON, so a model that writes a backslash-u sequence in an Edit/Write argument has it decoded by the JSON parser before it reaches the file. Any agent editing issue text can hit this. `format-check` (`check_format_gaps` in `scripts/little_loops/issue_parser.py`, CLI in `scripts/little_loops/cli/issues/format_check.py`) has no check for it.

## Expected Behavior

- `check_format_gaps` reports a new gap class (e.g. `invisible_chars`) listing each offending character by code point and line number.
- `ll-issues format-check` exits non-zero on it, like the other structural gaps. The class is **blocking**: it is not added to `_ADVISORY_GAP_CLASSES` (`issue_parser.py:515`), and it is rendered in `format_check.py`'s report (a class counted by `has_gaps` but not rendered exits 1 with an empty report; see the comment at `format_check.py:435`).
- The report names the code point in words (e.g. `U+2028 LINE SEPARATOR at line 291`), never by reproducing the character. `unicodedata.name()` raises `ValueError` for C0/C1 controls and DEL (they have no name), so the scan needs a fallback: the control-code alias (`NULL`, `UNIT SEPARATOR`, …) from a small table, or `<control>` plus the code point.
- The scan covers the whole file, frontmatter included (a `title:` can carry these too). Only a U+FEFF at offset 0 is exempt.

## Motivation

The corruption is silent, invisible in most renderers, and turns a precise spec into a wrong one. A cheap deterministic check catches it at the gate every refined issue already passes through.

## Proposed Solution

Add a scan over the whole issue file in `check_format_gaps`: flag U+2028, U+2029, U+200B, U+200C, U+200D, U+2060, U+FEFF (except at offset 0), U+202A–U+202E, U+2066–U+2069, U+00AD, U+007F, U+0080–U+009F, and code points below U+0020 other than tab, LF, and CR. The bidi controls are the strongest case: they can reorder how text renders without changing what a parser reads (the "Trojan Source" class). Add the new field to `FormatGaps` and its serialized/rendered output, and a report-only gap with no auto-fix (removal is not always the right fix, since the intended text was an escape sequence). Optionally add a CONTRIBUTING note: write escape sequences in specs out in words or as hex-digit tables, never as literal backslash-u text.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `check_format_gaps` gains the scan; `FormatGaps` gains an `invisible_chars` field and its serialized/rendered output.
- `scripts/little_loops/cli/issues/format_check.py` — report lines and exit code for the new gap class.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_design.py` — consumes `format-check --format json` output; confirm the new key does not break it.

### Existing Offenders (must be cleaned in this issue)
A scan on 2026-09-24 over `.issues/` with the widened character set finds these. Each must be replaced with the intended visible text: a spelled-out escape, or deleted when it is stray.
- `.issues/features/P3-FEAT-2390-policy-rubric-loop-emit-and-validate-core.md:562` — U+0000 NULL (the sentence is *about* a NUL byte and contains a literal one).
- `.issues/enhancements/P1-ENH-2939-delete-session-log-hunting-prose.md:100`, `:102`, `:106`, `:108` — U+200B ZERO WIDTH SPACE.
- `.issues/enhancements/P3-ENH-2507-persist-context-pressure-measurements-into-history-db.md:180` — U+001F UNIT SEPARATOR.
- `.issues/enhancements/P3-ENH-2495-record-session-lifecycle-handoff-events.md:1081` — U+001F UNIT SEPARATOR (inside a `join(…)` code example).
- `.issues/enhancements/P2-ENH-2746-f3-compaction-shrink-ratio-outside-gate-band.md:44` — U+00AD SOFT HYPHEN.

The ones checked (FEAT-2390, ENH-2939, ENH-2507, ENH-2495) are `done`; cleaning them is a text-only edit. Re-run the scan at implementation time, since new offenders may have landed.

### Similar Patterns
- Existing report-only gap classes in `FormatGaps` (e.g. `template_placeholders`, which reports "no --fix, needs content").

### Tests
- `scripts/tests/test_issue_parser.py` — per-character detection, allowed characters (tab, LF, CR, leading BOM) not flagged.
- `scripts/tests/test_ll_issues_format_check.py` — CLI report text and non-zero exit.

### Documentation
- `docs/reference/CLI.md` — list the new gap class under `ll-issues format-check`.
- `CONTRIBUTING.md` — optional note on spelling escape sequences out in words in specs.

### Configuration
- N/A

## Program Design

### Types
- `FormatGaps.invisible_chars: list[str]` (new field, `issue_parser.py:521` class) — one entry per offending character, formatted as code point name plus line number.

### Signatures
- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None, symbol_index: SymbolIndex | None = None, cli_index: CliSurfaceIndex | None = None) -> FormatGaps` (existing, `issue_parser.py:684`) — adds the body scan.
- `cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int` (existing, `format_check.py:517`) — reports the new gap class and exits non-zero.

### Call Path
`cmd_format_check` -> `check_format_gaps` -> `FormatGaps`

### Decision Rules
- Flag U+2028, U+2029, U+200B, U+200C, U+200D, U+2060; U+FEFF except at offset 0; U+202A–U+202E and U+2066–U+2069; U+00AD; U+007F; U+0080–U+009F; code points below U+0020 other than tab, LF, CR.
- Scan the whole file, frontmatter included.
- Report the code point by name, never by reproducing the character; fall back to a control-alias table where `unicodedata.name()` has no name.
- Blocking, not advisory.

## Implementation Steps

1. Add the scan to `check_format_gaps` and the `invisible_chars` field to `FormatGaps` (plus `has_gaps` and `to_dict`), reporting code point name and line number, with the control-name fallback.
2. Surface it in `ll-issues format-check` output (text and JSON) with a non-zero exit.
3. Clean the existing offenders listed under Existing Offenders.
4. Verify: unit tests per character class and allowed character (including a nameless control), a CLI test, and a clean run over the current `.issues/` tree.

## Impact

- **Priority**: P4 — guard against a rare, upstream-caused corruption.
- **Effort**: Small — one scan, one gap class, tests.
- **Risk**: Low — the five current offenders are cleaned as part of this issue.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: the detection gap class, its report line, tests, cleaning the existing offenders, optional CONTRIBUTING note.
- **Out of scope**: auto-fixing (the intended content cannot be recovered mechanically); fixing the upstream tool-call decoding; scanning non-issue files.

## Acceptance Criteria

- [ ] An issue body containing each listed character yields one `invisible_chars` entry per occurrence with its code point name and line number, and `format-check` exits non-zero.
- [ ] Tab, LF, CR, and a leading U+FEFF BOM are not flagged.
- [ ] A nameless control (e.g. U+001F) is reported by its alias or `<control>` label without raising.
- [ ] A character in frontmatter (e.g. in `title:`) is flagged.
- [ ] After the listed offenders are cleaned, the full `.issues/` tree produces no `invisible_chars` gaps. (A 2026-09-24 scan found the offenders listed above, so this does not hold without the cleanup.)

## Related

- ENH-3540 (where the corruption was found and repaired)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-09-24T18:27:44 - `3f3defe9-b6c6-432f-af65-d7ce83807520.jsonl`
