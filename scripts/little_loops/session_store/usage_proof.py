"""Pure native usage-candidate correspondence proof (ENH-3744).

Given retained replay inputs (stored raw rows decoded into ``UsageReplayRecord``
values, or ``UsageReplayFailure`` markers for rows that could not be decoded) and
the committed ``usage_events`` observations, decide for every logical usage
candidate whether a compatible observation, or an actual native
coalesced/deduplicated representation, exists.

This module is a pure function of its arguments: it reads no files, runs no SQL,
prices nothing and never calls the write normalizers. It also hosts the producer
recognition and value-capture rules the usage writer shares with the proof, so both
read the same native contract. Native keys, paths and raw/observation references
live only on the proof's internal evidence fields and never appear in ``repr`` or
:meth:`UsageCandidateProof.status`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from little_loops.pii import is_replay_safe_history_context
from little_loops.session_store.claude_usage import (
    CLAUDE_USAGE_CONTRACT,
    claude_transcript_contract,
)

if TYPE_CHECKING:
    from little_loops.session_store.writers import UsageReplayRecord

Correspondence = Literal[
    "represented", "missing", "intentional_omission", "excluded_channel", "unprovable"
]

# Prune retention reasons produced from proof outcomes.
RETENTION_GAP = "usage_derive_gap"
RETENTION_UNPROVABLE = "usage_proof_unprovable"
RETENTION_LIMIT = "usage_proof_limit"

CODEX_NATIVE_EVENT_TYPES = frozenset(
    {"session_meta", "turn_context", "token_usage_record", "event_msg"}
)

#: Native payload paths the proof reads for identity/grain, by supported shape. Every
#: entry must be protected by ``pii._protocol_rules`` for its host/event type; a parity
#: test pins this table to the registry. Numeric usage components are captured values,
#: not identity.
PROOF_IDENTITY_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    "claude": (
        ("type",),
        ("sessionId",),
        ("version",),
        ("message", "id"),
        ("message", "model"),
    ),
    "session_meta": (("id",),),
    "turn_context": (("turn_id",), ("model",)),
    "event_msg": (("type",), ("turn_id",)),
    "token_usage_record": (("thread_id",), ("turn_id",), ("response_id",)),
}

_CLAUDE_COMPONENTS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


# -- Types ------------------------------------------------------------------


@dataclass(frozen=True)
class UsageReplayFailure:
    """A retained row that produced no usable ``UsageReplayRecord``.

    ``reason`` is a bounded decode/context code (never exception text). Scope fields
    identify the row only so a failure can be attributed to its source.
    """

    source_label: str
    reason: str
    raw_event_id: int | None = None
    line_no: int | None = None
    ordinal: int | None = None
    host: str | None = None
    event_type: str | None = None


@dataclass(frozen=True)
class UsageCandidateProof:
    """Correspondence outcome for one logical usage candidate (or undecodable row).

    ``matched_observation_ids`` are the committed observations the correspondence
    depends on; ``protected_observation_ids`` are contenders to preserve while proving
    no (or doubtful) correspondence. ``context_raw_event_ids`` are the retained raw
    rows the decision needs and ``supplier_sources`` the ``source_path`` of each
    matched observation's actual supplier (``None`` = source attribution absent).
    All evidence fields are internal.
    """

    correspondence: Correspondence
    reason: str
    host: str | None = field(default=None, repr=False)
    session_id: str | None = field(default=None, repr=False)
    channel: str | None = field(default=None, repr=False)
    source_label: str | None = field(default=None, repr=False)
    raw_event_id: int | None = field(default=None, repr=False)
    native_key: str | None = field(default=None, repr=False)
    matched_observation_ids: tuple[int, ...] = field(default=(), repr=False)
    protected_observation_ids: tuple[int, ...] = field(default=(), repr=False)
    context_raw_event_ids: tuple[int, ...] = field(default=(), repr=False)
    supplier_sources: tuple[str | None, ...] = field(default=(), repr=False)
    supplier_positions: tuple[tuple[int | None, int | None], ...] = field(default=(), repr=False)

    def status(self) -> dict[str, str]:
        """Shareable outcome: bounded correspondence and reason, no native references."""
        return {"correspondence": self.correspondence, "reason": self.reason}


def retention_reasons(proofs: Iterable[UsageCandidateProof]) -> frozenset[str]:
    """Bounded prune retention reasons implied by *proofs* (empty = nothing vetoed)."""
    reasons: set[str] = set()
    for proof in proofs:
        if proof.correspondence == "missing":
            reasons.add(RETENTION_GAP)
        elif proof.correspondence == "unprovable":
            reasons.add(RETENTION_UNPROVABLE)
    return frozenset(reasons)


# -- Shared native recognition (also used by the usage writer) ---------------


@dataclass(frozen=True)
class ClaudeRecognition:
    """Producer-level reading of one Claude-shaped assistant record."""

    kind: Literal["candidate", "omission", "missing_session"]
    session_id: str | None
    message_id: str | None
    model: Any
    usage: dict[str, Any]
    qualified: bool
    observation_key: str | None


def recognize_claude_usage(
    payload: Mapping[str, Any],
    *,
    host: str | None,
    host_basis: str | None,
    usage_contract: str | None,
) -> ClaudeRecognition | None:
    """Classify a Claude-shaped record; ``None`` means it carries no usage candidate.

    ``omission`` is a current-version producer snapshot that is malformed, partial or
    all-zero under a verified message identity: the last valid snapshot for that ID
    wins, so it is deliberately never an observation. ``missing_session`` is
    usage-bearing but has no session identity, so no observation can exist for it.
    A NULL persisted ``usage_contract`` leaves a record unqualified; qualification is
    never derived from the retained payload alone.
    """
    if host in {"codex", "kimi-code"} or payload.get("type") != "assistant":
        return None
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    if usage.get("input_tokens") is None and usage.get("output_tokens") is None:
        return None
    message_id = message.get("id")
    session_id = payload.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return ClaudeRecognition(
            "missing_session",
            None,
            message_id if isinstance(message_id, str) else None,
            message.get("model"),
            usage,
            False,
            None,
        )
    native_contract = claude_transcript_contract(payload, host=host, host_basis=host_basis)
    if (
        host == "claude-code"
        and host_basis == "handle"
        and payload.get("version") == "2.1.284"
        and isinstance(message_id, str)
        and message_id
        and native_contract is None
    ):
        return ClaudeRecognition(
            "omission", session_id, message_id, message.get("model"), usage, False, None
        )
    qualified = usage_contract == CLAUDE_USAGE_CONTRACT and native_contract == CLAUDE_USAGE_CONTRACT
    observation_key = (
        json.dumps([host, session_id, message_id], separators=(",", ":"))
        if qualified and isinstance(message_id, str) and message_id
        else None
    )
    return ClaudeRecognition(
        "candidate",
        session_id,
        message_id if isinstance(message_id, str) else None,
        message.get("model"),
        usage,
        qualified,
        observation_key,
    )


def is_codex_native_record(event_type: str, host: str | None) -> bool:
    """Whether a replay record is a Codex rollout record (not a normalized exec record)."""
    return event_type in CODEX_NATIVE_EVENT_TYPES and (
        host == "codex" or event_type == "session_meta"
    )


def codex_count_signature(info: dict[str, Any]) -> str | None:
    """Dedup signature of a ``token_count`` notification: total and last usage."""
    total = info.get("total_token_usage")
    last = info.get("last_token_usage")
    if not isinstance(total, dict) or not isinstance(last, dict):
        return None
    return json.dumps([total, last], sort_keys=True, separators=(",", ":"))


def is_adjacent_record(
    previous: tuple[dict[str, Any], int | None, int | None] | None,
    ordinal: int | None,
    line_no: int | None,
    usage: dict[str, Any],
) -> bool:
    """Whether a notification is the writer-adjacent copy (``+1`` ordinal, else line)."""
    if previous is None or previous[0] != usage:
        return False
    _, prev_ordinal, prev_line = previous
    if prev_ordinal is not None and ordinal is not None:
        return ordinal == prev_ordinal + 1
    return prev_line is not None and line_no == prev_line + 1


def codex_components(
    usage: dict[str, Any],
) -> tuple[int | None, int | None, int | None, int | None, bool]:
    """Return disjoint components and whether a producer count is complete."""
    from little_loops.subprocess_utils import normalize_codex_input

    split = normalize_codex_input(usage)
    output = usage.get("output_tokens")
    valid_output = type(output) is int and output >= 0
    complete = split.consistent and valid_output
    return (
        split.uncached_input,
        output if valid_output else None,
        split.cache_read,
        split.cache_write,
        complete,
    )


# -- Proof ---------------------------------------------------------------------


@dataclass
class _Cand:
    index: int
    record: Any
    channel: str
    host: str | None
    session_id: str | None
    values: tuple[Any, ...]
    model: Any = None
    turn_id: str | None = None
    request_id: str | None = None
    key: str | None = None
    keyed: bool = False
    thread_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    context: list[int] = field(default_factory=list)
    conflict: bool = False
    follows: _Cand | None = None
    proof: UsageCandidateProof | None = None


class _Index:
    """Observation lookups by exact raw link, Claude key and Codex request identity."""

    def __init__(self, observations: Iterable[Mapping[str, Any]]) -> None:
        self.by_link: dict[int, Mapping[str, Any]] = {}
        self.by_key: dict[str, Mapping[str, Any]] = {}
        self.by_request: dict[str, list[Mapping[str, Any]]] = {}
        for obs in observations:
            link = obs.get("source_raw_event_id")
            if isinstance(link, int):
                self.by_link[link] = obs
            key = obs.get("observation_key")
            if isinstance(key, str):
                self.by_key[key] = obs
            request = obs.get("request_id")
            if isinstance(request, str) and obs.get("channel") == "rollout":
                self.by_request.setdefault(request, []).append(obs)


def _position(record: Any) -> int | None:
    return record.ordinal if record.ordinal is not None else record.line_no


def _order_proven(records: list[Any]) -> bool:
    """Whether native order inside one source is established by strict positions.

    Deterministic SQL sorting is not native ordering proof: positions must be present,
    of one kind, strictly increasing, and (when raw IDs are known) agree with
    ingestion order. Duplicates, resets and contradictions are unproven.
    """
    if len({r.ordinal is None for r in records}) > 1:
        return False
    positions = [_position(r) for r in records]
    if any(p is None for p in positions):
        return False
    if not all(a < b for a, b in zip(positions, positions[1:], strict=False)):  # type: ignore[operator]
        return False
    ids = [r.raw_event_id for r in records]
    if all(i is not None for i in ids):
        return all(a < b for a, b in zip(ids, ids[1:], strict=False))  # type: ignore[operator]
    return True


def _proof(
    cand: _Cand,
    correspondence: Correspondence,
    reason: str,
    *,
    matched: Iterable[Mapping[str, Any]] = (),
    protected: Iterable[Mapping[str, Any]] = (),
    context: Iterable[int] = (),
) -> UsageCandidateProof:
    matched_rows = list(matched)
    ids = tuple(dict.fromkeys(i for i in (*cand.context, *context) if i is not None))
    return UsageCandidateProof(
        correspondence=correspondence,
        reason=reason,
        host=cand.host,
        session_id=cand.session_id,
        channel=cand.channel,
        source_label=cand.record.source_label,
        raw_event_id=cand.record.raw_event_id,
        native_key=cand.key,
        matched_observation_ids=tuple(o["id"] for o in matched_rows if o.get("id") is not None),
        protected_observation_ids=tuple(
            dict.fromkeys(o["id"] for o in (*matched_rows, *protected) if o.get("id") is not None)
        ),
        context_raw_event_ids=ids,
        supplier_sources=tuple(o.get("source_path") for o in matched_rows),
        supplier_positions=tuple(
            (o.get("source_line_no"), o.get("source_ordinal")) for o in matched_rows
        ),
    )


def inspect_usage_candidates(
    records: Iterable[UsageReplayRecord | UsageReplayFailure],
    observations: Iterable[Mapping[str, Any]],
    *,
    channel: str | None = None,
) -> tuple[UsageCandidateProof, ...]:
    """Prove, for every recognized logical usage candidate, whether it is represented.

    *records* is a whole deterministically ordered retained proof scope (all required
    native context included); *observations* are the committed ``usage_events`` rows
    selected by the scope's native identities and exact raw links. The result has one
    proof per candidate, omission or undecodable row, in input order; records that
    carry no usage (benign non-usage) produce none. With *channel*, candidates of other
    acquisition channels are reported ``excluded_channel`` and not evaluated.
    """
    items = list(records)
    index = _Index(observations)
    slots: list[UsageCandidateProof | None] = [None] * len(items)
    claude: list[_Cand] = []
    codex_sources: dict[str, list[tuple[int, Any]]] = {}

    for i, item in enumerate(items):
        if isinstance(item, UsageReplayFailure):
            slots[i] = UsageCandidateProof(
                "unprovable",
                f"decode_{item.reason}",
                host=item.host,
                channel=None,
                source_label=item.source_label,
                raw_event_id=item.raw_event_id,
            )
            continue
        if is_codex_native_record(item.event_type, item.host):
            codex_sources.setdefault(item.source_label, []).append((i, item))
            continue
        recognized = recognize_claude_usage(
            item.payload,
            host=item.host,
            host_basis=item.host_basis,
            usage_contract=item.usage_contract,
        )
        if recognized is None:
            continue
        cand = _claude_cand(i, item, recognized)
        if recognized.kind == "omission":
            cand.proof = _proof(cand, "intentional_omission", "claude_terminal_snapshot")
        elif recognized.kind == "missing_session":
            cand.proof = _proof(cand, "unprovable", "session_identity_missing")
        elif not is_replay_safe_history_context(host=item.host, event_type="assistant"):
            cand.proof = _proof(cand, "unprovable", "identity_path_unregistered")
        elif (
            isinstance(item.session_id, str)
            and item.session_id
            and item.session_id != recognized.session_id
        ):
            cand.proof = _proof(cand, "unprovable", "identity_contradiction")
        elif item.raw_event_id is None:
            cand.proof = _proof(cand, "unprovable", "raw_identity_missing")
        claude.append(cand)

    _evaluate_claude(claude, index)
    codex: list[_Cand] = []
    for pairs in codex_sources.values():
        codex.extend(_walk_codex_source(pairs))
    _evaluate_codex(codex, index)

    for cand in (*claude, *codex):
        slots[cand.index] = cand.proof
    out: list[UsageCandidateProof] = []
    for slot in slots:
        if slot is None:
            continue
        if channel is not None and slot.channel is not None and slot.channel != channel:
            slot = UsageCandidateProof(
                "excluded_channel",
                "channel_filtered",
                host=slot.host,
                session_id=slot.session_id,
                channel=slot.channel,
                source_label=slot.source_label,
                raw_event_id=slot.raw_event_id,
            )
        out.append(slot)
    return tuple(out)


def _claude_cand(index: int, record: Any, rec: ClaudeRecognition) -> _Cand:
    usage = rec.usage
    return _Cand(
        index=index,
        record=record,
        channel="transcript",
        host=record.host,
        session_id=rec.session_id,
        values=(rec.model, *(usage.get(name) for name in _CLAUDE_COMPONENTS)),
        model=rec.model,
        key=rec.observation_key,
        keyed=rec.observation_key is not None,
        context=[record.raw_event_id] if record.raw_event_id is not None else [],
        usage=usage,
    )


def _claude_obs_values(obs: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        obs.get("model"),
        obs.get("input_tokens"),
        obs.get("output_tokens"),
        obs.get("cache_read_input_tokens"),
        obs.get("cache_creation_input_tokens"),
    )


def _evaluate_claude(cands: list[_Cand], index: _Index) -> None:
    keyed: dict[str, list[_Cand]] = {}
    for cand in cands:
        if cand.proof is not None:
            continue
        if cand.keyed and cand.key is not None:
            keyed.setdefault(cand.key, []).append(cand)
            continue
        _evaluate_claude_audit(cand, index)
    for key, members in keyed.items():
        _evaluate_claude_group(key, members, index)


def _identity_matches(obs: Mapping[str, Any], cand: _Cand) -> bool:
    return (
        obs.get("host") == cand.host
        and obs.get("session_id") == cand.session_id
        and obs.get("channel") in (None, cand.channel)
    )


def _evaluate_claude_audit(cand: _Cand, index: _Index) -> None:
    obs = index.by_link.get(cand.record.raw_event_id)
    if obs is None:
        cand.proof = _proof(cand, "missing", "no_exact_link")
    elif obs.get("source_path") != cand.record.source_label or not _identity_matches(obs, cand):
        cand.proof = _proof(cand, "unprovable", "identity_contradiction", protected=[obs])
    elif _claude_obs_values(obs) != cand.values:
        cand.proof = _proof(cand, "unprovable", "value_mismatch", protected=[obs])
    else:
        cand.proof = _proof(cand, "represented", "linked_audit", matched=[obs])


def _evaluate_claude_group(key: str, members: list[_Cand], index: _Index) -> None:
    members.sort(key=lambda c: c.record.raw_event_id)
    winner = members[-1]
    ids = [c.record.raw_event_id for c in members]
    obs = index.by_key.get(key)
    protected = [obs] if obs is not None else []
    verdict: tuple[Correspondence, str, list[Mapping[str, Any]]]

    sources = {c.record.source_label for c in members}
    if len({c.values for c in members}) > 1 and len(sources) > 1:
        verdict = ("unprovable", "cross_source_conflict", [])
    elif not _winner_last(members, winner):
        verdict = ("unprovable", "native_order_unproven", [])
    elif obs is None:
        verdict = ("missing", "no_observation", [])
    elif not _identity_matches(obs, winner):
        verdict = ("unprovable", "identity_contradiction", [])
    elif _claude_obs_values(obs) == winner.values:
        verdict = ("represented", "keyed_snapshot", [obs])
    else:
        link = obs.get("source_raw_event_id")
        if isinstance(link, int) and link > winner.record.raw_event_id:
            verdict = ("represented", "dominated_by_newer_snapshot", [obs])
        else:
            verdict = ("missing", "newer_snapshot_not_captured", [])
    for cand in members:
        cand.proof = _proof(
            cand,
            verdict[0],
            verdict[1],
            matched=verdict[2],
            protected=protected,
            context=ids if verdict[0] != "represented" else [winner.record.raw_event_id],
        )


def _winner_last(members: list[_Cand], winner: _Cand) -> bool:
    """The highest-ID snapshot must also be the latest by position within its source."""
    same = [c for c in members if c.record.source_label == winner.record.source_label]
    if len(same) < 2:
        return True
    positions = [_position(c.record) for c in same]
    if any(p is None for p in positions):
        return False
    return _position(winner.record) == max(positions)  # type: ignore[type-var]


# -- Codex ----------------------------------------------------------------------


@dataclass
class _CodexState:
    thread_id: str | None = None
    current_turn: str | None = None
    model_by_turn: dict[str, str] = field(default_factory=dict)
    closed: set[str] = field(default_factory=set)
    last_count: str | None = None
    last_count_cand: _Cand | None = None
    preceding: tuple[dict[str, Any], int | None, int | None] | None = None
    preceding_cand: _Cand | None = None
    meta_id: int | None = None
    turn_context_ids: dict[str, int] = field(default_factory=dict)
    started_id: int | None = None
    complete_ids: dict[str, int] = field(default_factory=dict)


def _walk_codex_source(pairs: list[tuple[int, Any]]) -> list[_Cand]:
    """Walk one Codex source in replay order, mirroring the writer's request grain."""
    records = [rec for _, rec in pairs]
    cands: list[_Cand] = []

    def blank(index: int, record: Any) -> _Cand:
        return _Cand(
            index=index,
            record=record,
            channel="rollout",
            host=record.host,
            session_id=None,
            values=(),
            context=[record.raw_event_id] if record.raw_event_id is not None else [],
        )

    if not _order_proven(records):
        for index, record in pairs:
            if _codex_may_carry_usage(record):
                cand = blank(index, record)
                cand.proof = _proof(cand, "unprovable", "native_order_unproven")
                cands.append(cand)
        return cands

    state = _CodexState()
    for index, record in pairs:
        payload = record.payload
        rid = record.raw_event_id
        etype = record.event_type
        if etype == "session_meta":
            header_id = payload.get("id")
            if isinstance(header_id, str) and header_id:
                state.thread_id = header_id
                state.meta_id = rid
        elif etype == "turn_context":
            turn_id = payload.get("turn_id")
            model = payload.get("model")
            if isinstance(turn_id, str) and isinstance(model, str) and model and rid is not None:
                state.model_by_turn[turn_id] = model
                state.turn_context_ids[turn_id] = rid
        elif etype == "event_msg":
            subtype = payload.get("type")
            if subtype == "task_started":
                turn_id = payload.get("turn_id")
                state.current_turn = turn_id if isinstance(turn_id, str) else None
                state.last_count = None
                state.last_count_cand = None
                state.preceding = None
                state.preceding_cand = None
                state.started_id = rid
            elif subtype == "task_complete":
                turn_id = payload.get("turn_id")
                if isinstance(turn_id, str):
                    state.closed.add(turn_id)
                    if rid is not None:
                        state.complete_ids[turn_id] = rid
                if turn_id == state.current_turn:
                    state.current_turn = None
            elif subtype == "token_count":
                info = payload.get("info")
                cand = blank(index, record)
                if not isinstance(info, dict) or "last_token_usage" not in info:
                    cand.proof = _proof(
                        cand, "intentional_omission", "codex_rate_limit_notification"
                    )
                    cands.append(cand)
                    continue
                raw_usage = info["last_token_usage"]
                usage = raw_usage if isinstance(raw_usage, dict) else {}
                if is_adjacent_record(state.preceding, record.ordinal, record.line_no, usage):
                    cand.follows = state.preceding_cand
                    state.preceding = None
                    state.preceding_cand = None
                    cands.append(cand)
                    continue
                state.preceding = None
                state.preceding_cand = None
                signature = codex_count_signature(info)
                if signature is not None and signature == state.last_count:
                    cand.follows = state.last_count_cand
                    cands.append(cand)
                    continue
                state.last_count = signature
                _fill_codex(cand, state, usage, turn_id=state.current_turn, request_id=None)
                state.last_count_cand = cand
                cands.append(cand)
        elif etype == "token_usage_record":
            cand = blank(index, record)
            raw_usage = payload.get("usage")
            usage = raw_usage if isinstance(raw_usage, dict) else {}
            turn_id = payload.get("turn_id")
            native_thread = payload.get("thread_id")
            response_id = payload.get("response_id")
            thread = state.thread_id or record.session_id
            valid = (
                isinstance(turn_id, str)
                and bool(turn_id)
                and isinstance(native_thread, str)
                and native_thread == thread
                and isinstance(response_id, str)
                and bool(response_id)
            )
            _fill_codex(
                cand,
                state,
                usage,
                turn_id=turn_id if isinstance(turn_id, str) else None,
                request_id=response_id if isinstance(response_id, str) else None,
            )
            cand.keyed = valid
            if valid:
                cand.key = json.dumps([record.host or "", response_id], separators=(",", ":"))
                state.preceding = (usage, record.ordinal, record.line_no)
                state.preceding_cand = cand
            else:
                state.preceding = None
                state.preceding_cand = None
                if isinstance(native_thread, str) and native_thread != thread:
                    cand.proof = _proof(cand, "unprovable", "identity_contradiction")
            cands.append(cand)
    _finalize_codex_targets(cands, state)
    return cands


def _finalize_codex_targets(cands: list[_Cand], state: _CodexState) -> None:
    """Add the closure each request actually consumed once the whole native span is read.

    A request's value record can precede its ``task_complete``; qualification consumes that
    later closure (the writer decides ``closed`` after the whole source), so it belongs to
    the request's dependency set. Only the request's own turn closure is added -- never
    another turn's -- and the captured value supplier and model are left untouched.
    """
    for cand in cands:
        if cand.proof is not None or cand.turn_id is None:
            continue
        closure = state.complete_ids.get(cand.turn_id)
        if closure is not None and closure not in cand.context:
            cand.context.append(closure)


def _codex_may_carry_usage(record: Any) -> bool:
    if record.event_type == "token_usage_record":
        return True
    if record.event_type != "event_msg":
        return False
    payload = record.payload
    info = payload.get("info")
    return (
        payload.get("type") == "token_count"
        and isinstance(info, dict)
        and "last_token_usage" in info
    )


def _fill_codex(
    cand: _Cand,
    state: _CodexState,
    usage: dict[str, Any],
    *,
    turn_id: str | None,
    request_id: str | None,
) -> None:
    record = cand.record
    cand.usage = usage
    cand.turn_id = turn_id
    cand.request_id = request_id
    cand.thread_id = state.thread_id or record.session_id
    cand.session_id = cand.thread_id
    cand.model = state.model_by_turn.get(turn_id or "")
    uncached, output, cache_read, cache_write, _ = codex_components(usage)
    cand.values = (uncached, output, cache_read, cache_write)
    for extra in (
        state.meta_id,
        state.started_id,
        state.turn_context_ids.get(turn_id or ""),
        state.complete_ids.get(turn_id or ""),
    ):
        if extra is not None:
            cand.context.append(extra)
    if not is_replay_safe_history_context(host=record.host, event_type=record.event_type):
        cand.proof = _proof(cand, "unprovable", "identity_path_unregistered")
    elif (
        state.thread_id
        and isinstance(record.session_id, str)
        and record.session_id
        and record.session_id != state.thread_id
    ):
        cand.proof = _proof(cand, "unprovable", "identity_contradiction")
    elif record.raw_event_id is None:
        cand.proof = _proof(cand, "unprovable", "raw_identity_missing")


def _codex_obs_matches(obs: Mapping[str, Any], cand: _Cand) -> bool:
    uncached, output, cache_read, cache_write = cand.values
    if (
        obs.get("input_tokens"),
        obs.get("output_tokens"),
        obs.get("cache_read_input_tokens"),
        obs.get("cache_creation_input_tokens"),
    ) != (uncached, output, cache_read, cache_write):
        return False
    if obs.get("turn_id") != cand.turn_id:
        return False
    if obs.get("session_id") != cand.thread_id:
        return False
    if obs.get("host") not in (None, cand.host):
        return False
    # Model and closure only qualify an observation; they never invalidate audit correspondence.
    model = obs.get("model")
    return not (model is not None and cand.model is not None and model != cand.model)


def models_compatible(first: Any, second: Any) -> bool:
    """Whether two consumed models can belong to one request (missing context is compatible).

    Equal counts with two *known, different* models are not an identical copy; an absent
    model alone is never evidence of a different request (ENH-3770).
    """
    return first is None or second is None or first == second


def _evaluate_codex(cands: list[_Cand], index: _Index) -> None:
    # Response-copy dedup follows the writer: first copy per (host, response) wins;
    # identical thread/turn/usage copies coalesce, conflicting copies stay separate.
    seen: dict[str, _Cand] = {}
    for cand in cands:
        if cand.proof is not None or cand.follows is not None or not cand.keyed or cand.key is None:
            continue
        earlier = seen.get(cand.key)
        if earlier is None:
            seen[cand.key] = cand
        elif (
            earlier.thread_id == cand.thread_id
            and earlier.turn_id == cand.turn_id
            and earlier.usage == cand.usage
            and models_compatible(earlier.model, cand.model)
        ):
            cand.follows = earlier
        else:
            earlier.conflict = True
            cand.conflict = True
    for cand in cands:
        if cand.proof is None and cand.follows is None:
            _evaluate_codex_one(cand, index)
    for cand in cands:
        if cand.proof is not None:
            continue
        target = cand.follows
        while target is not None and target.proof is None:
            target = target.follows
        if target is None or target.proof is None:
            cand.proof = _proof(cand, "unprovable", "coalesced_target_unresolved")
            continue
        base = target.proof
        cand.proof = UsageCandidateProof(
            correspondence=base.correspondence,
            reason="coalesced_copy" if base.correspondence == "represented" else base.reason,
            host=cand.host,
            session_id=base.session_id,
            channel=cand.channel,
            source_label=cand.record.source_label,
            raw_event_id=cand.record.raw_event_id,
            native_key=base.native_key,
            matched_observation_ids=base.matched_observation_ids,
            protected_observation_ids=base.protected_observation_ids,
            context_raw_event_ids=tuple(
                dict.fromkeys((*cand.context, *base.context_raw_event_ids))
            ),
            supplier_sources=base.supplier_sources,
            supplier_positions=base.supplier_positions,
        )


def _evaluate_codex_one(cand: _Cand, index: _Index) -> None:
    link = index.by_link.get(cand.record.raw_event_id)
    if cand.keyed and not cand.conflict and cand.request_id is not None:
        group = list(index.by_request.get(cand.request_id, ()))
        compat = [o for o in group if _codex_obs_matches(o, cand)]
        if compat:
            cand.proof = _proof(cand, "represented", "native_response", matched=compat)
            return
        if group:
            cand.proof = _proof(cand, "unprovable", "value_mismatch", protected=group)
            return
    if link is None:
        cand.proof = _proof(cand, "missing", "no_exact_link")
    elif link.get("source_path") != cand.record.source_label:
        cand.proof = _proof(cand, "unprovable", "link_source_mismatch", protected=[link])
    elif _codex_obs_matches(link, cand):
        cand.proof = _proof(cand, "represented", "linked_audit", matched=[link])
    else:
        cand.proof = _proof(cand, "unprovable", "value_mismatch", protected=[link])
