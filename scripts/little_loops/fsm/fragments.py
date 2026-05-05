"""Fragment library resolution for FSM loops.

Implements parse-time expansion of ``fragment:`` references in loop YAML files.
Fragment libraries define named partial state definitions that any loop can import
and reference, eliminating copy-paste duplication across loop files.

Fragment resolution happens before ``FSMLoop.from_dict`` is called, so the engine
never sees ``fragment:`` keys.

Example loop YAML::

    import:
      - lib/common.yaml

    states:
      lint:
        fragment: shell_exit    # inherits action_type + evaluate from fragment
        action: "ruff check ."
        on_yes: done
        on_no: fix

Example library YAML (``lib/common.yaml``)::

    fragments:
      shell_exit:
        action_type: shell
        evaluate:
          type: exit_code
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "loops"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two dicts; override keys win at every nesting level.

    For nested dicts, recursively merges instead of replacing. For all other
    value types (str, int, bool, list, None), the override value wins outright.
    Returns a new dict; neither input is mutated.

    Args:
        base: Base dict (e.g. a fragment definition).
        override: Override dict (e.g. state-level fields).

    Returns:
        New merged dict with override taking precedence.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_fragments(raw_loop_dict: dict[str, Any], loop_dir: Path) -> dict[str, Any]:
    """Load fragment libraries, merge namespaces, and expand ``fragment:`` references.

    Resolution steps:
    1. Load each path in ``import:`` (relative to ``loop_dir``), collecting all
       named fragments. Later imports override earlier imports for the same name.
    2. Merge the loop's own ``fragments:`` block on top (local overrides imports).
    3. For each state that has a ``fragment:`` key, deep-merge the named fragment
       into the state dict (state-level keys win), then remove the ``fragment:`` key.

    Returns a new dict with all ``fragment:`` keys expanded. The ``import:`` and
    ``fragments:`` keys remain in the returned dict so callers can access them for
    display or validation purposes.

    Args:
        raw_loop_dict: Raw YAML dict loaded from a loop file.
        loop_dir: Directory containing the loop file; import paths are resolved
            relative to this directory.

    Returns:
        New dict with fragment references expanded.

    Raises:
        FileNotFoundError: If an ``import:`` path does not exist relative to ``loop_dir``.
        ValueError: If a state references a ``fragment:`` name that is not defined in
            any imported library or the local ``fragments:`` block.
    """
    # Step 1: load imported fragment libraries
    imported_fragments: dict[str, dict[str, Any]] = {}
    for import_path in raw_loop_dict.get("import", []):
        lib_path = loop_dir / import_path
        if not lib_path.exists():
            builtin_path = _BUILTIN_LOOPS_DIR / import_path
            if builtin_path.exists():
                lib_path = builtin_path
            else:
                raise FileNotFoundError(
                    f"Fragment library not found: {import_path} "
                    f"(checked '{loop_dir / import_path}' and '{builtin_path}')"
                )
        with open(lib_path) as f:
            lib_data = yaml.safe_load(f)
        if isinstance(lib_data, dict):
            for name, frag in lib_data.get("fragments", {}).items():
                imported_fragments[name] = frag

    # Step 2: merge local fragments: block on top (local wins)
    all_fragments: dict[str, dict[str, Any]] = {
        **imported_fragments,
        **raw_loop_dict.get("fragments", {}),
    }

    result = dict(raw_loop_dict)
    states: dict[str, Any] = dict(result.get("states", {}))

    # Step 3: if no states reference a fragment, return early (no-op)
    if not any(isinstance(s, dict) and s.get("fragment") is not None for s in states.values()):
        return result

    for state_name, state_dict in states.items():
        if not isinstance(state_dict, dict):
            continue
        fragment_name = state_dict.get("fragment")
        if fragment_name is None:
            continue
        if fragment_name not in all_fragments:
            available = ", ".join(sorted(all_fragments))
            raise ValueError(
                f"State '{state_name}': fragment '{fragment_name}' not found. "
                f"Available fragments: {available or '(none)'}"
            )
        # Deep merge: fragment is the base, state fields override
        # Strip description before merge — it is metadata, not a state field
        frag_copy = dict(all_fragments[fragment_name])
        frag_copy.pop("description", None)
        merged = _deep_merge(frag_copy, state_dict)
        del merged["fragment"]  # consume the fragment: key
        states[state_name] = merged

    result["states"] = states
    return result


def resolve_inheritance(
    raw_loop_dict: dict[str, Any],
    loop_dir: Path,
    _seen: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Resolve ``from:`` template inheritance by deep-merging parent into child.

    A loop YAML with ``from: <name>`` inherits all top-level fields and states
    from the named parent loop. The child's own fields override the parent's at
    every nesting level (per :func:`_deep_merge` semantics): scalars and lists
    are replaced by the child, dicts are merged recursively. The ``from:`` key
    itself is stripped from the returned dict.

    Parent lookup uses :func:`little_loops.cli.loop._helpers.resolve_loop_path`,
    which searches ``loop_dir`` first then falls back to the bundled built-in
    loops directory. Cycles in the ``from:`` chain raise ``ValueError`` with the
    full chain path; missing parents raise ``FileNotFoundError``.

    Resolution must run *before* :func:`resolve_fragments` and *before* the
    required-fields check in :func:`load_and_validate`, so a child can omit
    fields its parent provides (including ``initial`` and ``states``) and so a
    parent's ``import:``/``fragments:`` blocks survive into the merged result.

    Args:
        raw_loop_dict: Raw YAML dict loaded from a loop file.
        loop_dir: Directory containing the (child) loop file; parent names are
            resolved relative to this directory.
        _seen: Internal tuple of parent names already visited during recursion;
            used for cycle detection.

    Returns:
        New dict with ``from:`` resolved and stripped. If the input has no
        ``from:`` key, returns it unchanged.

    Raises:
        ValueError: If ``from:`` is not a string, the parent is not a YAML
            mapping, or a cycle is detected in the inheritance chain.
        FileNotFoundError: If the parent loop name cannot be resolved.
    """
    if "from" not in raw_loop_dict:
        return raw_loop_dict

    parent_name = raw_loop_dict["from"]
    if not isinstance(parent_name, str):
        raise ValueError(f"`from:` must be a string, got {type(parent_name).__name__}")

    if parent_name in _seen:
        chain = " -> ".join(_seen + (parent_name,))
        raise ValueError(f"Circular `from:` chain: {chain}")

    # Lazy import to avoid circular import at module load (cli.loop._helpers
    # imports from fsm.* indirectly). Mirrors the pattern used in
    # fsm/executor.py:410 for sub-loop calls.
    from little_loops.cli.loop._helpers import resolve_loop_path

    parent_path = resolve_loop_path(parent_name, loop_dir)
    with open(parent_path) as f:
        parent_data = yaml.safe_load(f)

    if not isinstance(parent_data, dict):
        raise ValueError(
            f"Parent loop '{parent_name}' is not a YAML mapping (got {type(parent_data).__name__})"
        )

    parent_data = resolve_inheritance(parent_data, parent_path.parent, _seen + (parent_name,))

    child_without_from = {k: v for k, v in raw_loop_dict.items() if k != "from"}
    merged = _deep_merge(parent_data, child_without_from)
    merged.pop("from", None)
    return merged


def resolve_flow(raw_loop_dict: dict[str, Any]) -> dict[str, Any]:
    """Expand ``flow:`` linear shorthand into a verbose ``states:`` map.

    A loop YAML with ``flow: [<state>, ...]`` declares an ordered linear chain
    of states. Each entry is either a bare name (unconditional forward
    transition) or a ternary ``name?yes_target:no_target`` (conditional
    branching). The last entry is implicitly ``terminal: true``.

    Optional ``state_defs:`` supplies prompt/action/evaluate bodies that are
    deep-merged into the generated state skeletons. If both ``flow:`` and
    ``states:`` are present, raises ``ValueError`` — the two are mutually
    exclusive.

    Resolution runs *after* :func:`resolve_inheritance` (so a child can
    override a parent's states with its own ``flow:``) and *before* the
    required-fields check in :func:`load_and_validate` (so the expanded
    ``states:`` key satisfies the validator).

    Args:
        raw_loop_dict: Raw YAML dict loaded from a loop file.

    Returns:
        New dict with ``flow:`` expanded to ``states:`` and both ``flow:``
        and ``state_defs:`` stripped. If the input has no ``flow:`` key,
        returns it unchanged.

    Raises:
        ValueError: If ``flow:`` is not a list, is empty, or contains a
            malformed ternary entry.
    """
    if "flow" not in raw_loop_dict:
        return raw_loop_dict

    # If both flow: and states: are present, flow: takes precedence. This
    # handles the case where states was inherited via `from:` — the child's
    # explicit flow: overrides the parent's states.
    #

    flow = raw_loop_dict["flow"]
    if not isinstance(flow, list):
        raise ValueError(f"'flow:' must be a list, got {type(flow).__name__}")
    if len(flow) < 1:
        raise ValueError("'flow:' must contain at least one state")

    state_defs: dict[str, dict[str, Any]] = raw_loop_dict.get("state_defs", {})
    if not isinstance(state_defs, dict):
        state_defs = {}

    generated_states: dict[str, dict[str, Any]] = {}

    # Pre-parse all entries to extract state names (strip ternary suffixes)
    def _parse_name(raw: str) -> str:
        return raw.split("?", 1)[0] if "?" in raw else raw

    parsed_names = [_parse_name(e) if isinstance(e, str) else e for e in flow]

    for i, entry in enumerate(flow):
        is_last = i == len(flow) - 1
        next_name = parsed_names[i + 1] if not is_last else None

        if not isinstance(entry, str):
            raise ValueError(f"'flow:' entry {i} must be a string, got {type(entry).__name__}")

        if "?" in entry:
            # Ternary form: name?yes_target:no_target
            parts = entry.split("?", 1)
            state_name = parts[0]
            targets = parts[1]

            if ":" not in targets or targets.endswith(":") or targets.startswith(":"):
                raise ValueError(
                    f"Malformed ternary in flow entry '{entry}': must be name?yes_target:no_target"
                )
            yes_target, no_target = targets.split(":", 1)
            if not yes_target or not no_target:
                raise ValueError(
                    f"Malformed ternary in flow entry '{entry}': "
                    f"both yes and no targets must be non-empty"
                )

            skeleton: dict[str, Any] = {"on_yes": yes_target, "on_no": no_target}
        else:
            state_name = entry
            skeleton = {}
            if next_name is not None:
                skeleton["next"] = next_name

        if is_last:
            skeleton["terminal"] = True

        # Deep-merge state_defs body into generated skeleton
        if state_name in state_defs:
            skeleton = _deep_merge(skeleton, state_defs[state_name])

        generated_states[state_name] = skeleton

    result = {k: v for k, v in raw_loop_dict.items() if k not in ("flow", "state_defs")}
    result["states"] = generated_states
    return result
