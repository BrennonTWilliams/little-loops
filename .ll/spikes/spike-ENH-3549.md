# Spike Plan: ENH-3549 — read-side divergent fakes on the session seam

## Context
Outcome confidence 52. Risk (a): no precedent injects a fake host into session discovery — fakes are runner-side only (`_HOST_RUNNER_REGISTRY`/`TEST_ONLY_HOSTS`); no test patches `_PARSERS`/`_REGISTERED_HOSTS`. Risk (b): no test drives the read side with two divergently shaped hosts, so the AC "divergent fakes pass on the read side" has no proven fixture mechanism.

## Approach
Register two fake hosts (`fake`, `fake-minimal`, deliberately different JSONL shapes) on the real seam via test-scoped `monkeypatch` (`_PARSERS`, `_REGISTERED_HOSTS`, `_LAYOUT_HOSTS`, `_project_folder_for_layout_host`, `writers.host_layout_for`), write fixture transcripts under a fake home, and drive the unmodified `detect_sessions` / `iter_events` / `explain_no_sessions`. Host-specific text extraction stays outside the seam (no common record abstraction).

## Critical files
`scripts/little_loops/session_store/sessions.py` (registries, `detect_sessions`, `iter_events`, `explain_no_sessions`), `session_store/writers.py:host_layout_for`, `scripts/tests/conformance/test_host_composition.py` (`_FAKES`).

## Implementation
```
scripts/tests/spike/enh3549_read_side_fake_hosts/
├── __init__.py
├── fake_read_hosts.py            # writers, parsers, install_fake_read_hosts(monkeypatch), read_prompts
└── test_read_side_fake_hosts.py  # AC tests
```

## Acceptance Criteria → Test Table
| Test | Retires | Kind |
|------|---------|------|
| `test_fakes_unknown_to_seam_without_install` | patches are the only thing registering fakes | behavior |
| `test_both_fakes_discovered_via_real_detect_sessions` / `test_union_discovery_carries_both_fake_hosts` | risk (a): injection into discovery works | behavior |
| `test_divergent_shapes_yield_same_observation` | risk (b): read side host-agnostic | behavior |
| `test_raw_payloads_really_diverge` | fakes genuinely divergent | behavior |
| `test_real_hosts_still_resolve_with_fakes_installed` | injection does not break real hosts | behavior |
| `test_explain_no_sessions_survives_fake_registration` / `test_fake_host_absence_is_named_not_empty` | named-cause warning intact | behavior |
| `test_patches_undone_after_test` | no registry leak | regression |
| `test_spike_does_not_edit_production_registries` | isolation guard (AST) | regression |

## Verification
```bash
python -m pytest scripts/tests/spike/enh3549_read_side_fake_hosts/ -v
python -m pytest scripts/tests/test_session_discovery.py scripts/tests/test_cli_ctx_stats.py scripts/tests/test_cli_messages.py scripts/tests/conformance/test_host_composition.py -v
```

## Out of Scope
Parsers for real hosts, `ll-ctx-stats` provenance, the `.claude/projects` gate, modifying any production file.

## Promotion
Fold `install_fake_read_hosts` and the fake writers/parsers into `scripts/tests/conformance/` (beside `test_host_composition.py`) in a separate PR; the `_FAKES` tuple there drives the parametrization.
