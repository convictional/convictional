import { describe, expect, test } from "vitest"

import {
  describePropertyType,
  fieldsFromSchema,
} from "../../../../../app/javascript/react/features/backgroundJobs/argumentFields"

describe("fieldsFromSchema", () => {
  test("lists required fields first, drops the base fields, and carries type + description", () => {
    const fields = fieldsFromSchema({
      properties: {
        workspace_id: { type: "string", format: "uuid", description: "The workspace to reindex." },
        dry_run: { type: "boolean" },
        perform_at: { type: "string" },
        queue: { type: "string" },
        unique: { type: "boolean" },
      },
      required: ["workspace_id"],
    })

    expect(fields).toEqual([
      { name: "workspace_id", required: true, typeLabel: "uuid", description: "The workspace to reindex." },
      { name: "dry_run", required: false, typeLabel: "boolean", description: null },
    ])
  })

  test("resolves $ref enum fields to their options instead of 'any'", () => {
    const fields = fieldsFromSchema({
      properties: { mode: { $ref: "#/$defs/Mode" } },
      required: ["mode"],
      $defs: { Mode: { enum: ["fast", "slow"], type: "string" } },
    })

    expect(fields).toEqual([{ name: "mode", required: true, typeLabel: '"fast" | "slow"', description: null }])
  })
})

describe("describePropertyType", () => {
  test("prefers enum options, then format, then type, and unwraps optional unions", () => {
    expect(describePropertyType({ enum: ["a", "b"] })).toBe('"a" | "b"')
    expect(describePropertyType({ type: "string", format: "uuid" })).toBe("uuid")
    expect(describePropertyType({ type: "integer" })).toBe("integer")
    expect(describePropertyType({ anyOf: [{ type: "string" }, { type: "null" }] })).toBe("string")
    expect(describePropertyType({})).toBe("any")
  })

  test("resolves a $ref against $defs (enum and nested-model fields)", () => {
    const defs = { Mode: { enum: ["fast", "slow"], type: "string" } }
    expect(describePropertyType({ $ref: "#/$defs/Mode" }, defs)).toBe('"fast" | "slow"')
    // A $ref with no matching def degrades to "any" rather than throwing.
    expect(describePropertyType({ $ref: "#/$defs/Missing" }, defs)).toBe("any")
  })
})
