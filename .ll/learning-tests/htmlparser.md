---
target: html.parser
date: '2026-09-24'
status: proven
assertions:
- claim: feed() of a start tag calls handle_starttag with attrs as a list of (name, value) tuples
  result: pass
- claim: tag and attribute names are lowercased while attribute values keep their case
  result: pass
- claim: a valueless (boolean) attribute has value None
  result: pass
- claim: with default convert_charrefs=True, entities in attribute values and text data are decoded
  result: pass
- claim: a self-closing tag like <br/> calls handle_startendtag only
  result: pass
- claim: script contents are delivered as a single handle_data call and not parsed as tags
  result: pass
- claim: close() does not synthesize handle_endtag for unclosed tags
  result: pass
- claim: with convert_charrefs=False, entities arrive via handle_entityref and split the data
  result: pass
raw_output_path: .ll/learning-tests/raw/htmlparser.txt
---
