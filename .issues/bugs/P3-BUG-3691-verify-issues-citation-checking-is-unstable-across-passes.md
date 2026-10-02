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
verify_verdict: DIRECTIVE_DRIFT
relates_to:
- ENH-3690
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

Move `path:line` / `file:symbol` citation resolution into a deterministic CLI check (like `ll-verify-evidence`) that `verify-issues` runs every pass and treats as ground truth; the model only judges semantic claims.

## Integration Map

### Files to Modify
- `commands/verify-issues.md` - run the deterministic citation check every pass and treat its output as ground truth
- `scripts/little_loops/cli/verify_evidence.py` - existing artifact resolution (`resolve_artifact`, `build_tracked_index`) to reuse for exact full-path lookup only; it is exact-match, so bare filenames resolve through `text_utils.build_ref_index` / `suffix_match_candidates` instead (finding: "`resolve_artifact` is exact-match only")
- `scripts/pyproject.toml` - register the new `ll-verify-*` entry point alongside `ll-verify-evidence`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/verify_citations.py` (new) — new module (`main_verify_citations`, `check_citations`, `extract_citations`, `CitationFinding`); modelled on `main_verify_evidence` in `cli/verify_evidence.py` [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — import `main_verify_citations` and add to `__all__`; the only test enforcing the import is `test_cli_doctor_install_checks.py::TestEntryPoints.test_real_pyproject_all_entry_points_resolve` [Agent 3 finding]
- `scripts/little_loops/init/writers.py` — add `"Bash(ll-verify-citations:*)"` to `_LL_PERMISSIONS` next to `"Bash(ll-verify-evidence:*)"`; no duplicate entries (`test_init_core.py::TestMergeSettings::test_idempotent_on_re_run`) [Agent 1 finding]
- `skills/configure/areas.md` — add `ll-verify-citations` to the "Authorize all ll- CLI tools" option description [Agent 1 finding]
- `commands/verify-issues.md` — frontmatter `allowed-tools` needs its own `Bash(ll-verify-citations:*)` line; add the new step as check **B8** under §2B after check 7 ("Evidence-quote existence check (BUG-3282)") so B6/B7 citations in §C, §2.5, `refine-issue.md` §3.9 and `arm_proposal_revision.py:_NO_EVIDENCE` need no renumbering [Agent 2 finding]
- `skills/ll-verify-issues/SKILL.md` — generated bridge; regenerate with `ll-adapt --host codex --apply`, never hand-edit [Agent 2 finding]
- `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — generated host mirrors of `commands/verify-issues.md`; regenerate with `ll-adapt --host <gemini|qwen|kimi-code> --apply` [Agent 2 finding]
- `.gemini/skills/configure/areas.md`, `.qwen/skills/configure/areas.md`, `.kimi-code/skills/configure/areas.md` — generated mirrors of `skills/configure/areas.md`; regenerate the same way [Agent 1 finding]
- `README.md` and `scripts/README.md` — optional: "52 typed CLI tools" at line 184 is already stale against the 55 `[project.scripts]` entries and is not enforced against `pyproject.toml`; bumping it means editing both files (byte-identical, `test_packaging_duplicate_files.py::test_readme_matches_repo_root`) and the literal in `test_wiring_guides_and_meta.py` [Agent 2 finding]

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
- `scripts/tests/test_verify_evidence.py` - model for a new citation-check test module (stable findings across repeated runs; bare-filename resolution)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_verify_citations.py` (new) — new module; copy `test_verify_evidence.py` helpers (`_git`, `_init_repo`, `_mkissues`, `_write`, `_commit_all`, `repo` fixture, `_run(repo, *args, capsys)`) and the `TestCli` layout; no shared git-repo fixture exists in `conftest.py`, so each module redefines them; cover `extract_citations`, `check_citations`, `main_verify_citations` exit codes, the run-twice byte-identical JSON contract and sorted `ambiguous` candidates [Agent 3 finding]
- `scripts/tests/test_text_utils.py` — `TestBuildRefIndex` shows the inline tmp-git-repo `RefIndex` construction to reuse for the bare-filename case [Agent 3 finding]
- `scripts/tests/test_wiring_cli_registry.py` — add `("docs/reference/CLI.md", "ll-verify-citations", "BUG-3691")` to `DOC_STRINGS_PRESENT` (convention; `test_cli_entry_point_coverage` already fails until the `### ll-verify-citations` CLI.md section exists) [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` — optionally add `("commands/verify-issues.md", "ll-verify-citations", "BUG-3691")` to the presence tuples; `test_host_artifacts_are_not_stale[<host>-commands]` fails for gemini/kimi-code/qwen/codex until mirrors are regenerated [Agent 2 finding]
- `scripts/tests/test_issue_parser.py` — `TestPriorityRegexCompletenessAllowlist._ALLOWLIST` needs `("cli/verify_citations.py", "_ISSUE_ID_RE")` if the new module defines a `P[0-5]-` regex; if `_ISSUE_ID_RE` moves out of `cli/verify_evidence.py` the existing key goes stale — import `resolve_artifact` rather than relocating it [Agent 2 finding]
- `scripts/tests/test_bug3691_verify_issues_citations.py` (new) — new wiring test modelled on `test_enh3126_verify_issues_graph_seeding.py::TestVerifyIssuesFrontmatter` (`Bash(ll-verify-citations:*)` in command frontmatter and in `test_bridge_mirrors_allowed_tools`-style bridge check; B8 step present between check 7 and `#### C. Determine Verdict`) [Agent 3 finding]
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — may break: slices on `#### B. Verify Against Codebase` / `#### C. Determine Verdict` / `Persist the verdict to frontmatter` / `### 3. Request User Approval` via `body.index(...)`; the new B8 text must keep those anchors present and in order [Agent 3 finding]
- `scripts/tests/test_verify_skill_prose.py::TestBaselineNeverIncreases::test_current_tree_baseline_does_not_grow` — may break (`BASELINE_COUNT = 17`) if B8 prose adds `python3 -c` or union-find wording; call the CLI and avoid inline Python JSON filtering [Agent 2 finding]
- `scripts/tests/test_docs_audience_gate.py` — may break if B8 prose cites `scripts/` paths; cite `little_loops.cli.verify_citations` instead [Agent 3 finding]
- `scripts/tests/test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero` and `TestMainVerifyCliAllowlist::test_clean_state_returns_zero` — fail until `writers._LL_PERMISSIONS` and `areas.md` list the new CLI [Agent 3 finding]
- `scripts/tests/test_cli_doctor_install_checks.py::TestEntryPoints::test_real_pyproject_all_entry_points_resolve` — fails until `cli/__init__.py` exports `main_verify_citations` [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` - document the new `ll-verify-*` entry point

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the section must be titled exactly `### ll-verify-citations` (`doc_counts.py:verify_coverage`, enforced by `test_wiring_cli_registry.py::test_cli_entry_point_coverage`) [Agent 3 finding]
- `docs/reference/COMMANDS.md` — describes `/ll:verify-issues` in its `/ll:verify-issues` section; optionally note the deterministic citation check (not gated) [Agent 1 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — lists what `/ll:verify-issues` checks ("Referenced files exist / Referenced functions/anchors exist") under its `/ll:verify-issues` entry; optional note (not gated) [Agent 2 finding]
- `CONTRIBUTING.md` — "Instead, update these files" table is the new-CLI checklist; a per-tool section like "Evidence Quote Verification (ll-verify-evidence)" is needed only if a pre-commit hook or suite gate is added (none planned) [Agent 2 finding]

### Configuration
- N/A or list config files

_Wiring pass added by `/ll:wire-issue`:_
- `.pre-commit-config.yaml` — no change: the `ll-verify-evidence` hook has no counterpart planned for citations (a whole-corpus scan would hit done/old issues, as `.ll/evidence-baseline.json` does) [Agent 2 finding]
- `.github/workflows/ci.yml` — no change: gates run through pytest; `fetch-depth: 0` is needed only for history-index CLIs, and the new check uses `build_tracked_index` / `build_ref_index` (`git ls-files`) only [Agent 2 finding]

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

- `CitationFinding.cited: str`
- `CitationFinding.resolved_path: str | None`
- `CitationFinding.status: Literal["holds", "unresolved", "ambiguous"]`

### Signatures

- `extract_citations(body: str) -> list[str]`
- `check_citations(issue_path: Path, base_dir: Path) -> list[CitationFinding]`
- `main_verify_citations() -> int`

### Call Path

`verify-issues` command -> `main_verify_citations` -> `check_citations` -> `resolve_artifact`

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

1. Add `extract_citations` and `check_citations`: resolve bare filenames through `text_utils.build_ref_index` / `suffix_match_candidates` (0 / 1 / >1 tracked paths → `unresolved` / `holds` / `ambiguous`, ambiguous candidates sorted), and reuse `resolve_artifact` only for exact full-path lookup (it never matches a path without its directory)
2. Add the `ll-verify-citations` CLI entry point and register it in `scripts/pyproject.toml`, `cli/__init__.py`, `init/writers.py:_LL_PERMISSIONS`, and `skills/configure/areas.md` (see Wiring Phase)
3. Update `commands/verify-issues.md` to run the check every pass and treat its findings as ground truth; the model judges only semantic claims
4. Add tests: byte-identical JSON across two runs over an unchanged `tmp_path` git-repo fixture issue, sorted `ambiguous` candidates, and bare-filename resolution; run `python -m pytest scripts/tests/`

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/__init__.py` — import `main_verify_citations`, add to `__all__` (pyproject target is `little_loops.cli:main_verify_citations`)
- Update `scripts/little_loops/init/writers.py` — add `"Bash(ll-verify-citations:*)"` to `_LL_PERMISSIONS`
- Update `skills/configure/areas.md` — add `ll-verify-citations` to the "Authorize all ll- CLI tools" list
- Update `commands/verify-issues.md` — add `Bash(ll-verify-citations:*)` to `allowed-tools` and add check B8 after §2B check 7, mirroring its fail-open wording (non-zero on invocation itself → silent fallback) and treating exit 2 as verification incomplete, never clean; keep the `test_enh3250` anchors in order and avoid `python3 -c` / `scripts/` paths
- Reinstall the editable package (`<interp> -m pip install -e "./scripts[dev]"`, using the interpreter that runs pytest) so `ll-verify-cli-allowlist` sees the new entry point in installed metadata
- Regenerate host mirrors — `ll-adapt --host <gemini|kimi-code|qwen|codex> --apply` for `commands/verify-issues.md` and `skills/configure/areas.md` changes
- Update `docs/reference/CLI.md` — add a `### ll-verify-citations` section
- Update `scripts/tests/test_wiring_cli_registry.py` — add the `DOC_STRINGS_PRESENT` row for `ll-verify-citations`
- Update `scripts/tests/test_issue_parser.py` — add the `_ALLOWLIST` key only if `verify_citations.py` defines a priority-shaped regex
- Add `scripts/tests/test_verify_citations.py` (new) and `scripts/tests/test_bug3691_verify_issues_citations.py` (new) — CLI behaviour (run-twice identical JSON, bare-filename resolution, sorted ambiguous candidates) and command/bridge wiring
- Run `python -m pytest scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py scripts/tests/test_verify_skill_prose.py scripts/tests/test_docs_audience_gate.py` after the `verify-issues.md` edit

## Impact

- **Priority**: P3 - causes a late-pass `GATE_UNMET` run end, but only when a citation defect exists
- **Effort**: Medium - new deterministic check plus skill wiring and tests
- **Risk**: Low - additive check; the model-judged path remains for semantic claims
- **Breaking Change**: No

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue BUG-3689` against an issue whose Tests section cites a symbol by the importing module rather than the defining module.
2. Compare the per-pass verify summaries in `.loops/.running/<run>.log`.

## Root Cause

Citation verification is performed by the model with ad-hoc reads/greps (the passes reported "direct reads and greps", no graph queries), not by a deterministic check, so coverage varies per pass.

## Acceptance Criteria

- Repeated `--check` passes over an unchanged issue yield the same citation findings.
- A bare filename citation is resolved by search and not reported as a different path.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-01 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-10-01T22:38:30 - `481f71a6-8878-4664-a5d1-327d85ef26ef.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-01T22:36:37 - `b3ad147a-1b97-4e9e-9ff4-48d129540768.jsonl`
- `/ll:verify-issues` - 2026-10-01T22:29:42 - `a49c8713-7686-4a9e-bacf-5deb614f716c.jsonl`
- `/ll:reconcile-issue` - 2026-10-01T22:27:31 - `63eca4e2-7910-4f8b-a85d-8d3e1f5ace32.jsonl`
- `/ll:verify-issues` - 2026-10-01T22:26:30 - `92efd7c9-cd87-454a-b212-dd9b0cf0e924.jsonl`
- `/ll:wire-issue` - 2026-10-01T22:23:51 - `5e15de52-8cf2-472b-9798-f3ad06f6968f.jsonl`
- `/ll:refine-issue` - 2026-10-01T22:13:27 - `ddfc7f67-a67f-4b84-ae24-829db8cff1f4.jsonl`
- `/ll:format-issue` - 2026-10-01T22:07:09 - `ab89f402-e50e-4f70-99ea-6014766a7a2a.jsonl`
- `/ll:capture-issue` - 2026-10-01T22:03:38 - `8a253271-7b3f-4496-adff-dcad85be0bc1.jsonl`
