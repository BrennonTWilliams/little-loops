"""CLI entry points for little-loops tools.

Provides command-line interfaces for automated issue management:
- ll-action: Invoke ll skills as one-shot commands with JSON-structured output
- ll-auto: Process all backlog issues sequentially in priority order
- ll-parallel: Process issues concurrently using isolated git worktrees
- ll-sprint: Define and execute curated issue sets with dependency-aware ordering
- ll-loop: Execute FSM-based automation loops
- ll-workflows: Identify multi-step workflow patterns from user message history
- ll-messages: Extract user messages from Claude Code logs
- ll-history: Completed issue statistics and analysis
- ll-logs: Discover and extract ll-relevant JSONL entries from ~/.claude/projects/
- ll-deps: Cross-issue dependency discovery and validation
- ll-sync: GitHub Issues sync
- ll-verify-docs: Documentation count verification
- ll-check-links: Markdown link checking
- ll-issues: Issue management and visualization utilities
- ll-gitignore: Suggest and apply .gitignore patterns
- ll-migrate: One-time migration of completed/deferred issues to type-based directories
- ll-migrate-relationships: Rename parent_issue:/related: frontmatter keys to parent:/relates_to:
- ll-migrate-labels: Migrate freeform ## Labels body sections to labels: frontmatter
- ll-create-extension: Scaffold a new little-loops extension project
- ll-generate-schemas: Generate JSON Schema files for all LLEvent types (internal: dev tooling)
- ll-generate-skill-descriptions: Auto-generate ≤100-char skill descriptions via Claude CLI
- ll-learning-tests: Query and manage the learning test registry
"""

from little_loops.cli.action import main_action
from little_loops.cli.auto import main_auto
from little_loops.cli.create_extension import main_create_extension
from little_loops.cli.deps import main_deps
from little_loops.cli.docs import main_check_links, main_verify_docs, main_verify_skill_budget
from little_loops.cli.generate_skill_descriptions import main_generate_skill_descriptions
from little_loops.cli.gitignore import main_gitignore
from little_loops.cli.history import main_history
from little_loops.cli.issues import main_issues
from little_loops.cli.learning_tests import main_learning_tests
from little_loops.cli.logs import main_logs
from little_loops.cli.loop import main_loop
from little_loops.cli.messages import main_messages
from little_loops.cli.migrate import main_migrate
from little_loops.cli.migrate_labels import main_migrate_labels
from little_loops.cli.migrate_relationships import main_migrate_relationships
from little_loops.cli.parallel import main_parallel
from little_loops.cli.schemas import main_generate_schemas  # internal: dev tooling
from little_loops.cli.sprint import (
    _render_dependency_graph,
    _render_execution_plan,
    _render_health_summary,
    main_sprint,
)
from little_loops.cli.sync import main_sync

__all__ = [
    "main_action",
    "main_auto",
    "main_check_links",
    "main_create_extension",
    "main_deps",
    "main_generate_schemas",  # internal: dev tooling
    "main_generate_skill_descriptions",
    "main_gitignore",
    "main_history",
    "main_migrate",
    "main_migrate_labels",
    "main_migrate_relationships",
    "main_learning_tests",
    "main_logs",
    "main_issues",
    "main_loop",
    "main_messages",
    "main_parallel",
    "main_sprint",
    "main_sync",
    "main_verify_docs",
    "main_verify_skill_budget",
    # Re-exported for backward compatibility (used in tests)
    "_render_execution_plan",
    "_render_dependency_graph",
    "_render_health_summary",
]
