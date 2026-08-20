import { useEffect, useState } from "react"
import { apiFetch, errorMessage } from "~/react/shared/apiFetch"
import { useNativeShell } from "~/react/shared/hooks/useNativeShell"
import { isIOS } from "~/react/shared/platform"
import { isPushAvailableHere } from "../platformDetection"
import {
  disableDevice,
  enablePushOnThisDevice,
  getCurrentDeviceEndpointSuffix,
  getCurrentPermission,
  PushPermissionDeniedError,
  type PushSubscriptionDevice,
} from "../pushSubscription"
import type { PushWorkingHours } from "../types"
import { AddToHomeScreenInstructions } from "./AddToHomeScreenInstructions"

interface Props {
  devices: PushSubscriptionDevice[]
  vapidPublicKey: string
  workingHours: PushWorkingHours | null
  onDevicesChange: (devices: PushSubscriptionDevice[]) => void
  onWorkingHoursChange: (workingHours: PushWorkingHours | null) => void
  onError: (message: string) => void
}

// Starting values the inputs pre-fill with when the user opens the section
// without any saved working hours. They aren't a default — null means "no
// working hours" both client- and server-side. The user has to actually change
// one of the values (or re-confirm by retyping) for a save to fire.
const STARTING_START = "09:00"
const STARTING_END = "17:00"

function SectionShell({ children }: { children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="text-lg font-accent">Push notifications</h2>
      <p className="text-sm text-base-content/60 mt-1 mb-2">
        Get push notifications for key chat and post activity, including @mentions, DMs, and replies.
      </p>
      <div className="rounded-2xl border border-base-300 overflow-hidden">
        <div className="px-4 py-4 bg-base-50">{children}</div>
      </div>
    </section>
  )
}

function UnsupportedMessage() {
  return <p className="text-sm text-base-content/50 italic">Push isn&apos;t available in this browser.</p>
}

function NativeShellMessage() {
  return (
    <p className="text-sm text-base-content/70">
      Push notifications are managed by the Convictional app. Enable them from your device&apos;s system settings.
    </p>
  )
}

export function PushNotificationsSection({
  devices,
  vapidPublicKey,
  workingHours,
  onDevicesChange,
  onWorkingHoursChange,
  onError,
}: Props) {
  const [permission, setPermission] = useState<NotificationPermission>(() => getCurrentPermission())
  const [thisDeviceSuffix, setThisDeviceSuffix] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const isNative = useNativeShell()
  const persistedStart = workingHours?.start ?? STARTING_START
  const persistedEnd = workingHours?.end ?? STARTING_END
  const [startValue, setStartValue] = useState(persistedStart)
  const [endValue, setEndValue] = useState(persistedEnd)
  const isConfigured = workingHours !== null

  // Reset the inputs when the persisted values change from outside (initial load
  // or a rollback). Depend on the primitive values, not the object reference,
  // so the optimistic-update round-trip doesn't clobber an in-progress edit.
  useEffect(() => {
    setStartValue(persistedStart)
    setEndValue(persistedEnd)
  }, [persistedStart, persistedEnd])

  // Re-read permission once on mount in case it changed since the last render
  // (the API has no event for that — only mount, focus, or after our prompt).
  // Also fetch the current browser's subscription so we know which row in
  // the list represents "this device."
  useEffect(() => {
    setPermission(getCurrentPermission())
    let cancelled = false
    getCurrentDeviceEndpointSuffix().then(suffix => {
      if (!cancelled) setThisDeviceSuffix(suffix)
    })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleEnable() {
    setBusy(true)
    try {
      const device = await enablePushOnThisDevice(vapidPublicKey)
      onDevicesChange([device, ...devices.filter(d => d.id !== device.id)])
      setPermission(getCurrentPermission())
      setThisDeviceSuffix(await getCurrentDeviceEndpointSuffix())
    } catch (err) {
      if (err instanceof PushPermissionDeniedError) {
        setPermission("denied")
        onError("Push notifications are blocked. Update your browser permissions to re-enable.")
      } else {
        onError(errorMessage(err, "Could not enable push notifications on this device."))
      }
    } finally {
      setBusy(false)
    }
  }

  async function saveWorkingHours(next: PushWorkingHours | null) {
    const previous = workingHours
    onWorkingHoursChange(next)
    try {
      const updated = await apiFetch<PushWorkingHours | null>("/api/push/working_hours", {
        method: "PATCH",
        body: JSON.stringify({ start: next?.start ?? null, end: next?.end ?? null }),
      })
      // Skip the second update when the server echoed the same values back —
      // a fresh object reference would re-render parents for no content change.
      if (updated?.start !== next?.start || updated?.end !== next?.end) {
        onWorkingHoursChange(updated)
      }
    } catch (err) {
      onWorkingHoursChange(previous)
      onError(errorMessage(err, "Could not save your working hours."))
    }
  }

  async function handleHoursBlur() {
    if (startValue === persistedStart && endValue === persistedEnd) return
    if (startValue === endValue) {
      // Server rejects start == end; reset to last persisted so the UI doesn't
      // imply the value was saved.
      setStartValue(persistedStart)
      setEndValue(persistedEnd)
      onError("Working hours start and end must differ.")
      return
    }
    await saveWorkingHours({ start: startValue, end: endValue })
  }

  async function handleWorkingHoursToggle(enable: boolean) {
    if (enable) {
      // Turning on saves the suggested window immediately so "on" always means
      // "a real window is configured" — no pending-state ambiguity.
      await saveWorkingHours({ start: STARTING_START, end: STARTING_END })
    } else {
      await saveWorkingHours(null)
    }
  }

  async function handleDisable(device: PushSubscriptionDevice) {
    const previous = devices
    const isCurrentDevice = device.endpoint_suffix === thisDeviceSuffix
    onDevicesChange(devices.filter(d => d.id !== device.id))
    setBusy(true)
    try {
      await disableDevice(device.id, { isCurrentDevice })
      if (isCurrentDevice) setThisDeviceSuffix(await getCurrentDeviceEndpointSuffix())
    } catch (err) {
      onDevicesChange(previous)
      onError(errorMessage(err, "Could not disable this device."))
    } finally {
      setBusy(false)
    }
  }

  // Hide the section entirely when keys aren't loaded — without a VAPID
  // public key the browser API rejects subscribe(), so there's nothing
  // useful to render.
  if (!vapidPublicKey) return null

  // Inside the native shell APNs handles push, not the W3C Push API. Show a
  // brief note pointing the user at the OS settings; once native registration
  // is wired the device list below this will populate from the same API.
  if (isNative) {
    return (
      <SectionShell>
        <NativeShellMessage />
      </SectionShell>
    )
  }

  // iOS Safari in a tab can't subscribe at all (Apple gates push to standalone
  // PWAs), so the Enable button would be a dead end. Show Add-to-Home-Screen
  // steps instead. Anything else that fails the support check (older browser,
  // missing API) gets the generic "not available" note.
  if (!isPushAvailableHere()) {
    return <SectionShell>{isIOS() ? <AddToHomeScreenInstructions /> : <UnsupportedMessage />}</SectionShell>
  }

  const thisDeviceInList = thisDeviceSuffix !== null && devices.some(d => d.endpoint_suffix === thisDeviceSuffix)

  return (
    <SectionShell>
      {devices.length > 0 && (
        <ul className="divide-y divide-base-300 -mx-4 -mt-1 mb-6">
          {devices.map(device => {
            const isThisDevice = device.endpoint_suffix === thisDeviceSuffix
            return (
              <li key={device.id} className="flex items-center justify-between gap-3 px-4 py-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-semibold truncate">{device.platform || "Unknown browser"}</div>
                    {isThisDevice && (
                      <span className="text-xs font-medium text-primary bg-primary/10 px-1.5 py-0.5 rounded">
                        This device
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-base-content/50 font-mono truncate">{device.endpoint_suffix}</div>
                </div>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  disabled={busy}
                  onClick={() => handleDisable(device)}
                >
                  Disable
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {permission === "denied" ? (
        // Once a user denies notifications, the API cannot prompt them again —
        // the only recovery is via the browser's site-permissions UI.
        <p className="text-sm text-base-content/70">
          Push notifications are blocked in this browser. Click the lock icon in your address bar, allow notifications
          for this site, then reload the page.
        </p>
      ) : thisDeviceInList ? (
        <p className="text-sm text-base-content/60">
          To enable push on another device, open this page on it and tap <strong>Enable</strong>.
        </p>
      ) : (
        <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={handleEnable}>
          {busy ? "Working…" : "Enable push on this device"}
        </button>
      )}

      {devices.length > 0 && (
        <div className="mt-6 pt-4 border-t border-base-300 space-y-2">
          <label className="flex gap-3 cursor-pointer items-center">
            <input
              type="radio"
              name="working_hours_mode"
              className={`radio radio-sm ${!isConfigured ? "radio-primary" : "hover:radio-primary"}`}
              checked={!isConfigured}
              onChange={() => handleWorkingHoursToggle(false)}
            />
            <span className={`text-sm font-semibold ${!isConfigured ? "" : "text-base-content/60"}`}>Always</span>
          </label>
          <label className="flex gap-3 cursor-pointer items-center">
            <input
              type="radio"
              name="working_hours_mode"
              className={`radio radio-sm ${isConfigured ? "radio-primary" : "hover:radio-primary"}`}
              checked={isConfigured}
              onChange={() => handleWorkingHoursToggle(true)}
            />
            <span className={`text-sm font-semibold ${isConfigured ? "" : "text-base-content/60"}`}>
              During working hours
            </span>
            <span className="flex items-center gap-2">
              <input
                type="time"
                disabled={!isConfigured}
                className="input input-sm input-bordered"
                value={startValue}
                onChange={e => setStartValue(e.target.value)}
                onBlur={handleHoursBlur}
                aria-label="Working hours start"
              />
              <span className="text-sm text-base-content/60">to</span>
              <input
                type="time"
                disabled={!isConfigured}
                className="input input-sm input-bordered"
                value={endValue}
                onChange={e => setEndValue(e.target.value)}
                onBlur={handleHoursBlur}
                aria-label="Working hours end"
              />
            </span>
          </label>
        </div>
      )}
    </SectionShell>
  )
}
