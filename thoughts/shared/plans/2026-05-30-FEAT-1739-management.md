# Implementation Plan: FEAT-1739 — learning-tests-audit Loop

## Summary

Create `scripts/little_loops/loops/learning-tests-audit.yaml` — an FSM loop that scans the Learning Test Registry for stale records via a three-phase detection pipeline, bulk-marks stale records, and produces a triage report.

## Design Decisions

All decisions made autonomously per `--gates` not set:

- **Fragment usage**: `shell_exit` for list_records/enumerate_installed, `llm_gate` for classify_packages/build_report, explicit evaluators for check_versions and mark_stale_candidates (need output_json, not exit_code or llm_structured).
- **Context**: Include `stale_after_days` defaulting to "30" (from LearningTestsConfig) as a pre-filter optimization.
- **Registry error handling**: Gracefully degrade — registry unavailable → `stale_candidate: false` with detection_note.
- **Category**: `api-adoption` (consistent with adopt-third-party-api and integrate-sdk).
- **Report path**: Two-state pattern (shell state computes dated path, prompt state writes report) following evaluation-quality.yaml.

## Implementation Phases

### Phase 0: Plan Document (this file)
- [x] Write implementation plan

### Phase 1: Loop YAML
- [ ] Create `scripts/little_loops/loops/learning-tests-audit.yaml` with 7 states + done_empty

### Phase 2: Tests
- [ ] Add `"learning-tests-audit"` to `expected` set in `test_expected_loops_exist`
- [ ] Add `TestLearningTestsAuditLoop` test class

### Phase 3: Documentation
- [ ] Update `scripts/little_loops/loops/README.md` — add row under API Adoption
- [ ] Update `docs/guides/LOOPS_GUIDE.md` — add row under API Adoption
- [ ] Update `docs/guides/LEARNING_TESTS_GUIDE.md` — add Troubleshooting note
- [ ] Update `docs/ARCHITECTURE.md` — add cross-reference in Learning Test Registry section
- [ ] Update `docs/reference/CONFIGURATION.md` — add consumer note for stale_after_days
- [ ] Update `README.md` — loop count 58 → 59
- [ ] Update `CONTRIBUTING.md` — loop count 59 → 60

### Phase 4: Validation
- [ ] Run `ll-loop validate learning-tests-audit`
- [ ] Run `python -m pytest scripts/tests/test_builtin_loops.py -v`
- [ ] Run full test suite

## State Topology

```
list_records (shell_exit)
  → on_yes: enumerate_installed
  → on_no:  done_empty

enumerate_installed (shell_exit)
  → on_yes: classify_packages
  → on_no:  classify_packages  # empty installs is fine

classify_packages (llm_gate)
  → action: map target strings → {target, slug, package, ecosystem}
  → on_yes: check_versions
  → on_no:  check_versions  # classification can't fail, always proceed
  → on_partial: classify_packages  # retry once

check_versions (shell, output_json)
  → on_yes: mark_stale_candidates  # stale_count > 0
  → on_no:  build_report          # no stale candidates

mark_stale_candidates (shell, output_json)
  → on_yes: build_report  # marked > 0
  → on_no:  build_report  # nothing marked

build_report (llm_gate)
  → on_yes: done
  → on_no:  done  # report was written regardless

done (terminal)
done_empty (terminal)
```
