---
discovered_commit: fc652df07b9234f2a79fb0663efd253590b170eb
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: audit-docs
status: done
labels:
- documentation
verify_verdict: VALID
completed_at: '2026-08-16T04:52:44Z'
priority: P4
---

# ENH-3067: 13 modules listed in API.md's overview table have no reference section

## Summary

`docs/reference/API.md` opens with a Module Overview table and then documents each module
under a `## little_loops.<module>` heading. Thirteen modules appear in the table but have no
corresponding section, so the table promises a reference entry that does not exist.

## Current Behavior

The following have an overview row and no `## little_loops.<module>` section:

`pricing`, `stats`, `sft_formatter`, `ab_writer`, `subprocess_utils`, `file_utils`, `sync`,
`decisions`, `decisions_sync`, `output_parsing`, `output_cleaner`, `testing`,
`worktree_utils`.

Readers following the table land on nothing; the one-line table description is the entire
available reference for these modules.

## Expected Behavior

Each listed module either has a section documenting its public surface (classes, public
functions with signatures, and a short usage note), or the overview table marks it
explicitly as "no dedicated section — see source".

## Proposed Solution

Write a `## little_loops.<module>` section per module, following the shape of the existing
sections (e.g. `## little_loops.host_runner`): a one-paragraph purpose statement, then
subsections per public class/function with a fenced signature block.

These are all small, stable modules — `stats` is a single Wilson-interval helper,
`file_utils` is atomic-write wrappers, `worktree_utils` is worktree setup/cleanup. The work
is bounded but real: API.md is already ~10.4k lines and this would add roughly 1k more.

Consider splitting the deliverable per module cluster so it can land incrementally rather
than as one large diff.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Types
- N/A — no new data types. The public dataclasses this issue documents already exist: `ABResults` (`ab_writer.py`), `TokenUsage`/`ToolCall` (`subprocess_utils.py`, frozen), `SyncedIssue`/`SyncResult`/`SyncStatus` (`sync.py`), `DecisionOutcome`/`RuleEntry`/`DecisionEntry`/`ExceptionEntry`/`CouplingEntry` (`decisions.py`, each with `from_dict`/`to_dict`).

### Signatures
Full public surface per module (source: `scripts/little_loops/<module>.py`), to be reproduced in each module's new `## little_loops.<module>` section per the `little_loops.host_runner`/`little_loops.context_window` template shape (see Integration Map):

- `pricing.py`: `estimate_cost_usd(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_creation_tokens: int = 0, is_batch: bool = False) -> float | None`; constants `MODEL_PRICING`, `INTRO_PRICING`, `BATCH_DISCOUNT`.
- `stats.py`: `wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]`.
- `sft_formatter.py`: `to_chatml(turns: list[tuple[str, str]]) -> dict`, `to_alpaca(turns: list[tuple[str, str]]) -> dict`, `to_sharegpt(turns: list[tuple[str, str]]) -> dict`.
- `ab_writer.py`: `calculate_ab_summary(per_item_results: list[dict[str, Any]]) -> ABResults`, `ab_results_to_dict(results: ABResults) -> dict[str, Any]`, `write_ab_json(results: ABResults, run_dir: str) -> None`, `read_ab_json(run_dir: str) -> ABResults | None`, `get_ab_schema() -> dict[str, Any]`.
- `subprocess_utils.py`: `detect_context_handoff(output: str) -> bool`, `read_continuation_prompt(repo_path: Path | None = None) -> str | None`, `read_sentinel(repo_path: Path | None = None) -> dict | None`, `write_sentinel(repo_path: Path | None = None, token_count: int = 0, context_limit: int | None = None) -> None`, `assemble_guillotine_prompt(original_command: str, captured_stdout: str, token_stats: dict, sprint_context: SprintWorkerContext | None = None, issue_id: str | None = None) -> str`, `run_claude_command(...) -> subprocess.CompletedProcess[str]` (18+ kwargs — the module's largest signature).
- `file_utils.py`: `atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None`, `atomic_write_json(path: Path, data: Any) -> None`, `issue_lock_path(issue_path: Path, base_dir: str = ".issues") -> Path`, `acquire_lock(path: Path, timeout: float = 10.0) -> Generator[None, None, None]` (contextmanager).
- `sync.py`: `GitHubSyncManager.__init__(self, config: BRConfig, logger: Logger, dry_run: bool = False) -> None`, `.push_issues(self, issue_ids: list[str] | None = None) -> SyncResult`, `.pull_issues(self, labels: list[str] | None = None) -> SyncResult`, `.get_status(self) -> SyncStatus`, `.diff_issue(self, issue_id: str) -> SyncResult`, `.diff_all(self) -> SyncResult`, `.close_issues(...)`, `.reopen_issues(...)`, `.reconcile_pr_merges(self) -> int`.
- `decisions.py`: `load_decisions(path: Path | None = None) -> list[AnyEntry]`, `save_decisions(entries, path=None) -> None`, `add_entry(entry, path=None) -> None`, `update_entry(entry_id: str, mutate: Callable[[AnyEntry], AnyEntry], path=None) -> None`, `list_entries(path=None, *, type=None, category=None, label=None) -> list[AnyEntry]`, `resolve_active(entries) -> list[AnyEntry]`, `set_outcome(entry_id: str, result: str, measured_at: str, notes: str | None = None, path=None, *, force: bool = False) -> None`, `load_coupling_entries(path=None, *, changed_globs=None, archetype=None) -> list[CouplingEntry]`, `generate_from_completed(config: BRConfig) -> int`.
- `decisions_sync.py`: `sync_to_local_md(path: Path | None = None) -> None`.
- `output_parsing.py`: `extract_tagged_json(raw: str, tag: str) -> tuple[list | dict | None, str | None]`, `parse_sections(output: str) -> dict[str, str]`, `parse_validation_table(section_content: str) -> dict[str, dict[str, str]]`, `parse_status_lines(section_content: str) -> dict[str, str]`, `parse_ready_issue_output(output: str) -> dict[str, Any]`, `parse_manage_issue_output(output: str) -> dict[str, Any]`.
- `output_cleaner.py`: `filter_output(raw: str, *, dup_threshold: int = 1) -> str`.
- `testing.py`: `LLTestBus.__init__(self, events: list[LLEvent]) -> None`, `.from_jsonl(cls, path: str | Path) -> LLTestBus` (classmethod), `.register(self, ext: LLExtension) -> None`, `.replay(self) -> None`, attribute `delivered_events: list[LLEvent]`.
- `worktree_utils.py`: `detect_default_branch(repo_path: Path, git_lock: GitLock | None = None) -> str`, `resolve_epic_base(epic_id: str, base_branch: str, repo_path: Path | None = None, config: object | None = None) -> str`, `resolve_epic_branch_name(epic_id: str, prefix: str, slug: str) -> str`, `setup_worktree(repo_path: Path, worktree_path: Path, branch_name: str, copy_files: list[str], logger: Logger, git_lock: GitLock, base_branch: str | None = None, checkout_existing: bool = False) -> None`, `cleanup_worktree(worktree_path: Path, repo_path: Path, logger: Logger, git_lock: GitLock, delete_branch: bool = True) -> None`, `setup_prepatch_worktree(repo_path: Path, worktree_base: str | Path, base_ref: str, test_files: dict[str, str], logger: Logger, git_lock: GitLock, src_dir: str | None = None) -> Path`, `format_verify_detail(stdout: str | None, stderr: str | None, *, max_lines: int = 40, max_chars: int = 2000) -> str`, `verify_epic_branch_before_merge(...) -> tuple[bool, str | None, int | None]`, `merge_epic_branch_to_base(...) -> bool`, `open_pr_for_epic_branch(...) -> None`.

Representative signatures, one per line, exactly as they will appear in each module's fenced `python` block:

- `estimate_cost_usd(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_creation_tokens: int = 0, is_batch: bool = False) -> float | None`
- `wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]`
- `filter_output(raw: str, *, dup_threshold: int = 1) -> str`

### Call Path
N/A — doc-only change; no new runtime call path is added or modified. The work reads existing, already-defined functions and writes markdown into `docs/reference/API.md`. Grounding anchors (unchanged by this issue): `estimate_cost_usd` (`pricing.py`), `wilson_ci` (`stats.py`), `filter_output` (`output_cleaner.py`).

### Decision Rules
N/A — no new decision logic. The one open choice (write a full section vs. mark a row "no dedicated section — see source") is an existing either/or in `## Expected Behavior`, not a new gap kind, gate, or threshold this issue introduces.

## Impact

- **Priority**: P4 — documentation completeness. No user is blocked; the modules are
  discoverable from source and the overview table gives a one-line orientation.
- **Effort**: Medium — 13 sections of genuine reference prose, each requiring a read of
  the module to get signatures right.
- **Risk**: Low. Doc-only. Main risk is writing signatures from memory rather than
  from source and introducing new staleness — every signature must be copied from the
  module.

## Integration Map

- `docs/reference/API.md` — the Module Overview table (~lines 20–95) and the per-module
  section body
- The 13 modules under `scripts/little_loops/` named above — read for signatures
- `scripts/tests/test_doc_counts.py` — check whether any count claim in API.md is
  gated before/after adding sections

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:1427` — contains a pre-existing markdown link `` [`LLTestBus`](API.md#lltestbus) `` that is currently dangling (no `## little_loops.testing` section exists yet). No edit needed to this file, but the new `little_loops.testing` section must use the exact heading `### LLTestBus` so the anchor slug (`#lltestbus`) resolves once this issue lands. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_reference_docs.py` — append one `(doc_path, string, issue_id)` tuple per new section to `DOC_STRINGS_PRESENT` (e.g. `("docs/reference/API.md", "## little_loops.pricing", "ENH-3067")`), pinning each new heading against future regression. This is the file's existing convention (147 tuples already present, several already keyed on `docs/reference/API.md`); `test_string_present_in_doc` requires no changes. [Agent 3 finding]
- Not adding a structural overview-row/section parity checker (`test_verify_host_map.py`'s `TestCheckDocParity` pattern) — Agent 3 confirmed it's the only precedent for that kind of doc-vs-source-of-truth diff, but building it is materially more work than this issue's doc-only scope and is not required to close the 13 missing sections. Left as a possible future issue, not part of this one.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- `docs/reference/API.md:20-104` — Module Overview table (H2 at line 20, header at 22-23, 83 module rows 24-104). Each of the 13 rows already exists with its own one-line description; the row text does not need to change, only the missing `## little_loops.<module>` sections below the table.
- `docs/reference/API.md:9417-9724` — `## little_loops.host_runner` is the fullest template: H2 → purpose paragraph → fenced `python` import block (matches `__all__` where defined) → one `### ClassName`/`### function_name` per public symbol → `**Fields:**`/`**Parameters:**` table or `**Behavior:**` bullets → trailing `---` before the next `##`. `docs/reference/API.md:2727-2764` (`little_loops.context_window`) is the minimal-viable shape for a small module: one-line summary, one `###` per function, fenced `python` block with the full signature *and* docstring reproduced verbatim, `**Parameters**:`/`**Returns**:` bullets, `**Examples**:` block. Both `---` and no-`---` section endings occur in the file — not a hard rule.
- No precedent exists in `docs/reference/API.md` for the "no dedicated section — see source" opt-out phrasing proposed in `## Expected Behavior`; grepping the file for that phrase returns zero matches. If that path is taken for any module, it establishes new convention rather than following one.
- The 13 modules named in this issue are not the only overview-table rows without a section — `little_loops.logo` (`API.md:44`), `little_loops.loops` (`API.md:63`), and `little_loops.cli_args` (`API.md:64`) are also missing sections and are out of this issue's named scope.
- Module sizes vary far more than the issue's "small, stable" framing suggests. Genuinely small (issue's claim holds): `pricing` (141 lines), `stats` (39), `sft_formatter` (57), `file_utils` (123), `decisions_sync` (58), `output_cleaner` (112), `testing` (104). Substantially larger: `ab_writer` (279), `output_parsing` (514), `decisions` (610), `subprocess_utils` (661), `worktree_utils` (749), `sync` (1176 — largest of the 13, with a stateful `GitHubSyncManager` class). This affects the "split per module cluster" suggestion in Proposed Solution — a cluster boundary drawn by module count alone would put one ~1200-line module in the same batch as several ~50-line ones.
- Files to Modify: `docs/reference/API.md` only — all 13 target modules (`scripts/little_loops/pricing.py`, `stats.py`, `sft_formatter.py`, `ab_writer.py`, `subprocess_utils.py`, `file_utils.py`, `sync.py`, `decisions.py`, `decisions_sync.py`, `output_parsing.py`, `output_cleaner.py`, `testing.py`, `worktree_utils.py`) are read-only sources for signatures, not edit targets.
- Tests: `scripts/tests/test_wiring_reference_docs.py` (`DOC_STRINGS_PRESENT`/`DOC_STRINGS_ABSENT` tuples of `(doc_path, string, issue_id)`) is the only test asserting on `API.md` content, and it checks specific past-issue strings, not section/row parity — adding the 13 sections trips no existing assertion. `scripts/tests/test_doc_counts.py` gates file-system counts in other docs (commands/agents/skills/loops) and has zero references to `API.md`. No generator or checker enforces a 1:1 overview-row-to-section invariant; `API.md` is fully hand-authored.

## Related Key Documentation

- `thoughts/audit-docs-reference-2026-08-05.md` — the docs audit that surfaced this
  (recorded there as a "low, completeness" finding)

## Session Log
- `/ll:manage-issue` - 2026-08-16T04:52:30 - `8b9dc661-91c8-44f1-925c-7a7beb2a263a.jsonl`
- `/ll:wire-issue` - 2026-08-16T04:00:14 - `953e8134-a0de-46ec-8da0-03d0781ca4b7.jsonl`
- `/ll:refine-issue` - 2026-08-16T03:53:58 - `953e8134-a0de-46ec-8da0-03d0781ca4b7.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:11 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`

---

## Status

**Open** | Created: 2026-08-05 | Priority: P4
