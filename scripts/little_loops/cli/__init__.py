"""CLI entry points for little-loops tools.

Provides command-line interfaces for automated issue management:
- ll-harness: One-shot runner evaluation (skill, cmd, mcp, prompt) with exit-code and semantic criteria
- ll-action: Invoke ll skills as one-shot commands with JSON-structured output
- ll-adapt-agents-for-codex: Add Codex subagent TOML files to .codex/agents/
- ll-adapt-skills-for-codex: Add Codex Skills API frontmatter to ll skill SKILL.md files
- ll-auto: Process all backlog issues sequentially in priority order
- ll-parallel: Process issues concurrently using isolated git worktrees
- ll-sprint: Define and execute curated issue sets with dependency-aware ordering
- ll-loop: Execute FSM-based automation loops
- ll-workflows: Identify multi-step workflow patterns from user message history
- ll-messages: Extract user messages from Claude Code logs
- ll-history: Completed issue statistics and analysis
- ll-logs: Discover, extract, and analyze ll-relevant JSONL entries from ~/.claude/projects/ (scan-failures mines failed ll-* calls)
- ll-session: Query the unified session store (SQLite + FTS5)
- ll-history-context: render a ## Historical Context block for an issue from .ll/history.db
- ll-deps: Cross-issue dependency discovery and validation
- ll-sync: GitHub Issues sync
- ll-verify-docs: Documentation count verification
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
"""

from little_loops.cli.action import main_action
from little_loops.cli.adapt_agents_for_codex import main_adapt_agents_for_codex
from little_loops.cli.adapt_skills_for_codex import main_adapt_skills_for_codex
from little_loops.cli.auto import main_auto
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
from little_loops.cli.verify_triggers import main_verify_triggers
from little_loops.init.cli import main_init

__all__ = [
    "main_action",
    "main_harness",
    "main_adapt_agents_for_codex",
    "main_adapt_skills_for_codex",
    "main_auto",
    "main_check_links",
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
    "main_verify_skill_budget",
    "main_verify_skills",
    "main_verify_triggers",
    # Re-exported for backward compatibility (used in tests)
    "_render_execution_plan",
    "_render_dependency_graph",
    "_render_health_summary",
]
