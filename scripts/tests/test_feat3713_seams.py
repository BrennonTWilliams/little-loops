"""``sprint``/``scan`` action variants, registry/config/schema seams, domain rendering (FEAT-3713 step 1)."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import little_loops.next_arena.state as state_module
from little_loops.cli import main_next
from little_loops.next_arena import render
from little_loops.next_arena.actions import (
    ACTION_KEYS,
    FINGERPRINT_SCOPE_V1,
    ActionSpecError,
    ScanActionSpec,
    SprintActionSpec,
    SprintMember,
    UnrepresentableAction,
    action_fingerprint,
    action_key,
    fingerprint_material,
    parse_shell,
    render_action,
    scan_scope_hash,
    spec_from_dict,
    spec_to_dict,
)
from little_loops.next_arena.axes import AXIS_BOUNDS
from little_loops.next_arena.candidates import scan_target_key, sprint_target_key
from little_loops.next_arena.registry import REGISTRY
from tests.next_arena_candidates_support import ready_issue
from tests.next_arena_support import AS_OF, make_project, schema_errors, write_issue

CWD = "/proj"
DIGEST = "sha256:" + "ab" * 32


def make_sprint(**overrides: Any) -> SprintActionSpec:
    fields: dict[str, Any] = {
        "target": "alpha",
        "definition_source": ".sprints/alpha.yaml",
        "definition_digest": DIGEST,
        "fingerprint_scope": FINGERPRINT_SCOPE_V1,
        "working_directory": CWD,
        "members": (SprintMember("FEAT-001", "open"), SprintMember("BUG-002", "done")),
    }
    fields.update(overrides)
    return SprintActionSpec(**fields)


def make_scan(**overrides: Any) -> ScanActionSpec:
    fields: dict[str, Any] = {
        "target": "project",
        "focus_dirs": ("scripts", "src"),
        "exclude_patterns": ("**/vendor/**",),
        "working_directory": CWD,
    }
    fields.update(overrides)
    return ScanActionSpec(**fields)


# --------------------------------------------------------------------------- sprint variant


def test_sprint_spec_serializes_in_contract_order_and_round_trips() -> None:
    spec = make_sprint()
    data = spec_to_dict(spec)
    assert list(data) == [
        "variant",
        "target",
        "definition_source",
        "definition_digest",
        "fingerprint_scope",
        "working_directory",
        "members",
    ]
    assert data["members"] == [
        {"issue_id": "FEAT-001", "status": "open"},
        {"issue_id": "BUG-002", "status": "done"},
    ]
    assert spec_from_dict(json.loads(json.dumps(data))) == spec


def test_sprint_action_key_and_command_use_the_option_safe_form() -> None:
    assert action_key(make_sprint()) == "run-sprint"
    assert render_action(make_sprint()) == "ll-sprint run -- alpha"
    dash = make_sprint(target="-dash")
    shown = render_action(dash)
    assert shown == "ll-sprint run -- -dash"
    assert parse_shell(shown).operands == ("-dash",)
    quoted = make_sprint(target="has space")
    assert parse_shell(render_action(quoted)).operands == ("has space",)


def test_sprint_fingerprint_binds_definition_identity_not_members_or_directory() -> None:
    base = action_fingerprint(make_sprint())
    material = fingerprint_material(make_sprint())
    assert list(material) == [
        "variant",
        "target",
        "definition_source",
        "definition_digest",
        "fingerprint_scope",
    ]
    # a member completing / a different checkout location is the same definition identity
    assert action_fingerprint(make_sprint(members=(SprintMember("FEAT-001", "done"),))) == base
    assert action_fingerprint(make_sprint(working_directory="/elsewhere")) == base
    # an edited definition (digest), renamed source or other sprint name is a different offer
    assert action_fingerprint(make_sprint(definition_digest="sha256:" + "cd" * 32)) != base
    assert action_fingerprint(make_sprint(definition_source=".sprints/other.yaml")) != base
    assert action_fingerprint(make_sprint(target="beta")) != base


@pytest.mark.parametrize(
    "overrides",
    [
        {"definition_source": "/abs/alpha.yaml"},
        {"definition_source": "../alpha.yaml"},
        {"definition_source": "builtin:alpha.yaml"},
        {"definition_digest": "sha256:ABCD"},
        {"fingerprint_scope": "v2"},
        {"working_directory": ""},
        {"members": ("FEAT-001",)},
    ],
)
def test_sprint_spec_rejects_invalid_fields(overrides: dict[str, Any]) -> None:
    with pytest.raises(ActionSpecError):
        make_sprint(**overrides)


def test_sprint_spec_rejects_empty_or_nul_target() -> None:
    for target in ("", "a\x00b"):
        with pytest.raises(UnrepresentableAction):
            make_sprint(target=target)


def test_sprint_from_dict_requires_exact_keys_and_member_records() -> None:
    good = spec_to_dict(make_sprint())
    for key in good:
        if key == "variant":
            continue
        broken = {k: v for k, v in good.items() if k != key}
        with pytest.raises(ActionSpecError, match="missing"):
            spec_from_dict(broken)
    with pytest.raises(ActionSpecError, match="unknown"):
        spec_from_dict({**good, "extra": 1})
    with pytest.raises(ActionSpecError, match="members"):
        spec_from_dict({**good, "members": "FEAT-001"})
    with pytest.raises(ActionSpecError, match="exactly issue_id and status"):
        spec_from_dict({**good, "members": [{"issue_id": "FEAT-001"}]})
    with pytest.raises(ActionSpecError, match="exactly issue_id and status"):
        spec_from_dict({**good, "members": [{"issue_id": "FEAT-001", "status": "open", "x": 1}]})


def test_sprint_members_may_be_empty_but_are_required() -> None:
    spec = make_sprint(members=())
    assert spec_from_dict(spec_to_dict(spec)) == spec
    data = spec_to_dict(spec)
    del data["members"]
    with pytest.raises(ActionSpecError):
        spec_from_dict(data)


# ----------------------------------------------------------------------------- scan variant


def test_scan_spec_serializes_in_contract_order_and_round_trips() -> None:
    spec = make_scan()
    data = spec_to_dict(spec)
    assert list(data) == [
        "variant",
        "target",
        "focus_dirs",
        "exclude_patterns",
        "working_directory",
    ]
    assert spec_from_dict(json.loads(json.dumps(data))) == spec


def test_scan_command_is_plain_with_no_scope_argument() -> None:
    assert action_key(make_scan()) == "scan-codebase"
    assert render_action(make_scan()) == "/ll:scan-codebase"
    assert render_action(make_scan(focus_dirs=("a",), exclude_patterns=())) == "/ll:scan-codebase"


def test_scan_fingerprint_binds_scope_not_working_directory() -> None:
    base = action_fingerprint(make_scan())
    assert list(fingerprint_material(make_scan())) == [
        "variant",
        "target",
        "focus_dirs",
        "exclude_patterns",
    ]
    assert action_fingerprint(make_scan(working_directory="/elsewhere")) == base
    assert action_fingerprint(make_scan(focus_dirs=("scripts",))) != base
    assert action_fingerprint(make_scan(exclude_patterns=())) != base


@pytest.mark.parametrize(
    "overrides",
    [
        {"target": "other"},
        {"focus_dirs": ("src", "scripts")},  # not sorted
        {"focus_dirs": ("src", "src")},  # not deduplicated
        {"exclude_patterns": ("b", "a")},
        {"focus_dirs": "src"},
        {"focus_dirs": (1,)},
        {"working_directory": ""},
    ],
)
def test_scan_spec_rejects_invalid_fields(overrides: dict[str, Any]) -> None:
    with pytest.raises(ActionSpecError):
        make_scan(**overrides)


def test_scan_from_dict_requires_exact_keys() -> None:
    good = spec_to_dict(make_scan())
    with pytest.raises(ActionSpecError, match="unknown"):
        spec_from_dict({**good, "scope_hash": "x"})
    with pytest.raises(ActionSpecError, match="missing"):
        spec_from_dict({k: v for k, v in good.items() if k != "exclude_patterns"})
    with pytest.raises(ActionSpecError, match="list of strings"):
        spec_from_dict({**good, "focus_dirs": "src"})


def test_scope_hash_is_full_sha256_of_canonical_scope_and_keys_the_target() -> None:
    digest = scan_scope_hash(("scripts", "src"), ("**/vendor/**",))
    assert len(digest) == 64 and digest == digest.lower()
    assert scan_target_key(("scripts", "src"), ("**/vendor/**",)) == f"scan:{digest}"
    assert scan_scope_hash(("scripts",), ()) != scan_scope_hash((), ("scripts",))
    assert sprint_target_key("alpha") == "sprint:alpha"


# --------------------------------------------------------------------- registry/schema seams


def test_every_registered_axis_has_bounds_meeting_the_nominal_weight_property() -> None:
    for name, spec in REGISTRY.items():
        for axis in spec.axes:
            worst, best = AXIS_BOUNDS[axis]
            assert (worst / best) ** spec.default_weights[axis] >= 0.6, (name, axis)
    assert AXIS_BOUNDS["ready_share"] == (0.4, 1.0)
    assert AXIS_BOUNDS["since_last_run"] == (0.2, 1.0)
    assert AXIS_BOUNDS["priority"] == (0.2, 1.0)
    # the explicit curve floors from the issue's table at nominal weights
    assert math.isclose(0.4**0.5, 0.6325, abs_tol=1e-4)
    assert math.isclose(0.2**0.2, 0.7248, abs_tol=1e-4)
    assert math.isclose(0.2**0.3, 0.6170, abs_tol=1e-4)


def test_output_schema_admits_the_new_verbs_keys_axes_and_variants() -> None:
    schema = render.build_output_schema()
    props = schema["$defs"]["recommendation"]["properties"]
    assert {"run-sprint", "capture-issues"} <= set(props["action_type"]["enum"])
    assert {"run-sprint", "scan-codebase"} <= set(props["action_key"]["enum"])
    assert set(ACTION_KEYS) == set(props["action_key"]["enum"])
    assert {"ready_share", "since_last_run"} <= set(props["axes"]["propertyNames"]["enum"])
    branches = schema["$defs"]["action_spec"]["oneOf"]
    assert [b["properties"]["variant"]["const"] for b in branches] == [
        "slash",
        "loop",
        "sprint",
        "scan",
    ]
    assert schema["properties"]["schema_version"] == {"const": 4}
    assert render.build_feedback_schema()["properties"]["schema_version"] == {"const": 2}
    assert render.FEEDBACK_SCHEMA_VERSION == 2


def test_schema_branches_accept_valid_and_reject_malformed_sprint_and_scan_payloads() -> None:
    for schema in (render.build_output_schema(), render.build_feedback_schema()):
        union = schema["$defs"]["action_spec"]
        sprint, scan = spec_to_dict(make_sprint()), spec_to_dict(make_scan())
        assert schema_errors(sprint, union, schema) == []
        assert schema_errors(scan, union, schema) == []
        assert schema_errors({**sprint, "extra": 1}, union, schema)
        assert schema_errors({**sprint, "definition_digest": "sha256:zz"}, union, schema)
        assert schema_errors({**sprint, "members": [{"issue_id": "X"}]}, union, schema)
        assert schema_errors({k: v for k, v in sprint.items() if k != "members"}, union, schema)
        assert schema_errors({**scan, "target": "other"}, union, schema)
        assert schema_errors({**scan, "focus_dirs": "src"}, union, schema)
        assert schema_errors({**scan, "scope_hash": "x"}, union, schema)


def test_checked_in_schemas_match_the_generators() -> None:
    assert json.loads(render.output_schema_text()) == render.load_output_schema()
    assert json.loads(render.feedback_schema_text()) == render.load_feedback_schema()


# ----------------------------------------------------------------- domain rendering (explain)


def test_scope_subject_and_target_not_found_are_domain_aware() -> None:
    assert render.scope_subject("run-sprint", "alpha") == "sprint:alpha"
    assert render.scope_subject("capture-issues", "project") == "scan:project"
    assert render.scope_subject("run-loop", "daily") == "loop:daily"
    assert render.scope_subject("implement-issue", "FEAT-001") == "FEAT-001"
    sprint = render.target_not_found("alpha", "run-sprint")
    assert sprint.subject == "sprint:alpha" and "sprint definition" in sprint.message
    scan = render.target_not_found("nope", "capture-issues")
    assert scan.subject == "scan:nope" and "--explain capture-issues project" in scan.message
    for diag in (sprint, scan):
        assert "issue" not in diag.message.lower().replace("capture-issues", "")


@pytest.fixture
def proj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(state_module, "_normalize_as_of", lambda _as_of: AS_OF)
    root = make_project(tmp_path / "proj")
    write_issue(root, "features/P2-FEAT-001-impl.md", text=ready_issue())
    monkeypatch.chdir(root)
    return root.resolve()


Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Run:
    def _run(*argv: str) -> tuple[int, str, str]:
        with patch("sys.argv", ["ll-next", *argv]):
            code = main_next()
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def test_absent_sprint_target_explains_with_sprint_wording(proj: Path, run: Run) -> None:
    code, out, err = run("--explain", "run-sprint", "FEAT-001")
    assert (code, err) == (1, "")
    assert "no sprint target 'FEAT-001' for run-sprint" in out
    assert "issue target" not in out and "known issue ID" not in out
    code, out, _ = run("--json", "--explain", "run-sprint", "alpha")
    envelope = json.loads(out)
    assert code == 1 and envelope["explanation"] is None
    assert [d["subject"] for d in envelope["diagnostics"]] == ["sprint:alpha"]


def test_absent_scan_target_explains_with_scan_wording(proj: Path, run: Run) -> None:
    # the configured scope exists (even though unusable here), so only other targets are absent
    code, out, err = run("--explain", "capture-issues", "elsewhere")
    assert (code, err) == (1, "")
    assert "no scan target 'elsewhere' for capture-issues" in out
    assert "issue target" not in out and "known issue ID" not in out


@pytest.mark.parametrize(
    ("verb", "noun"), [("run-sprint", "sprint definition"), ("capture-issues", "scan scope")]
)
def test_empty_bucket_uses_the_verbs_own_domain_wording(
    proj: Path, run: Run, verb: str, noun: str
) -> None:
    code, out, err = run("--type", verb)
    assert (code, err) == (1, "")
    assert f"[empty_source] {verb}: no valid {noun}" in out or (
        f"[empty_source] {verb}: no configured {noun}" in out
    )
    assert "leaf issue" not in out


def test_uncollected_domains_leave_the_default_pass_unchanged(proj: Path, run: Run) -> None:
    code, out, _ = run("--json", "--no-record")
    envelope = json.loads(out)
    assert code == 0
    assert [r["action_type"] for r in envelope["recommendations"]] == ["implement-issue"]
    policy = envelope["selection_policy"]
    assert policy["bucket_order"] == [
        "implement-issue",
        "refine-issue",
        "resolve-blocker",
        "run-loop",
        "run-sprint",
        "capture-issues",
    ]
    assert policy["caps"]["run-sprint"] == policy["caps"]["capture-issues"] == 2
