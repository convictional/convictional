import type { JsonSchema, JsonSchemaProperty } from "./types"

// Present on every JobDefinition (the base class), so they're noise in a
// per-job reference — every job would list the same three. The old page never
// surfaced them either.
const BASE_FIELDS = new Set(["perform_at", "queue", "unique"])

export interface SchemaField {
  name: string
  required: boolean
  typeLabel: string
  description: string | null
}

// Flatten a job's schema into a displayable field reference: required fields
// first, then optional, each with a best-effort type label. Defensive — jobs
// have arbitrary schemas, so anything we can't read degrades to "any".
export function fieldsFromSchema(schema: JsonSchema): SchemaField[] {
  const required = new Set(schema.required ?? [])
  const defs = schema.$defs ?? {}
  const entries = Object.entries(schema.properties ?? {}).filter(([name]) => !BASE_FIELDS.has(name))

  return entries
    .map(([name, prop]) => ({
      name,
      required: required.has(name),
      typeLabel: describePropertyType(prop, defs),
      description: prop.description ?? null,
    }))
    .sort((a, b) => Number(b.required) - Number(a.required))
}

// Resolve a one-hop $ref ("#/$defs/Name") against the root $defs so callers see
// the concrete schema (enum options, type) instead of a bare reference. Returns
// the property unchanged when there's no $ref or the target is missing.
export function resolveRef(prop: JsonSchemaProperty, defs: Record<string, JsonSchemaProperty>): JsonSchemaProperty {
  if (!prop.$ref) return prop
  const name = prop.$ref.split("/").pop()
  return (name && defs[name]) || prop
}

// A short human label for a property's type. Resolves $ref first, then prefers
// an enum's options, a semantic format (uuid, date-time), the raw JSON type, and
// finally unwraps the `str | None` style `anyOf` unions Pydantic emits for
// optional fields.
export function describePropertyType(prop: JsonSchemaProperty, defs: Record<string, JsonSchemaProperty> = {}): string {
  const resolved = resolveRef(prop, defs)
  if (resolved.enum && resolved.enum.length > 0) {
    return resolved.enum.map(value => JSON.stringify(value)).join(" | ")
  }
  if (resolved.format) return resolved.format
  if (resolved.type) return resolved.type
  if (resolved.anyOf && resolved.anyOf.length > 0) {
    const labels = resolved.anyOf.map(p => describePropertyType(p, defs)).filter(label => label !== "null")
    if (labels.length > 0) return labels.join(" | ")
  }
  return "any"
}
