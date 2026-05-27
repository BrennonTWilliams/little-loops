---
id: FEAT-1739
type: FEAT
priority: P3
status: open
captured_at: '2026-05-27T18:08:06Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
relates_to:
- EPIC-1694
- FEAT-1695
- FEAT-1696
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

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-27T18:08:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55979bca-15d7-443c-b4d3-a76d29148106.jsonl`
