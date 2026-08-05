"""ll-loop scaffold-verify: generate a single-issue FSM verification loop YAML (FEAT-2948).

Mechanical port of skills/verify-issue-loop/SKILL.md + templates.md's two
per-mode state-synthesis templates: the criteria-mode linear chain (one
`verify-criterion-N` state per acceptance-criterion bullet, on_yes chaining,
on_no/on_partial routed to a shared `failed` terminal) and the fixed
adversarial-mode 3-probe template (`probe-boundary` -> `probe-malformed-hostile`
-> `probe-failure-mode` -> `count_probes`, a non-LLM filesystem-derived gate).
Both templates' prompt text is fully determined by the issue's own title and
extracted criterion text, so — unlike scaffold-eval — nothing here is a
`<PLACEHOLDER>` left for an LLM to fill; scaffold-verify's output is
immediately runnable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.loop._scaffold_core import ScaffoldResult, dump_fsm_yaml, resolve_issue
from little_loops.cli.output import print_json
from little_loops.file_utils import atomic_write
from little_loops.fsm.schema import EvaluateConfig, FSMLoop, StateConfig
from little_loops.fsm.validation import ValidationSeverity, validate_fsm
from little_loops.issue_parser import CriterionSlot, slugify

_CRITERIA_TIMEOUT = 1800
_ADVERSARIAL_TIMEOUT = 2700
_STATE_TIMEOUT = 300
_MAX_STEPS = 20


def _criteria_states(criteria: list[CriterionSlot], issue_id: str) -> dict[str, StateConfig]:
    """Build the criteria-mode linear chain of `verify-criterion-N` states."""
    states: dict[str, StateConfig] = {}
    total = len(criteria)
    for slot in criteria:
        next_state = criteria[slot.index].state_name if slot.index < total else "done"
        action_text = (
            f"Verify acceptance criterion {slot.index} for {issue_id}: {slot.source_text}. "
            "Inspect the implementation, run any commands needed, and gather concrete "
            "evidence about whether the criterion holds. Report what you observed."
        )
        eval_prompt = (
            f"Does the implementation satisfy criterion {slot.index} of {issue_id}?\n\n"
            f"Criterion: {slot.source_text}\n\n"
            "Answer YES only if the evidence clearly shows the criterion is met.\n"
            "Answer NO if the criterion is not met or evidence is missing/ambiguous.\n"
            "Provide a one-sentence reason citing the observed evidence."
        )
        states[slot.state_name] = StateConfig(
            action=action_text,
            action_type="prompt",
            timeout=_STATE_TIMEOUT,
            evaluate=EvaluateConfig(type="llm_structured", prompt=eval_prompt),
            on_yes=next_state,
            on_no="failed",
            on_partial="failed",
        )
    states["done"] = StateConfig(terminal=True)
    states["failed"] = StateConfig(terminal=True, failure=True)
    return states


# (name, probe_class, result_file, verb, instructions, evidence_ref) — verbatim per
# skills/verify-issue-loop/templates.md's fixed 3-probe template.
_PROBES = (
    (
        "probe-boundary",
        "boundary",
        "probe-boundary.json",
        "Probe boundary conditions",
        "Try to break the feature using boundary and extreme values: empty inputs, maximum "
        "sizes, off-by-one values, Unicode edge cases, very large payloads, zero/negative "
        "numbers. Attempt at least two distinct boundary probes. For each probe, run a real "
        "command or exercise the feature concretely — do not just theorize.",
        "the boundary probe",
    ),
    (
        "probe-malformed-hostile",
        "malformed_hostile",
        "probe-malformed.json",
        "Probe malformed and hostile inputs",
        "Try to break the feature using: wrong types, injection-shaped strings (shell, "
        "path-traversal), partial or incomplete state, concurrent or duplicate invocations, "
        "null/None values, unexpected encoding, negative indices. Attempt at least two "
        "distinct malformed/hostile probes. Run real commands — do not theorize.",
        "the malformed/hostile-input probe",
    ),
    (
        "probe-failure-mode",
        "failure_mode",
        "probe-failure.json",
        "Probe known failure modes",
        "Try to break the feature by simulating failure conditions: missing config files, "
        "absent required files or directories, interrupted or partial runs, corrupted state, "
        "unavailable dependencies, missing environment variables, permission errors. Attempt "
        "at least two distinct failure-mode probes. Run real commands — do not theorize.",
        "the failure-mode probe",
    ),
)


def _adversarial_states(issue_id: str, title: str) -> dict[str, StateConfig]:
    """Build the fixed 3-probe adversarial template (emitted verbatim, no per-issue variation)."""
    states: dict[str, StateConfig] = {}
    names = [p[0] for p in _PROBES]
    for i, (name, probe_class, result_file, verb, instructions, evidence_ref) in enumerate(_PROBES):
        next_state = names[i + 1] if i + 1 < len(names) else "count_probes"
        action_text = (
            f"{verb} for {issue_id}: {title}.\n\n"
            f"{instructions}\n\n"
            f"After probing, write a JSON result to ${{context.run_dir}}/{result_file}:\n"
            f'  {{"probe_class": "{probe_class}", "probes_attempted": <N>, '
            f'"break_found": <true|false>, "finding": "<what happened>"}}\n\n'
            "Report what you tried and what you observed."
        )
        eval_prompt = (
            f"Did {evidence_ref} of {issue_id} survive without exposing a genuine break?\n\n"
            "A genuine break is a reproducible bug, crash, error, or wrong output caused by "
            "the probe. A probe that did NOT break the feature (the feature handled it "
            "correctly) is a PASS.\n\n"
            "Answer YES if the feature survived (no genuine break found).\n"
            "Answer NO if a probe found a genuine break — a reproducible failure, crash, or "
            "wrong output.\n"
            "Provide a one-sentence reason citing what was tried and what was observed."
        )
        states[name] = StateConfig(
            action=action_text,
            action_type="prompt",
            timeout=_STATE_TIMEOUT,
            evaluate=EvaluateConfig(type="llm_structured", prompt=eval_prompt),
            on_yes=next_state,
            on_no="failed_with_finding",
        )

    states["count_probes"] = StateConfig(
        action="ls \"${context.run_dir}\"/probe-*.json 2>/dev/null | wc -l | tr -d ' '\n",
        action_type="shell",
        evaluate=EvaluateConfig(type="output_numeric", operator="ge", target=3),
        on_yes="done",
        on_no="failed_too_few",
    )
    states["done"] = StateConfig(terminal=True)
    states["failed_with_finding"] = StateConfig(terminal=True, failure=True)
    states["failed_too_few"] = StateConfig(terminal=True, failure=True)
    return states


def _slug_name(issue_id: str, title: str, adversarial: bool) -> str:
    prefix = "adversarial" if adversarial else "verify"
    issue_lower = issue_id.lower()
    title_slug = slugify(title)
    if title_slug:
        return f"{prefix}-{issue_lower}-{title_slug}"
    return f"{prefix}-{issue_lower}"


def scaffold_verify(issue_id: str, adversarial: bool) -> ScaffoldResult:
    """Generate a verification loop for *issue_id* (criteria mode by default).

    Timeout selection is code, not prose: criteria mode gets 1800s, adversarial
    gets 2700s. Validates the built ``FSMLoop`` in-process via ``validate_fsm()``
    before returning; never raises on validation failure.
    """
    path, info, error = resolve_issue(issue_id)
    if error or path is None or info is None:
        return ScaffoldResult(
            yaml_path=None, yaml_text="", placeholders=[], validated=False, errors=[error or ""]
        )

    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueParser

    parser = IssueParser(BRConfig(Path.cwd()))

    if adversarial:
        states = _adversarial_states(issue_id, info.title)
        initial = "probe-boundary"
        timeout = _ADVERSARIAL_TIMEOUT
        description = (
            f"Adversarial verification loop for {issue_id}: {info.title}.\n"
            "Tries to break the feature via boundary values, malformed/hostile inputs, and "
            "failure modes.\n"
            "FAIL fires when fewer than 3 probe classes are genuinely attempted "
            "(count_probes gate).\n"
            "Generated by `ll-loop scaffold-verify --adversarial`."
        )
    else:
        criteria = parser.extract_criteria(path)
        if not criteria:
            return ScaffoldResult(
                yaml_path=None,
                yaml_text="",
                placeholders=[],
                validated=False,
                errors=[
                    f"Issue {issue_id} has no Acceptance Criteria or Expected Behavior bullets. "
                    "Run refine/format-issue to add criteria, or pass --adversarial."
                ],
            )
        states = _criteria_states(criteria, issue_id)
        initial = criteria[0].state_name
        timeout = _CRITERIA_TIMEOUT
        description = (
            f"Verification loop for {issue_id}: {info.title}.\n"
            "Walks each acceptance criterion in order; fails fast on any criterion that "
            "fails.\n"
            "Generated by `ll-loop scaffold-verify`."
        )

    name = _slug_name(issue_id, info.title, adversarial)
    fsm = FSMLoop(
        name=name,
        initial=initial,
        states=states,
        description=description,
        category="verification",
        max_steps=_MAX_STEPS,
        timeout=timeout,
    )

    validation_errors = validate_fsm(fsm)
    has_errors = any(e.severity == ValidationSeverity.ERROR for e in validation_errors)
    yaml_text = dump_fsm_yaml(fsm)

    return ScaffoldResult(
        yaml_path=None,
        yaml_text=yaml_text,
        placeholders=[],
        validated=not has_errors,
        errors=[f"{e.severity.value}: {e.path}: {e.message}" for e in validation_errors],
    )


def cmd_scaffold_verify(args: argparse.Namespace, loops_dir: Path) -> int:
    """Entry point for ``ll-loop scaffold-verify <id> [--adversarial] [--out|--stdout] [--json]``."""
    result = scaffold_verify(args.issue_id, adversarial=bool(getattr(args, "adversarial", False)))

    out_path: Path | None = getattr(args, "out", None)
    if result.yaml_text and out_path is not None:
        atomic_write(out_path, result.yaml_text)
        result.yaml_path = out_path

    if getattr(args, "json", False):
        print_json(result.to_dict())
        return 0 if result.yaml_text and result.validated else 1

    if not result.yaml_text:
        for err in result.errors:
            print(f"Error: {err}")
        return 1

    if getattr(args, "stdout", False) or out_path is None:
        print(result.yaml_text)

    if out_path is not None:
        print(f"Wrote: {out_path}")

    print(f"Validated: {'PASS' if result.validated else 'FAIL'}")
    for err in result.errors:
        print(f"  {err}")

    return 0 if result.validated else 1
