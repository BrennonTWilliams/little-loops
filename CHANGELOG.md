# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Windows compatibility testing
- Performance benchmarks for large repositories

## [1.58.0] - 2026-03-21

### Added

- **`ll-history` date range filters** — New `--since` and `--until` flags for `ll-history analyze` to scope analysis to a time window (dcf6bb8f)
- **`ll-issues sequence` type filter** — New `--type` flag to filter sequence output by issue type (b9e3cea6)

### Fixed

- **`INDEX.md` case-sensitivity** — Renamed `INDEX.md` to `index.md` to generate the root `index.html` correctly on case-sensitive filesystems (2d4b046, ad38703)

### Changed

- **Behavioral quality stack** — Replaced completion-as-quality assumption with explicit behavioral quality evaluation in FEAT-849 loop (c290863a)

### Documentation

- **APO loop descriptions** — Expanded APO loop descriptions to block scalars for improved readability (bd023823)
- **FSM evaluator docs** — Documented `diff_stall` and `mcp_result` evaluators, and removed unimplemented paradigm compilation docs (04f73bc8, 66bb0c6c)
- **FSM verdict terminology** — Updated all docs from `success`/`failure` verdict terminology to `yes`/`no` (7f4f505, 7aff407)
- **Docs site branding** — Added site logo/favicon, updated index branding, and removed stale nav entries (a2b2a61)

### Maintenance

- **Cloudflare Pages deployment** — Added `site/` build output to version control for Cloudflare Pages deployment (c8cb43f)

## [1.57.0] - 2026-03-21

### Added

- **`ll-loop history` filters** — New `--event`, `--state`, and `--since` filters for targeted history queries (FEAT-543)
- **`ll-messages` skill/examples flags** — New `--skill` filter and `--examples-format` flags for targeted message extraction (153706b)
- **`workflow-analyzer` default input** — `ll-workflows analyze` now defaults `--input` to the ll-messages pipeline output path (FEAT-559)
- **MkDocs Material docs site** — Full documentation site with Cloudflare Pages deployment config (FEAT-852)
- **`context-health-monitor` FSM loop** — New built-in loop for monitoring and responding to context pressure (3c1f07f)
- **Unified harness example loops** — Example loops merged with built-in loops directory for consistent discoverability (ENH-851)

### Fixed

- **`_find_test_file` path resolution** — Anchors test file search to project root instead of process CWD (ENH-828)
- **Parse errors now logged** — JSONL parse errors emit a warning instead of being silently swallowed (64fbadf)
- **Orphaned worktree branch derivation** — Uses `git rev-parse` for reliable branch name detection in cleanup (BUG-823)
- **`go-no-go` agents authentication** — Removed worktree isolation from adversarial agents to fix "Not logged in" failure (BUG-849)

### Changed

- **`_extract_messages_with_context` performance** — O(n²) inner scan replaced with O(n) single-pass using index map (ENH-827)

### Documentation

- **Loops guide**: harness examples table and `--tail` flag entry (bf4db8d)
- **CLI/COMMANDS reference**: `mcp-call` and `check-code` build mode docs (661cf4a)
- **Workflow analyzer**: updated `--input` flag documentation (6b1f583)

[1.58.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.57.0...v1.58.0
[1.57.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.56.0...v1.57.0

## [1.56.0] - 2026-03-20

### Fixed

- **`--verbose` flag for stream-json with `--print`** — Adds required `--verbose` flag so stream-json output works correctly when `--print` is active (25d4737)
- **Implementation Failure — FEAT-543** — Tracked and resolved failed FEAT-543 implementation attempt (BUG-848)

### Changed

- **Show LLM model name in ll-auto header** — Displays active model name in `ll-auto` run header using stream-json init event (ENH-838)
- **Harness FSM diagram shows all 5 evaluation phases** — LOOPS_GUIDE harness FSM diagram now correctly shows all 5 evaluation phases instead of 3 (ENH-847)

### Maintenance

- style: apply ruff formatting to subprocess_utils and test files (5697233)

[1.56.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.55.0...v1.56.0

## [1.55.0] - 2026-03-20

### Added

- **Sub-loop FSM diagram rendering** — Child FSM diagram renders alongside parent during sub-loop execution with `--show-diagrams` (46bfa69)
- **Sub-loop events forwarded to parent callback** — Sub-loop state transitions are forwarded to parent callback with depth annotation (632bc9a)
- **`ll-sync reopen` subcommand** — Reopen closed GitHub Issues from local issue files (e9df9cb)
- **`--status` flag for `ll-issues count`** — Count issues by status with the new `--status` filter flag (1449881)
- **`--date-field=updated` search** — Search issues by last-updated date using Session Log timestamps (cc192c2)
- **Deferred directory search in `ll-issues show`** — `ll-issues show` now searches deferred issues in addition to active ones (4ad1e72)

### Fixed

- **`StateManager.save` atomic write** — Prevents state file corruption on crash by using atomic write (1dfa79b)
- **`_current_process` tracking in FSMExecutor** — Adds `_current_process` tracking to `FSMExecutor._run_subprocess` for reliable subprocess management (f0a270f)
- **Missed handoff signals failure** — Missed continuation handoff now correctly signals failure with `returncode=1` (642a477)
- **Parent state highlighted during sub-loop execution** — Parent FSM diagram keeps current state highlighted while sub-loop runs (4f124df)
- **Configurable `remote_name` in `ll-parallel` and `ll-sprint`** — Hardcoded "origin" remote replaced with configurable `remote_name` option (f62e476)
- **Undefer issue commits undeferred section** — `undefer_issue` now correctly commits the undeferred section (3aa2738)
- **`ll-parallel` leak detection uses configured src/test dirs** — Leak detection now respects `src_dir`/`test_dir` from config instead of hardcoding paths (cf1aba2)
- **Comma-separated `--priority` in `ll-issues`** — `ll-issues list` and `ll-issues count` now accept comma-separated priority values (887dbeb)
- **Logger type fix in `load_loop`** — Corrects Logger type annotation in `load_loop` call (2934b4c)
- **YAML block sequence frontmatter parsing** — Parses YAML block sequences in issue frontmatter without spurious warnings (964c0fb)
- **Lint errors resolved** — Fix lint errors and reformat to pass ruff checks (548be51)

### Changed

- **Documentation: `ll-gitignore` CLI tool** — Added `ll-gitignore` to CLAUDE.md and README documentation (2e65c0e)
- **Documentation: sub-loop FSM diagram `--show-diagrams`** — Added guide for visualizing sub-loop execution (789d338)
- **Documentation: harness FSM diagram annotation** — Simplified annotation and fixed inaccuracies in harness FSM diagram guide (76663a9, 7271b44, 8a8dc63)
- **Documentation: CLI flags** — Added `--context-limit`, `--priority`, `--idle-timeout`, `--builtin` flags and new sort fields to CLI reference (69f2dba, f3d0dae)
- **Documentation: README ll-sync subcommands** — Added `diff`, `close`, `reopen` subcommands and bumped CLI tool count to 13 (63263bc, f4dc17a)

[1.55.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.54.0...v1.55.0

## [1.54.0] - 2026-03-19

### Added

- **Example FSM harness loops** — Built-in harness loop examples for automatic harnessing workflows (198abf8)
- **`/ll:go-no-go` skill** — Adversarial issue assessment that stress-tests implementation plans before coding begins (202d59f)
- **Auto-detect model from JSONL in context monitor** — Context monitor reads session JSONL to detect which model is active and select the correct context limit (0cfbc0c)

### Fixed

- **FSM tmp paths scoped to project CWD** — Temporary files created by FSM loops are now scoped to the project directory, preventing cross-project collisions (3dde2d0)
- **`general-task` plan file scoped to project dir** — Plan files are now project-scoped, avoiding conflicts between concurrent sessions (828086d)
- **`ll-continue-prompt.md` write permission** — Added `Write(ll-continue-prompt.md)` to canonical permissions so handoff no longer prompts for approval (BUG-811)
- **Context monitor default limit raised from 150K to 1M** — Prevents premature handoffs on modern models with large context windows (BUG-809)

### Changed

- **FSM diagram visual improvements** — State box titles are bold; transition line characters are color-coded by edge type; edge label colors are configurable via `ll-config.json` (1da47fb, 8fc6508, 49d574f)
- **`analyze-loop` name-based analysis scoped to most recent execution** — Avoids false positives from older loop runs with the same name (7cf3373)
- **Context monitor uses JSONL transcript baseline** — More accurate token estimation via JSONL transcript rather than conversation estimates (8749815)
- **`on_handoff` set to `spawn` across all built-in loop configs** — Ensures consistent session handoff behavior (533cc27)

## [1.53.0] - 2026-03-18

### Added

- **`--priority` filter for `ll-auto`** — Filter issue processing by priority level; also fixes validation in `ll-parallel` (b2d242d)
- **FSM state box unicode composition badges** — State boxes now render unicode badges indicating state type, replacing text annotations (fca522b)

### Fixed

- **Route states missing unicode badge in FSM diagram** — `_get_state_badge()` now checks `state.route` so routing/branching states receive a distinct visual badge (BUG-806)
- **Numeric-only `--only` filter support** — `ll-auto`, `ll-parallel`, and `ll-sprint` now correctly accept numeric-only values for the `--only` filter (4d0942a)

### Changed

- **FSM state box badge moved to top border** — Badge character is now embedded in the box's top border line with one space of padding on each side, rather than appearing in the first content row (ENH-807)

### Documentation

- Fixed documentation accuracy issues across 5 guide files: LOOPS_GUIDE (10 fixes), AUTOMATIC_HARNESSING_GUIDE (10 fixes), SESSION_HANDOFF (8 fixes), WORKFLOW_ANALYSIS_GUIDE (9 fixes), SPRINT_GUIDE (5 fixes) (9ab98f1, 1026be3, f6a32a0, 159a2e2, d739fa2)

## [1.52.0] - 2026-03-17

### Added

- **Hierarchical sub-loop states for composable FSM loops** — FSM loops can now delegate to specialized sub-loops as named states (930fd7e)
- **Evaluation-quality FSM loop** — Built-in loop for multi-dimensional health checks across quality dimensions (d6dc7e4)
- **`plan` state in `general-task` loop** — Decomposes tasks into steps before execution for improved planning (fc42348)
- **`testable` field in `IssueInfo` dataclass** — Tracks whether an issue can be automatically validated (ENH-800)
- **Auto-detect `testable: false` for doc-only issues** — Pipeline and `manage-issue` automatically mark documentation-only issues as non-testable (ENH-802)

### Fixed

- **LLM evaluator uses `--json-schema` flag** — Prevents LLM preamble from corrupting structured output in evaluators (BUG-794)
- **`on_error` handlers in issue-refinement loop prompt states** — Prevents silent failures when prompt states encounter errors (BUG-773)
- **RL coding agent stall detection and live LLM judge** — More accurate stall detection with live LLM judging prevents false stalls (ENH-793)

### Changed

- **`analyze-loop` distinguishes intentional cycling from stuck retries** — Retry flood detection no longer conflates on_no routing with true stuck retries (ENH-775)
- **`create-loop` wizard uses structural patterns** — Templates and questions refactored to guide users toward pattern-based loop design (ENH-756)
- **`parse_frontmatter` warns on unsupported YAML syntax** — Surfaces warnings when YAML lists or colon-containing values are silently dropped (ENH-693)
- **`rl-coding-agent` reads `test_cmd`/`lint_cmd` from `ll-config.json`** — Agent uses project-configured commands instead of defaults (ENH-793)
- **`issue-history` uses `statistics.linear_regression`** — Replaced manual OLS implementation with Python standard library (5aad93f)
- **BFS edge case coverage for coupling cluster analysis** — Added tests for `_build_coupling_clusters` edge cases (ENH-697)

### Documentation

- **Sub-loop composition guide** — Architecture and guides updated to cover hierarchical sub-loop composition patterns (cee79f5)
- **Claude Code structured outputs guide** — New guide covering structured output generation with `--json-schema` (b1bf58f)
- **Docs accuracy fixes** — Corrected `diff_stall` verdicts, `capture_template` config, and loops catalog entries (9e2840b)

## [1.51.0] - 2026-03-16

### Added

- **Enhance `ll-sprint show` CLI Output Styling** — Colorized output and improved visual formatting for sprint status (ENH-745)
- **`plan_call` Action Type for FSM States** — New FSM action type that invokes plan mode during state execution (ENH-778)
- **`rl-coding-agent` Policy+RLHF composite loop** — New built-in loop combining policy gradient and RLHF for coding agent workflows (a124f8e)
- **`ll-gitignore` CLI command** — New command to expose the built-in gitignore suggestion library (d24aaf2)
- **`--sort`/`--asc`/`--desc` flags for `ll-issues list`** — Sort issue list output by any field in ascending or descending order (e8dcf75)
- **`--limit`/`-n` flag for `ll-issues list`** — Cap list output to N issues (3cb3013)
- **Confidence-check Phase 4.5 findings write-back** — Confidence check now persists Phase 4.5 evaluation findings back to issue files (64e650d)
- **Error states and `on_handoff` pause in RL loop configs** — RL loops handle error states and support pausing on handoff events (a04e5b3)
- **`EntityCluster.span` and `inferred_workflow` in workflow-analyzer** — Enriched entity cluster data with temporal span and inferred workflow context (8bfef3e)

### Changed

- **Init validates hook script dependencies and version alignment** — Step 9.5 hook dependency validation added to the init wizard (ENH-705)
- **Preserve `--only` argument order in `ll-auto`** — Issue processing order now matches the order arguments were provided (2e16ae0)
- **Type misclassification detection in `normalize-issues`** — Detects and flags issues filed under an incorrect type (1ca7753)

### Fixed

- **`analyze-loop` no longer treats exit_code=1 as failure when `on_no` is defined** — Prevents false failure signals when a no-branch is configured (d695b62)
- **Loop evaluate classifier splits `NEEDS_FORMAT` from `NEEDS_VERIFY`** — Cleaner evaluation state distinction avoids conflating format and verify signals (483ab8d)
- **Session log skips fake `## Session Log` headings in code blocks** — Uses last-match strategy to avoid false positives from headings inside fenced code (d6386c8)
- **`ll-issues list` display text normalization** — Fixed inconsistent output text in the list subcommand (9fdfdff)

## [1.50.0] - 2026-03-16

### Added

- **Loop-level `default_timeout` for FSM executor** — Per-state action timeout fallback eliminates hardcoded timeouts and per-state annotations (ENH-777)
- **APO built-in loops** — OPRO, beam search, and TextGrad loops for automatic prompt optimization (1694797, 1dc689d, 5e471a8, a87703f)
- **RL built-in loop types** — `rl-bandit`, `rl-rlhf`, and `rl-policy` reinforcement-learning loop variants (affc355)
- **TDD issue implementation loop** — Built-in loop for test-driven development workflows (0dcb159)
- **`--handoff-threshold` flag** — Added to `ll-loop run` and `resume` for session handoff control (32b9360)
- **`--status` flag for `ll-issues list`** — Filter issues by status in the list subcommand (a476fb3)
- **`allowed-tools` area in configure skill and init wizard** — Configure allowed tools interactively (748d398)

### Fixed

- **Friendly error for missing context variables** — Loop executor now surfaces clear messages when context vars are absent (5c6e8d6)
- **APO convergence check on_error routing** — Route to `generate_variants` instead of failing on convergence errors (e3bc2ab)
- **`general-task` loop on_error routing** — Added on_error routing and failure terminal to prevent silent hangs (31336cd)

### Changed

- **Dynamic column elision in refine-status** — Narrow terminal widths now gracefully elide lower-priority columns (814f12b)

## [1.49.0] - 2026-03-15

### Changed

- **Add route_create guard to sprint-build-and-validate** — Prevents invalid route creation in sprint build loops (f5dfd76)
- **Remove one-off workflow loops from built-in catalog** — Cleans up catalog of ad-hoc loops not intended for general use (b8dad90)

### Fixed

- **FSM on_blocked shorthand field and routing branch** — Added `on_blocked` shorthand support with proper routing branch handling (a428d91)
- **LLM evaluation timeout raised to 1800s** — Default timeout increased from 30s to prevent premature evaluation failures (9fda9ca)
- **Context variable interpolation in llm_structured evaluate prompt** — Properly interpolates context vars in evaluation prompts (f565209)

### Documentation

- Fixed three inaccuracies in harnessing guide (bae4fdf)

## [1.48.0] - 2026-03-15

### Changed

- **Parameterized confidence thresholds in sprint-build-and-validate** — Added `readiness_threshold` and `outcome_threshold` to loop context with defaults (85/70), replaced 3 hardcoded occurrences, with runtime override support (8118b99)

### Fixed

- **FSM diagram label truncation** — Corrected back_edge_margin calculation and non-adjacent edge label placement (714e862)

### Documentation

- Marked all 18 skills with ^ suffix in COMMANDS.md Quick Reference to distinguish from commands (3e8f7cd)
- Refined ENH-753 and ENH-757 with complete codebase reference maps and confidence scoring
- Corrected skill count from 17 to 18 in CLAUDE.md

## [1.47.0] - 2026-03-15

### Added

- **--handoff-threshold CLI override** — Added to ll-auto, ll-parallel, ll-sprint for per-run session handoff threshold configuration (8475824)
- **--type filter for impact-effort** — New `--type` flag on `ll-issues impact-effort` to filter by issue type (b6dd14e)
- **--json output for ll-loop** — `ll-loop status` and `ll-loop show` now support `--json` for machine-readable output (968ce1c)
- **--json output for ll-issues** — `ll-issues show` and `ll-issues sequence` now support `--json` for machine-readable output (740bafb)

### Documentation

- Fixed default_max_workers value in SPRINT_GUIDE (ed3bb0b)
- Fixed two inaccuracies found during reference docs audit (dca73b6)
- Fixed stale skill counts and documented missing ll-issues subcommands (28d969a)
- Documented --handoff-threshold flag in CLI reference and SESSION_HANDOFF guide (c12b368)
- Added check_skill evaluation phase for skill-as-judge verification (fea5775)
- Documented MCP tool gates as optional evaluation phase (8933eb6)
- Documented --json and --type flags added in FEAT-701/702/703 (2305d6b)

## [1.46.0] - 2026-03-15

### Added

- **Update-docs skill** — Automated documentation maintenance triggered by code changes (FEAT-751)
- **MCP tool action type for FSM Loops** — New `action_type: mcp_tool` with MCP result evaluator support (FEAT-729)
- **ll-loop positional string input** — `ll-loop run` now accepts a positional string input argument (FEAT-725)
- Automatic Harnessing Guide for FSM loops (9ff9ae6)

### Fixed

- **Loop `/tmp` scratch files use global names** — Fixed cross-project conflicts from non-unique scratch file names (BUG-744)
- **format-issue --auto `formatted` flag** — Fixed flag never being set, causing infinite loops in issue-refinement (BUG-743)

### Changed

- **Verbose loop history LLM call details** — Loop history verbose mode now shows full LLM call details (ENH-740)
- **Stall detection via diff comparison** — FSM loops now detect stalls by comparing state diffs (ENH-714)
- **Deferred `detect_regression_or_duplicate`** — Lazy evaluation eliminates eager calls for displaced matches (ENH-691)

## [1.45.0] - 2026-03-14

### Added

- **4-section anchored schema for session handoff** — `handoff` skill now uses a structured 4-section schema for richer session continuity (ecaff979)
- **Session linking for loop history** — Loop history now captures session IDs for prompt states, enabling cross-session traceability (c1579dc)
- **Per-state retry limits for FSM** — FSM states support `max_retries` and `on_retry_exhausted` for fine-grained retry control (4f68e5a)
- **`ll-issues search` subcommand** — New search subcommand with filters and sorting for issue discovery (221c059)

### Fixed

- **FSM yes/no schema** — Updated schema and validation to use `on_yes`/`on_no` fields replacing `on_success`/`on_failure` (357073a)
- **Loop CLI display** — Updated CLI display to reflect yes/no verdict rename (dd6b854)
- **Loop config files** — Updated built-in loop configs for yes/no verdict and on_yes/on_no rename (169e588)
- **Quality checks** — Resolved lint, format, and type check failures (70ce0f4)

### Changed

- **FSM verdict naming** — Renamed `success`/`failure` verdicts to `yes`/`no` and `on_success`/`on_failure` to `on_yes`/`on_no` for clearer semantics (a18e79e, 45c9956)
- **`review-loop` LLM state detection** — Detects replaceable LLM prompt states for optimization recommendations (63d0b19)
- **Config module refactor** — Split `config.py` into a `config/` subpackage for better organization (cde1bbe)
- **Issue history deduplication** — Extracted `get_issue_content()` helper eliminating 10 code duplicates (b1be301)
- **Issue discovery performance** — Deferred `detect_regression_or_duplicate` to after loop in Passes 2 and 3 (26b8d06)

## [1.44.0] - 2026-03-14

### Added

- **`ll-issues append-log` subcommand** — New CLI subcommand for appending session log entries; five commands (`refine-issue`, `verify-issues`, `scan-codebase`, `tradeoff-review-issues`, `ready-issue`) now use the CLI instead of direct Bash calls (ENH-747)

### Changed

- **Sprint planner worktree safety** — Separated `overlaps_with()` and `contends_with()` in `FileHints`; `ll-parallel` now uses the more conservative `contends_with()` to prevent false positive file-overlap serialization (ENH-746)

## [1.43.0] - 2026-03-14

### Added

- **Suggest FSM loop configs from commands, prompts, and workflows** — `loop-suggester --from-commands` mode analyzes the command and skill catalog to propose ready-to-use FSM loop configurations (FEAT-716)
- **Loop run history archiving** — Loop runs are now archived to `.loops/.history/` before clearing, enabling persistent history retrieval across sessions (FEAT-733)
- **Harness loop type for `create-loop`** — New `Harness` loop type wraps existing skills and prompts into FSM loops without custom state logic (469a98f)
- **plugin-health-check convergence FSM loop** — Extended the `plugin-health-check` built-in loop into a full convergence FSM loop with self-healing transitions (bc2f910)
- **`description` field for FSMLoop schema** — FSM loop definitions now support an optional human-readable description field (c7ed2b8)
- **Workflow analyzer cross-references** — Workflow analyzer cross-references workflows to entity clusters and populates `handoff_points` for richer handoff context (27f482d)
- **backlog-flow-optimizer built-in loop** — New `backlog-flow-optimizer` loop replaces `issue-throughput-monitor` with improved flow-based optimization (81500eb)

### Fixed

- **Loop scratch files use project-scoped directory** — Scratch files now write to `.loops/tmp/` instead of system `/tmp/`, preventing cross-project collisions (9ddd8d1)
- **`format-issue` session log in auto mode** — Fixed programmatic session log write in auto mode (0b7fccb)
- **FSM diagram back-edge connector rendering** — Fixed rendering glitches in back-edge connectors (c5704ca)
- **Built-in loop configs audit** — Removed `secret-scan` loop and updated semantics across multiple built-in loop configs (10f9873, 09562b7)
- **`docs-sync` loop `on_error` routing** — Added missing `on_error` routing to `route_results` state in the docs-sync loop (35d39c4)
- **Issue refinement budget exhaustion** — Prevented budget exhaustion on stubborn issues in the `issue-refinement` loop (9a0abf3)

### Changed

- **Stall detection via diff comparison** — New `diff_stall` evaluator detects FSM iteration stalls by comparing successive diffs (ENH-714)
- **`ll-loop list` visual polish** — Colorized output matches `ll-issues` quality with priority and status indicators (ENH-715)
- **`ll-loop history --verbose` LLM details** — Verbose history output now includes LLM call counts and token details per iteration (8a881e6)
- **`create-sprint` surfaces refinement status** — Sprint creation now shows issue refinement status to help curate sprint candidates (1ddae71)
- **`ll-loop init` wizard simplified** — Removed product analysis and auto-timeout prompts from the interactive initialization wizard (6a333fb)
- **FSM BFS optimization** — Replaced `list.pop(0)` with `deque.popleft()` for O(1) BFS traversal (c452331)

## [1.42.0] - 2026-03-13

### Added

- **Parallel merge coordinator** — New merge coordinator for `ll-parallel` enabling concurrent issue processing with safe state transitions (76cb72d)

### Fixed

- **FSM layout: same-layer connectors occluding intermediate state boxes** — Prevented connectors on the same layer from drawing over intermediate state boxes (6057136)
- **`IssueManager`: too-narrow except clause in `gather_all_issue_ids`** — Broadened except to catch `ImportError`, `OSError`, and all other exceptions to prevent `IssueManager` construction crashes (BUG-690, 548c386)
- **FSM: SIGKILL'd prompt actions route to next state instead of shutdown** — Route prompt actions terminated by SIGKILL to the shutdown state (6c33e5f)
- **Merge coordinator: unprotected `_current_issue_id` reads and writes** — Added locking around `_current_issue_id` access for thread safety (dc5470b)
- **Orchestrator: unprotected concurrent state mutations** — Added `_state_lock` to protect concurrent state mutations in the orchestrator (76b0a52)
- **WorkerPool: unprotected `_active_workers` reads and writes** — Added locking to `_active_workers` for thread-safe worker pool management (1bbdd99)
- **Merge coordinator: `_current_issue_id` not cleared on error exit** — Wrapped `_process_merge` in outer try/finally to guarantee `_current_issue_id` is cleared (e1652dd)
- **Subprocess: ambiguous returncode check** — Replaced `returncode or 0` with explicit `None` check to correctly handle zero exit codes (fc0b331)

## [1.41.0] - 2026-03-13

### Added

- **`--clear` flag for `ll-loop run` and `resume`** — Emits ANSI clear-screen before each iteration; combine with `--show-diagrams` for a live in-place FSM dashboard. Suppressed when stdout is not a tty (ENH-718)
- **`--delay <SECONDS>` flag for `ll-loop run` and `resume`** — Inserts an interruptible pause between FSM iterations; useful for recording terminal sessions. Overrides `backoff:` from the loop YAML. (ENH-735)
- **`ll-loop analyze` skill** — Synthesizes actionable issues from loop execution history; captures patterns across iterations into BUG/ENH/FEAT issue files (FEAT-719)
- **20 built-in FSM loop definitions** — Common dev workflow loops bundled with `ll-loop` for immediate use (c1b18fe)

### Fixed

- **FSM diagram disconnected box-drawing junction characters** — Upgraded box-drawing corners to junctions on character collision (BUG-710)
- **`issue-refinement` loop: three logic defects** — Fixed counter reset, LLM-managed iteration, and LLM ceiling-acceptance defects (BUG-720)
- **`issue-refinement` loop: LLM parses issue ID instead of shell** — Replaced LLM-driven ID extraction with deterministic shell `parse_id` state (BUG-721)
- **`--show-diagrams` suppressed by `--quiet`** — Allow `--show-diagrams` to work alongside `--quiet` (BUG-727)
- **`--json` flag missing from `ll-loop history` and `ll-loop list --running`** — Added `--json` support to both subcommands (b27bd30)
- **FSM bugs across built-in loop configs** — Audited and fixed 18+ bugs across 24 built-in FSM loops plus 6 simplifications (5867dbd, 1708235, d66c3ac)
- **FSM layout: multi-branch horizontal connector gaps** — Connected multi-branch horizontal connectors across source box gaps and skip-layer edge horizontals (f8ba63c, 6ebff0e)
- **`format-issue` missing confidence gate** — Added confidence gate to interactive mode questions (8c8c3cd)

## [1.40.0] - 2026-03-12

### Added

- **`--check` flag for issue prep skills** - Added check-only evaluation mode with exit code routing for FSM loop evaluators across 8 skills (ENH-668)
- **`--auto` flag for issue prep skills** - Non-interactive mode for verify-issues, map-dependencies, and issue-size-review with conservative defaults (ENH-669)
- **`count` sub-command for `ll-issues`** - Lightweight issue volume queries with `--type`, `--priority` filters and `--json` output (ENH-677)
- **`issue-discovery-triage` builtin loop** - New FSM loop for automated issue discovery and triage (2a515c6)

### Fixed

- **FSM diagram branch edges to terminal states not rendered** - Added right-margin forward-skip edge renderer for edges spanning 2+ layers (BUG-678)
- **FSM diagram main-path cycle edges not rendered** - Extended edge reclassification to scan forward_edge_labels for backward-pointing main-path edges (BUG-679)
- **`init --interactive` does not create .issues directory structure** - Refactored interactive init to auto-detect and create issue directories (BUG-656)
- **Dependency mapper inflated default scores** - Applied overlap guards and fixed scoring in dependency mapper (30a0453)
- **Refine-status table too wide for narrow terminals** - Reduced column widths saving ~21 chars per row (ENH-676)
- **`ll-loop show` States section visibility** - Gated States section behind `--verbose` flag (0f87a97)
- **Test: add issue-discovery-triage to expected builtin loops set** (00b639c)

### Changed

- **Optimize FSM diagram edge classification** - Replaced O(n) `bfs_order.index()` calls with O(1) dict lookup (ENH-542)
- **Add `/ll:review-loop` to COMMANDS.md reference** (ENH-680)
- **Documentation updates** - Fixed stale counts, paths, and missing entries in ARCHITECTURE and CONTRIBUTING (a57e67c)

## [1.39.0] - 2026-03-11

### Added

- **Adaptive layout engine for FSM diagrams** - New layout engine that automatically adjusts FSM diagram geometry based on graph structure (5f2df71)
- **`--json` flag for `ll-issues`, `ll-loop`, and `ll-sprint` list commands** - Machine-readable JSON output for all list subcommands (7f88574, 8477dda)

### Fixed

- **FSM back-edge rendering: corner characters and arrow direction** - Corrected corner chars and arrow direction for back-edge pipes; consolidated three successive fix iterations (8c35e70, 48703d5, 3f33e0b)

### Changed

- **Remove deprecated paradigm compilation system** - Removed `compile_paradigm` from FSM engine runtime load path and deleted deprecated paradigm compilation code (09c83ab, d0692bd)
- **Remove 4 Paradigms concept from docs** - Updated all documentation to reflect FSM YAML as the canonical loop format (c6021ef)

## [1.38.0] - 2026-03-09

### Added

- **New `/ll:review-loop` FSM Loop Quality Auditor** - Comprehensive skill for auditing FSM loop configurations, analyzing logic, and suggesting improvements (FEAT-660)
- **Issue-refinement-git FSM loop** - Automated issue refinement workflow using git integration (88baf5d)

### Fixed

- **FSM Diagram Off-Path Arrows and Back-Edges Broken** - Fixed rendering of off-path arrows and back-edges in FSM diagrams for multi-state chains (BUG-664)
- fix(review-loop): rename FA-N checks to QC-8/QC-13 to prevent early termination (e99931c)

### Changed

- **Add Unknown-Key Detection to `load_and_validate()`** - Improved FSM validation with detection of unknown keys in loop configurations (ENH-661)
- **review-loop FSM Logic Analysis Phase** - Enhanced review-loop with comprehensive FSM logic analysis and evaluation (ENH-662)
- **Extract Shared `_process_alive` to Eliminate Duplication** - Refactored concurrency module to eliminate code duplication between `concurrency.py` and `lifecycle.py` (ENH-537)
- **Pre-resolve Scope Paths to Eliminate O(n×m) stat Calls** - Performance optimization for `_scopes_overlap` path resolution (ENH-629)
- **FSM Test Coverage for `maintain` Mode and `direction="maximize"`** - Added missing executor-level tests (ENH-538, ENH-631)

## [1.37.3] - 2026-03-09

### Fixed

- **Correct FSM diagram for linear off-path chains** - Fixed FSM diagram rendering where linear off-path chains were not correctly represented in the state machine visualization (BUG-658)

## [1.37.2] - 2026-03-08

### Fixed

- **`ll-loop history` `--tail` counts suppressed `action_output` events, hiding earlier iterations** - Filters `action_output` events before applying `--tail` so iteration history is not crowded out by verbose shell output (BUG-657)

## [1.37.1] - 2026-03-08

### Fixed

- fix(issues): refine BUG-656 with root cause, solution, and confidence scores (7975326)

### Changed

- improve(init): remove 11 interactive prompts and use sensible defaults (eb70156)

### Documentation

- docs: update install instructions to reference PyPI package (58f27dc)

## [1.37.0] - 2026-03-08

### Added

- **TDD Mode in Round 3a advanced features** - Moved TDD Mode selection to Round 3a advanced features during `ll-init` setup (feat(init): 2045a2a)

### Fixed

- **Off-Path State Highlighting Missing in FSM Diagram** - Fixed `ll-loop run --show-diagrams` to properly highlight off-path states with green borders and bold text when they become the active state (BUG-655)
- fix(config): replace hardcoded issue paths with config-driven resolution (ed5b3ad)
- fix(schema): align worktree_copy_files default with code (470ef08)
- fix(config): add test_dir field to ProjectConfig (ce3fc59)
- fix(schema): correct default_max_workers default from 4 to 2 (e783ae7)

### Changed

- docs(schema): add three undocumented config fields to config-schema.json (aadf455)
- docs(issues): clarify skills in README and update FEAT-638 verification logs (93411ce)

## [1.36.1] - 2026-03-07

### Fixed

- **ll-issues refine-status ID column truncates 4-digit FEAT IDs** - Replaced hardcoded `_ID_WIDTH = 8` with a dynamic column width computed from the longest issue ID in the dataset (BUG-647)

### Changed

- **API.md missing documentation sections** - Added documentation for `work_verification`, `session_log`, config classes (`SprintsConfig`, `LoopsConfig`, `GitHubSyncConfig`, etc.), FSM submodules (`handoff_handler`, `concurrency`, `signal_detector`), parallel types, and CLI entry points (ENH-646)

[1.37.3]: https://github.com/BrennonTWilliams/little-loops/compare/v1.37.2...v1.37.3
[1.37.2]: https://github.com/BrennonTWilliams/little-loops/compare/v1.37.1...v1.37.2
[1.37.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.37.0...v1.37.1
[1.37.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.36.1...v1.37.0
[1.36.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.36.0...v1.36.1

## [1.36.0] - 2026-03-07

### Added

- feat(loop): add `--show-diagrams` flag to `ll-loop run` and `resume` — display FSM box diagram with active state highlighted during verbose run (cbae36b, 8d6585d)
- feat(loop): add `--context KEY=VALUE` CLI override for `run` and `resume` (f307e13)
- feat(loop): add `--exit-code` to `ll-loop test` for slash-command states (952e653)
- feat(fsm): add numeric range checks to `validate_fsm` (db4d8e0)
- feat(fsm): add `on_stall` override to convergence paradigm compiler (7ad4673)
- feat(compilers): add `on_partial_target` field to all paradigm compilers (c101325)
- feat(simulate): add all-error scenario for non-interactive error-verdict testing (b8c060a)

### Fixed

- fix(evaluators): raise `ValueError` when `output_numeric` or convergence target is `None` (e17c3d3)
- fix(evaluators): guard `output_numeric` target against non-numeric strings (c2860a8)
- fix(executor): drain stderr in background thread to prevent pipe deadlock (d961aab)
- fix(fsm): remove `on_error="fix"` from `compile_goal` evaluate state (ea6d525)
- fix(fsm): clear `_pending_error` on resume alongside `_pending_handoff` (37700a7)
- fix(loop): write PID file for foreground runs so `cmd_stop` sends SIGTERM (df233e6)
- fix(loop): forward `--verbose` flag to background process (f6edb97)
- fix(persistence): map timeout termination to `timed_out` status (7096c9c)
- fix(validation): add `on_partial` to `_validate_state_routing` shorthand check (763823a)
- fix(handoff): anchor continuation prompt path to project root (9c8232a)
- fix(issue_parser): add session log check to `is_formatted` (28622fe)
- fix(docs): correct API.md signatures, data class schemas, and goals_parser reference (c242966, 955c370, 31f8165)
- fix(docs): correct `$schema` relative path in CONFIGURATION.md example (e3d018a)

### Changed

- refactor(fsm): extract `_is_prompt_action` helper in `FSMExecutor` (cd0b742)

[1.36.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.35.0...v1.36.0

## [1.35.0] - 2026-03-06

### Added

- feat(ll-loop): add paradigm/description display and --status filter to list (9549f7a)
- feat(workflows): add --format json output option to ll-workflows analyze (d6f7c10)
- feat(workflows): add per-stage verbose progress to analyze_workflows (1e49376)
- feat(workflows): expose overlap_threshold and boundary_threshold via CLI and API (4a7e87d, 63a7a41)
- feat(cli): add --idle-timeout flag to ll-auto and ll-parallel (58d9889)
- feat(sprint): add --only flag to ll-sprint run (7f251e6)
- feat(ll-loop): add --state flag to ll-loop test (5f67587)
- feat(ll-loop): add --background flag to resume command (8c5dc4d)

### Fixed

- fix(file-hints): require colon delimiter in scope/component pattern (9de08ed)
- fix(sprint): route BLOCKED verdict to skipped_blocked_issues, not failed (e789a46)
- fix(sprint): prevent stale orchestrator state loading on fresh wave run (23cc8a2)
- fix(ready-issue): add BLOCKED verdict for unresolved blocking dependencies (b295b2e)

[1.35.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.34.0...v1.35.0

## [1.34.0] - 2026-03-06

### Added

- **Fix `ll-loop show` box truncation and add diagram centering** (ENH-589)
- **Colorize ll-issues show card output** (ENH-593)
- **Colorize ll-loop run output** (ENH-595)
- **Colorize ll-issues refine-status output** (ENH-596)
- feat(doc-scraper): add BoundaryML docs scraper and scraped output (5dcbb2c)
- feat(cli): add subcommand aliases to ll-issues, ll-loop, and ll-sprint (e5d428e)

### Fixed

- fix(persistence): remove redundant route-event state save (f284a1c)
- fix(loop): map terminated_by to distinct exit codes (83de39f)
- fix(loop): remove PID file after SIGTERM/SIGKILL stop (7f9fead)
- fix(persistence): warn on corrupted state file instead of silently returning None (ebf96f5)
- fix(loop): use FSMLoop.to_dict() in cmd_compile to preserve all fields (31140c8)
- fix(loop): extract signal handler to _helpers and register in cmd_resume (32e2f1c)
- fix(cli): normalize args.command to canonical name for subcommand aliases (89078d8)
- fix(workflow-analyzer): handle malformed JSONL lines in _load_messages (9090819)

## [1.33.1] - 2026-03-05

### Fixed

- **FSM diagram off-path states side-by-side** - Off-path FSM states now render side-by-side instead of stacking vertically (BUG-598)
- **issue-refinement loop infinite cycle** - Resolve 5 infinite cycle bugs caused by fmt/priority issues in the loop configuration (BUG-599)

### Changed

- **fix-quality-and-tests loop** - Run tests via shell for improved test execution in the quality gate loop (ea06153)
- **issue-refinement loop** - Remove map-dependencies step and tests-until-passing loop from issue-refinement configuration (b7ab12e, ba52386)

## [1.33.0] - 2026-03-05

### Added

- **fix-quality-and-tests FSM loop** - Sequential quality gate loop: lint/format/types must pass before tests are checked; auto-fixes violations and loops back after fixing test failures to catch regressions (b6eb5a9)

### Fixed

- **`ll-loop stop` process termination** - Kill running subprocess on SIGTERM and escalate to SIGKILL; `ll-loop stop` now terminates active processes immediately (BUG-592)
- **ISSUE_TEMPLATE.md section count** - Correct internally inconsistent section count claim in issue template documentation (BUG-597)

### Changed

- **`ll-loop history` colored output** - Structured, colored output for `ll-loop history` command (ENH-566)
- **`ll-issues show` card colorization** - Colorize `ll-issues show` card output for improved readability (ENH-593)
- **`ll-issues impact-effort` color and layout** - ANSI color, dynamic layout, and summary count for `ll-issues impact-effort` (ENH-594)
- **`ll-loop run` colored output** - Colorize `ll-loop run` output for improved readability (ENH-595)
- **`ll-issues refine-status` colorization** - Colorize `ll-issues refine-status` output (ENH-596)
- **Built-in loops cleanup** - Remove built-in loops except issue-refinement; simplify loops directory (84e26ad)

## [1.32.1] - 2026-03-05

### Changed

- **`ll-loop show` box rendering** - Fix box truncation and add diagram centering in `ll-loop show` output (ENH-589)
- **Issue-refinement loop** - Audit and fix issue-refinement loop configuration, move to canonical `loops/` directory (ENH-590)
- **`ll-issues` output styling** - Fix output styling consistency and colorize `ll-issues` CLI commands (ENH-591)
- **CLI output styling reference** - Add reference documentation for CLI output styling (284a2d7)

## [1.32.0] - 2026-03-05

### Added

- **FSM live output streaming** - Stream live output from prompt and shell states in real-time (feat(fsm): 9b785ae)

### Fixed

- **FSM JSON schema** - Embed JSON schema in prompt instead of using --json-schema flag (fix(fsm): a12a570)
- **Executor session flag** - Replace --verbose with --no-session-persistence in claude CLI call (fix(executor): 65939d0)
- **Code quality** - Fix lint errors and reformat codebase (fix(code-quality): 90bb731)

### Changed

- **Refine-status columns configurable** - Make refine-status table columns configurable via ll-config.json (improve(issues): 3df3707)
- **ll-loop verbose polish** - Visual polish for ll-loop show --verbose output (improve(cli): a13e68d)

## [1.31.0] - 2026-03-04

### Added

- **FSM evaluate.source field** - FSMExecutor._evaluate() now supports evaluate.source field for dynamic source configuration (feat(fsm): 63f8fd1)
- **FSM multiline fix auto-detect** - Auto-detect multiline fix tool as prompt in compile_goal (feat(fsm): ad2b8d9)
- **CLI color output configurable** - CLI color output now configurable via ll-config.json (feat(cli): 2d0310c)
- **Responsive terminal output** - Responsive terminal output using stdlib utilities (feat(cli): 6b08081)
- **Sprint pre-validation** - `ll-sprint run` pre-validates issues are still active before wave dispatch (ENH-581)
- **ll-loop validation warnings** - Surface validation warnings in cmd_validate output (feat(ll-loop): 3b2e206)
- **refine-status template detection** - Detect issue formatting from template config instead of session log (feat(refine-status): 7a1398d)

### Fixed

- **Sprint contention sub-waves** - Route contention sub-waves through sequential in-place execution (fix(sprint): b30a3aa)
- **Parallel orphan cleanup** - Guard orphan cleanup against concurrent session worktrees (fix(parallel): 7e86ba3)
- **Workflow-analyzer entities_matched** - Compute entities_matched before all_entities mutation (fix(workflow-analyzer): de0d0a9)
- **FSM prev_result capture** - Capture prev_result in next-routed state action (fix(fsm): 6d00499)
- **Workflow-analyzer evidence list** - Preserve full evidence list in SessionLink (fix(workflow-analyzer): ccbcfce)
- **ll-loop stuck in evaluate** - Fix ll-loop stuck in evaluate state and improve timeout output clarity (fix(fsm): a2a2e08)
- **Parallel committed leaks** - Detect and recover committed leaks to main repo (fix(parallel): 56b62ba)
- **Hooks worktree cleanup** - Skip worktree cleanup when session runs inside a worktree (fix(hooks): 12ea54c)
- **FSM --no-llm flag** - Honor --no-llm flag in FSMExecutor._evaluate() (fix(fsm): 2f8ded0)

[1.33.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.32.1...v1.33.0
[1.32.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.32.0...v1.32.1
[1.32.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.31.0...v1.32.0
[1.31.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.30.0...v1.31.0

## [1.30.0] - 2026-03-04

### Added

- **Goal paradigm per-tool action_type** - Goal paradigm YAML spec supports per-tool action_type configuration (FEAT-572)

### Fixed

- **Mixed timestamp crashes** - Handle mixed naive/aware timestamps in workflow-analyzer (BUG-546)
- **ll-loop prompt output** - Improve output for prompt actions (BUG-564)
- **ll-loop shell output truncated** - Show last 8 lines of shell command output on handoff (BUG-566)
- **on_partial transition dropped** - Add on_partial as first-class FSM transition (BUG-567)
- **File hints scope** - Scope overlap detection to write-target sections only (BUG-571)
- **FSM diagram multi-label edges** - Join all multi-label edges in FSM diagram (BUG-574)

### Changed

- **ll-loop show verbose** - Improved verbose output quality with action-type-aware truncation, on_handoff display, evaluate prompt and state-level fields (ENH-568, ENH-569, ENH-570, ENH-573, ENH-575)
- **Section JSON alignment** - Align bug/enh section JSON with format-issue templates v2.0 (ENH-576)
- **Sprint stability** - Reduce default_max_workers to 2 for sprint stability (7921151)
- **Template alignment** - Align section JSONs and config with templates.md v2.0 (122167f)

[1.30.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.29.0...v1.30.0

## [1.29.0] - 2026-03-04

### Added

- **FSM executor improvements** - Enhanced event system, CLI display, interruptible sleep with backoff enforcement (40f1741, e83879c)
- **LLM evaluator migration** - Migrate FSM LLM evaluator from Anthropic SDK to Claude CLI (da750eb)
- **ll-issues refine-status subcommand** - New `ll-issues refine-status` with dynamic column table: Key, Norm, source/tradeoff/map columns, and refine-run counts (ENH-560, ENH-561)
- **Dual confidence thresholds** - Configurable dual confidence thresholds in confidence-check config (ENH-562)
- **BM25 relevance scoring** - Hybrid BM25 relevance scoring in `ll-history export` (2ae2133)
- **Session Log audit trail** - Session log steps added to issue-modifying commands and skills (ENH-524)

### Fixed

- **Loop resume elapsed time** - Restore elapsed time correctly across loop resume (BUG-527)
- **Concurrency TOCTOU race** - Eliminate TOCTOU race condition in LockManager.acquire() (b96efcf)
- **Process signal distinction** - Distinguish ESRCH from EPERM in _process_alive (e43fc6f)
- **FSM signal handling** - Handle FATAL_ERROR and LOOP_STOP signals in FSMExecutor (0da74d8)
- **Issue-refinement loop** - Fix evaluate prompt and convert from goal to FSM paradigm (9f459c3, 2041c5f)

### Changed

- **Frontmatter deduplication** - Remove duplicate frontmatter parsing between sync.py and parsing.py (ENH-484)
- **Dependency mapper module** - Split monolithic dependency_mapper into focused sub-package (275a1b4)
- **Issue parser performance** - Replace prefix loop with pre-compiled union regex (6de1002)
- **ll-history export rename** - Rename `generate-docs` subcommand to `export` (6772aca)

[1.29.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.28.1...v1.29.0

## [1.28.1] - 2026-03-02

### Fixed

- fix(ll-history): replace Jaccard with intersection scoring (d253f0b)

[1.28.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.28.0...v1.28.1

## [1.28.0] - 2026-03-02

### Added

- **ll-sync diff and close subcommands** - New `ll-sync diff [ID]` to show content differences between local and GitHub versions, and `ll-sync close [ID]` to close GitHub issues when local counterparts are completed (399e95c)

### Other

- docs(issues): update ENH-484 line refs and mark blockers resolved (1ae3d75)
- docs(readme): correct CLI tools count from 13 to 12 (043d252)
- docs(index): add 17 missing entries to docs/INDEX.md (8325dc7)

[1.28.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.27.0...v1.28.0

## [1.27.0] - 2026-03-02

### Added

- **ll-history generate-docs subcommand** - Synthesize architecture documentation from completed issue history with relevance scoring and progressive construction (FEAT-503)

### Changed

- enhance(format-issue): default to highest-priority issue when no args (b395620)
- enhance(sync): use issue-sections.json template in ll-sync pull (25bc374)
- enhance(architecture): extract output_parsing from parallel/ to root package (bbd577c)
- enhance(cli): remove redundant ll-next-id standalone tool (bac9428)
- enhance(cli): sharpen CLI tool descriptions for unambiguous tool selection (c576cd9)
- refactor(templates): split issue-sections.json into per-type files (50231fb)

### Other

- docs(ll-history): document generate-docs subcommand across all references (e7c2a61)
- style: apply ruff formatting to 4 files (1a7ca55)

[1.27.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.26.0...v1.27.0

## [1.26.0] - 2026-03-01

### Added

- **ll-issues show sub-command** - View issue summary cards with detail fields and full summary in dedicated card section (FEAT-505)
- **ll-loop --background daemon mode** - Run FSM loops as background daemon processes (feat, 6d4d58c)

### Fixed

- fix(cli): wrap long summary text in ll-issues show card (853053e)
- fix(docs): correct 20 documentation issues found by full audit (0e51bc8)
- fix(docs): address 5 remaining documentation audit findings (caa31d2)

### Changed

- **Forward-message pattern investigation** - Investigated coordinator synthesis behavior for ll-parallel result fidelity; closed as low utility (ENH-501)
- **ll-issues list layout** - Enhanced list output with type-based grouping, section headers, counts, and `--flat` flag (ENH-509)
- **issue_discovery module split** - Refactored 954-line module into focused package with matching, extraction, and search sub-modules (ENH-471)
- **Confidence-check outcome scoring** - Added dual-score output with Readiness Score and Outcome Confidence Score (ENH-446)
- **Init conflicting flags and dry-run** - Added conflict detection for mutually exclusive flags and `--dry-run` preview mode (ENH-458)
- **Audit frontmatter validation** - Extended plugin-config-auditor with 8 agent fields and 5 skill fields validation (ENH-464)

### Other

- docs(readme): add recently-added CLI features to README (43a0263)
- style: apply ruff formatting to scripts (d11cfb2)
- style: fix formatting in issues show card renderer (2afb4c2)

[1.26.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.25.0...v1.26.0

## [1.25.0] - 2026-02-27

### Added

- **Configurable dependency mapping thresholds** - All overlap and conflict thresholds now configurable via `ll-config.json` with `DependencyMappingConfig` dataclass and per-project overrides (ENH-514)

### Fixed

- **Impact-effort matrix row labels** - Fixed repeated "IMPACT" labels on every row of the 2×2 ASCII matrix (BUG-508)
- fix(deps): prune generic keywords from section and type matching to reduce false positives (9fb7605)
- fix(parallel): add thresholds to overlap detection to reduce false serialization (3f352ef)

### Changed

- **Sprint runner optimization** - Disabled redundant runtime overlap detection in sprint path since wave splitting already guarantees no overlap (ENH-512)

### Other

- docs(api): add text_utils module to API reference (bc28e52)
- docs: fix outdated directory trees and wrong API doc path (46a37e8)

[1.25.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.24.0...v1.25.0

## [1.24.0] - 2026-02-26

### Added

- **Grouped ll-issues list output** - `ll-issues list` now groups output by type (BUG, FEAT, ENH) with section counts and a total footer; added `--flat` flag for backward-compatible scripting output (ENH-509)

### Other

- docs(architecture): fix outdated counts and CLI directory structure (54f1f83)
- style: fix lint and format issues in scripts (3fec926)
- chore(issues): tradeoff review of 23 active issues (7ba83dd)

[1.24.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.23.0...v1.24.0

## [1.23.0] - 2026-02-26

### Added

- **TDD mode for issue implementation** - Add test-first development mode to manage-issue skill with Phase 3a (Write Tests — Red), config toggle, and plan template updates (0c54487)
- **Observation masking scratch pad pattern** - Add scratch pad behavioral instructions for handling large tool outputs (>200 lines) to reduce context window usage in automation (010df53)

[1.23.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.22.0...v1.23.0

## [1.22.0] - 2026-02-25

### Added

- **Deferred issues folder support** - Add support for deferred issues folder in issue management (6a62ba9)

### Fixed

- **Config-driven category lists** - Replace hardcoded category lists with config-driven values (c18269c)
- **Impact-effort grid alignment** - Fix grid alignment and axis labels in impact-effort visualization (d7e8fdc)
- **Impact-effort row labels** - Fix row label repetition in impact-effort grid (5c0cd76)

### Changed

- refactor(issues): refine issue files with updated scores and research (8f6b06e)

### Other

- test(workflow-analyzer): add unit tests for internal pipeline functions (68f3f4c)
- docs(plans): add implementation plan for ENH-471 issue_discovery split (6391fc1)
- chore: update session continuation prompt (91348c4)

[1.22.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.21.0...v1.22.0

## [1.21.0] - 2026-02-25

### Added

- **ll-issues CLI Command** - New `ll-issues` command with sub-commands: `next-id`, `list`, `sequence` (dependency-aware topological sort), and `impact-effort` (ASCII 2×2 quadrant visualization) (FEAT-505)

### Changed

- **issue_discovery Module** - Split monolithic `issue_discovery.py` into domain-organized package by finding type (ENH-471)

### Other

- docs(guides): fix factual errors and broken links in user guides (d3d0409)
- docs(readme): fix CLI tool count from 12 to 13 (a24f067)
- docs(release): fix v1.20.0 changelog — tests-until-passing is a built-in loop, not a paradigm (b888598)
- chore(issues): map cross-issue dependencies via ll-deps analyze (8c8004b)
- chore(issues): verify issues and correct stale references (3d9ccce)

[1.21.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.20.0...v1.21.0

## [1.20.0] - 2026-02-24

### Added

- feat(loops): add `tests-until-passing` built-in loop — runs pytest and iterates fix/evaluate cycles until all tests pass (79e5251)

### Fixed

- **Failed Sprint Wave Resume** - Prevent failed issues from being skipped on resume in ll-sprint (BUG-473)
- **YAML Frontmatter Corruption** - Fix frontmatter corruption on yaml.safe_load/dump round-trip (BUG-474)
- **Malformed github_issue Crash** - Handle malformed github_issue values in sync module (BUG-475)
- **Session Log Append** - Only replace first occurrence of section header in session_log (BUG-476)
- **ll-messages CLI Flag** - Correct epilog flag from --include-commands to --skip-cli (BUG-477)
- **IssueParser Silent Exception** - Log warning instead of swallowing exception on unreadable file (BUG-478)
- **Stash Pop Verification** - Verify stash pop success before re-queueing in merge_coordinator (BUG-479)
- **WorkerResult Docstring** - Remove stale "(not implemented)" from should_close docstring (BUG-480)

### Changed

- **Context Degradation Checkpoints** - Add checkpoints between issues in ll-auto to detect and respond to context degradation (ENH-499)
- refactor(cli): split cli/sprint.py into cli/sprint/ package (63635c7)

### Other

- docs: fix broken link to Loops Guide in README (dcaf618)
- docs: add getting started and sprint guides, reorganize structure (912f364)
- docs(loops): expand LOOPS_GUIDE with advanced features, CLI reference, and troubleshooting (1cdf7a5)
- chore: add management plans and session continuation prompt (ef7764f)
- chore(quality): fix lint and formatting issues in scripts (a51d5cd)
- chore(issues): verify and correct stale line numbers and function refs (e3615ac)
- chore(issues): format all active issues to template v2.0 (0f9bed6)
- chore(issues): verify issues and close ENH-482 as already resolved (c816422)

[1.20.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.19.1...v1.20.0

## [1.19.1] - 2026-02-24

### Fixed

- fix(issues): correct BUG-473 to identify same bug in both sprint code paths (3fb733e)

### Changed

- refactor(issue_history): split analysis.py into focused sub-modules (7324591)

### Other

- docs: reorganize docs/ folder into semantic subdirectories (95d4139)
- docs: move guide docs into docs/guides/ subfolder (be3855e)
- docs: add Issue Management Guide end-to-end workflow tutorial (edcd83e)
- chore(issues): add ENH-491 for using issue-sections.json in ll-sync pull (50b344c)
- chore(issues): add 18 issues from codebase scan (7614085)
- chore: remove completed ENH-448 issue, update logo asset, and refresh test sprint fixtures (036f834)
- chore(issues): re-prioritize issues (dfb15d8)

[1.19.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.19.0...v1.19.1

## [1.19.0] - 2026-02-24

### Changed

- **Add `__all__` to cli/loop/__init__.py** - Maintains consistency with other 5 package init files that already define `__all__` (ENH-472)
- enhance(configure): audit and expose unreachable config-schema fields (896c4ea)

### Other

- docs(loops): add user-facing loops guide with paradigm examples (0d13f53)
- chore(issues): add tradeoff review notes to FEAT-440 and ENH-470 (5066b9a)
- chore(issues): verify 8 open issues against codebase (08239b5)
- chore(issues): auto-format 6 issues to template v2.0 structure (1f41aef)

[1.19.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.18.0...v1.19.0

## [1.18.0] - 2026-02-23

### Changed

- **Audit settings hierarchy validation** - Full settings hierarchy validation in audit-claude-config (ENH-465)
- **Confidence-check outcome scoring** - Add outcome confidence scoring dimension (ENH-446)
- **Init auto-create issue directories** - Offer to create issue directories during initialization (ENH-453)
- **Init wizard round renumbering** - Renumber wizard rounds to eliminate Round 6.5 (ENH-454)
- **Init wizard expanded coverage** - Expand parallel, commands, and issues coverage in wizard (ENH-455)
- **Init wizard intro and descriptions** - Add intro context and improve feature descriptions (ENH-456)
- **Init templates as single source of truth** - Reconcile templates/*.json with presets.md (ENH-457)
- **MCP audit across all scopes** - Extend MCP audit to all scopes with env var expansion validation (ENH-466)
- **Init conflicting flags and dry-run** - Handle conflicting flags and add --dry-run (ENH-458)
- **Init command validation** - Optional command validation during init (ENH-460)
- **Command table completeness** - Add 7 missing skills to README and COMMANDS.md command tables (ENH-467)

### Fixed

- fix(loop): resolve mypy type error in FSM diagram renderer (bae6844)

### Other

- docs(audit): fix INDEX.md missing entry and track incomplete command tables (ab949ec)

[1.18.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.17.0...v1.18.0

## [1.17.0] - 2026-02-22

### Added

- **Init wizard: sprints, loops, and automation** - Add sprints, loops, and automation sections to interactive wizard (ENH-451)
- **Init wizard progress indicator** - Add progress indicator to interactive wizard rounds (ENH-452)

### Fixed

- fix(agents): update plugin-config-auditor to recognize all 17 hook event types (30fc2bc)
- fix(init): add missing state files to .gitignore step (40faae4)
- fix(init): split Round 5 into 5a/5b to respect AskUserQuestion 4-question limit (b44d28e)
- fix(skills): remove disable-model-invocation from all skills (d70e63f)
- fix(ci): resolve documentation link check failures (618cc6e)

### Changed

- **Audit frontmatter validation** - Add agent and skill frontmatter field validation to audit (ENH-464)
- **Audit config surfaces** - Add 5 missing config surfaces to audit-claude-config (ENH-462)

### Other

- deps(issues): map cross-issue dependencies for 22 active issues (2834d71)
- issues: add 13 issues from /ll:init interactive mode audit (82ead60)
- ci: remove documentation link check workflow (c778a02)

[1.17.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.16.0...v1.17.0

## [1.16.0] - 2026-02-22

### Added

- **Confidence score blocking gate for manage-issue** - ConfidenceGateConfig with enabled/threshold settings, Phase 2.5 gate check, `--force-implement` flag, and configure skill integration (ENH-447)

### Other

- chore(issues): add ENH-446, ENH-447, ENH-448 to backlog (87c469f)

[1.16.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.15.0...v1.16.0

## [1.15.0] - 2026-02-19

### Changed

- **2D ASCII renderer for FSM loop diagrams** - Replaced flat 1D text diagram with a 2D Unicode box renderer; main-path states rendered as boxes connected by labeled arrows, with self-loops indicated by ↺ marker (ENH-444)
- **FSM graph diagram in `ll-loop show`** - Implemented `_render_fsm_diagram()` with BFS-based edge classification rendering main flow, branches, and back-edges sections with labeled edges (ENH-443)
- **Per-iteration progress display in `ll-loop run`** - Fixed event callback wiring in `run_foreground`; added `[iter X] state: name (Xs)` format respecting `--quiet` flag (ENH-442)

### Other

- docs: fix ll-loop compile argument name in README (18b2af8)
- docs: remove unsupported action_type from paradigm templates (1f10d4e)
- style: fix lint and format issues in loop display code (ff1f49f)
- style: apply ruff formatting to 3 files (df48bb2)

[1.15.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.14.1...v1.15.0

## [1.14.1] - 2026-02-15

### Fixed

- **worktree_copy_files directory crash** - Skip directory entries in worktree file copying to prevent IsADirectoryError (BUG-438)
- **Hardcoded main branch references** - Auto-detect base branch in ll-sprint/ll-parallel instead of hardcoding "main"; update test assertions accordingly (BUG-439)

### Other

- docs(readme): add missing CLI subcommands for ll-loop and ll-history (4e81bf8)

[1.14.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.14.0...v1.14.1

## [1.14.0] - 2026-02-15

### Added

- **Sprint conflict analysis CLI** - `ll-sprint analyze` command for detecting conflicts between sprint issues (FEAT-433)
- **Dependency auto-repair** - `ll-deps fix` command to auto-repair broken dependency references (FEAT-432)
- **Metrics export** - Export historical metrics from `ll-history` (FEAT-435)
- **Git sync conflict resolution** - Commands for resolving sync conflicts with GitHub (FEAT-436)
- **Standalone overlap detection** - Pre-flight overlap detection command for sprint planning (FEAT-434)

### Fixed

- **Bare exception in merge loop** - Narrow bare exception to `queue.Empty` in merge coordinator (BUG-424)
- **Lock file race condition** - Replace TOCTOU race with `missing_ok=True` in LockManager (BUG-423)
- **Subprocess timeouts** - Add `timeout=30` to all `subprocess.run` calls in issue lifecycle (BUG-422)
- **File deletion race** - Replace TOCTOU file deletion race with `missing_ok=True` (BUG-421)
- **Process.wait() timeout** - Add timeout to `process.wait()` calls to prevent indefinite blocking (BUG-420)
- **UnboundLocalError** - Initialize result before loop to prevent `UnboundLocalError` in `_run_with_continuation()` (BUG-419)
- **Return code masking** - Fix `process.returncode` None being masked as success (BUG-425)

### Changed

- **Issue ID extraction** - Centralize issue ID extraction logic into shared utility (ENH-429)
- **Code fence stripping** - Centralize code fence stripping utility (ENH-430)
- **Wave refinement performance** - Fix O(N²) wave refinement with synchronous file reads (ENH-427)
- **Test coverage** - Add missing test coverage for core modules (ENH-426)
- **README template coverage** - Update template list to reflect all 9 project-type templates (ENH-437)

### Other

- docs(readme): add missing CLI subcommands for ll-sprint and ll-deps (c3b96f8)
- docs(issues): tech-debt audit — close 6 issues, narrow 2 (21828a1)
- docs(issues): architectural audit — close 6 issues, annotate 3 (b2d756c)
- docs(issues): add 18 issues from codebase scan (e09d628)
- docs(CLAUDE.md): distinguish skills from commands in capability list (71616c7)
- style(tests): auto-format test files with ruff (90b70c6)

[1.14.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.13.0...v1.14.0

## [1.13.0] - 2026-02-14

### Added

- **ll-auto content marker checking** - Verify phase fallback chain now checks implementation markers in issue file content (ENH-328)
- **Sprint sequential retry** - Merge-failed issues are retried sequentially after parallel waves complete (feat, 6c27480)

### Fixed

- fix(code-quality): resolve lint error and reformat 10 files (d50cb78)
- fix(docs): update CONTRIBUTING.md skills tree to list all 15 directories (21254eb)
- fix(docs): update README Skills table to list all 15 skills (872ebad)
- fix(docs): correct command and skill counts, reopen regressed doc issues (88025ba)

### Changed

- **Skill invocation allocation** - Audit and optimize skill invocation allocation across commands (ENH-279)
- **Test coverage improvements** - Add 59 tests across 6 modules, improving coverage from 86% to 89% (ENH-410)
- **Batched git log calls** - Batch git log calls in issue discovery for reduced subprocess overhead (ENH-352)
- enh(docs): update CLAUDE.md date and add skills count (eb95e2a)
- enh(sprint): relabel "file contention" to "file overlap" in sprint show output (8df1e2e)
- enh(plugin): add explicit agents declaration to plugin.json (0cf3e99)
- enh(commands): replace hardcoded tool names with config references (7a59449)
- enh(commands): add flag conventions to commands and skills (1267f27)
- enh(cli): add --type flag to ll-auto, ll-parallel, and ll-sprint (e53a574)
- enh(audit-claude-config): add Skills to Commands cross-reference validation (e480671)
- perf(link-checker): parallelize HTTP URL checking with ThreadPoolExecutor (e3d62c7)
- perf(issue-discovery): batch git log calls into single subprocess (01c60d4)
- perf(issue-history): cache issue file contents across analysis pipeline (60dfdce)
- refactor(text-utils): consolidate duplicated file path extraction into shared module (69175d2)
- refactor(cli-loop): split monolithic loop.py into focused subcommand package (8898582)
- refactor(issue-history): split god module into focused package (b51acb9)

### Other

- chore(issues): verify and correct stale file references in ENH-387, ENH-276, ENH-342 (cbd655b)

[1.13.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.12.2...v1.13.0

## [1.12.2] - 2026-02-13

### Other

- chore: standardize remaining underscore command/skill refs to hyphens (c74c178)

[1.12.2]: https://github.com/BrennonTWilliams/little-loops/compare/v1.12.1...v1.12.2

## [1.12.1] - 2026-02-13

### Fixed

- fix(commands): standardize all command/skill names to hyphens (28ff0f5)

### Other

- chore(issues): verify 19 open issues and fix stale references (22186c1)
- chore(issues): deprioritize FEAT-324 to P6 and FEAT-417 to P7 (30fae5a)
- close(issues): won't-fix 5 low-value enhancements after architecture review (d5b5a04)

[1.12.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.12.0...v1.12.1

## [1.12.0] - 2026-02-13

### Added

- **Sprint show improvements** - Nested sub-wave display and health summary in `ll-sprint show` (7f000dc)
- **Confidence check batch mode** - `--all` and `--auto` flags for batch processing (ENH-408)
- **Sprint theme grouping** - Theme-based grouping options in `create_sprint` (ENH-407)

### Fixed

- **Sprint dependency graph** - Use structural root detection in dependency graph rendering (588ff3d)
- **Issue heading IDs** - Correct mismatched IDs in issue headings (cd4e206)
- **Dependency references** - Clean up resolved blockers and stale dependency references (9c7f22f)
- **Plugin config auditor** - Complete hook event types and handler validation (ENH-368)

### Changed

- **Skills --all flag** - `--all` flag implicitly enables `--auto` behavior (ENH-416)
- **Confidence check labels** - Type-specific criterion 3 labels and rubrics (ENH-418)
- **Hooks configuration** - Add description and statusMessage fields to hooks.json (ENH-371)
- **Hook matchers** - Remove silently-ignored matchers from UserPromptSubmit and Stop events (a706be4)
- **Hook feedback** - Use exit 2 in precompact-state.sh for user-visible feedback (d646559)
- **Command frontmatter** - Add argument-hint frontmatter to 27 command/skill files (ENH-401)
- **Skill frontmatter** - Add model and allowed-tools frontmatter to 8 skills (ENH-398)
- **Skill migration** - Migrate 8 oversized commands to skill directories (ENH-400)
- **Agent frontmatter** - Add model and tools frontmatter fields to all agents (ENH-355)
- **Command tools** - Add allowed-tools frontmatter to 25 commands (ENH-399)
- **Manage issue resume** - Read continuation prompt on `--resume` (cf788e1)

### Other

- docs(cli): document ll-next-id in README, CLAUDE.md, and cli/__init__.py (b9aaae5)
- docs(issues): capture ENH-418, ENH-416, FEAT-417, ENH-405 (352f022, 7f42a6c)
- style(sprint): auto-format and fix line length in sprint modules (4123c21, ad3867f)

[1.12.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.11.1...v1.12.0

## [1.11.1] - 2026-02-13

### Fixed

- fix(docs): update CONTRIBUTING.md project tree cli.py → cli/ package (703da46)
- fix(docs): add review_sprint to all command documentation (76498c8)

### Other

- docs: fix README counts and create issues for undocumented commands/tools (a641b33)
- style: apply ruff format to scripts (925b8ce)

[1.11.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.11.0...v1.11.1

## [1.11.0] - 2026-02-13

### Added

- **Parallel merge for BUG-402** - Enable parallel merge workflow for bug fix processing (27ee877)

### Fixed

- **Config test fixtures** - Remove stale default_mode from test fixtures (8063ff6)
- **Cross-type issue references** - Resolve false "nonexistent" warnings for cross-type issue references (ff50bc6)
- **Command $ARGUMENTS placement** - Add explicit $ARGUMENTS placement to 6 command files (e339afe)
- **Sync status errors** - Surface GitHub query failures in sync status (aa3b2a3)
- **Mutable default aliasing** - Prevent mutable default aliasing in ProcessingState.from_dict (37c05c3)
- **Scan command tools** - Add missing tools to allowed-tools in scan commands (6c3af0b)
- **Sprint dependency graph** - Suppress flat dependency graph when no intra-sprint edges exist (3d7713c)

### Other

- close(bugs): BUG-403 - Closed - Already Fixed (2ab0411)
- close(bugs): BUG-365 - Closed - Invalid (09ca349)
- docs(issues): add test and documentation coverage to 29 active issues (36b4241)
- docs(issues): resolve BUG-364 marketplace version mismatch (c1bc313)
- docs(issues): auto-format and verify 42 active issues (b689764)
- docs(issues): add cross-issue dependency references for command/skill audit issues (72d6326)

[1.11.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.10.1...v1.11.0

## [1.10.1] - 2026-02-12

### Added

- **Plugin config audit issues** - Add plugin config audit issues and update ENH-371 with once field (130dd65)
- **Cross-issue dependency mappings** - Add cross-issue dependency mappings and ENH-396 issue (c14cbc4)
- **`ll-next-id` command** - Consolidate issue ID assignment with new CLI command (cc50082)
- **Sprint review skill** - Add `/ll:review-sprint` skill for AI-guided sprint health checks (c4b6b11)
- **Sprint edit subcommand** - Add `ll-sprint edit` subcommand for sprint modifications (6c195f2)
- **Sprint-scoped dependency analysis** - Add `--sprint` flag to `ll-deps` for sprint-scoped analysis (dee0890)

### Fixed

- **Sprint review plugin discovery** - Move review_sprint from skill to command for plugin discovery (264a3de)
- **Sprint skill arguments** - Add missing `$ARGUMENTS` section to review_sprint skill (1dd0c1c)
- **Documentation module listings** - Update ARCHITECTURE and API module listings from audit (2c063eb)

### Other

- docs: add Claude Code reference documentation for hooks, plugins, and skills (f54a723)
- style(cli): fix line length formatting in loop and sprint modules (4550a0a)

[1.10.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.10.0...v1.10.1

## [1.10.0] - 2026-02-12

### Added

- **Auto-mode for prioritize_issues** - Run priority assignment without interactive prompts (FEAT-380, ENH-389)
- **Re-prioritize option** - Re-prioritize already-prioritized issues when backlog shifts (ENH-389)
- **Refine issue command** - New `refine_issue` with codebase-driven research for deeper issue refinement (FEAT-380)
- **`ll-loop show` command** - Inspect loop configuration details from the CLI (FEAT-345)
- **CLI tool loop templates** - Ship built-in loop templates for common CLI tool workflows (ENH-332)
- **Pre-implementation confidence check** - Validate implementation readiness before coding begins (ENH-277)
- **Abstract base classes for CLI commands** - Shared ABC for CLI command structure (FEAT-001)
- **Session log linking** - Link session JSONL logs to issue files for traceability (FEAT-323)

### Fixed

- **Prioritize issues gate logic** - Simplify and fix re-prioritize gate wording and AskUserQuestion reliability (BUG-361)
- **Normalize issues duplicate detection** - Include `completed/` directory in duplicate ID detection (BUG-382)
- **Configure phantom section** - Remove phantom workflow configuration section (BUG-367)
- **Sprint issue parsing** - Log warning when issue file parsing fails instead of crashing (BUG-348)
- **Hook timeout values** - Correct timeout values from milliseconds to seconds (BUG-376)
- **Hook prompt handling** - Use `exit 0` + stdout instead of `exit 2` + stderr in user-prompt-check (BUG-361)
- **Absolute path removal** - Replace absolute paths with relative/generic paths for public repo distribution (BUG-338)
- **Issue size review reference** - Correct command reference in issue-size-review skill (BUG-358)
- **README skills count** - Fix skills count (7 vs 8) and add missing loop-suggester to table (BUG-381)
- **CONTRIBUTING directory trees** - Update outdated directory trees for skills, loops, and docs (BUG-382)
- **Help references** - Correct multiple stale and missing references in help.md (BUG-336)
- **Create loop wizard** - Present paradigms instead of use-case templates (BUG-333)
- **Context monitor compaction** - Reset token estimate after context compaction (BUG-329)
- **Manage issue improve action** - Clarify that improve action requires full implementation (BUG-326, BUG-327)

### Changed

- **Behavioral rules extraction** - Split CLAUDE.md behavioral rules into core docs (ENH-278)
- **Test file splitting** - Split large test files into focused modules (ENH-311)
- **Text dependency graphs** - Replace mermaid dependency graphs with ASCII text diagrams in CLI (ENH-334)
- **Documentation reorganization** - Organize docs with command and skill groupings (ENH-335)
- **Dependency mapping delegation** - `map-dependencies` skill delegates to `dependency_mapper.py` (ENH-337)
- **Configurable continuation path** - Continuation prompt path now configurable (ENH-340)
- **CLI package split** - Split `cli.py` into `cli/` package for maintainability (ENH-344)
- **Serialization mixin** - Extract serialization mixin for dataclass `to_dict` boilerplate (ENH-354)
- **Agent model fields** - Add missing `model` field to all agent frontmatter (ENH-355)
- **CLAUDE.md completeness** - Document orphan commands and CLI tools (ENH-356)
- **Settings validation** - `audit_claude_config` now validates `settings.json` content (ENH-369)
- **Command examples** - Add missing Examples sections to commit and tradeoff_review_issues commands (ENH-373)
- **Remove .mcp.json placeholder** - Remove empty `.mcp.json` placeholder file (ENH-375)
- **Rename refine_issue** - Rename `refine_issue` to `format_issue` for honest naming (ENH-379)
- **Audit docs direct fix** - Add direct fix option for auto-fixable findings in audit_docs (ENH-383)
- **Context monitor tracking** - Track Claude output and user message tokens (ENH-330)

[1.10.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.9.0...v1.10.0

## [1.9.0] - 2026-02-11

### Added

- **Pre-implementation confidence-check skill** - New skill for validating implementation readiness before starting work (ENH-277)
- **Session log linking** - Link Claude Code JSONL session logs to issue files for traceability (FEAT-323)
- **Context monitor token tracking** - Track Claude output and user message tokens with compaction reset (ENH-330)

### Fixed

- **Config schema cleanup** - Remove 5 unused schema sections with no implementation (ENH-343)
- **Hardcoded path removal** - Replace hardcoded paths with config template refs in commands and skills (ENH-341)
- **Loops directory config** - Read loops directory path from ll-config.json instead of hardcoding (BUG-339)
- **Hook directory config** - Read hook directory paths from ll-config.json (BUG-338)
- **Help references** - Correct stale references in help.md (BUG-336)
- **Create loop wizard** - Present paradigms instead of use-case templates in wizard (BUG-333)
- **Context monitor compaction** - Reset token estimate after context compaction (BUG-329)
- **Issue manager resume** - Use `--resume` flag for continuation sessions (BUG-327)

### Changed

- **CLI package split** - Split `cli.py` god module into `cli/` package for better maintainability (ENH-344)
- **Dependency mapping delegation** - `map-dependencies` skill now delegates to `ll-deps` CLI (ENH-337)
- **ASCII dependency graphs** - Replace mermaid dependency graphs with ASCII text diagrams (ENH-334)
- **Documentation reorganization** - Organize commands and skills under 9 capability groupings (ENH-335)

[1.9.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.8.0...v1.9.0

## [1.8.0] - 2026-02-11

### Added

- **Auto mode for issue refinement** - `refine_issue` now supports automatic template v2.0 alignment without interactive Q&A (ENH-325, FEAT-256)
- **Session linking and history DB issues** - New issues for session continuity and historical tracking (FEAT-255)
- feat(refine_issue): add auto mode for template v2.0 alignment (2fb8ab4)

### Fixed

- **Improve action clarity** - `manage_issue` improve action now clearly requires full implementation, not just plans (BUG-326)
- **Template v2.0 section names** - Corrected old v1.0 template section names in 3 files (BUG-322)

### Changed

- refactor(issue): reduce ENH-319 scope from 12 to 6 enhancements (8e6ec6e)
- chore: add .sprints/ to .gitignore (e7ab913)
- chore: ignore generated loop-suggestions cache directory (f8e7ce4)
- style: fix lint errors and reformat with ruff (ae44c67)

[1.8.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.7.0...v1.8.0

## [1.7.0] - 2026-02-10

### Added

- **Issue template v2.0 with Integration Map** - New template format with integration analysis section for better cross-component awareness (ENH-320, ENH-321)

### Fixed

- **Null command guards** - Commands no longer crash when project commands (lint_cmd, type_cmd, format_cmd, test_cmd) are null (BUG-312)
- **Sprint duplicate status lines** - Suppress duplicate status output during parallel execution (BUG-305)
- **Documentation accuracy** - Correct 3 config default values, command count, `max_continuations` section placement, missing commands in README tables, ghost `find_demo_repos` entry, and `--include-p0` flag docs (BUG-313, BUG-315, BUG-316, BUG-317, BUG-318)

### Changed

- **Sprint file contention warnings** - Execution plan now shows file contention warnings for better parallel planning (ENH-309)
- **build_cmd verification** - `check_code` now includes build_cmd verification step (ENH-310)
- **run_cmd config field** - Added run_cmd to config and wired into manage_issue verification (ENH-311)
- **README config documentation** - Added sync, sprints, documents, and missing config sections to README (ENH-314, ENH-318)
- docs(contributing): add issue creation guidelines for v2.0 (fe6fea5)
- docs(commands): update commands for template v2.0 (317144c)

[1.7.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.6.0...v1.7.0

## [1.6.0] - 2026-02-10

### Changed

- **Semantic conflict analysis in dependency mapper** - Detect semantic conflicts within shared files, distinguishing safe parallel modifications from true conflicts (ENH-300)
- **Dependency mapper integration** - Integrate dependency mapping into sprint creation and execution workflows for improved wave splitting (ENH-301)
- **File-contention-aware wave splitting** - Intelligent wave splitting based on file contention analysis for optimized parallel execution (ENH-306)

### Fixed

- **Sprint subprocess hang in automation mode** - Prevent subprocess hang when Claude calls AskUserQuestion in `-p` mode (BUG-302)
- **Parallel wave overlap detection** - Enable overlap detection for parallel wave execution (BUG-305)
- **Sprint state per-issue tracking** - Use per-issue tracking from orchestrator queue instead of wave-level exit code (BUG-307)
- fix(config): disable idle timeout by default to prevent false kills (6f3f6e0)

[1.6.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.5.0...v1.6.0

<!-- Versions 1.2.0-1.4.0 were internal development milestones without tagged releases. -->

## [1.5.0] - 2026-02-09

### Added

- **GitHub Issues sync** - Bidirectional sync with GitHub Issues including `ll-sync` CLI tool, `--dry-run` support, and `--labels` filtering (FEAT-222, FEAT-226)
- **Release management** - `/ll:manage-release` command for git tags, changelogs, GitHub releases, and version bumping (FEAT-268)
- **Product analysis** - `/ll:product-analyzer` skill and `/ll:scan-product` command for product-focused codebase analysis (FEAT-022)
- **Issue dependency mapping** - Automated cross-issue dependency discovery with semantic conflict analysis (FEAT-261)
- **Loop automation** - `/ll:create-loop` and `/ll:loop-suggester` skills for FSM loop configuration; ship 5 built-in loops (FEAT-219, FEAT-270)
- **Tradeoff review** - `/ll:tradeoff-review-issues` skill for issue utility vs complexity evaluation (FEAT-257)
- **Issue refinement** - `/ll:refine-issue` skill with content-quality analysis for interactive issue clarification (FEAT-225)
- **Open PR command** - `/ll:open-pr` command and skill for pull request creation (FEAT-228)
- **GitHub sync in init wizard** - Add sync setup to `/ll:init` and `/ll:configure` (ENH-227)
- **Sprint management** - `ll-sprint` CLI tool with YAML sprint definitions and quiet mode
- **Workflow analysis** - `/ll:analyze-workflows` and `/ll:workflow-automation-proposer` skills
- **History analysis** - `/ll:analyze-history` skill for project health insights
- **CLI command extraction** - `ll-messages --include-commands` for CLI command history (FEAT-221)
- **End-to-end CLI tests** - Comprehensive CLI workflow tests (FEAT-210)
- **Fuzz testing** - Fuzz testing for critical parsers (ENH-216)
- **Documentation tooling** - CLI link checker (ENH-267), automated doc count verification (ENH-265), central documentation index (ENH-266)
- **Real-time progress** - Worktree progress visibility in `ll-parallel` (ENH-262)
- **Quiet mode** - `--quiet` flag for `ll-auto` and `ll-sprint`

### Fixed

- **ll-auto verification** - Detect plan creation in Phase 3 verification (BUG-280)
- **Process management** - Reap child process after timeout kill to prevent zombies (BUG-231); close selector to prevent file descriptor leak (BUG-230); detach spawned continuation process as daemon (BUG-236)
- **Parallel processing** - Ensure worker callback invoked on future exception (BUG-229); narrow exception catch in priority queue to `queue.Empty` (BUG-233)
- **GitHub sync** - Use global issue numbering to prevent collision with completed issues (BUG-234); pass `--labels` flag to `gh issue list` during pull (BUG-235)
- **Documentation accuracy** - Correct README command count, skills table, and plugin.json path (BUG-273); update outdated directory trees across README, CONTRIBUTING, and ARCHITECTURE (BUG-274)
- **FSM documentation** - Clarify max_iterations defaults vs recommended values (BUG-194); add notation legend to FSM Compilation Reference (BUG-197); update ll-loop test output docs (BUG-199)
- **ll-messages** - Aggregate all assistant turns for `--include-response-context` (BUG-220)
- **Plugin configuration** - Correct relative paths for commands and skills directories; correct marketplace.json source path
- **Create loop docs** - Document missing `action_type` field (BUG-192) and `on_handoff` feature (BUG-193)

### Changed

- **Frontmatter parsing** - Consolidated duplicated parsing into shared module
- **Work verification** - Consolidated duplicated verification code into single source
- **CLI architecture** - Extracted shared CLI argument definitions to `cli_args` module
- **Plugin structure** - Converted `refine_issue` from skill to command
- **Error messages** - Standardized error message format across paradigm validators
- **Templates** - Extracted issue section checks into shared template file
- **Hooks** - Unified feature flag checking with shared functions
- **Issue management** - Added integration analysis to lifecycle; added product impact fields to issue parsing
- **Config** - Added configurable duplicate detection thresholds

### Testing

- Improved `issue_manager.py` test coverage to 87% (ENH-207)
- Improved `merge_coordinator.py` test coverage to 80% (ENH-208)
- Improved `orchestrator.py` test coverage (ENH-209)
- Added concurrent access tests (ENH-217)
- Improved error message validation in tests (ENH-215)
- Added comprehensive testing documentation (ENH-214)
- Split large test files into focused modules
- Added tests for loop-suggester and create_loop skill artifacts

[1.5.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.1.0...v1.5.0

## [1.1.0] - 2026-02-01

### Added

- **`ll-history` CLI tool** - View completed issue statistics including total count, date range, velocity (issues/day), and breakdowns by type and priority. Supports `--json` flag for scripting.

[1.1.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.0.0...v1.1.0

## [1.0.0] - 2026-01-02

### Added

- **20 slash commands** for development workflows:
  - `/ll:init` - Project initialization with auto-detection for 7 project types
  - `/ll:help` - Command reference and usage guide
  - `/ll:toggle-autoprompt` - Toggle automatic prompt optimization
  - `/ll:check-code` - Code quality checks (lint, format, types)
  - `/ll:run-tests` - Test execution with scope filtering
  - `/ll:find-dead-code` - Unused code detection
  - `/ll:manage-issue` - Full issue lifecycle management
  - `/ll:ready-issue` - Issue validation with auto-correction
  - `/ll:prioritize-issues` - Priority assignment (P0-P5)
  - `/ll:verify-issues` - Issue verification against codebase
  - `/ll:normalize-issues` - Fix invalid issue filenames
  - `/ll:scan-codebase` - Issue discovery
  - `/ll:audit-docs` - Documentation auditing
  - `/ll:audit-architecture` - Architecture analysis
  - `/ll:audit-claude-config` - Comprehensive config audit
  - `/ll:describe-pr` - PR description generation
  - `/ll:commit` - Git commit creation with approval
  - `/ll:iterate-plan` - Plan iteration and updates
  - `/ll:handoff` - Generate continuation prompt for session handoff
  - `/ll:resume` - Resume from previous session's continuation prompt

- **7 specialized agents**:
  - `codebase-analyzer` - Implementation details analysis
  - `codebase-locator` - File and feature discovery
  - `codebase-pattern-finder` - Code pattern identification
  - `consistency-checker` - Cross-component consistency validation
  - `plugin-config-auditor` - Plugin configuration auditing
  - `prompt-optimizer` - Codebase context for prompt enhancement
  - `web-search-researcher` - Web research capability

- **Sequential automation** (`ll-auto`):
  - Priority-based issue processing
  - State persistence for resume capability
  - Real-time output streaming
  - Configurable timeouts

- **Parallel automation** (`ll-parallel`):
  - Git worktree isolation per worker
  - Concurrent issue processing
  - Automatic merge coordination
  - `--show-model` flag for model verification
  - Configurable worker count

- **Configuration system**:
  - JSON Schema validation
  - 9 project-type templates (Python, JavaScript, TypeScript, Go, Rust, Java Maven/Gradle, .NET, Generic)
  - Variable substitution in command templates
  - Command override support

- **Issue management**:
  - Auto-correction during validation
  - Automatic issue closure for invalid/resolved issues
  - Fallback lifecycle completion
  - Work verification before marking complete

### Fixed

- Safety checks for stale state in close/complete functions
- Circular import in parallel orchestrator
- Markdown bold formatting in verdict parsing
- Type annotations and shadowed variable issues

### Security

- All subprocess calls use argument lists (no shell=True)
- Git operations constrained to repository directory
- Claude CLI invoked with `--dangerously-skip-permissions` (documented requirement for automation)

[1.54.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.53.0...v1.54.0
[1.53.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.52.0...v1.53.0
[1.52.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.51.0...v1.52.0
[1.51.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.50.0...v1.51.0
[1.50.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.49.0...v1.50.0
[1.49.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.48.0...v1.49.0
[1.48.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.47.0...v1.48.0
[1.47.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.46.0...v1.47.0
[1.46.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.45.0...v1.46.0
[1.45.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.44.0...v1.45.0
[1.44.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.43.0...v1.44.0
[1.43.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.42.0...v1.43.0
[1.42.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.41.0...v1.42.0
[1.41.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.40.0...v1.41.0
[1.40.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.39.0...v1.40.0
[1.39.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.38.0...v1.39.0
[1.38.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.37.3...v1.38.0
[1.34.0]: https://github.com/BrennonTWilliams/little-loops/compare/v1.33.1...v1.34.0
[1.33.1]: https://github.com/BrennonTWilliams/little-loops/compare/v1.33.0...v1.33.1
[1.0.0]: https://github.com/BrennonTWilliams/little-loops/compare/v0.0.1...v1.0.0
