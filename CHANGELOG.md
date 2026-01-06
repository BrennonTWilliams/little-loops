# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-02

### Added

- **18 slash commands** for development workflows:
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

## [Unreleased]

### Planned

- Test coverage for core modules
- Windows compatibility testing
- Performance benchmarks for large repositories
