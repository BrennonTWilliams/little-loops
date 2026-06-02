---
id: FEAT-1739
title: "`learning-tests-audit` loop \u2014 stale record detection and triage report"
type: FEAT
priority: P3
status: done
captured_at: '2026-05-27T18:08:06Z'
completed_at: '2026-05-31T04:36:48Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
relates_to:
- EPIC-1694
- FEAT-1695
- FEAT-1696
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1739: `learning-tests-audit` loop — stale record detection and triage report

## Summary

Add `scripts/little_loops/loops/learning-tests-audit.yaml` — an FSM loop that scans `.ll/learning-tests/` for all records, detects stale records via a three-phase detection pipeline (LLM-assisted package classification → batch enumeration of installed packages → PyPI/npm registry release-date comparison), bulk-marks stale records via `ll-learning-tests mark-stale`, and produces a triage report covering: records newly marked stale, records already stale, refuted records still pending action, and proven records with `untested` assertions that were never resolved.

## Current Behavior

When a dependency bumps (e.g. `anthropic==0.52.0` → `0.53.0`), there is no automated way to detect that the corresponding learning test records may now be stale. The developer must manually notice the version change and call `ll-learning-tests mark-stale "<target>"` for each affected record. Unnoticed stale records lead to integration code built against the old proven shapes.

There is also no aggregated view of the registry's health: refuted records that were never acted on, proven records whose `untested` assertions are still open TODOs, and records that have never been re-exercised after a dependency upgrade.

## Expected Behavior

```bash
# Run periodically or before sprint planning
ll-loop run learning-tests-audit
```

The loop:

1. `list_records` (shell) — runs `ll-learning-tests list` and emits the full record set as JSON.
2. `enumerate_installed` (shell) — runs `pip list --format=json` and `npm ls --json --depth=0` once to get a map of all installed packages and their current versions. Emits `{pip: [{name, version}], npm: {<pkg>: {version}}}`.
3. `classify_packages` (prompt) — takes the list of proven records' target strings plus the installed package map as context; uses the LLM to map each target string to its canonical installable package name and ecosystem (`pip`/`npm`/`unknown`). Emits `[{target, slug, package, ecosystem}]`. The LLM resolves ambiguities using the installed package list (e.g. `anthropic-sdk-streaming` → `{package: "anthropic", ecosystem: "pip"}`; `@anthropic-ai/sdk tool_use` → `{package: "@anthropic-ai/sdk", ecosystem: "npm"}`). Records with `ecosystem: unknown` are skipped in the next step.
4. `check_versions` (shell) — for each classified record with a known ecosystem, (a) looks up its installed version from the `enumerate_installed` output, (b) queries the PyPI JSON API (`https://pypi.org/pypi/<pkg>/json`) or npm registry (`https://registry.npmjs.org/<pkg>`) to get per-version publish dates, (c) collects all versions published after the record's `date` field. If any newer version exists: `stale_candidate: true` with `newer_versions: [list]`. If the registry API is unreachable or the package isn't found: `stale_candidate: false`, `detection_note: "registry unavailable"` — no false positives. Emits `[{target, slug, package, installed_version, newer_versions, stale_candidate, detection_note}]`.
5. `mark_stale_candidates` (shell) — for each `stale_candidate: true` entry, calls `ll-learning-tests mark-stale "<target>"`. Emits a count of records marked.
6. `build_report` (prompt) — reads `ll-learning-tests list` again (reflecting newly stale records), then writes `.loops/runs/learning-tests-audit/report-<timestamp>.md` with four sections:
   - **Newly stale** — records just marked stale by this run
   - **Already stale** — records with `status: stale` before this run
   - **Refuted** — records with `status: refuted` that have no follow-up action on record
   - **Open TODOs** — proven records with at least one assertion whose `result: untested`
7. `done` (terminal) — prints report path.

## Motivation

- **No stale-detection automation exists.** When a dependency bumps, records silently become out-of-date. This loop closes that gap by running version checks and marking stale atomically.
- **Aggregated registry health.** `ll-learning-tests list` exists but gives no triage signal. The loop's report is the "sprint start checklist" for LT registry maintenance.
- **`untested` assertions are structured TODOs that rot.** Records whose `--assume` claims were never upgraded to `pass`/`fail` are invisible without an audit pass. The loop surfaces them.

## Use Case

A developer runs `learning-tests-audit` at the start of a sprint. The loop classifies `anthropic-sdk-streaming` → `{package: "anthropic", ecosystem: "pip"}`, finds `anthropic 0.53.0` installed, and queries the PyPI API to discover that `anthropic 0.51.0` and `0.52.0` were released after the record date of 2026-04-10. The record is marked stale. The report shows:

- **Newly stale**: `anthropic-sdk-streaming` (installed: 0.53.0, newer since 2026-04-10: [0.51.0, 0.52.0, 0.53.0])
- **Refuted**: `stripe-webhook-signature-verification` (never acted on after refuted 2026-03-15)
- **Open TODOs**: `claude-api-tool-use` — 2 assertions with `result: untested` since 2026-04-22

The developer re-runs `/ll:explore-api "Anthropic SDK streaming"` to refresh the stale record, investigates the refuted Stripe record, and either proves or closes the two untested tool-use assertions.

## Proposed Solution

```
list_records (shell)
  → ll-learning-tests list → capture: records
  evaluate: output_json .length gt 0
  on_yes: enumerate_installed
  on_no:  done_empty   # no records at all → trivial done

enumerate_installed (shell)
  → pip list --format=json; npm ls --json --depth=0
  → emit {pip: [{name, version}], npm: {<pkg>: {version}}}
  capture: installed
  next: classify_packages

classify_packages (prompt)
  → input: proven records' target strings + installed package map
  → output: [{target, slug, package, ecosystem: "pip"|"npm"|"unknown"}]
  evaluate: output_json .length >= 0   # always passes; classification can't fail
  next: check_versions

check_versions (shell)
  → python3 inline:
      for each record with ecosystem != "unknown":
        installed_version = installed[ecosystem][package]
        if ecosystem == "pip":
          data = GET https://pypi.org/pypi/<package>/json
          newer = [v for v, info in data["releases"].items()
                   if info[0]["upload_time"] > record["date"]]
        else:  # npm
          data = GET https://registry.npmjs.org/<package>
          newer = [k for k, v in data["time"].items()
                   if k not in ("created","modified") and v > record["date"]]
        stale_candidate = bool(newer)
        # on registry error: stale_candidate=false, detection_note="registry unavailable"
  capture: version_check
  next: mark_stale_candidates

mark_stale_candidates (shell)
  → python3 inline: iterate version_check output; for stale_candidate=true,
    run ll-learning-tests mark-stale "<target>" via subprocess
  capture: stale_result
  next: build_report

build_report (prompt)
  → re-reads ll-learning-tests list (reflects newly stale),
    writes .loops/runs/learning-tests-audit/report-<timestamp>.md
    (newly stale entries include newer_versions list from version_check)
  next: done

done (terminal)
done_empty (terminal)
```

**Detection pipeline:** Three stages replace the old first-token heuristic:

1. **`enumerate_installed`** — one batch call each to `pip list` and `npm ls` gives all installed packages with versions; no per-record subprocess calls.
2. **`classify_packages`** — LLM maps human-readable target strings to canonical package names using the installed package list as disambiguation context. Handles compound slugs (`anthropic-sdk-streaming` → `anthropic`), namespaced packages (`@anthropic-ai/sdk`), and multi-word descriptions (`Stripe webhook signature` → `stripe`). Records mapped to `ecosystem: unknown` are skipped — no false stale-marks.
3. **`check_versions`** — queries PyPI (`https://pypi.org/pypi/<pkg>/json`) or npm registry (`https://registry.npmjs.org/<pkg>`) to get per-version publish dates. Compares against the record's `date` field to find versions released after the record was written. Registry API errors degrade gracefully to `stale_candidate: false` with a `detection_note`.

## Integration Map

### Files to Create
- `scripts/little_loops/loops/learning-tests-audit.yaml` — new FSM loop YAML (7 states)

### Files to Modify
- `scripts/tests/test_builtin_loops.py` — add `"learning-tests-audit"` to `expected` set in `test_expected_loops_exist()` (line ~68); add `TestLearningTestsAuditLoop` structural test class
- `scripts/little_loops/loops/README.md` — add `learning-tests-audit` row under "API Adoption" section (between `integrate-sdk` and `proof-first-task`)
- `docs/guides/LOOPS_GUIDE.md` — add row under "API Adoption" section
- `docs/guides/LEARNING_TESTS_GUIDE.md` — add note under "Troubleshooting" section
- `README.md` — update loop count (58 → 59)
- `CONTRIBUTING.md` — update loop count (59 → 60)

### Integration Surface
- `scripts/little_loops/learning_tests.py` — registry module:
  - `list_records(base_dir)` (line 117) — returns `list[LearnTestRecord]`; used by `list_records` state
  - `mark_stale(target_slug, base_dir)` (line 130) — patches `status: stale` via `update_frontmatter()`; used by `mark_stale_candidates` state
  - `check_learning_test(target, base_dir)` (line 140) — slugifies target then calls `read_record()`
  - `LearnTestRecord` dataclass (line 45) — fields: `target`, `date`, `status`, `assertions`, `raw_output_path`
  - `Assertion` dataclass — fields: `claim`, `result` (`"pass"` | `"fail"` | `"untested"`)
- `scripts/little_loops/cli/learning_tests.py` — CLI entry point:
  - `cmd_list()` — `ll-learning-tests list` outputs JSON array of all records
  - `cmd_mark_stale()` — `ll-learning-tests mark-stale <target>` patches one record; exit 1 if target not found
  - `cmd_check()` — `ll-learning-tests check <target>` outputs single record as JSON; exit 1 if not found

### Similar Patterns
- `scripts/little_loops/loops/issue-staleness-review.yaml` — closest analog: discovers stale items via shell command, reviews with prompt, routes to action (close/reprioritize). Same "scan → evaluate → act → loop" shape.
- `scripts/little_loops/loops/dead-code-cleanup.yaml` — scan-and-report pattern: `count_findings` state uses `output_json` on shell-generated JSON to gate on zero vs non-zero findings.
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — extensively calls `ll-learning-tests check` from shell states via `subprocess.run()` in Python heredocs.

### FSM Schema Reference
- `scripts/little_loops/fsm/schema.py` — `FSMLoop`, `StateConfig`, `EvaluateConfig` dataclasses
- `scripts/little_loops/fsm/evaluators.py` — 9 evaluator types: `exit_code`, `output_json`, `output_contains`, `output_numeric`, `llm_structured`, `convergence`, `diff_stall`, `mcp_result`, `harbor_scorer`
- `scripts/little_loops/fsm/validation.py` — `load_and_validate()` enforces required fields, state reachability, evaluator field requirements

### Tests
- `scripts/tests/test_builtin_loops.py` — structural test class pattern: `TestEvaluationQualityLoop` (line 403) with `LOOP_FILE`, `data` fixture, and assertions for required states, terminal flags, capture names, routing edges, evaluator types
- `scripts/tests/test_learning_tests.py` — existing `mark_stale` tests (line 167); no new tests needed for the registry module
- `scripts/tests/test_cli_learning_tests.py` — existing CLI tests for `check`, `list`, `mark-stale` (line 128); no new CLI tests needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::test_all_validate_as_valid_fsm` — automatically exercises the new loop once the YAML file exists; validates FSM structure, state reachability, and evaluator field requirements
- `scripts/tests/test_builtin_loops.py::test_all_parse_as_yaml` — validates the new loop parses as valid YAML
- `scripts/tests/test_builtin_loops.py::test_all_have_description_field` — validates the loop has a `description:` field (ENH-1331 regression guard)
- No changes needed to `test_learning_tests.py`, `test_cli_learning_tests.py`, `test_learning_state.py`, `test_config.py`, `test_config_schema.py`, `test_feat1287_doc_wiring.py`, `test_feat1743_configure_wiring.py`, `test_feat1756_init_wiring.py`, `test_feat1743_init_wiring.py`, `test_extension.py`, `test_fsm_schema.py`, `test_fsm_executor.py`, `test_ll_loop_execution.py`, `test_cli.py`, or `test_ll_loop_integration.py` — the loop uses shell states calling the existing `ll-learning-tests` CLI, which none of these tests modify

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add `learning-tests-audit` row under "API Adoption" section
- `docs/guides/LEARNING_TESTS_GUIDE.md` — add troubleshooting note pointing to this loop for bulk staleness management
- `scripts/little_loops/loops/README.md` — add `learning-tests-audit` row under "API Adoption" section
- `docs/reference/CLI.md` — no changes expected (loop invoked via `ll-loop run`, no new CLI surface)
- `docs/ARCHITECTURE.md` — add one-line cross-reference in Learning Test Registry section (~line 1152) pointing to `ll-loop run learning-tests-audit` for automated staleness detection [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — note `learning-tests-audit` loop as a consumer of `stale_after_days` in the setting description (~line 637) [Agent 2 finding]

### Downstream Consumers (no changes needed)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/verify_learning_citations.sh` — reads `status:` from record YAML frontmatter (line 65); after the loop marks records stale, this script will correctly reject them (exit 1) — desired behavior, no change needed
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — calls `ll-learning-tests check` from shell states; if the audit loop marks records stale, the gate will trigger re-exploration — intended cascading behavior
- `skills/explore-api/SKILL.md` — Phase 1 treats `status: stale` records as needing re-exploration; bulk-marking from the audit loop increases re-exploration frequency — intended behavior, no change needed

## Implementation Steps

1. Draft `scripts/little_loops/loops/learning-tests-audit.yaml` with the seven-state design above.
2. Wire `enumerate_installed` as a shell state: `pip list --format=json 2>/dev/null` and `npm ls --json --depth=0 2>/dev/null`; merge into `{pip: [...], npm: {...}}` JSON. Emit empty maps on failure (not an error).
3. Wire `classify_packages` as a prompt state: pass proven records' target strings + the `enumerate_installed` output as context; prompt must emit `[{target, slug, package, ecosystem}]` JSON array. Evaluate with `output_json .length >= 0`.
4. Wire `check_versions` as a shell state with inline Python:
   - For each entry with `ecosystem != "unknown"`, look up installed version from `enumerate_installed` dict lookup (O(1)).
   - Fetch PyPI or npm registry JSON; filter versions by upload/publish date > record date.
   - On `urllib.error.URLError` or HTTP error: set `stale_candidate: false`, `detection_note: "registry unavailable"`.
5. Wire `mark_stale_candidates` to call `ll-learning-tests mark-stale` for each `stale_candidate: true` entry via `subprocess.run`.
6. Author `build_report` prompt with the four-section template; newly stale entries should include `newer_versions` list.
7. Pre-create `.loops/runs/learning-tests-audit/` in a `build_report` pre-step or via a preceding shell state.
8. Run `ll-loop validate learning-tests-audit` until no ERRORs.
9. Update `scripts/tests/test_builtin_loops.py` — add `"learning-tests-audit"` to `expected` set and add `TestLearningTestsAuditLoop` structural test class with state assertions for all seven states.
10. Update loop counts in `README.md` and `CONTRIBUTING.md`.
11. Add row to `docs/guides/LOOPS_GUIDE.md` under "API Adoption" section.
12. Add a note to `docs/guides/LEARNING_TESTS_GUIDE.md` under "Troubleshooting" pointing to this loop for bulk staleness management.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. Update `scripts/little_loops/loops/README.md` — add a `learning-tests-audit` row under the "API Adoption" table (between `integrate-sdk` and `proof-first-task`), following the same `| \`loop-name\` | Description |` format.
14. Update `docs/ARCHITECTURE.md` — add a one-line cross-reference in the Learning Test Registry section (~line 1152) pointing to `ll-loop run learning-tests-audit` for automated bulk staleness detection.
15. Update `docs/reference/CONFIGURATION.md` — note `learning-tests-audit` loop as a consumer of `stale_after_days` in the setting description (~line 637).

### Verification Phase (added by `/ll:wire-issue`)

_These integration checks were identified by wiring analysis and should be verified after implementation:_

16. Verify `verify_learning_citations.sh` correctly rejects records the loop marks stale — run the loop against a test record with a known-older version, then run `bash scripts/verify_learning_citations.sh` and confirm exit 1 for the stale record.
17. Verify the per-loop validation sweep (`test_all_validate_as_valid_fsm`, `test_all_parse_as_yaml`, `test_all_have_description_field`) passes with the new loop YAML in place — these tests automatically pick up new `.yaml` files in the built-in loops directory.
18. Verify `test_expected_loops_exist` passes after adding `"learning-tests-audit"` to the expected set — strict set equality, no other loop names should be present or missing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1-2 (loop YAML + enumerate_installed):** Follow existing shell-state patterns in `ready-to-implement-gate.yaml:15-21` (Python heredoc producing JSON). Use `mkdir -p .loops/tmp` in shell actions following convention in `evaluation-quality.yaml:51`. The `enumerate_installed` state should emit `{pip: [...], npm: {...}}` as a single JSON object via `python3 << 'PYEOF'`.
- **Step 3 (classify_packages prompt):** Model after `backlog-flow-optimizer.yaml:34-61` (diagnostic tag emission). Inject captured data via `${captured.enumerate_installed.output}`. Use `evaluate: {type: output_json, path: ".length", operator: gte, target: 0}` for the routing gate — classification always produces output, so this always routes to `on_yes`.
- **Step 4 (check_versions shell):** Use Python heredoc pattern (`python3 << 'PYEOF'`) from `adopt-third-party-api.yaml:59-88`. Inject `${captured.classify_packages.output}`. Call `urllib.request.urlopen()` for PyPI/npm APIs. On `URLError`, set `stale_candidate: false, detection_note: "registry unavailable"`.
- **Step 5 (mark_stale_candidates shell):** Use `subprocess.run(["ll-learning-tests", "mark-stale", target])` pattern from `ready-to-implement-gate.yaml:33-43`. Capture results as JSON for the report.
- **Step 6 (build_report prompt):** Model after `evaluation-quality.yaml:167-195` (report writing via prompt state). Pre-create output directory with `mkdir -p .loops/runs/learning-tests-audit/` in a preceding shell action or inline in the prompt state action.
- **Step 9 (tests):** Follow `TestEvaluationQualityLoop` class structure at `test_builtin_loops.py:403-498`: `LOOP_FILE` class attribute, `data` fixture with `yaml.safe_load()`, and assertions for required states, terminal flag, capture names, routing edges (`on_yes`/`on_no`/`on_error`), evaluator types/operators/targets, fragment usage, and action string contents.
- **Loop metadata conventions:** Set `category: "api-adoption"` (consistent with `adopt-third-party-api.yaml` and `integrate-sdk.yaml`). Include `max_iterations`, `timeout`, and `on_handoff: spawn` as standard top-level fields. Set `description` — required for built-in loops per ENH-1331 regression guard (tested in `test_all_have_description_field()`).
- **Validation pitfalls:** `ll-loop validate` enforces evaluator field requirements — `output_json` needs `path`, `operator`, `target`. Prompt states need `on_error` and `on_blocked` routing. Shell actions must escape bare `${VAR}` as `$${VAR}` (BUG-1675 regression guard tested in `test_no_bare_bash_variable_in_shell_actions()`).
- **Fragment library (`lib/common.yaml`):** `list_records` and `enumerate_installed` can use `fragment: shell_exit` from `lib/common.yaml:14-21` to simplify YAML — the fragment provides `action_type: shell` + `evaluate: {type: exit_code}`. State only needs to supply `action`, `on_yes`, `on_no`, and optionally `on_error`/`timeout`. Import with `import: [lib/common.yaml]` at the loop top level. Other useful fragments: `retry_counter` (exponential backoff), `llm_gate` (LLM-structured yes/no), `numeric_gate` (output_numeric comparison), `with_throttle` (tool-call rate limiting).
- **`mark_stale` CLI slugify behavior:** `cmd_mark_stale()` at `cli/learning_tests.py:32-41` calls `mark_stale(slugify(args.target))` — slugification is applied internally by the CLI. The `mark_stale_candidates` shell state must pass the **raw target string** (from `classify_packages` output) directly to `subprocess.run(["ll-learning-tests", "mark-stale", target])`, NOT a pre-slugified value. Double-slugifying would produce incorrect paths.
- **`subprocess.run` conventions:** Use `check=False` to prevent `CalledProcessError` on non-zero exit codes (the CLI returns exit 1 when target not found). Use `capture_output=True, text=True` for stdout/stderr capture. Always emit valid JSON to stdout even on error paths — never let a Python traceback reach the FSM evaluator.
- **`output_json` path conventions:** Object key paths use `.` prefix (`.count`, `.verdict`, `.stale_count`). `output_length` is a built-in special field without dot prefix (used in `assumption-firewall.yaml:183` as `path: output_length` to check array length). Confirmed across 11 evaluator configurations in built-in loops.

_Added by `/ll:refine-issue` 2026-05-30 — second research pass:_

- **`stale_after_days` config integration:** `LearningTestsConfig` at `config/features.py:345` exposes `stale_after_days: int = 30`. This is a time-based staleness threshold separate from the loop's version-check pipeline. The loop could use it as a pre-filter (skip records newer than `stale_after_days` — they can't be stale yet) to reduce registry API calls. It could also serve as a fallback detection method: if the registry API is unreachable, check `(today - record.date) > stale_after_days` as a coarse signal. Config is accessible via `${context.learning_tests.stale_after_days}` when the loop YAML declares it in `context:`.
- **Fragment library applicability by state:** Each state maps to a specific `lib/common.yaml` fragment:
  - `list_records` → `fragment: shell_exit` (shell command, exit-code evaluation, no `output_json` needed)
  - `enumerate_installed` → `fragment: shell_exit` (shell command that always succeeds; `on_no` routes to a degrade path rather than an error terminal)
  - `classify_packages` → `fragment: llm_gate` (prompt state with `llm_structured` evaluator; state supplies `action` + `evaluate.prompt`; the fragment provides `action_type: prompt` + `evaluate.type: llm_structured`)
  - `check_versions` → cannot use `shell_exit` because it needs `output_json` evaluation (`.stale_count > 0`), not exit-code. Use explicit `action_type: shell` + `evaluate: {type: output_json, path: ".stale_count", operator: gt, target: 0}`
  - `mark_stale_candidates` → `fragment: numeric_gate` could work with `path: ".marked"` but easier to use explicit `output_json` since it also needs to capture results for the report. Use explicit `action_type: shell` + `evaluate: {type: output_json}`.
  - `build_report` → `fragment: llm_gate` (prompt state routing on yes/no); the fragment provides `action_type: prompt` + `evaluate.type: llm_structured`. The state supplies the report-writing prompt as `action` and a yes/no question as `evaluate.prompt`. Follow `evaluation-quality.yaml:159-195` two-state pattern: a shell state computes the report path (`mkdir -p .loops/runs/learning-tests-audit/ && echo ".loops/runs/learning-tests-audit/report-$(date +%Y-%m-%dT%H%M%S).md"`), then the prompt state writes to `${captured.report_path.output}`.
- **`min_confidence: 0.5` convention:** The standard threshold for `llm_structured` evaluators on JSON validation prompts across built-in loops (`adopt-third-party-api.yaml:56`, `assumption-firewall.yaml:46`). Use this for `classify_packages` and `build_report` evaluators.
- **PyPI API response structure for `check_versions`:** `GET https://pypi.org/pypi/<package>/json` returns `{"releases": {"0.52.0": [{"upload_time": "2026-04-15T10:30:00"}], ...}}`. Each release key maps to a list of distribution metadata dicts; `[0]["upload_time"]` is the ISO 8601 upload timestamp. The npm registry returns `{"time": {"0.52.0": "2026-04-15T10:30:00.000Z", "created": "...", "modified": "..."}}` — filter out `"created"` and `"modified"` keys when iterating versions. Both APIs return ISO 8601 strings that support lexicographic comparison with record `date` strings (YYYY-MM-DD). For comparison: `if version_date[:10] > record["date"]` catches any version published on a day after the record date.
- **`llm_structured` `on_partial` routing:** `fix-quality-and-tests.yaml:25` demonstrates the `on_partial` routing key for `llm_structured` evaluators — used when the LLM confidence is between `min_confidence` and a higher threshold. For `classify_packages`, add `on_partial: classify_packages` (retry once) to handle ambiguous package mappings.
- **Shell variable escaping in YAML:** `$` in shell actions must be escaped as `$$` within YAML double-quoted strings to prevent YAML from interpreting them as anchors (BUG-1675 regression, tested by `test_no_bare_bash_variable_in_shell_actions()` at `test_builtin_loops.py:156`). Within single-quoted heredocs (`<< 'PYEOF'`), bash does NOT expand variables, so Python `$` usage is safe — but `${context.x}` and `${captured.y.z}` are FSM template variables resolved before the heredoc reaches bash, not bash variables. No escaping needed for FSM template variables.

## Acceptance Criteria

- `scripts/little_loops/loops/learning-tests-audit.yaml` exists and `ll-loop validate learning-tests-audit` reports no ERRORs.
- `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` passes with `"learning-tests-audit"` in `expected`.
- When records exist: loop produces a report at `.loops/runs/learning-tests-audit/report-<timestamp>.md`.
- When no records exist: loop routes to `done_empty` without error.
- Records whose package has had a new version published after the record's `date` field are marked `stale`. The newly stale report entry includes the list of newer version strings.
- Report contains four sections: newly stale, already stale, refuted, open TODOs.
- `classify_packages` correctly maps compound slugs and multi-word target strings to installable package names (e.g. `anthropic-sdk-streaming` → `anthropic`).
- Records with `ecosystem: unknown` are not marked stale — no false positives when the target has no detectable package.
- If the PyPI or npm registry API is unreachable, affected records are skipped (`detection_note: "registry unavailable"`) rather than false-marked stale.
- `enumerate_installed` is called once per loop run, not once per record.

## Labels

`feat`, `loop`, `learning-tests`, `fsm`, `audit`, `stale-detection`, `triage`

---

## Scope Extension

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-28): This issue's automated stale-detection pipeline intentionally extends beyond FEAT-1282's original scope boundary, which excluded "automatic staleness enforcement." The decomposed children of FEAT-1282 (FEAT-1285/1286/1287) shipped the registry infrastructure (`ll-learning-tests check`, `list`, `mark-stale` CLI) that makes automated detection feasible — the registry is no longer a raw file store but a queryable system with version metadata. This issue builds on that shipped infrastructure.

## Status

**Open** | Created: 2026-05-27 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-30_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- 7-site enumeration across 4 subsystems (loop YAML, tests, docs, root docs) — individually mechanical but breadth creates coordination risk; missing one site produces stale references
- New loop YAML gets structural validation tests but no runtime integration test — check_versions inline Python logic and classify_packages prompt quality can only be verified manually or through production use
- Change surface spans 6 existing files with varying modification types (set addition, table row, count bump, test class) — verification requires checking every site

## Session Log
- `/ll:ready-issue` - 2026-05-31T04:26:22 - `ee2d1106-3483-4188-b4d2-88a104011060.jsonl`
- `/ll:wire-issue` - 2026-05-31T03:31:18 - `99584557-a170-433a-8c61-eedd8d845509.jsonl`
- `/ll:refine-issue` - 2026-05-31T03:23:33 - `cda8a917-6813-4923-ad31-5889e7ef70df.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:confidence-check` - 2026-05-29T19:00:00Z - `6a99f544-bd0d-4ac3-a506-f33ffd4a0bf7.jsonl`
- `/ll:confidence-check` - 2026-05-30T00:00:00Z - `2210570a-56ab-4d7f-83a7-9929d3d9d025.jsonl`
- `/ll:wire-issue` - 2026-05-30T03:35:18 - `7a79d03a-934b-4752-a81b-96cb9e93728e.jsonl`
- `/ll:refine-issue` - 2026-05-30T03:27:54 - `a1d51e1b-fa76-4e37-b9b8-b2f75b1951eb.jsonl`
- `/ll:capture-issue` - 2026-05-27T18:08:06Z - `55979bca-15d7-443c-b4d3-a76d29148106.jsonl`
- `/ll:refine-issue` - 2026-05-31T02:50:00Z - `b9109a4b-4e94-4dd5-bb69-010258918170.jsonl`
- `/ll:wire-issue` - 2026-05-30T04:30:00Z - `b9109a4b-4e94-4dd5-bb69-010258918170.jsonl`
- `/ll:confidence-check` - 2026-05-30T00:00:00Z - `4d644c4c-dc2e-4c46-81ec-295af344b92f.jsonl`
