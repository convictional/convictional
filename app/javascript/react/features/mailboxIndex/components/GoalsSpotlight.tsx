import { useEffect, useState } from "react"

import { GoalBadge } from "~/react/composites/goals/GoalBadge"
import { apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { NavLink } from "~/react/shared/NavLink"

import type { TopGoalForUserResponse } from "../types"

// Inbox-zero empty state. Mirrors templates/goals/spotlight.html.jinja:
// intro text, a highlight-themed goal badge pill, and an "All goals" link.
export function GoalsSpotlight() {
  const { user } = useCurrentUser()
  const [state, setState] = useState<TopGoalForUserResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!user) return
    let cancelled = false
    apiFetch<TopGoalForUserResponse>(`/api/users/${user.id}/top_goal?expand=parent`)
      .then(data => {
        if (!cancelled) setState(data)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [user])

  if (loading || error) return null
  const goal = state?.top_goal
  if (!goal) return null

  return (
    <div className="max-w-4xl min-w-0 space-y-4 px-4 py-6 text-sm opacity-50 text-pretty">
      <p>Here's a goal that needs your attention.</p>
      <div className="flex justify-center">
        <GoalBadge goal={goal} />
      </div>
      <NavLink href="/goals" clientRouted className="link no-underline hover:underline">
        All goals
      </NavLink>
    </div>
  )
}
