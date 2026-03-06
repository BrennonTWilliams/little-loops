---
url: https://docs.boundaryml.com/ref/baml_client/errors/baml-client-finish-reason-error.mdx
scraped_at: 2026-03-06T01:00:42.137293
filepath: docs-docs-boundaryml-com/ref/baml-client/errors/baml-client-finish-reason-errormdx.md
---


***

title: BamlClientFinishReasonError
description: Technical reference for the BamlClientFinishReasonError class
--------------------------------------------------------------------------

The `BamlClientFinishReasonError` class represents an error that occurs when an LLM terminates with a disallowed finish reason.

You can allow or disallow finish reasons like this:```baml
  clientOpenAIWithFinishReasonError {
    provider openai
    options {
      api_key env.OPENAI_API_KEY
      model "gpt-4"
      // make it very small so model will stop early
      max_tokens 10 
      // throws if the model returns any other finish reason
      finish_reason_allow_list ["stop"]
      // or allow all finish reasons except length
      // finish_reason_deny_list ["length"]
    }
  }
  ```## Type Definition```typescript Type Definition
  class BamlClientFinishReasonError extends Error {
    type: 'BamlClientFinishReasonError'
    message: string
    prompt: string
    raw_output: string
    detailed_message: string
  }
  ```## PropertiesLiteral type identifier for the error class.Error message describing the specific finish reason that caused the termination.The original prompt sent to the LLM.The partial output received from the LLM before termination.Comprehensive error information that includes the complete history of all failed attempts when using fallback clients or retry policies. When multiple attempts are made (via fallback or retry), this field contains formatted details about each failed attempt, making it invaluable for debugging complex client configurations.## Type Guards

The error can be identified using TypeScript's `instanceof` operator:```typescript Type Check
  if (error instanceof BamlClientFinishReasonError) {
    // Handle finish reason error
  }
  ```
