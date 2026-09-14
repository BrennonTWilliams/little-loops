---
id: 3466
title: "Goal 7 \u2014 credential-scan verification primitive (FEAT-034 extension)"
type: ENH
priority: P1
status: done
discovered_date: '2026-09-13'
labels:
- goal-7,security,verification,research-applied
decision_needed: false
learning_tests_required:
- gitleaks
verify_verdict: VALID
confidence_score: 80
outcome_confidence: 62
score_complexity: 14
score_test_coverage: 20
score_ambiguity: 10
score_change_surface: 18
size: Very Large
---

## Summary

Extend the deterministic verification-evidence bundle (FEAT-3182) with a credential-scan primitive: a gitleaks-class deterministic, non-LLM scan that re-reads evidence bundles and either passes or fails on credential/PII pattern matches.

The motivating failure class is concrete. A published 2026 academic study of scraped public agent rollouts recovered hundreds of PII artifacts and credentials from reasoning traces; in the genuine-user-session subset, 64 of 704 artifacts were **entirely absent from the visible chat history** — recoverable only from the model's hidden reasoning, restated when the model re-read the session it was asked to "clean up." A redaction catalog built around *visible* secret patterns catches zero of those. The same exposure applies to anything that stores full session lines: `raw_events.parsed_json` in `history.db` is verbatim and intentionally reasoning-preserving across hosts.

The scan is the same primitive the fine-tuning dataset export uses as its emit-gate; here it is applied longitudinally to `history.db` as a credential-leakage regression-detection signal. The evidence bundle gains a `credential_scan` entry: `{ tool, version, rules_sha, scanned_at, hits }` — so the scan is reproducible, the rule set is pinned by hash, and downstream consumers know whether a bundle is safe to redistribute.

## Design

- Deterministic and non-LLM by construction: the scan re-reads what was emitted — including any field not in the redaction catalog — and fails the bundle on a pattern match rather than trusting the upstream redaction pass.
- Tool version and `rules_sha` are recorded in the entry so two scans of the same bundle at different times are comparable, and a rule-set change is visible as a different hash rather than a silent behavior change.
- Extends FEAT-3182; does not duplicate it. The bundle is the artifact; this is one more deterministic entry in it, and the same scan then serves three consumers: the bundle entry, the export emit-gate, and the longitudinal leakage signal over `history.db`.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

No existing gitleaks-class credential scanner is invoked from Python anywhere in this repo — `gitleaks` (v8.30.1) is wired solely as a pre-commit hook against staged git diffs (`.pre-commit-config.yaml`); `grep -r gitleaks scripts/` returns zero call sites, and `verify_private_refs.py`'s own docstring already draws the boundary that gitleaks covers "credentials," not the paths/names it scans instead. Building the primitive this issue asks for means either invoking the existing pinned gitleaks binary as a subprocess, or extending the existing in-process regex scanner (`pii.py`, currently email/phone/ssn only) with credential patterns.

**Option A**: Shell out to the already-pinned `gitleaks` binary (`.pre-commit-config.yaml` pins `v8.30.1`) as a subprocess from the new evidence-bundle code path, reusing its ruleset and treating its version string as the entry's `tool`/`version` fields.

**Option B**: Extend `pii.py`'s existing in-process regex approach with a credential-pattern set (API keys, tokens, private keys), following the same deterministic-scanner shape already established by `verify_private_refs.py`/`verify_evidence.py` (frozen-dataclass rule table -> frozen-dataclass finding list -> exit-code convention), with no external binary dependency.

> **Selected:** Option B — extends `pii.py`'s in-process regex scanner, matching the deterministic rule-table → finding-list → exit-code shape already used three times in this codebase, with no new runtime dependency.

**Recommended**: Option B — this codebase's stated dependency policy (`.claude/CLAUDE.md` Code Style: "Minimize third-party dependencies") and its existing deterministic-scanner convention both favor an in-process, no-subprocess scanner; Option A also introduces a runtime dependency on gitleaks being installed wherever `ll-loop evidence` runs, which the pre-commit-only wiring today does not require.

**Open constraint** (not a decision — see Program Design): the requested `credential_scan.scanned_at` field is in tension with `EvidenceBundle`'s existing reproducibility guarantee (`canonical_json()` must be byte-identical across reruns of unchanged inputs, tested by `test_rerun_over_unchanged_inputs_is_byte_identical`; FEAT-3182 step 3e states the bundle deliberately has no timestamp field for this reason). Whoever implements this must either exclude `scanned_at` from the reproducibility-tested scope or resolve this conflict explicitly — it is not addressed by either option above.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-13.

**Selected**: Option B — Extend `pii.py`'s in-process regex approach with a credential-pattern set

**Reasoning**: Option B matches a convention independently implemented three times in this codebase (`verify_private_refs.py`, `verify_evidence.py`, `verify_skill_prose.py` — a frozen-dataclass rule table → finding-list → scan function → exit-code shape), is fully in-process and unit-testable with zero new runtime dependencies, and aligns with `.claude/CLAUDE.md`'s dependency-minimization policy. Option A would introduce the first product-code runtime dependency on an external binary the codebase's own docs classify as contributor-only tooling (`CONTRIBUTING.md`), with no existing product-code precedent for treating a subprocess exit code as a deterministic-gate verdict.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (gitleaks subprocess) | 1/3 | 2/3 | 1/3 | 0/3 | 4/12 |
| Option B (extend pii.py) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- The gitleaks-subprocess approach: zero Python call sites for gitleaks exist anywhere in `scripts/`; `CONTRIBUTING.md` states gitleaks is "repo-maintenance tooling for contributors — it is not a little-loops product feature," and the dependency-minimization policy weighs directly against a new runtime binary dependency.
- The pii.py-extension approach: the rule-table → finding-list → exit-code shape is already implemented three times (`verify_private_refs.py`, `verify_evidence.py`, `verify_skill_prose.py`); `pii.py` is the only existing in-process regex secret scanner, with 3 live call sites and a matching test convention (`test_pii.py`) — though it inherits `apply_pii_action`'s top-level-string-only scanning blind spot (misses nested chatml `messages` lists) unless explicitly addressed during implementation.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

**Predecessor verification**: `FEAT-034` (per the issue title) does not exist anywhere in this repo — no issue file, docstring, or code identifier matches that ID (repo-wide search, zero hits outside this issue's own filename). The only real predecessor this issue extends is `FEAT-3182` (`scripts/little_loops/cli/loop/evidence.py`); the "FEAT-034 extension" framing in the title is unverifiable against a concrete artifact.

**Files to Modify**
- `scripts/little_loops/cli/loop/evidence.py` — `EvidenceEntry`/`EvidenceBundle` definitions the new `credential_scan` entry must fit into. `EvidenceEntry.source` is constrained to a closed frozenset `_EVIDENTIARY_SOURCES = {"git_ref", "history_db_row", "run_dir_file"}`, test-enforced by `test_every_evidentiary_entry_traces_to_deterministic_source` (`scripts/tests/test_feat3182_evidence_bundle.py`) — a `credential_scan` entry needs either a 4th source value added there or to be modeled under one of the three existing ones.
- `scripts/little_loops/pii.py` — the only existing regex-based secret scanner in the repo (`PII_PATTERNS` = email/phone/ssn only; no credential/API-key/token patterns exist anywhere in `scripts/little_loops/`).

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/cli/loop/__init__.py:1001-1006,1127-1128` — registers/dispatches `ll-loop evidence` -> `cmd_evidence()`, the sole caller of `assemble_bundle()`.
- `scripts/tests/test_feat3182_evidence_bundle.py` — `TestReproducibility.test_rerun_over_unchanged_inputs_is_byte_identical` requires `EvidenceBundle.canonical_json()` stay byte-identical across reruns of unchanged inputs; the bundle deliberately has no timestamp field today (FEAT-3182 step 3e) — a `credential_scan.scanned_at` field is in tension with this test unless scoped out of the reproducibility check.
- `scripts/little_loops/loops/sft-corpus.yaml` (`check_pii` state) — the closest existing "emit-gate" shape the issue references; it is PII-only (no credential patterns) and inline in FSM YAML, not a standalone function.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py:64,177-179` — re-exports `apply_pii_action`/`detect_pii`/`redact_pii` from `pii.py` as public package API under `# pii`. If the credential scan is exposed as a new public `pii.py` symbol, it needs the same export + `__all__` entry, following the one-symbol-per-export convention already in force here.
- `scripts/little_loops/cli/logs.py:1843-1852` — a second, previously unlisted production caller of `pii.py`: imports and calls `redact_pii(text)` directly (docstring: "Applies `pii.redact_pii` (email/phone/SSN) then `_ABS_PATH_RE`..."). Not itself a required edit (call signature is unchanged by extending `PII_PATTERNS`), but any credential-redaction behavior added to `redact_pii` flows through this call site too.
- `scripts/tests/test_extension.py:765,771,777` — `test_smoke_import_detect_pii`/`test_smoke_import_redact_pii`/`test_smoke_import_apply_pii_action`, one dedicated smoke test per exported `pii.py` symbol. A new public symbol added per the point above needs a matching smoke test here.

**Conventions in Force**
- Deterministic scan/gate CLIs in this codebase (`scripts/little_loops/cli/verify_private_refs.py`, `scripts/little_loops/cli/verify_evidence.py`) share one shape: a frozen-dataclass rule table -> frozen-dataclass finding list -> `scan_file`/`scan_all` functions returning `list[Finding]` -> exit `0` (clean) / `1` (findings) -> a tracked baseline JSON under `.ll/` for regression-only gating -> a `<!-- x-ok: reason -->`-shaped suppression comment (`ll-private-ok:` / `ll-evidence-ok:`).
- Bundle entries are plain `@dataclass` with an explicit `to_dict()`, never `TypedDict` — evidence: `EvidenceEntry`/`ContextEntry`/`GapEntry` (`cli/loop/evidence.py`); repo-wide `TypedDict` usage is limited to 2 unrelated files.
- No field literally named `rules_sha` exists anywhere in the repo. The closest analogs: per-file `content_hash` staleness hash (`scripts/little_loops/codequery/codegraph.py:_sha256_file`) and a `{version, algo}` pair gating an entire cache file (`verify_evidence.py`'s `VerdictCache`) — the two disagree on granularity (per-artifact vs. whole-file invalidation).
- Existing "tool version" precedent: `LoopRun.ll_version` (`scripts/little_loops/history_reader/models.py`) stamps the package's own version onto a persisted row — the closest analog to the requested `credential_scan.{tool, version}` pair.
- `gitleaks` (v8.30.1, `.pre-commit-config.yaml`) is the only credential scanner in the repo, wired exclusively as a pre-commit hook against staged diffs; `grep -r gitleaks scripts/` finds zero Python call sites. `scripts/little_loops/cli/verify_private_refs.py`'s own docstring states gitleaks covers "credentials," not "paths and project names" — confirming the boundary is already drawn in this codebase's own documentation, with no code-level overlap today.
- `raw_events.raw_line`/`parsed_json` are zlib-compressed BLOBs, read via `_unpack_payload()` dispatching on Python type (`scripts/little_loops/session_store/writers.py`); Codex's `parse_codex_rollout()` (`scripts/little_loops/session_store/sessions.py`) documents that `reasoning` subtype payloads pass through untouched into the stored payload — direct evidence the issue's premise (hidden reasoning reaches `raw_events.parsed_json`) holds in this codebase.

**Tests**
- `scripts/tests/test_feat3182_evidence_bundle.py` — precedent for testing a new bundle entry: a segregation invariant (nothing non-deterministic in `evidentiary`), a reproducibility test (byte-identical `canonical_json()` across reruns), a shape test (`to_dict()` plain JSON only), an allowlist test.
- `scripts/tests/test_pii.py` — existing regex-scanner test convention (class-per-function, positive/negative pairs).
- `scripts/tests/test_verify_private_refs.py` — existing deterministic-gate CLI test convention (`tmp_path` scans, `capsys` exit-code assertions, baseline-regression tests, a self-hosted "gate stays green against the real repo" test).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loops_sft_corpus.py` (`TestPiiFlagPassthrough` L528, `TestPiiRedact` L591, `TestPiiDiscard` L689, `TestPiiDefaultBehavior` L1466) — ~20 methods that shell out to the literal `python3` heredoc from `sft-corpus.yaml`'s `check_pii` state, the de facto end-to-end coverage for the PII gate. No test here asserts `PII_PATTERNS`' exact key set or length, so extending it with credential patterns is additive and won't break these — but new credential-scan behavior surfaced through this same gate should get sibling test methods/classes in this file.
- `scripts/tests/test_feat3182_evidence_bundle.py:168` (`test_carries_schema_version_and_comment_no_timestamp`) — greps only the literal keys `"ts"`/`"timestamp"`/`"generated_at"`; a field named `scanned_at` won't trip this specific assertion but directly conflicts with the design invariant it encodes ("no timestamp field exists anywhere in the shape, by design") — this test must be reconciled too, not just the byte-identical reproducibility test already cited above.
- `scripts/little_loops/cli/loop/evidence.py:27-36` (`_BUNDLE_COMMENT`) and `:116-118` (`canonical_json()` docstring) — both assert the "no timestamp field" invariant in code comments/docstrings, not just in tests or `CLI.md` prose; both need revision if `scanned_at` is added.
- Closest scan-primitive test template: `scripts/tests/test_verify_private_refs.py` — `TestStructuralRules`, `TestSuppression` (same-line/preceding-line/hash-comment/two-lines-up-negative), `TestRedaction`, `TestBaseline`, `TestCLI`, `TestRepoGate` (self-hosted gate-stays-green test with a `shutil.which(...)`-skip fixture). `pii.py` currently has no suppress-marker regex or per-line skip logic at all — if a `ll-credential-ok:`-shaped escape hatch is added, this is the pattern to follow, alongside `TestSuppressionEscapeHatch::test_counter_example_quote_flags_before_suppression` in `scripts/tests/test_verify_evidence.py:517-565` (a fixture that quotes a fake secret must still flag pre-suppression).

**Documentation**
- `docs/reference/CLI.md`, `docs/ARCHITECTURE.md` — reference FEAT-3182/`pii`/`raw_events`; no `credential_scan` mention exists yet.
- `CONTRIBUTING.md` (§ Secret Scanning (gitleaks)) — states explicitly gitleaks is "repo-maintenance tooling for contributors — it is not a little-loops product feature," relevant context for whether this issue reuses gitleaks or builds a product-facing scanner.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:60` (module table) and `:8077-8163` (`## little_loops.pii` section) — documents `PII_PATTERNS` as exactly the 3-row email/phone/ssn table with a worked example; needs a credential-patterns row/section. Previously unlisted — the issue's own Documentation subsection only named `CLI.md`/`ARCHITECTURE.md`.
- `docs/reference/API.md:4504-4568` — `EvidenceEntry`/`EvidenceBundle`/`canonical_json` API reference; needs the new `credential_scan` entry shape documented.
- `docs/reference/CLI.md:1297-1322`, specifically line ~1308, which states verbatim: *"no timestamp field exists anywhere in the shape, by design, so reruns over unchanged inputs are byte-identical"* — this sentence becomes false the moment `credential_scan.scanned_at` lands and must be revised, along with the `#### ll-loop evidence` "Bundle shape" list gaining a `credential_scan: {tool, version, rules_sha, scanned_at, hits}` clause.
- `docs/reference/loops.md:439-490` — describes the `check_pii` state, `pii_action` predicate, and `little_loops.pii.apply_pii_action()` for the sft-corpus loop; update if the gate's behavior or pattern set changes. Previously unlisted.

**Configuration**
- No `credential_scan`/`redaction`/`rules_sha` key exists in `scripts/little_loops/config-schema.json` (searched repo-wide) — a new config surface would be net-new, not an extension of an existing schema block.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

**Types**
- No literal `rules_sha` field/convention exists in the repo. Closest analogs: `content_hash` per-file hash (`scripts/little_loops/codequery/codegraph.py:_sha256_file`, full 64-char sha256 hex) and `VerdictCache`'s `{version, algo}` pair (`scripts/little_loops/cli/verify_evidence.py`) that invalidates a whole cache file, plus `blob_fp`/`wt_sha` fingerprints truncated to 16 hex chars — two different truncation conventions already coexist for sha256-based fingerprints in this codebase.
- `EvidenceEntry.source` is a closed `frozenset` literal (`_EVIDENTIARY_SOURCES = {"git_ref", "history_db_row", "run_dir_file"}`), test-enforced. A `credential_scan` entry needs to either fit one of these three or add a fourth, updating the enforcing test.

**Signatures**
- `EvidenceEntry.to_dict() -> dict[str, Any]` and `EvidenceBundle.canonical_json() -> str` (= `json.dumps(self.to_dict(), sort_keys=True, default=str)`, `scripts/little_loops/cli/loop/evidence.py`) — the existing shape a `credential_scan` entry must serialize through.
- `apply_pii_action(example: dict, action: str) -> dict | None` (`scripts/little_loops/pii.py`) — scans only top-level string values of `example` (`combined = " ".join(v for v in example.values() if isinstance(v, str))`); a nested `messages: [{"role", "content"}]` list (chatml, the sft-corpus loop's default `sft_format`) is invisible to it, since `messages` is a `list` not a `str`. This is a concrete, already-present instance of the issue's stated failure class — a scanner over rendered/top-level fields misses content a full-transcript scan would catch.
- `scan_file`/`scan_all`/`scan_paths` (`scripts/little_loops/cli/verify_private_refs.py`) — the codebase's existing deterministic-scanner signature shape: take a rule table, return `list[Finding]`; pass/fail is derived by the caller from list emptiness, not encoded on the dataclass.

**Call Path**
`ll-loop evidence <run>` -> `cmd_evidence()` -> `assemble_bundle()` -> `EvidenceBundle.to_dict()`/`canonical_json()` [existing, unchanged by this issue]. No existing call path reaches a credential scan: `gitleaks` runs only via the `.pre-commit-config.yaml` hook against staged diffs at commit time, never invoked from Python, never touches `history.db` (confirmed: zero Python call sites for `gitleaks`).

**Decision Rules**
This issue introduces a new deterministic pass/fail gate (bundle fails on a pattern match) but does not pin: (a) which scanner/pattern set runs (reuse the pinned `gitleaks` binary via subprocess vs. extend `pii.py`'s in-process regex approach), (b) the literal rule/pattern list or its `rules_sha` source, (c) an escape/suppression hatch analogous to the sibling gates' `ll-private-ok:`/`ll-evidence-ok:` comment convention. See Proposed Solution for the two viable resolutions to (a); (b) and (c) remain open for the implementer.

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- **Option B convention mismatch**: `apply_pii_action`/`detect_pii`/`redact_pii` (`scripts/little_loops/pii.py`) do not yet match the frozen-dataclass rule-table → finding-list → exit-code shape the Decision Rationale cites as the target convention. `PII_PATTERNS` is a plain `dict[str, re.Pattern[str]]` (name → compiled regex, no `rationale`/severity field, not a dataclass), and `pii.py` has no `Finding` dataclass, no `scan_file`/`scan_all` function, and no exit-code convention anywhere — `apply_pii_action()` returns a transformed/filtered dict, not a `list[Finding]`. Matching the stated convention is net-new structure to introduce (either converting `PII_PATTERNS` or adding a parallel credential rule table alongside it), not an append to the existing dict.
- **Rule-table/finding shape to match** — `verify_private_refs.py` is the closer precedent since `verify_evidence.py` has no rule-table dataclass at all: `PrivateRefRule(name: str, pattern: re.Pattern[str], rationale: str)` (`@dataclass(frozen=True)`, `verify_private_refs.py:118`), `STRUCTURAL_RULES: tuple[PrivateRefRule, ...]` (`:132`), `PrivateRefFinding(path: Path, line: int, rule: str, rationale: str, excerpt: str)` (`@dataclass(frozen=True)`, `:200`), `scan_file(path, rules, rel_path=None) -> list[PrivateRefFinding]` (`:261`), `scan_all(base_dir, rules) -> list[...]` (`:365`), `scan_paths(base_dir, paths, rules, added_only=False) -> list[...]` (`:375`); suppression via `_SUPPRESS_RE = re.compile(r"ll-private-ok:\s*(.+?)\s*(?:-->|$)")` (`:69`) checked on the finding's own or preceding line. `verify_evidence.py`'s only finding dataclass, `EvidenceFinding(issue_path: Path, section: str, line: int, span: str, artifact: str)` (`:162`), has no rule-table counterpart.
- **`assemble_bundle()` insertion point** (`scripts/little_loops/cli/loop/evidence.py:193`): entries are built procedurally in a fixed order — git predicates, then `loop_runs_row` fields, then `run_dir` file hashes, then loop-start facts, then resume-consistency/end-of-run/probe-count gap checks, then issue-path evidence, then the segregated `context_non_evidentiary` entries. A `credential_scan` entry would be appended as new `EvidenceEntry(...)` call(s) in this sequence; its `source` must already be a member of `_EVIDENTIARY_SOURCES = frozenset({"git_ref", "history_db_row", "run_dir_file"})` (`:25`) — none of the three cleanly fits an in-process scan of the bundle's own already-collected data — or that frozenset and its enforcing test (`test_every_evidentiary_entry_traces_to_deterministic_source`, `test_feat3182_evidence_bundle.py:153-159`) must be extended with a fourth value.
- **No `rules_sha` hashing helper exists to reuse**: `_sha256_file` (`scripts/little_loops/codequery/codegraph.py:124-130`) hashes on-disk file bytes only (`path.read_bytes()` → full 64-char hex digest); `VerdictCache`'s `{version, algo}` pair (`verify_evidence.py:1124-1125`, `_CACHE_VERSION = 2`, `_CACHE_ALGO = "blob-v1"`) is a pair of literal constants, not a hash function output. Computing `rules_sha` for an in-process Python rule table (per Option B) requires net-new code — there is no existing "hash this in-memory rule set" helper anywhere in the repo.

## Confidence Check Notes

_Added by `/ll:confidence-check` - 2026-09-13:_

Readiness 80/100, Outcome Confidence 62/100 (MODERATE) — but the **Learning Test Hard
Override** forces `STOP — ADDRESS GAPS` regardless of the readiness score. Re-run after
`/ll:refine-issue:gap-analysis`, `/ll:decide-issue`, `/ll:wire-issue`, and `/ll:verify-issues`
deepened Program Design and Integration Map; the underlying gaps are unchanged from the
prior pass.

### Gaps to Address
- `learning_tests_required: [gitleaks]` has no record in the Learning Test Registry
  (`ll-learning-tests check gitleaks` → "no record found", exit 1). This is stale: the
  Decision Rationale selected **Option B** (extend `pii.py` in-process, zero new runtime
  dependency), so `gitleaks` is no longer an external assumption this issue depends on.
  Remedy: remove `gitleaks` from `learning_tests_required` rather than attempting to
  prove it — there is no external API left to prove under the selected option.
- `credential_scan.scanned_at` conflicts with `EvidenceBundle`'s byte-identical
  reproducibility invariant (`test_rerun_over_unchanged_inputs_is_byte_identical`) and
  the "no timestamp field" design comment/docstring in `evidence.py`. Neither option in
  Proposed Solution resolves this — implementer must explicitly exclude `scanned_at`
  from the reproducibility-tested scope or resolve the conflict another way.
- Program Design's Decision Rules (b) and (c) remain open: the literal credential
  pattern list / `rules_sha` source, and whether a suppression escape hatch
  (`ll-credential-ok:`-shaped) is needed.
- `pii.py`'s current shape (`PII_PATTERNS: dict[str, re.Pattern[str]]`, no `Finding`
  dataclass, no `scan_file`/`scan_all`, no exit-code convention) does not yet match the
  frozen-dataclass rule-table → finding-list → exit-code convention the Decision
  Rationale cites as the target shape — matching it is net-new structure, not an append
  to the existing dict.

### Outcome Risk Factors
- Complexity (14/25): 6-15 distinct change sites (evidence.py, pii.py, `__init__.py`
  exports, ~4 test files, ~4 docs files) with a typical site that is Local (contained
  dataclass/function additions), pulled down by the reproducibility-invariant conflict
  and the pii.py convention-mismatch site both requiring more than mechanical edits.
- Ambiguity (10/25): main implementation option is decided, but several supporting
  design questions remain open (pattern list source, `rules_sha` mechanics, suppression
  convention, `scanned_at` conflict) — will require judgment calls during
  implementation.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-09-13
- **Reason**: Issue too large for single session (score 11/11, Very Large)

### Decomposed Into
- ENH-3469: Credential-pattern deterministic scanner in pii.py
- ENH-3470: Wire credential scan into the FEAT-3182 EvidenceBundle

### Not Covered by the Decomposition
- The **longitudinal `history.db` leakage signal** (third consumer named in
  Summary/Design) is in neither child. The sft-corpus emit gate is covered
  by ENH-3469 (credentials flow through `detect_pii`/`redact_pii`). File a
  follow-on for the `history.db` scan once ENH-3469 lands; it only needs
  `scan_text` over `raw_events.parsed_json` values.
- `credential_scan.scanned_at` was **dropped** in ENH-3470 (review
  2026-09-13): it conflicts with the bundle's byte-identical invariant and
  adds nothing deterministic; `version` + `rules_sha` carry comparability.

## Session Log
- `/ll:issue-size-review` - 2026-09-13T17:50:41 - `d24791a3-28b5-4b07-851d-ac809549dbb5.jsonl`
- `/ll:confidence-check` - 2026-09-13T17:47:07 - `af91c8c0-1ded-4070-974d-27b469b17351.jsonl`
- `/ll:verify-issues` - 2026-09-13T17:43:20 - `4d84d8e9-9fc3-4321-aba6-1c6a24b5cb4a.jsonl`
- `/ll:verify-issues` - 2026-09-13T17:43:06 - `4d84d8e9-9fc3-4321-aba6-1c6a24b5cb4a.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-13T17:40:51 - `bfdd8672-322e-41ad-9d09-46f2ccfad227.jsonl`
- `/ll:confidence-check` - 2026-09-13T17:36:28 - `955567ca-fbda-4517-9075-8f2f10d47936.jsonl`
- `/ll:verify-issues` - 2026-09-13T17:33:27 - `f8b8e54b-7cdf-4e9b-ac2b-7c14d0e2b8ee.jsonl`
- `/ll:wire-issue` - 2026-09-13T17:31:08 - `a1121005-80c2-4c1c-8eb7-7b418e0b5402.jsonl`
- `/ll:decide-issue` - 2026-09-13T17:24:06 - `66fed3e6-b255-402a-a541-14a6788ff647.jsonl`
- `/ll:refine-issue` - 2026-09-13T17:17:43 - `a3e28b2c-7397-43a7-8b4e-efd0c8d35b0f.jsonl`
