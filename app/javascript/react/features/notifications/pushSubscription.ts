import { apiFetch } from "~/react/shared/apiFetch"

export interface PushSubscriptionDevice {
  id: string
  endpoint_suffix: string
  user_agent: string | null
  platform: string | null
  created_at: string
}

export class PushPermissionDeniedError extends Error {
  constructor() {
    super("Notification permission denied")
    this.name = "PushPermissionDeniedError"
  }
}

export class PushUnsupportedError extends Error {
  constructor() {
    super("Push notifications are not supported in this browser")
    this.name = "PushUnsupportedError"
  }
}

export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  )
}

export function getCurrentPermission(): NotificationPermission {
  if (typeof window === "undefined" || !("Notification" in window)) return "default"
  return Notification.permission
}

// Returns the last-12-char suffix (matching the server's PushSubscriptionResponse
// shape) of the current browser's push subscription, or null if no subscription
// exists. The component compares this to the rendered device list to identify
// which row is "this device" and hide the now-redundant Enable button.
export async function getCurrentDeviceEndpointSuffix(): Promise<string | null> {
  if (!isPushSupported()) return null
  try {
    const reg = await navigator.serviceWorker.ready
    const sub = await reg.pushManager.getSubscription()
    return sub ? `…${sub.endpoint.slice(-12)}` : null
  } catch {
    return null
  }
}

// Chrome rejects a raw base64url string passed to `applicationServerKey` with
// `InvalidAccessError: The provided applicationServerKey is not valid.` The
// W3C Push API spec allows `BufferSource | string`, but Chrome's implementation
// only accepts the BufferSource form for VAPID keys. Without this helper,
// enablePushOnThisDevice would fail on the largest target browser.
export function urlBase64ToUint8Array(base64url: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64url.length % 4)) % 4)
  const base64 = (base64url + padding).replace(/-/g, "+").replace(/_/g, "/")
  const raw = atob(base64)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

// The service worker reads this on `pushsubscriptionchange` (rotation can
// fire when the page isn't open, so the SW must be self-sufficient). The SW
// can't import bundled code — keep these constants in sync with the matching
// block in `static/service-worker.js`.
const VAPID_DB_NAME = "push-subscription-state"
const VAPID_STORE = "state"
const VAPID_KEY = "vapid_public_key"

function openVapidDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(VAPID_DB_NAME, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(VAPID_STORE)) db.createObjectStore(VAPID_STORE)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function stashVapidPublicKey(vapidPublicKey: string): Promise<void> {
  // IndexedDB is missing in private-browsing iframes and on revoked storage
  // permission. Failure to stash isn't a subscribe-blocker — the user just
  // can't recover from browser-initiated rotation without a manual re-enable.
  if (typeof indexedDB === "undefined") return
  let db: IDBDatabase | null = null
  try {
    db = await openVapidDB()
    const existing = await new Promise<string | null>((resolve, reject) => {
      const tx = db!.transaction(VAPID_STORE, "readonly")
      const req = tx.objectStore(VAPID_STORE).get(VAPID_KEY)
      req.onsuccess = () => resolve(typeof req.result === "string" ? req.result : null)
      req.onerror = () => reject(req.error)
    })
    if (existing === vapidPublicKey) return
    await new Promise<void>((resolve, reject) => {
      const tx = db!.transaction(VAPID_STORE, "readwrite")
      tx.objectStore(VAPID_STORE).put(vapidPublicKey, VAPID_KEY)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error)
    })
  } catch {
    // Swallow — see comment above.
  } finally {
    db?.close()
  }
}

export async function enablePushOnThisDevice(vapidPublicKey: string): Promise<PushSubscriptionDevice> {
  if (!isPushSupported()) throw new PushUnsupportedError()
  if (!vapidPublicKey) throw new Error("Push notifications aren't configured for this environment")

  if (Notification.permission === "denied") throw new PushPermissionDeniedError()
  if (Notification.permission === "default") {
    const result = await Notification.requestPermission()
    if (result !== "granted") throw new PushPermissionDeniedError()
  }

  const registration = await navigator.serviceWorker.ready
  const browserSubscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
  })
  await stashVapidPublicKey(vapidPublicKey)

  // Cast through `unknown` to access toJSON, which is on PushSubscription but
  // typed loosely by the stock lib.dom.d.ts.
  const json = (browserSubscription as unknown as { toJSON: () => PushSubscriptionJSON }).toJSON()
  const endpoint = json.endpoint ?? browserSubscription.endpoint
  const keys = json.keys ?? {}

  if (!endpoint || !keys.p256dh || !keys.auth) {
    throw new Error("Browser returned an incomplete push subscription")
  }

  return await apiFetch<PushSubscriptionDevice>("/api/push/subscriptions", {
    method: "POST",
    body: JSON.stringify({
      protocol: "web_push",
      endpoint,
      keys: { p256dh: keys.p256dh, auth: keys.auth },
      user_agent: navigator.userAgent,
    }),
  })
}

export async function disableDevice(
  subscriptionId: string,
  { isCurrentDevice }: { isCurrentDevice: boolean }
): Promise<void> {
  // Only unsubscribe the local browser when disabling the row that represents
  // *this* device. Disabling a different device (e.g., the user's phone, from
  // their laptop) must not touch the local pushManager — otherwise the laptop
  // silently loses its own subscription.
  //
  // Order matters when it IS the current device: unsubscribe the browser
  // BEFORE the server DELETE. If we delete server-side first and the browser
  // unsubscribe fails, pushManager.getSubscription() keeps returning the same
  // endpoint; a later re-enable short-circuits via the dedupe semantics and
  // the user silently misses pushes routed to the freshly-deleted row.
  if (isCurrentDevice && isPushSupported()) {
    try {
      const registration = await navigator.serviceWorker.ready
      const browserSubscription = await registration.pushManager.getSubscription()
      if (browserSubscription) await browserSubscription.unsubscribe()
    } catch {
      // Swallow and continue: the user clicked Disable, so we owe them the
      // server-side delete even if the browser-side unsubscribe fails. A
      // stale browser registration repairs itself on the next re-enable.
    }
  }

  await apiFetch(`/api/push/subscriptions/${subscriptionId}`, { method: "DELETE" })
}
