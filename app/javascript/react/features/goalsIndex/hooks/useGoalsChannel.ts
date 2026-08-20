import { useState } from "react"

import type { GoalsView } from "~/react/features/goalsIndex/types"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import type { User } from "~/react/shared/types"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

export function useGoalsChannel(view: GoalsView) {
  const { user } = useCurrentUser()
  const organizationId = user?.organization_id
  const [presentUsers, setPresentUsers] = useState<User[]>([])

  useChannel(
    organizationId
      ? { stream: ChannelStream.GOALS_PRESENCE, params: { organization_id: organizationId, view } }
      : null,
    ChannelEventResource.GOALS_PRESENCE,
    (_action, data) => {
      const users = data.users as User[] | undefined
      if (users) {
        setPresentUsers(users)
      }
    }
  )

  return { presentUsers }
}
