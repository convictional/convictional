import { useMemo } from "react"

import { fieldsFromSchema } from "./argumentFields"
import type { JsonSchema } from "./types"

// Read-only reference for the selected job's arguments, so editing the JSON is
// guided rather than guesswork. The schema is the full Pydantic
// model_json_schema(); we surface each field's name, whether it's required, its
// type, and any Field(description=...).
export function SchemaFields({ schema }: { schema: JsonSchema }) {
  // Re-derive only when the schema changes, not on every parent re-render
  // (the arguments textarea re-renders BackgroundJobs on each keystroke).
  const fields = useMemo(() => fieldsFromSchema(schema), [schema])

  return (
    <div className="rounded-md border border-base-300 bg-base-100 p-3">
      {fields.length === 0 ? (
        <p className="text-xs opacity-50">This job takes no arguments.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {fields.map(field => (
            <li key={field.name} className="text-xs">
              <div className="flex items-baseline gap-2">
                <code className="font-mono font-semibold">{field.name}</code>
                {field.required ? (
                  <span className="badge badge-xs badge-error">required</span>
                ) : (
                  <span className="opacity-50">optional</span>
                )}
              </div>
              <p className="font-mono opacity-50">{field.typeLabel}</p>
              {field.description && <p className="opacity-60 text-pretty">{field.description}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
