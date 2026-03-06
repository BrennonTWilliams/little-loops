---
url: https://docs.boundaryml.com/ref/attributes/skip.mdx
scraped_at: 2026-03-06T01:00:35.557907
filepath: docs-docs-boundaryml-com/ref/attributes/skipmdx.md
---


The `@skip` attribute in BAML is used to exclude certain fields or values from being included in prompts or parsed responses. This can be useful when certain data is not relevant for the LLM's processing.In the case of class fields, the field type must be nullable if `@skip` is used
  in order to allow parsing LLM responses that will not include the field.

  This is valid:

  ```baml {3} OK
  class MyClass {
    field1 string
    field2 string? @skip // OK because field2 is nullable
  }
  ```

  This is not:

  ```baml {3} NOT OK
  class MyClass {
    field1 string
    field2 string @skip // Error: Field with @skip attribute must be optional.
  }
  ```## Prompt Impact

### Without `@skip`

```baml BAML
enum MyEnum {
  Value1
  Value2
}

class MyClass {
  field1 string
  field2 string?
}
```

**ctx.output\_format:**

* `MyEnum`

```
MyEnum
---
Value1
Value2
```

* `MyClass`

```
{
  field1: string,
  field2: string or null,
}
```

### With `@skip`

```baml BAML
enum MyEnum {
  Value1
  Value2 @skip
}

class MyClass {
  field1 string
  field2 string? @skip
}
```

**ctx.output\_format:**

* `MyEnum`

```
MyEnum
---
Value1
```

* `MyClass`

```
{
  field1: string,
}
```
