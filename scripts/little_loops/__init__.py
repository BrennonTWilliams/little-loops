"""little-loops: Development workflow toolkit for Claude Code.

This package provides automation tools for issue management, code quality checks,
and development workflows that can be configured for any software project.
"""

from little_loops.config import BRConfig
from little_loops.events import EventBus, LLEvent
from little_loops.extension import (
    ActionProviderExtension,
    EvaluatorProviderExtension,
    ExtensionLoader,
    InterceptorExtension,
    LLExtension,
    LLHookIntentExtension,
    NoopLoggerExtension,
    wire_extensions,
)
from little_loops.fsm import RouteContext, RouteDecision
from little_loops.git_operations import check_git_status
from little_loops.hooks.types import LLHookEvent, LLHookResult
from little_loops.host_runner import (
    CapabilityEntry,
    CapabilityNotSupported,
    CapabilityReport,
    HookEntry,
    HostInvocation,
    HostNotConfigured,
    HostRunner,
    apply_host_cli_from_config,
)
from little_loops.issue_lifecycle import (
    FailureType,
    classify_failure,
    close_issue,
    complete_issue_lifecycle,
    create_issue_from_failure,
    verify_issue_completed,
)
from little_loops.issue_manager import AutoManager
from little_loops.learning_tests import LearnTestRecord, check_learning_test
from little_loops.output_parsing import parse_manage_issue_output, parse_ready_issue_output
from little_loops.pii import apply_pii_action, detect_pii, redact_pii
from little_loops.session_store import SQLiteTransport, record_issue_snapshot
from little_loops.sync import GitHubSyncManager, SyncResult, SyncStatus
from little_loops.testing import LLTestBus
from little_loops.transport import (
    JsonlTransport,
    OTelTransport,
    Transport,
    UnixSocketTransport,
    WebhookTransport,
    wire_transports,
)
from little_loops.work_verification import (
    EXCLUDED_DIRECTORIES,
    filter_excluded_files,
    verify_work_was_done,
)

__version__ = "1.142.0"
__all__ = [
    "BRConfig",
    # learning_tests
    "LearnTestRecord",
    "check_learning_test",
    # events
    "EventBus",
    "LLEvent",
    # hooks
    "LLHookEvent",
    "LLHookResult",
    # host runner
    "CapabilityEntry",
    "CapabilityNotSupported",
    "CapabilityReport",
    "HookEntry",
    "HostInvocation",
    "HostNotConfigured",
    "HostRunner",
    "apply_host_cli_from_config",
    # extensions
    "ActionProviderExtension",
    "EvaluatorProviderExtension",
    "ExtensionLoader",
    "InterceptorExtension",
    "LLExtension",
    "LLHookIntentExtension",
    "NoopLoggerExtension",
    "wire_extensions",
    # testing
    "LLTestBus",
    # transport
    "JsonlTransport",
    "OTelTransport",
    "SQLiteTransport",
    "record_issue_snapshot",
    "Transport",
    "UnixSocketTransport",
    "WebhookTransport",
    "wire_transports",
    # fsm
    "RouteContext",
    "RouteDecision",
    # git_operations
    "check_git_status",
    # work_verification
    "EXCLUDED_DIRECTORIES",
    "filter_excluded_files",
    "verify_work_was_done",
    # issue_lifecycle
    "FailureType",
    "classify_failure",
    "close_issue",
    "complete_issue_lifecycle",
    "create_issue_from_failure",
    "verify_issue_completed",
    # output_parsing
    "parse_manage_issue_output",
    "parse_ready_issue_output",
    # issue_manager
    "AutoManager",
    # sync
    "GitHubSyncManager",
    "SyncResult",
    "SyncStatus",
    # pii
    "apply_pii_action",
    "detect_pii",
    "redact_pii",
]
