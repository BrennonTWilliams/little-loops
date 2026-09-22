---
target: node:crypto
date: '2026-09-22'
status: proven
assertions:
- claim: createHash sha256 hex digest is 64-char lowercase hex
  result: pass
- claim: randomBytes(n) returns a Buffer of length n
  result: pass
- claim: randomUUID() returns a string matching RFC 4122 v4 UUID format
  result: pass
- claim: createHmac sha256 hex digest is 64-char hex
  result: pass
- claim: webcrypto.subtle is available as the Web Crypto SubtleCrypto interface
  result: pass
- claim: timingSafeEqual throws when given buffers of different lengths
  result: pass
- claim: createHash throws when given an unsupported digest algorithm name
  result: pass
raw_output_path: .ll/learning-tests/raw/nodecrypto.txt
---
