"""Action grammar, tagged union, action_key table and fingerprints (FEAT-3561 phase A)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from little_loops.next_arena.actions import (
    ACTION_KEY_TABLE,
    ActionSpecError,
    ParsedShell,
    SlashActionSpec,
    UnknownVariantError,
    UnrepresentableAction,
    action_fingerprint,
    action_key,
    fingerprint_material,
    parse_shell,
    parse_slash,
    render_shell,
    render_slash,
    slash_spec_for,
    spec_from_dict,
    spec_to_dict,
)

CWD = "/work/project"

# (action_key, issue id, canonical fingerprint JSON, literal fingerprint, rendered slash)
GOLDENS = [
    (
        "format-issue",
        "FEAT-123",
        '{"args":["FEAT-123"],"command":"format-issue","variant":"slash"}',
        "sha256:c29606888b1415a553b682d14424dae7c242d7c0eadabffd6e515307ca85a32c",
        "/ll:format-issue FEAT-123",
    ),
    (
        "verify-issues",
        "FEAT-123",
        '{"args":["FEAT-123"],"command":"verify-issues","variant":"slash"}',
        "sha256:00e77ec9b62ec1b8513717633c1005089fd8237dd64687c2c5b7c86fb77297b8",
        "/ll:verify-issues FEAT-123",
    ),
    (
        "confidence-check",
        "FEAT-123",
        '{"args":["FEAT-123"],"command":"confidence-check","variant":"slash"}',
        "sha256:1cfa0ed4ff7369a9bd1baae238bbac701fcef55847d71503d425d4d2dd0bb900",
        "/ll:confidence-check FEAT-123",
    ),
    (
        "refine-issue",
        "FEAT-123",
        '{"args":["FEAT-123"],"command":"refine-issue","variant":"slash"}',
        "sha256:fcc77be61d5718e96b017f2d06ae1d94a2000e4f9c0b39ba47932e1adb7b5a56",
        "/ll:refine-issue FEAT-123",
    ),
    (
        "manage-issue:fix",
        "BUG-007",
        '{"args":["bug","fix","BUG-007"],"command":"manage-issue","variant":"slash"}',
        "sha256:65d064c990133a079e2b0396150f84cfb17d790a3f782c6acc1e4e2eceeb7bac",
        "/ll:manage-issue bug fix BUG-007",
    ),
    (
        "manage-issue:implement",
        "FEAT-123",
        '{"args":["feature","implement","FEAT-123"],"command":"manage-issue","variant":"slash"}',
        "sha256:fb7be9c0b746490e7e5e389cf321c19c1895cc8f36a22d153208fed2d8398edd",
        "/ll:manage-issue feature implement FEAT-123",
    ),
    (
        "manage-issue:improve",
        "ENH-045",
        '{"args":["enhancement","improve","ENH-045"],"command":"manage-issue","variant":"slash"}',
        "sha256:e249c6896b8278b81d5aed563aff00d990eccffb6d8bcdbab745e78b38385b68",
        "/ll:manage-issue enhancement improve ENH-045",
    ),
]


class TestActionKeyTable:
    def test_exactly_seven_rows_in_documented_order(self) -> None:
        assert list(ACTION_KEY_TABLE) == [g[0] for g in GOLDENS]
        assert len(ACTION_KEY_TABLE) == 7

    @pytest.mark.parametrize(("key", "issue_id", "_material", "_fp", "rendered"), GOLDENS)
    def test_projection_round_trips(
        self, key: str, issue_id: str, _material: str, _fp: str, rendered: str
    ) -> None:
        spec = slash_spec_for(key, issue_id, CWD)
        assert action_key(spec) == key
        assert render_slash(spec) == rendered
        assert spec.args[-1] == issue_id

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ActionSpecError):
            slash_spec_for("manage-issue:delete", "BUG-1", CWD)

    def test_unprojectable_spec_rejected(self) -> None:
        with pytest.raises(ActionSpecError):
            action_key(SlashActionSpec("manage-issue", ("bug", "implement", "BUG-1"), CWD))
        with pytest.raises(ActionSpecError):
            action_key(SlashActionSpec("format-issue", (), CWD))


class TestFingerprintGoldens:
    @pytest.mark.parametrize(("key", "issue_id", "material", "fingerprint", "_r"), GOLDENS)
    def test_literal_golden_hex(
        self, key: str, issue_id: str, material: str, fingerprint: str, _r: str
    ) -> None:
        spec = slash_spec_for(key, issue_id, CWD)
        assert action_fingerprint(spec) == fingerprint
        # The pinned literal is the sha256 of the pinned canonical JSON, independently.
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        assert fingerprint == "sha256:" + digest
        assert json.loads(material) == fingerprint_material(spec)

    def test_material_is_host_neutral_and_path_free(self) -> None:
        spec = slash_spec_for("manage-issue:implement", "FEAT-1", CWD)
        material = fingerprint_material(spec)
        assert set(material) == {"variant", "command", "args"}
        assert "/ll:" not in json.dumps(material)
        assert CWD not in json.dumps(material)

    def test_working_directory_excluded(self) -> None:
        a = slash_spec_for("refine-issue", "FEAT-1", "/one/checkout")
        b = slash_spec_for("refine-issue", "FEAT-1", "/moved/elsewhere")
        assert a != b
        assert action_fingerprint(a) == action_fingerprint(b)

    def test_parameter_changes_change_fingerprint(self) -> None:
        base = slash_spec_for("refine-issue", "FEAT-1", CWD)
        assert action_fingerprint(base) != action_fingerprint(
            slash_spec_for("refine-issue", "FEAT-2", CWD)
        )
        assert action_fingerprint(base) != action_fingerprint(
            slash_spec_for("format-issue", "FEAT-1", CWD)
        )
        # Positional order is meaningful.
        assert action_fingerprint(SlashActionSpec("x", ("a", "b"), CWD)) != action_fingerprint(
            SlashActionSpec("x", ("b", "a"), CWD)
        )

    def test_fingerprints_distinct_across_rows(self) -> None:
        assert len({g[3] for g in GOLDENS}) == 7


class TestSlashGrammar:
    @pytest.mark.parametrize(("key", "issue_id", "_m", "_fp", "rendered"), GOLDENS)
    def test_render_parse_round_trip(
        self, key: str, issue_id: str, _m: str, _fp: str, rendered: str
    ) -> None:
        spec = slash_spec_for(key, issue_id, CWD)
        command, args = parse_slash(render_slash(spec))
        assert (command, args) == (spec.command, spec.args)
        assert rendered == render_slash(SlashActionSpec(command, args, CWD))

    def test_bare_command_round_trip(self) -> None:
        spec = SlashActionSpec("help", (), CWD)
        assert render_slash(spec) == "/ll:help"
        assert parse_slash("/ll:help") == ("help", ())

    @pytest.mark.parametrize(
        "token",
        [
            "-x",
            "--force",
            "a b",
            "",
            " lead",
            "trail ",
            'q"uote',
            "it's",
            "a$b",
            "a`b`",
            "a;b",
            "é",
            "a\nb",
            "_x",
            ".x",
        ],
    )
    def test_unrepresentable_tokens_raise(self, token: str) -> None:
        with pytest.raises(UnrepresentableAction):
            SlashActionSpec("refine-issue", (token,), CWD)
        with pytest.raises(UnrepresentableAction):
            SlashActionSpec(token, (), CWD)

    def test_unrepresentable_is_an_action_spec_error(self) -> None:
        assert issubclass(UnrepresentableAction, ActionSpecError)
        assert issubclass(ActionSpecError, ValueError)

    @pytest.mark.parametrize(
        "text",
        [
            "ll:help x",
            "/help x",
            "/ll:",
            "/ll: x",
            "/ll:help  x",
            "/ll:help -x",
            "/ll:help 'a b'",
            "/ll:help x ",
        ],
    )
    def test_parse_rejects_non_grammar(self, text: str) -> None:
        with pytest.raises(UnrepresentableAction):
            parse_slash(text)

    def test_valid_punctuated_tokens_allowed(self) -> None:
        spec = SlashActionSpec("a.b", ("x_y", "p:q", "v1.2-rc", "0"), CWD)
        assert parse_slash(render_slash(spec)) == ("a.b", ("x_y", "p:q", "v1.2-rc", "0"))

    def test_args_coerced_to_tuple(self) -> None:
        spec = SlashActionSpec("x", ["a", "b"], CWD)  # type: ignore[arg-type]
        assert spec.args == ("a", "b")
        hash(spec)


class TestShellArgv:
    @pytest.mark.parametrize(
        "operand",
        [
            "plain",
            "has space",
            "it's",
            'dq"uote',
            "$HOME",
            "$(whoami)",
            "`id`",
            "a;b && c",
            "-leading-dash",
            "--flag",
            "-",
            "--",
            "",
            "multi\nline",
            "tab\there",
            "*.md",
            "~user",
            "unicodé",
        ],
    )
    def test_operand_round_trips_literally(self, operand: str) -> None:
        text = render_shell(["ll-issues", "show"], ["--json"], ["FEAT-1", operand, "tail"])
        assert parse_shell(text) == ParsedShell(
            ("ll-issues", "show"), ("--json",), ("FEAT-1", operand, "tail")
        )

    def test_dash_operands_land_after_terminator(self) -> None:
        text = render_shell(["tool"], ["--type", "x"], ["-rf", "--help"])
        assert text == "tool --type x -- -rf --help"
        assert parse_shell(text).operands == ("-rf", "--help")

    def test_dangerous_text_is_quoted_not_executed(self) -> None:
        text = render_shell(["tool"], (), ["$(touch /tmp/pwned)", "`id`", "a b"])
        assert text == "tool -- '$(touch /tmp/pwned)' '`id`' 'a b'"
        assert parse_shell(text).operands == ("$(touch /tmp/pwned)", "`id`", "a b")

    def test_no_operands_omits_terminator(self) -> None:
        text = render_shell(["ll-next"], ["--json", "--top", "3"])
        assert text == "ll-next --json --top 3"
        assert parse_shell(text) == ParsedShell(("ll-next",), ("--json", "--top", "3"), ())

    def test_option_values_with_spaces_and_dashes(self) -> None:
        text = render_shell(["tool"], ["--name", "a b", "--delta", "-1"], ["x"])
        assert parse_shell(text) == ParsedShell(
            ("tool",), ("--name", "a b", "--delta", "-1"), ("x",)
        )

    def test_prefix_only(self) -> None:
        assert parse_shell(render_shell(["ll-loop", "run", "name"])) == ParsedShell(
            ("ll-loop", "run", "name"), (), ()
        )

    @pytest.mark.parametrize(
        ("prefix", "options", "operands"),
        [
            ([], [], []),
            (["-x"], [], []),
            (["tool", "--sneaky"], [], []),
            (["tool"], ["value-first"], []),
            (["tool"], ["--a", "--", "--b"], []),
        ],
    )
    def test_unrepresentable_shapes_raise(
        self, prefix: list[str], options: list[str], operands: list[str]
    ) -> None:
        with pytest.raises(UnrepresentableAction):
            render_shell(prefix, options, operands)


class TestTaggedUnion:
    def test_to_dict_shape(self) -> None:
        spec = slash_spec_for("manage-issue:fix", "BUG-007", CWD)
        data = spec_to_dict(spec)
        assert list(data) == ["variant", "command", "args", "working_directory"]
        assert data == {
            "variant": "slash",
            "command": "manage-issue",
            "args": ["bug", "fix", "BUG-007"],
            "working_directory": CWD,
        }
        json.dumps(data)

    @pytest.mark.parametrize(("key", "issue_id", "_m", "_fp", "_r"), GOLDENS)
    def test_dict_round_trip(self, key: str, issue_id: str, _m: str, _fp: str, _r: str) -> None:
        spec = slash_spec_for(key, issue_id, CWD)
        assert spec_from_dict(spec_to_dict(spec)) == spec

    @pytest.mark.parametrize("variant", ["sprint", "scan"])
    def test_sprint_scan_variants_registered_with_their_own_shapes(self, variant: str) -> None:
        # FEAT-3713 registered the former reserved names: a slash-shaped payload is a shape
        # error for the named variant, not an unknown/reserved variant.
        with pytest.raises(ActionSpecError, match=f"{variant} action_spec keys invalid"):
            spec_from_dict(
                {"variant": variant, "command": "x", "args": [], "working_directory": "/"}
            )

    @pytest.mark.parametrize("variant", ["shell", "Slash", "", "capture"])
    def test_unregistered_variants_rejected(self, variant: str) -> None:
        with pytest.raises(UnknownVariantError, match="unregistered"):
            spec_from_dict(
                {"variant": variant, "command": "x", "args": [], "working_directory": "/"}
            )

    @pytest.mark.parametrize("data", [{}, {"variant": None}, {"variant": 3}, {"command": "x"}])
    def test_missing_or_non_string_variant_rejected(self, data: dict[str, Any]) -> None:
        with pytest.raises(UnknownVariantError):
            spec_from_dict(data)

    @pytest.mark.parametrize(
        "data",
        [
            {"variant": "slash", "command": "x", "args": []},
            {"variant": "slash", "command": "x", "args": [], "working_directory": "/", "extra": 1},
            {"variant": "slash", "command": "x", "args": "ab", "working_directory": "/"},
            {"variant": "slash", "command": "x", "args": [1], "working_directory": "/"},
            {"variant": "slash", "command": 1, "args": [], "working_directory": "/"},
            {"variant": "slash", "command": "x", "args": [], "working_directory": None},
        ],
    )
    def test_invalid_slash_payloads_rejected(self, data: dict[str, Any]) -> None:
        with pytest.raises(ActionSpecError):
            spec_from_dict(data)

    def test_unrepresentable_token_payload_rejected(self) -> None:
        with pytest.raises(UnrepresentableAction):
            spec_from_dict(
                {"variant": "slash", "command": "x", "args": ["--evil"], "working_directory": "/"}
            )

    def test_non_mapping_rejected(self) -> None:
        with pytest.raises(ActionSpecError):
            spec_from_dict([])  # type: ignore[arg-type]

    def test_variant_names_come_from_registry(self) -> None:
        from little_loops.next_arena.registry import ACTION_VARIANTS

        assert SlashActionSpec.variant in ACTION_VARIANTS
