---
target: Anthropic API pricing
date: '2026-10-04'
status: proven
assertions:
- claim: 1h cache write is exactly 2x base input and 5m cache write exactly 1.25x for every current model
  result: pass
- claim: Cache read is 0.1x base input except Fable 5.1 (0.025x) and Opus 5.5 (0.05x)
  result: pass
- claim: Batch input/output rates are exactly 50% of standard (Sonnet 5.5 is $1/$5, Opus 5.5 is $2/$10)
  result: pass
- claim: Fast mode is exactly 2x standard input/output (Opus 5.5 $8/$40, Opus 5 and 4.8 $10/$50)
  result: pass
- claim: little_loops.pricing.estimate_cost_usd applies the batch discount to all four cache-adjusted token types
  result: pass
- claim: little_loops.pricing.MODEL_PRICING rates match the page for every model it contains
  result: pass
- claim: little_loops.pricing.MODEL_PRICING covers every current page model
  result: fail
- claim: 'US inference_geo applies a 1.1x multiplier to all four token types on Claude 4.6+ models'
  result: untested
- claim: 'Web search costs $10 per 1,000 searches and web fetch has no extra charge'
  result: untested
raw_output_path: .ll/learning-tests/raw/anthropic-api-pricing.txt
---
