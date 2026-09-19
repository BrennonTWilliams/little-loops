---
target: Web Storage API
date: '2026-09-19'
status: proven
assertions:
- claim: setItem coerces non-string values to strings
  result: pass
- claim: getItem returns null for a missing key
  result: pass
- claim: length counts entries and key(n) returns the key name, or null when out of range
  result: pass
- claim: removeItem on a missing key does not throw, and removes an existing key
  result: pass
- claim: clear() empties the storage
  result: pass
- claim: property assignment/access maps to items and stringifies values
  result: pass
- claim: localStorage and sessionStorage are separate stores
  result: pass
- claim: exceeding the quota throws QuotaExceededError
  result: pass
- claim: localStorage is available in Node without any flag
  result: fail
raw_output_path: .ll/learning-tests/raw/web-storage-api.txt
---
