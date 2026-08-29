# Spike Plan: ENH-3342 — `scan_action()` call-site `file` param

## Context

ENH-3342's `### Outcome Risk Factors` names an unresolved Program Design
adapter-gap as a concrete open engineering decision:

> Ambiguity: the unresolved Program Design adapter-gap (see Concerns) — what
> value to pass as `scan_action()`'s keyword-only `file` argument, and how to
> reconstruct a message-worthy token from `InterpSite`'s bare
> `namespace.key_path` — is a concrete open engineering decision left to the
> implementer with no stated resolution.

This spike targets the `file` half only (the token-reconstruction half is a
separate, already-tracked finding). The concrete failure the spike must rule
out: **(a)** the mechanism has zero precedent — no MR-11-style single-loop
validator has ever called `interp_sweep.scan_action()`, only `scan_corpus()`
(a disk-walking batch scanner) does today, so there is no existing pattern
to copy for what a single in-memory `FSMLoop` should supply as `file`; **(b)**
no existing test exercises `scan_action()` from a caller that lacks a real
disk path, which is exactly MR-11's situation for two of its three real call
sites (see below).

`interp_sweep.scan_action(action: str, *, state: str, file: str)`
(`interp_sweep.py:128`) requires a mandatory keyword-only `file: str`.
`FSMLoop` (`schema.py:1360`, ~90 fields via `dataclasses.fields()`) has no
file-path/source-path field, and `validate_fsm()`
(`structural_rules.py:983`) is never passed one by any of its three real
callers. `InterpSite.file` participates in the dataclass's equality/hash
(`interp_sweep.py:100`, `compare=True` by omission), which is what makes the
"what do we pass" question look load-bearing.

## Approach

Call the **real** `interp_sweep.scan_action()`, `classify_site()`, and
`InterpSite`, plus the real `FSMLoop`/`StateConfig`/`validate_fsm` — nothing
reimplemented — and prove three things against the actual code:

1. **No real path is available at 2 of 3 call sites**, so "thread a real
   path through `FSMLoop`/`validate_fsm`'s call chain" (option a) cannot be a
   uniform fix — it would need a fabricated value at those two sites anyway.
2. **The `file` value never reaches anything MR-11 produces or compares** —
   MR-11's own message builder (`_validate_unsafe_context_interpolation`)
   keys entirely on `state` + the raw token text, never `file`, and MR-11
   makes no cross-call `InterpSite` equality comparison (that machinery
   exists solely for ENH-3338's `scan_corpus()` baseline diff, a disjoint
   code path) — so any constant placeholder is functionally safe for MR-11's
   use.
3. **`FSMLoop.name` is universally available** at all three real call sites
   (including the two with no disk path) and is a already-there field
   requiring zero schema change — the natural placeholder.

Nothing is faked or stubbed: the spike drives the real `scan_action()` with
various `file` values and the real `validate_fsm()` call chain to observe
actual behavior, not a model of it.

## Critical files

Read-only references (production, not modified by this skill):

- `scripts/little_loops/fsm/interp_sweep.py` — `scan_action()`, `classify_site()`,
  `InterpSite`, `_merge_counts()`
- `scripts/little_loops/fsm/schema.py` — `FSMLoop`, `StateConfig`
- `scripts/little_loops/fsm/validation/structural_rules.py` — `validate_fsm()`
  and its disk-loading caller (has `path: Path` in scope but never threads it
  into `validate_fsm`)
- `scripts/little_loops/cli/loop/scaffold_eval.py:267-278` — builds `FSMLoop`
  in-memory, calls `validate_fsm(fsm)` **before** any disk path exists
- `scripts/little_loops/cli/loop/scaffold_verify.py:323-337` — same pattern
- `scripts/little_loops/fsm/validation/shell_safety.py` —
  `_find_unsafe_context_interpolations` / `_validate_unsafe_context_interpolation`
  (the MR-11 functions this issue widens)

New spike paths:

- `scripts/tests/spike/enh3342_scan_action_file_param/__init__.py`
- `scripts/tests/spike/enh3342_scan_action_file_param/test_file_param.py`

## Implementation

```
scripts/tests/spike/enh3342_scan_action_file_param/
├── __init__.py
└── test_file_param.py     # the AC test class — calls real production code directly
```

No separate library module or driver is needed: this is a call-site/design
question about existing production functions, not a novel mechanism to
build — the test module calls `interp_sweep.scan_action()`,
`little_loops.fsm.schema.FSMLoop`, and `validate_fsm()` directly.

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_real_call_sites_have_no_file_path_available_for_validate_fsm` | Risk (a): confirms `validate_fsm()`'s signature and `FSMLoop`'s fields carry no path, and that the two scaffold call sites build an in-memory `FSMLoop` with no disk path before validating — proving "thread a real path" cannot be a uniform fix | regression-guard (structural; fails loudly if a future change threads a path, signalling this spike's premise needs re-checking) |
| `test_scan_action_file_value_does_not_leak_into_mr11_style_message` | Risk (b): proves an MR-11-style message builder (keys on `state` + token, per the real `_validate_unsafe_context_interpolation` shape) produces byte-identical output regardless of what `file` value is passed to `scan_action()` | behavior |
| `test_merge_counts_is_insensitive_to_constant_file_value_within_one_call` | Risk (b): proves `_merge_counts()`'s `(file, state, var, cls)` dedup key still merges duplicate sites correctly within one `scan_action()` call regardless of which constant `file` value is chosen | behavior |
| `test_fsm_name_is_always_available_at_every_real_call_site` | Resolves the ambiguity: constructs an `FSMLoop` the way each of the three real call sites does (disk-loaded via `from_dict`, and the two scaffold constructions) and asserts `.name` is always a non-empty string, proving it as the recommended `file` placeholder | behavior |

## Verification

```bash
python -m pytest scripts/tests/spike/enh3342_scan_action_file_param/ -v
python -m pytest scripts/tests/test_interp_sweep.py -v
python -m pytest scripts/tests/test_fsm_validation_shell_safety.py -v
```

## Out of Scope

- The token-reconstruction half of the adapter-gap finding (`InterpSite.var`'s
  bare `namespace.key_path` vs. the full suffix-chain token MR-11's message
  currently embeds) — a separate, already-tracked finding, not this spike's
  target.
- Option (c), reimplementing `classify_site()`'s logic directly in
  `shell_safety.py` instead of delegating — the issue's own Program Design
  Codebase Research Findings already settled on the two-scan-path delegation
  design (`## Implementation Steps` step 1); re-litigating that design choice
  is out of scope here.
- Actually wiring the widened bash-token-position scan or the
  `scan_action()`-delegated Python-body scan into `shell_safety.py` — that is
  the real implementation, done in a separate change.

## Promotion

No promotion — this spike answers a design question with a set of proof
tests; the code it produces is not what ships. On acceptance, ENH-3342's
Implementation Steps should be updated to say explicitly: "pass
`file=fsm.name` to `scan_action()`", and the Program Design § Signatures
over-claim should be corrected as already drafted in the issue's own
Codebase Research Findings.
