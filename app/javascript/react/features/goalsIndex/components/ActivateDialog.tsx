import { useEffect, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { Dialog } from "~/react/ui/Dialog"
import { showFlash } from "~/shared/flash"
import { pluralize } from "~/shared/strings"

interface ActivateSummary {
  planning_goals_count: number
  completed_count: number
  incomplete_count: number
  open_threads_count: number
}

interface ActivateDialogProps {
  planningListName: string
  onActivated: () => void
  onClose: () => void
}

export function ActivateDialog({ planningListName, onActivated, onClose }: ActivateDialogProps) {
  const [summary, setSummary] = useState<ActivateSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [activating, setActivating] = useState(false)

  useEffect(() => {
    async function fetchSummary() {
      try {
        const data = await apiFetch<ActivateSummary>(
          `/api/goals/planning_lists/${encodeURIComponent(planningListName)}`
        )
        setSummary(data)
      } catch {
        showFlash("Failed to load activation summary.", "error")
        onClose()
      } finally {
        setLoading(false)
      }
    }
    fetchSummary()
  }, [planningListName]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleActivate() {
    setActivating(true)
    try {
      await apiFetch(`/api/goals/planning_lists/${encodeURIComponent(planningListName)}/activate`, {
        method: "POST",
      })
      showFlash(`'${planningListName}' goals have been activated.`)
      onActivated()
    } catch {
      showFlash("Failed to activate planning list. Please try again.", "error")
    } finally {
      setActivating(false)
    }
  }

  return (
    <Dialog isOpen={true} onClose={onClose} className="floating-card w-11/12 max-w-md">
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <span className="loading loading-spinner" />
        </div>
      ) : summary ? (
        <>
          <h3 className="text-base font-medium text-base-content mb-1">Activate {planningListName}</h3>
          <p className="text-sm text-base-content/60 mb-4">This will replace your current active goals.</p>
          <div className="space-y-2 mb-6">
            <div className="bg-base-100 rounded-lg px-3 py-2.5">
              <div className="text-xs font-medium text-base-content/50 uppercase tracking-wide mb-0.5">Activating</div>
              <div className="text-sm text-base-content">
                <span className="font-semibold">{summary.planning_goals_count}</span>{" "}
                {pluralize(summary.planning_goals_count, "goal", "goals")} from {planningListName}
              </div>
            </div>
            {(summary.completed_count > 0 || summary.incomplete_count > 0) && (
              <div className="bg-base-100 rounded-lg px-3 py-2.5">
                <div className="text-xs font-medium text-base-content/50 uppercase tracking-wide mb-0.5">
                  Closing active goals
                </div>
                <div className="text-sm text-base-content">
                  {summary.completed_count > 0 && summary.incomplete_count > 0 ? (
                    <>
                      <span className="font-semibold">{summary.completed_count}</span> as complete &middot;{" "}
                      <span className="font-semibold">{summary.incomplete_count}</span> as incomplete
                    </>
                  ) : summary.completed_count > 0 ? (
                    <>
                      <span className="font-semibold">{summary.completed_count}</span> as complete
                    </>
                  ) : (
                    <>
                      <span className="font-semibold">{summary.incomplete_count}</span> as incomplete
                    </>
                  )}
                </div>
              </div>
            )}
            {summary.open_threads_count > 0 && (
              <div className="bg-base-100 rounded-lg px-3 py-2.5">
                <div className="text-xs font-medium text-base-content/50 uppercase tracking-wide mb-0.5">
                  Conversations
                </div>
                <div className="text-sm text-base-content">
                  <span className="font-semibold">{summary.open_threads_count}</span>{" "}
                  {pluralize(summary.open_threads_count, "thread", "threads")} will be closed
                </div>
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <button type="button" className="btn btn-ghost flex-1" onClick={onClose}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary flex-1" disabled={activating} onClick={handleActivate}>
              {activating ? <span className="loading loading-spinner loading-sm" /> : "Activate"}
            </button>
          </div>
        </>
      ) : null}
    </Dialog>
  )
}
