"""CLI entry points for little-loops tools.

Provides command-line interfaces for automated issue management:
- ll-auto: Process all backlog issues sequentially in priority order
- ll-parallel: Process issues concurrently using isolated git worktrees
- ll-sprint: Define and execute curated issue sets with dependency-aware ordering
- ll-loop: Execute FSM-based automation loops
- ll-workflows: Identify multi-step workflow patterns from user message history
- ll-messages: Extract user messages from Claude Code logs
- ll-history: Completed issue statistics and analysis
- ll-deps: Cross-issue dependency discovery and validation
- ll-sync: GitHub Issues sync
- ll-verify-docs: Documentation count verification
- ll-check-links: Markdown link checking
- ll-issues: Issue management and visualization utilities
- ll-gitignore: Suggest and apply .gitignore patterns
- ll-create-extension: Scaffold a new little-loops extension project
- ll-generate-schemas: Generate JSON Schema files for all LLEvent types (internal: dev tooling)
"""

from little_loops.cli.auto import main_auto
from little_loops.cli.create_extension import main_create_extension
from little_loops.cli.deps import main_deps
from little_loops.cli.docs import main_check_links, main_verify_docs
from little_loops.cli.gitignore import main_gitignore
from little_loops.cli.history import main_history
from little_loops.cli.issues import main_issues
from little_loops.cli.loop import main_loop
from little_loops.cli.messages import main_messages
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
    "main_auto",
    "main_check_links",
    "main_create_extension",
    "main_deps",
    "main_generate_schemas",  # internal: dev tooling
    "main_gitignore",
    "main_history",
    "main_issues",
    "main_loop",
    "main_messages",
    "main_parallel",
    "main_sprint",
    "main_sync",
    "main_verify_docs",
    # Re-exported for backward compatibility (used in tests)
    "_render_execution_plan",
    "_render_dependency_graph",
    "_render_health_summary",
]
