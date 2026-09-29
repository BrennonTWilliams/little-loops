# Gemini CLI usage survey (ENH-3648)

`usage-historical-version-unknown.jsonl` contains two sanitized real on-disk
Gemini records with the same message `id`, timestamp, model, and `tokens`
values; `toolCallCount` changes from 0 to 4. The capture's **CLI version is
unknown**, so it cannot certify the installed Gemini CLI **0.46.0** contract.
The older `session.jsonl` and `legacy.json` are synthetic parser fixtures,
not producer evidence. `ll-verify-private-refs` passes for the real excerpt.

The historical records expose `tokens.{input,output,cached,thoughts,tool,total}`.
They suggest an update/rewrite of one message rather than two independent
consumption events, but the original file's update and resume behavior is
unverified. Cache inclusivity, cache-write reporting, omitted fields,
reasoning-in-output, and request grain are unknown. The `id` is a candidate
message key, not yet a proved source-event key. The current Gemini normalizer
drops `tokens` from the Claude-shaped `iter_events()` output.

| Channel | Versioned evidence | Classification |
| --- | --- | --- |
| `transcript` | Historical real records, version unknown. | All normalized metric availability unknown. |
| `live` | A 0.46.0 probe could not run without Vertex configuration. | All availability unknown; failed configuration is not producer absence. |
| `rollout`, `context_hook` | No capture. | Unknown. |

**Recommendation:** Defer measured ingestion. ENH-3663 must capture a
versioned live/session pair with tool use and resume, then establish identity,
cache and reasoning semantics before ENH-3534 maps these fields.
