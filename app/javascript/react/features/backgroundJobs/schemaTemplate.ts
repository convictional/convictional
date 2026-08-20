import { resolveRef } from "./argumentFields"
import type { JsonSchemaProperty, JsonSchema } from "./types"

// Build a JSON skeleton holding only the job's required fields, each defaulted
// by type. The schema is the full Pydantic model_json_schema(); inherited base
// fields (perform_at, queue, unique) aren't required, so they're omitted.
export function templateFromSchema(schema: JsonSchema): string {
  const template: Record<string, unknown> = {}
  const defs = schema.$defs ?? {}

  if (schema.properties) {
    for (const [name, prop] of Object.entries(schema.properties)) {
      if (!schema.required?.includes(name)) continue
      template[name] = defaultForProperty(resolveRef(prop, defs))
    }
  }

  return JSON.stringify(template, null, 2)
}

function defaultForProperty(prop: JsonSchemaProperty): unknown {
  // Seed an enum with its first valid option so the template is submittable
  // as-is rather than seeding an invalid placeholder.
  if (prop.enum && prop.enum.length > 0) return prop.enum[0]
  switch (prop.type) {
    case "string":
      return ""
    case "number":
    case "integer":
      return 0
    case "boolean":
      return false
    default:
      return null
  }
}
