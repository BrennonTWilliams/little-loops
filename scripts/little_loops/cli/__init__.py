"""CLI entry points for little-loops tools.

Provides command-line interfaces for automated issue management:
- ll-auto: Sequential issue processing
- ll-parallel: Parallel issue processing with git worktrees
- ll-messages: Extract user messages from Claude Code logs
- ll-loop: FSM-based automation loop execution
- ll-sprint: Sprint and sequence management
- ll-sync: GitHub Issues sync
- ll-history: Completed issue statistics and analysis
- ll-verify-docs: Documentation count verification
- ll-check-links: Markdown link checking
"""

from little_loops.cli.auto import main_auto
from little_loops.cli.docs import main_check_links, main_verify_docs
from little_loops.cli.history import main_history
from little_loops.cli.loop import main_loop
from little_loops.cli.messages import main_messages
from little_loops.cli.next_id import main_next_id
from little_loops.cli.parallel import main_parallel
from little_loops.cli.sprint import (
    _render_dependency_graph,
    _render_execution_plan,
    main_sprint,
)
from little_loops.cli.sync import main_sync

__all__ = [
    "main_auto",
    "main_check_links",
    "main_history",
    "main_loop",
    "main_messages",
    "main_next_id",
    "main_parallel",
    "main_sprint",
    "main_sync",
    "main_verify_docs",
    # Re-exported for backward compatibility (used in tests)
    "_render_execution_plan",
    "_render_dependency_graph",
]
