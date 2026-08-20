import { useEffect, useState } from "react"
import { apiFetch } from "~/react/shared/apiFetch"
import { sourceMetaFor } from "~/react/shared/notificationSources"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { PostGroupMutes } from "./components/PostGroupMutes"
import { PushNotificationsSection } from "./components/PushNotificationsSection"
import { SourceRow } from "./components/SourceRow"
import type { PushSubscriptionDevice } from "./pushSubscription"
import type {
  NotificationLevel,
  NotificationPreference,
  NotificationsResponse,
  PostGroupMute,
  PushWorkingHours,
} from "./types"

const SOURCE_ORDER = ["Chat", "Post", "EmailThread", "Document", "Goal", "Meeting"] as const

export function Notifications() {
  const [preferences, setPreferences] = useState<NotificationPreference[]>([])
  const [postGroupMutes, setPostGroupMutes] = useState<PostGroupMute[]>([])
  const [pushDevices, setPushDevices] = useState<PushSubscriptionDevice[]>([])
  const [vapidPublicKey, setVapidPublicKey] = useState<string>("")
  const [workingHours, setWorkingHours] = useState<PushWorkingHours | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [flashError, setFlashError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    apiFetch<NotificationsResponse>("/api/notifications")
      .then(data => {
        if (cancelled) return
        setPreferences(data.preferences)
        setPostGroupMutes(data.post_group_mutes)
        setPushDevices(data.push.devices)
        setVapidPublicKey(data.push.vapid_public_key)
        setWorkingHours(data.push.working_hours)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError("Could not load notification settings.")
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function updatePreference(resourceType: string, level: NotificationLevel) {
    const previous = preferences
    setPreferences(prev => prev.map(p => (p.resource_type === resourceType ? { ...p, default_level: level } : p)))
    try {
      const updated = await apiFetch<NotificationPreference>(`/api/notifications/${resourceType.toLowerCase()}`, {
        method: "PATCH",
        body: JSON.stringify({ default_level: level }),
      })
      setPreferences(prev => prev.map(p => (p.resource_type === resourceType ? updated : p)))
    } catch {
      // Revert on failure so the UI never shows a state that didn't actually persist.
      setPreferences(previous)
      setFlashError("Could not save your change.")
    }
  }

  async function updatePostGroupMute(groupId: string, muted: boolean) {
    const previous = postGroupMutes
    setPostGroupMutes(prev => prev.map(m => (m.group_id === groupId ? { ...m, muted } : m)))
    try {
      const updated = await apiFetch<PostGroupMute>(`/api/notifications/posts/groups/${groupId}/mute`, {
        method: "PATCH",
        body: JSON.stringify({ muted }),
      })
      setPostGroupMutes(prev => prev.map(m => (m.group_id === groupId ? updated : m)))
    } catch {
      setPostGroupMutes(previous)
      setFlashError("Could not save your change.")
    }
  }

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} />

  const orderedPreferences = SOURCE_ORDER.map(type => preferences.find(p => p.resource_type === type)).filter(
    (p): p is NotificationPreference => p !== undefined && sourceMetaFor(p.resource_type) !== undefined
  )

  return (
    <div>
      <StickyHeader>
        <div className="flex items-center gap-2 p-2">
          <h1 className="text-lg font-accent px-1">Notifications</h1>
        </div>
      </StickyHeader>
      <div className="px-2 pb-8">
        <p className="text-sm text-base-content/60 mb-5">@mentions, assignments, and direct asks always reach you.</p>

        {flashError && (
          <div role="alert" className="alert alert-error mb-4">
            <span>{flashError}</span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setFlashError(null)}>
              Dismiss
            </button>
          </div>
        )}

        <div className="rounded-2xl border border-base-300 divide-y divide-base-300 overflow-hidden">
          {orderedPreferences.map(pref => {
            const isPosts = pref.resource_type === "Post"
            return (
              <SourceRow
                key={pref.resource_type}
                preference={pref}
                onChange={level => updatePreference(pref.resource_type, level)}
              >
                {isPosts && postGroupMutes.length > 0 && (
                  <PostGroupMutes mutes={postGroupMutes} onChange={updatePostGroupMute} />
                )}
              </SourceRow>
            )
          })}
        </div>

        <PushNotificationsSection
          devices={pushDevices}
          vapidPublicKey={vapidPublicKey}
          workingHours={workingHours}
          onDevicesChange={setPushDevices}
          onWorkingHoursChange={setWorkingHours}
          onError={setFlashError}
        />
      </div>
    </div>
  )
}
