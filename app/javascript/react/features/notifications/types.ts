import type { SubscriptionLevel } from "~/react/shared/types"
import type { PushSubscriptionDevice } from "./pushSubscription"

export type NotificationLevel = SubscriptionLevel

export interface NotificationPreference {
  resource_type: string
  default_level: NotificationLevel
}

export interface PostGroupMute {
  group_id: string
  group_name: string
  muted: boolean
}

export interface PushWorkingHours {
  start: string
  end: string
}

export interface PushSettings {
  devices: PushSubscriptionDevice[]
  vapid_public_key: string
  working_hours: PushWorkingHours | null
}

export interface NotificationsResponse {
  preferences: NotificationPreference[]
  post_group_mutes: PostGroupMute[]
  push: PushSettings
}
