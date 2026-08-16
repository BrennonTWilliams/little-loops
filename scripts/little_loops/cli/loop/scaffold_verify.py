"""ll-loop scaffold-verify: generate a single-issue FSM verification loop YAML (FEAT-2948).

Mechanical port of skills/verify-issue-loop/SKILL.md + templates.md's two
per-mode state-synthesis templates: the criteria-mode linear chain (one
`verify-criterion-N` state per acceptance-criterion bullet, on_yes/on_no/
on_partial/on_error/on_blocked all chaining to the next criterion so every
criterion is evaluated regardless of an earlier failure, ending at an
aggregate state that reports every criterion that did not pass — ENH-3200)
and the fixed adversarial-mode 3-probe template (`probe-boundary` ->
`probe-malformed-hostile` -> `probe-failure-mode`, each routing every verdict
forward to the next probe, -> `count_probes`, a non-LLM filesystem-derived
gate, -> `probe-aggregate`, ENH-3200).
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

# ENH-2998: documentation only, not emitted by either template below and not
# validated as YAML. The deterministic pre-patch check (ENH-3142/ENH-2997) has
# no generator flag -- unlike `count_probes` (a *mechanical*, always-emitted
# deterministic gate for adversarial mode), it is an opt-in guard a caller
# hand-adds to a criteria-mode state's StateConfig when
# `config.prepatch_check.enabled` is true. It pairs a deterministic verdict
# alongside the `llm_structured` one this generator always emits -- the same
# deterministic-alongside-llm_structured shape `count_probes` already
# demonstrates for the adversarial template. See
# `skills/verify-issue-loop/SKILL.md` for the full explanation.
PREPATCH_CHECK_STATE_EXAMPLE = """\
verify-criterion-1:
  action: "Verify acceptance criterion 1 for ENH-1234: ..."
  action_type: prompt
  evaluate:
    type: llm_structured
    prompt: "Does the implementation satisfy criterion 1?"
  prepatch_check: fail   # fail | warn | allow -- runs run_prepatch_check() on
                          # green exit (StateConfig field; FSMLoop.prepatch_check
                          # sets a loop-level default instead)
  capture: verify-criterion-1   # ENH-3200: verdict written back post-evaluate,
                                 # read by the aggregate state at chain end
  on_yes: verify-criterion-2
  on_no: verify-criterion-2     # ENH-3200: no short-circuit -- every verdict
  on_partial: verify-criterion-2 # routes forward; the aggregate state (final
  on_error: verify-criterion-2   # chain member) derives pass/fail from every
  on_blocked: verify-criterion-2 # criterion's captured verdict, not from which
                                  # terminal was reached.
"""


def _aggregate_state(entries: list[tuple[str, str]], on_yes: str, on_no: str) -> StateConfig:
    """Build a deterministic aggregate state (ENH-3200).

    *entries* is a list of ``(label, capture_key)`` pairs. The generated shell
    action inspects each entry's captured verdict via the guarded
    ``${captured.<key>.verdict:default=...}`` idiom (never a bare/unguarded
    ref, per the reachability lint) and reports every entry whose verdict is
    not ``yes`` — including an absent verdict (state never ran, or its
    evaluator returned ``None``), which counts as not-passed rather than a
    silent pass. The captured ``failure_type`` is surfaced alongside a
    not-passed verdict so an infra fault (e.g. a transient API error) stays
    distinguishable from a genuine NO (AC8).

    Bash-only expansions (arrays, `${VAR:+...}`) are avoided throughout —
    every `${...}` in the generated action is an intentional FSM
    interpolation ref; bare `$VAR` is used for pure-bash values so nothing
    collides with the FSM interpolation pass that runs before bash executes.
    """
    lines = ['FAILURES=""']
    for label, key in entries:
        lines.append(f'V="${{captured.{key}.verdict:default=unknown}}"')
        lines.append(f'FT="${{captured.{key}.failure_type:default=}}"')
        lines.append('if [ "$V" != "yes" ]; then')
        lines.append('  if [ -n "$FT" ]; then')
        lines.append(f'    FAILURES="$FAILURES {label}:$V:$FT"')
        lines.append("  else")
        lines.append(f'    FAILURES="$FAILURES {label}:$V"')
        lines.append("  fi")
        lines.append("fi")
    lines.append('if [ -z "$FAILURES" ]; then')
    lines.append('  echo "ALL_PASSED"')
    lines.append("else")
    lines.append('  echo "NOT_PASSED:$FAILURES"')
    lines.append("fi")
    action_text = "\n".join(lines) + "\n"
    return StateConfig(
        action=action_text,
        action_type="shell",
        evaluate=EvaluateConfig(type="output_contains", pattern="ALL_PASSED"),
        on_yes=on_yes,
        on_no=on_no,
    )


def _criteria_states(criteria: list[CriterionSlot], issue_id: str) -> dict[str, StateConfig]:
    """Build the criteria-mode linear chain of `verify-criterion-N` states.

    ENH-3200: every criterion is evaluated on every run -- on_yes/on_no/
    on_partial/on_error/on_blocked all route to the next criterion state (the
    last criterion routes to the aggregate state instead of a shared `failed`
    terminal). Each state declares `capture` so its verdict is available to
    the aggregate via the executor's post-evaluate write-back.
    """
    states: dict[str, StateConfig] = {}
    total = len(criteria)
    for slot in criteria:
        next_state = criteria[slot.index].state_name if slot.index < total else "verify-aggregate"
        action_text = (
            f"Verify acceptance criterion {slot.index} for {issue_id}: {slot.source_text}. "
            "Inspect the implementation, run any commands needed, and gather concrete "
            "evidence about whether the criterion holds. Report what you observed."
        )
        eval_prompt = (
            f"Does the implementation satisfy criterion {slot.index} of {issue_id}?\n\n"
            f"Criterion: {slot.source_text}\n\n"
            "Answer YES only if the evidence clearly shows the criterion is met.\n"
            "Answer NO if the evidence clearly shows the criterion is not met.\n"
            "Answer CANNOT JUDGE if the evidence is missing or ambiguous — do not guess.\n"
            "Provide a one-sentence reason citing the observed evidence."
        )
        states[slot.state_name] = StateConfig(
            action=action_text,
            action_type="prompt",
            timeout=_STATE_TIMEOUT,
            evaluate=EvaluateConfig(type="llm_structured", prompt=eval_prompt),
            capture=slot.state_name,
            on_yes=next_state,
            on_no=next_state,
            on_partial=next_state,
            on_error=next_state,
            on_blocked=next_state,
        )
    states["verify-aggregate"] = _aggregate_state(
        entries=[(slot.state_name, slot.state_name) for slot in criteria],
        on_yes="done",
        on_no="failed",
    )
    states["done"] = StateConfig(terminal=True)
    states["failed"] = StateConfig(terminal=True, failure=True)
    return states


# (name, probe_class, result_file, verb, instructions, evidence_ref) — the fixed 3-probe
# template this module generates (skills/verify-issue-loop/templates.md is a stub pointing
# here post-FEAT-2948; there is no separate template to stay in sync with).
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
    """Build the fixed 3-probe adversarial template (emitted verbatim, no per-issue variation).

    ENH-3200: same no-short-circuit treatment as `_criteria_states()`. Every
    probe verdict (yes/no/partial/error/blocked) routes to the next probe
    instead of `on_no` terminating at `failed_with_finding`. `count_probes`
    keeps its existing file-count gate (unchanged: still requires all 3 probe
    result files to exist) but now routes its on_yes to the new aggregate
    state instead of `done`; the aggregate derives pass/fail from every
    probe's captured verdict.
    """
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
            capture=name,
            on_yes=next_state,
            on_no=next_state,
            on_partial=next_state,
            on_error=next_state,
            on_blocked=next_state,
        )

    states["count_probes"] = StateConfig(
        action="ls \"${context.run_dir}\"/probe-*.json 2>/dev/null | wc -l | tr -d ' '\n",
        action_type="shell",
        evaluate=EvaluateConfig(type="output_numeric", operator="ge", target=3),
        on_yes="probe-aggregate",
        on_no="failed_too_few",
    )
    states["probe-aggregate"] = _aggregate_state(
        entries=[(name, name) for name in names],
        on_yes="done",
        on_no="failed_with_finding",
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
            "failure modes. Every probe runs regardless of an earlier probe's verdict "
            "(ENH-3200); FAIL fires when fewer than 3 probe classes are genuinely attempted "
            "(count_probes gate) or when any probe found a genuine break "
            "(probe-aggregate).\n"
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
            "Walks every acceptance criterion, regardless of an earlier criterion's verdict "
            "(ENH-3200); the aggregate state reports every criterion that did not pass.\n"
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
