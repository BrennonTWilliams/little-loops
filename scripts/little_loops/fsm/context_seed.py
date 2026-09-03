"""FSM context-seeding leaves — self-contained, no cli/ dependency.

Relocated from ``cli/loop/_helpers.py`` (ENH-2776) so ``fsm/executor.py``'s
child-loop context-resolution path (BUG-2767/BUG-2832) can seed its own
confidence-gate thresholds and input hash without a core -> cli import.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def seed_confidence_thresholds(context: dict[str, Any], config: Any = None) -> None:
    """Seed ``readiness_threshold`` / ``outcome_threshold`` from ll-config (BUG-2767).

    Resolves ``commands.confidence_gate.readiness_threshold`` and
    ``.outcome_threshold`` into the FSM context so loops that gate on
    ``${context.readiness_threshold}`` honor project configuration instead of a
    hardcoded literal. Keys already present win, which gives the precedence
    chain: ``--context`` override > loop YAML ``context:`` literal >
    ``commands.confidence_gate.*`` > ``ConfidenceGateConfig`` defaults (85/65).

    Args:
        context: The FSM context dict, mutated in place.
        config: An optional pre-built ``BRConfig``; loaded from the cwd if omitted.
    """
    if "readiness_threshold" in context and "outcome_threshold" in context:
        return

    if config is None:
        from little_loops.config import BRConfig

        config = BRConfig(Path.cwd())

    gate = config.commands.confidence_gate
    if "readiness_threshold" not in context:
        context["readiness_threshold"] = gate.readiness_threshold
    if "outcome_threshold" not in context:
        context["outcome_threshold"] = gate.outcome_threshold


def inject_design_context(context: dict[str, Any], config: BRConfig | None = None) -> None:
    """Inject ``design_tokens_context``/``design_guidance_context``, honoring the
    ``use_design_tokens`` opt-out (BUG-3266).

    A loop can set ``context.use_design_tokens=false`` (YAML boolean or
    ``--context use_design_tokens=false`` string) to skip token injection
    entirely. Defaults to True for backward compatibility with all existing
    loops. Shared by ``cmd_run`` and ``cmd_resume`` so the gate cannot diverge
    between the two entry points again.

    Args:
        context: The FSM context dict, mutated in place.
        config: An optional pre-built ``BRConfig``; loaded from the cwd if omitted.
    """
    if config is None:
        from little_loops.config import BRConfig

        config = BRConfig(Path.cwd())

    from little_loops.design_tokens import load_design_tokens, render_as_prompt_context

    _use_tokens = context.get("use_design_tokens", True)
    if isinstance(_use_tokens, str):
        _use_tokens = _use_tokens.strip().lower() not in ("", "0", "false", "no", "off")
    if _use_tokens and not context.get("design_tokens_context"):
        _tokens = load_design_tokens(config)
        context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""
        context["design_guidance_context"] = _tokens.guidance if _tokens else ""
    else:
        # Ensure the keys exist ("" when excluded) so `${context.design_tokens_context}`
        # / `${context.design_guidance_context}` interpolate without error in prompts
        # that reference them.
        context.setdefault("design_tokens_context", "")
        context.setdefault("design_guidance_context", "")


def derive_input_hash(context: dict[str, Any]) -> None:
    """Seed ``input_hash`` from ``context["input"]`` (BUG-2832).

    Derives a stable 12-char sha256 prefix of the string ``input`` context
    value so states that interpolate ``${context.input_hash}`` (e.g.
    ``resume_check``) work whether the loop was launched by the CLI, resumed,
    simulated, or spawned as a sub-loop child. An explicit ``input_hash``
    already bound (``--context input_hash=...``, ``with:``, or a loop's own
    ``context:`` literal) always wins.

    Args:
        context: The FSM context dict, mutated in place.
    """
    if "input_hash" not in context and isinstance(context.get("input"), str):
        context["input_hash"] = hashlib.sha256(context["input"].encode()).hexdigest()[:12]
