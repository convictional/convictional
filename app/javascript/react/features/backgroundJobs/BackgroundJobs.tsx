import { useEffect, useRef, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { toastStore } from "~/react/shared/stores/toast"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { SubmitButton } from "~/react/ui/SubmitButton"
import { JobTypePicker } from "./JobTypePicker"
import { SchemaFields } from "./SchemaFields"
import { templateFromSchema } from "./schemaTemplate"
import type { EnqueueJobResponse, JobType, JobTypesListResponse } from "./types"

export interface BackgroundJobsProps {
  userId: string
  organizationId: string
}

// FastAPI's native validation-error entry shape. Every 422 from the background
// jobs API (unknown job type, invalid arguments) comes back as a list of these.
interface ValidationErrorDetail {
  loc: (string | number)[]
  msg: string
}

const INVALID_JSON_ERROR = "Your job arguments were invalid JSON."
const NOT_OBJECT_ERROR = "Your job arguments must be a JSON object."
const GENERIC_ERROR = "Something went wrong enqueueing the job. Please try again."

export function BackgroundJobs({ userId, organizationId }: BackgroundJobsProps) {
  const [jobTypes, setJobTypes] = useState<JobType[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [selectedJobType, setSelectedJobType] = useState("")
  const [argsJson, setArgsJson] = useState("")
  const [errors, setErrors] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  // Synchronous re-entry guard: the `submitting` state stays false across the
  // `await confirm(...)` window and reads stale in a synchronous click burst, so
  // a ref (which mutates immediately) is what actually prevents a double enqueue
  // of an irreversible job. Mirrors FeedbackDialog.
  const isSubmittingRef = useRef(false)

  const selectedJob = jobTypes.find(job => job.job_type === selectedJobType) ?? null

  useEffect(() => {
    let cancelled = false
    apiFetch<JobTypesListResponse>("/api/background_job_types")
      .then(response => {
        if (cancelled) return
        setJobTypes(response.job_types)
      })
      .catch(() => {
        if (cancelled) return
        setLoadError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function handleSelect(job: JobType) {
    setSelectedJobType(job.job_type)
    setArgsJson(templateFromSchema(job.args_schema))
    setErrors([])
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (isSubmittingRef.current || !selectedJob) return

    let parsed: unknown
    try {
      parsed = JSON.parse(argsJson)
    } catch {
      setErrors([INVALID_JSON_ERROR])
      return
    }
    // The arguments are spread into the job model (job_class(**arguments)), so
    // they must be a JSON object — reject scalars/arrays/null before confirming.
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setErrors([NOT_OBJECT_ERROR])
      return
    }
    const parsedArguments = parsed as Record<string, unknown>

    // Claim the guard before awaiting the confirm dialog so a second click in
    // the meantime can't open a second dialog / fire a second enqueue.
    isSubmittingRef.current = true
    const confirmed = await confirm({
      title: `Enqueue ${selectedJob.name}?`,
      message: "Review the arguments below — many jobs are irreversible and can break production.",
      confirmLabel: "Enqueue job",
    })
    if (!confirmed) {
      isSubmittingRef.current = false
      return
    }

    setErrors([])
    setSubmitting(true)
    try {
      await apiFetch<EnqueueJobResponse>(
        "/api/background_jobs",
        {
          method: "POST",
          body: JSON.stringify({ job_type: selectedJob.job_type, arguments: parsedArguments }),
        },
        { expectedStatuses: [422] }
      )
      toastStore.getState().show({ message: "Job enqueued successfully", level: "success", persistent: false })
      // Reset the arguments to the job's pristine template so a second enqueue
      // is a deliberate act, not a stale resubmit of an irreversible job.
      setArgsJson(templateFromSchema(selectedJob.args_schema))
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && Array.isArray(err.body?.detail)) {
        const detail = err.body.detail as ValidationErrorDetail[]
        setErrors(detail.map(formatValidationError))
      } else {
        setErrors([GENERIC_ERROR])
      }
    } finally {
      setSubmitting(false)
      isSubmittingRef.current = false
    }
  }

  return (
    <>
      <div role="alert" className="alert alert-error mb-6 text-sm">
        <span className="material-symbols-outlined">warning</span>
        <p>
          These jobs are <strong>not documented</strong>. The code is the documentation. If you don&apos;t know exactly
          what a job does and how to run it, <strong>don&apos;t</strong>. You can break production. Many of these jobs
          are irreversible.
        </p>
      </div>

      {loading ? (
        <LoadingState />
      ) : loadError ? (
        <ErrorState message="We couldn't load the job types. Please try refreshing the page." />
      ) : (
        <>
          {errors.length > 0 && (
            <div role="alert" className="alert alert-error text-sm mb-8 flex-col items-start gap-1">
              {errors.map((message, index) => (
                <p key={index} className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-lg">error</span>
                  {message}
                </p>
              ))}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <label className="fieldset">
              <div className="label">
                <span className="label-text">Job type</span>
              </div>
              <JobTypePicker jobTypes={jobTypes} selected={selectedJob} onSelect={handleSelect} />
            </label>

            {selectedJob && (
              <p className="text-xs text-base-content/60 mt-2 flex items-center gap-1.5">
                Runs on the
                <span className="badge badge-sm badge-neutral font-mono">{selectedJob.queue}</span>
                queue
              </p>
            )}

            <div className="flex flex-col lg:flex-row gap-4 mt-2">
              <label className="fieldset flex-1">
                <div className="label">
                  <span className="label-text">Arguments JSON</span>
                </div>
                {/* Not `required`: the value is filled programmatically when a
                    job is selected, which fires no native input event for
                    SubmitButton's validity check. Submission is gated on a
                    selected job, and the JSON is validated in handleSubmit. */}
                <textarea
                  className="textarea font-mono h-64 w-full bg-base-200"
                  value={argsJson}
                  onChange={event => setArgsJson(event.target.value)}
                />
              </label>
              {selectedJob && (
                <div className="fieldset lg:w-72 shrink-0">
                  <div className="label">
                    <span className="label-text">Fields</span>
                  </div>
                  <SchemaFields schema={selectedJob.args_schema} />
                </div>
              )}
            </div>

            <div className="mt-4">
              <SubmitButton submitting={submitting} disabled={!selectedJob}>
                Enqueue job
              </SubmitButton>
            </div>
          </form>
        </>
      )}

      {/* Context for the superuser running the job (which user / org it
          enqueues as) — secondary reference, so a muted footer. */}
      <div className="mt-10 pt-4 border-t border-base-300 flex flex-col gap-1 text-xs text-base-content/50">
        <p>
          User ID <code className="font-mono text-base-content/70">{userId}</code>
        </p>
        <p>
          Organization ID <code className="font-mono text-base-content/70">{organizationId}</code>
        </p>
      </div>
    </>
  )
}

// Strip FastAPI's request-path prefix ("body", "arguments") so the user sees
// "goal_id: Field required" instead of "body.arguments.goal_id: Field required".
function formatValidationError(detail: ValidationErrorDetail): string {
  const path = [...detail.loc]
  if (path[0] === "body") path.shift()
  if (path[0] === "arguments") path.shift()
  const field = path.join(".") || "request"
  return `${field}: ${detail.msg}`
}
