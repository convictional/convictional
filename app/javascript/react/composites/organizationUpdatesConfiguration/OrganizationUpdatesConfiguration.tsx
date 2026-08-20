import { useQuery, useQueryClient } from "@tanstack/react-query"
import { type FormEvent, useEffect, useState } from "react"
import { SettingsSection } from "~/react/composites/settings/SettingsSection"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { SubmitButton } from "~/react/ui/SubmitButton"
import { showFlash } from "~/shared/flash"
import { updatesConfigurationQueryOptions } from "./queries"
import type { UpdateFrequency, UpdatesConfiguration } from "./types"

const ENDPOINT = "/api/organization/updates_configuration"
const PROFILE_SETTINGS_PATH = "/profile/edit"

const FREQUENCY_OPTIONS: { value: UpdateFrequency; label: string }[] = [
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
]

// Cron day-of-week values sent to the schedule endpoint (0 = Sunday).
const DAY_OPTIONS: { value: string; label: string }[] = [
  { value: "0", label: "Sunday" },
  { value: "1", label: "Monday" },
  { value: "2", label: "Tuesday" },
  { value: "3", label: "Wednesday" },
  { value: "4", label: "Thursday" },
  { value: "5", label: "Friday" },
  { value: "6", label: "Saturday" },
]

// Cron hour values 0-23 sent to the schedule endpoint, shown as 12-hour labels.
const HOUR_OPTIONS: { value: string; label: string }[] = Array.from({ length: 24 }, (_, h) => ({
  value: String(h),
  label: `${h % 12 || 12}:00 ${h < 12 ? "AM" : "PM"}`,
}))

// The schedule endpoint returns the validator message (e.g. weekly without a day)
// as a 422 with a string `detail`; surface that, otherwise a generic fallback.
function scheduleErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 422 && typeof error.body?.detail === "string") {
    return error.body.detail
  }
  return "Could not save the schedule. Please try again."
}

export function OrganizationUpdatesConfiguration() {
  const { user } = useCurrentUser()
  const timezone = user?.time_zone ?? null
  const queryClient = useQueryClient()
  const { data: config, isPending, isError } = useQuery(updatesConfigurationQueryOptions)

  // Form fields, seeded from the server state but edited independently.
  const [frequency, setFrequency] = useState<UpdateFrequency | "">("")
  const [hour, setHour] = useState("")
  const [dayOfWeek, setDayOfWeek] = useState("")
  const [goalQuestion, setGoalQuestion] = useState("")
  const [seeded, setSeeded] = useState(false)

  const [savingSchedule, setSavingSchedule] = useState(false)
  const [scheduleError, setScheduleError] = useState<string | null>(null)
  const [savingQuestion, setSavingQuestion] = useState(false)
  const [questionError, setQuestionError] = useState<string | null>(null)

  // Seed the form once when the query first resolves. Guarding on `seeded` keeps a
  // later cache update (a save's setQueryData, or a background refetch) from
  // stomping unsaved edits — each save re-seeds only the fields it owns below.
  useEffect(() => {
    if (!config || seeded) return
    setFrequency(config.frequency ?? "")
    setHour(config.hour === null ? "" : String(config.hour))
    setDayOfWeek(config.day_of_week ?? "")
    setGoalQuestion(config.goal_update_question)
    setSeeded(true)
  }, [config, seeded])

  // Both save buttons PATCH the same endpoint and apply the returned state to the
  // badge (via the query cache); they differ only in the body they send, which
  // saving/error state they drive, and how they translate a failure into a message.
  // On success the updated config is returned so each caller can re-seed only the
  // fields it owns — the schedule and question forms are independent, so one save
  // must not stomp the other's unsaved edits.
  async function patchConfig(
    body: object,
    setSaving: (saving: boolean) => void,
    setError: (message: string | null) => void,
    errorFor: (error: unknown) => string
  ): Promise<UpdatesConfiguration | null> {
    setError(null)
    setSaving(true)
    try {
      const updated = await apiFetch<UpdatesConfiguration>(ENDPOINT, { method: "PATCH", body: JSON.stringify(body) })
      queryClient.setQueryData(updatesConfigurationQueryOptions.queryKey, updated)
      return updated
    } catch (error) {
      setError(errorFor(error))
      return null
    } finally {
      setSaving(false)
    }
  }

  async function saveSchedule(event: FormEvent) {
    event.preventDefault()
    // frequency + hour move together (the cron is rebuilt from both); day_of_week
    // only applies to weekly. Sent as one unit per the API contract.
    const body = {
      frequency,
      hour: hour === "" ? null : Number(hour),
      // `canSaveSchedule` already guarantees a non-empty day for weekly, so `|| null` is a
      // defensive guard, not a live branch: it keeps the body correct (null, never "") if that
      // gating ever weakens, rather than coupling this handler to the button's disabled state.
      day_of_week: frequency === "weekly" ? dayOfWeek || null : null,
    }
    const updated = await patchConfig(body, setSavingSchedule, setScheduleError, scheduleErrorMessage)
    if (updated) {
      setFrequency(updated.frequency ?? "")
      setHour(updated.hour === null ? "" : String(updated.hour))
      setDayOfWeek(updated.day_of_week ?? "")
      showFlash("Schedule saved.", "success")
    }
  }

  async function saveQuestion(event: FormEvent) {
    event.preventDefault()
    const updated = await patchConfig(
      { goal_update_question: goalQuestion },
      setSavingQuestion,
      setQuestionError,
      () => "Could not save the question. Please try again."
    )
    if (updated) {
      setGoalQuestion(updated.goal_update_question)
      showFlash("Goal update question saved.", "success")
    }
  }

  if (isPending) return <LoadingState />
  if (isError || !config) return <ErrorState message="Could not load updates configuration." />

  const isWeekly = frequency === "weekly"
  const isMonthly = frequency === "monthly"
  // Disable until the fields the cron needs are chosen; the server still validates.
  const canSaveSchedule = frequency !== "" && hour !== "" && (!isWeekly || dayOfWeek !== "")

  return (
    <SettingsSection
      title={
        <>
          <span>Updates Configuration</span>
          {config.enabled ? (
            <span className="badge badge-success badge-xs">Enabled</span>
          ) : (
            <span className="badge badge-warning badge-xs">Disabled</span>
          )}
        </>
      }
      description="Configure how updates are requested from your team."
    >
      <div className="flex flex-col gap-6">
        <form onSubmit={saveSchedule} className="flex flex-col gap-4">
          <div className="grid gap-2">
            <h3 className="text-sm text-base-500 flex items-center gap-2">
              Schedule{" "}
              <span className="text-xs">
                (
                <a href={PROFILE_SETTINGS_PATH} className="link">
                  {timezone || "UTC"}
                </a>
                )
              </span>
            </h3>
            <div className="flex flex-wrap gap-2 items-end">
              <select
                aria-label="Frequency"
                className="select select-sm bg-base-200 min-w-32"
                value={frequency}
                onChange={e => setFrequency(e.target.value as UpdateFrequency | "")}
              >
                <option value="" disabled>
                  Select frequency
                </option>
                {FREQUENCY_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {isWeekly && (
                <select
                  aria-label="Day of week"
                  className="select select-sm bg-base-200 min-w-36"
                  value={dayOfWeek}
                  onChange={e => setDayOfWeek(e.target.value)}
                >
                  <option value="" disabled>
                    Select a day
                  </option>
                  {DAY_OPTIONS.map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              )}
              <select
                aria-label="Time"
                className="select select-sm bg-base-200 min-w-40"
                value={hour}
                onChange={e => setHour(e.target.value)}
              >
                <option value="" disabled>
                  Select a time
                </option>
                {HOUR_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <div className="flex-1 flex justify-end">
                <SubmitButton
                  submitting={savingSchedule}
                  disabled={!canSaveSchedule}
                  className="btn bg-base-200 border border-neutral"
                >
                  Save Schedule
                </SubmitButton>
              </div>
            </div>
            {isMonthly && (
              <div className="text-xs text-base-500">Updates will be sent on the last day of each month</div>
            )}
            {scheduleError && (
              <div role="alert" className="text-xs text-error">
                {scheduleError}
              </div>
            )}
          </div>
        </form>
      </div>
      {config.has_goals && (
        <>
          <h3 className="text-lg font-semibold mt-8">Goal update question</h3>
          <p className="text-sm text-base-content/60 mb-4">
            Goal owners will be asked this question on the schedule you configured above. To disable goal updates,
            simply remove the question and save.
          </p>
          <form onSubmit={saveQuestion}>
            <div className="flex gap-2 items-end">
              <div className="flex-1 fieldset p-0">
                <label className="label" htmlFor="goal_update_question">
                  <span className="label-text">Question</span>
                </label>
                <input
                  className="input input-sm w-full bg-base-200 placeholder-base-500"
                  id="goal_update_question"
                  name="goal_update_question"
                  type="text"
                  value={goalQuestion}
                  onChange={e => setGoalQuestion(e.target.value)}
                />
              </div>
              <SubmitButton submitting={savingQuestion} className="btn bg-base-200 border border-neutral">
                Save
              </SubmitButton>
            </div>
            {questionError && (
              <div role="alert" className="text-xs text-error mt-2">
                {questionError}
              </div>
            )}
          </form>
        </>
      )}
    </SettingsSection>
  )
}
