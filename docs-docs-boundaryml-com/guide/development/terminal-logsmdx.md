---
url: https://docs.boundaryml.com/guide/development/terminal-logs.mdx
scraped_at: 2026-03-06T01:00:28.340697
filepath: docs-docs-boundaryml-com/guide/development/terminal-logsmdx.md
---


***

## slug: /guide/development/terminal-logs

You can add logging to determine what the BAML runtime is doing when it calls LLM endpoints and parses responses.

To enable logging, set the `BAML_LOG` environment variable:

```sh
# default is info
BAML_LOG=info
``````go Go
  // Set logging level in Go application
  os.Setenv("BAML_LOG", "info")

  // Or run with environment variable:
  // BAML_LOG=info go run main.go
  ```

  ```python Python
  # Set logging level in Python
  import os
  os.environ["BAML_LOG"] = "info"

  # Or run with environment variable:
  # BAML_LOG=info python main.py
  ```

  ```typescript TypeScript
  // Set logging level in TypeScript/JavaScript
  process.env.BAML_LOG = "info";

  // Or run with environment variable:
  // BAML_LOG=info node main.js
  ```| Level   | Description                                                                         |
| ------- | ----------------------------------------------------------------------------------- |
| `error` | Fatal errors by BAML                                                                |
| `warn`  | Logs any time a function fails (includes LLM calling failures, parsing failures)    |
| `info`  | Logs every call to a function (including prompt, raw response, and parsed response) |
| `debug` | Requests and detailed parsing errors (warning: may be a lot of logs)                |
| `trace` | Everything and more                                                                 |
| `off`   | No logging                                                                          |

Example log:***

Since `>0.54.0`:

To truncate each log entry to a certain length, set the `BOUNDARY_MAX_LOG_CHUNK_CHARS` environment variable:

```sh
BOUNDARY_MAX_LOG_CHUNK_CHARS=3000
```

This will truncate each part in a log entry to 3000 characters.```go Go
  // Set log truncation in Go application
  os.Setenv("BOUNDARY_MAX_LOG_CHUNK_CHARS", "3000")

  // Example with both logging and truncation
  func main() {
      // Configure logging
      os.Setenv("BAML_LOG", "info")
      os.Setenv("BOUNDARY_MAX_LOG_CHUNK_CHARS", "3000")
      
      // Your application code here
  }
  ```

  ```python Python
  # Set log truncation in Python
  import os
  os.environ["BOUNDARY_MAX_LOG_CHUNK_CHARS"] = "3000"

  # Example with both logging and truncation
  os.environ["BAML_LOG"] = "info"
  os.environ["BOUNDARY_MAX_LOG_CHUNK_CHARS"] = "3000"
  ```

  ```typescript TypeScript
  // Set log truncation in TypeScript/JavaScript
  process.env.BOUNDARY_MAX_LOG_CHUNK_CHARS = "3000";

  // Example with both logging and truncation
  process.env.BAML_LOG = "info";
  process.env.BOUNDARY_MAX_LOG_CHUNK_CHARS = "3000";
  ```
