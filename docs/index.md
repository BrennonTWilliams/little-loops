![little-loops](assets/logo.svg){ width="200" .home-logo }

# Documentation Index

Complete reference for all little-loops documentation.

## Quick Start

New to little-loops? Start here:
- [Getting Started Guide](guides/GETTING_STARTED.md) - Mental model, first workflow, and when to escalate
- [README](../README.md) - Installation, quick start, and configuration
- [Command Reference](reference/COMMANDS.md) - All available slash commands
- [Troubleshooting](development/TROUBLESHOOTING.md) - Common issues and solutions

## User Documentation

Documentation for using little-loops in your projects.

### Codex CLI

- [Codex CLI Overview](codex/README.md) - What works, what is deferred, and where to start
- [Getting Started with Codex](codex/getting-started.md) - Install, trust prompt, skill discovery, first-run verification
- [Codex Usage](codex/usage.md) - Orchestration CLIs, skill invocation, opt-in pre_tool_use, current limitations

### Reference

- [Configuration Reference](reference/CONFIGURATION.md) - Full config options, variable substitution, and command overrides
- [Command Reference](reference/COMMANDS.md) - Complete reference for all slash commands with usage examples
- [CLI Reference](reference/CLI.md) - All `ll-` CLI tools with flags and examples
- [Output Styling Reference](reference/OUTPUT_STYLING.md) - Terminal output formatting and styling conventions
- [Troubleshooting](development/TROUBLESHOOTING.md) - Common issues, diagnostic commands, and solutions
- [Session Handoff](guides/SESSION_HANDOFF.md) - Context management and session continuation guide
- [Issue Management Guide](guides/ISSUE_MANAGEMENT_GUIDE.md) - End-to-end issue workflow: discovery, refinement, validation, and implementation
- [Sprint Guide](guides/SPRINT_GUIDE.md) - Sprint creation, wave execution, dependency ordering, file contention, and resume
- [Loops Guide](guides/LOOPS_GUIDE.md) - Loop creation, FSM YAML, built-in loops, and walkthrough
- [Learning Tests Guide](guides/LEARNING_TESTS_GUIDE.md) - Verify external APIs and SDKs via the Feathers Learning Test lifecycle and the `.ll/learning-tests/` registry
- [Automatic Harnessing Guide](guides/AUTOMATIC_HARNESSING_GUIDE.md) - Harness loop quality pipeline: multi-stage evaluation, retries, and wizard setup
- [Examples Mining Guide](guides/EXAMPLES_MINING_GUIDE.md) - Co-evolutionary examples mining with apo-textgrad for continuously improving prompts
- [Workflow Analysis Guide](guides/WORKFLOW_ANALYSIS_GUIDE.md) - Discover automation opportunities from message history using ll-workflows, analyze-workflows, and workflow-automation-proposer
- [Decisions Log Guide](guides/DECISIONS_LOG_GUIDE.md) - Record decisions and required rules, generate them from history, and sync active rules into `ll.local.md`
- [Learning Tests Guide](guides/LEARNING_TESTS_GUIDE.md) - Verify external APIs and SDKs via the Feathers Learning Test lifecycle and the `.ll/learning-tests/` registry
- [History & Session Guide](guides/HISTORY_SESSION_GUIDE.md) - Long-term observability via `.ll/history.db`: what ran, what changed, what was corrected
- [Built-in Hooks Guide](guides/BUILTIN_HOOKS_GUIDE.md) - Every hook little-loops ships, what it does automatically, and the config keys that turn each on or off
- [Issue Template Guide](reference/ISSUE_TEMPLATE.md) - Issue file structure, sections, and template v2.0 reference

## Developer Documentation

Documentation for contributing to and developing little-loops.

- [Contributing Guide](../CONTRIBUTING.md) - Development setup, guidelines, and workflow
- [Architecture Overview](ARCHITECTURE.md) - System design, component relationships, and diagrams
- [API Reference](reference/API.md) - Python module documentation with detailed class and method references
- [Event Schema Reference](reference/EVENT-SCHEMA.md) - All LLEvent types plus hook intent types (`LLHookEvent`, `LLHookResult`), wire format, and machine-readable JSON schemas — primary reference for extension authors and external consumers
- [Write a Hook](claude-code/write-a-hook.md) - Authoring guide for `LLHookIntentExtension`: the Protocol, adapter flow, and pure-function + subprocess testing patterns
- [Testing Guide](development/TESTING.md) - Testing patterns, conventions, and best practices
- [E2E Testing](development/E2E_TESTING.md) - End-to-end testing guide for CLI workflows

## Advanced Topics

Deep dives into specific systems and internals.

- [FSM Loop System Design](generalized-fsm-loop.md) - Internal FSM architecture, schema, evaluators, and compiler details
- [Merge Coordinator](development/MERGE-COORDINATOR.md) - Sophisticated merge coordination for parallel processing

---

**Need help?** See the [Troubleshooting Guide](development/TROUBLESHOOTING.md) or check [Getting Help](development/TROUBLESHOOTING.md#getting-help) section.
