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

`ll-issues format-check` should flag invisible and control characters in issue bodies: U+2028 LINE SEPARATOR, U+2029 PARAGRAPH SEPARATOR, zero-width characters (U+200B, U+200C, U+200D, and U+FEFF anywhere but offset 0), and C0 control characters other than tab and newline. These never belong in an issue file, and they are the one visible trace of a silent corruption that has already broken a spec once.

## Current Behavior

ENH-3540's `script_json` rule needed the literal text of six-character JSON unicode escapes (backslash, `u`, four hex digits). Every committed revision of that file instead held the decoded characters, so the rule read as identity mappings ("replace `<` with `<`") and contained raw U+2028/U+2029 bytes. A manual "repair" recorded in its Session Log never landed. Nothing flagged it; it was found only by reading the raw bytes.

The most likely cause is upstream of little-loops: tool-call arguments are JSON, so a model that writes a backslash-u sequence in an Edit/Write argument has it decoded by the JSON parser before it reaches the file. Any agent editing issue text can hit this. `format-check` (`check_format_gaps` in `scripts/little_loops/issue_parser.py`, CLI in `scripts/little_loops/cli/issues/format_check.py`) has no check for it.

## Expected Behavior

- `check_format_gaps` reports a new gap class (e.g. `invisible_chars`) listing each offending character by code point and line number.
- `ll-issues format-check` exits non-zero on it, like the other structural gaps.
- The report names the code point in words (e.g. `U+2028 LINE SEPARATOR at line 291`), never by reproducing the character.

## Motivation

The corruption is silent, invisible in most renderers, and turns a precise spec into a wrong one. A cheap deterministic check catches it at the gate every refined issue already passes through.

## Proposed Solution

Add a scan over the issue body in `check_format_gaps`: flag U+2028, U+2029, U+200B, U+200C, U+200D, U+FEFF (except at offset 0), and code points below U+0020 other than tab, LF, and CR. Add the new field to `FormatGaps` and its serialized/rendered output, and a report-only gap with no auto-fix (removal is not always the right fix, since the intended text was an escape sequence). Optionally add a CONTRIBUTING note: write escape sequences in specs out in words or as hex-digit tables, never as literal backslash-u text.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `check_format_gaps` gains the scan; `FormatGaps` gains an `invisible_chars` field and its serialized/rendered output.
- `scripts/little_loops/cli/issues/format_check.py` — report lines and exit code for the new gap class.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_design.py` — consumes `format-check --format json` output; confirm the new key does not break it.

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
- Flag U+2028, U+2029, U+200B, U+200C, U+200D; U+FEFF except at offset 0; code points below U+0020 other than tab, LF, CR.
- Report the code point by name, never by reproducing the character.

## Implementation Steps

1. Add the scan to `check_format_gaps` and the `invisible_chars` field to `FormatGaps`, reporting code point name and line number.
2. Surface it in `ll-issues format-check` output (text and JSON) with a non-zero exit.
3. Verify: unit tests per character and allowed character, a CLI test, and a clean run over the current `.issues/` tree.

## Impact

- **Priority**: P4 — guard against a rare, upstream-caused corruption.
- **Effort**: Small — one scan, one gap class, tests.
- **Risk**: Low — no issue currently trips it.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: the detection gap class, its report line, tests, optional CONTRIBUTING note.
- **Out of scope**: auto-fixing (the intended content cannot be recovered mechanically); fixing the upstream tool-call decoding; scanning non-issue files.

## Acceptance Criteria

- [ ] An issue body containing each listed character yields one `invisible_chars` entry per occurrence with its code point name and line number, and `format-check` exits non-zero.
- [ ] Tab, LF, CR, and a leading U+FEFF BOM are not flagged.
- [ ] The full `.issues/` tree currently produces no `invisible_chars` gaps (a scan on 2026-09-24 found none after ENH-3540 was fixed).

## Related

- ENH-3540 (where the corruption was found and repaired)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-09-24T18:27:44 - `3f3defe9-b6c6-432f-af65-d7ce83807520.jsonl`
