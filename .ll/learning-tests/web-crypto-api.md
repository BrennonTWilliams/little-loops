---
target: Web Crypto API
date: '2026-09-19'
status: proven
assertions:
- claim: crypto.subtle.digest('SHA-256', data) resolves to a 32-byte ArrayBuffer
  result: pass
- claim: SHA-256 of "abc" hex-encodes to ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
  result: pass
- claim: crypto.getRandomValues fills the typed array in place and returns the same array
  result: pass
- claim: crypto.randomUUID returns a v4 UUID string
  result: pass
- claim: AES-GCM encrypt/decrypt round-trips and ciphertext is plaintext length + 16 bytes (tag)
  result: pass
- claim: AES-GCM decrypt of tampered ciphertext rejects with OperationError
  result: pass
- claim: HMAC verify accepts the right message, rejects a different one, and exportKey on a non-extractable key throws InvalidAccessError
  result: pass
- claim: crypto.subtle.digest rejects a string argument with TypeError
  result: pass
raw_output_path: .ll/learning-tests/raw/web-crypto-api.txt
---
