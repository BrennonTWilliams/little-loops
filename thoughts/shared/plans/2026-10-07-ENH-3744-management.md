# ENH-3744: Semantic usage-candidate proof, derive-gap retention and prune veto

## Approach
1. `session_store/usage_proof.py` (pure): shared Claude/Codex recognition seams
   (`recognize_claude_usage`, `codex_components`, `codex_count_signature`,
   `is_adjacent_record`, `is_codex_native_record`), `UsageReplayFailure`,
   `UsageCandidateProof`, `inspect_usage_candidates`, `PROOF_IDENTITY_PATHS`.
2. `session_store/usage_proof_scope.py` (storage adapter): bounded whole-scope collection
   (10,000 items / 64 MiB encoded / 64 MiB decoded, private), total decode adapter,
   related-source rows and observations selected by native identity and exact raw links.
3. `writers.py`: `normalize_host_usage` and the Codex helpers delegate to the shared seams;
   `usage_replay_record_from_row` factors record construction. No writer behavior change.
4. `lifecycle.py`: `_plan_raw_prune` gains a per-source semantic veto (both branches),
   supplier-protection check and dry-run overlay; `prune` commits one source per
   `BEGIN IMMEDIATE`, fail-fast with a bounded note.
5. Tests (`test_enh3744_usage_candidate_proof.py`) + docs (API, CLI, HISTORY_SESSION_GUIDE).

## Decisions (no open questions)
- Claude keyed dominance mirrors the writer (highest raw ID wins) but is only accepted when
  it also agrees with native position inside its source; cross-source value conflicts are
  unprovable (order across sources is unproven).
- Codex order is proven only from strictly increasing positions that agree with raw-ID order.
- Reasons: `usage_derive_gap`, `usage_proof_unprovable`, `usage_proof_limit`.
