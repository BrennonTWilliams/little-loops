"""Capability-rank comparison and consult path for the advisor.

`MODEL_RANKS`/`rank_model`/`check_floor` (FEAT-3108) are a self-declared
ordinal within each host, not derived from a benchmark — for `claude-code`
it follows the conventional tier naming (haiku < sonnet < opus), with
`fable` placed as the top flagship tier. Every other host key carries an
empty rank table until a follow-up issue gives it real capability data;
`rank_model` returns `None` for any model on those hosts, and `check_floor`
classifies that as `unknown` rather than guessing.

`consult()`/`AdvisorVerdict` (FEAT-3120) compose FEAT-3042's named-host
transport with the floor check above into the accountable, signal-cited
consult contract. `consult()` uses the subprocess transport exclusively
(`resolve_host_named` -> `build_blocking_json` -> `run_blocking_json`), so
it structurally never touches `derive_input_hash` or
`dispatch_anthropic_request` — this is deliberate so a future FSM-integrated
advisor state (FEAT-3039) doesn't accidentally wire a consult into either
mechanism.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from little_loops.file_utils import acquire_lock, atomic_write_json
from little_loops.host_runner import (
    BlockingJsonError,
    HostNotConfigured,
    resolve_host,
    resolve_host_named,
    resolve_model_alias,
    run_blocking_json,
)

if TYPE_CHECKING:
    from little_loops.config import BRConfig

logger = logging.getLogger(__name__)

# Per-host capability rank, keyed on the concrete model ID that
# `resolve_model_alias()` normalizes aliases to (host_runner.py:79-84).
# Higher rank == more capable. Hosts with no populated table below rank
# every model as unknown (`rank_model` returns None) rather than guessing.
MODEL_RANKS: dict[str, dict[str, int]] = {
    "claude-code": {
        "claude-haiku-4-5": 1,
        "claude-sonnet-5": 2,
        "claude-opus-5": 3,
        "claude-fable-5": 4,
    },
    "codex": {},
    "opencode": {},
    "pi": {},
    "gemini": {},
    "omp": {},
    "kimi-code": {},
}


@dataclass(frozen=True)
class FloorResult:
    """Outcome of comparing an advisor model's rank against the main model's.

    Mirrors `host_runner.CapabilityEntry` / `cli.doctor.CheckResult`'s
    frozen-dataclass + closed-`Literal`-status shape. `status` is `"ok"`
    (advisor ranks at or above main, same host), `"violation"` (same host,
    advisor ranks below main), `"advisory"` (cross-host — ranks aren't
    comparable across hosts), or `"unknown"` (either model unrankable).
    """

    status: Literal["ok", "violation", "advisory", "unknown"]
    detail: str


def rank_model(host: str, model: str) -> int | None:
    """Capability rank of *model* within *host*; `None` when unrankable.

    Normalizes *model* through `resolve_model_alias()` before lookup, so an
    alias (`"opus"`) and its concrete ID (`"claude-opus-5"`) rank the same.
    """
    normalized = resolve_model_alias(model)
    return MODEL_RANKS.get(host, {}).get(normalized)


def check_floor(
    advisor_host: str, advisor_model: str, main_host: str, main_model: str
) -> FloorResult:
    """Classify an advisor/main model pairing against the capability floor.

    The cross-host check runs before rank lookup: two hosts' rank tables
    are separate ordinal spaces, so a host mismatch is `"advisory"`
    regardless of whether either model happens to be individually
    rankable. `"unknown"` only applies within a single host, when either
    model can't be ranked there. Equality (advisor rank == main rank, same
    host) classifies as `"ok"` — an advisor no weaker than the main model
    satisfies the floor.
    """
    if advisor_host != main_host:
        return FloorResult(
            status="advisory",
            detail=(
                f"cross-host pairing, ranks not comparable: "
                f"{advisor_host}/{advisor_model} vs {main_host}/{main_model}"
            ),
        )

    advisor_rank = rank_model(advisor_host, advisor_model)
    main_rank = rank_model(main_host, main_model)

    if advisor_rank is None or main_rank is None:
        return FloorResult(
            status="unknown",
            detail=(
                f"unrankable pairing: {advisor_host}/{advisor_model} vs {main_host}/{main_model}"
            ),
        )

    if advisor_rank < main_rank:
        return FloorResult(
            status="violation",
            detail=(
                f"advisor {advisor_model} (rank {advisor_rank}) ranks below "
                f"main {main_model} (rank {main_rank}) on {advisor_host}"
            ),
        )

    return FloorResult(
        status="ok",
        detail=(
            f"advisor {advisor_model} (rank {advisor_rank}) meets the floor "
            f"set by main {main_model} (rank {main_rank}) on {advisor_host}"
        ),
    )


# Sent to the host at build time (`build_blocking_json(json_schema=...)`), not
# via `run_blocking_json(schema=...)` — the latter only handles the inline
# `--json-schema` case, while codex needs the schema materialized into a
# temp file at build time. `signal`/`host`/`model` are stamped locally by
# `consult()`, not requested from the model.
_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommendation": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "dissent": {"type": "string"},
    },
    "required": ["recommendation", "risks", "confidence", "dissent"],
}

_VERDICT_KEYS = frozenset({"recommendation", "risks", "confidence", "dissent"})


@dataclass(frozen=True)
class AdvisorVerdict:
    """A structured, signal-cited consult response from the advisor host."""

    recommendation: str
    risks: list[str]
    confidence: float
    dissent: str
    signal: str
    host: str
    model: str


class AdvisorNotConfigured(RuntimeError):
    """No advisor host resolved — no ``--host`` flag and no ``advisor.host`` in config."""


class CapabilityFloorViolation(RuntimeError):
    """`check_floor()` classified the advisor/main pairing as `"violation"`.

    Same-host pairing where the advisor ranks below the main model —
    refuses the consult per MR-1 (no self-decided escalation on vibes).
    """

    def __init__(self, floor: FloorResult) -> None:
        super().__init__(floor.detail)
        self.floor = floor


def consult(
    *,
    question: str,
    signal: str,
    context: str = "",
    config: BRConfig | None = None,
    main_host: str | None = None,
    main_model: str | None = None,
) -> AdvisorVerdict:
    """Issue one blocking, signal-cited consult to the configured advisor host.

    Resolves the advisor host/model from *config* (``.ll/ll-config.json``'s
    ``advisor`` block, overridden by the CLI's ``--host``/``--model`` flags
    via direct mutation of ``config.advisor`` before this call — see
    ``cli/advise.py``), gates the pairing through `check_floor` (FEAT-3108),
    and — for anything but a `"violation"` — issues one
    `run_blocking_json` call against `resolve_host_named(advisor_host)`,
    independent of the ambient `orchestration.host_cli` / `LL_HOST_CLI`.

    Never calls `apply_host_cli_from_config()`; never touches
    `derive_input_hash` or `dispatch_anthropic_request` (satisfied by
    construction — this function only reaches the subprocess transport).

    Args:
        question: The consult prompt.
        signal: What prompted this consult (e.g. `"score_stall"`,
            `"user_requested"`). Required by the caller (`main_advise`
            enforces this via argparse); every consult is signal-cited.
        context: Optional caller-authored context appended to the prompt.
            Never an auto-slurp of the working tree.
        config: Project config; defaults to `BRConfig(Path.cwd())`.
        main_host: The host running the primary session, for the floor
            check. Defaults to the ambient `resolve_host().name`.
        main_model: The model running the primary session, for the floor
            check. Defaults to `fsm.schema.DEFAULT_LLM_MODEL`.

    Returns:
        The structured `AdvisorVerdict`.

    Raises:
        AdvisorNotConfigured: no `advisor.host` resolved.
        CapabilityFloorViolation: `check_floor()` returns `"violation"`.
        HostNotConfigured: the advisor host isn't registered or isn't on
            PATH (`resolve_host_named` / ambient `resolve_host` for
            `main_host`).
        BlockingJsonError: the transport call times out, the binary is
            missing, the subprocess exits non-zero, or the structured
            output can't be parsed — including a `shape_mismatch` detail
            flag when a tag-fallback parse succeeds but doesn't carry the
            `AdvisorVerdict` keys (never a silently defaulted verdict).
    """
    from little_loops.fsm.schema import DEFAULT_LLM_MODEL

    if config is None:
        from little_loops.config import BRConfig as _BRConfig

        config = _BRConfig(Path.cwd())

    advisor_host = config.advisor.host
    advisor_model = config.advisor.model

    if not advisor_host:
        raise AdvisorNotConfigured(
            "advisor host not configured — set advisor.host in .ll/ll-config.json or pass --host"
        )

    resolved_main_host = main_host or resolve_host().name
    resolved_main_model = main_model or DEFAULT_LLM_MODEL

    floor = check_floor(advisor_host, advisor_model, resolved_main_host, resolved_main_model)
    if floor.status == "violation":
        raise CapabilityFloorViolation(floor)
    if floor.status in ("advisory", "unknown"):
        print(f"advisor: {floor.status} — {floor.detail}", file=sys.stderr)

    runner = resolve_host_named(advisor_host)
    prompt = f"{question}\n\nContext:\n{context}" if context else question
    invocation = runner.build_blocking_json(
        prompt=prompt, model=advisor_model, json_schema=_VERDICT_SCHEMA
    )
    result = run_blocking_json(invocation, timeout=config.advisor.timeout_seconds)

    if result is None or not _VERDICT_KEYS.issubset(result.keys()):
        got_keys = sorted((result or {}).keys())
        raise BlockingJsonError(
            f"advisor response missing expected verdict keys ({sorted(_VERDICT_KEYS)}): "
            f"got {got_keys}",
            {"error": "advisor response missing expected verdict keys", "shape_mismatch": True},
        )

    return AdvisorVerdict(
        recommendation=str(result["recommendation"]),
        risks=[str(r) for r in result["risks"]],
        confidence=float(result["confidence"]),
        dissent=str(result["dissent"]),
        signal=signal,
        host=advisor_host,
        model=advisor_model,
    )


@dataclass(frozen=True)
class TaskKey:
    """Stable identity for the unit of work a consult is scoped to (FEAT-3116).

    Precedence tiers, resolved by `resolve_task_key()`: issue ID (running
    under ll-auto/ll-sprint/ll-parallel) -> loop run ID (ll-loop) -> session
    ID (otherwise).
    """

    kind: Literal["issue", "loop_run", "session"]
    value: str


@dataclass(frozen=True)
class ConsultBudget:
    """A task's consult allowance and current spend."""

    max_per_task: int
    spent: int
    task_key: TaskKey


@dataclass(frozen=True)
class ConsultOutcome:
    """Result of `consult_for_trigger()` — never a bare `None`.

    Exactly one of `verdict`/`skipped_reason` is set. `skipped_reason`'s
    vocabulary maps 1:1 onto FEAT-3300's `AdvisorConsultRow.outcome` enum.
    """

    task_key: TaskKey
    verdict: AdvisorVerdict | None = None
    skipped_reason: (
        Literal[
            "disabled",
            "trigger_not_allowed",
            "budget_exhausted",
            "not_configured",
            "floor_violation",
            "failed",
            "timeout",
        ]
        | None
    ) = None
    error: str | None = None


def resolve_task_key(env: dict[str, str] | None = None) -> TaskKey:
    """Resolve the current `TaskKey` from environment, mirroring `resolve_host()`.

    Pure env lookup — never calls `_resolve_issue_id()` or reads orchestrator
    state directly; those values only reach this resolver via the env
    contract orchestrators export at their spawn sites (`LL_ISSUE_ID`,
    `LL_LOOP_RUN_ID`).

    Tiers, in order:
        1. `LL_ISSUE_ID` — set by ll-auto, ll-sprint, ll-parallel.
        2. `LL_LOOP_RUN_ID` — set by ll-loop.
        3. Session ID — `CLAUDE_SESSION_ID` from *env* first, then
           `session_log.get_current_session_id()` (best-effort, the most
           recently modified session JSONL — nondeterministic when multiple
           sessions run concurrently against the same project).
    """
    if env is None:
        env = dict(os.environ)

    issue_id = env.get("LL_ISSUE_ID")
    if issue_id:
        return TaskKey(kind="issue", value=issue_id)

    loop_run_id = env.get("LL_LOOP_RUN_ID")
    if loop_run_id:
        return TaskKey(kind="loop_run", value=loop_run_id)

    session_id = env.get("CLAUDE_SESSION_ID")
    if not session_id:
        from little_loops.session_log import get_current_session_id

        session_id = get_current_session_id()

    return TaskKey(kind="session", value=session_id or "unknown")


def _budget_path(task_key: TaskKey) -> Path:
    return Path.cwd() / ".ll" / "advisor-budget" / f"{task_key.kind}-{task_key.value}.json"


def record_consult(task_key: TaskKey) -> int:
    """Persist and increment the consult counter for *task_key*; return the new count.

    One JSON file per key at `.ll/advisor-budget/<kind>-<value>.json`,
    read-modify-write under `acquire_lock()` + `atomic_write_json()` — safe
    across the subprocess boundary a consult from a child runner crosses.
    """
    path = _budget_path(task_key)
    with acquire_lock(path.with_suffix(".lock")):
        spent = 0
        if path.exists():
            try:
                spent = int(json.loads(path.read_text()).get("spent", 0))
            except (OSError, ValueError, json.JSONDecodeError):
                spent = 0
        spent += 1
        atomic_write_json(path, {"spent": spent})
    return spent


def _current_spent(task_key: TaskKey) -> int:
    path = _budget_path(task_key)
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text()).get("spent", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def should_consult(
    trigger: str,
    config: BRConfig,
    *,
    task_key: TaskKey | None = None,
    manual: bool = False,
) -> bool:
    """Gate predicate deciding whether a consult for *trigger* may proceed.

    Fail-soft, mirroring `hooks/__init__.py:_hooks_telemetry_enabled()`: any
    config-read failure is treated as "do not consult" rather than raised.
    `manual=True` (the `ll-advise` path) bypasses the `advisor.enabled`
    master switch and the `advisor.triggers` allowlist — an explicit
    user-requested consult is not an auto-consult — but the budget check
    always applies.
    """
    try:
        if not manual:
            if not config.advisor.enabled:
                return False
            if trigger not in config.advisor.triggers:
                return False

        if task_key is None:
            task_key = resolve_task_key()

        spent = _current_spent(task_key)
        if spent >= config.advisor.max_consults_per_task:
            logger.warning(
                "advisor: budget exhausted for task %s/%s (%d/%d consults spent)",
                task_key.kind,
                task_key.value,
                spent,
                config.advisor.max_consults_per_task,
            )
            return False
    except Exception:
        logger.warning("advisor: should_consult failed, defaulting to no-consult", exc_info=True)
        return False

    return True


def _task_key_str(task_key: TaskKey) -> str:
    return f"{task_key.kind}:{task_key.value}"


def _write_consult_telemetry(
    *,
    task_key: TaskKey,
    signal: str,
    config: BRConfig,
    outcome: str,
    floor_status: str | None = None,
    latency_ms: int | None = None,
    verdict: AdvisorVerdict | None = None,
) -> None:
    """Best-effort write of one `advisor_consults` row (FEAT-3300).

    Never raises into the caller — `write_advisor_consult` is itself
    fail-soft against `sqlite3.Error`, and this wrapper additionally
    suppresses any other exception (e.g. db-path resolution) so a
    telemetry failure can never alter `consult_for_trigger`'s return value.
    """
    with suppress(Exception):
        from little_loops.session_store import DEFAULT_DB_PATH, write_advisor_consult

        verdict_body = None
        if verdict is not None and config.advisor.store_verdict_body:
            verdict_body = verdict.recommendation

        write_advisor_consult(
            DEFAULT_DB_PATH,
            session_id=os.environ.get("CLAUDE_SESSION_ID"),
            task_key=_task_key_str(task_key),
            signal=signal,
            advisor_host=config.advisor.host,
            advisor_model=config.advisor.model,
            main_model=None,
            outcome=outcome,
            floor_status=floor_status,
            latency_ms=latency_ms,
            confidence=verdict.confidence if verdict is not None else None,
            verdict_body=verdict_body,
        )


def consult_for_trigger(
    trigger: str,
    *,
    question: str,
    context: str = "",
    config: BRConfig | None = None,
    main_host: str | None = None,
    main_model: str | None = None,
    manual: bool = False,
) -> ConsultOutcome:
    """The single caller of `consult()` — no other call site may call it (AC #5).

    Resolves the task key once, spends budget *before* the host call
    (reserve-before-consult: a timed-out or failed consult still spends
    budget, bounding retries of a hung advisor), then calls `consult()`.
    Never raises — `AdvisorNotConfigured`, `CapabilityFloorViolation`,
    `HostNotConfigured`, and `BlockingJsonError` each map to a
    `skipped_reason` with `error=str(exc)`, logged at warning level.

    Writes exactly one `advisor_consults` telemetry row per invocation
    (FEAT-3300) — issued, every `skipped_reason`, failed, or timeout. The
    write is fail-soft and never affects the returned `ConsultOutcome`.
    """
    if config is None:
        from little_loops.config import BRConfig as _BRConfig

        config = _BRConfig(Path.cwd())

    task_key = resolve_task_key()

    if not should_consult(trigger, config, task_key=task_key, manual=manual):
        if not manual and not config.advisor.enabled:
            reason: Literal["disabled", "trigger_not_allowed", "budget_exhausted"] = "disabled"
        elif not manual and trigger not in config.advisor.triggers:
            reason = "trigger_not_allowed"
        else:
            reason = "budget_exhausted"
        _write_consult_telemetry(task_key=task_key, signal=trigger, config=config, outcome=reason)
        return ConsultOutcome(task_key=task_key, skipped_reason=reason)

    record_consult(task_key)

    start = time.monotonic()
    try:
        verdict = consult(
            question=question,
            signal=trigger,
            context=context,
            config=config,
            main_host=main_host,
            main_model=main_model,
        )
    except AdvisorNotConfigured as exc:
        logger.warning("advisor: consult skipped, not configured: %s", exc)
        not_configured_reason: Literal["not_configured"] = "not_configured"
        _write_consult_telemetry(
            task_key=task_key, signal=trigger, config=config, outcome=not_configured_reason
        )
        return ConsultOutcome(
            task_key=task_key, skipped_reason=not_configured_reason, error=str(exc)
        )
    except CapabilityFloorViolation as exc:
        logger.warning("advisor: consult skipped, floor violation: %s", exc)
        floor_violation_reason: Literal["floor_violation"] = "floor_violation"
        _write_consult_telemetry(
            task_key=task_key,
            signal=trigger,
            config=config,
            outcome=floor_violation_reason,
            floor_status=exc.floor.status,
        )
        return ConsultOutcome(
            task_key=task_key, skipped_reason=floor_violation_reason, error=str(exc)
        )
    except HostNotConfigured as exc:
        logger.warning("advisor: consult failed, host not configured: %s", exc)
        host_not_configured_reason: Literal["failed"] = "failed"
        _write_consult_telemetry(
            task_key=task_key, signal=trigger, config=config, outcome=host_not_configured_reason
        )
        return ConsultOutcome(
            task_key=task_key, skipped_reason=host_not_configured_reason, error=str(exc)
        )
    except BlockingJsonError as exc:
        skipped_reason: Literal["timeout", "failed"] = (
            "timeout" if exc.details.get("timeout") else "failed"
        )
        logger.warning("advisor: consult %s: %s", skipped_reason, exc)
        _write_consult_telemetry(
            task_key=task_key, signal=trigger, config=config, outcome=skipped_reason
        )
        return ConsultOutcome(task_key=task_key, skipped_reason=skipped_reason, error=str(exc))

    latency_ms = int((time.monotonic() - start) * 1000)
    _write_consult_telemetry(
        task_key=task_key,
        signal=trigger,
        config=config,
        outcome="issued",
        latency_ms=latency_ms,
        verdict=verdict,
    )
    return ConsultOutcome(task_key=task_key, verdict=verdict)
