---
url: https://docs.boundaryml.com/ref/baml_client/image.mdx
scraped_at: 2026-03-06T01:00:42.528656
filepath: docs-docs-boundaryml-com/ref/baml-client/imagemdx.md
---


***

title: Image
description: Learn how to handle image inputs in BAML functions
---------------------------------------------------------------

Image values to BAML functions can be created in client libraries. This document explains how to use these functions both at compile time and runtime to handle image data. For more details, refer to [image types](/ref/baml/types#image).

## Usage Examples```python
  from baml_py import Image
  from baml_client import b

  async def test_image_input():
      # Create an Image from a URL
      img = Image.from_url("https://upload.wikimedia.org/wikipedia/en/4/4d/Shrek_%28character%29.png")
      res = await b.TestImageInput(img=img)

      # Create an Image from Base64 data
      image_b64 = "iVB0xyz..."
      img = Image.from_base64("image/png", image_b64)
      res = await b.TestImageInput(img=img)
  ```

  ```typescript
  import { b } from '../baml_client'
  import { Image } from "@boundaryml/baml"

  // Create an Image from a URL
  let res = await b.TestImageInput(
      Image.fromUrl('https://upload.wikimedia.org/wikipedia/en/4/4d/Shrek_%28character%29.png')
  )

  // Create an Image from Base64 data
  const image_b64 = "iVB0xyz..."
  res = await b.TestImageInput(
      Image.fromBase64('image/png', image_b64)
  )

  // Browser-specific methods
  const fileImage = await Image.fromFile(file)
  const blobImage = await Image.fromBlob(blob, 'image/png')
  ```

  ```tsx
  import { useTestImageInput } from '../baml_client/react/hooks'
  import { Image } from "../baml_client/react/media"

  export function TestImageInput() {
      const { mutate } = useTestImageInput()

      const handleClick = async () => {
          const image = await Image.fromUrl('https://upload.wikimedia.org/wikipedia/en/4/4d/Shrek_%28character%29.png')
          mutate(image)
      }

      return (Test Image Input)
  }
  ```

  ```go
  package main

  import (
      "context"
      
      b "example.com/myproject/baml_client"
  )

  func testImageInput() error {
      ctx := context.Background()
      
      // Create an Image from a URL
      img, err := b.NewImageFromUrl("https://upload.wikimedia.org/wikipedia/en/4/4d/Shrek_%28character%29.png", nil)
      if err != nil {
          return err
      }
      
      result, err := b.TestImageInput(ctx, img)
      if err != nil {
          return err
      }

      // Create an Image from Base64 data
      imageB64 := "iVB0xyz..."
      img2, err := b.NewImageFromBase64(imageB64, stringPtr("image/png"))
      if err != nil {
          return err
      }
      
      result2, err := b.TestImageInput(ctx, img2)
      if err != nil {
          return err
      }
      
      return nil
  }

  // Helper function for string pointer
  func stringPtr(s string) *string {
      return &s
  }
  ```

  ```rust Rust
  use myproject::baml_client::sync_client::B;
  use myproject::baml_client::new_image_from_url;
  use myproject::baml_client::new_image_from_base64;

  fn test_image_input() {
      // Create an Image from a URL
      let img = new_image_from_url(
          "https://upload.wikimedia.org/wikipedia/en/4/4d/Shrek_%28character%29.png",
          None,
      );
      let res = B.TestImageInput.call(&img).unwrap();

      // Create an Image from Base64 data
      let image_b64 = "iVB0xyz...";
      let img = new_image_from_base64(image_b64, Some("image/png"));
      let res = B.TestImageInput.call(&img).unwrap();
  }
  ```

  ```ruby
  # Ruby implementation is in development.
  ```## API Reference### Static MethodsCreates an Image object from a URL. Optionally specify the media type, otherwise it will be inferred from the URL.Creates an Image object using Base64 encoded data along with the given MIME type.### Instance MethodsCheck if the image is stored as a URL.Get the URL of the image if it's stored as a URL. Raises an exception if the image is not stored as a URL.Get the base64 data and media type if the image is stored as base64. Returns `[base64_data, media_type]`. Raises an exception if the image is not stored as base64.Convert the image to a dictionary representation. Returns either `{"url": str}` or `{"base64": str, "media_type": str}`.### Static MethodsCreates an Image object from a URL. Optionally specify the media type, otherwise it will be inferred from the URL.Creates an Image object using Base64 encoded data along with the given MIME type.Only available in browser environments. @boundaryml/baml/browserCreates an Image object from a File object. Available in browser environments only.Only available in browser environments. @boundaryml/baml/browserCreates an Image object from a Blob object. Available in browser environments only.Only available in browser environments.Creates an Image object by fetching from a URL. Available in browser environments only.### Instance MethodsCheck if the image is stored as a URL.Get the URL of the image if it's stored as a URL. Throws an Error if the image is not stored as a URL.Get the base64 data and media type if the image is stored as base64. Returns `[base64Data, mediaType]`. Throws an Error if the image is not stored as base64.Convert the image to a JSON representation. Returns either a URL object or a base64 object with media type.### Static MethodsCreates an Image object from a URL. Optionally specify the media type, otherwise it will be inferred from the URL.Creates an Image object using Base64 encoded data along with the given MIME type.### Instance MethodsCheck if the image is stored as a URL.Get the URL of the image if it's stored as a URL. Returns an error if the image is not stored as a URL.Get the base64 data and media type if the image is stored as base64. Returns `(base64Data, mediaType, error)`. Returns an error if the image is not stored as base64.Convert the image to a map representation. Returns either `{"url": string}` or `{"base64": string, "media_type": string}`.### Static MethodsCreates an Image from a URL. Optionally specify the media type.Creates an Image from Base64 encoded data with an optional MIME type.Ruby implementation is in development.## URL Handling

When you create an Image using `from_url`, BAML processes the URL according to your client's `media_url_handler` configuration:

* **[OpenAI](/ref/llm-client-providers/open-ai#media_url_handler)**: By default keeps URLs as-is (`send_url`). Set to `send_base64` to convert to base64.
* **[Anthropic](/ref/llm-client-providers/anthropic#media_url_handler)**: By default keeps URLs as-is (`send_url`). The provider accepts both formats.
* **[Google AI](/ref/llm-client-providers/google-ai-gemini#media_url_handler)**: By default uses `send_base64_unless_google_url` to preserve gs\:// URLs while converting others.
* **[Vertex AI](/ref/llm-client-providers/google-vertex#media_url_handler)**: By default uses `send_url_add_mime_type` to include MIME type information.
* **[AWS Bedrock](/ref/llm-client-providers/aws-bedrock#media_url_handler)**: By default converts to base64 (`send_base64`).

You can override these defaults in your client configuration. See the provider-specific documentation linked above for details.
