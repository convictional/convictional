import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"

import { useOptionalRouter } from "~/react/shared/hooks/useOptionalRouter"

// Pill-shaped badge linking to a goal. The hover-preview card is intentionally
// omitted — add it when a React caller needs it.
type GoalBadgeTheme = "highlight" | "beige" | "light"
type GoalBadgeSize = "medium" | "small"

export interface GoalBadgeGoal {
  id: string
  title?: string | null
  description?: string | null
  parent?: { description: string } | null
}

interface GoalBadgeProps {
  goal: GoalBadgeGoal
  theme?: GoalBadgeTheme
  size?: GoalBadgeSize
}

const THEME_CLASSES: Record<GoalBadgeTheme, { container: string; text: string }> = {
  highlight: { container: "bg-primary/10 hover:opacity-90", text: "font-medium text-primary" },
  beige: { container: "bg-base-200 border border-neutral hover:border-base-400", text: "" },
  light: { container: "bg-base-50 border border-base-300 hover:border-base-400 shadow-badge", text: "" },
}

const SIZE_CLASSES: Record<GoalBadgeSize, { container: string; text: string }> = {
  medium: { container: "gap-2 px-3.5 py-0.75", text: "text-sm" },
  small: { container: "gap-1.5 px-2.5 py-0.5", text: "text-xs" },
}

// The badge renders both inside the SPA shell (goal alignments) and in islands
// with no RouterProvider (the mailbox, ProfileCard), so it can't commit to one
// navigation mechanism. NavLink can't do this job: it decides by looking the
// pathname up in router.routesByPath, which is keyed by route *template*
// (/goals/$goalId), so a concrete /goals/abc never matches and always falls
// through to a full load. A parameterized target needs the typed <Link> form,
// hence the explicit branch on router context.
export function GoalBadge({ goal, theme = "highlight", size = "medium" }: GoalBadgeProps) {
  const router = useOptionalRouter()
  const themeClasses = THEME_CLASSES[theme]
  const sizeClasses = SIZE_CLASSES[size]
  const className = `inline-flex max-w-full min-w-0 items-center rounded-full transition-all duration-200 ${themeClasses.container}`

  const content: ReactNode = (
    <div className={`flex items-center flex-1 min-w-0 ${sizeClasses.container}`}>
      {goal.parent ? (
        <>
          <span className={`${sizeClasses.text} text-base-content/50 flex-1 shrink min-w-0 truncate`}>
            {goal.parent.description}
          </span>
          <span className={`text-base-400 ${sizeClasses.text} shrink`}>›</span>
          <span className={`${sizeClasses.text} ${themeClasses.text} flex-2 shrink min-w-0 max-w-fit truncate`}>
            {goal.description}
          </span>
        </>
      ) : (
        <span className={`min-w-0 truncate max-w-fit ${sizeClasses.text} ${themeClasses.text}`}>
          {goal.title || goal.description}
        </span>
      )}
    </div>
  )

  if (router) {
    return (
      <Link to="/goals/$goalId" params={{ goalId: goal.id }} className={className}>
        {content}
      </Link>
    )
  }

  // hx-boost="false" makes htmx.process() skip this anchor, so the click is a
  // native navigation that loads the SPA shell in one request rather than a
  // boosted fragment fetch the shell has to bounce with HX-Redirect. Matches what
  // NavLink emits for a clientRouted anchor in island mode.
  return (
    <a href={`/goals/${goal.id}`} className={className} {...{ "hx-boost": "false" }}>
      {content}
    </a>
  )
}
