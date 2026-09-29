# OpenCode usage survey (ENH-3648)

Real OpenCode **1.1.53** capture, sanitized and reduced to usage-bearing
records. `live-v1.1.53.jsonl` is the live `step_finish` stream for an invocation
with a tool call and two model steps. `stored-v1.1.53.jsonl` contains the
corresponding stored `step-finish` parts. The `resume-*` pair comes from a
subsequent invocation in the same session. `ll-verify-private-refs` passes.

| Channel | Native record and fields | Identity and grain | Evidence class |
| --- | --- | --- | --- |
| `live` | `step_finish.part.tokens.{input,output,reasoning,cache.read,cache.write}` | `sessionID` scopes the session; `part.id` identifies a stored part and is present in the live envelope. Two different part IDs occur in the first invocation; resume retains the session ID and adds a third. The values are per step in this sample, rather than a monotone session total. | `output_tokens`, cache-read and cache-creation field availability: supported in 1.1.53. Normalized disjoint `input_tokens`: unknown. |
| `transcript` | Stored `type: step-finish` part has the same token fields and IDs. | `part.id` is the candidate source-event key within `sessionID`; `messageID` names the associated message. | Same field availability and input uncertainty as `live`. |
| `rollout`, `context_hook` | No capture. | Unknown. | Unknown. |

All captured cache read/write values are zero. These samples do **not** prove
whether `tokens.input` includes cached tokens, whether nonzero cache writes
are possible, what omission means, or whether `tokens.reasoning` is included
in `tokens.output`. Treat normalized input and measured-observation eligibility
as unknown until a cache-hit capture and producer contract settle these rules.
The live and stored records share `part.id`, so ingestion must not count both
copies as independent consumption. OpenCode's current little-loops runner is
also not configured for orchestration; that ingestion state does not change
the native field-availability finding. ENH-3660 owns the remaining evidence.

**Recommendation:** Use these fields as ENH-3534's candidate live/stored
normalizer and dedup input, after ENH-3660 confirms cache and reasoning
semantics. Preserve the individual parts rather than summing an invocation
total inferred from the first record.
