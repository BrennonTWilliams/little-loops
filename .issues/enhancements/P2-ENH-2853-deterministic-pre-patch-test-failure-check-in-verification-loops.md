---
id: 2853
title: Deterministic pre-patch test-failure check in verification loops
type: ENH
priority: P2
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
---

# ENH-2853: Deterministic pre-patch test-failure check in verification loops

Origin: ll-product #ENH-051

## Summary

A test that passes on the pre-change tree proves nothing about the change. Add a deterministic check that runs newly added or modified tests against the **pre-patch** code and requires them to fail there before a verification loop may treat them as evidence.

This is a non-LLM check and belongs in `ll-harness`, `/ll:verify-issue-loop`, and the verification-evidence bundle, alongside the existing semantic criteria rather than replacing them.

## Motivation

The most common way an agent fakes verification is writing a test that passes before and after the change. It costs nothing, it turns the suite green, and every downstream signal — transition predicates, evidence bundles, success rates — reads it as proof. Semantic criteria do not catch it reliably because the test genuinely looks correct in isolation; the defect is only visible relative to the pre-change tree.

The check is deterministic, cheap, and has no false-positive mode that matters: a test that is supposed to demonstrate a change must fail without that change.

## Proposed Change

1. **Identify the candidate tests** — from the diff of the verification step, collect test functions that were added or modified.
2. **Reconstruct the pre-patch tree** — check out the base state in an isolated worktree, then apply *only* the test changes onto it.
3. **Run the candidate tests there** and record per-test pass/fail.
4. **Verdict** — any candidate test that *passes* against the pre-patch tree is flagged. The loop must not count it as evidence; the transition either fails or the test is excluded from the evidence set, per configuration.
5. **Report** — emit per-test results (name, file, pre-patch outcome, post-patch outcome) into the verification evidence bundle so the check is auditable without re-running it.

## Design Notes

- Apply *only* the test-file portion of the diff to the base tree. Applying the full diff defeats the purpose; applying nothing means the tests don't exist to run.
- A candidate test that **errors** on the pre-patch tree (import error because the new module doesn't exist yet) counts as failing — that is the expected outcome for a test of new code, not a harness problem. Distinguish error-vs-fail in the report but treat both as "did not pass".
- Use an isolated worktree rather than mutating the working tree in place; a verification check must never leave the user's tree in a different state than it found it.
- Pure-refactor changes may legitimately have no new tests. Zero candidate tests is not a failure — report it explicitly rather than silently passing, so "no tests were added" is visible.
- Keep this independent of any LLM call. The whole value is that the signal is mechanical.
- **Added vs. modified tests carry different contracts.** A *newly added* test must fail pre-patch — that is the clean "demonstrates the change" contract. A *modified* test routinely passes pre-patch legitimately (an assertion added to an already-passing test, a tightened comparison, a rename). Split the verdict: added-and-passes-pre-patch is a hard flag; modified-and-passes-pre-patch is recorded in the evidence but soft by default (configurable to hard). A hard flag on modified tests would punish exactly the assertion-strengthening behavior the epic wants to encourage.
- **Import isolation is load-bearing in editable-install repos.** A worktree checkout of the pre-patch tree can still import the *main-tree* package when the project is installed editable (the install pins an absolute path — see the epic-verify false-negative history in this repo). A "pre-patch" run that imports post-patch code passes trivially and the check reports garbage. The pre-patch run must resolve imports from the worktree (PYTHONPATH injection ahead of site-packages, or a fresh non-editable install into the worktree's environment), and a test must prove the isolation.
- **Define the base state explicitly.** Under `ll-auto`/`ll-sprint` a verification step may span multiple commits. "Pre-patch" means the tree at the SHA recorded when the issue was dequeued (fall back to merge-base with the base branch when no dequeue SHA is recorded) — not simply `HEAD~1`.
- **Shared test-file identification with ENH-2854.** Both this check and the tamper guard need to classify paths as test files. Implement one shared module (driven by a `project.test_patterns` config key — see ENH-2854) so the two checks cannot drift to divergent globs.

## Acceptance Criteria

- [ ] Newly added and modified test functions are identified from the verification step's diff.
- [ ] Those tests are run against the pre-patch tree with only the test changes applied, in an isolated worktree.
- [ ] A newly *added* candidate test that passes pre-patch is hard-flagged and is not counted as verification evidence.
- [ ] A *modified* candidate test that passes pre-patch is recorded in the evidence as soft by default, with a config option to escalate it to a hard flag.
- [ ] A candidate test that fails or errors pre-patch is accepted as evidence.
- [ ] The pre-patch run resolves imports from the pre-patch worktree, not the main tree's editable install; a test proves the isolation (post-patch-only module is unimportable in the pre-patch run).
- [ ] The base state is the dequeue-time SHA when recorded, else the merge-base with the base branch; the chosen base is named in the evidence bundle.
- [ ] Test-file identification is shared with ENH-2854's guard (one module, one `project.test_patterns` source of truth).
- [ ] The zero-candidate-tests case is reported explicitly rather than passing silently.
- [ ] Per-test results (name, file, pre-patch outcome, post-patch outcome) appear in the verification evidence bundle.
- [ ] The user's working tree is unchanged after the check runs, including on failure paths.
- [ ] The check makes no LLM calls.
- [ ] Tests cover: a fake test that passes pre-patch, a genuine test that fails pre-patch, a test that errors pre-patch, and the zero-test case.
