---
url: https://docs.boundaryml.com/ref/baml_client/media.mdx
scraped_at: 2026-03-06T01:00:42.697688
filepath: docs-docs-boundaryml-com/ref/baml-client/mediamdx.md
---


***

title: Image / Audio / Pdf / Video
description: 'Learn how to handle image, audio, Pdf, and video inputs in BAML functions'
----------------------------------------------------------------------------------------

BAML functions can accept image, audio, Pdf, and video inputs for multimedia processing capabilities. Choose the appropriate type based on your needs:Create Image objects from URLs, base64 data, or browser-specific sources like File and Blob objects.Create Audio objects from URLs, base64 data, or browser-specific sources like File and Blob objects.Create Pdf objects from URLs, base64 data, or browser-specific sources like File and Blob objects.Create Video objects from URLs, base64 data, or browser-specific sources like File and Blob objects.## URL Resolution

BAML automatically handles URL-to-base64 conversion based on provider requirements. You can control this behavior using the `media_url_handler` configuration option in your client definition.

By default:

* URLs are converted to base64 for providers that don't support external URLs
* Google Cloud Storage URLs (gs\://) are preserved when using Google providers
* MIME types are added when required by the provider

See the client configuration documentation for provider-specific defaults and configuration options.
