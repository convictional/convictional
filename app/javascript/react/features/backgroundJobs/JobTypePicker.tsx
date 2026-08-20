import { useMemo, useState } from "react"

import { Dropdown } from "~/react/ui/Dropdown"
import type { JobType } from "./types"

interface JobTypePickerProps {
  jobTypes: JobType[]
  selected: JobType | null
  onSelect: (jobType: JobType) => void
}

// Searchable picker for the ~105 registered jobs. A native <select> of that
// many options is a scroll-and-squint; this mirrors the app's typeahead pickers
// (GroupPicker, OwnerPicker) using the shared Dropdown primitive.
export function JobTypePicker({ jobTypes, selected, onSelect }: JobTypePickerProps) {
  const [query, setQuery] = useState("")

  const filtered = useMemo(() => {
    if (!query) return jobTypes
    const q = query.toLowerCase()
    return jobTypes.filter(job => job.name.toLowerCase().includes(q) || job.job_type.toLowerCase().includes(q))
  }, [jobTypes, query])

  return (
    <Dropdown
      placement="bottom-start"
      onOpenChange={open => !open && setQuery("")}
      className="dropdown-card w-80 z-50"
      trigger={
        <button
          type="button"
          aria-label={selected ? `Job type: ${selected.name}` : "Select a job type"}
          className="select bg-base-200 cursor-pointer w-full flex items-center justify-between text-left"
        >
          <span className={selected ? "" : "opacity-50"}>{selected ? selected.name : "Select a job type"}</span>
        </button>
      }
    >
      {({ close }) => (
        <>
          <div className="p-2 pb-0">
            <input
              type="text"
              placeholder="Search jobs..."
              autoComplete="off"
              className="input input-sm input-bordered !outline-none bg-base-50 w-full"
              value={query}
              onChange={e => setQuery(e.target.value)}
              autoFocus
            />
          </div>
          <div className="p-2">
            <ul className="max-h-72 overflow-y-auto grid gap-1">
              {filtered.length === 0 && (
                <li className="text-center py-2 text-sm text-base-500">No jobs match your search</li>
              )}
              {filtered.map(job => (
                <li key={job.job_type}>
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(job)
                      close()
                    }}
                    className="dropdown-item w-full text-left flex flex-col gap-0.5 p-1"
                  >
                    <span className="text-sm font-semibold truncate">{job.name}</span>
                    <span className="font-mono text-xs opacity-50 truncate">{job.job_type}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </Dropdown>
  )
}
