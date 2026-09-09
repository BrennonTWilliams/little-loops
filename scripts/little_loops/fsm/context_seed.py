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
    from little_loops.fsm.schema import ParameterSpec


def seed_parameter_defaults(context: dict[str, Any], parameters: dict[str, "ParameterSpec"]) -> None:
    """Seed ``parameters.<name>.default`` into context for unbound optional parameters (BUG-3425).

    Historically only the sub-loop ``with:`` binding branch in ``executor.py``
    applied ``ParameterSpec.default``; every other context-construction path
    (standalone ``ll-loop run``/``resume``/``simulate``, and the
    ``context_passthrough`` sub-loop branch) ignored ``fsm.parameters``
    entirely. This is the shared leaf all of those paths call so a
    ``parameters:`` declaration works the same way everywhere.

    Uses ``setdefault`` so anything already present (persisted resume context,
    ``with:`` bindings, passthrough, a loop's own ``context:`` literal, or an
    earlier ``--context``/positional/program.md seed) wins over the default.
    ``required: true`` parameters and parameters with ``default: null`` (i.e.
    ``spec.default is None``) are skipped — an explicit ``default: ""`` is
    seeded.

    Args:
        context: The FSM context dict, mutated in place.
        parameters: ``fsm.parameters`` (or ``child_fsm.parameters``).
    """
    for name, spec in parameters.items():
        if spec.required or spec.default is None:
            continue
        context.setdefault(name, spec.default)


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


def apply_context_overrides(context: dict[str, Any], overrides: list[str]) -> None:
    """Apply ``--context KEY=VALUE`` CLI overrides, coerced to declared types.

    ``argparse`` hands every value in as a string, but the key being replaced
    usually says what the value *is*: a YAML ``flag: true`` literal (or a
    ``{type: boolean}`` FEAT-1311 declaration, or a JSON-positional unpack
    that already wrote a real ``bool``) makes ``--context flag=false`` mean
    ``False`` — the raw string ``"false"`` is truthy everywhere the context
    is consumed (Jinja tests, Python routing), so an uncoerced override could
    never turn a default-``true`` flag off. Number-ish keys parse to real
    numbers for the same reason. Coercion only happens when the current
    value's shape (``bool``/``int``/``float`` instance, or a ``type:``-keyed
    dict) declares the intent; everything else — undeclared keys, plain
    string fields, failed parses — stays the raw string, preserving the
    historical behavior for existing invocations.

    Shared by ``cli/loop/run.py`` and ``cli/loop/lifecycle.py`` (resume) so
    the two ``--context`` paths cannot diverge.

    Args:
        context: The FSM context dict, mutated in place.
        overrides: Raw ``KEY=VALUE`` argv entries (``args.context``).

    Raises:
        SystemExit: On a malformed entry without ``=`` (CLI usage error).
    """
    for kv in overrides:
        if "=" not in kv:
            raise SystemExit(f"Invalid --context format: {kv!r} (expected KEY=VALUE)")
        key, _, value = kv.partition("=")
        context[key.strip()] = _coerce_override(context.get(key.strip()), value.strip())


def _coerce_override(current: Any, value: str) -> Any:
    """Coerce one ``--context`` string to the type its key already carries."""
    if isinstance(current, bool):
        lowered = value.lower()
        return lowered == "true" if lowered in ("true", "false") else value
    if isinstance(current, int):
        try:
            return int(value)
        except ValueError:
            return value
    if isinstance(current, float):
        try:
            return float(value)
        except ValueError:
            return value
    declared = current if isinstance(current, dict) else None
    decl_type = (declared or {}).get("type")
    if decl_type == "boolean":
        lowered = value.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
    elif decl_type in ("number", "integer"):
        try:
            return int(value) if decl_type == "integer" else float(value)
        except ValueError:
            return value
    return value
