---
id: 3416
title: Add attempt budget, backoff, and dead-lettering to ll-queue
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
labels:
- queue
- reliability

---

## Summary

`ll-queue` ships with no failure policy, and the recovery path it does have is an unbounded retry loop. `queue_store.py` models pending/running/done with `claimed_at` and `owner_pid`; the only recovery is `reset_to_pending`, which clears both and carries no attempt counter. `cli/queue.py`'s `_reclaim_stale` runs on watcher startup and on every idle poll, returning any entry whose owner is not verifiably alive. An entry that reliably kills its own drainer — OOM, a crash in the dispatched action, a malformed spec — is therefore reclaimed and re-dispatched forever, with nothing recording that it has failed before. This is the precise failure that dead-lettering exists to stop, and a long-lived drainer makes it the normal case rather than a rare one someone is present to witness.

Specify and implement: an attempt counter per entry, bounded exponential backoff between attempts with a `next_attempt_at` the dequeue path honors, and a terminal dead-letter status carrying the last error so a poison entry leaves the rotation and stays inspectable. Distinguish the requeue semantics rather than collapsing them into one — a retry after failure consumes the attempt budget and applies backoff; a reclaim after an owner died without a verdict should preserve the original enqueue timestamp so the entry keeps its place in priority/FIFO fairness instead of going to the back; and an operator cancel should carry a reason and not be retried at all. Overflow and trimming should match each path's fairness intent rather than using one rule. Classify retryability from the error rather than guessing from an exit code, reusing whatever the open timeout-semantics issue settles — a dead owner and a rejected spec are not the same condition and should not share a policy.

## Reference shape

A production message-batching queue that has solved this exact problem lands on:

- **Bounded exponential backoff, 10 attempts, 5s → 300s, then dead-letter.**
- **Three distinct requeue semantics**, each preserving a different invariant that one generic retry would destroy: a budget-consuming requeue that applies backoff; a timestamp-preserving requeue, so an item retried after an owner death keeps its fairness position; and a cancelled-with-reason requeue that is never retried.
- **Overflow trimming that differs per path** — oldest-first in one, newest-first in the other — matching each path's fairness intent instead of applying one rule everywhere.
- **Typed retryability classification** at the transport layer: narrow the error to a class rather than guessing from a status code, and honor a server-supplied retry delay but **ceiling-clamp** it so worst-case latency stays bounded. Auth gets one refresh-and-retry, guarded so a static credential that "refreshes to itself" fails terminal immediately instead of replaying a byte-identical rejected request.

That last guard generalizes: a retry that cannot change the input is not a retry.

## Acceptance Criteria (added 2026-08-25)

- **Every error class marked retryable must be reachable by a policy whose maximum attempt count exceeds one.** Assert this as a deterministic test that enumerates the retryable classes and walks the policies that consume them. The failure it catches is silent and specific: a correct classification chain — retryable, non-fatal, backoff-eligible — rendered inert because the single policy that consumed it allowed one attempt. A durable-execution agent platform hit exactly this: a provider 429 killed a deployed run and tripped a circuit breaker, with the classification chain entirely correct and `maximum_attempts=1` making it make no difference. As `ll-queue` and the FSM executor gain richer error taxonomies, the gap between "classified retryable" and "actually retried" widens with nothing watching it. The companion retryable-vs-fail-fast admission table tabulates the classes and this issue sets the budgets; nothing currently asserts the join between them.

- **Express the policies as a small set of named constants, each carrying the failure that motivated it and the trade-off accepted in exchange, and lock the set with a test.** Not a post-hoc refactor — a shaping constraint on how this issue, the admission table, and the consecutive-failure circuit breaker are built, so all three land in one legible vocabulary instead of three slices with implicit rationale. A callsite that constructs its own policy literal rather than referencing a named constant is a bug of the same class, and the locking test is what makes that mechanically visible; this is the same discipline as restating a constraint where it is read rather than only where it is declared.

The named-constants requirement is not stylistic. The failure it prevents is a contract leak: a component declares a non-retryability policy on itself, and a caller hand-typing a fresh policy literal at the invocation site silently drops the declaration. The declaration was correct; the callsite quietly overrode it. Shared named constants re-imposed at the callsite, plus a test that locks them, is the answer that has been paid for elsewhere.

## Folded constraints

The following were closed as design constraints with no shippable unit of their own; this issue carries their rule.

- **Terminality is claimed per call site, not encoded into the error.** The error carries a structured reason; each call site (checkpoint vs read path) decides whether it is terminal and records that decision as metadata.
- **Classify agent failures by whether observable work exists, and revive in place.** Retryability keys on whether the user already saw output; revival reuses the same run identity; a persisted `retried_at` fence caps residue at one re-run per entry.
