---
target: Anthropic pricing page
date: '2026-09-24'
status: proven
assertions:
- claim: Sonnet 5 standard rates are $2 input / $10 output / $0.20 read / $2.50 5m write
  result: pass
- claim: Sonnet 5 $2/$10 intro pricing is documented as now standard (planned $3/$15 increase cancelled)
  result: pass
- claim: Opus 4.5, 4.6 and 4.7 are each $5 input / $25 output / $0.50 read / $6.25 5m write
  result: pass
- claim: Haiku 4.5 is $1 input / $5 output / $0.10 read / $1.25 5m write
  result: pass
- claim: For all other models 5m cache write = 1.25x input and cache read = 0.1x input
  result: pass
- claim: Fable 5.1 cache read is 0.025x input ($0.25) and Opus 5.5 is $4/$20 with 0.05x read ($0.20)
  result: pass
- claim: Batch input/output rates are exactly 50% of standard for every model
  result: pass
raw_output_path: .ll/learning-tests/raw/anthropic-pricing-page.txt
---
