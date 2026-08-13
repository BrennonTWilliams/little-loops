"""Evaluator/pairing rule family (MR-8 evidence-contract, MR-10 parse-swallow,
MR-12 pruning-profile consistency, MR-13 terminal-action/abandonment-verdict,
plus session-mode-eval and haiku-gen): rules about how a state's evaluator or
verdict-judging configuration is paired with the rest of the loop.
"""

from __future__ import annotations

import re

from little_loops.fsm.schema import FSMLoop, PruningProfileConfig, StateConfig
from little_loops.fsm.validation._base import (
    _SKILL_INVOKE_RE,
    ValidationError,
    ValidationSeverity,
    _effective_session_mode,
    _is_llm_judged,
)

# MR-10: parse-swallow detector. Flags shell states that call json.loads/json.load,
# catch JSONDecodeError/ValueError/Exception, and explicitly exit 0 — without an
# on_error: route. Shifts the BUG-2383 silent-swallow class left into the validator.
_JSON_PARSE_CALL_RE = re.compile(r"\bjson\.loads?\s*\(")

_PARSE_EXCEPT_CATCHING_RE = re.compile(
    r"\bexcept\s+(?:\(\s*)?(?:(?:json\.)?JSONDecodeError|ValueError|Exception)\b"
)

_ZERO_EXIT_RE = re.compile(r"\b(?:sys\.exit|exit)\s*\(\s*0\s*\)")


def _validate_terminal_action_ok(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule BUG-2813: non-empty ``action`` on a ``terminal: true`` state.

    The executor returns ``_finish("terminal")`` the instant a terminal state is
    entered — before that state's own ``action:`` (if any) ever runs. Any inline
    action on a plain terminal is therefore dead code. The fix is to move the
    action into a new penultimate non-terminal state with ``next: <terminal>``
    and an ``on_error:`` route, leaving the terminal bare (the
    ``rn-implement::report`` shape).

    Exemption: a terminal state named as the loop's ``on_max_steps`` or
    ``on_max_iterations`` handler IS reachable with its action executed (BUG-158
    fallthrough in the executor), so it is not dead code and is skipped.

    Suppressed by ``terminal_action_ok: true`` at the loop top-level.
    """
    if fsm.terminal_action_ok:
        return []

    exempt_terminal_names: set[str] = {
        name for name in (fsm.on_max_steps, fsm.on_max_iterations) if name is not None
    }

    errors: list[ValidationError] = []
    terminal_states = fsm.get_terminal_states()
    for state_name in terminal_states:
        if state_name in exempt_terminal_names:
            continue
        state = fsm.states[state_name]
        if state.action:
            errors.append(
                ValidationError(
                    message=(
                        f"Terminal state '{state_name}' has a non-empty 'action', which "
                        "never executes: the executor finishes the run the instant a "
                        "terminal: true state is entered, before its action would run. "
                        "Move the action into a new penultimate non-terminal state with "
                        f"'next: {state_name}' and an 'on_error:' route (see "
                        "rn-implement::report), leaving the terminal bare. Set "
                        "`terminal_action_ok: true` to suppress. (BUG-2813)"
                    ),
                    path=f"states.{state_name}.action",
                    severity=ValidationSeverity.WARNING,
                )
            )
    return errors


def _validate_parse_swallow(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-10: shell state silently swallows a JSON parse failure with exit 0.

    Flags any shell state whose inline Python calls ``json.loads``/``json.load``,
    catches ``JSONDecodeError``, ``ValueError``, or bare ``Exception``, and explicitly
    exits 0 (``sys.exit(0)`` or ``exit(0)``) — without an ``on_error:`` route on the
    state. When all three hold the FSM receives exit 0 on a parse failure and treats the
    state as successful, producing zero results with no log, no stderr, and no non-zero
    exit code (as observed in BUG-2383 across three loops).

    Suppressed by ``parse_swallow_ok: true`` at the loop top-level for the rare case
    where treating a parse failure as an empty result is intentional.
    """
    if fsm.parse_swallow_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        if state.action_type not in ("shell", None):
            continue
        if state.action.lstrip().startswith("/"):
            continue
        if state.on_error is not None:
            continue
        action = state.action
        if not _JSON_PARSE_CALL_RE.search(action):
            continue
        if not _PARSE_EXCEPT_CATCHING_RE.search(action):
            continue
        if not _ZERO_EXIT_RE.search(action):
            continue
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] shell action calls json.loads/json.load, "
                    "catches JSONDecodeError/ValueError/Exception, and exits 0 without "
                    "an on_error: route. Parse failures are silently discarded; the FSM "
                    "sees exit 0 and treats the state as successful (BUG-2383 pattern). "
                    "Add on_error: to route parse failures, or set parse_swallow_ok: true "
                    "to suppress. (MR-10)"
                ),
                path=f"states.{state_name}.action",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


# MR-13 (ENH-2860): abandonment-mechanism heuristics — a shell action that
# rewrites a checkbox line to the `[!]` abandonment marker, or rewrites a
# checkbox to `[x]` alongside an "abandoned" annotation (the pre-ENH-2857
# laundering shape), or consumes a `max_step_attempts`-style attempt-cap
# context var.
_ABANDON_BANG_MARKER_RE = re.compile(r"-\s*\\?\[!\\?\]")

_ABANDON_CHECKED_ANNOTATION_RE = re.compile(r"\\?\[x\\?\].{0,80}abandon", re.IGNORECASE | re.DOTALL)

_ABANDON_ATTEMPT_CAP_RE = re.compile(r"max_step_attempts")

# Any reference to an abandonment counter/branch in the same action — used
# both to detect the mechanism and as the "has a guard" escape hatch for the
# hardcoded-verdict check below.
_ABANDON_COUNTER_REF_RE = re.compile(r"abandon", re.IGNORECASE)

# A literal "abandoned" key emitted into a JSON summary via printf/write.
_ABANDONED_KEY_EMIT_RE = re.compile(r'"abandoned"\s*:')

# A hardcoded (non-interpolated) success verdict — JSON-literal or shell-var
# assignment form.
_HARDCODE_VERDICT_SUCCESS_RE = re.compile(
    r'"verdict"\s*:\s*"success"|\bverdict\s*=\s*success\b', re.IGNORECASE
)


def _validate_abandonment_verdict(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-13 (ENH-2860): abandonment must reach summary.json and downgrade the verdict.

    Two independent conditions share this one suppress flag:

    1. The loop has an abandonment mechanism — a shell action rewriting a
       checkbox line to the ``[!]`` marker, rewriting to ``[x]`` with an
       "abandoned" annotation, or consuming a ``max_step_attempts``-style
       attempt-cap context var — but NO state's action emits an
       ``"abandoned"`` key into a summary JSON printf/write. Abandoned work
       is tracked internally but never reaches the artifact audit tooling
       reads (the pre-ENH-2857 general-task defect: 8-of-34 abandoned steps
       laundered into a bare "success").
    2. A shell action contains a literal, non-interpolated
       ``"verdict":"success"`` (or ``verdict=success``) with no conditional
       branch referencing an abandonment/failure counter and no
       ``"abandoned"`` key emitted in that same state. A guarded literal
       (branches on an abandoned-count check, or emits the "abandoned" key
       alongside it) is the correct shape and is not flagged — this is what
       distinguishes the fix (ENH-2657/ENH-2857) from the defect.

    Suppressed by ``abandonment_verdict_ok: true`` at the loop top-level.
    """
    if fsm.abandonment_verdict_ok:
        return []
    errors: list[ValidationError] = []

    mechanism_state: str | None = None
    any_state_emits_abandoned_key = False
    for state_name, state in fsm.states.items():
        action = state.action or ""
        if not action:
            continue
        if mechanism_state is None and (
            _ABANDON_BANG_MARKER_RE.search(action)
            or _ABANDON_CHECKED_ANNOTATION_RE.search(action)
            or _ABANDON_ATTEMPT_CAP_RE.search(action)
        ):
            mechanism_state = state_name
        if _ABANDONED_KEY_EMIT_RE.search(action):
            any_state_emits_abandoned_key = True

    if mechanism_state is not None and not any_state_emits_abandoned_key:
        errors.append(
            ValidationError(
                message=(
                    f"[state: {mechanism_state}] loop has an abandonment mechanism "
                    "(checkbox rewrite to [!] / abandoned annotation, or a "
                    "max_step_attempts-style attempt cap) but no state emits an "
                    '"abandoned" key into a summary JSON printf/write — abandoned '
                    "work is invisible to audit tooling (general-task pre-ENH-2857 "
                    'pattern). Emit an "abandoned" key from the summary-writing '
                    "state, or set `abandonment_verdict_ok: true` to suppress. "
                    "(MR-13)"
                ),
                path=f"states.{mechanism_state}.action",
                severity=ValidationSeverity.WARNING,
            )
        )

    for state_name, state in fsm.states.items():
        action = state.action or ""
        if not action:
            continue
        if not _HARDCODE_VERDICT_SUCCESS_RE.search(action):
            continue
        if _ABANDON_COUNTER_REF_RE.search(action):
            continue
        if _ABANDONED_KEY_EMIT_RE.search(action):
            continue
        errors.append(
            ValidationError(
                message=(
                    f'[state: {state_name}] shell action hardcodes "verdict":'
                    '"success" (or verdict=success) with no conditional branch on '
                    'an abandonment/failure counter and no "abandoned" key emitted '
                    "in the same state — any abandoned work is silently laundered "
                    "into a clean success verdict. Guard the verdict on an "
                    'abandonment counter and emit an "abandoned" key, or set '
                    "`abandonment_verdict_ok: true` to suppress. (MR-13)"
                ),
                path=f"states.{state_name}.action",
                severity=ValidationSeverity.WARNING,
            )
        )

    return errors


def _effective_pruning_profile(fsm: FSMLoop, state: StateConfig) -> PruningProfileConfig | None:
    """Resolve the effective pruning profile for a state: state override, then loop default."""
    if state.pruning_profile is not None:
        return state.pruning_profile
    return fsm.pruning_profile


def _validate_pruning_profile(
    fsm: FSMLoop, orchestration_request_path: str | None = None
) -> list[ValidationError]:
    """Validate rule MR-12 (ENH-2714 / ENH-2805): automation-context pruning-profile consistency.

    Three checks against the resolved pruning profile (state ``pruning_profile:``
    override, else the loop-level default):

    1. ERROR — a state's own ``tools:`` allowlist excludes a ``/ll:<skill>``
       it actually invokes via ``action:``. The state would fail at runtime
       because its own narrowing flags block its own action.
    2. WARN — a state runs under a profile with ``suppress_catalog: true`` and
       invokes a ``/ll:<skill>`` action. Catalog suppression removes the skill
       listing the host needs to resolve the slash command, so the invocation
       may fail depending on host behavior.
    3. WARN (ENH-2805, narrowed by BUG-2831) — a skill/command-invoking state
       has NO resolvable ``pruning_profile`` at all (neither state override
       nor loop default). Every such state pays the SessionStart digest on
       every invocation. (The catalog and CLAUDE.md are also re-sent, but a
       profile does NOT currently prune them — ``suppress_catalog`` and
       ``suppress_claude_md`` are declarative-only with no runtime consumer,
       so the realized saving from a profile is the hook output alone,
       ~1K tokens.) Static-prefix cost overall is the dominant share of
       fleet token spend
       (session-level traffic, not the FSM-state-tagged ~1% `request_path:
       sdk` touches). ``request_path: sdk``/``batch`` states used to be
       exempt on the theory that they bypass ``action_runner`` entirely via
       ``_dispatch_live`` and send a bare single-turn API call with no
       catalog/CLAUDE.md/hooks to prune — but BUG-2831 found that theory
       false for *this* branch of the function: every state reaching this
       point already matched ``_SKILL_INVOKE_RE`` above, and
       ``FSMExecutor._resolve_request_path()`` now force-downgrades any
       skill-invoking sdk/batch state to ``cli`` at runtime (a bare
       tool-less SDK call can't run a `/ll:` skill). A skill-invoking state
       genuinely does reach ``action_runner`` and does need pruning, so the
       exemption no longer applies here — the check fires regardless of
       ``request_path``. (Non-skill-invoking sdk/batch states never enter
       this loop body in the first place, since they're filtered out by the
       ``/`` + skill-regex guard above; their exemption from pruning
       guidance was never conditional on this check.)

    Suppressed by ``pruning_profile_ok: true`` at the loop top-level (all
    three checks share this flag rather than minting a per-check flag).
    """
    if fsm.pruning_profile_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not state.action or not state.action.lstrip().startswith("/"):
            continue
        match = _SKILL_INVOKE_RE.search(state.action)
        if match is None:
            continue
        skill = match.group(1)

        # Check 1 (ERROR): state's own tools: allowlist excludes its own skill.
        if state.tools is not None and skill not in state.tools:
            errors.append(
                ValidationError(
                    message=(
                        f"[state: {state_name}] action invokes /ll:{skill} but the "
                        f"state's own tools: allowlist {state.tools!r} excludes it — "
                        "the state would fail to resolve its own action at runtime. "
                        "Add the skill to tools:, or set `pruning_profile_ok: true` "
                        "at the loop top-level to suppress. (ENH-2714 MR-12)"
                    ),
                    path=f"states.{state_name}.tools",
                    severity=ValidationSeverity.ERROR,
                )
            )

        # Check 2 (WARN): catalog-suppressed profile but state invokes a skill.
        profile = _effective_pruning_profile(fsm, state)
        if profile is not None and profile.enabled and profile.suppress_catalog:
            errors.append(
                ValidationError(
                    message=(
                        f"[state: {state_name}] runs under a pruning profile with "
                        "suppress_catalog: true and invokes /ll:"
                        f"{skill} — catalog suppression removes the skill listing "
                        "the host needs to resolve slash commands. Verify the host "
                        "still resolves this skill, or set `pruning_profile_ok: true` "
                        "at the loop top-level to suppress. (ENH-2714 MR-12)"
                    ),
                    path=f"states.{state_name}.action",
                    severity=ValidationSeverity.WARNING,
                )
            )

        # Check 3 (WARN, ENH-2805): no resolvable pruning_profile at all.
        # BUG-2831: no sdk/batch exemption here — every state reaching this
        # point already invokes a /ll: skill, and the executor now
        # force-downgrades skill-invoking sdk/batch states to cli at
        # runtime, so they genuinely go through action_runner and need
        # pruning guidance same as any other skill-invoking state.
        if profile is None:
            errors.append(
                ValidationError(
                    message=(
                        f"[state: {state_name}] invokes /ll:{skill} with no "
                        "resolvable pruning_profile (state override or loop "
                        "default) — this state pays the SessionStart digest "
                        "on every invocation (~1K tokens). Consider setting a "
                        "`pruning_profile:` for high-volume repeated states, or "
                        "set `pruning_profile_ok: true` at the loop top-level "
                        "to suppress. Note: the catalog and CLAUDE.md are NOT "
                        "prunable today — suppress_catalog/suppress_claude_md "
                        "are declarative-only, so a profile saves only the hook "
                        "output. (ENH-2805 MR-12)"
                    ),
                    path=f"states.{state_name}.pruning_profile",
                    severity=ValidationSeverity.WARNING,
                )
            )
    return errors


_TAMPER_GUARD_VALUES: frozenset[str] = frozenset({"revert", "fail", "allow"})


def _effective_tamper_guard(fsm: FSMLoop, state: StateConfig) -> str | None:
    """Resolve the effective tamper_guard policy for a state: state override, then loop default."""
    if state.tamper_guard is not None:
        return state.tamper_guard
    return fsm.tamper_guard


def _validate_tamper_guard(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule (ENH-2934): unrecognized ``tamper_guard`` values.

    ``StateConfig.tamper_guard``/``FSMLoop.tamper_guard`` accept any string at
    the dataclass layer (like ``session_mode``) with no built-in enum
    rejection. This WARNs on a value outside ``{"revert", "fail", "allow"}``.

    Checks the loop-level default (if set) once, plus each state's own
    override (if set) — not every state's *inherited* value, which would
    duplicate one bad loop-level default across every state that doesn't
    override it.

    Suppressed by ``tamper_guard_ok: true`` at the loop top-level.
    """
    if fsm.tamper_guard_ok:
        return []
    errors: list[ValidationError] = []
    if fsm.tamper_guard is not None and fsm.tamper_guard not in _TAMPER_GUARD_VALUES:
        errors.append(
            ValidationError(
                message=(
                    f"loop-level tamper_guard: {fsm.tamper_guard!r} is not one of "
                    f"{sorted(_TAMPER_GUARD_VALUES)!r}. Set a valid value, or "
                    "`tamper_guard_ok: true` at the loop top-level to suppress. (ENH-2934)"
                ),
                path="tamper_guard",
                severity=ValidationSeverity.WARNING,
            )
        )
    for state_name, state in fsm.states.items():
        if state.tamper_guard is None or state.tamper_guard in _TAMPER_GUARD_VALUES:
            continue
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] tamper_guard: {state.tamper_guard!r} is not "
                    f"one of {sorted(_TAMPER_GUARD_VALUES)!r}. Set a valid value, or "
                    "`tamper_guard_ok: true` at the loop top-level to suppress. (ENH-2934)"
                ),
                path=f"states.{state_name}.tamper_guard",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


_PREPATCH_CHECK_VALUES: frozenset[str] = frozenset({"fail", "warn", "allow"})


def _effective_prepatch_check(fsm: FSMLoop, state: StateConfig) -> str | None:
    """Resolve the effective prepatch_check policy for a state: state override, then loop default."""
    if state.prepatch_check is not None:
        return state.prepatch_check
    return fsm.prepatch_check


def _validate_prepatch_check(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule (ENH-2997): unrecognized ``prepatch_check`` values.

    Mirrors ``_validate_tamper_guard``: checks the loop-level default (if
    set) once, plus each state's own override (if set) — not every state's
    *inherited* value.

    Suppressed by ``prepatch_check_ok: true`` at the loop top-level.
    """
    if fsm.prepatch_check_ok:
        return []
    errors: list[ValidationError] = []
    if fsm.prepatch_check is not None and fsm.prepatch_check not in _PREPATCH_CHECK_VALUES:
        errors.append(
            ValidationError(
                message=(
                    f"loop-level prepatch_check: {fsm.prepatch_check!r} is not one of "
                    f"{sorted(_PREPATCH_CHECK_VALUES)!r}. Set a valid value, or "
                    "`prepatch_check_ok: true` at the loop top-level to suppress. (ENH-2997)"
                ),
                path="prepatch_check",
                severity=ValidationSeverity.WARNING,
            )
        )
    for state_name, state in fsm.states.items():
        if state.prepatch_check is None or state.prepatch_check in _PREPATCH_CHECK_VALUES:
            continue
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] prepatch_check: {state.prepatch_check!r} is not "
                    f"one of {sorted(_PREPATCH_CHECK_VALUES)!r}. Set a valid value, or "
                    "`prepatch_check_ok: true` at the loop top-level to suppress. (ENH-2997)"
                ),
                path=f"states.{state_name}.prepatch_check",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


_EVIDENCE_CONTRACT_KEYWORDS: frozenset[str] = frozenset({"verbatim", "quote", "evidence"})


def _validate_llm_evidence_contract(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-8 (ENH-2342): LLM-judged state prompts should include evidence-contract keywords.

    A check_semantic/llm_structured state whose ``evaluate.prompt`` does not contain any of
    ``{"verbatim", "quote", "evidence"}`` may produce verdicts without cited output text,
    defaulting to optimism (SHOR Table 1: 33–55% accuracy; Sonnet 4.6 = 33.4%).

    States with no evaluate block (Path B: action prompt) or ``evaluate.prompt is None``
    inherit DEFAULT_LLM_PROMPT which includes CHECK_SEMANTIC_EVIDENCE_CONTRACT after ENH-2342
    and are not flagged here.

    Suppressed by ``evidence_contract_ok: true`` at the loop top-level.
    """
    if fsm.evidence_contract_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not _is_llm_judged(state):
            continue
        if state.evaluate is None:
            continue
        if state.evaluate.prompt is None:
            continue
        prompt_lower = state.evaluate.prompt.lower()
        if not any(kw in prompt_lower for kw in _EVIDENCE_CONTRACT_KEYWORDS):
            errors.append(
                ValidationError(
                    message=(
                        f"[state: {state_name}] check_semantic/llm_structured prompt "
                        "does not include evidence-contract keywords (verbatim, quote, evidence). "
                        "Verdicts without cited evidence default to optimism "
                        "(SHOR Table 1: 33–55% accuracy). Add a requirement to quote exact "
                        "output text, or set `evidence_contract_ok: true` to suppress. "
                        "(ENH-2342 MR-8)"
                    ),
                    path=f"states.{state_name}.evaluate.prompt",
                    severity=ValidationSeverity.WARNING,
                )
            )
    return errors


def _validate_haiku_pinned_generator(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule (ENH-2713): haiku-pinned generator states.

    Haiku pinning is intended for cheap, rigidly-templated verdict states
    (check_semantic/llm_structured), which MR-1 already gates with a non-LLM
    evaluator in their routing chain — a wrong verdict from a cheaper model is
    caught by that external signal. A state whose `model:` names a haiku
    variant but is NOT LLM-judged (i.e. it generates/writes artifacts rather
    than producing a verdict) has no equivalent quality backstop.

    Suppressed by ``haiku_generator_ok: true`` at the loop top-level.
    """
    if fsm.haiku_generator_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if state.model is None or "haiku" not in state.model.lower():
            continue
        if _is_llm_judged(state):
            continue
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] model: '{state.model}' pins a haiku variant "
                    "on a generator state (not an evaluator/verdict state). Haiku pinning "
                    "is intended for cheap check_semantic/llm_structured verdicts, which "
                    "MR-1 already gates with a non-LLM evaluator — generator output has no "
                    "equivalent quality backstop. Set `haiku_generator_ok: true` to suppress. "
                    "(ENH-2713)"
                ),
                path=f"states.{state_name}.model",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


def _validate_session_mode_evaluator_inheritance(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule (FEAT-2711): an evaluator state must not inherit session continuity.

    A ``check_semantic``/``llm_structured`` evaluator state that resolves to
    ``session_mode: continue`` (via its own override or the loop-level
    default) sees the prior chained state's compact-summary injected into its
    prompt. This breaks MR-1-style evaluator independence — the FSM's design
    point is that evaluator verdicts are judged fresh, not primed by a prior
    state's reasoning. Evaluator states must default to `fresh` regardless of
    the loop's continuity-chain default.

    Requires an *explicit* ``evaluate: {type: check_semantic|llm_structured}``
    block (same guard as MR-8's ``_validate_llm_evidence_contract``) rather
    than the broader ``_is_llm_judged`` heuristic — a bare prompt-mode
    generator state with unconditional ``next:`` routing and no ``evaluate:``
    block (e.g. a plain "write this file" step) is not itself graded by any
    judge and is exactly the kind of state a continuity chain targets, so it
    must not be flagged here.

    Suppressed by ``session_mode_ok: true`` at the loop top-level.
    """
    if fsm.session_mode_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if state.evaluate is None or state.evaluate.type not in (
            "llm_structured",
            "check_semantic",
        ):
            continue
        if _effective_session_mode(fsm, state) != "continue":
            continue
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] check_semantic/llm_structured evaluator "
                    "inherits session_mode: continue — the prior chained state's "
                    "compact-summary would be injected into this evaluator's prompt, "
                    "breaking MR-1-style independent judgment. Set `session_mode: "
                    "fresh` on this state, or `session_mode_ok: true` at the loop "
                    "top-level to suppress. (FEAT-2711)"
                ),
                path=f"states.{state_name}.session_mode",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


def _validate_classify_route_default(fsm: FSMLoop) -> list[ValidationError]:
    """Validate that classify states with a route: table include a default: fallback.

    A ``classify`` state whose ``route:`` table has no ``default:`` will dead-end
    whenever the action emits a token not listed in the table. This rule flags
    that gap as a WARNING so loop authors add a catch-all branch.

    Suppressed by ``partial_route_ok: true`` at the loop top-level when a
    dead-end on an unlisted token is intentional.
    """
    if fsm.partial_route_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if state.evaluate is None or state.evaluate.type != "classify":
            continue
        if state.route is None or state.route.default is not None:
            continue
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] classify route: table has no default: — "
                    "unknown tokens will dead-end the loop. Add a default: catch-all, "
                    "or set `partial_route_ok: true` at the loop top-level to suppress."
                ),
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors
