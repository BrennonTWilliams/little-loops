"""Loop-domain collection: discovery, captured loading, resolution, preflight, history (FEAT-3769)."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest

import little_loops.next_arena.loop_state as loop_state_module
from little_loops.config import BRConfig
from little_loops.fsm.loop_paths import resolution_context, resolve_loop_path
from little_loops.fsm.validation import load_and_validate
from little_loops.next_arena.loop_state import (
    KIND_BUILTIN,
    KIND_DRAFT,
    KIND_PROJECT,
    collect_loop_definitions,
    collect_loop_history,
    collect_loop_inputs,
    collect_loop_sources,
    resolve_target,
    zero_argument_context,
)
from tests.next_arena_loop_support import (
    completed_run,
    isolate_builtins,
    loop_project,
    loop_state,
    loop_yaml,
    write_loop,
    write_run,
)
from tests.next_arena_support import AS_OF


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    isolate_builtins(monkeypatch, tmp_path / "builtin-loops")
    return loop_project(tmp_path / "proj")


def by_target(records: Any) -> dict[str, Any]:
    return {r.target: r for r in records}


def collect(root: Path) -> dict[str, Any]:
    return by_target(collect_loop_definitions(root, config=BRConfig(root)))


# --------------------------------------------------------------------------- discovery


def test_discovery_uses_catalog_shapes_and_canonical_targets(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builtin = tmp_path / "builtin-loops"
    (builtin / "oracles").mkdir(parents=True)
    (builtin / "oracles" / "gate.yaml").write_text(loop_yaml("gate"))
    (builtin / "lib").mkdir()
    (builtin / "lib" / "fragments.yaml").write_text("fragments:\n  f:\n    action: echo\n")
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    write_loop(root, "compiled.fsm.yaml", loop_yaml("compiled"))
    write_loop(root, "group/nested.yaml", loop_yaml("nested"))
    write_loop(root, "runs/inst-1/workflow.yaml", loop_yaml("generated-name"))
    write_loop(root, "runs/inst-1/other.yaml", loop_yaml("probe"))  # not a draft shape
    write_loop(root, "runs/inst-1/deeper/workflow.yaml", loop_yaml("deep"))
    write_loop(root, ".history/x/workflow.yaml", loop_yaml("hidden"))
    write_loop(root, "lib/shared.yaml", "fragments:\n  g:\n    action: echo\n")
    write_loop(root, "notes.yaml", "- just\n- a list\n")
    write_loop(root, "readme.txt", "not yaml")
    records = collect(root)
    assert sorted(records) == [
        "alpha",
        "compiled",
        "group/nested",
        "inst-1",
        "oracles/gate",
    ]
    assert records["alpha"].kind == records["compiled"].kind == KIND_PROJECT
    assert records["oracles/gate"].kind == KIND_BUILTIN
    assert records["inst-1"].kind == KIND_DRAFT
    assert records["inst-1"].draft_folder == "inst-1"
    assert records["inst-1"].draft_internal_name == "generated-name"
    assert records["inst-1"].logical_name == "generated-name"
    assert records["alpha"].source == ".loops/alpha.yaml"
    assert records["compiled"].source == ".loops/compiled.fsm.yaml"
    assert records["inst-1"].source == ".loops/runs/inst-1/workflow.yaml"
    assert records["oracles/gate"].source == "builtin:oracles/gate.yaml"


def test_digest_is_the_sha256_of_the_captured_top_level_bytes(root: Path) -> None:
    text = loop_yaml("alpha")
    path = write_loop(root, "alpha.yaml", text)
    record = collect(root)["alpha"]
    assert record.digest == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert record.valid and record.logical_name == "alpha"


def test_each_top_level_source_is_read_once_and_loaded_from_that_buffer(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("a", "b", "c"):
        write_loop(root, f"{name}.yaml", loop_yaml(name))
    reads: list[Path] = []
    real = loop_state_module._read_bytes

    def counting(path: Path) -> bytes:
        reads.append(path)
        return real(path)

    monkeypatch.setattr(loop_state_module, "_read_bytes", counting)
    loads: list[tuple[Path, bool]] = []
    import little_loops.fsm.validation as validation

    real_load = validation.load_and_validate

    def spying(path: Path, *args: Any, **kwargs: Any) -> Any:
        loads.append((path, kwargs.get("source_data") is not None))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(validation, "load_and_validate", spying)
    collect(root)
    assert sorted(p.name for p in reads) == ["a.yaml", "b.yaml", "c.yaml"]
    assert len(reads) == len(set(reads))
    top = [(p, captured) for p, captured in loads if p.parent == root / ".loops"]
    assert len(top) == 3 and all(captured for _p, captured in top)


def test_replacement_after_capture_cannot_mix_definitions(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_loop(root, "alpha.yaml", loop_yaml("original"))
    original = path.read_bytes()
    real = loop_state_module._read_bytes

    def swap_after_read(p: Path) -> bytes:
        data = real(p)
        p.write_text(loop_yaml("replacement"), encoding="utf-8")  # concurrent edit
        return data

    monkeypatch.setattr(loop_state_module, "_read_bytes", swap_after_read)
    record = collect(root)["alpha"]
    assert record.logical_name == "original"
    assert record.digest == "sha256:" + hashlib.sha256(original).hexdigest()


# ---------------------------------------------------------------- validation and exclusions


def test_validation_warnings_become_diagnostics_not_output(
    root: Path, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    # No ``scope:`` -> a WARNING-severity violation (raise_on_error=True would log it).
    write_loop(root, "warny.yaml", "name: warny\ninitial: go\nstates:\n  go:\n    terminal: true\n")
    with caplog.at_level(logging.DEBUG):
        record = collect(root)["warny"]
    out, err = capfd.readouterr()
    assert (out, err) == ("", "")
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert record.valid
    codes = {d.code for d in record.diagnostics}
    assert codes == {"loop_validation_warning"}
    assert all(d.subject == "loop:warny" for d in record.diagnostics)


def test_error_severity_violation_means_invalid_and_stays_explainable(root: Path) -> None:
    bad = "name: bad\ninitial: nowhere\nscope: ['.']\nstates:\n  go:\n    terminal: true\n"
    write_loop(root, "bad.yaml", bad)
    record = collect(root)["bad"]
    assert not record.valid and record.exclusion == "validation_error"
    assert record.errors and "nowhere" in record.exclusion_detail
    assert record.digest and record.logical_name == "bad"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("name: x\ninitial: go\nstates: [unbalanced\n", "yaml_error"),
        ("name: x\nfrom: missing-parent\n", "load_error"),
    ],
)
def test_per_definition_failures_are_contained(root: Path, text: str, code: str) -> None:
    write_loop(root, "broken.yaml", text)
    write_loop(root, "healthy.yaml", loop_yaml("healthy"))
    records = collect(root)
    assert records["healthy"].valid
    assert not records["broken"].valid and records["broken"].exclusion == code


def test_undecodable_and_unreadable_sources_are_explainable_exclusions(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / ".loops").mkdir(exist_ok=True)
    (root / ".loops" / "latin.yaml").write_bytes(b"name: \xff\xfe broken\n")
    write_loop(root, "locked.yaml", loop_yaml("locked"))
    real = loop_state_module._read_bytes

    def flaky(path: Path) -> bytes:
        if path.name == "locked.yaml":
            raise PermissionError("denied")
        return real(path)

    monkeypatch.setattr(loop_state_module, "_read_bytes", flaky)
    records = collect(root)
    assert records["latin"].exclusion == "decode_error" and records["latin"].digest
    assert records["locked"].exclusion == "read_error" and records["locked"].digest is None
    sources = collect_loop_sources(root, config=BRConfig(root))
    assert {d.code for d in sources[2]} == {"loop_definition_excluded"}


def test_fragment_and_non_mapping_sources_are_not_definitions(root: Path) -> None:
    write_loop(root, "frag.yaml", "fragments:\n  f:\n    action: echo\n")
    write_loop(root, "list.yaml", "- a\n- b\n")
    write_loop(root, "empty.yaml", "")
    write_loop(root, "child-of-fragment.yaml", "name: c\nfrom: frag\n")
    assert collect(root) == {}


def test_out_of_root_loops_dir_yields_a_diagnostic_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolate_builtins(monkeypatch, tmp_path / "builtin-loops")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "far.yaml").write_text(loop_yaml("far"))
    project = loop_project(
        tmp_path / "proj", config={"project": {"name": "t"}, "loops": {"loops_dir": str(outside)}}
    )
    records, _inventory, diagnostics = collect_loop_sources(project, config=BRConfig(project))
    record = by_target(records)["far"]
    assert record.source is None and not record.valid
    assert record.exclusion == "out_of_root_loops_dir" and record.digest is None
    assert any(d.code == "loops_dir_out_of_root" for d in diagnostics)


# --------------------------------------------------------- root-based resolution (no chdir)


def test_resolution_context_probes_relative_to_the_root_without_chdir(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "tools").mkdir()
    (root / "tools" / "parent.yaml").write_text(loop_yaml("parent"))
    nested = root / "sub" / "dir"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    with pytest.raises(FileNotFoundError):  # legacy behavior: cwd-relative
        resolve_loop_path("tools/parent.yaml", root / ".loops")
    cwd_before = os.getcwd()
    with resolution_context(root):
        assert resolve_loop_path("tools/parent.yaml", root / ".loops") == root / "tools/parent.yaml"
    assert os.getcwd() == cwd_before
    with pytest.raises(FileNotFoundError):  # context restored
        resolve_loop_path("tools/parent.yaml", root / ".loops")


def test_nested_cwd_collection_matches_collection_from_the_root(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "tools").mkdir()
    (root / "tools" / "parent.yaml").write_text(loop_yaml("parent", extra="description: base"))
    (root / "tools" / "worker.yaml").write_text(loop_yaml("worker"))
    # Inherited parent present only at the root (direct-path operand).
    write_loop(root, "child.yaml", "name: child\nfrom: tools/parent.yaml\n")
    # Static child reference (checked by _validate_loop_references).
    caller = (
        "name: caller\ninitial: go\nscope: ['.']\nstates:\n  go:\n    loop: tools/worker.yaml\n"
        "    terminal: true\n"
    )
    write_loop(root, "caller.yaml", caller)
    from_root = {t: (r.valid, r.exclusion) for t, r in collect(root).items()}
    nested = root / "deep" / "er"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    from_nested = {t: (r.valid, r.exclusion) for t, r in collect(root).items()}
    assert from_root == from_nested == {"child": (True, None), "caller": (True, None)}
    # Without the context the same definitions would not load from a nested cwd.
    with pytest.raises(FileNotFoundError):
        load_and_validate(root / ".loops" / "child.yaml", raise_on_error=False)


def test_legacy_load_and_validate_still_reads_the_file_and_accepts_captured_data(
    root: Path,
) -> None:
    path = write_loop(root, "alpha.yaml", loop_yaml("alpha", context={"k": "v"}))
    legacy_fsm, legacy_violations = load_and_validate(path, raise_on_error=False)
    import yaml

    data = yaml.safe_load(path.read_text())
    snapshot = json.dumps(data, sort_keys=True)
    captured_fsm, captured_violations = load_and_validate(
        path, raise_on_error=False, source_data=data
    )
    assert json.dumps(data, sort_keys=True) == snapshot  # never mutated
    assert captured_fsm.to_dict() == legacy_fsm.to_dict()
    assert [str(v) for v in captured_violations] == [str(v) for v in legacy_violations]
    path.unlink()  # a captured load does not need (or touch) the file
    again, _ = load_and_validate(path, raise_on_error=False, source_data=data)
    assert again.name == "alpha"
    with pytest.raises(FileNotFoundError):
        load_and_validate(path)


def test_shipped_builtin_definitions_load_identically_from_a_captured_buffer() -> None:
    """Real built-ins: the captured-content seam reproduces the legacy path loader."""
    import yaml

    from little_loops.fsm.loop_paths import get_builtin_loops_dir

    builtin = get_builtin_loops_dir()
    sample = sorted(p for p in builtin.glob("*.yaml"))[:12]
    assert sample
    for path in sample:
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict) or "name" not in data:
            continue
        try:
            legacy = load_and_validate(path, raise_on_error=False)
        except ValueError:
            continue
        captured = load_and_validate(path, raise_on_error=False, source_data=data)
        assert captured[0].to_dict() == legacy[0].to_dict(), path.name
        assert [str(v) for v in captured[1]] == [str(v) for v in legacy[1]], path.name


# ------------------------------------------------------------------------ visibility


def test_inherited_and_normalized_visibility(root: Path) -> None:
    write_loop(root, "base.yaml", loop_yaml("base", extra="visibility: internal"))
    write_loop(root, "kid.yaml", "name: kid\nfrom: base\n")
    write_loop(root, "ex.yaml", loop_yaml("ex", extra="visibility: example"))
    write_loop(root, "odd.yaml", loop_yaml("odd", extra="visibility: sparkly"))
    write_loop(root, "nul.yaml", loop_yaml("nul", extra="visibility:"))
    write_loop(root, "plain.yaml", loop_yaml("plain"))
    write_loop(root, "runs/d1/workflow.yaml", loop_yaml("drafty", extra="visibility: internal"))
    records = collect(root)
    assert records["base"].visibility == "internal"
    assert records["kid"].visibility == "internal"  # inherited, not a public fallback
    assert records["ex"].visibility == "example"
    assert records["odd"].visibility == "public"
    assert records["nul"].visibility == records["plain"].visibility == "public"
    assert records["d1"].is_draft and records["d1"].visibility == "internal"
    assert any("sparkly" in d.message for d in records["odd"].diagnostics)


# --------------------------------------------------------------------- resolver parity


def _write_universe(root: Path, builtin: Path) -> None:
    write_loop(root, "both.yaml", loop_yaml("both-project"))
    write_loop(root, "both.fsm.yaml", loop_yaml("both-compiled"))
    write_loop(root, "only-project.yaml", loop_yaml("only-project"))
    (builtin / "only-builtin.yaml").write_text(loop_yaml("only-builtin"))
    (builtin / "shared.yaml").write_text(loop_yaml("shared-builtin"))
    write_loop(root, "shared.yaml", loop_yaml("shared-project"))
    write_loop(root, "runs/folder-a/workflow.yaml", loop_yaml("dup-name"))
    write_loop(root, "runs/folder-b/workflow.yaml", loop_yaml("dup-name"))
    write_loop(root, "runs/solo/workflow.yaml", loop_yaml("solo-draft"))
    write_loop(root, "frag-shadow.yaml", "fragments:\n  f:\n    action: echo\n")
    (builtin / "frag-shadow.yaml").write_text(loop_yaml("shadowed-builtin"))


def test_pure_resolver_matches_resolve_loop_path_from_the_root(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(root, tmp_path / "builtin-loops")
    # Latest mtime wins among duplicate draft logical names.
    old = root / ".loops/runs/folder-a/workflow.yaml"
    new = root / ".loops/runs/folder-b/workflow.yaml"
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    (root / "only-project").write_text("a file at the project root with the target's name\n")
    config = BRConfig(root)
    records, inventory, _ = collect_loop_sources(root, config=config)
    operands = sorted({r.target for r in records} | {"dup-name", "solo-draft", "ghost"})
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    for cwd in (root, nested):  # the printed root, not the caller's cwd, decides
        monkeypatch.chdir(cwd)
        for operand in operands:
            ours = resolve_target(inventory, operand)
            with resolution_context(root, notes=[]):
                try:
                    theirs: Path | None = resolve_loop_path(operand, root / ".loops")
                except FileNotFoundError:
                    theirs = None
            if theirs is None:
                assert ours.path is None, operand
            else:
                assert ours.path is not None, operand
                assert ours.path.resolve() == theirs.resolve(), (operand, ours)
    assert resolve_target(inventory, "both").path == root / ".loops/both.fsm.yaml"
    assert resolve_target(inventory, "shared").kind == "project"
    assert resolve_target(inventory, "only-builtin").kind == "builtin"
    assert resolve_target(inventory, "folder-a").kind == "draft"
    assert resolve_target(inventory, "dup-name").path == new  # internal-name fallback
    assert resolve_target(inventory, "dup-name").kind == "draft_name"
    assert resolve_target(inventory, "only-project").kind == "direct"  # root file collision
    assert resolve_target(inventory, "ghost").kind == "none"


def test_direct_path_collisions_capture_existence_and_type(root: Path) -> None:
    write_loop(root, "thing.yaml", loop_yaml("thing"))
    (root / "thing").mkdir()
    write_loop(root, "other.yaml", loop_yaml("other"))
    (root / "other").write_text("file")
    _records, inventory, _ = collect_loop_sources(root, config=BRConfig(root))
    assert dict(inventory.direct) == {"other": "file", "thing": "dir"}
    assert resolve_target(inventory, "thing").kind == "direct"


# ---------------------------------------------------------------- zero-argument preflight


def preflight(root: Path, name: str, **loop: Any):
    write_loop(root, f"{name}.yaml", loop_yaml(name, **loop))
    config = BRConfig(root)
    record = by_target(collect_loop_definitions(root, config=config))[name]
    assert record.valid, record.errors
    return zero_argument_context(record, collect_loop_inputs(root, config=config))


def test_missing_template_context_is_unresolved(root: Path) -> None:
    ctx = preflight(root, "needs-input", action="echo ${context.input}")
    assert ctx.missing_keys == ("input",) and not ctx.ok


@pytest.mark.parametrize(
    "action",
    [
        "echo ${context.input:default=x}",
        "echo ${context.input?}",
        "echo ${context.input:shell:default=x}",
        "echo ${context.run_dir} ${context.max_steps}",
        "echo ${context.readiness_threshold} ${context.outcome_threshold}",
        "echo ${context.design_tokens_context} ${context.design_guidance_context}",
    ],
)
def test_guarded_refs_and_runner_bound_keys_are_available(root: Path, action: str) -> None:
    assert preflight(root, "ok", action=action).ok


def test_shell_suffix_still_requires_the_underlying_key(root: Path) -> None:
    assert preflight(root, "sh", action="echo ${context.target:shell}").missing_keys == ("target",)


def test_context_literals_and_parameter_defaults_satisfy_template_refs(root: Path) -> None:
    assert preflight(root, "lit", action="echo ${context.topic}", context={"topic": "x"}).ok
    extra = "parameters:\n  topic:\n    type: string\n    default: hello\n"
    assert preflight(root, "par", action="echo ${context.topic}", extra=extra).ok
    required = "parameters:\n  topic:\n    type: string\n    required: true\n"
    assert not preflight(root, "req", action="echo ${context.topic}", extra=required).ok


def test_steering_overwrites_yaml_literal_and_satisfies_required_inputs(root: Path) -> None:
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".ll" / "program.md").write_text("## Benchmark\nmetric: 7\n\n## Directive\nsteer\n")
    # Falsy YAML literal is overwritten by a steering benchmark value: eligible.
    ok = preflight(
        root,
        "steered",
        action="echo ${context.metric}",
        context={"metric": ""},
        extra="required_inputs: [metric]",
    )
    assert ok.ok and ok.provenance["metric"].startswith("steering")
    # A required_inputs key satisfied only by steering is eligible.
    only = preflight(root, "only-steer", extra="required_inputs: [directive]")
    assert only.ok and only.provenance["directive"].startswith("steering")


def test_required_inputs_use_truthiness_not_key_membership(root: Path) -> None:
    for name, value in (("zero", 0), ("empty", ""), ("off", False)):
        ctx = preflight(
            root,
            name,
            action="echo ${context.flag}",
            context={"flag": value},
            extra="required_inputs: [flag]",
        )
        assert ctx.unresolved_inputs == ("flag",) and not ctx.ok, name
    assert preflight(root, "truthy", context={"flag": "yes"}, extra="required_inputs: [flag]").ok


def test_conditional_runtime_seeds_stay_conditional(root: Path) -> None:
    hash_ref = "echo ${context.input_hash}"
    assert preflight(root, "nohash", action=hash_ref).missing_keys == ("input_hash",)
    assert preflight(root, "hash", action=hash_ref, context={"input": "seed"}).ok
    assert preflight(root, "nonstr", action=hash_ref, context={"input": 5}).missing_keys == (
        "input_hash",
    )
    iters = "echo ${context.max_iterations}"
    assert preflight(root, "noiter", action=iters).missing_keys == ("max_iterations",)
    assert preflight(root, "iter", action=iters, extra="max_steps: 10\nmax_iterations: 4").ok
    include = "echo ${context.include}"
    assert preflight(root, "noinc", action=include).missing_keys == ("include",)


def test_include_default_comes_from_captured_config(tmp_path: Path, monkeypatch: Any) -> None:
    isolate_builtins(monkeypatch, tmp_path / "builtin-loops")
    project = loop_project(
        tmp_path / "proj",
        config={"project": {"name": "t"}, "loops": {"run_defaults": {"include": "a,b"}}},
    )
    assert preflight(project, "inc", action="echo ${context.include}").ok


def test_design_context_is_symbolic_and_never_loaded(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("design tokens must not be loaded by the arena")

    monkeypatch.setattr("little_loops.design_tokens.load_design_tokens", boom)
    monkeypatch.setattr("little_loops.fsm.context_seed.inject_design_context", boom)
    names = "required_inputs: [design_tokens_context]"
    unknown = preflight(root, "tok", extra=names)
    assert unknown.unknown_inputs == ("design_tokens_context",) and not unknown.ok
    opt_out = preflight(root, "off", context={"use_design_tokens": False}, extra=names)
    assert opt_out.unresolved_inputs == ("design_tokens_context",)  # known empty
    known = preflight(root, "lit", context={"design_tokens_context": "tokens"}, extra=names)
    assert known.ok  # preserved known truthy literal
    str_off = preflight(root, "stroff", context={"use_design_tokens": "no"}, extra=names)
    assert str_off.unresolved_inputs == ("design_tokens_context",)


def test_preflight_negative_cases_agree_with_the_real_runner(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive ``cmd_run`` up to its preflight gate; it must refuse what the arena refuses."""
    from little_loops.cli.loop.run import cmd_run

    cases = {
        "needs-key": {"action": "echo ${context.nope}"},
        "falsy-input": {
            "action": "echo hi",
            "context": {"flag": 0},
            "extra": "required_inputs: [flag]",
        },
    }
    config = BRConfig(root)
    monkeypatch.chdir(root)
    for name, spec in cases.items():
        write_loop(root, f"{name}.yaml", loop_yaml(name, **spec))
        record = by_target(collect_loop_definitions(root, config=config))[name]
        assert not zero_argument_context(record, collect_loop_inputs(root, config=config)).ok

        class Sink:
            def __init__(self) -> None:
                self.errors: list[str] = []

            def error(self, msg: str) -> None:
                self.errors.append(msg)

            def debug(self, msg: str) -> None: ...
            def info(self, msg: str) -> None: ...
            def warning(self, msg: str) -> None: ...

        sink = Sink()
        args = argparse.Namespace(
            input=None, max_steps=None, max_iterations=None, delay=None, no_llm=False,
            llm_model=None, dry_run=False, background=False, foreground_internal=False,
            instance_id=None, quiet=False, verbose=False, context=[], program_md=None,
            builtin=False, worktree=False, handoff_threshold=None, context_limit=None,
        )  # fmt: skip
        assert cmd_run(name, args, root / ".loops", sink) == 1  # type: ignore[arg-type]
        assert sink.errors, name


# --------------------------------------------------------------- preserved catalog scans


def test_duplicate_draft_resolver_note_is_a_diagnostic_not_stderr(
    root: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """``resolve_loop_path`` prints a ``Note:`` for duplicate draft names; child validation
    reaches it too. Under collection it is captured as a diagnostic instead."""
    write_loop(root, "runs/a/workflow.yaml", loop_yaml("dup"))
    write_loop(root, "runs/b/workflow.yaml", loop_yaml("dup"))
    os.utime(root / ".loops/runs/a/workflow.yaml", (1_000_000, 1_000_000))
    caller = (
        "name: caller\ninitial: go\nscope: ['.']\nstates:\n  go:\n    loop: dup\n"
        "    terminal: true\n"
    )
    write_loop(root, "caller.yaml", caller)
    record = collect(root)["caller"]
    assert capfd.readouterr() == ("", "")
    assert record.valid
    notes = [d for d in record.diagnostics if d.code == "loop_resolution_note"]
    assert notes and "skipped older draft(s) named 'dup'" in notes[0].message
    assert notes[0].subject == "loop:caller"


def test_artifact_output_catalog_scan_warning_is_preserved_as_a_diagnostic(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existing reference-warning scan revisits sibling sources; it is kept, not replaced."""
    write_loop(root, "producer.yaml", loop_yaml("producer", extra="artifact_output: report.html"))
    caller = (
        "name: caller\ninitial: go\nscope: ['.']\nstates:\n  go:\n    loop: producer\n"
        "    terminal: true\n"
    )
    write_loop(root, "caller.yaml", caller)
    reads: list[Path] = []
    real = loop_state_module._read_bytes

    def counting(path: Path) -> bytes:
        reads.append(path)
        return real(path)

    monkeypatch.setattr(loop_state_module, "_read_bytes", counting)
    producer = collect(root)["producer"]
    assert producer.valid
    assert any(
        "artifact_output" in d.message and d.code == "loop_validation_warning"
        for d in producer.diagnostics
    )
    # The arena's own ingestion still reads each discovered source exactly once; the catalog
    # scan's extra reads are separate collection-validation I/O and never replace the digest.
    assert sorted(p.name for p in reads) == ["caller.yaml", "producer.yaml"]
    path = root / ".loops" / "producer.yaml"
    assert producer.digest == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------ history


def history(root: Path) -> Any:
    return collect_loop_history(root / ".loops", as_of=AS_OF, project_root=root)


def test_missing_history_directory_is_available_and_empty(root: Path) -> None:
    snap = history(root)
    assert snap.available and snap.records == () and snap.diagnostics == ()


def test_qualification_and_exclusion_reasons(root: Path) -> None:
    write_run(root, "2026-10-01T100000", "ok", completed_run("2026-10-01T10:00:00+00:00"))
    write_run(root, "2026-10-01T110000", "naive", completed_run("2026-10-01T11:00:00"))
    write_run(root, "2026-10-01T120000", "dateonly", completed_run("2026-10-01"))
    write_run(root, "2026-10-01T130000", "offset", completed_run("2026-10-01T15:00:00+02:00"))
    write_run(root, "2026-10-01T140000", "future", completed_run("2026-10-09T10:00:00Z"))
    write_run(root, "2026-10-01T150000", "badstart", completed_run("not-a-date"))
    write_run(root, "2026-10-01T160000", "nostart", {"status": "completed"})
    write_run(root, "2026-10-01T170000", "nonmapping", ["list"])
    write_run(root, "2026-10-01T180000", "malformed", "{not json")
    write_run(root, "2026-10-01T190000", "nofile", None)
    write_run(root, "2026-10-01T200000", "nostatus", {"started_at": "2026-10-01T10:00:00Z"})
    write_run(root, "2026-10-01T210000", "weirdstatus", {"status": 7, "started_at": "2026-10-01"})
    (root / ".loops" / ".history" / "not-a-run-folder").mkdir()
    (root / ".loops" / ".history" / "stray.txt").write_text("x")
    snap = history(root)
    got = {r.logical_name: r for r in snap.records}
    assert set(got) == {
        "ok", "naive", "dateonly", "offset", "future", "badstart", "nostart",
        "nonmapping", "malformed", "nofile", "nostatus", "weirdstatus",
    }  # fmt: skip
    qualified = {n for n, r in got.items() if r.qualified}
    assert qualified == {"ok", "naive", "dateonly", "offset", "nostatus", "weirdstatus"}
    assert got["offset"].started_at.isoformat() == "2026-10-01T13:00:00+00:00"
    assert got["naive"].started_at.isoformat() == "2026-10-01T11:00:00+00:00"
    assert got["dateonly"].started_at.isoformat() == "2026-10-01T00:00:00+00:00"
    assert got["future"].exclusion == "started_at_future"
    assert got["badstart"].exclusion == "started_at_malformed_date"
    assert got["nostart"].exclusion == "started_at_absent"
    assert got["nonmapping"].exclusion == "state_not_mapping"
    assert got["malformed"].exclusion == "state_malformed_json"
    assert got["nofile"].exclusion == "state_missing"
    assert got["weirdstatus"].status is None and got["weirdstatus"].status_raw == 7
    assert got["ok"].status == "completed" and got["nostatus"].status is None
    # Excluded records keep their raw provenance and one summary diagnostic per reason.
    assert got["badstart"].started_at_raw == "not-a-date"
    reasons = {d.message.rsplit(": ", 1)[1] for d in snap.diagnostics}
    assert "started_at_future" in reasons and "state_missing" in reasons
    assert all(d.code == "loop_history_record_excluded" for d in snap.diagnostics)


def test_each_state_file_is_read_once_in_one_batched_enumeration(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(5):
        write_run(root, f"2026-10-01T10000{i}", f"l{i}", completed_run("2026-10-01T10:00:00Z"))
    reads: list[Path] = []
    scans: list[Path] = []
    real_read, real_scan = loop_state_module._read_state_bytes, loop_state_module._scandir

    def counting_read(path: Path) -> bytes:
        reads.append(path)
        return real_read(path)

    def counting_scan(path: Path) -> Any:
        scans.append(path)
        return real_scan(path)

    monkeypatch.setattr(loop_state_module, "_read_state_bytes", counting_read)
    monkeypatch.setattr(loop_state_module, "_scandir", counting_scan)
    snap = history(root)
    assert len(snap.records) == 5 and len(reads) == 5 and len(set(reads)) == 5
    assert scans == [root / ".loops" / ".history"]


def test_history_non_directory_is_unavailable_with_a_scoped_diagnostic(root: Path) -> None:
    (root / ".loops").mkdir(exist_ok=True)
    (root / ".loops" / ".history").write_text("a file, not a directory")
    snap = history(root)
    assert not snap.available and snap.unavailable_reason == "not_a_directory"
    assert snap.records == ()
    assert [d.code for d in snap.diagnostics] == ["loop_history_unavailable"]
    assert "never ran" in snap.diagnostics[0].message


def test_enumeration_failure_after_a_partial_batch_discards_the_batch(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(4):
        write_run(root, f"2026-10-01T10000{i}", f"l{i}", completed_run("2026-10-01T10:00:00Z"))

    class Exploding:
        def __init__(self, entries: list[Any]) -> None:
            self._entries = entries

        def __enter__(self) -> Exploding:
            return self

        def __exit__(self, *exc: object) -> None: ...

        def __iter__(self) -> Any:
            for i, entry in enumerate(self._entries):
                if i == 2:
                    raise PermissionError("enumeration failed mid-batch")
                yield entry

    real = loop_state_module._scandir

    def failing(path: Path) -> Any:
        with real(path) as it:
            return Exploding(list(it))

    monkeypatch.setattr(loop_state_module, "_scandir", failing)
    snap = history(root)
    assert not snap.available and snap.records == ()
    assert snap.unavailable_reason.startswith("enumeration_failed")


def test_history_is_read_from_the_configured_loops_directory_only(root: Path) -> None:
    write_run(root, "2026-10-01T100000", "here", completed_run("2026-10-01T10:00:00Z"))
    write_run(
        root, "2026-10-01T100000", "elsewhere", completed_run("2026-10-01T10:00:00Z"), base=".other"
    )
    (root / ".loops" / ".running").mkdir(exist_ok=True)
    (root / ".loops" / ".running" / "2026-10-01T100000-running.pid").write_text("1")
    assert [r.logical_name for r in history(root).records] == ["here"]


def test_inputs_capture_steering_once_and_tolerate_absence(root: Path) -> None:
    config = BRConfig(root)
    absent = collect_loop_inputs(root, config=config)
    assert not absent.steering_present and dict(absent.steering_sections) == {}
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".ll" / "program.md").write_text("## Budget\nten\n")
    present = collect_loop_inputs(root, config=config)
    assert present.steering_present and dict(present.steering_sections) == {"budget": "ten"}
    assert present.readiness_threshold == 85 and present.outcome_threshold == 65


def test_domain_collection_is_scope_aware(root: Path) -> None:
    from tests.next_arena_support import collect

    issue_only = collect(root)
    assert issue_only.loop_definitions is None and issue_only.loop_history is None
    assert issue_only.loop_inputs is None and issue_only.loop_diagnostics == ()
    full = loop_state(root)
    assert full.loop_definitions == () and full.loop_history is not None  # collected, none found
