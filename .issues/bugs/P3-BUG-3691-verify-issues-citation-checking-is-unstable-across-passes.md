---
id: BUG-3691
type: BUG
title: verify-issues citation checking is unstable across passes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-01'
captured_at: '2026-10-01T22:03:31Z'
reconcile_attempted: true
relates_to:
- ENH-3690
parent: EPIC-3694
epic: EPIC-3694
---

# BUG-3691: verify-issues citation checking is unstable across passes

## Summary

`/ll:verify-issues <ID> --check --auto` does not check citations consistently between passes of the same loop run, so a citation defect can surface only on a late pass, after the loop's repair budgets are spent.

Observed on BUG-3689 (run `refine-to-ready-issue-20261001T151155`): passes 1 and 2 reported every cited code reference as holding and returned `DIRECTIVE_DRIFT` (Acceptance Criteria gaps). Pass 3, with no relevant citation edits in between, flagged two wrong citations and returned `NON_VALID`, which ended the run `GATE_UNMET` (see the companion ENH on NON_VALID having no repair route). In the same run `refine_followup`'s gap analysis judged the bare name `runner_spec.py` acceptable, while verify pass 3 described it under an `fsm/`-prefixed directory (a path the issue text does not contain and that does not exist; the file is `scripts/little_loops/runner_spec.py`), i.e. it misread the citation before calling it wrong.

## Current Behavior

`verify-issues` resolves `path:line` / `file:symbol` citations through the model's ad-hoc reads and greps, so coverage differs between passes over an unchanged issue. Passes 1 and 2 of the BUG-3689 run reported every citation as holding; pass 3 flagged two as wrong. Bare filenames can also be misread as a different path before being judged.

## Expected Behavior

Citation resolution is deterministic: repeated `--check` passes over an unchanged issue produce identical citation findings, and a bare filename citation is resolved by search rather than reported as a different path.

## Motivation

A citation defect that surfaces only on a late pass lands after the loop's repair budgets are spent, turning a fixable issue into a `GATE_UNMET` run end. Making the check deterministic moves such defects to pass 1, where the repair route can still act on them, and removes a source of run-to-run variance in `refine-to-ready-issue`.

## Proposed Solution

Make citation findings deterministic **by extending `ll-issues format-check`** and making `verify-issues` consume its keys as ground truth; the model keeps only semantic claims.

> **Rescoped 2026-10-02 (EPIC-3694 review, Opus second opinion).** The original plan — a brand-new `ll-verify-citations` CLI — is dropped. It duplicated `ll-issues format-check` (which already runs `stale_file_ref` / `ambiguous_file_ref` / `stale_symbol_ref` / `mislocated_symbol_ref` right before `verify_issue` and which `verify-issues` ignores), carried ~20 registration touchpoints, and still would not have caught the real defect (a symbol cited via its *importing* module: `symbol_exists_in_file` is satisfied by the import at `feed.py:44`). Research findings below predate the rescope; items about registering a new CLI no longer apply.

1. **Defined-in vs imported-in rule** (`symbol_claims`): a symbol claimed in file F that F only *imports* (no `def`/`class`/assignment) while exactly one other tracked module defines it → `mislocated_symbol_ref` (use `symbol_resolves_elsewhere` for the target). Be conservative to avoid false positives where citing the importer is the intended usage-site claim: trigger only on definition-shaped claims (`file:symbol`, "defined in", `symbol()` as owner), and honor the existing `<!-- ll-prose-ok -->` suppression marker.
2. **Line past end of file**: new gap key (e.g. `stale_line_ref`) for a cited `path:N[-M]` whose line exceeds the file length; `anchors.resolve_anchor` clamps today, so this needs its own check relative to the project root, not process cwd.
3. **Bare-filename citations**: resolve slash-less refs (BUG-3689's `runner_spec.py:335`) through `text_utils.suffix_match_candidates` — 0 / 1 / >1 tracked paths → `stale_file_ref` / ok / `ambiguous_file_ref`, candidates sorted; report mirror-only matches distinctly; honor `(new)` planned-new markers.
4. **Scope**: widen the symbol/line checks beyond `_symbol_claim_scope_text` (Summary / Current Behavior / Root Cause / Context) to cover Integration Map, Tests and Wiring Phase — the BUG-3689 pass-3 defect sat in Tests/Wiring Phase — keeping fenced-block skipping (`text_utils.fence_spans`).
5. **`verify-issues` wiring**: new check **B8** (after check 7) reads `ll-issues format-check <ID> --format json` and treats its ref keys as authoritative; the model must not raise a path/line/symbol-location finding that format-check does not back up (demote it to an advisory note that does not affect the verdict). Fail-open wording matches B7: invocation failure → silent fallback.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/symbol_claims.py` — defined-in vs imported-in rule (`symbol_exists_in_file` / `symbol_resolves_elsewhere` callers)
- `scripts/little_loops/issue_parser.py` — `check_format_gaps` (add `stale_line_ref`; bare-filename resolution; widened scope next to `_symbol_claim_scope_text`) and the gap dataclass
- `scripts/little_loops/text_utils.py` — slash-less ref handling in `classify_file_ref` (or a sibling resolver using `suffix_match_candidates`); sorted candidates
- `scripts/little_loops/cli/issues/format_check.py` — report/`--format json` surface for the new key(s)
- `commands/verify-issues.md` — new check **B8** after §2B check 7; keep the `test_enh3250` anchors (`#### B. Verify Against Codebase`, `#### C. Determine Verdict`, `Persist the verdict to frontmatter`, `### 3. Request User Approval`) present and in order; `Bash(ll-issues:*)` is already granted
- Host mirrors of `commands/verify-issues.md` — regenerate with `ll-adapt --host <gemini|qwen|kimi-code|codex> --apply` (never hand-edit)

No new CLI: nothing to change in `scripts/pyproject.toml`, `cli/__init__.py`, `init/writers.py` (`_LL_PERMISSIONS`), `skills/configure/areas.md`, or `docs/reference/CLI.md` entry-point coverage.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` - runs `verify-issues --check --auto` each pass and routes on its verdict (a root `loops/` directory does not exist)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the real location of the `refine-to-ready-issue` loop (a root `loops/` directory does not exist); states `verify_issue` (runs `/ll:verify-issues ... --check --auto`) and `route_pre_score_obligation`; no edit needed while no new verdict value is added [Agent 1 finding]
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict` maps persisted `verify_verdict`; unchanged as long as citation findings reuse existing verdicts (§2.5 precedence); a new verdict value would also touch `next_obligation.py`, the `route:` table, `test_builtin_loops.py::TestRefineToReadyDispatch` and `test_ll_issues_next_obligation.py::TestVerify` [Agent 2 finding]
- `scripts/little_loops/text_utils.py` — `build_ref_index`, `suffix_match_candidates`, `classify_file_ref` are the bare-filename resolution primitives the new module imports; read-only reuse, no signature change [Agent 1 finding]
- `scripts/little_loops/cli/issues/format_check.py` — existing deterministic file-ref linter (`stale_file_ref` / `ambiguous_file_ref`) over the same `RefIndex`; overlaps the new check but deliberately skips slash-less refs [Agent 1 finding]
- `scripts/little_loops/issues/anchor_sweep.py` and `scripts/little_loops/issues/symbol_claims.py` — adjacent `file:line` / symbol extractors (`_FILE_LINE`, `_EXPLICIT_RE`) the new `extract_citations` must either reuse or stay consistent with [Agent 1 finding]
- `commands/refine-issue.md` and `skills/ll-refine-issue/SKILL.md` — grant `Bash(ll-verify-evidence:*)` and call `/ll:verify-issues`; no edit unless `refine-issue` also invokes the new CLI (`test_refine_issue_command.py` pins its grant) [Agent 1 finding]

### Similar Patterns
- `ll-verify-evidence` (`scripts/little_loops/cli/verify_evidence.py`) - deterministic CLI check consumed by a skill/loop as ground truth

### Tests
- `scripts/tests/test_symbol_claims.py` / `test_issue_parser.py` / `test_format_check*.py` (locate the existing `stale_symbol_ref` / `stale_file_ref` suites): importing-module claim → `mislocated_symbol_ref`; defining-module claim → clean; line past EOF; bare filename 0/1/>1 matches with sorted candidates; mirror-only match; `(new)` planned file not flagged; `ll-prose-ok` suppression
- Determinism: run `check_format_gaps` / `format-check --format json` twice over an unchanged fixture issue (`tmp_path` git repo; helpers in `test_verify_evidence.py` style) and assert byte-identical output
- `scripts/tests/test_bug3691_verify_issues_citations.py` (new) — B8 present between check 7 and `#### C. Determine Verdict`; consumes `ll-issues format-check`; modelled on `test_enh3126_verify_issues_graph_seeding.py`
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — slices on the §2B/§C/§3 anchors via `body.index(...)`; must stay green
- `scripts/tests/test_verify_skill_prose.py::TestBaselineNeverIncreases` (`BASELINE_COUNT = 17`) — B8 prose must not add `python3 -c` / union-find wording; name the CLI as owner, do not describe the resolution steps (EPIC-2938 invariant)
- `scripts/tests/test_docs_audience_gate.py` — B8 prose must not cite `scripts/` paths (use `little_loops.<module>`)
- `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` — fails until mirrors are regenerated

### Documentation
- `docs/reference/CLI.md` — the `ll-issues format-check` section: new gap key(s) and bare-filename behavior
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — optional note under `/ll:verify-issues` that citation checks are deterministic

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- **`resolve_artifact` is exact-match only.** `verify_evidence.py:resolve_artifact(base_dir, ref, config, tracked=None, cache=None) -> str | None` returns `ref` only if it is a member of the `build_tracked_index` frozenset (or resolves an issue ID); it does no basename/suffix search and does not strip `:line` / `:symbol`. A bare `runner_spec.py` returns `None` because the tracked path is `scripts/little_loops/runner_spec.py`. Bare-filename resolution therefore needs a different primitive.
- **Basename-search primitives already exist in `text_utils.py`:** `build_ref_index(root)` (one `git ls-files -z`, `RefIndex.by_basename`), `suffix_match_candidates(ref, index)` (exact hit, else paths ending `"/" + ref`, then drops host-adapter mirror prefixes), `resolve_ref_path`, `classify_file_ref(ref, index, line="")` -> `resolved | stale | unresolvable_form | planned_new | ambiguous | untracked_by_design`. `resolve_ref_path` cannot distinguish absent from ambiguous; `classify_file_ref` can, but returns `unresolvable_form` for any ref with no `/` before any lookup, so bare filenames are deliberately unchecked by `ll-issues format-check` (`stale_file_ref` / `ambiguous_file_ref`). That gap is the BUG-3689 `runner_spec.py` case.
- **Candidate order is not sorted.** `suffix_match_candidates` returns candidates in `git ls-files` order; `format_check` sorts only when printing. Stable findings across passes require the new check to impose its own ordering when reporting `ambiguous` candidates.
- **Symbol and line coverage today:** `issues/symbol_claims.py` (`extract_symbol_claims`, `symbol_exists_in_file`, `symbol_resolves_elsewhere`) already surfaces `stale_symbol_ref` / `mislocated_symbol_ref` through `ll-issues format-check`, scoped by `issue_parser._symbol_claim_scope_text` to Summary / Current Behavior / Root Cause / Context only (so a citation in Tests or Integration Map is outside it). Nothing in `scripts/little_loops` reports a cited line number as beyond end of file or checks a cited line's content; `issues/anchors.py:resolve_anchor(file_path, line_number)` reads relative to process cwd and clamps past-EOF lines rather than failing.
- **`verify-issues` consumes none of this today.** `commands/verify-issues.md` §2A/§2B (model reads/greps, optional `ll-code defines` relocation in §2B.0) does the citation work; its only deterministic CLI calls are `ll-verify-evidence` (check B7, quoted spans, not citations) and `ll-issues format-check` for prose-dependency keys (§C step 3, line 313). `refine-to-ready-issue.yaml` already runs `ll-issues format-check <ID> --fix --apply` then `--format json` in `normalize_structure` immediately before `verify_issue`, so the file/symbol-ref gap keys exist before verify runs but are not read by it.
- **Loop routing:** the verdict is persisted as `verify_verdict` frontmatter (§2.5 precedence `NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT` > `VALID`) and read by `route_pre_score_obligation` via `classify_verify_verdict`; `NON_VALID` maps to `other` -> `check_gate_refine_limit`. A citation wrong outside the correctable sections (Findings, Integration Map, Similar Patterns…) is what persists as `NON_VALID`; ENH-3690 owns the repair route for that case and is orthogonal to this issue's determinism fix.
- **Registration surface for a new `ll-verify-*` entry point** (omissions are caught by gates, listed under Tests/Documentation below): `scripts/pyproject.toml` `[project.scripts]` (`little_loops.cli:main_verify_*` form), `scripts/little_loops/cli/__init__.py` (import + `__all__`), `scripts/little_loops/init/writers.py:_LL_PERMISSIONS` (`Bash(ll-verify-evidence:*)` at line 172), `skills/configure/areas.md` "Authorize all" list (line 862), and the `allowed-tools` frontmatter of `commands/verify-issues.md` plus its generated bridge `skills/ll-verify-issues/SKILL.md`.
- **Gates that fire on a new entry point:** `ll-verify-cli-allowlist` (`verify_cli_allowlist.py:_all_ll_entry_points()` reads *installed distribution metadata*, so the editable install must be re-registered before `test_verify_cli_allowlist.py::TestMainVerifyCliAllowlist::test_clean_state_returns_zero` sees the new script); `doc_counts.py:verify_coverage` requires a `### ll-verify-citations` section in `docs/reference/CLI.md` (`test_doc_counts.py::TestVerifyCoverage`); `test_wiring_cli_registry.py:DOC_STRINGS_PRESENT` is a hand-edited list (rows are per-CLI, not auto-derived).
- **Conventions in force for CLI shape:** `scripts/little_loops/cli/verify_<name>.py` with `main_verify_<name>()` wrapped in `cli_event_context(DEFAULT_DB_PATH, "ll-verify-<name>", sys.argv[1:])`; `-j/--json` via `cli_args.add_json_arg`; exit `0` clean / `1` findings / `2` verification incomplete; JSON payload `{"ok", "mode", "count", "findings": [...]}`; fail-open on invocation failure from the consuming command (silent fallback, per `verify-issues.md` B7 and §B.0). The two existing signature styles disagree: parameterless (`kinds`, `cli_allowlist`, `decisions`, `triggers`, tested by patching `sys.argv`) vs `argv: list[str] | None = None` (`evidence`, `private_refs`, `skill_prose`, tested by passing a list); the latter family also carries `-C/--directory`. Evidence: `verify_evidence.py:main_verify_evidence`, `verify_kinds.py`, `verify_private_refs.py`.
- **Four overlapping `path[:line]` extractors** exist: `text_utils.py` (`_BACKTICK_PATH`, `_BOLD_FILE_PATH`, `_STANDALONE_PATH`; line suffix dropped), `anchor_sweep.py:_FILE_LINE` (`:\d+` required), `verify_evidence.py:_FILE_PATH_CANDIDATE_RE` (optional `:N`, `:N-M`, `:N,M`; the line suffix is non-capturing so it is not returned), `symbol_claims.py:_EXPLICIT_RE`. None returns `(path, line, symbol)` together, so `extract_citations` cannot reuse one unchanged; which to extend (or whether to consolidate) is an implementation call. Fence handling is likewise duplicated (`text_utils.fence_spans`/`in_fence` is the shared form; `anchor_sweep.py` still has a local one).

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- **No numbered check beyond 7 exists in `commands/verify-issues.md` §2B.** Check 7 (`ll-verify-evidence`) is the only deterministic CLI step in that list; checks 1–2 (files exist, line numbers) are model-judged with no prescribed tool. `$ISSUE_FILE`, which check 7's invocation uses, is not assigned in the §0/§1 shell blocks (they set `ISSUE_ID`, `FLAGS`, `AUTO_MODE`, `CHECK_MODE` and print paths via `ll-issues path`), so a new check must state where the path comes from.
- **Contested convention — CLI-unavailable handling.** `verify-issues.md` check 7 and §B.0 say silent fallback with zero behavior change; `refine-issue.md` §3.9/§6.8 records "incomplete verification" and reports it. Neither text says how to tell an invocation failure from exit 1 (findings) for `verify-issues`. `ll-verify-evidence` itself emits exit 2 only in snapshot/delta modes. Which reading the new check follows decides whether a missing CLI can ever silently reproduce the instability this issue describes.
- **Format-check already computes part of this and `verify-issues` ignores it.** `refine-to-ready-issue.yaml` runs `ll-issues format-check <ID> --fix --apply` then `--format json` in `normalize_structure` immediately before `verify_issue`; `stale_file_ref`, `ambiguous_file_ref`, `stale_symbol_ref`, `mislocated_symbol_ref` exist in that payload but only `directive_gaps` is read. `check_format_gaps` iterates refs and symbol claims in sorted order, which is why those keys are stable across passes.
- **Verdict mapping is prose only.** The sections-to-verdict rule (correctable scope for `CLAIMS_OUTDATED`, precedence list) lives in `verify-issues.md` §C/§2.5, not in code; `classify_verify_verdict` (`check_verify_verdict.py`) only classifies the persisted token. Any citation finding therefore reaches routing solely through the model's verdict write.
- **Suppression-marker convention.** Each verify CLI owns a `<!-- ll-<x>-ok: reason -->` marker (`ll-evidence-ok` honours the same or preceding line; `ll-prose-ok` preceding line only, in `verify_skill_prose` and `symbol_claims._SUPPRESS_RE`). A citation check that cannot be silenced for a reviewed false positive diverges from both.
- **`verify_skill_prose` lints prose that reimplements a CLI-owned algorithm** (EPIC-2938 invariant, suppression `ll-prose-ok`); B8 wording should name the CLI as the owner rather than describe the resolution steps.

## Program Design

### Types

- `FormatGaps.stale_line_ref: list[str]` — new gap key (cited `path:N` beyond end of file); existing `stale_file_ref`, `ambiguous_file_ref`, `stale_symbol_ref`, `mislocated_symbol_ref` reused

### Signatures

- `symbol_defined_in_file(index: SymbolIndex, file: str, symbol: str) -> bool | None` — new in `issues/symbol_claims.py`: True only for a definition (not an import); `None` when the file cannot be read/parsed
- `check_format_gaps(...)` — unchanged signature; emits the new/changed keys

### Call Path

`verify-issues` check B8 -> `ll-issues format-check <ID> --format json` -> `check_format_gaps` -> `symbol_claims` / `text_utils.suffix_match_candidates`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- `resolve_artifact` takes a required `config` argument (`BRConfig | None`) and treats a full-match issue ID specially via `issue_parser.resolve_issue_path`; calling it with `config=None` is supported. Its `str | None` return collapses "absent" and "ambiguous", so `CitationFinding.status` values `unresolved` vs `ambiguous` cannot come from `resolve_artifact` alone — the `ambiguous` status needs the candidate list from `text_utils.suffix_match_candidates` (`list[str]`, `git ls-files` order).
- Anchors for the existing call-path nodes: `verify_evidence.py:build_tracked_index(base_dir, *, strict=False) -> frozenset[str]`, `verify_evidence.py:resolve_artifact`, `text_utils.py:build_ref_index(root) -> RefIndex`, `text_utils.py:classify_file_ref`. Decision Rules: N/A — the check adds no new gap kind to `format-check`; a bare filename resolving to 0 / 1 / >1 tracked paths maps to `unresolved` / `holds` / `ambiguous`, and ambiguous candidates must be reported in a sorted order to meet the "identical findings across passes" criterion.

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- **No extractor returns `(path, line, symbol)` together**, and the five path-shaped regexes disagree: extension length `{2,4}` (`anchor_sweep._FILE_LINE`) vs `{1,6}` (`symbol_claims._EXPLICIT_RE`); `:N-M` / `:N,M` ranges accepted only by `verify_evidence._FILE_PATH_CANDIDATE_RE` (as a non-capturing suffix); `anchor_sweep._FILE_LINE` requires whitespace or line start before the path, so a backtick-preceded `path:N` does not match; `issue_discovery/matching.py:_extract_line_numbers` is a fifth `:N(-M)` parser. The `extract_citations(body) -> list[str]` signature above carries no line or symbol, so whether a cited line beyond EOF or an explicit `file:symbol` is in scope is undecided by the types as written.
- **Bare-filename routing constraint.** `classify_file_ref` returns `unresolvable_form` for any ref with no `/` before any lookup, so it cannot be the resolver for the BUG-3689 `runner_spec.py` case. `suffix_match_candidates` does resolve it (basename lookup, then `"/" + ref` suffix match), but returns `[]` when every match is a host-adapter mirror path (`.codex/`, `.gemini/`, `.kimi-code/`), so that case reads as `unresolved`, not `ambiguous`.
- **Planned-new false-positive hazard.** `_PLANNED_NEW_RE` (`(new)`, `(new file)`, `(to be created)`, `**new**`) is applied only inside `classify_file_ref`. `resolve_artifact` and `suffix_match_candidates` have no such handling, so a check built only on those would report every planned-new file in an Integration Map (this issue's own `verify_citations.py` is one) as `unresolved`.
- **Fence handling must match the rest of the call path:** `text_utils.fence_spans`/`in_fence` is line-anchored and offset-preserving (BUG-3202) and is what `verify_evidence` uses; `extract_file_paths`, `anchor_sweep` and `symbol_claims` use the unanchored `_CODE_FENCE` regex. Citations inside a fenced block are skipped by all of them; an extractor using the other form can produce different findings on the same body.
- **Output-ordering constraint.** `extract_file_paths` returns a `set` and `build_tracked_index` a `frozenset`; neither has a defined iteration order. Findings, not just `ambiguous` candidates, need an explicit sort key for the byte-identical-JSON criterion (`verify_evidence.scan_file` sorts by line only, which is stable but not total).
- **CLI contract in force** (`verify_evidence.py:main_verify_evidence`, `verify_skill_prose.py:main_verify_skill_prose`): `main_*(argv: list[str] | None = None) -> int` inside `cli_event_context(DEFAULT_DB_PATH, "<cli>", sys.argv[1:])`; `-C/--directory`, `add_json_arg`; JSON payload `{"ok", "mode", "count", "findings"}`; exit 0 clean / 1 findings / 2 only for incomplete verification. The Signatures above use a parameterless `main_verify_citations() -> int`; the parameterless style (`verify_kinds`, `verify_cli_allowlist`) lacks `-C`/`--json`, and the argv style is the one the other scanning CLIs and their tests use.
- Decision Rules: N/A — no new `format-check` gap kind; the unresolved/holds/ambiguous mapping is stated in the finding above.

## Implementation Steps

1. Add the defined-in vs imported-in rule in `symbol_claims` and route it to `mislocated_symbol_ref` (conservative trigger; honor `ll-prose-ok`).
2. Add the line-past-EOF check and slash-less bare-filename resolution (0/1/>1, sorted candidates, mirror-only distinct, `(new)` markers skipped) in `check_format_gaps` / `text_utils`; widen scope to Integration Map, Tests and Wiring Phase.
3. Surface the new key(s) in `ll-issues format-check` text/JSON output.
4. Add check B8 to `commands/verify-issues.md` (format-check keys are ground truth; unbacked citation findings are advisory); regenerate host mirrors.
5. Tests: per Tests section, including the run-twice byte-identical determinism test; run `python -m pytest scripts/tests/`.
6. Replay the BUG-3689 case: a fixture with `runner_spec.py:335` (bare) and `cli/loop/feed.py:terminal_size()` must surface on pass 1.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- Bare-filename resolution must go through a basename-keyed index (`text_utils.RefIndex.by_basename` already provides one); `resolve_artifact` alone cannot satisfy the second acceptance criterion because it never matches a path without its directory.
- Registration of the new entry point must leave these green: `test_verify_cli_allowlist.py`, `test_doc_counts.py::TestVerifyCoverage`, `test_wiring_cli_registry.py`, and the docs-audience gate (`commands/verify-issues.md` may cite `little_loops.<module>`, never `scripts/` paths). The bridge `skills/ll-verify-issues/SKILL.md` mirrors the command's frontmatter and must be regenerated, not hand-edited.
- Determinism verification: a test that runs the check twice over an unchanged fixture issue (in a `tmp_path` git repo, using the `_init_repo`/`_write`/`_commit_all` style of `test_verify_evidence.py`) and asserts byte-identical JSON; no existing test in `test_verify_evidence.py` asserts run-to-run equality, so this is a new contract.
- Scope check: the BUG-3689 pass-3 defect was a symbol cited by its importing module rather than its defining module (Steps to Reproduce); `symbol_claims.symbol_resolves_elsewhere` already detects that shape but only inside the sections `_symbol_claim_scope_text` selects, so the new check's section scope must be decided against that gap. Retry/repair for a `NON_VALID` that remains is out of scope (ENH-3690).

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- Outcome: a citation to a file the issue marks as planned-new is not reported `unresolved`; verified by a fixture issue carrying a `(new)` marker beside an untracked path.
- Outcome: a bare filename whose only tracked matches are host-adapter mirrors is reported distinctly from a genuinely absent one, or the choice to merge them is stated in the CLI docs; verified by a fixture with a mirror-only match.
- Outcome: `ll-verify-citations` exit codes follow the `ll-verify-evidence` contract (0 clean, 1 findings, 2 verification incomplete), and `commands/verify-issues.md` states what a non-zero invocation failure does; verified by `test_enh3250_verify_issues_proposal_vs_code.py` anchors staying in order.
- Run-to-run precedents for the determinism test exist outside the verify CLIs (`test_ll_issues_find_similar.py::test_find_similar_deterministic` compares two invocations' output); the verify-CLI fixture style remains `test_verify_evidence.py`.

## Impact

- **Priority**: P3 - causes a late-pass `GATE_UNMET` run end, but only when a citation defect exists
- **Effort**: Medium - extend format-check (3 rules + scope widening), one verify-issues check, mirrors and tests (no new CLI)
- **Risk**: Low-Medium - the defined-in rule can false-positive on usage-site citations (mitigated by conservative trigger + suppression marker); barring unbacked model citation findings could hide errors format-check cannot express (prose without `file:symbol` form)
- **Breaking Change**: No

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue BUG-3689` against an issue whose Tests section cites a symbol by the importing module rather than the defining module.
2. Compare the per-pass verify summaries in `.loops/.running/<run>.log`.

## Root Cause

Citation verification is performed by the model with ad-hoc reads/greps (the passes reported "direct reads and greps", no graph queries), not by a deterministic check, so coverage varies per pass.

## Acceptance Criteria

- Repeated `--check` passes over an unchanged issue yield the same citation findings (byte-identical `format-check --format json` across two runs; `verify-issues` raises no citation finding that format-check does not back up).
- A bare filename citation is resolved by search (0 / 1 / >1 tracked paths), never reported as a different path.
- A symbol cited via a module that only imports it (BUG-3689's `cli/loop/feed.py:terminal_size()`) is reported `mislocated_symbol_ref` on pass 1, including in Tests / Wiring Phase sections.
- A cited line beyond end of file is reported.
- Planned-new (`(new)`) files are not reported stale.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-01 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Scope vs ENH-3690: B8 governs only a path/line/symbol-location finding that `ll-issues format-check` does not back up — it is demoted to an advisory note and does not affect the verdict. Format-check-backed findings feed ENH-3690's repair route; premise-changing non-citation findings stay `NON_VALID` (ENH-3690).

## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:00 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:verify-issues` - 2026-10-01T22:38:30 - `481f71a6-8878-4664-a5d1-327d85ef26ef.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-01T22:36:37 - `b3ad147a-1b97-4e9e-9ff4-48d129540768.jsonl`
- `/ll:verify-issues` - 2026-10-01T22:29:42 - `a49c8713-7686-4a9e-bacf-5deb614f716c.jsonl`
- `/ll:reconcile-issue` - 2026-10-01T22:27:31 - `63eca4e2-7910-4f8b-a85d-8d3e1f5ace32.jsonl`
- `/ll:verify-issues` - 2026-10-01T22:26:30 - `92efd7c9-cd87-454a-b212-dd9b0cf0e924.jsonl`
- `/ll:wire-issue` - 2026-10-01T22:23:51 - `5e15de52-8cf2-472b-9798-f3ad06f6968f.jsonl`
- `/ll:refine-issue` - 2026-10-01T22:13:27 - `ddfc7f67-a67f-4b84-ae24-829db8cff1f4.jsonl`
- `/ll:format-issue` - 2026-10-01T22:07:09 - `ab89f402-e50e-4f70-99ea-6014766a7a2a.jsonl`
- `/ll:capture-issue` - 2026-10-01T22:03:38 - `8a253271-7b3f-4496-adff-dcad85be0bc1.jsonl`
