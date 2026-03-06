---
url: https://docs.boundaryml.com/ref/baml_client/video.mdx
scraped_at: 2026-03-06T01:00:44.570298
filepath: docs-docs-boundaryml-com/ref/baml-client/videomdx.md
---


***

title: Video
description: Learn how to handle video inputs in BAML functions
---------------------------------------------------------------

Video values to BAML functions can be created in client libraries. This document explains how to use these functions both at compile time and runtime to handle video data. For more details, refer to [video types](/ref/baml/types#video).When you create a `Video` using `from_url` (Python) or `fromUrl` (TypeScript), the URL is passed directly to the model without any intermediate fetching. If the model cannot access external media, it will fail on such inputs. In these cases, convert the video to Base64 before passing it to the model.

  For AWS Bedrock models with video support, you can pass `s3://` URIs through `Video.from_url`. BAML forwards the URI as an `s3Location` and includes the `media_type` you provide so Bedrock can fetch the object without uploading it through BAML first. BAML does **not** infer video MIME types for Bedrock requests, so always supply the correct `media_type` (for example, `video/mp4`).Direct video inputs are only supported by Google Gemini, Google Vertex AI, and AWS Bedrock models that advertise video support. Other providers (Anthropic Claude, OpenAI GPT-4o) will error or require you to extract frames as images or provide transcripts. See the model compatibility table below for details.## Usage Examples```python
  from baml_py import Video
  from baml_client import b

  async def test_video_input():
      # Create a Video object from a URL
      video = Video.from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
      res = await b.TestVideoInput(video=video)

      # Create a Video object from Base64 data
      video_b64 = "AAAAGGZ0eXBpc29t..."
      video = Video.from_base64("video/mp4", video_b64)
      res = await b.TestVideoInput(video=video)

      # Pass an S3 video reference directly to an AWS Bedrock model
      bedrock_video = Video.from_url(
          "s3://baml-test-bucket/example/path/video.mp4", media_type="video/mp4"
      )
      res = await b.TestAwsVideoDescribe(video_input=bedrock_video)
  ```

  ```typescript
  import { b } from '../baml_client'
  import { Video } from "@boundaryml/baml"

  // Create a Video object from a URL
  let res = await b.TestVideoInput(
      Video.fromUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  )

  // Create a Video object from Base64 data
  const video_b64 = "AAAAGGZ0eXBpc29t..."
  res = await b.TestVideoInput(
      Video.fromBase64('video/mp4', video_b64)
  )

  // Pass an S3 video reference directly to an AWS Bedrock model
  const bedrockVideo = Video.fromUrl(
    's3://baml-test-bucket/example/path/video.mp4',
    'video/mp4',
  )
  // Pass `bedrockVideo` to any function backed by a Bedrock model with video support

  // Browser-specific methods
  const fileVideo = await Video.fromFile(file)
  const blobVideo = await Video.fromBlob(blob, 'video/mp4')
  const fetchedVideo = await Video.fromUrlToBase64('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  ```

  ```tsx
  import { useTestVideoInput } from '../baml_client/react/hooks'
  import { Video } from "../baml_client/react/media"

  export function TestVideoInput() {
      const { mutate } = useTestVideoInput()

      const handleClick = async () => {
          const video = await Video.fromUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
          mutate(video)
      }

      return (Test Video Input)
  }
  ```

  ```rust Rust
  use myproject::baml_client::sync_client::B;
  use myproject::baml_client::new_video_from_url;

  fn test_video_input() {
      // Create a Video from a URL
      let video = new_video_from_url("https://example.com/sample.mp4", None);
      let res = B.TestVideoInput.call(&video).unwrap();
  }
  ```

  ```ruby
  # Ruby implementation is in development.
  ```## API Reference### Static MethodsCreates a Video object from a URL. Optionally specify the media type, otherwise it will be inferred from the URL. When targeting AWS Bedrock with an `s3://` URI, pass the media type explicitly so the request includes the expected `format`.Creates a Video object using Base64 encoded data along with the given MIME type.### Instance MethodsCheck if the video is stored as a URL.Get the URL of the video if it's stored as a URL. Raises an exception if the video is not stored as a URL.Get the base64 data and media type if the video is stored as base64. Returns `[base64_data, media_type]`. Raises an exception if the video is not stored as base64.Convert the video to a dictionary representation. Returns either `{"url": str}` or `{"base64": str, "media_type": str}`.### Static MethodsCreates a Video object from a URL. Optionally specify the media type, otherwise it will be inferred from the URL. When targeting AWS Bedrock with an `s3://` URI, pass the media type explicitly so the request includes the expected `format`.Creates a Video object using Base64 encoded data along with the given MIME type.Only available in browser environments. @boundaryml/baml/browserCreates a Video object from a File object. Available in browser environments only.Only available in browser environments. @boundaryml/baml/browserCreates a Video object from a Blob object. Available in browser environments only.Only available in browser environments.Creates a Video object by fetching from a URL. Available in browser environments only.### Instance MethodsCheck if the video is stored as a URL.Get the URL of the video if it's stored as a URL. Throws an Error if the video is not stored as a URL.Get the base64 data and media type if the video is stored as base64. Returns `[base64Data, mediaType]`. Throws an Error if the video is not stored as base64.Convert the video to a JSON representation. Returns either a URL object or a base64 object with media type.### Static MethodsCreates a Video object from a URL. Optionally specify the media type for better model compatibility.Creates a Video object using Base64 encoded data along with the given MIME type.### Instance MethodsCheck if the video is stored as a URL.Get the URL of the video if it's stored as a URL. Returns an error if the video is not stored as a URL.Get the base64 data and media type if the video is stored as base64. Returns `(base64Data, mediaType, error)`. Returns an error if the video is not stored as base64.Convert the video to a map representation. Returns either `{"url": string}` or `{"base64": string, "media_type": string}`.### Static MethodsCreates a Video from a URL. Optionally specify the media type for better model compatibility.Creates a Video from Base64 encoded data with an optional MIME type.Ruby implementation is in development.## URL Handling

Video URLs are typically passed directly to providers without conversion (default: `never` for all providers). This is because:

1. Video files are often too large for base64 encoding
2. Most providers that support video input can fetch URLs directly
3. Base64 encoding videos significantly increases payload size

Provider defaults:

* **[OpenAI](/ref/llm-client-providers/open-ai#media_url_handler)**: Keeps URLs as-is (`send_url`)
* **[Anthropic](/ref/llm-client-providers/anthropic#media_url_handler)**: Keeps URLs as-is (`send_url`)
* **[Google AI](/ref/llm-client-providers/google-ai-gemini#media_url_handler)**: Keeps URLs as-is (`send_url`)
* **[Vertex AI](/ref/llm-client-providers/google-vertex#media_url_handler)**: Keeps URLs as-is (`send_url`)
* **[AWS Bedrock](/ref/llm-client-providers/aws-bedrock#media_url_handler)**: Keeps URLs as-is (`send_url`)

For Bedrock, `s3://` URLs are passed through unchanged and encoded in the request body as an `s3Location`, allowing Bedrock to fetch the object directly from S3 without routing bytes through BAML.

You can override this behavior using `media_url_handler.video` in your client configuration, but be aware of size limitations when using `send_base64` mode.

## Model Compatibility

Different AI models have varying levels of support for video input methods **(As of July 2025)**:

| Provider / API       |   | Video Input Support                                                                                                                         |
| -------------------- | - | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Anthropic**        | ✗ | No native video support. Only accepts PDF, images, and common docs.                                                                         |
| **AWS Bedrock**      | ✓ | Fully multimodal. Accepts video as Base64 bytes in request or S3 URI. JSON must include format (e.g. mp4) and source.                       |
| **Google Gemini**    | ✓ | Three options: upload with `ai.files.upload` and use `file_uri`, inline Base64 (\<20MB), or YouTube URL (preview). Requires `mime_type`.    |
| **OpenAI**           | ✗ | Video input not yet in public API. Only text and images. Must extract frames and send as images for now.                                    |
| **Google Vertex AI** | ✓ | Accepts video via Cloud Storage `gs://` URI (up to 2GB), public HTTP/HTTPS URL (≤15MB), YouTube URL, or inline Base64. Requires `mimeType`. |For most models, direct video input is limited to Google Gemini, Google Vertex AI, and AWS Bedrock models with video support. For other providers, you must extract frames as images or use transcripts. Always specify the correct MIME type (e.g., video/mp4) when required.
