---
target: direct_url.json
date: '2026-09-26'
status: proven
assertions:
- claim: Distribution.read_text("direct_url.json") returns a str for an editable install
  result: pass
- claim: the parsed JSON has a "url" key starting with "file://" for a local-directory install
  result: pass
- claim: the parsed JSON has dir_info.editable == true for a pip install -e install
  result: pass
- claim: Distribution.read_text("direct_url.json") returns None for dists installed from an index
  result: pass
- claim: direct_url.json appears in Distribution.files for the editable install
  result: pass
raw_output_path: .ll/learning-tests/raw/direct_urljson.txt
---
