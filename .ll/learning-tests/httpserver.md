---
target: http.server
date: '2026-08-28'
status: proven
assertions:
- claim: ThreadingHTTPServer binds to 127.0.0.1 loopback with an ephemeral port (port=0)
  result: pass
- claim: a handler can send Content-Type text/event-stream with Transfer-Encoding chunked and the client sees those headers
  result: pass
- claim: chunked SSE frames written incrementally (wfile.write + flush per frame) are received by the client incrementally, not buffered until the response closes
  result: pass
- claim: an unmatched path returns a distinct status code (404) via ordinary do_GET routing
  result: pass
- claim: a POST body is readable via rfile.read(Content-Length) and can be delivered to a queue.Queue shared with the SSE handler thread
  result: pass
- claim: server.shutdown() followed by server.server_close() terminates a ThreadingHTTPServer cleanly without hanging
  result: pass
raw_output_path: .ll/learning-tests/raw/httpserver.txt
---
