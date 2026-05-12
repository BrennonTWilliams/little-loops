"""Hook intent types: host-agnostic dataclasses for hook events and results.

`LLHookEvent` and `LLHookResult` are the wire format for the hook-intent
abstraction layer (FEAT-1116). Per-host adapters parse the host's native
hook payload into `LLHookEvent`, invoke a core intent handler, and translate
the returned `LLHookResult` back into the host's expected response (exit
code + stderr for Claude Code; structured object for OpenCode; etc.).

Sibling type to ``little_loops.events.LLEvent`` — see ``docs/reference/EVENT-SCHEMA.md``.
``LLEvent`` is pub/sub fire-and-forget; hook intents are request/response,
so they live on a separate dataclass with its own ``to_dict``/``from_dict``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLHookEvent:
    """Host-agnostic hook event payload.

    Attributes:
        host: Host agent identifier (e.g. ``"claude-code"``, ``"opencode"``).
            Required — adapters set this to identify the source host so that
            core handlers can branch on host-specific quirks if needed.
        intent: Hook intent name (e.g. ``"pre_compact"``, ``"session_start"``,
            ``"pre_tool_use"``). Matches the module under
            ``scripts/little_loops/hooks/`` that handles this intent.
        timestamp: ISO 8601 timestamp string (UTC) for when the host emitted
            the hook event.
        payload: Host-supplied event data (tool name, args, session_id, cwd,
            etc.). Schema is intent-specific and documented per-intent.
        session_id: Host session identifier when available. Optional because
            not every hook intent carries a session.
        cwd: Working directory the host was operating in. Optional.
    """

    host: str
    intent: str = ""
    timestamp: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    cwd: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dict for JSON transport.

        Skips ``None``-valued optional fields so the wire format stays
        compact and unambiguous (a missing key means "not provided" rather
        than "explicitly null").
        """
        out: dict[str, Any] = {
            "host": self.host,
            "intent": self.intent,
            "ts": self.timestamp,
            "payload": self.payload,
        }
        if self.session_id is not None:
            out["session_id"] = self.session_id
        if self.cwd is not None:
            out["cwd"] = self.cwd
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLHookEvent:
        """Reconstruct from a flat dict (JSON deserialization).

        Accepts both wire-format keys (``ts``) and field-name aliases
        (``timestamp``) for robustness, matching the precedent set by
        ``LLEvent.from_dict``.
        """
        return cls(
            host=data.get("host", ""),
            intent=data.get("intent", ""),
            timestamp=data.get("ts", data.get("timestamp", "")),
            payload=data.get("payload", {}) or {},
            session_id=data.get("session_id"),
            cwd=data.get("cwd"),
        )


@dataclass
class LLHookResult:
    """Host-agnostic hook handler response.

    Adapters translate this into the host's expected reply shape — exit
    code + stderr for Claude Code shell hooks, a structured object for
    OpenCode TS plugins, etc.

    Attributes:
        exit_code: Numeric exit code semantics borrowed from Claude Code:
            ``0`` means pass, ``2`` means "block and inject ``feedback`` into
            the model's context". Non-Claude hosts map this to their own
            permit/deny semantics.
        feedback: Optional human-readable message. For Claude Code, this is
            written to stderr when ``exit_code == 2``. For permission-style
            intents (PreToolUse), this is the rationale for the decision.
        decision: Optional permission decision for permission-checking
            intents (e.g. ``"allow"``, ``"deny"``, ``"ask"``). ``None`` for
            intents that don't make permission decisions.
        data: Additional structured data the handler wants returned to the
            host (e.g. stdout JSON for Claude Code's structured-response
            intents). Default empty dict.
        stdout: Optional raw payload to be written to the host's stdout stream
            (e.g. SessionStart's merged config JSON, which Claude Code ingests
            as session context). ``None`` means "write nothing to stdout".
            Adapters that don't model a stdout channel may ignore this field.
    """

    exit_code: int = 0
    feedback: str | None = None
    decision: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    stdout: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dict for JSON transport.

        Skips ``None``-valued optional fields and the empty ``data`` dict
        so the wire format stays compact.
        """
        out: dict[str, Any] = {"exit_code": self.exit_code}
        if self.feedback is not None:
            out["feedback"] = self.feedback
        if self.decision is not None:
            out["decision"] = self.decision
        if self.data:
            out["data"] = self.data
        if self.stdout is not None:
            out["stdout"] = self.stdout
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLHookResult:
        """Reconstruct from a flat dict (JSON deserialization)."""
        return cls(
            exit_code=data.get("exit_code", 0),
            feedback=data.get("feedback"),
            decision=data.get("decision"),
            data=data.get("data", {}) or {},
            stdout=data.get("stdout"),
        )
