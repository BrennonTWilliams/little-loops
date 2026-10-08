"""``loop`` action variant: payload, key, fingerprint and command grammar (FEAT-3769)."""

from __future__ import annotations

import contextlib
import json
import shlex
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.next_arena import render
from little_loops.next_arena.actions import (
    ACTION_KEY_TABLE,
    ACTION_KEYS,
    FINGERPRINT_SCOPE_V1,
    ActionSpecError,
    LoopActionSpec,
    SlashActionSpec,
    UnknownVariantError,
    UnrepresentableAction,
    action_fingerprint,
    action_key,
    fingerprint_material,
    parse_shell,
    render_action,
    render_loop,
    slash_spec_for,
    spec_from_dict,
    spec_to_dict,
)
from tests.next_arena_support import schema_errors

DIGEST = "sha256:" + "ab" * 32
CWD = "/proj/root"


def make_spec(**overrides: Any) -> LoopActionSpec:
    fields: dict[str, Any] = {
        "target": "demo",
        "definition_source": ".loops/demo.yaml",
        "definition_digest": DIGEST,
        "fingerprint_scope": FINGERPRINT_SCOPE_V1,
        "working_directory": CWD,
    }
    fields.update(overrides)
    return LoopActionSpec(**fields)


def test_spec_dict_shape_and_round_trip() -> None:
    spec = make_spec()
    data = spec_to_dict(spec)
    assert list(data) == [
        "variant",
        "target",
        "definition_source",
        "definition_digest",
        "fingerprint_scope",
        "working_directory",
    ]
    assert data["variant"] == "loop"
    assert spec_from_dict(json.loads(json.dumps(data))) == spec


def test_action_key_is_run_loop_and_slash_table_is_unchanged() -> None:
    assert action_key(make_spec()) == "run-loop"
    assert "run-loop" in ACTION_KEYS and "run-loop" not in ACTION_KEY_TABLE
    assert len(ACTION_KEY_TABLE) == 7
    assert ACTION_KEYS == (*ACTION_KEY_TABLE, "run-loop")
    assert action_key(slash_spec_for("refine-issue", "FEAT-001", CWD)) == "refine-issue"


def test_fingerprint_material_excludes_working_directory_and_is_path_free() -> None:
    material = fingerprint_material(make_spec())
    assert list(material) == [
        "variant",
        "target",
        "definition_source",
        "definition_digest",
        "fingerprint_scope",
    ]
    assert "working_directory" not in material
    assert CWD not in json.dumps(material)


def test_relocation_with_identical_relative_sources_keeps_the_fingerprint() -> None:
    a, b = make_spec(working_directory="/a/proj"), make_spec(working_directory="/b/other/proj")
    assert action_fingerprint(a) == action_fingerprint(b)


@pytest.mark.parametrize(
    "overrides",
    [
        {"target": "other"},
        {"definition_source": ".loops/other.yaml"},
        {"definition_source": "builtin:demo.yaml"},
        {"definition_digest": "sha256:" + "cd" * 32},
    ],
)
def test_each_identity_field_changes_the_fingerprint(overrides: dict[str, str]) -> None:
    assert action_fingerprint(make_spec(**overrides)) != action_fingerprint(make_spec())


def test_pinned_fingerprint_material_and_digest_golden() -> None:
    """Independent of the projection helper: the literal canonical JSON and its SHA-256."""
    canonical = (
        '{"definition_digest":"sha256:' + "ab" * 32 + '","definition_source":".loops/demo.yaml",'
        '"fingerprint_scope":"v1/top-level-bytes","target":"demo","variant":"loop"}'
    )
    assert (
        json.dumps(fingerprint_material(make_spec()), sort_keys=True, separators=(",", ":"))
        == canonical
    )
    assert (
        action_fingerprint(make_spec())
        == "sha256:b272aab8c9265fd88118533aafbf7fd8edcb82d572263a0f32d8f5d425592374"
    )


def test_slash_fingerprints_are_unchanged_by_the_union() -> None:
    spec = slash_spec_for("manage-issue:implement", "FEAT-001", CWD)
    assert isinstance(spec, SlashActionSpec)
    assert fingerprint_material(spec) == {
        "variant": "slash",
        "command": "manage-issue",
        "args": ["feature", "implement", "FEAT-001"],
    }


@pytest.mark.parametrize(
    "target",
    ["demo", "sub/dir name", "-foo", "--json", "it's", "a b", "$HOME", "x;y", "日本"],
)
def test_render_round_trips_through_shell_grammar(target: str) -> None:
    text = render_loop(make_spec(target=target))
    parsed = parse_shell(text)
    assert parsed.prefix == ("ll-loop", "run")
    assert parsed.options == ()
    assert parsed.operands == (target,)
    assert shlex.split(text) == ["ll-loop", "run", "--", target]
    assert render_action(make_spec(target=target)) == text


def test_render_always_uses_explicit_run_and_terminator() -> None:
    assert render_loop(make_spec()) == "ll-loop run -- demo"


@pytest.mark.parametrize("target", ["demo", "-foo", "--json", "a b"])
def test_real_runner_parser_accepts_the_rendered_command(target: str) -> None:
    """Drive ``ll-loop``'s own argument parsing; the runner is replaced, never executed."""
    from little_loops.cli.loop import main_loop

    seen: list[tuple[str, Any]] = []

    def fake_cmd_run(loop_name: str, args: Any, loops_dir: Any, logger: Any) -> int:
        seen.append((loop_name, args))
        return 0

    argv = shlex.split(render_loop(make_spec(target=target)))
    with (
        patch("sys.argv", argv),
        patch("little_loops.cli.loop.run.cmd_run", fake_cmd_run),
        patch("little_loops.cli.loop.cli_event_context", lambda *a, **k: contextlib.nullcontext()),
    ):
        assert main_loop() == 0
    assert len(seen) == 1
    name, args = seen[0]
    assert name == target
    assert getattr(args, "input", None) is None
    assert not getattr(args, "context", None)


@pytest.mark.parametrize(
    "data",
    [
        {"variant": "loop"},
        {
            "variant": "loop",
            "target": "demo",
            "definition_source": ".loops/demo.yaml",
            "definition_digest": DIGEST,
            "fingerprint_scope": FINGERPRINT_SCOPE_V1,
        },  # missing working_directory
    ],
)
def test_deserialization_rejects_missing_fields(data: dict[str, Any]) -> None:
    with pytest.raises(ActionSpecError, match="keys invalid"):
        spec_from_dict(data)


def test_deserialization_rejects_extra_fields_and_foreign_keys() -> None:
    good = spec_to_dict(make_spec())
    with pytest.raises(ActionSpecError, match="unknown"):
        spec_from_dict({**good, "input": "x"})
    with pytest.raises(ActionSpecError, match="unknown"):
        spec_from_dict({**good, "context": ["k=v"]})
    with pytest.raises(ActionSpecError, match="unknown"):
        spec_from_dict({**good, "command": "x", "args": []})


@pytest.mark.parametrize(
    "key", ["target", "definition_source", "definition_digest", "fingerprint_scope"]
)
def test_deserialization_rejects_wrong_types(key: str) -> None:
    for bad in (3, None, ["x"]):
        with pytest.raises(ActionSpecError):
            spec_from_dict({**spec_to_dict(make_spec()), key: bad})


@pytest.mark.parametrize(
    "digest",
    [
        "",
        "sha256:" + "AB" * 32,  # uppercase hex
        "sha256:" + "ab" * 31,  # too short
        "sha256:" + "ab" * 33,
        "sha1:" + "ab" * 20,
        "ab" * 32,  # missing algorithm prefix
        "sha256:" + "zz" * 32,
    ],
)
def test_malformed_digest_is_rejected(digest: str) -> None:
    with pytest.raises(ActionSpecError, match="definition_digest"):
        make_spec(definition_digest=digest)


def test_unsupported_scope_is_rejected() -> None:
    with pytest.raises(ActionSpecError, match="fingerprint_scope"):
        make_spec(fingerprint_scope="v2/full-definition")


@pytest.mark.parametrize(
    "source",
    [
        "/abs/.loops/demo.yaml",
        "../outside.yaml",
        ".loops/../../outside.yaml",
        "builtin:/abs/demo.yaml",
        "builtin:../demo.yaml",
        "builtin:",
        "",
        ".loops//demo.yaml",
        "./demo.yaml",
        "C:/loops/demo.yaml",
        ".loops\\demo.yaml",
    ],
)
def test_absolute_or_traversing_source_identities_are_rejected(source: str) -> None:
    with pytest.raises(ActionSpecError, match="definition_source"):
        make_spec(definition_source=source)


def test_valid_source_identities() -> None:
    for source in (".loops/demo.yaml", "loops/sub/demo.fsm.yaml", "builtin:oracles/gate.yaml"):
        assert make_spec(definition_source=source).definition_source == source


def test_unrepresentable_target_is_rejected() -> None:
    with pytest.raises(UnrepresentableAction):
        make_spec(target="")
    with pytest.raises(UnrepresentableAction):
        make_spec(target="a\x00b")


def test_reserved_variants_still_rejected_and_unknown_variants_too() -> None:
    for variant in ("sprint", "scan"):
        with pytest.raises(UnknownVariantError, match="reserved"):
            spec_from_dict({"variant": variant})
    with pytest.raises(UnknownVariantError, match="unregistered"):
        spec_from_dict({"variant": "shell"})


def test_schema_branch_accepts_and_rejects_loop_payloads() -> None:
    schema = render.build_output_schema()
    root = schema
    action_spec = schema["$defs"]["action_spec"]
    good = spec_to_dict(make_spec())
    assert schema_errors(good, action_spec, root) == []
    assert schema_errors({**good, "extra": 1}, action_spec, root)
    assert schema_errors({**good, "definition_digest": "sha256:zz"}, action_spec, root)
    assert schema_errors({**good, "fingerprint_scope": "v2"}, action_spec, root)
    slash = spec_to_dict(slash_spec_for("refine-issue", "FEAT-001", CWD))
    assert schema_errors(slash, action_spec, root) == []
    branches = action_spec["oneOf"]
    assert [b["properties"]["variant"]["const"] for b in branches] == ["slash", "loop"]
