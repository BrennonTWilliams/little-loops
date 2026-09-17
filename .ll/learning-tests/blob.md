---
target: Blob
date: '2026-09-17'
status: proven
assertions:
- claim: Blob is a global constructor in Node (no require/import)
  result: pass
- claim: new Blob([...parts]).size equals UTF-8 byte length of concatenated string parts
  result: pass
- claim: new Blob([...], {type}).type returns the type string as given
  result: pass
- claim: blob.text() resolves to the original string content
  result: pass
- claim: blob.arrayBuffer() resolves to an ArrayBuffer whose byteLength equals blob.size
  result: pass
- claim: blob.stream() returns a ReadableStream whose chunks concatenate to the original bytes
  result: pass
- claim: blob.slice(0, 5) returns a new immutable Blob with size === 5, leaving the original unmutated
  result: pass
raw_output_path: .ll/learning-tests/raw/blob.txt
---
