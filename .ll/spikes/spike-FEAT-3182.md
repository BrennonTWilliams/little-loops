# Spike Plan: FEAT-3182 — Deterministic Verification-Evidence Bundle (Option A)

## Context

FEAT-3182 has no `## Confidence Check Notes` (no `/ll:confidence-check` pass has
run yet), but `refine-issue`'s own `## Program Design` → `Decision Rules` flags
an `unproven_mechanism: true` risk directly:

> "no precedent for evidencing a check whose verdict is itself LLM-graded... No
> existing codebase site draws this line: searched repo-wide for
> `evidentiary`/`non_evidentiary`, no hits besides this issue's own text."

Two failure drivers apply: **(a)** zero precedent — no `Bundle`-suffixed class,
no evidentiary/non-evidentiary field distinction anywhere in the codebase; **(b)**
no existing test exercises segregating LLM-sourced evaluator output from
deterministic run facts.

The issue's own `## Proposed Solution` names the concrete failure this spike
must rule out: Option A (deterministic-only bundle, LLM verdicts segregated as
labeled non-evidentiary context) satisfies AC3 literally, but risks producing an
attestation so weak ("a check was attempted") that it isn't useful to a
reviewer. Per the user-confirmed scope, this spike builds Option A and produces
a sample bundle to eyeball that usefulness question, without resolving the
Option A vs. B decision itself (that stays `/ll:decide-issue` territory).

## Approach

Build an isolated `EvidenceBundle` library that assembles a bundle from three
plain-data inputs — a `loop_runs`-row-shaped dict, an archived-run-directory
path (fixture, not a real `.loops/.history/` run — none of this issue's
target loop shape exists in this repo's history yet), and independently-computed
git facts (passed in, not shelled out to `git rev-parse` — the git-facts helper
is a separate, unrisky mechanism already precedented at every other call site) —
and partitions every candidate field into exactly two buckets:

- **`evidentiary`**: entries whose source is one of `git_ref`, `history_db_row`,
  or `run_dir_file` (existence/hash/count facts only — never a field read from
  an `evaluate` event or a `captured.*.verdict`).
- **`context_non_evidentiary`**: entries sourced from an `evaluate` event
  carrying `llm_model` (i.e. `llm_structured`-graded verdicts/reasons), always
  labeled with `"llm_sourced": true`.

What's faked: the archived run directory is a hand-built fixture (`state.json` +
`events.jsonl` + `probe-*.json`) mirroring the exact shape the issue's Call Path
documents, not a real loop run — building a full `verify-issue-loop` fixture
loop is out of scope and unnecessary to prove the segregation/reproducibility/
gap-detection mechanics. The `loop_runs` row and git facts are plain dicts, not
a real sqlite read or subprocess call — those are unrisky, already-precedented
mechanisms (see `Critical files`), not what this spike needs to retire risk on.

## Critical files

Read-only references (production, not modified by this spike):

- `scripts/little_loops/fsm/cost_graph.py:106-139` — `CostReport`: the
  `Report`-suffixed dataclass shape (`to_dict()`, no custom encoder) this
  spike's `EvidenceBundle` models itself on.
- `scripts/little_loops/issue_parser.py:505-533` — `FormatGaps`: the
  enumerable-gap-list convention (`list[str]` per category + `has_gaps`).
- `scripts/little_loops/prepatch_check.py` — `PrePatchEvidence`: the one
  existing "evidence bundle" shape/term precedent in this codebase.
- `scripts/little_loops/cli/loop/audit.py:60-190` — `resolve_run()`/
  `_read_events()`/`_read_json_file()`: the existing archived-run-directory
  reader this spike's fixture-reading helper mirrors (defensive per-line
  JSONL parsing).
- `scripts/little_loops/cli/artifact/dashboard.py:179-210` — the
  frozen-clock, gzip-`mtime=0` reproducibility pattern this spike's
  reproducibility test follows.
- `scripts/little_loops/session_store/schema.py:563-580` — `loop_runs`
  column shape the fixture row dict mirrors.
- `scripts/little_loops/cli/loop/scaffold_verify.py:111,199,245` —
  `_criteria_states()`/`_adversarial_states()`/`count_probes`: the source of
  truth for what an `evaluate` event and a `probe-*.json` file look like.

New spike paths (created by this skill):

```
scripts/tests/spike/verify_evidence_bundle/
├── __init__.py
├── bundle.py
├── driver.py
└── test_bundle.py
```

## Implementation

```
scripts/tests/spike/verify_evidence_bundle/
├── __init__.py
├── bundle.py           # EvidenceBundle, EvidenceEntry, GapEntry, assemble_bundle()
├── driver.py            # renders a sample bundle from a fixture run + prints it
└── test_bundle.py       # the AC test class
```

API sketch (`bundle.py`):

```python
@dataclass
class EvidenceEntry:
    key: str
    value: Any
    source: str  # "git_ref" | "history_db_row" | "run_dir_file"

@dataclass
class ContextEntry:
    key: str
    value: Any
    llm_sourced: bool = True  # always True; field exists for shape symmetry

@dataclass
class GapEntry:
    category: str  # "missing_run_dir" | "missing_loop_runs_row" | "missing_probe_file"
    detail: str

@dataclass
class EvidenceBundle:
    evidentiary: list[EvidenceEntry] = field(default_factory=list)
    context_non_evidentiary: list[ContextEntry] = field(default_factory=list)
    gaps: list[GapEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]: ...
    @property
    def has_gaps(self) -> bool: ...

def assemble_bundle(
    loop_runs_row: dict[str, Any] | None,
    run_dir: Path | None,
    git_facts: dict[str, str],
) -> EvidenceBundle: ...
```

`assemble_bundle()` reads `state.json`'s `captured` map and `events.jsonl`'s
`evaluate`-typed events (fixture shape, per Critical files) to build
`context_non_evidentiary`; reads `run_dir` file existence/sha256 hashes and
`probe-*.json` counts plus the passed-in `loop_runs_row` fields and
`git_facts` to build `evidentiary`; emits a `GapEntry` for any of the three
inputs that is `None`/missing rather than silently omitting it.

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_llm_sourced_fields_never_land_in_evidentiary` | Decision Rule risk: no precedent distinguishing LLM- vs. deterministic-origin fields | behavior |
| `test_every_evidentiary_entry_traces_to_deterministic_source` | AC1: enumerable, source-traced entries | behavior |
| `test_rerun_over_unchanged_inputs_is_byte_identical` | AC2: reproducible | behavior |
| `test_missing_run_dir_produces_explicit_gap_not_silent_bundle` | AC4: incomplete evidence → explicit gap list | behavior |
| `test_missing_loop_runs_row_produces_explicit_gap` | AC4 (second gap source) | behavior |
| `test_bundle_is_plain_json_no_custom_types` | AC5: readable without little-loops installed | behavior |
| `test_spike_does_not_import_production_session_store_or_fsm` | isolation guard | regression |

`driver.py` renders a sample bundle from the fixture run to a scratch file for
manual inspection — the empirical "is Option A still useful to a reviewer"
question the issue asks the spike to answer. This is a qualitative read, not
an assertion; its output is reported in `## Spike Results`, not gated by pytest.

## Verification

```bash
python -m pytest scripts/tests/spike/verify_evidence_bundle/ -v
python -m pytest scripts/tests/test_feat3304_artifact_dashboard.py -v -k reproducible
python -m pytest scripts/tests/test_prepatch_check.py -v
```

## Out of Scope

- Resolving Option A vs. Option B (`/ll:decide-issue` territory).
- Reading a real `history.db` / real archived `.loops/.history/` run — fixture
  data only.
- Deriving git facts via a real `git rev-parse` subprocess call — passed in as
  plain data; that mechanism is already precedented (`worktree_utils.py:65`,
  `pytest_history_plugin.py:141-142`) and carries no risk to retire.
- The exporter's CLI surface (`ll-loop bundle` or similar) and its
  `docs/reference/CLI.md`/`docs/reference/API.md` entries.
- A real `verify-issue-loop` fixture loop run — the `state.json`/`events.jsonl`/
  `probe-*.json` fixture mirrors the documented shape but is hand-built.

## Promotion

On acceptance, promote `bundle.py`'s `EvidenceBundle`/`assemble_bundle()` shape
from `scripts/tests/spike/verify_evidence_bundle/` to
`scripts/little_loops/spike/verify_evidence_bundle/` (or directly into
`scripts/little_loops/cli/artifact/` per the issue's placement convention) in a
**separate PR**, wired to real `history.db` reads and a real `git rev-parse`
git-facts helper.
