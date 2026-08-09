---
target: ruamel.yaml
date: '2026-08-08'
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
- claim: CommentedSeq (list under round-trip mode) preserves per-item comments through a load-dump cycle
  result: pass
- claim: yaml.indent(mapping=2, sequence=4, offset=2) changes list-item indentation in dump output
  result: pass
- claim: inserting a new key into a CommentedMap at a specific position (via insert()) places it there in dump output, not appended at the end
  result: pass
- claim: yaml.preserve_quotes = True preserves original quote style (single vs double) on scalar strings through round-trip
  result: pass
- claim: dumping a CommentedMap with yaml.width set to a small value wraps long scalar lines
  result: pass
raw_output_path: .ll/learning-tests/raw/ruamelyaml.txt
---
