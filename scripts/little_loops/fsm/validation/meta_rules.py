"""Meta-loop rule family (MR-1..MR-6): harness-optimization loops that
modify other harness artifacts (loop YAMLs, skills, agents, commands) get
extra scrutiny -- a non-LLM evaluator backstop, artifact isolation/versioning,
partial-route dead-end detection, and hand-patching discipline.
"""

from __future__ import annotations

import re
from itertools import chain

from little_loops.fsm.schema import FSMLoop
from little_loops.fsm.validation._base import (
    EVALUATOR_REQUIRED_FIELDS,
    NON_LLM_EVALUATOR_TYPES,
    VALID_OPERATORS,
    VALID_VISIBILITY,
    ValidationError,
    ValidationSeverity,
    _is_llm_judged,
)

# Meta-loop detector: action string patterns that indicate harness artifact writes
_META_LOOP_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"loops/[\w-]+\.yaml"),
    re.compile(r"skills/[\w-]+/SKILL\.md"),
    re.compile(r"agents/[\w-]+\.md"),
    re.compile(r"commands/[\w-]+\.md"),
    re.compile(r"\.claude/(CLAUDE\.md|settings)"),
)

# Action string tokens that indicate meta-loop behavior
_META_LOOP_ACTION_TOKENS: frozenset[str] = frozenset({"yaml_state_editor", "replace_action"})

# Import paths that identify a loop as a meta-loop (harness optimization framework)
_META_LOOP_IMPORT_TRIGGERS: frozenset[str] = frozenset({"lib/benchmark.yaml"})

# MR-3: shared-tmp path detector. The runner injects ${context.run_dir} resolving
# to .loops/runs/<loop>-<timestamp>/; loops that hardcode .loops/tmp/ instead
# cause state corruption under concurrent runs (ll-parallel, retries, etc.).
_SHARED_TMP_PATH_RE = re.compile(r"\.loops/tmp/[\w./-]+")

# ENH-1819: Regex patterns for detecting multimodal evaluation in prompt actions
_MULTIMODAL_EVAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Read the screenshot", re.IGNORECASE),
    re.compile(r"view the (generated )?(website|page|image)", re.IGNORECASE),
    re.compile(r"screenshot\.(png|jpg|jpeg|webp)"),
    re.compile(r"\.(png|jpg|jpeg|webp)\b.*\b(read|view|evaluate|score|judge)", re.IGNORECASE),
)


def _is_meta_loop(fsm: FSMLoop) -> bool:
    """Return True if fsm is classified as a meta-loop.

    A loop is meta if ANY of the following match:
    1. Any state action string matches a harness-artifact path regex
       (writes another loop YAML, skill, agent, command, or project config)
    2. The loop's import list contains lib/benchmark.yaml
    3. Any state action references yaml_state_editor or replace_action
    """
    # Condition 2: imports lib/benchmark.yaml
    if any(imp in _META_LOOP_IMPORT_TRIGGERS for imp in fsm.imports):
        return True
    # Conditions 1 and 3: scan action strings
    for state in fsm.states.values():
        if state.action is None:
            continue
        for pattern in _META_LOOP_ACTION_PATTERNS:
            if pattern.search(state.action):
                return True
        for token in _META_LOOP_ACTION_TOKENS:
            if token in state.action:
                return True
    return False


def _validate_meta_loop_evaluation(fsm: FSMLoop) -> list[ValidationError]:
    """Validate meta-loop evaluation rules MR-1 and MR-2.

    MR-1 (ERROR): meta-loop must have at least one non-LLM evaluator.
    MR-2 (WARNING): meta-loop should reference a captured baseline in an evaluator.

    Both rules are suppressed by ``meta_self_eval_ok: true`` at the loop top-level.
    """
    errors: list[ValidationError] = []
    if fsm.meta_self_eval_ok or not _is_meta_loop(fsm):
        return errors

    # Collect all evaluator types used across all states
    evaluator_types: set[str] = set()
    for state in fsm.states.values():
        if state.evaluate is not None:
            evaluator_types.add(state.evaluate.type)

    # MR-1: must have at least one non-LLM evaluator
    if not evaluator_types & NON_LLM_EVALUATOR_TYPES:
        errors.append(
            ValidationError(
                message=(
                    "Loop modifies harness artifacts but has no non-LLM evaluator. "
                    "LLM self-grades on harness updates are unreliable (SHOR Table 1: "
                    "33-55% accuracy). Pair every check_semantic state with at least one "
                    "of: exit_code, output_numeric, convergence, diff_stall, score_stall, "
                    "action_stall, mcp_result. "
                    "Note: llm_structured and comparator both use the LLM and do not satisfy MR-1. "
                    "To suppress with justification, set `meta_self_eval_ok: true` at the "
                    "loop top-level."
                ),
                path="<root>",
                severity=ValidationSeverity.ERROR,
            )
        )

    # MR-2: should reference a captured baseline in a later evaluator
    capture_names: set[str] = {state.capture for state in fsm.states.values() if state.capture}
    if capture_names and not _has_baseline_reference(fsm, capture_names):
        errors.append(
            ValidationError(
                message=(
                    "Meta-loop appears to lack a measure→propose→apply→re-measure "
                    "spine: no captured baseline value is referenced by a later evaluator. "
                    "Meta-loops should compare a post-change score against a pre-change "
                    "baseline (see loops/harness-optimize.yaml as reference template). "
                    "To suppress, set `meta_self_eval_ok: true`."
                ),
                path="<root>",
                severity=ValidationSeverity.WARNING,
            )
        )

    return errors


def _validate_harness_multimodal_evaluator_blind_spot(fsm: FSMLoop) -> list[ValidationError]:
    """Warn when harness loops use LLM multimodal eval as sole gate to terminal.

    LLMs can silently fall back to text-only analysis when reading images,
    producing verdicts based on incomplete information. The output_contains
    evaluator can verify the LLM wrote the pass string but not that it
    actually processed the image. This is the same class of failure as MR-1
    (LLM self-evaluation bias) applied to artifact evaluation rather than
    harness modification.

    Suppressed by ``meta_self_eval_ok: true`` at the loop top-level.
    """
    errors: list[ValidationError] = []
    if fsm.meta_self_eval_ok or fsm.category != "harness":
        return errors

    terminal_states = fsm.get_terminal_states()

    for state_name, state in fsm.states.items():
        if state.action_type != "prompt" or not state.action:
            continue
        if state.evaluate is None or state.evaluate.type != "output_contains":
            continue
        if not any(p.search(state.action) for p in _MULTIMODAL_EVAL_PATTERNS):
            continue
        if state.on_yes not in terminal_states:
            continue
        errors.append(
            ValidationError(
                message=(
                    f"State '{state_name}' evaluates a screenshot/image via LLM "
                    "prompt and routes directly to a terminal on success. The "
                    "output_contains evaluator can verify the LLM wrote the pass "
                    "string but not that the LLM actually processed the image. "
                    "Consider adding a shell-action verification state (e.g., "
                    "functional smoke test) between scoring and the terminal."
                ),
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            )
        )

    return errors


def _find_shared_tmp_writes(fsm: FSMLoop) -> list[tuple[str, str]]:
    """Return (state_name, matched_path) for every action referencing shared .loops/tmp/.

    Scans `state.action` only. Prompts and sub-loop bindings can also reference
    paths, but those are out of static-scan reach: action strings are the
    place where loop YAMLs directly encode artifact paths.
    """
    findings: list[tuple[str, str]] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        for match in _SHARED_TMP_PATH_RE.finditer(state.action):
            findings.append((state_name, match.group(0)))
    return findings


def _validate_artifact_isolation(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-3: loops must isolate artifacts to ${context.run_dir}.

    The runner injects ${context.run_dir} pointing at .loops/runs/<loop>-<ts>/
    and creates the folder before execution. Loops that write intermediate
    state (queues, checkpoints, generated files) to shared .loops/tmp/ paths
    will corrupt each other under concurrent runs (ll-parallel workers, retries,
    repeated invocations).

    Suppressed by `shared_state_ok: true` at the loop top-level for loops that
    intentionally share state across runs.
    """
    if fsm.shared_state_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, path in _find_shared_tmp_writes(fsm):
        errors.append(
            ValidationError(
                message=(
                    f"State writes to shared '{path}' instead of "
                    "'${context.run_dir}/...'. Concurrent runs of this loop "
                    "(e.g., under ll-parallel) will corrupt each other's state. "
                    "Use the runner-injected `${context.run_dir}` for per-run "
                    "artifact paths, or set `shared_state_ok: true` at the loop "
                    "top-level if cross-run sharing is intentional."
                ),
                path=f"states.{state_name}.action",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


def _validate_partial_route_dead_end(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-4: LLM-judged states with only on_yes have a partial/no dead-end.

    A state gated by the default LLM judge can receive yes/no/partial verdicts.
    If only on_yes is mapped (and no on_no, on_partial, next, or route table with
    a default exist), a partial or no verdict returns None from _route and silently
    terminates the loop — the parent treats this as failed.

    Suppressed by `partial_route_ok: true` at the loop top-level for the rare
    case where dead-ending on a non-yes verdict is intentional.
    """
    if fsm.partial_route_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not _is_llm_judged(state):
            continue
        # States with an unconditional next: or a full route: table are safe.
        if state.next is not None or state.route is not None:
            continue
        # Only flag when on_yes is set but at least one of on_no/on_partial is missing.
        if state.on_yes is None:
            continue
        missing = [v for v in ("no", "partial") if getattr(state, f"on_{v}") is None]
        if not missing:
            continue
        unrouted = " or ".join(f"`{v}`" for v in missing)
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] LLM-judged prompt routes only on_yes; "
                    f"a {unrouted} verdict has no route and will dead-end the loop "
                    "(parent reads this as failed). Add on_no/on_partial, use `next:` "
                    "for an unconditional handoff, or a `route:` table with a default. "
                    "Set `partial_route_ok: true` at the loop top-level to suppress "
                    "if intentional. (ENH-1917)"
                ),
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


def _validate_artifact_overwrite(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-5 (ENH-1957): harness loops should version artifacts per iteration.

    A harness-category loop that iteratively generates and overwrites a flat artifact
    path (e.g. ``${context.run_dir}/image.svg``) loses all intermediate versions.
    Only the final iteration survives. This rule flags iterative generate→evaluate→generate
    cycles that write to artifact paths without declaring versioning intent.

    Suppressed by ``artifact_versioning: true`` (loop snapshots per-iteration artifacts)
    or ``artifact_versioning_ok: true`` (intentional overwrite, e.g. artifact varies
    by task).
    """
    if fsm.artifact_versioning or fsm.artifact_versioning_ok:
        return []
    if fsm.category not in ("harness",):
        return []

    errors: list[ValidationError] = []

    # Find states that write to artifact paths (shell actions with file output)
    writers: dict[str, set[str]] = {}  # state_name -> set of artifact paths
    for state_name, state in fsm.states.items():
        if not state.action or state.action_type not in ("shell", None):
            continue
        # Skip sub-loop delegation states
        if state.action_type == "loop":
            continue
        action = state.action
        # Find run_dir-based artifact writes: ${context.run_dir}/<path> or $RUNDIR/<path>
        import re

        # Match patterns like: ${context.run_dir}/output.svg, $RUNDIR/image.png, > path
        # We look for output redirections or cp/mv commands writing to run_dir
        artifact_refs = set()
        for pattern in (
            r'\$\{context\.run_dir\}/([^\s"\';&]+)',
            r'\$\{captured\.[^}]+\}/([^\s"\';&]+)',
        ):
            for m in re.finditer(pattern, action):
                artifact_refs.add(m.group(1))
        # Also detect explicit cp/mv writing to run_dir paths
        for m in re.finditer(r'(?:cp|mv)\s+.*\s+\$\{context\.run_dir\}/([^\s"\';&]+)', action):
            artifact_refs.add(m.group(1))
        if artifact_refs:
            writers[state_name] = artifact_refs

    if not writers:
        return []

    # Detect iterative cycles: a writer state that is reachable from itself
    # via a non-trivial path through other states (generate → evaluate → generate)
    for state_name in writers:
        refs = fsm.states[state_name].get_referenced_states()
        # Check if this writer or its downstream states loop back to this writer
        visited: set[str] = set()
        to_visit = list(refs - {"$current"})
        while to_visit:
            target = to_visit.pop()
            if target in visited or target not in fsm.states:
                continue
            visited.add(target)
            if target == state_name:
                # Found a cycle: this writer state is reachable from itself
                artifact_list = ", ".join(sorted(writers[state_name]))
                errors.append(
                    ValidationError(
                        message=(
                            f"[state: {state_name}] Harness loop writes artifact(s) "
                            f"({artifact_list}) to a flat path in an iterative cycle "
                            f"({state_name} → ... → {state_name}). Per-iteration versions "
                            "are lost; only the final output survives. Add per-iteration "
                            "snapshots (see oracle generator-evaluator for pattern) and "
                            "declare `artifact_versioning: true`, or set "
                            "`artifact_versioning_ok: true` if intentional. (ENH-1957)"
                        ),
                        path=f"states.{state_name}",
                        severity=ValidationSeverity.WARNING,
                    )
                )
                break
            target_state = fsm.states.get(target)
            if target_state is not None:
                target_refs = target_state.get_referenced_states()
                for r in target_refs:
                    if r != "$current" and r not in visited:
                        to_visit.append(r)

    return errors


def _validate_generator_fix_discipline(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-6 (ENH-2079): meta-loops should not hand-patch generator artifacts.

    Detects the hand-patching anti-pattern: a ``shell``-type state that writes to the
    same file path as a non-shell (LLM-type) generator state in the same loop.
    Hand-patching creates fragile output that diverges from the generator on the next
    run; the stable fix is to update the generator action instead.

    Suppressed by ``generator_fix_ok: true`` at the loop top-level for intentional
    post-processing cases.
    """
    if fsm.generator_fix_ok or not _is_meta_loop(fsm):
        return []

    # Markers that indicate a prompt/slash_command state is generating file artifacts
    _GENERATOR_MARKERS = ("yaml_state_editor", "replace_action", "to_file:")

    _PATH_PATTERNS = (
        re.compile(r'\$\{context\.run_dir\}/([^\s"\';&|]+)'),
        re.compile(r'\$\{captured\.[^}]+\}/([^\s"\';&|]+)'),
    )

    def _extract_paths(action: str) -> set[str]:
        paths: set[str] = set()
        for pat in _PATH_PATTERNS:
            for m in pat.finditer(action):
                paths.add(m.group(1).rstrip("/"))
        return paths

    shell_targets: dict[str, set[str]] = {}  # state_name -> set of file paths
    generator_targets: dict[str, set[str]] = {}  # state_name -> set of file paths

    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        action = state.action
        paths = _extract_paths(action)
        if not paths:
            continue
        action_type = state.action_type
        if action_type in ("shell", None):
            shell_targets[state_name] = paths
        elif action_type in ("prompt", "slash_command"):
            if any(marker in action for marker in _GENERATOR_MARKERS):
                generator_targets[state_name] = paths

    errors: list[ValidationError] = []
    for gen_name, gen_paths in generator_targets.items():
        for shell_name, shell_paths in shell_targets.items():
            overlap = gen_paths & shell_paths
            if overlap:
                artifact_list = ", ".join(sorted(overlap))
                errors.append(
                    ValidationError(
                        message=(
                            f"[states: {gen_name}, {shell_name}] Hand-patching anti-pattern: "
                            f"LLM-generator state '{gen_name}' and shell state '{shell_name}' "
                            f"both write to ({artifact_list}). Move the fix into the generator "
                            "action so every run produces correct output automatically. "
                            "Set `generator_fix_ok: true` to suppress for intentional "
                            "post-processing. (ENH-2079)"
                        ),
                        path=f"states.{shell_name}",
                        severity=ValidationSeverity.WARNING,
                    )
                )

    return errors


# gate-completeness (FEAT-3328): literal collection displays of string
# literals -- {...}, [...], (...) -- possibly spanning multiple lines with a
# trailing comma. The `(` alternative excludes call syntax (a `(` immediately
# preceded by an identifier character or closing bracket is a function call,
# not a tuple display).
_BRACE_DISPLAY_RE = re.compile(r"\{([^{}]*)\}")
_BRACKET_DISPLAY_RE = re.compile(r"\[([^\[\]]*)\]")
_PAREN_DISPLAY_RE = re.compile(r"(?<![\w)\]])\(([^()]*)\)")

_STRING_LITERAL_RE = re.compile(r'"([^"\\]*)"|\'([^\'\\]*)\'')

# An `import` statement (bare or `from ... import`), capturing either a
# parenthesized multi-line group or the rest of the line -- matches the
# in-repo `from x import (\n    NAME,\n)` shape used by validate_evaluators.
_IMPORT_BLOCK_RE = re.compile(
    r"^[ \t]*(?:from[ \t]+\S+[ \t]+)?import[ \t]+(?:\([^)]*\)|[^\n]*)",
    re.MULTILINE,
)

# Tables checked smallest-first: NON_LLM_EVALUATOR_TYPES is derived from
# EVALUATOR_REQUIRED_FIELDS.keys() (a subset of it), so it must be checked
# first to report the tighter table and avoid a double emission (AC #1a).
# EVALUATOR_REQUIRED_FIELDS is linted on both its keys (evaluator type names)
# and its flattened values (field names); the two are disjoint so their
# relative order does not matter (AC #1c).
_GATE_COMPLETENESS_TABLES: tuple[tuple[str, frozenset[str]], ...] = (
    ("VALID_VISIBILITY", VALID_VISIBILITY),
    ("VALID_OPERATORS", VALID_OPERATORS),
    ("NON_LLM_EVALUATOR_TYPES", NON_LLM_EVALUATOR_TYPES),
    ("EVALUATOR_REQUIRED_FIELDS", frozenset(EVALUATOR_REQUIRED_FIELDS.keys())),
    (
        "EVALUATOR_REQUIRED_FIELDS",
        frozenset(chain.from_iterable(EVALUATOR_REQUIRED_FIELDS.values())),
    ),
)


def _extract_string_literal_members(body: str) -> list[str] | None:
    """Return the quoted string members of `body`, or None if `body` contains
    anything besides string literals, commas, and whitespace (e.g. it is not
    a pure string-literal collection display)."""
    members = [
        m.group(1) if m.group(1) is not None else m.group(2)
        for m in _STRING_LITERAL_RE.finditer(body)
    ]
    remainder = _STRING_LITERAL_RE.sub("", body)
    if remainder.strip(" \t\n,") != "":
        return None
    return members


def _imports_table(action: str, name: str) -> bool:
    """Return True if `name` appears on an `import` statement line (or a
    parenthesized multi-line import block) inside `action` -- a mention
    inside a comment does not count (AC #1)."""
    return any(
        re.search(rf"\b{re.escape(name)}\b", m.group(0)) for m in _IMPORT_BLOCK_RE.finditer(action)
    )


def _validate_gate_completeness(fsm: FSMLoop) -> list[ValidationError]:
    """Validate the gate-completeness rule (FEAT-3328): an intermediate
    `shell` gate must not hardcode a literal collection that restates a
    little-loops validator's exported rule table instead of importing it.

    When the restatement is a proper subset of what the terminal gate
    checks, it doesn't just miss defects -- it launders them, giving every
    downstream pass false confidence and pushing detection past the point
    where the retry topology can repair the mistake.

    Detection is regex-over-raw-string, not `ast.parse`: every other rule in
    this package (MR-3, MR-5, MR-6, and the shell_safety.py family) works the
    same way, and safely extracting embedded Python from a `python3 -c`/
    heredoc shell action would need its own quoting/escaping mini-parser --
    the cardinality floor below does the false-positive suppression `ast`
    would otherwise be used for.

    A literal is flagged only when it has >=3 members, every member is in one
    of the linted tables, and the action does not already import that
    table's identifier via an `import` statement (a comment mention does not
    count -- see `_imports_table`). Tables are checked smallest-first so a
    literal that is a subset of both NON_LLM_EVALUATOR_TYPES and
    EVALUATOR_REQUIRED_FIELDS.keys() (the former is derived from the latter)
    is reported once, against the tighter table.

    Known coverage gaps (documented, not fixed here -- AC #5):
    - only `shell` actions are inspected; a rule table restated in prose
      inside a `prompt` action is invisible to this rule (tracked separately
      as ENH-3355).
    - a full dict-display restatement of EVALUATOR_REQUIRED_FIELDS is not
      matched as a dict (the detection regex has no dict form); it is caught
      only indirectly, via any >=3-member nested value list.

    Suppressed by `gate_completeness_ok: true` at the loop top-level.
    """
    if fsm.gate_completeness_ok:
        return []

    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if state.action_type != "shell" or not state.action:
            continue
        action = state.action
        if "python3" not in action:
            continue

        for display_re in (_BRACE_DISPLAY_RE, _BRACKET_DISPLAY_RE, _PAREN_DISPLAY_RE):
            for match in display_re.finditer(action):
                members = _extract_string_literal_members(match.group(1))
                if members is None or len(members) < 3:
                    continue
                member_set = frozenset(members)
                # Match against the most specific (smallest, first-listed) table
                # only -- once found, stop, regardless of that table's import
                # status. Falling through to a broader table when the specific
                # one is already imported would double-report against a table
                # the author never intended to restate (AC #1a).
                for table_name, table in _GATE_COMPLETENESS_TABLES:
                    if member_set <= table:
                        if not _imports_table(action, table_name):
                            errors.append(
                                ValidationError(
                                    message=(
                                        f"[state: {state_name}] shell gate hardcodes a literal "
                                        f"{sorted(member_set)!r} that is a subset of "
                                        f"{table_name}. Import {table_name} from "
                                        "little_loops.fsm.validation instead of restating it "
                                        "-- a restated subset can launder defects past this "
                                        "gate until the terminal validator catches them, too "
                                        "late for the retry topology to reach the state that "
                                        "made the mistake. Set `gate_completeness_ok: true` "
                                        "at the loop top-level to suppress if this is a "
                                        "deliberate, narrower curated vocabulary. (FEAT-3328)"
                                    ),
                                    path=f"states.{state_name}.action",
                                    severity=ValidationSeverity.WARNING,
                                )
                            )
                        break

    return errors


def _has_baseline_reference(fsm: FSMLoop, capture_names: set[str]) -> bool:
    """Return True if any evaluate block references a captured variable."""
    for state in fsm.states.values():
        ev = state.evaluate
        if ev is None:
            continue
        # Check string fields that may interpolate captured values
        candidates = [ev.previous, ev.source]
        if isinstance(ev.target, str):
            candidates.append(ev.target)
        for field_val in candidates:
            if not field_val:
                continue
            for name in capture_names:
                if f"captured.{name}" in field_val:
                    return True
    return False
