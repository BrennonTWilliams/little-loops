---
url: https://docs.boundaryml.com/ref/baml_client/errors/baml-validation-error.mdx
scraped_at: 2026-03-06T01:00:41.976216
filepath: docs-docs-boundaryml-com/ref/baml-client/errors/baml-validation-errormdx.md
---


***

title: BamlValidationError
description: Technical reference for the BamlValidationError class
------------------------------------------------------------------

The `BamlValidationError` class represents an error that occurs when BAML fails to parse or validate LLM output.

## Type Definition```typescript Type Definition
  class BamlValidationError extends Error {
    type: 'BamlValidationError'
    message: string
    prompt: string
    raw_output: string
    detailed_message: string
  }
  ```## PropertiesLiteral type identifier for the error class.Error message describing the specific validation failure.The original prompt sent to the LLM.The raw output from the LLM that failed validation.Comprehensive error information that includes the complete history of all failed attempts when using fallback clients or retry policies. When multiple attempts are made (via fallback or retry), this field contains formatted details about each failed attempt, making it invaluable for debugging complex client configurations.## Type Guards

The error can be identified using TypeScript's `instanceof` operator:```typescript Type Check
  if (error instanceof BamlValidationError) {
    // Handle validation error
  }
  ```## Related Errors

* [BamlClientFinishReasonError](/ref/baml_client/errors/baml-client-finish-reason-error)
* [BamlClientError](/ref/baml_client/errors/baml-client-finish-reason-error)
