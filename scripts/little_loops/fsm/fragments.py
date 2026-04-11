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
