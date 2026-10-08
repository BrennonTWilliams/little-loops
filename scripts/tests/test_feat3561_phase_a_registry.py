"""Verb registry invariants (FEAT-3561 phase A)."""

from __future__ import annotations

import ast
import json
import math
from importlib import resources

import pytest

from little_loops.next_arena.registry import (
    ACTION_VARIANTS,
    CANONICAL_VERB_ORDER,
    REGISTRY,
    RESERVED_VARIANTS,
    SCHEMA_VERSION,
    get_verb,
    loop_verbs,
    registered_verbs,
    scan_verbs,
    sprint_verbs,
    verbs_in_domain,
)


def test_canonical_order_is_fixed() -> None:
    assert CANONICAL_VERB_ORDER == (
        "implement-issue",
        "refine-issue",
        "resolve-blocker",
        "run-loop",
        "run-sprint",
        "capture-issues",
    )


def test_all_canonical_verbs_registered_in_canonical_order() -> None:
    assert registered_verbs() == CANONICAL_VERB_ORDER
    assert list(REGISTRY) == [v for v in CANONICAL_VERB_ORDER if v in REGISTRY]


def test_unknown_verbs_are_absent() -> None:
    assert "nope" not in REGISTRY
    with pytest.raises(KeyError):
        get_verb("nope")


def test_axis_keys_and_order_are_exact() -> None:
    assert get_verb("implement-issue").axes == (
        "priority",
        "outcome",
        "leverage",
        "effort",
        "momentum",
    )
    assert get_verb("refine-issue").axes == (
        "priority",
        "readiness_gap",
        "leverage",
        "staleness",
        "momentum",
    )
    assert get_verb("resolve-blocker").axes == (
        "priority",
        "leverage",
        "effort",
        "staleness",
        "momentum",
    )
    assert get_verb("run-loop").axes == ("frequency", "recency", "success")
    assert get_verb("run-sprint").axes == ("ready_share", "priority", "since_last_run")
    assert get_verb("capture-issues").axes == ()  # evidence-only singleton: no scored axes


@pytest.mark.parametrize("name", list(REGISTRY))
def test_default_weights_cover_axes_in_order_and_sum_to_one(name: str) -> None:
    spec = get_verb(name)
    assert list(spec.default_weights) == list(spec.axes)
    if spec.evidence_only:
        assert dict(spec.default_weights) == {}
        return
    assert math.isclose(sum(spec.default_weights.values()), 1.0, abs_tol=1e-12)
    assert all(w > 0 for w in spec.default_weights.values())


def test_default_weights_values() -> None:
    assert dict(get_verb("implement-issue").default_weights) == {
        "priority": 0.30,
        "outcome": 0.30,
        "leverage": 0.20,
        "effort": 0.10,
        "momentum": 0.10,
    }
    assert dict(get_verb("refine-issue").default_weights) == {
        "priority": 0.30,
        "readiness_gap": 0.30,
        "leverage": 0.15,
        "staleness": 0.15,
        "momentum": 0.10,
    }
    assert dict(get_verb("resolve-blocker").default_weights) == {
        "priority": 0.25,
        "leverage": 0.50,
        "effort": 0.15,
        "staleness": 0.05,
        "momentum": 0.05,
    }
    assert dict(get_verb("run-loop").default_weights) == {
        "frequency": 0.50,
        "recency": 0.30,
        "success": 0.20,
    }
    assert dict(get_verb("run-sprint").default_weights) == {
        "ready_share": 0.50,
        "priority": 0.30,
        "since_last_run": 0.20,
    }


def test_caps_and_minimum_evidence() -> None:
    assert get_verb("implement-issue").default_cap == 2
    assert get_verb("implement-issue").default_refine_cap is None
    assert get_verb("refine-issue").default_cap == 2
    assert get_verb("refine-issue").default_refine_cap == 5
    assert get_verb("resolve-blocker").default_cap == 2
    assert get_verb("run-loop").default_cap == 2
    assert get_verb("run-sprint").default_cap == 2
    assert get_verb("capture-issues").default_cap == 2
    assert dict(get_verb("capture-issues").extra_settings) == {
        "activity_threshold": 20,
        "activity_lookback_days": 30,
    }
    assert all(spec.minimum_evidence for spec in REGISTRY.values())


def test_candidate_domains() -> None:
    assert [REGISTRY[v].domain for v in REGISTRY] == [
        "issue",
        "issue",
        "issue",
        "loop",
        "sprint",
        "scan",
    ]
    assert verbs_in_domain("loop") == loop_verbs() == ("run-loop",)
    assert verbs_in_domain("sprint") == sprint_verbs() == ("run-sprint",)
    assert verbs_in_domain("scan") == scan_verbs() == ("capture-issues",)


def test_variants_and_schema_version() -> None:
    assert ACTION_VARIANTS == ("slash", "loop", "sprint", "scan")
    assert RESERVED_VARIANTS == ()  # FEAT-3713 registered the last reserved variants
    assert not set(ACTION_VARIANTS) & set(RESERVED_VARIANTS)
    assert SCHEMA_VERSION == 4  # FEAT-3713: sprint/scan variants, run-sprint/capture-issues verbs


def test_registry_is_read_only() -> None:
    with pytest.raises(TypeError):
        REGISTRY["x"] = None  # type: ignore[index]
    with pytest.raises(TypeError):
        get_verb("implement-issue").default_weights["priority"] = 1.0  # type: ignore[index]


def test_registry_module_imports_stdlib_only() -> None:
    tree = ast.parse((resources.files("little_loops") / "next_arena" / "registry.py").read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "collections", "dataclasses", "types"}


def test_config_schema_matches_registry() -> None:
    schema = json.loads((resources.files("little_loops") / "config-schema.json").read_text())
    verbs = schema["properties"]["next"]["properties"]["verbs"]
    assert verbs["additionalProperties"] is False
    assert list(verbs["properties"]) == list(REGISTRY)
    for name, spec in REGISTRY.items():
        node = verbs["properties"][name]
        assert node["additionalProperties"] is False
        if spec.evidence_only:
            assert "weights" not in node["properties"]  # no weights key, not even `{}`
        else:
            weights = node["properties"]["weights"]
            assert weights["additionalProperties"] is False
            assert list(weights["properties"]) == list(spec.axes)
            for axis, leaf in weights["properties"].items():
                assert leaf["default"] == spec.default_weights[axis]
                assert leaf["minimum"] == 0
        for setting, default in spec.extra_settings.items():
            assert node["properties"][setting]["default"] == default
            assert node["properties"][setting]["minimum"] == 1
            assert node["properties"][setting]["type"] == "integer"
        assert node["properties"]["cap"]["default"] == spec.default_cap
        assert node["properties"]["cap"]["minimum"] == 1
        has_refine_cap = "refine_cap" in node["properties"]
        assert has_refine_cap == (spec.default_refine_cap is not None)
        if has_refine_cap:
            assert node["properties"]["refine_cap"]["default"] == spec.default_refine_cap
