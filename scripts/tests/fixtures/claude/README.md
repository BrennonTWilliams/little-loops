# Claude Code usage producer captures

Captured on 2026-09-29 with `claude --version` = `2.1.284 (Claude Code)`.
The matching headless invocation ran `claude -p --output-format stream-json
--verbose` in a scratch directory, called `pwd`, and then completed. Its
matching on-disk transcript was located by the emitted `session_id`.

- `live-v2.1.284.jsonl` retains the `assistant.message.usage` and final
  `result.usage` records. The final result totals equal the sum of the two
  distinct requests' final values: input 18, cache creation 11223, cache read
  38429, output 165. A nonzero cache read is present on both requests.
- `transcript-v2.1.284.jsonl` retains the matching four on-disk assistant
  records. Each request has two records with the same `message.id` and usage
  but different outer `uuid` values. Their usage must be counted once per
  request, not once per transcript line or outer UUID.
- `transcript-changing-usage-observed.jsonl` is a second real transcript
  sample from a Claude Code session on the same capture date. Five assistant
  records share one `message.id` but have different outer UUIDs. The first
  four report output 4; the final record reports output 481. The producer
  transcript records each carry `version: 2.1.284`, so this also proves the
  repeated-ID update shape for the captured version. A consumer must retain the final
  observation for that request rather than count all five or keep the first.
- `stop-hook-v2.1.284.json`, `stop-observation-v2.1.284.json`, and
  `stop-transcript-v2.1.284.jsonl` are a separate headless Stop-hook capture.
  The hook read the transcript path from its payload **while Stop was running**
  and found two complete assistant usage records, including the completed
  turn's final record with output 176 and cache read 24750. The observation
  preserves that at-hook fact; the transcript fixture is a projection of the
  matching source. The hook payload's local path is replaced with
  `__TRANSCRIPT_PATH__` in the fixture. This confirms the final usage record
  was present before a detached worker could start for this captured version.

All fixtures are projections of captured JSON records: prompt text, tool
arguments/results, local paths, and unrelated event fields were removed;
identity and usage fields were kept unchanged. `ll-verify-private-refs` passes.

The captured records always contain integer `input_tokens`, `output_tokens`,
`cache_creation_input_tokens`, and `cache_read_input_tokens`. The files do
not establish the meaning of an omitted field or an all-zero usage block;
those cases remain unverified. Anthropic's [usage documentation](https://docs.anthropic.com/en/docs/about-claude/pricing)
defines total input as the sum of the three disjoint input components.
