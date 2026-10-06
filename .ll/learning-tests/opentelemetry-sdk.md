---
target: opentelemetry-sdk
date: '2026-10-06'
status: proven
assertions:
- claim: InMemorySpanExporter is importable from opentelemetry.sdk.trace.export.in_memory_span_exporter
  result: pass
- claim: a span started via tracer.start_span is not exported until span.end() is called
  result: pass
- claim: after end(), InMemorySpanExporter.get_finished_spans() returns the span with .name equal to the name passed to start_span
  result: pass
- claim: attributes set on the span before end() are readable on the finished span
  result: pass
- claim: InMemorySpanExporter.clear() empties get_finished_spans()
  result: pass
raw_output_path: .ll/learning-tests/raw/opentelemetry-sdk.txt
---
