"""Reachability/dominance rule family: capture-reachability (ENH-1961/BUG-2812),
static `loop:` reference resolution, policy-table dimension scoring, and
progress-paths isolation (BUG-1767) -- rules that reason about the FSM graph's
structure rather than a single state in isolation.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path

from little_loops.fsm.loop_paths import resolve_loop_path
from little_loops.fsm.schema import FSMLoop
from little_loops.fsm.validation._base import (
    ValidationError,
    ValidationSeverity,
    _strip_interpolation_prefix,
)

# ENH-1961: Regex for extracting captured variable names from ${captured.<var>.*} references
_CAPTURED_REF_RE = re.compile(r"\$\{captured\.(\w+)")

# Full-reference form, capturing the var name and the remainder up to the closing
# brace so we can detect a `:default=` or `?` guard. A reference written as
# `${captured.x.output:default=...}` OR `${captured.x.output?}` is provably safe
# even on paths that bypass the capturing state — the interpolation engine
# (interpolation.py) substitutes the default (or "" for the `?` nullable suffix)
# when the path is missing — so it must NOT be flagged by the capture-reachability
# check. _CAPTURED_REF_RE alone can't see the guard.
_CAPTURED_REF_FULL_RE = re.compile(r"\$\{captured\.(\w+)([^}]*)\}")

# Fields exposed on the event-stream dict a sub-loop-delegating state's own
# `capture:` name resolves to (executor.py: capture stores {"output": ...,
# "exit_code": ...} for a `loop:` state, NOT the child's captures). A path
# with any other second segment (e.g. `.extracted.output`) is referencing a
# field that doesn't exist there (BUG-2812).
_SUB_LOOP_CAPTURE_OWN_FIELDS: frozenset[str] = frozenset({"output", "exit_code"})


def _unguarded_captured_refs(text: str) -> set[tuple[str, ...]]:
    """Return dotted-path tuples for `${captured...}` refs WITHOUT a
    `:default=` or `?` guard. Vars referenced only via
    `${captured.x...:default=...}` or `${captured.x...?}` (nullable) are omitted:
    both make a missing value safe (default substituted, or resolved to ""), so
    they should not trigger missing-capture or bypass-path diagnostics. This is
    the shared idiom for a state like refine-to-ready-issue's `diagnose` that is
    reachable from many failure sources, only one of whose captures is populated
    on any given run (BUG-2726).

    Each returned tuple is the full dotted path segments after `captured.`,
    e.g. `${captured.prove.targets.output}` -> `("prove", "targets", "output")`
    (BUG-2812: nested sub-loop capture paths, not just the first segment).
    """
    refs: set[tuple[str, ...]] = set()
    for var_name, remainder in _CAPTURED_REF_FULL_RE.findall(text):
        if ":default=" in remainder or remainder.endswith("?"):
            continue
        extra_segments = [seg for seg in remainder.split(".") if seg]
        refs.add((var_name, *extra_segments))
    return refs


def _validate_loop_references(fsm: FSMLoop, loop_dir: Path) -> list[ValidationError]:
    """Validate that every state's loop: reference resolves to an actual loop file.

    Called from load_and_validate (not validate_fsm) because resolving child loops
    requires file-system access via the loop directory path.

    Severity is ERROR: a reachable ``loop:`` state with an unresolvable *static*
    (non-``${...}``) target can never execute — the runtime executor calls the same
    ``resolve_loop_path`` and raises ``FileNotFoundError`` on dispatch. Originally a
    WARNING (BUG-2305) on the theory that some references are "intentionally optional",
    but that theory does not hold: dynamic names are already skipped above, and a static
    name either resolves at definition time or fails identically at runtime. Two
    multi-hour sprint runs silently burned compute because a missing ``oracles/`` prefix
    on ``refine-to-ready-issue.confidence_check`` produced only a WARNING that was then
    allowlisted away. Promoting to ERROR makes the loop fail to load (``ll-loop validate``
    exits non-zero, CI fails) instead of deferring to an opaque runtime ``on_error`` route.
    """
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if state.loop is None:
            continue
        # Skip dynamically interpolated loop names — they can only be checked at runtime
        if "${" in state.loop:
            continue
        try:
            resolve_loop_path(state.loop, loop_dir)
        except FileNotFoundError:
            errors.append(
                ValidationError(
                    message=f"Loop reference '{state.loop}' does not resolve to any file.",
                    path=f"states.{state_name}.loop",
                    severity=ValidationSeverity.ERROR,
                )
            )
    return errors


def _validate_policy_dimensions_scored(fsm: FSMLoop) -> list[ValidationError]:
    """Validate that policy_rules predicates only reference dimensions that are actually scored.

    A predicate on a dimension absent from both ``context.rubric_dimensions`` and any
    shell state's ``rubric-dim-<name>.txt`` write is silently inert at runtime —
    ``_eval_predicate`` returns ``True`` only for ``!=`` when the dimension is missing
    from the scores dict, so every other operator falls through to the catch-all.

    Referenced dimensions are kept **raw** (un-normalized); the scored set is normalized
    (lowercase + spaces→hyphens) to match the file-naming convention in
    ``lib/policy-router.yaml``.  This intentional asymmetry means a predicate whose dim
    is ``Has Citations`` is flagged as inert even if ``Has Citations`` appears in
    ``rubric_dimensions`` — because the score key written by ``policy_parse_scores`` is
    ``has-citations``, which the raw predicate dim never equals at runtime.

    The reserved ``aggregate`` pseudo-dimension is always written by ``policy_parse_scores``
    and is exempt from this check.

    Suppressed by ``policy_dims_scored_ok: true`` at the loop top-level.
    """
    if fsm.policy_dims_scored_ok:
        return []

    policy_rules_text = str(fsm.context.get("policy_rules", "")).strip()
    if not policy_rules_text:
        return []

    from little_loops.fsm.policy_rules import parse_rules

    try:
        rules = parse_rules(policy_rules_text)
    except ValueError:
        return []

    # Collect referenced dimensions raw (un-normalized); skip the reserved 'aggregate'
    _RESERVED = {"aggregate"}
    referenced: dict[str, list[str]] = {}
    for rule in rules:
        for pred in rule.predicates:
            if pred.dim in _RESERVED:
                continue
            pred_str = f"{pred.dim}:{pred.op}{pred.value}"
            referenced.setdefault(pred.dim, []).append(pred_str)

    if not referenced:
        return []

    # Build scored set: normalize rubric_dimensions (lowercase + spaces→hyphens)
    scored: set[str] = set()
    rubric_dims_raw = str(fsm.context.get("rubric_dimensions", ""))
    if rubric_dims_raw.strip():
        for name in rubric_dims_raw.split("|"):
            normalized = re.sub(r"\s+", "-", name.strip().lower())
            if normalized:
                scored.add(normalized)

    # Also collect dims written via rubric-dim-<name>.txt literals in shell state actions
    _SCORER_PATTERN = re.compile(r"rubric-dim-([\w-]+)\.txt")
    for state in fsm.states.values():
        if not state.action:
            continue
        if state.action_type not in ("shell", None):
            continue
        for m in _SCORER_PATTERN.finditer(state.action):
            scored.add(m.group(1))

    # Flag raw-referenced dimensions not present in the normalized scored set
    errors: list[ValidationError] = []
    for dim, predicates in sorted(referenced.items()):
        if dim in scored:
            continue
        pred_list = ", ".join(f"`{p}`" for p in predicates)
        errors.append(
            ValidationError(
                message=(
                    f"dimension `{dim}` is referenced in policy_rules but never scored "
                    f"(not in rubric_dimensions and no shell state writes "
                    f"rubric-dim-{dim}.txt) — predicate(s) {pred_list} are inert at "
                    "runtime and routing will fall through to the catch-all. "
                    "Set `policy_dims_scored_ok: true` to suppress."
                ),
                path="context.policy_rules",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


def _validate_progress_paths_isolation(fsm: FSMLoop) -> list[ValidationError]:
    """Warn when a state's action writes to a file listed in progress_paths (BUG-1767).

    When a loop's own bookkeeping files appear in both progress_paths and the
    state action strings, every append to those files resets the stall window,
    silently disabling the BUG-1674 stall guard for that loop. Authors should
    move such files to exclude_paths so the stall detector can still fire.
    """
    if fsm.circuit is None or fsm.circuit.repeated_failure is None:
        return []
    rf = fsm.circuit.repeated_failure
    if not rf.progress_paths:
        return []

    # Build a set of the relative path components we need to look for.
    watched = {_strip_interpolation_prefix(p) for p in rf.progress_paths}
    # Exclude paths that are already in exclude_paths — author acknowledged.
    excluded = {_strip_interpolation_prefix(p) for p in rf.exclude_paths}
    active_watched = watched - excluded
    if not active_watched:
        return []

    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        for path_fragment in active_watched:
            if path_fragment in state.action:
                errors.append(
                    ValidationError(
                        message=(
                            f"State action references '{path_fragment}', which is also "
                            "listed in circuit.repeated_failure.progress_paths. Writes "
                            "to this file will reset the stall window every cycle, "
                            "silently disabling stall detection. Move it to "
                            "circuit.repeated_failure.exclude_paths to separate "
                            "bookkeeping files from real progress signals."
                        ),
                        path=f"states.{state_name}.action",
                        severity=ValidationSeverity.WARNING,
                    )
                )
    return errors


def _dominated_by_any(fsm: FSMLoop, dominators: set[str], dominated: str) -> bool:
    """Return True if the set ``dominators`` collectively dominates ``dominated``.

    Group domination: every path from the initial state to ``dominated`` must
    pass through at least one state in ``dominators``. Checked by removing all
    dominator states from the graph and testing whether ``dominated`` is still
    reachable from the initial state.

    This generalizes single-state domination — used when a capture variable is
    produced by more than one state on mutually-exclusive branches, where the
    reference is safe as long as *some* capturing state runs on every path.

    Args:
        fsm: The FSM loop to analyze
        dominators: Names of the states that should collectively dominate
        dominated: Name of the state that should be dominated

    Returns:
        True if the dominators collectively dominate ``dominated``
    """
    if dominated in dominators:
        return True
    if dominated not in fsm.states:
        return False

    visited: set[str] = set()
    to_visit: deque[str] = deque([fsm.initial])

    while to_visit:
        current = to_visit.popleft()
        if current in visited or current not in fsm.states:
            continue
        if current in dominators:
            continue  # Block this node (simulate removal)

        visited.add(current)

        if current == dominated:
            # Reached dominated without going through any dominator
            return False

        state = fsm.states[current]
        for ref in state.get_referenced_states():
            if ref != "$current" and ref not in visited:
                to_visit.append(ref)

    # Dominated not reachable without the dominators → they dominate
    return True


def _dominates(fsm: FSMLoop, dominator: str, dominated: str) -> bool:
    """Return True if dominator dominates dominated in the FSM graph.

    A state D dominates S if every path from the initial state to S must pass
    through D. Thin single-state wrapper around :func:`_dominated_by_any`.
    """
    if dominator not in fsm.states:
        return False
    return _dominated_by_any(fsm, {dominator}, dominated)


def _find_bypass_path_any(fsm: FSMLoop, dominators: set[str], dominated: str) -> list[str]:
    """Find an example path from initial to dominated that bypasses all dominators.

    Uses BFS to find the shortest path that avoids every state in ``dominators``.
    Returns empty list if no bypass exists (should not happen when called after
    :func:`_dominated_by_any` returns False).
    """
    parent: dict[str, str] = {}
    to_visit: deque[str] = deque([fsm.initial])
    visited: set[str] = set()

    while to_visit:
        current = to_visit.popleft()
        if current in visited or current not in fsm.states:
            continue
        if current in dominators:
            continue

        visited.add(current)

        if current == dominated:
            # Reconstruct path
            path = [dominated]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            path.reverse()
            return path

        state = fsm.states[current]
        for ref in state.get_referenced_states():
            if ref != "$current" and ref not in visited:
                if ref not in parent:
                    parent[ref] = current
                to_visit.append(ref)

    return []


def _find_bypass_path(fsm: FSMLoop, dominator: str, dominated: str) -> list[str]:
    """Find an example path from initial to dominated that bypasses dominator.

    Thin single-state wrapper around :func:`_find_bypass_path_any`.
    """
    return _find_bypass_path_any(fsm, {dominator}, dominated)


def _has_sub_loop_state(fsm: FSMLoop) -> bool:
    """Return True if any state in the FSM has ``loop:`` set (delegates to a child loop).

    Used by ENH-1961 to distinguish "capture lives in a sub-loop" from "capture is missing".
    """
    return any(state.loop is not None for state in fsm.states.values())


def _validate_capture_reachability(fsm: FSMLoop) -> list[ValidationError]:
    """Validate that ``${captured.*}`` references are dominated by their capturing states.

    ENH-1961: For each state that references ``${captured.<var>.*}`` in its action
    or evaluate source, checks that the capturing state dominates the referencing
    state (i.e., all paths from the initial state pass through the capture state).

    Emits:
    - WARNING when a capture state does not dominate a referencing state
      (the reference may crash at runtime on paths that bypass the capture).
    - ERROR when a referenced capture variable has no capturing state at all
      in this FSM (excluding sub-loop captures which live in child namespaces).

    Suppressed by `capture_reachability_ok: true` at the loop top-level for
    loops with a reviewed, runtime-guarded bypass the dominance analysis can't
    model (e.g. a marker file checked by a shell action).
    """
    if fsm.capture_reachability_ok:
        return []
    errors: list[ValidationError] = []

    # Step 1: Build capture map (var_name → set of capturing state names).
    # A variable may be captured by more than one state on mutually-exclusive
    # branches (e.g. fifo_pop vs select_next dispatched by schedule_mode); the
    # reference is safe as long as the *set* collectively dominates it.
    capture_map: dict[str, set[str]] = {}
    for state_name, state in fsm.states.items():
        if state.capture:
            capture_map.setdefault(state.capture, set()).add(state_name)

    # BUG-2812: names of states that delegate to a sub-loop (`loop:` set).
    # A reference of the form `${captured.<state_name>.<var>...}` where
    # <state_name> is one of these is the CORRECT nested-namespace form —
    # executor.py merges the child's captures under the invoking state's own
    # name (`self.captured[self.current_state] = child_executor.captured`),
    # not under any locally-declared `capture:` name.
    loop_state_names = {name for name, state in fsm.states.items() if state.loop is not None}

    # Step 2: Build reference map (state_name → set of dotted-path tuples referenced)
    reference_map: dict[str, set[tuple[str, ...]]] = {}
    for state_name, state in fsm.states.items():
        # Skip sub-loop delegation states — their action is a loop name,
        # and captured vars belong to the child loop's namespace.
        if state.loop is not None:
            continue

        # Only collect references NOT guarded by `:default=` — a guarded
        # reference is safe even when the capture is missing on some path.
        refs: set[tuple[str, ...]] = set()
        if state.action:
            refs.update(_unguarded_captured_refs(state.action))
        if state.evaluate is not None and state.evaluate.source:
            refs.update(_unguarded_captured_refs(state.evaluate.source))
        if refs:
            reference_map[state_name] = refs

    if not reference_map:
        return errors

    # Step 3: For each reference, check dominance of capturing state
    for ref_state_name, ref_paths in reference_map.items():
        for path in ref_paths:
            var_name = path[0]
            nested = path[1:]

            if var_name in loop_state_names:
                # Correct nested sub-loop form: ${captured.<sub_loop_state>.<var>...}.
                # Validate dominance of the delegating state itself (still must
                # execute on every path reaching ref_state_name).
                cap_states = {var_name}
                if not _dominated_by_any(fsm, cap_states, ref_state_name):
                    bypass_path = _find_bypass_path_any(fsm, cap_states, ref_state_name)
                    path_str = " → ".join(bypass_path) if bypass_path else "unknown path"
                    errors.append(
                        ValidationError(
                            message=(
                                f"References ${{captured.{'.'.join(path)}}} but sub-loop "
                                f"state '{var_name}' may not execute on all paths to "
                                f"'{ref_state_name}'. Path(s) bypassing it: {path_str}"
                            ),
                            path=f"states.{ref_state_name}.action",
                            severity=ValidationSeverity.WARNING,
                        )
                    )
                continue

            if var_name not in capture_map:
                # Referenced capture variable has no capturing state in this FSM.
                # ENH-1998: downgrade to WARNING (not silent skip) when sub-loops
                # are present — the capture may live in a child namespace, but a
                # typo'd name should still surface rather than go completely dark.
                if _has_sub_loop_state(fsm):
                    errors.append(
                        ValidationError(
                            message=(
                                f"References ${{captured.{var_name}.*}} but no state in "
                                f"this loop captures '{var_name}'. "
                                f"If '{var_name}' is produced by a sub-loop, this may be "
                                f"intentional; otherwise add 'capture: {var_name}' to the "
                                f"state that produces this value."
                            ),
                            path=f"states.{ref_state_name}.action",
                            severity=ValidationSeverity.WARNING,
                        )
                    )
                    continue
                # No sub-loops: this is genuinely missing.
                errors.append(
                    ValidationError(
                        message=(
                            f"References ${{captured.{var_name}.*}} but no state in "
                            f"this loop captures '{var_name}'. Add 'capture: {var_name}' "
                            f"to the state that produces this value."
                        ),
                        path=f"states.{ref_state_name}.action",
                        severity=ValidationSeverity.ERROR,
                    )
                )
                continue

            # Capturing states present in this FSM (shouldn't drop any normally)
            cap_states = {s for s in capture_map[var_name] if s in fsm.states}
            if not cap_states:
                continue

            # BUG-2812: if var_name is itself a sub-loop-delegating state's own
            # `capture:` name, its value is the event-stream dict
            # {"output": ..., "exit_code": ...} — NOT the child's captures.
            # A nested path beyond that shape (e.g. `.extracted.output`)
            # references a field that doesn't exist there.
            delegating_cap_states = {s for s in cap_states if s in loop_state_names}
            if delegating_cap_states and nested:
                if len(nested) > 1 or nested[0] not in _SUB_LOOP_CAPTURE_OWN_FIELDS:
                    names = ", ".join(f"'{s}'" for s in sorted(delegating_cap_states))
                    errors.append(
                        ValidationError(
                            message=(
                                f"References ${{captured.{'.'.join(path)}}} but "
                                f"'{var_name}' is the sub-loop-delegating state "
                                f"{names}'s own `capture:` name — its value is only "
                                f"{{output, exit_code}} (the child's event stream), not "
                                f"the child's captures. Use "
                                f"${{captured.<sub_loop_state_name>.{'.'.join(nested)}}} "
                                f"to reference a captured value from the child loop."
                            ),
                            path=f"states.{ref_state_name}.action",
                            severity=ValidationSeverity.ERROR,
                        )
                    )
                    continue

            # Group dominance check: do the capturing states collectively
            # dominate ref_state_name (does at least one run on every path)?
            if not _dominated_by_any(fsm, cap_states, ref_state_name):
                bypass_path = _find_bypass_path_any(fsm, cap_states, ref_state_name)
                path_str = " → ".join(bypass_path) if bypass_path else "unknown path"

                if len(cap_states) == 1:
                    captured_by = f"state '{next(iter(cap_states))}' which may not"
                else:
                    names = ", ".join(f"'{s}'" for s in sorted(cap_states))
                    captured_by = f"states {names}, none of which"

                errors.append(
                    ValidationError(
                        message=(
                            f"References ${{captured.{var_name}.*}} but '{var_name}' "
                            f"is captured by {captured_by} "
                            f"execute on all paths to '{ref_state_name}'. "
                            f"Path(s) bypassing capture: {path_str}"
                        ),
                        path=f"states.{ref_state_name}.action",
                        severity=ValidationSeverity.WARNING,
                    )
                )

    return errors
