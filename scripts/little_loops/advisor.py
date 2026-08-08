"""Capability-rank comparison for the advisor consult path.

Source: FEAT-3108. `MODEL_RANKS` is a self-declared ordinal within each
host, not derived from a benchmark — for `claude-code` it follows the
conventional tier naming (haiku < sonnet < opus), with `fable` placed as
the top flagship tier. Every other host key carries an empty rank table
until a follow-up issue gives it real capability data; `rank_model` returns
`None` for any model on those hosts, and `check_floor` classifies that as
`unknown` rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from little_loops.host_runner import resolve_model_alias

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
