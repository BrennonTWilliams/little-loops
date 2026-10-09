"""ll-next renderers and the generated output schema (FEAT-3561 phase E).

The checked-in ``little_loops/next_arena/output-schema.json`` is generated, not hand-edited.
Regenerate it after changing ``render.build_output_schema()`` with::

    python -m little_loops.next_arena.render --write-schema
"""

from __future__ import annotations

import copy
import json
import math
import shlex
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import little_loops.next_arena.registry as registry
from little_loops.next_arena import render
from little_loops.next_arena.actions import ACTION_KEY_TABLE, ACTION_KEYS, parse_slash
from little_loops.next_arena.candidates import assess_candidates, candidates_from_assessments
from little_loops.next_arena.inputs import Diagnostic
from little_loops.next_arena.registry import (
    ACTION_VARIANTS,
    SCHEMA_VERSION,
    VerbSpec,
    registered_verbs,
    verbs_in_domain,
)
from little_loops.next_arena.selection import bucket_order_for, select_candidates, selection_policy
from little_loops.package_data import PACKAGE_DATA_ASSETS, check_asset_accessible
from tests.next_arena_candidates_support import fake_candidate, issue, project, ready_issue
from tests.next_arena_support import AS_OF, schema_errors

SCHEMA_PATH = Path(render.__file__).with_name("output-schema.json")


def _projects(tmp_path: Path):
    return project(
        tmp_path,
        {
            "features/P2-FEAT-001-impl.md": ready_issue(),
            "bugs/P1-BUG-002-fix.md": ready_issue(),
            "enhancements/P3-ENH-003-refine.md": issue(),
            "bugs/P3-BUG-004-done.md": issue({"status": "done"}),
            "epics/P3-EPIC-005-container.md": issue(),
            "bugs/P2-BUG-006-a.md": ready_issue(),
            "bugs/P3-BUG-006-b.md": ready_issue(),
        },
    )


def _envelope(tmp_path: Path, *, top: int | None = None, explain: tuple[str, str] | None = None):
    from little_loops.next_arena.candidates import assessments_for_target, target_key_for

    state = _projects(tmp_path)
    assessments = assess_candidates(state)
    settings = state.config.next.resolve_arena_settings()
    order = bucket_order_for(None)
    policy = selection_policy(top=top, bucket_order=order, caps=settings.caps)
    if explain is not None:
        verb, target = explain
        named, alternates = assessments_for_target(assessments, target_key_for(target), verb)
        return render.build_envelope(
            project_root=state.project_root,
            as_of=state.as_of,
            selection_policy=policy,
            recording={"status": "disabled", "reason": "explain"},
            explanation=render.build_explanation(named, alternates),
            diagnostics=[] if named else [render.target_not_found(target, verb)],
        )
    selected = select_candidates(
        candidates_from_assessments(assessments),
        top=top,
        bucket_order=order,
        caps=settings.caps,
    )
    return render.build_envelope(
        project_root=state.project_root,
        as_of=state.as_of,
        selection_policy=policy,
        recording={"status": "disabled", "reason": "no_record"},
        recommendations=selected,
        diagnostics=render.collect_diagnostics(state.diagnostics, assessments, order),
    )


def _validate(envelope: Mapping[str, Any]) -> list[str]:
    schema = render.load_output_schema()
    # round-trip through the serializer so tuples/mappings become plain JSON
    return schema_errors(json.loads(render.render_json(envelope)), schema, schema)


# --------------------------------------------------------------------- schema file / drift


def test_checked_in_schema_matches_generator() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render.output_schema_text(), (
        "output-schema.json drifted; regenerate with "
        "`python -m little_loops.next_arena.render --write-schema`"
    )


def test_schema_declared_in_package_data_and_accessible() -> None:
    assert render.SCHEMA_ASSET in PACKAGE_DATA_ASSETS
    assert check_asset_accessible(render.SCHEMA_ASSET)


def test_runtime_loader_reads_the_packaged_asset() -> None:
    assert render.load_output_schema() == render.build_output_schema()


def test_write_schema_helper_regenerates_file(tmp_path: Path) -> None:
    target = render.write_output_schema(tmp_path / "out.json")
    assert target.read_text(encoding="utf-8") == render.output_schema_text()


def test_schema_enums_derive_from_the_registries() -> None:
    schema = render.build_output_schema()
    recommendation = schema["$defs"]["recommendation"]["properties"]
    assert recommendation["action_type"]["enum"] == list(registered_verbs())
    assert recommendation["action_key"]["enum"] == list(ACTION_KEYS)
    assert set(ACTION_KEYS) - set(ACTION_KEY_TABLE) == {"run-loop", "run-sprint", "scan-codebase"}
    branches = schema["$defs"]["action_spec"]["oneOf"]
    assert [b["properties"]["variant"]["const"] for b in branches] == list(ACTION_VARIANTS)
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert schema["$defs"]["selection_policy"]["properties"]["bucket_order"]["items"]["enum"] == (
        list(registered_verbs())
    )


def test_registering_a_verb_extends_the_schema_without_a_second_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extra = VerbSpec("resolve-blocker", ("priority", "blocker_depth"), {}, 2, "x")
    extended = MappingProxyType({**registry.REGISTRY, "resolve-blocker": extra})
    monkeypatch.setattr(registry, "REGISTRY", extended)
    monkeypatch.setattr(render, "REGISTRY", extended)
    schema = render.build_output_schema()
    assert (
        "resolve-blocker" in schema["$defs"]["recommendation"]["properties"]["action_type"]["enum"]
    )
    assert (
        "blocker_depth"
        in schema["$defs"]["recommendation"]["properties"]["axes"]["propertyNames"]["enum"]
    )


def test_recommendation_requires_complete_action_identity_and_assessment_does_not() -> None:
    defs = render.build_output_schema()["$defs"]
    for name in (
        "action_key",
        "action_fingerprint",
        "action_spec",
        "display_command",
        "bucket_rank",
    ):
        assert name in defs["recommendation"]["required"]
        assert "anyOf" not in defs["recommendation"]["properties"][name]
        assert "anyOf" in defs["assessment"]["properties"][name]
    assert "eligible" in defs["assessment"]["required"]
    assert "eligible" not in defs["recommendation"]["properties"]


def test_axes_are_not_sorted_in_the_schema_or_output(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)
    rec = envelope["recommendations"][0]
    spec = registry.get_verb(rec["action_type"])
    assert list(rec["axes"]) == list(spec.axes)  # canonical order, not alphabetical
    assert list(rec["axes"]) != sorted(rec["axes"])
    text = render.render_json(envelope)
    assert list(json.loads(text)["recommendations"][0]["axes"]) == list(spec.axes)


# ---------------------------------------------------------------- sample outputs validate


def test_recommendation_output_validates(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path, top=4)
    assert envelope["recommendations"] and envelope["explanation"] is None
    assert _validate(envelope) == []


@pytest.mark.parametrize(
    ("verb", "target"),
    [
        ("implement-issue", "FEAT-001"),  # recommended target
        ("refine-issue", "FEAT-001"),
        ("refine-issue", "ENH-003"),
        ("implement-issue", "BUG-004"),  # terminal
        ("refine-issue", "EPIC-005"),  # EPIC container
        ("implement-issue", "ENH-003"),  # rejected: scores absent
        ("implement-issue", "BUG-006"),  # ambiguous duplicate id
    ],
)
def test_explain_output_validates(tmp_path: Path, verb: str, target: str) -> None:
    envelope = _envelope(tmp_path, explain=(verb, target))
    assert envelope["recommendations"] == []
    assert envelope["explanation"] is not None
    assert _validate(envelope) == []
    assessment = envelope["explanation"]["assessment"]
    assert assessment["target"] == target and assessment["action_type"] == verb
    others = {a["action_type"] for a in envelope["explanation"]["alternates"]}
    # Issue verbs alternate each other; loop targets (`loop:NAME`) never share a key with them.
    assert others == set(verbs_in_domain("issue")) - {verb}


def test_excluded_assessment_has_null_action_identity(tmp_path: Path) -> None:
    assessment = _envelope(tmp_path, explain=("implement-issue", "BUG-006"))["explanation"][
        "assessment"
    ]
    assert assessment["eligible"] is False
    for key in ("action_key", "action_fingerprint", "action_spec", "display_command"):
        assert assessment[key] is None
    assert assessment["bucket_rank"] is None and assessment["utility"] is None
    assert "ambiguous_issue_id" in assessment["exclusion_reasons"]


def test_absent_target_explanation_is_null_and_validates(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path, explain=("refine-issue", "FEAT-9999"))
    assert envelope["explanation"] is None and envelope["recommendations"] == []
    assert [d["code"] for d in envelope["diagnostics"]] == ["target_not_found"]
    assert _validate(envelope) == []


def test_empty_result_validates(tmp_path: Path) -> None:
    state = project(tmp_path, {})
    assessments = assess_candidates(state)
    envelope = render.build_envelope(
        project_root=state.project_root,
        as_of=state.as_of,
        selection_policy=selection_policy(
            top=None, bucket_order=registered_verbs(), caps=dict.fromkeys(registered_verbs(), 2)
        ),
        recording={"status": "disabled", "reason": "nothing_to_record"},
        diagnostics=render.collect_diagnostics(state.diagnostics, assessments, registered_verbs()),
    )
    assert envelope["recommendations"] == [] and envelope["explanation"] is None
    assert {d["code"] for d in envelope["diagnostics"]} == {"empty_source"}
    assert _validate(envelope) == []


def test_schema_rejects_malformed_recommendations(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path, top=2)
    base = json.loads(render.render_json(envelope))
    schema = render.load_output_schema()

    def broken(mutator) -> list[str]:
        doc = copy.deepcopy(base)
        mutator(doc)
        return schema_errors(doc, schema, schema)

    assert broken(lambda d: d["recommendations"][0].update(action_spec=None))
    assert broken(lambda d: d["recommendations"][0].update(action_fingerprint=None))
    assert broken(lambda d: d["recommendations"][0].update(display_command=None))
    assert broken(lambda d: d["recommendations"][0].update(bucket_rank=None))
    assert broken(lambda d: d["recommendations"][0]["action_spec"].update(variant="loop"))
    assert broken(lambda d: d["recommendations"][0]["action_spec"].pop("variant"))
    assert broken(lambda d: d["recommendations"][0].update(action_type="bogus-verb"))
    assert broken(lambda d: d.update(schema_version=2))
    # FEAT-3711: `recording` is required on every envelope; `rec_id` is required-nullable.
    assert broken(lambda d: d.pop("recording"))
    assert broken(lambda d: d["recommendations"][0].pop("rec_id"))
    assert broken(lambda d: d["recommendations"][0].update(rec_id="not-a-uuid"))
    assert broken(lambda d: d.update(recording={"status": "recorded", "reason": "no_record"}))
    assert broken(lambda d: d.update(recording={"status": "disabled", "reason": "bogus"}))
    assert broken(lambda d: d.update(recording={"status": "unavailable", "reason": None}))
    assert broken(lambda d: d.update(as_of="2026-10-07T12:00:00Z"))
    assert broken(lambda d: d.update(explanation={"assessment": None, "alternates": []}))
    assert broken(lambda d: d.update(extra_key=1))
    assert broken(lambda d: d["recommendations"][0].update(action_fingerprint="sha256:zz"))


def test_cross_check_with_jsonschema_when_available(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = render.load_output_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    for envelope in (
        _envelope(tmp_path / "a", top=4),
        _envelope(tmp_path / "b", explain=("refine-issue", "ENH-003")),
        _envelope(tmp_path / "c", explain=("refine-issue", "FEAT-9999")),
    ):
        validator.validate(json.loads(render.render_json(envelope)))


# ------------------------------------------------------------------------ JSON strictness


def test_render_json_rejects_nan_and_infinity() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            render.render_json({"value": bad})


def test_real_output_has_no_nan_or_infinity(tmp_path: Path) -> None:
    text = render.render_json(_envelope(tmp_path, top=4))
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text, parse_constant=lambda name: pytest.fail(f"non-finite constant {name}"))


def test_envelope_key_order_and_as_of_format() -> None:
    envelope = render.build_envelope(
        project_root="/p",
        as_of=datetime(2026, 10, 7, 12, 0, 5, 999, tzinfo=UTC),
        selection_policy=selection_policy(top=None, bucket_order=("implement-issue",), caps={}),
        recording={"status": "recorded", "reason": None},
    )
    assert list(envelope) == [
        "schema_version",
        "project_root",
        "as_of",
        "selection_policy",
        "recording",
        "recommendations",
        "explanation",
        "diagnostics",
    ]
    # FEAT-3711: the envelope renders the instant at fixed microsecond precision ...
    assert envelope["as_of"] == "2026-10-07T12:00:05.000999Z"
    whole = render.build_envelope(
        project_root="/p",
        as_of=AS_OF,
        selection_policy=selection_policy(top=None, bucket_order=("implement-issue",), caps={}),
        recording={"status": "recorded", "reason": None},
    )
    assert whole["as_of"] == "2026-10-07T12:00:00.000000Z"
    # ... while the public second-precision formatter keeps its behavior for other callers.
    assert render.format_as_of(AS_OF) == "2026-10-07T12:00:00Z"


# --------------------------------------------------------------------------- diagnostics


def test_bucket_diagnostics_distinguish_empty_source_gate_failed_and_gate_missing(
    tmp_path: Path,
) -> None:
    # implement: only an unscored (missing gate) open issue and a failing-threshold one
    state = project(
        tmp_path,
        {
            "bugs/P2-BUG-001-unscored.md": issue(),
            "bugs/P2-BUG-002-low.md": issue({"confidence_score": 10, "outcome_confidence": 10}),
        },
    )
    by_code = {
        (d.code, d.subject)
        for d in render.bucket_diagnostics(assess_candidates(state), ["implement-issue"])
    }
    assert ("gate_failed", "implement-issue") in by_code
    assert ("gate_missing", "implement-issue") in by_code
    assert ("empty_source", "implement-issue") not in by_code

    empty = project(tmp_path / "empty", {"bugs/P2-BUG-009-done.md": issue({"status": "done"})})
    codes = [d.code for d in render.bucket_diagnostics(assess_candidates(empty), ["refine-issue"])]
    assert codes == ["empty_source"]


def test_collect_diagnostics_surfaces_refine_cap_and_scopes_explain(tmp_path: Path) -> None:
    from tests.next_arena_candidates_support import FORMAT_ENTRY, VERIFY_ENTRY

    sessions = [FORMAT_ENTRY, VERIFY_ENTRY] + [
        ("/ll:refine-issue", f"2026-09-0{n}T10:00:00") for n in range(3, 9)
    ]
    state = project(
        tmp_path,
        {
            "bugs/P2-BUG-001-capped.md": issue(
                {"confidence_score": 10, "outcome_confidence": 10}, sessions=sessions
            ),
            "bugs/P2-BUG-002-other.md": issue(),
        },
    )
    assessments = assess_candidates(state)
    everything = render.collect_diagnostics(state.diagnostics, assessments, ["refine-issue"])
    assert "refine_cap_exhausted" in {d.code for d in everything}
    scoped = render.collect_diagnostics(
        state.diagnostics, assessments, ["refine-issue"], scope_to="BUG-002"
    )
    assert all(d.subject == "BUG-002" for d in scoped)


# ------------------------------------------------------------------------- human output


def test_text_states_copied_actions_run_from_project_root(tmp_path: Path) -> None:
    state = _projects(tmp_path)
    assessments = assess_candidates(state)
    selected = select_candidates(
        candidates_from_assessments(assessments),
        top=None,
        bucket_order=registered_verbs(),
        caps={},
    )
    text = render.render_text(
        project_root=state.project_root, recommendations=selected, bucket_order=registered_verbs()
    )
    assert f"Project root: {state.project_root}" in text
    assert "Run copied actions from the project root" in text
    assert "never runs them" in text
    # every displayed action parses back to the spec (grammar round trip, no execution)
    for cand in selected:
        assert f"   {cand.display_command}" in text.splitlines()
        command, args = parse_slash(cand.display_command)
        assert (command, args) == (cand.action_spec.command, cand.action_spec.args)


def test_text_root_hint_shell_quotes_metacharacters() -> None:
    root = "/tmp/a b/$HOME/`x`/it's"
    text = render.render_text(project_root=root, recommendations=[], bucket_order=("refine-issue",))
    hint = next(line for line in text.splitlines() if line.startswith("Run copied actions"))
    quoted = hint.split("(cd ", 1)[1].split(");", 1)[0]
    assert shlex.split(quoted) == [root]  # literal path, no expansion
    assert "no eligible candidate across refine-issue." in text


def test_text_truncates_long_diagnostic_lists() -> None:
    diags = [Diagnostic("code", f"message {n}", (), None) for n in range(30)]
    text = render.render_text(
        project_root="/p", recommendations=[], bucket_order=("implement-issue",), diagnostics=diags
    )
    assert f"... {30 - render.DIAGNOSTIC_LIMIT_TEXT} more (use --json for all)" in text


def test_text_includes_alternates_for_selected_targets() -> None:
    cand = fake_candidate("implement-issue", "BUG-001", 1)
    text = render.render_text(
        project_root="/p", recommendations=[cand], bucket_order=("implement-issue",)
    )
    assert "1. [implement-issue] BUG-001" in text
    assert "/ll:manage-issue feature implement BUG-001" in text


def test_explain_text_for_excluded_and_absent_targets(tmp_path: Path) -> None:
    excluded = _envelope(tmp_path, explain=("implement-issue", "BUG-006"))
    text = render.render_explain_text(
        project_root="/p",
        explanation=excluded["explanation"],
        verb="implement-issue",
        target="BUG-006",
    )
    assert "eligible: no" in text and "ambiguous_issue_id" in text
    assert "alternate refine-issue:" in text
    absent = render.render_explain_text(
        project_root="/p", explanation=None, verb="refine-issue", target="NOPE-1"
    )
    assert "no issue target 'NOPE-1'" in absent
