"""Reference interceptor extension for little-loops.

Demonstrates passthrough ``before_route()`` and ``before_issue_close()``
behavior. Copy this class, rename it, and replace the return values with
real veto or routing logic.
"""

from __future__ import annotations

from little_loops import RouteContext, RouteDecision
from little_loops.issue_parser import IssueInfo


class ReferenceInterceptorExtension:
    """Reference implementation demonstrating passthrough interceptor behavior.

    ``before_route()`` and ``before_issue_close()`` both return ``None``,
    which means "pass through without modifying the decision."

    To build a real interceptor:
    1. Copy this class and rename it.
    2. Implement ``before_route`` to redirect or veto FSM routing by returning
       a ``RouteDecision`` instance (``RouteDecision(None)`` vetoes the
       transition; ``RouteDecision("state_name")`` redirects to that state).
    3. Implement ``before_issue_close`` to veto an issue close by returning
       ``False``; return ``None`` to allow the close to proceed.
    4. Register your class in ``ll-config.json`` under the ``extensions`` key
       as ``"your_package.module:YourClassName"``.
    """

    def before_route(self, context: RouteContext) -> RouteDecision | None:
        """Return None to pass through without modifying routing.

        Return a ``RouteDecision`` to redirect or veto the FSM transition:
        - ``RouteDecision("state_name")`` — redirect to a different state
        - ``RouteDecision(None)`` — veto the transition (no state change)
        """
        return None

    def before_issue_close(self, info: IssueInfo) -> bool | None:
        """Return None to pass through; return False to veto the close.

        Args:
            info: Parsed issue information for the issue being closed.

        Returns:
            ``None`` to allow the close to proceed, ``False`` to veto it.
        """
        return None
