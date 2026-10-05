---
target: anthropic-batches-api
date: '2026-10-04'
status: proven
assertions:
- claim: 'SDK client messages.batches.create() POSTs to /v1/messages/batches with a body whose only key is "requests", each item having exactly custom_id and params (verified against httpx MockTransport, not the live server)'
  result: pass
- claim: 'create() returns a MessageBatch whose processing_status is one of in_progress, canceling, ended and whose request_counts has exactly processing, succeeded, errored, canceled, expired'
  result: pass
- claim: 'retrieve(id) is GET /v1/messages/batches/{id}, cancel(id) is POST /v1/messages/batches/{id}/cancel, delete(id) is DELETE /v1/messages/batches/{id}, and list(limit=N) is GET /v1/messages/batches?limit=N returning an iterable page'
  result: pass
- claim: 'results(id) first issues a GET retrieve and raises AnthropicError when the batch has no results_url (not yet ended); it does not hit /results while in_progress'
  result: pass
- claim: 'results(id) on an ended batch fetches /v1/messages/batches/{id}/results and yields MessageBatchIndividualResponse objects (custom_id + result) parsed from JSONL'
  result: pass
- claim: 'result.type discriminates into succeeded (has .message), errored (has .error.error.type), canceled, and expired result classes'
  result: pass
- claim: 'Live server behavior (24h expiry, ordering of results not matching request order, 50% price discount actually billed) matches the SDK model'
  result: untested
raw_output_path: .ll/learning-tests/raw/anthropic-batches-api.txt
---
