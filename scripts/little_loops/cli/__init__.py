"""CLI entry points for little-loops tools.

Provides command-line interfaces for automated issue management:
- ll-harness: One-shot runner evaluation (skill, cmd, mcp, prompt, dsl) with exit-code and semantic criteria
- ll-action: Invoke ll skills as one-shot commands with JSON-structured output
- ll-artifact: Generate self-contained human-facing HTML artifacts (policy-builder: file://-safe policy-router/rubric loop builder)
- ll-adapt: Unified host-parameterized skill/command/agent adapter (--host codex|omp|...)
- ll-adapt-agents-for-codex: Add Codex subagent TOML files to .codex/agents/ (alias for ll-adapt --host codex)
- ll-adapt-skills-for-codex: Add Codex Skills API frontmatter to ll skill SKILL.md files (alias for ll-adapt --host codex)
- ll-auto: Process all backlog issues sequentially in priority order
- ll-parallel: Process issues concurrently using isolated git worktrees
- ll-sprint: Define and execute curated issue sets with dependency-aware ordering
- ll-loop: Execute FSM-based automation loops
- ll-workflows: Identify multi-step workflow patterns from user message history
- ll-messages: Extract user messages from Claude Code logs
- ll-history: Completed issue statistics and analysis
- ll-logs: Discover, extract, and analyze ll-relevant JSONL entries from ~/.claude/projects/ (scan-failures mines failed ll-* calls)
- ll-session: Query the unified session store (SQLite + FTS5)
- ll-compact-session: Manually trigger LCM session-memory compaction for one session (distinct from `ll-session compact`'s retention sweep)
- ll-history-context: render a ## Historical Context block for an issue from .ll/history.db
- ll-deps: Cross-issue dependency discovery and validation
- ll-sync: GitHub Issues sync
- ll-verify-docs: Documentation count verification
- ll-verify-package-data: Lint package code for __file__ escapes and verify manifest assets are in-wheel
- ll-verify-design-tokens: Structural lint for half-flipped design-token theme profiles
- ll-verify-des-audit: Walk source tree and verify every event-emit site maps to a registered DES variant (ENH-2475 / F5 adoption gate)
- ll-check-links: Markdown link checking
- ll-issues: Issue management and visualization utilities
- ll-gitignore: Suggest and apply .gitignore patterns
- ll-init: Initialize little-loops for a project (headless; --yes/--plan/apply modes)
- ll-migrate: One-time migration of completed/deferred issues to type-based directories
- ll-migrate-relationships: Rename parent_issue:/related: frontmatter keys to parent:/relates_to:
- ll-migrate-labels: Migrate freeform ## Labels body sections to labels: frontmatter
- ll-migrate-status: Normalize non-canonical status: values to canonical ones (one-time, ENH-1551)
- ll-create-extension: Scaffold a new little-loops extension project
- ll-ctx-stats: Show context-window analytics for the current project
- ll-generate-schemas: Generate JSON Schema files for all LLEvent types (internal: dev tooling)
- ll-generate-skill-descriptions: Auto-generate ≤100-char skill descriptions via Claude CLI
- ll-learning-tests: Query and manage the learning test registry
- ll-doctor: Check host CLI capability support for little-loops features
- ll-code: Structural code queries (callers, callees, imports, impact) via a pluggable provider protocol
"""

from little_loops.cli.action import main_action
from little_loops.cli.adapt import main_adapt
from little_loops.cli.adapt_agents_for_codex import main_adapt_agents_for_codex
from little_loops.cli.adapt_skills_for_codex import main_adapt_skills_for_codex
from little_loops.cli.artifact import main_artifact
from little_loops.cli.auto import main_auto
from little_loops.cli.code import main_code
from little_loops.cli.compact_session import main_compact_session
from little_loops.cli.create_extension import main_create_extension
from little_loops.cli.ctx_stats import main_ctx_stats
from little_loops.cli.deps import main_deps
from little_loops.cli.docs import (
    main_check_links,
    main_verify_docs,
    main_verify_skill_budget,
    main_verify_skills,
)
from little_loops.cli.doctor import main_doctor
from little_loops.cli.generate_skill_descriptions import main_generate_skill_descriptions
from little_loops.cli.gitignore import main_gitignore
from little_loops.cli.harness import main_harness
from little_loops.cli.history import main_history
from little_loops.cli.history_context import main_history_context
from little_loops.cli.issues import main_issues
from little_loops.cli.learning_tests import main_learning_tests
from little_loops.cli.logs import main_logs
from little_loops.cli.loop import main_loop
from little_loops.cli.messages import main_messages
from little_loops.cli.migrate import main_migrate
from little_loops.cli.migrate_labels import main_migrate_labels
from little_loops.cli.migrate_relationships import main_migrate_relationships
from little_loops.cli.migrate_status import main_migrate_status
from little_loops.cli.parallel import main_parallel
from little_loops.cli.schemas import main_generate_schemas  # internal: dev tooling
from little_loops.cli.session import main_session
from little_loops.cli.sprint import (
    _render_dependency_graph,
    _render_execution_plan,
    _render_health_summary,
    main_sprint,
)
from little_loops.cli.sync import main_sync
from little_loops.cli.verify_decisions import main_verify_decisions
from little_loops.cli.verify_des_audit import main_verify_des_audit
from little_loops.cli.verify_design_tokens import main_verify_design_tokens
from little_loops.cli.verify_kinds import main_verify_kinds
from little_loops.cli.verify_package_data import main_verify_package_data
from little_loops.cli.verify_triggers import main_verify_triggers
from little_loops.init.cli import main_init

__all__ = [
    "main_action",
    "main_adapt",
    "main_artifact",
    "main_harness",
    "main_adapt_agents_for_codex",
    "main_adapt_skills_for_codex",
    "main_auto",
    "main_check_links",
    "main_code",
    "main_compact_session",
    "main_create_extension",
    "main_ctx_stats",
    "main_deps",
    "main_doctor",
    "main_generate_schemas",  # internal: dev tooling
    "main_generate_skill_descriptions",
    "main_gitignore",
    "main_init",
    "main_history",
    "main_history_context",
    "main_migrate",
    "main_migrate_labels",
    "main_migrate_relationships",
    "main_migrate_status",
    "main_learning_tests",
    "main_logs",
    "main_issues",
    "main_loop",
    "main_messages",
    "main_parallel",
    "main_session",
    "main_sprint",
    "main_sync",
    "main_verify_docs",
    "main_verify_design_tokens",
    "main_verify_decisions",
    "main_verify_des_audit",
    "main_verify_package_data",
    "main_verify_kinds",
    "main_verify_skill_budget",
    "main_verify_skills",
    "main_verify_triggers",
    # Re-exported for backward compatibility (used in tests)
    "_render_execution_plan",
    "_render_dependency_graph",
    "_render_health_summary",
]
