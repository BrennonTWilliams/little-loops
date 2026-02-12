# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Test coverage for core modules
- Windows compatibility testing
- Performance benchmarks for large repositories

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
- **Release management** - `/ll:manage_release` command for git tags, changelogs, GitHub releases, and version bumping (FEAT-268)
- **Product analysis** - `/ll:product-analyzer` skill and `/ll:scan_product` command for product-focused codebase analysis (FEAT-022)
- **Issue dependency mapping** - Automated cross-issue dependency discovery with semantic conflict analysis (FEAT-261)
- **Loop automation** - `/ll:create_loop` and `/ll:loop-suggester` skills for FSM loop configuration; ship 5 built-in loops (FEAT-219, FEAT-270)
- **Tradeoff review** - `/ll:tradeoff_review_issues` skill for issue utility vs complexity evaluation (FEAT-257)
- **Issue refinement** - `/ll:refine_issue` skill with content-quality analysis for interactive issue clarification (FEAT-225)
- **Open PR command** - `/ll:open_pr` command and skill for pull request creation (FEAT-228)
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
  - `/ll:toggle_autoprompt` - Toggle automatic prompt optimization
  - `/ll:check_code` - Code quality checks (lint, format, types)
  - `/ll:run_tests` - Test execution with scope filtering
  - `/ll:find_dead_code` - Unused code detection
  - `/ll:manage_issue` - Full issue lifecycle management
  - `/ll:ready_issue` - Issue validation with auto-correction
  - `/ll:prioritize_issues` - Priority assignment (P0-P5)
  - `/ll:verify_issues` - Issue verification against codebase
  - `/ll:normalize_issues` - Fix invalid issue filenames
  - `/ll:scan_codebase` - Issue discovery
  - `/ll:audit_docs` - Documentation auditing
  - `/ll:audit_architecture` - Architecture analysis
  - `/ll:audit_claude_config` - Comprehensive config audit
  - `/ll:describe_pr` - PR description generation
  - `/ll:commit` - Git commit creation with approval
  - `/ll:iterate_plan` - Plan iteration and updates
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
