---
id: ENH-2944
title: 'll-issues normalize: filename/ID mechanics out of normalize-issues.md'
type: ENH
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2941
- ENH-2953
labels:
- cli
- issues
- normalization
confidence_score: 96
outcome_confidence: 81
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 20
completed_at: '2026-08-01T09:09:26Z'
---

# ENH-2944: `ll-issues normalize` — filename/ID mechanics

## Summary

`commands/normalize-issues.md` (511 lines — the largest file in EPIC-2938's scope) is dominated by rename/ID bookkeeping the LLM executes by hand. Convert to an `ll-issues` subcommand; the LLM keeps only semantic type-classification review.

**Descoped after review** (2026-07-31): `prioritize --apply` split to **ENH-2953**. It is thin (233 lines, one judgment step) and was being gated behind the meatiest conversion in the epic for no reason. The two share a `git mv` rename helper — whichever lands first owns it.

## Current Behavior

**normalize-issues**: legacy-dir checks (L80–107), per-basename ID regex scans (L117–131), ID→file map + `sort | uniq -d` duplicate detection written to `.loops/tmp/` (L137–154), `ll-issues next-id` + keep-oldest-duplicate rules + slug generation (L215–246), three fixed report tables (L251–289), `git mv` loops (L293–312). Even "type misclassification" (L158–202) is a keyword→type lookup with a `(signals_for_top_type)/(total_signals+1)` confidence formula and a 0.7 cutoff — a Python function, not judgment.

## Expected Behavior

`ll-issues normalize [--check] [--auto] --json` — detects missing/duplicate/malformed IDs, legacy dirs, bad slugs; `--auto` applies renames via `git mv`; `--check` is a deterministic exit-code gate (EPIC convention: no LLM-narrated exits). Keyword-count type classification included; optionally cross-references ENH-2941's `find-similar --batch` for content-duplicate flagging (may land as a follow-up flag).

## Proposed Solution

Reuse `issue_parser` (`find_issues`, `slugify`, `get_next_issue_number`, `is_normalized`) and `frontmatter.py`. Duplicate-keep rule (oldest by git history, else alphabetical) implemented via `git log --follow` or file mtime fallback. Factor the `git mv` rename into a shared helper — ENH-2953 needs the same one.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Two existing `git mv` implementations already exist** and either can seed the shared helper this issue and ENH-2953 both need:
  - `scripts/little_loops/cli/issues/format_check.py:70` — `_move_file(src, dst, updated_content)`: checks `_is_git_tracked(src)` (from `little_loops.issue_lifecycle:393`, via `git ls-files`), prefers `subprocess.run(["git", "mv", str(src), str(dst)])`, falls back to plain write + `Path.rename()` for untracked files or on failure.
  - `scripts/little_loops/cli/loop/rename.py:199` — `_apply_rename()` (new/uncommitted, ENH-2943): `subprocess.run(["git", "mv", ...], check=True, capture_output=True, cwd=...)` for tracked scope, `.rename()` otherwise. This module's overall shape (`RenameReport` dataclass with a `dry_run` field, `rename_loop()` computing an identical plan for both dry-run and apply, `_apply_rename()` doing the actual move) is the closest sibling pattern in the repo and should be mirrored directly — same epic, same "offload mechanical work into ll-* CLI" intent.
  - `scripts/little_loops/cli/migrate.py` also has `_move_file()`/`_get_git_completion_date()` (git-log-based "which file is older" lookup) — useful precedent for the keep-oldest-duplicate rule, using `git log --format=%as -1 -- <path>` with a `timeout=30` guard.
- **`find_issues()` signature and status coverage**: `scripts/little_loops/issue_parser.py:1718` — `find_issues(config, category=None, skip_ids=None, only_ids=None, type_prefixes=None, status_filter=None, *, skip_blocked=False) -> list[IssueInfo]`. `scan_normalize()` should pass `status_filter=set(_ALL_STATUSES)` (as `format_check.py:185`'s `--all` sweep does) so done/deferred issues with malformed filenames aren't silently skipped.
- **`is_normalized`/`slugify`/`get_next_issue_number` are already at the exact signatures assumed** by this issue: `issue_parser.py:82` (`is_normalized(filename: str) -> bool`, regex `^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$` — matches the Validation Rules regex at `commands/normalize-issues.md:429-434` exactly), `issue_parser.py:961` (`slugify`), `issue_parser.py:975` (`get_next_issue_number(config, category=None) -> int`, already scans all category dirs globally for the max `PREFIX-NNN`).
- **No existing duplicate-ID-detection helper**: the ID→file map + `sort | uniq -d` dedup logic (`commands/normalize-issues.md:133-156`) exists only as inline bash today — `scan_normalize()` needs to implement this fresh in Python (iterate `find_issues()` results, group by parsed ID, flag groups with len > 1).
- **CLI wiring convention** (`scripts/little_loops/cli/issues/__init__.py`): one module per subcommand under `cli/issues/<name>.py`, either registered inline in `main_issues()` (simple case, e.g. `next-id` at lines 162-176) or via a self-registering `add_<name>_parser(subs)` helper for subcommands with more flags (e.g. `add_format_check_parser(subs)` at line 893) — `normalize`'s `--check`/`--auto`/`--json` flag surface should use the `add_normalize_parser(subs)` form, dispatched from the `if args.command == "normalize":` chain around lines 909-977.
- **`NormalizeFinding` dataclass precedent**: `scripts/little_loops/cli/issues/find_similar.py`'s `SimilarityMatch` (per-item dataclass with a `to_dict()` returning rounded/plain fields, produced by a pure `find_similar()` function and JSON-printed by a thin `cmd_find_similar()` wrapper) is the closer template than `FormatGaps`' per-category-list shape, since `NormalizeFinding` is per-file.
- **Exact line ranges in `commands/normalize-issues.md` to extract/delete**: legacy-dir checks (76-113), ID regex scan (115-131), ID→file map + duplicate detection writing to `.loops/tmp/` (133-156), type-misclassification keyword table + confidence formula (158-202, keep only as the LLM review prompt, not the scoring math), category/prefix mapping (204-213), next-ID lookup (215-223), filename generation incl. keep-oldest-duplicate rule (225-245, keep-oldest rule at line 239), the two report tables (247-291 "Normalization Plan", 374-425 "Issue Normalization Report"), and the `git mv` rename loop (293-312).
- **Test fixture pattern to follow**: `scripts/tests/test_cli_loop_rename.py`'s `TestRenameLoopDryRunParity` (asserts `dry_run` and `apply` runs produce structurally identical plans — `applied.total_files == dry.total_files`) directly answers this issue's "apply idempotency" acceptance criterion; `scripts/tests/test_ll_issues_find_similar.py`'s `_run(argv, temp_project_dir, sample_config)` helper shows the `main_issues()`-level CLI invocation pattern (patches `sys.argv`, writes `.ll/ll-config.json`, redirects stdout) for testing `ll-issues normalize` end-to-end.

## Integration Map

### Files to Modify
- `commands/normalize-issues.md` — slim from 511 → ~80 lines; delete the mechanical sections listed above, keep only the flag-parsing intro, the type-misclassification LLM-review prompt (stripped of the confidence-formula math), and the final "review + confirm" narration.
- `scripts/little_loops/cli/issues/__init__.py` — add `normalize` module import, `add_normalize_parser(subs)` registration (or inline parser if flag surface stays small), and dispatch arm in the `if args.command == "..."` chain (around lines 838-977).

### New Files
- `scripts/little_loops/cli/issues/normalize.py` — `NormalizeFinding` dataclass, `scan_normalize(issues_dir_or_config) -> list[NormalizeFinding]`, `apply_normalize(findings) -> None`, `classify_type(issue) -> tuple[str, float]`, `cmd_normalize(config, args) -> int`.

### Dependent Files (Callers/Importers)
- `skills/ll-normalize-issues/SKILL.md` — thin wrapper pointing at `commands/normalize-issues.md`; no code change needed but should be checked after the command is slimmed to ensure trigger examples still match.
- `commands/prioritize-issues.md` / ENH-2953 — expected to import the same `git mv` helper this issue factors out; coordinate the helper's exact location/signature so ENH-2953 doesn't duplicate it.

### Similar Patterns
- `scripts/little_loops/cli/loop/rename.py:129` (`rename_loop()`) and `:199` (`_apply_rename()`) — dry-run/apply parity shape to mirror for `scan_normalize()`/`apply_normalize()`.
- `scripts/little_loops/cli/loop/cleanup.py:57` (`classify_run()`) / `:121` (`cleanup()`) — pure-classifier vs. mutating-orchestrator split, same shape needed for `classify_type()` vs `apply_normalize()`.
- `scripts/little_loops/cli/issues/format_check.py` — `--check` exit-code convention (0 clean / 1 violations).
- `scripts/little_loops/cli/issues/find_similar.py` — pure-function-returns-`list[dataclass]` + thin `cmd_*` JSON-printing wrapper, the template for `NormalizeFinding`.

_Wiring pass added by `/ll:wire-issue`:_
- **Correction to the git-mv helper pointer above**: `cli/issues/format_check.py` has no `_move_file()`/`_is_git_tracked()` — those live in `scripts/little_loops/issue_lifecycle.py`: `_is_git_tracked()` at line 393, and the git-mv-with-fallback pattern to mirror is `skip_issue()` (~line 934-990: `git mv` when tracked, `atomic_write()` + `Path.rename()` fallback on failure or when untracked). Import from `issue_lifecycle`, not `format_check`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_bug_2816_cli_invocations.py:83-90` (`TestPromptAcrossIssuesQuickFix`) — pins `/ll:normalize-issues {issue_id} --auto` as the exact invocation string used by `scripts/little_loops/loops/prompt-across-issues.yaml:19`, and asserts no `--quick` flag exists. The `--auto` flag name/behavior on the slimmed command must survive unchanged.
- `skills/ll-normalize-issues/SKILL.md`, `.kimi-code/skills/ll-normalize-issues/SKILL.md`, `.gemini/commands/help.toml` — generated host-adapter mirrors of `commands/normalize-issues.md` (via `ll-adapt`). These go stale once the command is slimmed; regenerate with `ll-adapt --host <host> --apply` for each host after editing.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the `### ll-issues` section documents one `#### ll-issues <subcommand>` subsection per subcommand (e.g. `#### ll-issues format-check`); add `#### ll-issues normalize` documenting the `--check`/`--auto`/`--json` flag surface and exit-code semantics.
- `.claude/CLAUDE.md` — the `## CLI Tools` bullet for `ll-issues` enumerates every subcommand in its parenthetical list (`next-id, list, show, ... format-check, epic-progress, epic-consistency, deferred-triage, decisions (...)`); add `normalize` to that list. No existing test cross-checks this list against actual argparse subparsers (checked — `test_wiring_cli_registry.py`'s `DOC_STRINGS_PRESENT` mechanism only asserts individual substrings, not full enumeration), so this must be applied by hand.
- `docs/guides/LOOPS_GUIDE.md:1004` — documents the `--check` flag's FSM exit-code evaluator contract (`evaluate: type: exit_code`) shared across several "issue prep skills" including `normalize-issues`; the slimmed command's `--check` passthrough to `ll-issues normalize --check` must preserve this contract (0 clean / 1 violations).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py:134-135` — **hard constraint**: asserts literal substrings `"EPIC"` and `"epics/"` are present in `commands/normalize-issues.md` (FEAT-1407, epic-type support). The slimmed ~80-line command must retain at least one occurrence of each (e.g. in the retained type-classification LLM-review prompt's EPIC row/epics/ directory example) or this test fails.
- `scripts/tests/test_ll_issues_format_check.py` — closest sibling CLI test file; its `format_check_dir` fixture, `_write_issue()` helper, and `_invoke(argv)` (patches `sys.argv`, calls `main_issues()` directly, not subprocess) is an equally-valid alternate model to `test_ll_issues_find_similar.py`'s `_run()` harness already cited above. Its `TestFormatCheckFix` (FEAT-2851) is the closest existing dry-run-preview/`--apply`-idempotent precedent (second apply reports no further gap, file byte-identical) — model the `--check`/`--auto` idempotency test on this rather than deriving it fresh.
- After implementation, run `ll-verify-skill-prose` manually against the slimmed `commands/normalize-issues.md` — `TestBaselineNeverIncreases` (in the skill-prose test suite) enforces a ceiling (currently 23 findings) across `skills/*/SKILL.md` + `commands/*.md`; slimming should only reduce hits but is worth a manual spot-check.

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/normalize.py`: `NormalizeFinding` dataclass, `scan_normalize()` (built on `issue_parser.find_issues(config, status_filter=set(_ALL_STATUSES))`, `is_normalized()`, and fresh Python ID-duplicate-detection logic replacing the bash map/`uniq -d` at `commands/normalize-issues.md:133-156`), `classify_type()` (port the keyword-signal table + `(signals_for_top_type)/(total_signals+1)` confidence formula from lines 166-182), and `apply_normalize()` (git-mv helper mirroring `cli/loop/rename.py:199`'s `_apply_rename()` or `cli/issues/format_check.py:70`'s `_move_file()`).
2. Wire `ll-issues normalize [--check] [--auto] --json` into `scripts/little_loops/cli/issues/__init__.py` following the `add_format_check_parser(subs)` self-registration convention; `--check` returns 0/1 per the `format_check.py:cmd_format_check` pattern.
3. Slim `commands/normalize-issues.md` (511 → ~80), deleting the mechanical sections cataloged above, keeping only the type-misclassification LLM-review step.
4. Tests in `scripts/tests/test_ll_issues_normalize.py`: fixture tree with missing/dup/malformed IDs (model fixtures on `test_ll_issues_find_similar.py`'s `_write_issue()`/`_run()` helpers); check-mode exit codes; apply idempotency via a dry-run/apply parity test (model on `test_cli_loop_rename.py::TestRenameLoopDryRunParity`).
5. Coordinate the shared `git mv` helper's final location/signature with ENH-2953 before either lands, to avoid duplicate implementations.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Mirror the git-mv-with-fallback helper from `issue_lifecycle.py`'s `skip_issue()` (~line 934-990, using `_is_git_tracked()` at line 393) — not `format_check.py`, which has no such helper despite the original research note.
7. When slimming `commands/normalize-issues.md`, retain at least one occurrence each of the literal strings `"EPIC"` and `"epics/"` — `test_wiring_skills_and_commands.py:134-135` asserts their presence (FEAT-1407) and will fail otherwise.
8. Add `#### ll-issues normalize` to `docs/reference/CLI.md` (flags + exit-code semantics) and add `normalize` to the `ll-issues` subcommand list in `.claude/CLAUDE.md`'s `## CLI Tools` section.
9. After slimming, regenerate host-adapter mirrors of the command via `ll-adapt --host <host> --apply` (Codex, etc. — `skills/ll-normalize-issues/SKILL.md` and siblings).

## Program Design

### Types

- `NormalizeFinding: dataclass`
  - `path: Path`
  - `kind: str`  (missing_id | duplicate_id | malformed_id | legacy_dir | bad_slug | type_mismatch)
  - `proposed_path: Path | None`
  - `confidence: float | None`

### Signatures

- `scan_normalize(issues_dir: Path) -> list[NormalizeFinding]` — via `issue_parser.find_issues`, `is_normalized`, `slugify`
- `apply_normalize(findings: list[NormalizeFinding]) -> None` — `git mv`, ID allocation via `get_next_issue_number`
- `classify_type(issue: IssueInfo) -> tuple[str, float]` — keyword-signal table + `(signals_for_top_type)/(total_signals+1)` confidence

### Call Path

- `scan_normalize()` -> `find_issues()` (existing) -> `slugify()` (existing, `issue_parser.py`)
- `apply_normalize()` -> `get_next_issue_number()` (existing, `issue_parser.py`)

## Scope Boundaries

- In scope: the `normalize` subcommand (`--check`/`--auto`), slimming `commands/normalize-issues.md`, the deterministic exit-code gate, and the shared `git mv` rename helper.
- Out of scope: semantic (LLM) type reclassification, content-duplicate merging (flagging only, via ENH-2941 follow-up), `prioritize` (ENH-2953), changing the P0–P5 taxonomy.

## Impact

- **Priority**: P2 - Converts the largest single file in scope (511 lines) and fixes a narrated exit-code gate
- **Effort**: Medium - normalize is meaty
- **Risk**: Low-Medium - Renames via `git mv` with `--check` preview; collision-safe ID allocation tested

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues normalize --check` exit code is the FSM-usable gate (0 clean / 1 violations)
- [ ] `--auto` renames preserve git history (`git mv`) and never allocate colliding IDs
- [ ] `commands/normalize-issues.md` contains no glob/regex/table-rendering instructions
- [ ] The `git mv` rename helper is shared with (or shareable by) ENH-2953
- [ ] pytest coverage in `scripts/tests/`

## Notes

`prioritize` was split to ENH-2953 so it ships without waiting on this issue's classification heuristics.


## Session Log
- `ll-auto` - 2026-08-01T09:09:26 - `ec714973-d76f-4116-84ff-2e2c0251f99e.jsonl`
- `/ll:confidence-check` - 2026-08-01T08:56:23 - `07fe8ff1-a654-49aa-b711-930081c502cd.jsonl`
- `/ll:wire-issue` - 2026-08-01T08:55:16 - `f37cbe16-d840-480f-83e5-7eb99669367a.jsonl`
- `/ll:refine-issue` - 2026-08-01T08:50:10 - `6d9c28da-0fa7-4143-9794-2101fbcb91ff.jsonl`


---

## Resolution

- **Action**: improve
- **Completed**: 2026-08-01
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
