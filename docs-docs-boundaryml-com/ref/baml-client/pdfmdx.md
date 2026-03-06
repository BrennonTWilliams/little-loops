---
url: https://docs.boundaryml.com/ref/baml_client/pdf.mdx
scraped_at: 2026-03-06T01:00:43.029873
filepath: docs-docs-boundaryml-com/ref/baml-client/pdfmdx.md
---


***

title: Pdf
description: Learn how to handle Pdf inputs in BAML functions
-------------------------------------------------------------

Pdf values to BAML functions can be created in client libraries. This document explains how to use these functions both at compile time and runtime to handle Pdf data. For more details, refer to [pdf types](/ref/baml/types#pdf).`Pdf` instances can be created from URLs, Base64 data, or local files. URL
  processing is controlled by your client's
  [`media_url_handler`](/ref/baml_client/pdf#url-handling) configuration.
  Please note that many websites will block requests to directly fetch PDFs.Some models like Vertex AI require the media type to be explicitly specified.
  Always provide the `mediaType` parameter when possible for better compatibility.The PDF input may need to be put into the `user` message, not the `system` message in your prompt.## Usage Examples```python
  from baml_py import Pdf
  from baml_client import b

  async def test_pdf_input():
      # Create a Pdf object from URL
      pdf_url = Pdf.from_url("https://example.com/document.pdf")
      res1 = await b.TestPdfInput(pdf=pdf_url)
      
      # Create a Pdf object from Base64 data
      pdf_b64 = "JVBERi0K..."
      pdf = Pdf.from_base64(pdf_b64)
      res2 = await b.TestPdfInput(pdf=pdf)
  ```

  ```typescript
  import { b } from '../baml_client'
  import { Pdf } from "@boundaryml/baml"

  // Create a Pdf object from URL
  const pdfUrl = Pdf.fromUrl('https://example.com/document.pdf')
  const res1 = await b.TestPdfInput(pdfUrl)

  // Create a Pdf object from Base64 data
  const pdf_b64 = "JVBERi0K..."
  const res2 = await b.TestPdfInput(
    Pdf.fromBase64(pdf_b64)
  )

  // Browser-specific helpers
  const filePdf = await Pdf.fromFile(file)
  const blobPdf = await Pdf.fromBlob(blob)
  ```

  ```tsx
  import { useTestPdfInput } from '../baml_client/react/hooks'
  import { Pdf } from "../baml_client/react/media"

  export function TestPdfInput() {
      const { mutate } = useTestPdfInput()

      const handleClick = async () => {
          // Using URL
          const pdfUrl = Pdf.fromUrl('https://example.com/document.pdf')
          mutate(pdfUrl)
          
          // Or using Base64
          const pdf_b64 = "JVBERi0K..."
          const pdf = Pdf.fromBase64(pdf_b64)
          mutate(pdf)
      }

      return (Test Pdf Input)
  }
  ```

  ```go
  package main

  import (
      "context"
      
      b "example.com/myproject/baml_client"
  )

  func testPdfInput() error {
      ctx := context.Background()
      
      // Create a PDF object from URL
      pdfUrl, err := b.NewPDFFromUrl("https://example.com/document.pdf", nil)
      if err != nil {
          return err
      }
      
      result1, err := b.TestPdfInput(ctx, pdfUrl)
      if err != nil {
          return err
      }
      
      // Create a PDF object from Base64 data
      pdfB64 := "JVBERi0K..."
      pdf, err := b.NewPDFFromBase64(pdfB64, nil)
      if err != nil {
          return err
      }
      
      result2, err := b.TestPdfInput(ctx, pdf)
      if err != nil {
          return err
      }
      
      return nil
  }
  ```

  ```rust Rust
  use myproject::baml_client::sync_client::B;
  use myproject::baml_client::new_pdf_from_base64;

  fn test_pdf_input() {
      // Create a PDF from Base64 data
      let b64 = "JVBERi0K....";
      let pdf = new_pdf_from_base64(b64, None);
      let res = B.TestPdfInput.call(&pdf).unwrap();
  }
  ```

  ```ruby
  # Ruby implementation is in development.
  ```## Test Pdf in the Playground

To test a function that accepts a `pdf` in the VSCode playground using a local file, add a `test` block to your `.baml` file:

```baml
function AnalyzePdf(myPdf: pdf) -> string {
  client GPT4o
  prompt #"
    Summarize this Pdf: {{myPdf}}
  "#
}

test PdfFileTest {
  functions [AnalyzePdf]
  args {
    myPdf {
      file "../documents/report.pdf"
    }
  }
}
```The path to the PDF file. Supports relative paths (resolved from the current BAML file) or absolute paths. The file does not need to be inside `baml_src/`.## API Reference### Static MethodsCreates a Pdf object from a URL. The media type is automatically set to `application/pdf`.Creates a Pdf object using Base64 encoded data. The media type is automatically set to `application/pdf`.### Instance MethodsCheck if the Pdf is stored as a URL.Get the URL if the Pdf is stored as a URL. Raises an exception if the Pdf is not stored as a URL.Get the base64 data and media type if the Pdf is stored as base64. Returns `[base64_data, media_type]`. Raises an exception if the Pdf is not stored as base64.Convert the Pdf to a dictionary representation. Returns either `{"url": str}` or `{"base64": str, "media_type": str}`.### Static MethodsCreates a Pdf object from a URL. The `mediaType` parameter is optional but recommended for better model compatibility. If not provided, the media type will be inferred when the content is fetched.Creates a Pdf object using Base64 encoded data. The media type is automatically set to `application/pdf`.Only available in browser environments. @boundaryml/baml/browserCreates a Pdf object from a File object. Available in browser environments only.Only available in browser environments. @boundaryml/baml/browserCreates a Pdf object from a Blob object. Available in browser environments only.### Instance MethodsCheck if the Pdf is stored as a URL.Get the URL if the Pdf is stored as a URL. Throws an Error if the Pdf is not stored as a URL.Get the base64 data and media type if the Pdf is stored as base64. Returns `[base64Data, mediaType]`. Throws an Error if the Pdf is not stored as base64.Convert the Pdf to a JSON representation. Returns either a URL object or a base64 object with media type, depending on how the Pdf was created.### Static MethodsCreates a PDF object from a URL. Optionally specify the media type for better model compatibility.Creates a PDF object using Base64 encoded data. The media type is automatically set to `application/pdf` if not provided.### Instance MethodsCheck if the PDF is stored as a URL.Get the URL if the PDF is stored as a URL. Returns an error if the PDF is not stored as a URL.Get the base64 data and media type if the PDF is stored as base64. Returns `(base64Data, mediaType, error)`. Returns an error if the PDF is not stored as base64.Convert the PDF to a map representation. Returns either `{"url": string}` or `{"base64": string, "media_type": string}`.### Static MethodsCreates a PDF from Base64 encoded data. The media type defaults to `application/pdf`.Ruby implementation is in development.## URL Handling

PDF URLs are processed according to your client's `media_url_handler` configuration:

* **[Anthropic](/ref/llm-client-providers/anthropic#media_url_handler)**: By default converts to base64 (`send_base64`) as required by their API.
* **[AWS Bedrock](/ref/llm-client-providers/aws-bedrock#media_url_handler)**: By default converts to base64 (`send_base64`).
* **[OpenAI](/ref/llm-client-providers/open-ai#media_url_handler)**: By default keeps URLs as-is (`send_url`).
* **[Google AI](/ref/llm-client-providers/google-ai-gemini#media_url_handler)**: By default keeps URLs as-is (`send_url`).
* **[Vertex AI](/ref/llm-client-providers/google-vertex#media_url_handler)**: By default keeps URLs as-is (`send_url`).Many websites block direct PDF fetching. If you encounter issues with URL-based PDFs, try:

  1. Using `media_url_handler.pdf = "send_base64"` to fetch and embed the content
  2. Downloading the PDF locally and using `from_file`
  3. Using a proxy or authenticated request## Configuring Media URL Handlers

You can customize how PDF URLs are processed by configuring the `media_url_handler` in your BAML client definition. This is useful when you need to override provider defaults or ensure compatibility with specific model requirements.

```baml
// Basic example: OpenAI client with PDF base64 encoding
clientMyOpenAIClient {
  provider openai
  options {
    model "gpt-4o"
    api_key env.OPENAI_API_KEY
    media_url_handler {
      pdf "send_base64"  // Convert PDF URLs to base64
    }
  }
}

function AnalyzePdf(pdf: pdf) -> string {
  client MyOpenAIClient
  prompt #"
    Analyze this PDF: {{ pdf }}
  "#
}
```

### Available Modes

The `media_url_handler.pdf` setting accepts the following values:

* **`send_base64`**: Fetch the PDF from the URL and convert it to base64 before sending to the model. Use this when the provider requires base64 encoding or when you want to ensure the content is embedded in the request.

* **`send_url`**: Keep the PDF as a URL and send it directly to the model. The model provider will fetch the content. Note that many providers don't support direct URL fetching for PDFs.

* **`send_url_add_mime_type`**: Keep the PDF as a URL but add MIME type information (`application/pdf`). Useful for providers like Vertex AI that require explicit MIME types.

* **`send_base64_unless_google_url`**: Keep Google Cloud Storage URLs (`gs://`) as-is, but convert all other URLs to base64. Useful when working with Google AI models.

### Provider-Specific Examples

```baml
// OpenAI: Override default (send_url) to use base64
clientOpenAIClient {
  provider openai
  options {
    model "gpt-4o"
    api_key env.OPENAI_API_KEY
    media_url_handler {
      pdf "send_base64"  // OpenAI requires base64 for PDFs
    }
  }
}

// Anthropic: Override default (send_base64) to use URL
clientAnthropicClient {
  provider anthropic
  options {
    model "claude-3-5-sonnet-20241022"
    api_key env.ANTHROPIC_API_KEY
    media_url_handler {
      pdf "send_url"  // Anthropic supports both URL and base64
    }
  }
}

// Vertex AI: Use URL with MIME type
clientVertexClient {
  provider vertex-ai
  options {
    model "gemini-1.5-pro"
    project "your-project"
    location "us-central1"
    media_url_handler {
      pdf "send_url_add_mime_type"  // Vertex requires MIME type
    }
  }
}

// Google AI: Use conditional handling for GCS URLs
clientGoogleAIClient {
  provider google-ai
  options {
    model "gemini-1.5-pro"
    api_key env.GOOGLE_API_KEY
    media_url_handler {
      pdf "send_base64_unless_google_url"  // Keep gs:// URLs, convert others
    }
  }
}

// You can configure multiple media types independently
clientMultiMediaClient {
  provider openai
  options {
    model "gpt-4o"
    api_key env.OPENAI_API_KEY
    media_url_handler {
      image "send_base64"
      audio "send_url"
      pdf "send_base64"
      video "send_url"
    }
  }
}
```You can configure different handling modes for each media type (`image`, `audio`, `pdf`, `video`) independently in the same client.## Model Compatibility

Different AI models have varying levels of support for PDF input methods **(As of July 2025)**:

| Provider / API       |   | PDF Input Support                                                                                                                                                           |
| -------------------- | - | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Anthropic**        | ✓ | Accepts PDFs as a direct https URL or a base‑64 string in a document block.                                                                                                 |
| **AWS Bedrock**      | ✓ | PDF must be supplied as raw bytes (base‑64 in the request) or as an Amazon S3 URI (s3:// style). Ordinary https links are not supported.                                    |
| **Google Gemini**    | ✓ | Provide as inline base‑64 or upload first with media.upload and use the returned file\_uri. The model does not fetch http/https URLs for you.                               |
| **OpenAI**           | ✓ | PDF support (added March 2025) via base‑64 in the request. Supplying a plain URL is not accepted.                                                                           |
| **Google Vertex AI** | ✓ | Accepts either base‑64 data or a Cloud Storage gs\:// URI in a file\_data part; you must set mime\_type (for PDFs use application/pdf). Generic https URLs are not allowed. |For most models, direct https URLs are not accepted (except Anthropic). Prefer using base64, file uploads, or the appropriate cloud storage/file upload mechanism for your provider. Always specify the correct MIME type (e.g., application/pdf) when required.
