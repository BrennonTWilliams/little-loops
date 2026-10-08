"""Pure sprint-definition parsing, discovery and executor-state evidence (FEAT-3713 step 3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.config import BRConfig
from little_loops.next_arena.sprint_state import (
    STATE_FILENAME,
    collect_sprint_domain,
    parse_sprint_definition,
    sprint_history_names,
)
from tests.next_arena_support import make_project
from tests.sprint_support import write_sprint


def parse(name: str, text: str | bytes, ext: str = ".yaml") -> Any:
    data = text if isinstance(text, bytes) else text.encode()
    return parse_sprint_definition(
        name, Path(f"/proj/.sprints/{name}{ext}"), f".sprints/{name}{ext}", data, extension=ext
    )


def doc(name: str = "alpha", **fields: Any) -> str:
    import yaml

    return yaml.safe_dump({"name": name, "issues": ["FEAT-001"], **fields}, sort_keys=False)


# ---------------------------------------------------------------------- definition shape


def test_valid_definition_keeps_digest_of_the_parsed_bytes_and_runtime_defaults() -> None:
    data = doc().encode()
    d = parse("alpha", data)
    assert d.valid and d.exclusion is None
    assert d.digest == "sha256:" + hashlib.sha256(data).hexdigest()
    assert d.members == ("FEAT-001",)
    assert (d.options.max_iterations, d.options.timeout, d.options.max_workers) == (100, 3600, 2)
    assert d.created_raw is None  # an omitted creation date stays missing (no clock)


def test_cosmetic_yaml_edits_change_the_digest() -> None:
    a, b = parse("alpha", doc()), parse("alpha", doc() + "\n# note\n")
    assert a.valid and b.valid and a.digest != b.digest


def test_repeated_members_are_deduplicated_in_first_occurrence_order() -> None:
    text = "name: alpha\nissues: [BUG-002, FEAT-001, BUG-002, FEAT-001, ENH-003]\n"
    d = parse("alpha", text)
    assert d.members == ("BUG-002", "FEAT-001", "ENH-003")
    assert d.repeated == ("BUG-002", "FEAT-001")
    assert [x.code for x in d.diagnostics] == ["sprint_repeated_member"]


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (b"\xff\xfe", "invalid_encoding"),
        ("issues: [", "invalid_yaml"),
        ("- a\n- b\n", "definition_not_mapping"),
        ("just a string\n", "definition_not_mapping"),
        ("issues: [FEAT-001]\n", "name_mismatch"),  # missing name
        ("name: other\nissues: [FEAT-001]\n", "name_mismatch"),
        ("name: 5\nissues: [FEAT-001]\n", "name_mismatch"),
        ("name: alpha\n", "invalid_issues"),  # missing
        ("name: alpha\nissues: FEAT-001\n", "invalid_issues"),
        ("name: alpha\nissues: [feat-001]\n", "invalid_issues"),
        ("name: alpha\nissues: [FEAT-001, 7]\n", "invalid_issues"),
        ("name: alpha\nissues: [FEAT-001]\noptions: [1]\n", "invalid_options"),
        ("name: alpha\nissues: [FEAT-001]\noptions: 3\n", "invalid_options"),
    ],
)
def test_malformed_definitions_are_excluded_with_a_code_and_keep_their_digest(
    text: str | bytes, code: str
) -> None:
    d = parse("alpha", text)
    assert not d.valid and d.exclusion == code
    assert d.digest is not None and d.members == ()
    assert d.diagnostics and d.diagnostics[0].subject == "sprint:alpha"


@pytest.mark.parametrize(
    "options",
    [
        {"max_iterations": 0},
        {"max_iterations": -1},
        {"timeout": 1.5},
        {"timeout": "3600"},
        {"max_workers": True},
        {"max_workers": None},
        {"max_workers": []},
    ],
)
def test_supplied_option_values_must_be_positive_integers(options: dict[str, Any]) -> None:
    d = parse("alpha", doc(options=options))
    assert not d.valid and d.exclusion == "invalid_options"


def test_option_defaults_and_unknown_keys() -> None:
    absent = parse("alpha", doc())
    null = parse("alpha", "name: alpha\nissues: [FEAT-001]\noptions:\n")
    partial = parse("alpha", doc(options={"max_workers": 4}))
    assert null.valid and (null.options.max_iterations, null.options.max_workers) == (100, 2)
    assert (absent.options.timeout, partial.options.max_workers, partial.options.timeout) == (
        3600,
        4,
        3600,
    )
    unknown = parse("alpha", doc(options={"max_workers": 3, "colour": "red", "retries": 9}))
    assert unknown.valid and unknown.ignored_option_keys == ("colour", "retries")
    assert [d.code for d in unknown.diagnostics] == ["sprint_option_ignored"]


def test_reserved_epic_names_extensions_and_filename_stem_rules() -> None:
    for name in ("EPIC-12", "epic-3", "Epic-77"):
        d = parse(name, doc(name))
        assert not d.valid and d.exclusion == "reserved_epic_name"
    assert parse("epic-notes", doc("epic-notes")).valid  # only ^EPIC-\d+$ is reserved
    yml = parse("alpha", doc(), ".yml")
    assert not yml.valid and yml.exclusion == "unsupported_extension"


def test_definition_is_parsed_without_reading_the_clock_or_sprint_classes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import little_loops.sprint as sprint_module

    def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("SprintManager/Sprint.from_dict must not be used")

    monkeypatch.setattr(sprint_module.SprintManager, "__init__", boom)
    monkeypatch.setattr(sprint_module.Sprint, "from_dict", boom)
    assert parse("alpha", doc()).valid


# ------------------------------------------------------------------------- discovery


def collect(root: Path) -> Any:
    return collect_sprint_domain(root.resolve(), config=BRConfig(root.resolve()))


def test_discovery_reads_each_file_once_creates_nothing_and_orders_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_project(tmp_path / "p")
    write_sprint(root, "zeta", ["FEAT-001"])
    write_sprint(root, "alpha", ["FEAT-002"])
    reads: list[str] = []
    real = Path.read_bytes

    def counted(self: Path) -> bytes:
        reads.append(self.name)
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", counted)
    domain = collect(root)
    assert [d.name for d in domain.definitions] == ["alpha", "zeta"]
    assert sorted(reads) == ["alpha.yaml", "zeta.yaml"]
    assert [d.source for d in domain.definitions] == [".sprints/alpha.yaml", ".sprints/zeta.yaml"]


def test_absent_sprints_directory_is_no_definitions_and_is_not_created(tmp_path: Path) -> None:
    root = make_project(tmp_path / "p")
    domain = collect(root)
    assert domain.definitions == () and not (root / ".sprints").exists()


def test_yml_is_diagnosed_not_offered_and_shadowed_by_a_yaml(tmp_path: Path) -> None:
    root = make_project(tmp_path / "p")
    write_sprint(root, "solo", ["FEAT-001"], suffix=".yml")
    write_sprint(root, "twin", ["FEAT-001"])
    write_sprint(root, "twin", ["FEAT-002"], suffix=".yml")
    domain = collect(root)
    by_name = {d.name: d for d in domain.definitions}
    assert not by_name["solo"].valid and by_name["solo"].exclusion == "unsupported_extension"
    assert by_name["twin"].valid and by_name["twin"].members == ("FEAT-001",)
    assert [d.code for d in domain.diagnostics] == ["sprint_yml_shadowed"]


def test_malformed_sibling_does_not_disturb_valid_definitions(tmp_path: Path) -> None:
    root = make_project(tmp_path / "p")
    write_sprint(root, "good", ["FEAT-001"])
    write_sprint(root, "bad", text="name: bad\nissues: oops\n")
    domain = collect(root)
    assert {d.name: d.valid for d in domain.definitions} == {"good": True, "bad": False}
    assert sprint_history_names(domain.definitions) == ("good",)  # only valid names are batched


def test_configured_sprints_dir_is_project_relative_and_outside_dirs_are_excluded(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path / "p", config={"sprints": {"sprints_dir": "plans/sprints"}})
    write_sprint(root, "alpha", ["FEAT-001"], directory="plans/sprints")
    d = collect(root).definitions[0]
    assert d.valid and d.source == "plans/sprints/alpha.yaml"

    outside = tmp_path / "elsewhere"
    root2 = make_project(tmp_path / "q", config={"sprints": {"sprints_dir": str(outside)}})
    write_sprint(root2, "beta", ["FEAT-001"], directory=str(outside))
    domain = collect(root2)
    (beta,) = domain.definitions
    assert not beta.valid and beta.exclusion == "definition_source_outside_project"
    assert beta.source is None
    assert {x.code for x in domain.diagnostics} == {"sprint_directory_outside_project"}
    assert "sprint_source_outside_project" in {x.code for x in beta.diagnostics}


# ------------------------------------------------------------------- state evidence


def test_state_file_is_read_once_as_evidence_and_never_touched(tmp_path: Path) -> None:
    root = make_project(tmp_path / "p")
    absent = collect(root).state
    assert absent.exists is False and absent.path == str(root.resolve() / STATE_FILENAME)
    state_path = root / STATE_FILENAME
    state_path.write_text(json.dumps({"sprint_name": "other", "completed_issues": ["FEAT-001"]}))
    before = state_path.read_text()
    state = collect(root).state
    assert (state.exists, state.sprint_name, state.completed_issues) == (
        True,
        "other",
        ("FEAT-001",),
    )
    assert state_path.read_text() == before  # the arena never deletes or rewrites it
    state_path.write_text("{not json")
    broken = collect(root).state
    assert broken.exists and broken.error and broken.sprint_name is None
