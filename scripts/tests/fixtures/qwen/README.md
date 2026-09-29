# Qwen Code usage survey (ENH-3648)

`usage-pair-v0.24.6.jsonl` is a sanitized pair of real Qwen Code **0.24.6**
on-disk records from one response: a `systemPayload.uiEvent` and a following
assistant `usageMetadata`. This excerpt retains producer usage fields and IDs,
not the surrounding message body or a tool call. The older `session.jsonl` is
a synthetic normalizer fixture and does not establish the 0.24.6 contract.
`ll-verify-private-refs` passes for the new capture.

| Channel | Native record and fields | Identity and grain | Evidence class |
| --- | --- | --- | --- |
| `transcript` | `assistant.usageMetadata`: `promptTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount`, `totalTokenCount`, `cachedContentTokenCount`; preceding `systemPayload.uiEvent` uses snake-case equivalents. | Both records share `sessionId` and the same numerical usage; each has a separate `uuid`. The UI event additionally has `response_id` and `prompt_id`. This is one observed response with two usage representations; a durable join key between them is unproven. | Output and cache-read field availability: supported. Normalized disjoint input and cache-creation availability: unknown. |
| `live` | A 0.24.6 probe failed because the OAuth free tier was discontinued for the configured account. | No usage capture. | Unknown; failed authentication is not evidence that usage is absent. |
| `rollout`, `context_hook` | No capture. | Unknown. | Unknown. |

The captured `cachedContentTokenCount` is zero and no cache-write field is
present in this pair. Neither fact proves absence of cache writes or whether
`promptTokenCount` includes cached input. The example has
`totalTokenCount = promptTokenCount + candidatesTokenCount` while
`thoughtsTokenCount` is nonzero; whether thoughts are included in candidate
output is not established by that arithmetic. Omitted-field semantics,
resume/compaction reset behavior, and a stable source-event key remain
unknown. The sanitized excerpt lacks `message.parts`, so it is producer
evidence rather than an `iter_events()` normalization fixture. ENH-3662 owns
the remaining proof.

**Recommendation:** ENH-3534 should preserve the raw usage pair and normalize
only after ENH-3662 proves cache/reasoning semantics and duplicate handling.
Do not sum the system and assistant copies.
