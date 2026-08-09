---
target: opentelemetry
date: '2026-08-08'
status: proven
assertions:
- claim: 'span.set_attribute("k", "v") sets an attribute retrievable as span.attributes["k"] == "v" on the finished span'
  result: pass
- claim: BatchSpanProcessor + provider.force_flush() (not SimpleSpanProcessor) still makes InMemorySpanExporter.get_finished_spans() contain the span immediately, no async delay needed
  result: pass
- claim: OTLPSpanExporter(endpoint="http://localhost:1") (grpc exporter, no insecure kwarg, unreachable endpoint) constructs without raising
  result: pass
- claim: calling span.end() twice does not raise
  result: pass
- claim: a three-level span chain (loop -> state -> action, each via set_span_in_context) has action_span.parent.span_id == state_span.get_span_context().span_id
  result: pass
raw_output_path: .ll/learning-tests/raw/opentelemetry.txt
---
