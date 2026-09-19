---
target: Fetch API
date: '2026-09-19'
status: proven
assertions:
- claim: fetch resolves (does not reject) on HTTP 4xx/5xx with response.ok === false
  result: pass
- claim: fetch rejects with TypeError (cause.code ECONNREFUSED) on network failure
  result: pass
- claim: response.json() throws SyntaxError on a non-JSON body
  result: pass
- claim: a response body can be consumed only once; a second read rejects with TypeError
  result: pass
- claim: AbortSignal.timeout() aborts fetch with a TimeoutError DOMException
  result: pass
- claim: response.headers lookups are case-insensitive and names are lowercased
  result: pass
- claim: a POST with a string body and no content-type header sends text/plain;charset=UTF-8
  result: pass
raw_output_path: .ll/learning-tests/raw/fetch-api.txt
---
