---
target: unicodedata
date: '2026-09-24'
status: proven
assertions:
- claim: unicodedata.category("​") returns "Cf"
  result: pass
- claim: unicodedata.category("\x00") returns "Cc"
  result: pass
- claim: unicodedata.normalize("NFC", "é") equals "é"
  result: pass
- claim: unicodedata.name("A") returns "LATIN CAPITAL LETTER A"
  result: pass
- claim: unicodedata.name("\x00") raises ValueError when no default is given
  result: pass
- claim: east_asian_width returns "Na" for "A" and "W" for "あ"
  result: pass
- claim: unicodedata.combining("́") returns 230
  result: pass
raw_output_path: .ll/learning-tests/raw/unicodedata.txt
---
