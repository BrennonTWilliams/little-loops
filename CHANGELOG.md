# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Windows compatibility testing
- Performance benchmarks for large repositories

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

[1.0.0]: https://github.com/BrennonTWilliams/little-loops/compare/v0.0.1...v1.0.0

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
