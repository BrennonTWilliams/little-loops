---
target: OpenTelemetry
date: '2026-09-23'
status: proven
assertions:
- claim: span.set_attribute("k", "v") sets an attribute retrievable as span.attributes["k"] == "v" on the finished span
  result: pass
- claim: BatchSpanProcessor does not export synchronously, but provider.force_flush() makes InMemorySpanExporter.get_finished_spans() contain the span immediately
  result: pass
- claim: OTLPSpanExporter(endpoint="http://localhost:1") (grpc exporter, unreachable endpoint) constructs without raising
  result: pass
- claim: calling span.end() twice does not raise (logs a warning and exports once)
  result: pass
- claim: a three-level span chain (loop -> state -> action, each via set_span_in_context) has correct parent span_ids and a root with parent None
  result: pass
- claim: span.set_status(StatusCode.ERROR, "boom") is preserved on the finished span with the description
  result: pass
- claim: the default global tracer (no provider configured) yields non-recording spans
  result: pass
raw_output_path: .ll/learning-tests/raw/opentelemetry.txt
---
