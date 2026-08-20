import {
  FloatingPortal,
  autoUpdate,
  flip,
  offset,
  shift,
  useDismiss,
  useFloating,
  useHover,
  useInteractions,
} from "@floating-ui/react"
import { useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { peekCurrentUser } from "~/react/shared/stores/currentUser"
import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"
import {
  ProfileCard,
  ProfileCardSkeleton,
  type ProfileCardData,
  type ProfileCardGoal,
  type ProfileCardUser,
} from "./ProfileCard"

const OPEN_DELAY_MS = 200
const CLOSE_DELAY_MS = 100

interface PeopleResponse {
  user: ProfileCardUser
  groups: { id: string; name: string }[]
}

interface TopGoalForUserResponse {
  top_goal: ProfileCardGoal | null
}

export function UserHoverCard({ userId, children }: { userId: string; children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const [data, setData] = useState<ProfileCardData | null>(null)
  const hasFetchedRef = useRef(false)

  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: next => {
      setIsOpen(next)
      if (next && !hasFetchedRef.current) {
        hasFetchedRef.current = true
        Promise.all([
          apiFetch<PeopleResponse>(`/api/people/${userId}`),
          apiFetch<TopGoalForUserResponse>(`/api/users/${userId}/top_goal?expand=parent`),
        ])
          .then(([people, topGoal]) => {
            const goal = topGoal.top_goal
            setData({
              user: people.user,
              groups: people.groups,
              goal,
              isCurrentUser: people.user.id === peekCurrentUser()?.id,
            })
          })
          .catch(() => {
            hasFetchedRef.current = false
          })
      }
    },
    placement: "bottom-start",
    middleware: [offset(4), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })
  const { setReference, setFloating } = refs

  const hover = useHover(context, { move: false, delay: { open: OPEN_DELAY_MS, close: CLOSE_DELAY_MS } })
  const dismiss = useDismiss(context)

  const { getReferenceProps, getFloatingProps } = useInteractions([hover, dismiss])

  return (
    <>
      <span ref={setReference} {...getReferenceProps()}>
        {children}
      </span>
      <FloatingPortal id={FLOATING_PORTAL_ROOT_ID}>
        {isOpen && (
          <div ref={setFloating} style={floatingStyles} {...getFloatingProps()} className="z-50 w-72">
            {data ? <ProfileCard data={data} /> : <ProfileCardSkeleton />}
          </div>
        )}
      </FloatingPortal>
    </>
  )
}
