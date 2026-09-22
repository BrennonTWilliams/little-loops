---
target: crypto.subtle
date: '2026-09-22'
status: proven
assertions:
- claim: 'generateKey(''ECDSA'', P-256) returns a CryptoKeyPair with publicKey/privateKey as CryptoKey instances'
  result: pass
- claim: ECDSA sign/verify round-trips with SHA-256, and verify rejects tampered data
  result: pass
- claim: 'importKey(''jwk'', ...) accepts a JWK-format EC key'
  result: pass
- claim: 'exportKey(''jwk'', key) on an imported key round-trips back matching JWK fields (crv, x, y)'
  result: pass
- claim: deriveBits with PBKDF2 produces exactly the requested bit-length output
  result: pass
- claim: digest supports SHA-1 and SHA-512 (not just SHA-256)
  result: pass
raw_output_path: .ll/learning-tests/raw/cryptosubtle.txt
---
