import { describe, expect, test } from "vitest"

import { templateFromSchema } from "../../../../../app/javascript/react/features/backgroundJobs/schemaTemplate"

describe("templateFromSchema", () => {
  test("emits typed defaults for required fields only", () => {
    const result = templateFromSchema({
      properties: {
        name: { type: "string" },
        count: { type: "number" },
        dry_run: { type: "boolean" },
        payload: { type: "object" },
        queue: { type: "string" },
      },
      required: ["name", "count", "dry_run", "payload"],
    })

    expect(JSON.parse(result)).toEqual({
      name: "",
      count: 0,
      dry_run: false,
      payload: null,
    })
  })

  test("returns an empty object when there are no required fields", () => {
    const result = templateFromSchema({
      properties: { perform_at: { type: "string" }, unique: { type: "boolean" } },
    })
    expect(JSON.parse(result)).toEqual({})
  })

  test("is pretty-printed with two-space indentation", () => {
    const result = templateFromSchema({ properties: { name: { type: "string" } }, required: ["name"] })
    expect(result).toBe('{\n  "name": ""\n}')
  })

  test("seeds 0 for integer fields (Pydantic emits 'integer', not 'number')", () => {
    const result = templateFromSchema({ properties: { count: { type: "integer" } }, required: ["count"] })
    expect(JSON.parse(result)).toEqual({ count: 0 })
  })

  test("resolves a $ref enum and seeds its first option so the template is valid as-is", () => {
    const result = templateFromSchema({
      properties: { mode: { $ref: "#/$defs/Mode" } },
      required: ["mode"],
      $defs: { Mode: { enum: ["fast", "slow"], type: "string" } },
    })
    expect(JSON.parse(result)).toEqual({ mode: "fast" })
  })
})
