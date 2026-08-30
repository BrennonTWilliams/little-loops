"""Spike for ENH-3342: what value should MR-11's widened bash-token-position
scan pass as `interp_sweep.scan_action()`'s mandatory keyword-only `file`
argument, given `FSMLoop` has no file-path field and none of `scan_action()`'s
three real callers threads one down to `validate_fsm()`?

Calls the REAL production `scan_action()`, `classify_site()`, `InterpSite`,
`FSMLoop`, `StateConfig`, and `validate_fsm()` directly — nothing reimplemented.
See .ll/spikes/spike-ENH-3342.md for the full plan.
"""

from __future__ import annotations

import dataclasses
import inspect

from little_loops.fsm.interp_sweep import InterpSite, scan_action
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.fsm.validation.structural_rules import validate_fsm


def _mr11_style_message(state_name: str, token: str) -> str:
    """Mirrors _validate_unsafe_context_interpolation's message builder
    (shell_safety.py) exactly: keys on state_name + token only, never `file`.
    """
    return (
        f"[state: {state_name}] {token} interpolates user-controlled "
        'context raw into a shell body. A value containing ", $, `, \\, '
        "or ! can break bash tokenizing or inject commands (BUG-2622)."
    )


class TestNoRealPathAvailableAtCallSites:
    def test_real_call_sites_have_no_file_path_available_for_validate_fsm(self):
        """Structural regression guard: proves the spike's premise ("no path
        is threaded to validate_fsm today") still holds. If this ever fails,
        a future change threaded a path through — the file-param question
        needs re-spiking against the new call chain, not answered by this
        spike's conclusion.
        """
        sig = inspect.signature(validate_fsm)
        param_names = set(sig.parameters)
        assert param_names == {"fsm", "orchestration_request_path"}, (
            "validate_fsm() gained/lost a parameter; re-check whether a real "
            "file path is now threaded through before trusting this spike."
        )

        fsm_field_names = {f.name for f in dataclasses.fields(FSMLoop)}
        path_like = {
            name
            for name in fsm_field_names
            if {"path", "file", "source"} & set(name.lower().split("_"))
        }
        assert path_like == set(), (
            f"FSMLoop gained a path-like field {path_like!r}; a real file "
            "path may now be threadable — re-check option (a) before trusting "
            "this spike's fsm.name recommendation."
        )

        # The two scaffold call sites build FSMLoop in-memory and validate it
        # BEFORE any disk path exists (yaml_path is only computed after
        # validate_fsm() returns, from the generated `name`) — reproduced
        # here exactly as scaffold_eval.py / scaffold_verify.py do it.
        fsm = FSMLoop(
            name="scaffold-generated-loop",
            initial="execute",
            states={"execute": StateConfig(action="echo hi", action_type="shell", terminal=True)},
            description="scaffold-built, not yet written to disk",
            category="harness",
            max_steps=50,
            timeout=1800,
        )
        # No path exists for this fsm at validation time — there is nothing
        # to thread even if validate_fsm() grew a path parameter tomorrow,
        # short of fabricating one.
        errors = validate_fsm(fsm)
        assert isinstance(errors, list)  # real call succeeds; no path required or available


class TestFileValueDoesNotLeakIntoMr11Output:
    ACTION = "python3 <<'PYEOF'\ngoal = '${context.goal}'\nprint(goal)\nPYEOF\n"

    def _scan_and_render(self, file_value: str) -> list[str]:
        sites: list[InterpSite] = scan_action(self.ACTION, state="run", file=file_value)
        # Reconstruct MR-11-style messages the way the widened validator would,
        # deliberately never reading site.file.
        return [
            _mr11_style_message("run", "${" + site.var + "}") for site in sites if site.cls != "C"
        ]

    def test_scan_action_file_value_does_not_leak_into_mr11_style_message(self):
        messages_placeholder = self._scan_and_render("<unset>")
        messages_fsm_name = self._scan_and_render("my-real-loop-name")
        messages_empty = self._scan_and_render("")

        assert messages_placeholder, "sanity: the fixture action must produce at least one finding"
        assert messages_placeholder == messages_fsm_name == messages_empty, (
            "MR-11-style message text differs by `file` value; `file` is not "
            "actually inert for MR-11's output as assumed"
        )


class TestMergeCountsInsensitiveToFileConstant:
    # Same untrusted var appears twice in one Python body -> _merge_counts()
    # should collapse them to count=2, keyed on (file, state, var, cls).
    ACTION = (
        "python3 <<'PYEOF'\n"
        "a = '${captured.step_one.output}'\n"
        "b = '${captured.step_one.output}'\n"
        "PYEOF\n"
    )

    def test_merge_counts_is_insensitive_to_constant_file_value_within_one_call(self):
        for file_value in ("placeholder", "", "my-loop", "loops/whatever.yaml"):
            sites = scan_action(self.ACTION, state="s", file=file_value)
            matching = [s for s in sites if s.var == "captured.step_one.output"]
            assert len(matching) == 1, (
                f"expected the duplicate site to merge into one InterpSite for "
                f"file={file_value!r}, got {len(matching)}"
            )
            assert matching[0].count == 2, (
                f"expected merged count=2 for file={file_value!r}, got {matching[0].count}"
            )
            assert matching[0].file == file_value  # file is preserved, just never compared against


class TestFsmNameAlwaysAvailable:
    def test_fsm_name_is_always_available_at_every_real_call_site(self):
        # Site 1: disk-loaded shape (structural_rules.py's load_and_validate_fsm),
        # via FSMLoop.from_dict — the same entry point `ll-loop validate` uses.
        disk_loaded = FSMLoop.from_dict(
            {
                "name": "disk-loaded-loop",
                "initial": "s1",
                "states": {"s1": {"terminal": True}},
            }
        )
        assert disk_loaded.name == "disk-loaded-loop"

        # Site 2/3: scaffold_eval.py / scaffold_verify.py's in-memory shape —
        # both construct FSMLoop(name=..., initial=..., states=..., ...) directly,
        # with no disk path in existence yet.
        scaffold_eval_style = FSMLoop(
            name="rn-general-task-issue-123",
            initial="execute",
            states={"execute": StateConfig(action="echo hi", action_type="shell", terminal=True)},
            description="d",
            category="harness",
            max_steps=10,
            timeout=100,
        )
        scaffold_verify_style = FSMLoop(
            name="verify-enh-3342-widen-mr-11",
            initial="probe-boundary",
            states={
                "probe-boundary": StateConfig(action="echo hi", action_type="shell", terminal=True)
            },
            description="d",
            category="verification",
            max_steps=10,
            timeout=100,
        )

        for fsm in (disk_loaded, scaffold_eval_style, scaffold_verify_style):
            assert isinstance(fsm.name, str) and fsm.name, (
                f"fsm.name must be a non-empty string at every real call site, got {fsm.name!r}"
            )

        # And it round-trips cleanly through scan_action() as `file` with no error.
        for fsm in (disk_loaded, scaffold_eval_style, scaffold_verify_style):
            sites = scan_action(
                "python3 <<'PYEOF'\nx = '${context.input}'\nPYEOF\n",
                state="s",
                file=fsm.name,
            )
            assert sites and sites[0].file == fsm.name
