---
target: ruamel.yaml
date: '2026-06-19'
status: proven
assertions:
- claim: YAML(typ="rt") loads into CommentedMap, not plain dict
  result: pass
- claim: yaml.load(Path) accepts a pathlib.Path object directly
  result: pass
- claim: LiteralScalarString forces block literal style (action':' |) in dump output
  result: pass
- claim: round-trip mode preserves YAML comments through load-dump cycle
  result: pass
- claim: YAML(typ="safe") loads into a plain dict (not CommentedMap)
  result: pass
- claim: yaml.dump(data, StringIO()) produces str, not bytes
  result: pass
- claim: modifying one key in CommentedMap leaves sibling keys unchanged
  result: pass
raw_output_path: .ll/learning-tests/raw/ruamelyaml.txt
---
