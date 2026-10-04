---
target: Anthropic Message Batches API
date: '2026-10-04'
status: proven
assertions:
- claim: messages.batches.create POSTs to /v1/messages/batches with a body whose only
    key is requests, each item forwarded verbatim as {custom_id, params}, and sends
    no anthropic-beta header
  result: pass
- claim: the create response parses to a MessageBatch with processing_status in_progress,
    request_counts, a datetime expires_at, and results_url None until the batch ends
  result: pass
- claim: retrieve is GET /v1/messages/batches/{id}, cancel is POST .../{id}/cancel
    (returns processing_status canceling plus cancel_initiated_at), delete is DELETE
    .../{id} (returns DeletedMessageBatch), and list is GET /v1/messages/batches with
    limit and after_id as query params
  result: pass
- claim: messages.batches.results raises AnthropicError (after one retrieve GET) when
    the batch has no results_url yet
  result: pass
- claim: once results_url is set, results issues retrieve then a GET to the results
    URL with Accept application/binary, and decodes the JSONL lines into MessageBatchIndividualResponse
    objects whose result is a discriminated succeeded/errored/canceled/expired type
  result: pass
- claim: the SDK performs no client-side validation of the requests list (duplicate
    custom_id values and an empty list are sent unmodified)
  result: pass
- claim: retrieve, cancel, delete, and results raise ValueError on an empty batch ID
  result: pass
- claim: per-request params such as a system block with cache_control ttl 1h pass through
    batches.create unchanged
  result: pass
- claim: the server rejects duplicate custom_id values and an empty requests list
  result: untested
- claim: the server enforces the 100,000-request / 256 MB batch limits
  result: untested
- claim: batch requests are billed at a discount versus synchronous Messages calls
  result: untested
- claim: a batch that does not finish within 24 hours of creation ends with expired
    results
  result: untested
raw_output_path: .ll/learning-tests/raw/anthropic-message-batches-api.txt
---
