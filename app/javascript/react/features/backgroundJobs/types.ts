import type { PaginatedResponse } from "~/react/shared/types"

// A single property of a Pydantic JSON Schema. Defensive/partial: the API sends
// the full model_json_schema(), but jobs vary, so every field is optional and
// consumers fall back gracefully. `anyOf` appears for unions like `str | None`.
export interface JsonSchemaProperty {
  type?: string
  format?: string
  title?: string
  description?: string
  enum?: unknown[]
  anyOf?: JsonSchemaProperty[]
  // Pydantic emits nested models and enums as a reference into the root $defs
  // (e.g. "#/$defs/SomeEnum") rather than inlining them.
  $ref?: string
}

// Minimal view of a Pydantic JSON Schema — only the parts we read.
export interface JsonSchema {
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
  // Definitions referenced by $ref (enums, nested models).
  $defs?: Record<string, JsonSchemaProperty>
}

// Mirrors `app.routers.api.background_jobs.JobTypeResponse`.
export interface JobType {
  job_type: string
  name: string
  // The queue the job runs on by default (e.g. "maintenance", "indexing").
  queue: string
  args_schema: JsonSchema
}

// Mirrors `app.routers.api.background_jobs.JobTypesListResponse`.
export interface JobTypesListResponse extends PaginatedResponse {
  job_types: JobType[]
}

// Mirrors `app.routers.api.background_jobs.EnqueueJobResponse`.
export interface EnqueueJobResponse {
  job_id: string
  job_type: string
}
