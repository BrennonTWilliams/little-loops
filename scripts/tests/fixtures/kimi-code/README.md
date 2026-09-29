# Kimi Code usage survey (ENH-3648)

Sanitized real Kimi Code **0.30.0** captures: `live-v0.30.0.jsonl` contains
the streamed assistant/tool records and a resume hint, with no usage object
in the observed stream. `stored-v0.30.0.jsonl` contains an initial tool-call
turn (two LLM requests) and a resumed turn (one request), reduced to request,
usage, and resume records. `ll-verify-private-refs` passes.

| Channel | Native record and fields | Identity and grain | Evidence class |
| --- | --- | --- | --- |
| `transcript` | `usage.record.usage`: `inputOther`, `output`, `inputCacheRead`, `inputCacheCreation`; `usageScope: "turn"`. Each record is duplicated in an adjacent `context.append_loop_event.event.usage`. | Three usage records accompany `llm.request` steps `0.1`, `0.2`, and resumed `1.1`. `usage.record` has no explicit request ID; file order and `time` are candidate keys, not proved stable identity. Values are not a monotone session total. | Output, cache-read and cache-creation field availability: supported. Normalized disjoint input remains unknown pending semantics for `inputOther`. |
| `live` | No usage object in the captured stream, including resume. | One sample does not prove native absence. | Unknown. |
| `rollout`, `context_hook` | No capture. | Unknown. |

The second and third stored records have nonzero `inputCacheRead` (24,064
and 24,320); all observed `inputCacheCreation` values are zero. The field
names suggest disjoint input components, but their accounting semantics and
whether omission means zero are not yet verified. `output` versus reasoning
tokens is unproven. `usageScope: "turn"` does not by itself establish whether
two usage records in one user turn are distinct model requests. Counting both
`usage.record` and `context.append_loop_event` would double-count the same
sample. ENH-3665 owns the remaining contract and identity proof.

**Recommendation:** ENH-3534 can target stored `usage.record` after ENH-3665
settles component semantics and replay identity. Keep live usage unknown;
absence from one stream is not a producer-wide unsupported verdict.
