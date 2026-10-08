"""``next.verbs`` arena config resolution (FEAT-3561 phase A)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.config import ArenaSettings, BRConfig, NextConfig, NextConfigError
from little_loops.next_arena.registry import REGISTRY

IMPLEMENT = {"priority": 0.30, "outcome": 0.30, "leverage": 0.20, "effort": 0.10, "momentum": 0.10}
REFINE = {
    "priority": 0.30,
    "readiness_gap": 0.30,
    "leverage": 0.15,
    "staleness": 0.15,
    "momentum": 0.10,
}
BLOCKER = {"priority": 0.25, "leverage": 0.50, "effort": 0.15, "staleness": 0.05, "momentum": 0.05}
RUN_LOOP = {"frequency": 0.50, "recency": 0.30, "success": 0.20}
ALL_CAPS = {"implement-issue": 2, "refine-issue": 2, "resolve-blocker": 2, "run-loop": 2}


def _project(root: Path, base: dict[str, Any] | None = None, local: str | None = None) -> Path:
    (root / ".ll").mkdir(parents=True, exist_ok=True)
    cfg = {"project": {"name": "t"}}
    cfg.update(base or {})
    (root / ".ll" / "ll-config.json").write_text(json.dumps(cfg))
    if local is not None:
        (root / ".ll" / "ll.local.md").write_text(f"---\n{local}\n---\n")
    return root


def _arena(next_value: Any) -> ArenaSettings:
    return NextConfig(present=True, raw=next_value).resolve_arena_settings()


class TestDefaults:
    def test_absent_next_yields_registry_defaults(self, tmp_path: Path) -> None:
        settings = BRConfig(_project(tmp_path)).next.resolve_arena_settings()
        assert dict(settings.weights["implement-issue"]) == IMPLEMENT
        assert dict(settings.weights["refine-issue"]) == REFINE
        assert dict(settings.weights["resolve-blocker"]) == BLOCKER
        assert dict(settings.weights["run-loop"]) == RUN_LOOP
        assert dict(settings.caps) == ALL_CAPS
        assert settings.refine_cap == 5

    def test_settings_are_frozen_and_immutable(self) -> None:
        settings = NextConfig().resolve_arena_settings()
        with pytest.raises(AttributeError):
            settings.refine_cap = 9  # type: ignore[misc]
        with pytest.raises(TypeError):
            settings.weights["implement-issue"]["priority"] = 1.0  # type: ignore[index]

    @pytest.mark.parametrize(
        "value",
        [
            {},
            {"verbs": {}},
            {"verbs": {"implement-issue": {}}},
            {"verbs": {"refine-issue": {"weights": {}}}},
        ],
    )
    def test_empty_levels_resolve_to_defaults(self, value: dict[str, Any]) -> None:
        settings = _arena(value)
        assert dict(settings.weights["implement-issue"]) == IMPLEMENT
        assert settings.refine_cap == 5

    def test_to_dict_unchanged_when_next_absent(self, tmp_path: Path) -> None:
        cfg = BRConfig(_project(tmp_path))
        assert cfg.next.to_dict() == {
            "loop_history": {"weights": {"frequency": 0.5, "recency": 0.3, "success": 0.2}}
        }


class TestOverrides:
    def test_partial_weights_fill_defaults_in_canonical_order(self) -> None:
        settings = _arena(
            {"verbs": {"implement-issue": {"weights": {"momentum": 0.5, "priority": 1}}}}
        )
        weights = settings.weights["implement-issue"]
        assert list(weights) == list(REGISTRY["implement-issue"].axes)
        assert weights == {**IMPLEMENT, "momentum": 0.5, "priority": 1.0}

    def test_reordered_config_objects_give_identical_ordered_mappings(self) -> None:
        a = {
            "verbs": {
                "refine-issue": {"refine_cap": 3, "weights": {"momentum": 1, "priority": 2}},
                "implement-issue": {"cap": 4, "weights": {"effort": 0.5, "outcome": 0.1}},
            }
        }
        b = {
            "verbs": {
                "implement-issue": {"weights": {"outcome": 0.1, "effort": 0.5}, "cap": 4},
                "refine-issue": {"weights": {"priority": 2, "momentum": 1}, "refine_cap": 3},
            }
        }
        first, second = _arena(a), _arena(b)
        assert first == second
        assert list(first.weights) == list(REGISTRY)
        for verb in first.weights:
            assert list(first.weights[verb]) == list(second.weights[verb])
            assert list(first.weights[verb]) == list(REGISTRY[verb].axes)

    def test_caps_override(self) -> None:
        settings = _arena(
            {"verbs": {"implement-issue": {"cap": 7}, "refine-issue": {"cap": 1, "refine_cap": 9}}}
        )
        assert dict(settings.caps) == {**ALL_CAPS, "implement-issue": 7, "refine-issue": 1}
        assert settings.refine_cap == 9

    def test_new_verbs_are_tunable_through_next_verbs(self) -> None:
        settings = _arena(
            {
                "verbs": {
                    "run-loop": {"cap": 3, "weights": {"success": 1, "frequency": 0}},
                    "resolve-blocker": {"weights": {"leverage": 1}},
                }
            }
        )
        assert settings.caps["run-loop"] == 3
        assert dict(settings.weights["run-loop"]) == {**RUN_LOOP, "frequency": 0.0, "success": 1.0}
        assert list(settings.weights["run-loop"]) == ["frequency", "recency", "success"]
        assert settings.weights["resolve-blocker"]["leverage"] == 1.0

    def test_zero_weight_disables_axis_but_is_valid(self) -> None:
        settings = _arena({"verbs": {"implement-issue": {"weights": {"priority": 0}}}})
        assert settings.weights["implement-issue"]["priority"] == 0.0

    def test_local_override_merges_per_key(self, tmp_path: Path) -> None:
        base = {"next": {"verbs": {"implement-issue": {"cap": 3, "weights": {"effort": 0.4}}}}}
        local = "next:\n  verbs:\n    implement-issue:\n      weights:\n        momentum: 0.9"
        settings = BRConfig(_project(tmp_path, base, local)).next.resolve_arena_settings()
        assert settings.caps["implement-issue"] == 3
        assert settings.weights["implement-issue"]["effort"] == 0.4
        assert settings.weights["implement-issue"]["momentum"] == 0.9

    def test_local_null_resets_leaf_to_default(self, tmp_path: Path) -> None:
        base = {"next": {"verbs": {"implement-issue": {"cap": 3, "weights": {"effort": 0.4}}}}}
        local = "next:\n  verbs:\n    implement-issue:\n      cap: null\n      weights:\n        effort: null"
        settings = BRConfig(_project(tmp_path, base, local)).next.resolve_arena_settings()
        assert settings.caps["implement-issue"] == 2
        assert settings.weights["implement-issue"]["effort"] == 0.10

    def test_local_null_removes_whole_verbs_subtree(self, tmp_path: Path) -> None:
        base = {"next": {"verbs": {"implement-issue": {"cap": 3}}}}
        settings = BRConfig(_project(tmp_path, base, "next:\n  verbs: null")).next
        assert settings.resolve_arena_settings().caps["implement-issue"] == 2

    def test_resolution_is_pure(self) -> None:
        raw = {"verbs": {"implement-issue": {"cap": 3}}}
        cfg = NextConfig(present=True, raw=raw)
        cfg.resolve_arena_settings()
        assert raw == {"verbs": {"implement-issue": {"cap": 3}}}


class TestInvalid:
    @pytest.mark.parametrize(
        ("raw", "needle"),
        [
            (None, "next must be a mapping, got null"),
            ({"bogus": 1}, "next has unknown keys: 'bogus'"),
            ({"verbs": None}, "next.verbs must be a mapping, got null"),
            ({"verbs": []}, "next.verbs must be a mapping, got list"),
            ({"verbs": {"run-sprint": {}}}, "next.verbs has unknown keys: 'run-sprint'"),
            (
                {"verbs": {"run-loop": {"weights": {"priority": 1}}}},
                "next.verbs.run-loop.weights has unknown keys: 'priority'",
            ),
            (
                {"verbs": {"resolve-blocker": {"refine_cap": 3}}},
                "next.verbs.resolve-blocker has unknown keys: 'refine_cap'",
            ),
            (
                {"verbs": {"run-loop": {"weights": dict.fromkeys(RUN_LOOP, 0)}}},
                "next.verbs.run-loop.weights: at least one weight must be nonzero",
            ),
            ({"verbs": {"nope": {}}}, "next.verbs has unknown keys: 'nope'"),
            ({"verbs": {"implement-issue": None}}, "next.verbs.implement-issue must be a mapping"),
            (
                {"verbs": {"implement-issue": {"refine_cap": 3}}},
                "next.verbs.implement-issue has unknown keys: 'refine_cap'",
            ),
            (
                {"verbs": {"implement-issue": {"weights": {"staleness": 1}}}},
                "next.verbs.implement-issue.weights has unknown keys: 'staleness'",
            ),
            (
                {"verbs": {"implement-issue": {"weights": 1}}},
                "next.verbs.implement-issue.weights must be a mapping",
            ),
            (
                {"verbs": {"implement-issue": {"weights": {"priority": True}}}},
                "weights.priority must be a number",
            ),
            (
                {"verbs": {"implement-issue": {"weights": {"priority": "0.3"}}}},
                "weights.priority must be a number",
            ),
            (
                {"verbs": {"implement-issue": {"weights": {"priority": -0.1}}}},
                "weights.priority must be a finite number >= 0",
            ),
            (
                {"verbs": {"implement-issue": {"weights": {"priority": float("nan")}}}},
                "weights.priority must be a finite number",
            ),
            (
                {"verbs": {"implement-issue": {"weights": {"priority": float("inf")}}}},
                "weights.priority must be a finite number",
            ),
            (
                {"verbs": {"implement-issue": {"weights": {"priority": 10**400}}}},
                "weights.priority is too large",
            ),
            (
                {"verbs": {"implement-issue": {"weights": dict.fromkeys(IMPLEMENT, 0)}}},
                "next.verbs.implement-issue.weights: at least one weight must be nonzero",
            ),
            (
                {"verbs": {"refine-issue": {"weights": dict.fromkeys(REFINE, 0)}}},
                "next.verbs.refine-issue.weights: at least one weight must be nonzero",
            ),
            ({"verbs": {"implement-issue": {"cap": 0}}}, "cap must be a positive integer"),
            ({"verbs": {"implement-issue": {"cap": -1}}}, "cap must be a positive integer"),
            ({"verbs": {"implement-issue": {"cap": True}}}, "cap must be a positive integer"),
            ({"verbs": {"implement-issue": {"cap": 1.5}}}, "cap must be a positive integer"),
            ({"verbs": {"implement-issue": {"cap": "2"}}}, "cap must be a positive integer"),
            ({"verbs": {"implement-issue": {"cap": None}}}, "cap must be a positive integer"),
            ({"verbs": {"refine-issue": {"refine_cap": 0}}}, "refine_cap must be a positive"),
            ({"verbs": {"refine-issue": {"refine_cap": False}}}, "refine_cap must be a positive"),
        ],
    )
    def test_invalid_shapes_raise_setting_naming_error(self, raw: Any, needle: str) -> None:
        with pytest.raises(NextConfigError, match=needle):
            NextConfig(present=True, raw=raw).resolve_arena_settings()

    def test_construction_stays_lazy(self, tmp_path: Path) -> None:
        cfg = BRConfig(_project(tmp_path, {"next": {"verbs": {"implement-issue": {"cap": 0}}}}))
        assert cfg.to_dict()["next"] == {"verbs": {"implement-issue": {"cap": 0}}}
        with pytest.raises(NextConfigError):
            cfg.next.resolve_arena_settings()


class TestConsumerIsolation:
    def test_legacy_resolver_tolerates_invalid_arena_siblings(self) -> None:
        raw = {
            "loop_history": {"weights": {"recency": 0.9}},
            "verbs": {"implement-issue": {"cap": -5, "weights": {"bogus": "x"}}},
        }
        weights = NextConfig(present=True, raw=raw).resolve_loop_history_weights()
        assert weights == {"frequency": 0.5, "recency": 0.9, "success": 0.2}

    def test_legacy_resolver_tolerates_non_mapping_verbs(self) -> None:
        raw = {"verbs": 5}
        assert NextConfig(present=True, raw=raw).resolve_loop_history_weights()["recency"] == 0.3

    def test_arena_resolver_does_not_validate_loop_history(self) -> None:
        raw = {
            "loop_history": {"weights": {"recency": -1, "speed": "fast"}, "curve": 1},
            "verbs": {"implement-issue": {"cap": 5}},
        }
        settings = NextConfig(present=True, raw=raw).resolve_arena_settings()
        assert settings.caps["implement-issue"] == 5

    def test_legacy_loop_history_and_run_loop_weights_are_independent(self) -> None:
        raw = {
            "loop_history": {"weights": {"recency": 0.9}},
            "verbs": {"run-loop": {"weights": {"recency": 0.1}}},
        }
        cfg = NextConfig(present=True, raw=raw)
        assert cfg.resolve_loop_history_weights()["recency"] == 0.9
        assert cfg.resolve_arena_settings().weights["run-loop"]["recency"] == 0.1

    def test_legacy_resolver_tolerates_invalid_run_loop_weights(self) -> None:
        raw = {"verbs": {"run-loop": {"weights": {"recency": -1}}}}
        assert NextConfig(present=True, raw=raw).resolve_loop_history_weights()["recency"] == 0.3

    def test_arena_resolver_does_not_validate_non_mapping_loop_history(self) -> None:
        assert _arena({"loop_history": 5}).refine_cap == 5

    @pytest.mark.parametrize("method", ["resolve_loop_history_weights", "resolve_arena_settings"])
    def test_unknown_root_key_fails_at_both_consumers(self, method: str) -> None:
        cfg = NextConfig(present=True, raw={"verbs": {}, "loop_history": {}, "extra": 1})
        with pytest.raises(NextConfigError, match="next has unknown keys: 'extra'"):
            getattr(cfg, method)()

    @pytest.mark.parametrize("method", ["resolve_loop_history_weights", "resolve_arena_settings"])
    def test_non_mapping_root_fails_at_both_consumers(self, method: str) -> None:
        with pytest.raises(NextConfigError, match="next must be a mapping"):
            getattr(NextConfig(present=True, raw=[]), method)()

    def test_bad_verbs_do_not_break_other_command_construction(self, tmp_path: Path) -> None:
        cfg = BRConfig(_project(tmp_path, {"next": {"verbs": 5}}))
        assert cfg.project.name == "t"
