![little-loops](assets/logo.svg)

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

- [Configuration Reference](reference/CONFIGURATION.md) - Full config options, variable substitution, and command overrides
- [Command Reference](reference/COMMANDS.md) - Complete reference for all slash commands with usage examples
- [CLI Reference](reference/CLI.md) - All `ll-` CLI tools with flags and examples
- [Output Styling Reference](reference/OUTPUT_STYLING.md) - Terminal output formatting and styling conventions
- [Troubleshooting](development/TROUBLESHOOTING.md) - Common issues, diagnostic commands, and solutions
- [Session Handoff](guides/SESSION_HANDOFF.md) - Context management and session continuation guide
- [Issue Management Guide](guides/ISSUE_MANAGEMENT_GUIDE.md) - End-to-end issue workflow: discovery, refinement, validation, and implementation
- [Sprint Guide](guides/SPRINT_GUIDE.md) - Sprint creation, wave execution, dependency ordering, file contention, and resume
- [Loops Guide](guides/LOOPS_GUIDE.md) - Loop creation, FSM YAML, built-in loops, and walkthrough
- [Workflow Analysis Guide](guides/WORKFLOW_ANALYSIS_GUIDE.md) - Discover automation opportunities from message history using ll-workflows, analyze-workflows, and workflow-automation-proposer
- [Issue Template Guide](reference/ISSUE_TEMPLATE.md) - Issue file structure, sections, and template v2.0 reference

## Developer Documentation

Documentation for contributing to and developing little-loops.

- [Contributing Guide](../CONTRIBUTING.md) - Development setup, guidelines, and workflow
- [Architecture Overview](ARCHITECTURE.md) - System design, component relationships, and diagrams
- [API Reference](reference/API.md) - Python module documentation with detailed class and method references
- [Testing Guide](development/TESTING.md) - Testing patterns, conventions, and best practices
- [E2E Testing](development/E2E_TESTING.md) - End-to-end testing guide for CLI workflows

## Advanced Topics

Deep dives into specific systems and internals.

- [FSM Loop System Design](generalized-fsm-loop.md) - Internal FSM architecture, schema, evaluators, and compiler details
- [Merge Coordinator](development/MERGE-COORDINATOR.md) - Sophisticated merge coordination for parallel processing
- [Claude CLI Integration](research/claude-cli-integration-mechanics.md) - Technical details on Claude CLI integration
- [CLI Tools Audit](research/CLI-TOOLS-AUDIT.md) - Review and audit of CLI tools
- [LCM: Lossless Context Management](research/LCM-Lossless-Context-Management.md) - Research paper on lossless context management
- [LCM Integration Brainstorm](research/LCM-Integration-Brainstorm.md) - Technical roadmap for issue-based LCM integration
- [Demo Repository Rubric](demo/demo-repo-rubric.md) - Criteria for evaluating demo repositories
- [Demo Scenarios](demo/scenarios.md) - Demo scenarios showcasing key plugin capabilities
- [Demo Modules](demo/modules.md) - Bootcamp module list and focus areas
- [Demo README](demo/README.md) - Demo setup instructions and quick start

## Claude Code Reference

Reference documentation for Claude Code platform features.

- [Automate Workflows with Hooks](claude-code/automate-workflows-with-hooks.md) - Create hooks to automate repetitive workflows
- [Checkpointing](claude-code/checkpointing.md) - Session checkpointing and restoration
- [CLI Programmatic Usage](claude-code/cli-programmatic-usage.md) - Run Claude Code programmatically
- [CLI Reference](claude-code/cli-reference.md) - Complete CLI command reference
- [Create Plugins](claude-code/create-plugin.md) - Guide to creating Claude Code plugins
- [Custom Subagents](claude-code/custom-subagents.md) - Define and configure custom subagents
- [Hooks Reference](claude-code/hooks-reference.md) - Complete hooks API reference
- [Memory](claude-code/memory.md) - Manage Claude's memory and context
- [Plugins Reference](claude-code/plugins-reference.md) - Plugin system reference and configuration
- [Agent Teams](claude-code/run-agent-teams.md) - Orchestrate teams of Claude Code sessions
- [Settings](claude-code/settings.md) - Claude Code settings and configuration
- [Skills](claude-code/skills.md) - Extend Claude with skills

---

**Need help?** See the [Troubleshooting Guide](development/TROUBLESHOOTING.md) or check [Getting Help](development/TROUBLESHOOTING.md#getting-help) section.
