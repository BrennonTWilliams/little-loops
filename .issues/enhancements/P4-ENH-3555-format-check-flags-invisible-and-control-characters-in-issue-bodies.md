---
id: ENH-3555
type: ENH
title: format-check flags invisible and control characters in issue bodies
priority: P4
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:27:36Z'
completed_at: '2026-09-25T00:42:54Z'
labels:
- issues
- tooling
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3555: format-check flags invisible and control characters in issue bodies

## Summary

`ll-issues format-check` should flag invisible and control characters in issue files: U+2028 LINE SEPARATOR, U+2029 PARAGRAPH SEPARATOR, zero-width characters (U+200B, U+200C, U+200D, U+2060, and U+FEFF anywhere but offset 0), bidirectional controls and marks (U+202A–U+202E, U+2066–U+2069, U+200E, U+200F, U+061C), Unicode tag characters (U+E0000–U+E007F), U+00AD SOFT HYPHEN, DEL (U+007F), C1 controls (U+0080–U+009F), and C0 control characters other than tab, LF and CR. These never belong in an issue file, and they are the one visible trace of a silent corruption that has already broken a spec once.

## Current Behavior

ENH-3540's `script_json` rule needed the literal text of six-character JSON unicode escapes (backslash, `u`, four hex digits). Every committed revision of that file instead held the decoded characters, so the rule read as identity mappings ("replace `<` with `<`") and contained raw U+2028/U+2029 bytes. A manual "repair" recorded in its Session Log never landed. Nothing flagged it; it was found only by reading the raw bytes.

The most likely cause is upstream of little-loops: tool-call arguments are JSON, so a model that writes a backslash-u sequence in an Edit/Write argument has it decoded by the JSON parser before it reaches the file. Any agent editing issue text can hit this. `format-check` (`check_format_gaps` in `scripts/little_loops/issue_parser.py`, CLI in `scripts/little_loops/cli/issues/format_check.py`) has no check for it.

## Expected Behavior

- `check_format_gaps` reports a new gap class (e.g. `invisible_chars`) listing each offending character by code point and line number.
- `ll-issues format-check` exits non-zero on it, like the other structural gaps. The class is **blocking**: it is not added to `_ADVISORY_GAP_CLASSES` (`issue_parser.py:515`), and it is rendered in `format_check.py`'s report (a class counted by `has_gaps` but not rendered exits 1 with an empty report; see the comment at `format_check.py:435`).
- The report names the code point in words (e.g. `U+2028 LINE SEPARATOR at line 291`), never by reproducing the character. `unicodedata.name()` raises `ValueError` for C0/C1 controls and DEL (they have no name), so the scan needs a fallback: the control-code alias (`NULL`, `UNIT SEPARATOR`, …) from a small table, or `<control>` plus the code point.
- The scan covers the whole file, frontmatter included (a `title:` can carry these too). Only a U+FEFF at offset 0 is exempt.
- **Scan the raw file, not the newline-translated text.** `check_format_gaps` currently reads with `issue_path.read_text(encoding="utf-8")` (`issue_parser.py:940`), which applies universal-newline translation: a standalone CR and CRLF both become LF. The scan instead decodes `issue_path.read_bytes().decode("utf-8")` (no newline translation) and runs on that string.
- **The scan runs before the template-dependent early returns.** `check_format_gaps` returns early when the filename has no type prefix (`_ISSUE_TYPE_RE`) or `load_issue_sections` fails; the scan must run before both so those files are still checked.
- **Line numbers count `\n` only** in the raw decoded text: `raw.count("\n", 0, offset) + 1`. A standalone CR is not a line break, and CRLF counts once (via its LF). Do not number lines with `str.splitlines()`: it treats CR, U+2028, U+2029, U+0085, U+001C–U+001E, VT and FF as line boundaries, the very characters being detected, so every later line number in the report would be off.
- **`--fix --apply` does not remove or hide them.** The class is report-only; a fix run leaves offending characters in the file, and `format-check` still reports them afterwards.

## Motivation

The corruption is silent, invisible in most renderers, and turns a precise spec into a wrong one. A cheap deterministic check catches it at the gate every refined issue already passes through.

## Proposed Solution

Add a scan over the whole issue file in `check_format_gaps`: flag U+2028, U+2029, U+200B, U+200C, U+200D, U+2060, U+FEFF (except at offset 0), U+202A–U+202E, U+2066–U+2069, U+200E, U+200F, U+061C, U+E0000–U+E007F, U+00AD, U+007F, U+0080–U+009F, and code points below U+0020 other than tab, LF, and CR. The bidi controls and marks are a strong case: they can reorder how text renders without changing what a parser reads (the "Trojan Source" class, whose paper also lists LRM/RLM/ALM). The tag characters are the other: they are invisible and a known carrier for smuggled prompt-injection text, and issue files are read by models. (A 2026-09-24 scan found no existing offenders in the added ranges.) Add the new field to `FormatGaps` and its serialized/rendered output, and a report-only gap with no auto-fix (removal is not always the right fix, since the intended text was an escape sequence). Optionally add a CONTRIBUTING note: write escape sequences in specs out in words or as hex-digit tables, never as literal backslash-u text.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `check_format_gaps` gains the scan; `FormatGaps` gains an `invisible_chars` field and its serialized/rendered output.
- `scripts/little_loops/cli/issues/format_check.py` — report lines and exit code for the new gap class.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_design.py` — calls `check_format_gaps(path)` directly (not the JSON output) and reads only `design_gate_failed(gaps)` (`program_design_nonspecific`, `missing`, `empty`), so the new field does not affect it. No change needed.
- Other consumers of `format-check --format json` (loops, skills) read specific keys from `FormatGaps.to_dict()`; the new `invisible_chars` key is additive.

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
- `scripts/tests/test_issue_parser.py` — per-character detection, allowed characters (tab, LF, CR, leading BOM) not flagged; standalone-CR and CRLF fixtures (written with `write_bytes`) for line numbering; a file whose name has no type prefix is still scanned.
- `scripts/tests/test_ll_issues_format_check.py` — CLI report text and non-zero exit; `--fix --apply` leaves the offending characters in place and a following `format-check` still reports them. The existing `FormatGaps` field-parity test (`:3222`, iterates `dataclasses.fields(FormatGaps)`) fails if the new field is not rendered, which enforces the render requirement above.

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
- Flag U+2028, U+2029, U+200B, U+200C, U+200D, U+2060; U+FEFF except at offset 0; U+202A–U+202E, U+2066–U+2069, U+200E, U+200F, U+061C; U+E0000–U+E007F; U+00AD; U+007F; U+0080–U+009F; code points below U+0020 other than tab, LF, CR.
- Scan the whole file, frontmatter included, from `read_bytes().decode("utf-8")` (no newline translation), before any template-dependent early return.
- Line numbers count `\n` only in the raw text, never `splitlines()` boundaries; a standalone CR is not a line break.
- `--fix --apply` never removes flagged characters.
- Report the code point by name, never by reproducing the character; fall back to a control-alias table where `unicodedata.name()` has no name.
- Blocking, not advisory.

## Implementation Steps

1. Add the scan to `check_format_gaps` over the raw-decoded bytes, placed before the template-dependent early returns, and the `invisible_chars` field to `FormatGaps` (plus `has_gaps` and `to_dict`), reporting code point name and line number, with the control-name fallback.
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

- [x] An issue body containing each listed character yields one `invisible_chars` entry per occurrence with its code point name and line number, and `format-check` exits non-zero.
- [x] Tab, LF, CR, and a leading U+FEFF BOM are not flagged.
- [x] A nameless control (e.g. U+001F) is reported by its alias or `<control>` label without raising.
- [x] A character in frontmatter (e.g. in `title:`) is flagged.
- [x] Line numbers stay correct after a U+2028 or U+001E earlier in the file: a second offender on physical line N is reported at line N.
- [x] Line numbers follow `\n` in the raw bytes: with a standalone CR earlier on a line, the offender is still reported on that line; in a CRLF file, each CRLF counts as one line break.
- [x] A file skipped by the template-dependent early returns (no type prefix in the filename, or unloadable templates) is still scanned.
- [x] `ll-issues format-check --fix --apply` leaves flagged characters in the file, and a following `format-check` still reports them and exits non-zero.
- [x] U+200E, U+200F, U+061C and a tag character (e.g. U+E0041) are each flagged.
- [x] `ll-issues format-check --format json` includes an `invisible_chars` key (from `FormatGaps.to_dict()`) carrying the same entries as the text report.
- [x] After the listed offenders are cleaned, the full `.issues/` tree produces no `invisible_chars` gaps. (A 2026-09-24 scan found the offenders listed above, so this does not hold without the cleanup.)

## Related

- ENH-3540 (where the corruption was found and repaired)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

Checked 2026-09-24 against the working tree.

- Confirmed: `_ADVISORY_GAP_CLASSES` at `issue_parser.py:515`, `FormatGaps` at `:521`, `check_format_gaps` signature at `:684`, `read_text(encoding="utf-8")` at `:940`, early returns on `_ISSUE_TYPE_RE` (`:965`) and `load_issue_sections` (`:971`), render-parity comment at `format_check.py:434-440`, `cmd_format_check` at `format_check.py:517`, field-parity test at `test_ll_issues_format_check.py:3222`. `has_blocking_gaps` iterates `fields(self)`, so a new field outside `_ADVISORY_GAP_CLASSES` is blocking automatically; `has_gaps` (explicit OR chain) and `to_dict` (explicit dict) both need the field added by hand, as Implementation Step 1 says.
- Confirmed: `unicodedata.name()` has no name for U+001F, U+007F, U+0085 (fallback table needed).
- Confirmed: a re-scan of `.issues/` with the full character set finds exactly the eight listed occurrences across five files, and no others. All five offender issues are `done` (ENH-2746 included).
- Corrected: `check_design.py` was described as consuming `format-check --format json` output. It calls `check_format_gaps()` directly and reads only `design_gate_failed()` fields, so it is unaffected.
- Added: an Acceptance Criterion for the JSON `invisible_chars` key, which the Integration Map and Implementation Step 2 required but no criterion covered.
- `ll-verify-evidence`: clean (0 findings). No `## Blocked By` dependencies.

## Resolution

Implemented `invisible_chars` gap class (`_invisible_char_gaps` in `issue_parser.py`, rendered in `format_check.py`): blocking, report-only, scans raw bytes before early returns, `\n`-only line numbering. Cleaned the five existing offenders. Unrelated pre-existing failures: `test_no_new_unverifiable_evidence` (BUG-1688), `test_autodev_topology`.

## Status

**Open** | Created: 2026-09-24 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-09-25T00:42:54 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
- `/ll:ready-issue` - 2026-09-25T00:32:11 - `393a39b3-6e31-4e0a-89cc-6dce475ac438.jsonl`
- `/ll:confidence-check` - 2026-09-24T23:44:32 - `01d913d6-09f5-4671-9f2f-afb2a136b503.jsonl`
- `/ll:verify-issues` - 2026-09-24T23:39:33 - `ce8bec5b-7632-4ff9-a3da-7cdd35c70217.jsonl`
- `/ll:verify-issues` - 2026-09-24T22:56:17 - `4279401a-9acc-474c-b872-fd398cd78a8e.jsonl`
- `/ll:confidence-check` - 2026-09-24T22:35:26 - `55203869-e869-482b-b191-d68f9782af86.jsonl`
- `/ll:confidence-check` - 2026-09-24T22:10:01 - `b03f0e56-e701-4b6d-bb94-8f4cb425b852.jsonl`
- `/ll:capture-issue` - 2026-09-24T18:27:44 - `3f3defe9-b6c6-432f-af65-d7ce83807520.jsonl`
