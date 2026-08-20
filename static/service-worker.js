// Service worker. Its presence (along with a fetch handler) is what upgrades
// the app from a Home-screen shortcut to an installable PWA in Chrome. The
// only request we intercept is a failed top-level navigation — we serve a
// pre-cached offline page so the PWA shows our brand instead of the browser's
// generic "no internet" screen. Everything else passes through unchanged.

// Bump the suffix when offline assets change so the new copy ships immediately
// instead of waiting for the old cache to be evicted.
const OFFLINE_CACHE = "offline-v2"
const OFFLINE_URL = "/static/offline.html"
const OFFLINE_ASSETS = [OFFLINE_URL]

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(OFFLINE_CACHE)
      // `reload` bypasses the HTTP cache so the install always pulls fresh
      // copies of the offline assets rather than stale ones from an earlier SW.
      await cache.addAll(OFFLINE_ASSETS.map((url) => new Request(url, { cache: "reload" })))
    })()
  )
  self.skipWaiting()
})

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys()
      await Promise.all(names.filter((name) => name !== OFFLINE_CACHE).map((name) => caches.delete(name)))
      await self.clients.claim()
    })()
  )
})

self.addEventListener("fetch", (event) => {
  // Only handle top-level page loads. Asset requests (JS/CSS/images/API) fall
  // through to the network so we don't ship a stale shell or interfere with
  // HTMX/fetch-driven flows.
  if (event.request.mode !== "navigate") return

  event.respondWith(
    (async () => {
      try {
        return await fetch(event.request)
      } catch (_) {
        const cache = await caches.open(OFFLINE_CACHE)
        const cached = await cache.match(OFFLINE_URL)
        // If the cache somehow lost the entry (storage pressure, manual
        // clear), let the browser show its default offline screen rather
        // than throwing — there's nothing useful we can do here.
        return cached || Response.error()
      }
    })()
  )
})

// `client.url` is always absolute; the push and notificationclick handlers
// both compare it against pathname-only fields from the payload so trailing
// slashes / query strings / hashes don't break the match. URL parsing throws
// on garbage hosts seen on some Android WebViews — swallow that.
function clientPathname(client) {
  try {
    return new URL(client.url).pathname
  } catch (_) {
    return null
  }
}

self.addEventListener("push", (event) => {
  let payload = null
  if (event.data) {
    try {
      payload = event.data.json()
    } catch (_) {
      payload = null
    }
  }

  // Chrome enforces userVisibleOnly: if a push arrives and we never call
  // showNotification, it eventually shows a generic "site is doing work in
  // the background" warning. On a missing or unparseable payload we still
  // render a fallback card so the user sees something useful instead.
  const title = (payload && payload.title) || "New activity"
  const body = (payload && payload.body) || "Open Convictional to see what's new"
  const urlAbsolute = (payload && payload.url) || "/inbox"
  const urlPath = (payload && payload.url_path) || "/inbox"
  const mailboxEntryUrlAbsolute = payload && payload.mailbox_entry_url
  const mailboxEntryUrlPath = payload && payload.mailbox_entry_url_path
  const tag = payload && payload.tag

  event.waitUntil(
    (async () => {
      // Drop the push when a focused tab is already on the conversation. We compare
      // pathnames against open tabs — both the bare resource URL and the mailbox-entry
      // URL count as "on this conversation," so opening from the inbox suppresses too.
      // build_payload sends both pathname and absolute forms; we only need the SW to
      // URL-parse client.url, not the payload values.
      const matched = await self.clients.matchAll({ type: "window", includeUncontrolled: true })
      // Build the focus-check Set from payload fields only — the /inbox fallback
      // baked into urlPath above would otherwise suppress the fallback card on
      // an unparseable push when the user happens to be looking at the inbox,
      // and Chrome's userVisibleOnly contract requires *some* notification.
      const targetPaths = new Set(
        [payload && payload.url_path, payload && payload.mailbox_entry_url_path].filter(Boolean)
      )
      // `focused` alone can be true on multi-display setups where a focused window
      // is covered by another (visibilityState !== "visible"). The user isn't
      // actually seeing the in-app realtime there, so still render the OS card.
      const focusedOnTarget = matched.some(
        client => client.focused && client.visibilityState === "visible" && targetPaths.has(clientPathname(client))
      )
      if (focusedOnTarget) return

      // Tap prefers the mailbox-entry URL when present — opening it auto-marks the
      // entry read; the bare resource URL is the fallback.
      const tapUrlAbsolute = mailboxEntryUrlAbsolute || urlAbsolute
      const tapUrlPath = mailboxEntryUrlPath || urlPath
      await self.registration.showNotification(title, {
        body,
        // `url` is what openWindow needs (absolute); `url_path` is what we
        // compare against open tabs (pathname). Both are stored on the
        // notification so notificationclick can use whichever it needs without
        // re-parsing.
        data: { url: tapUrlAbsolute, url_path: tapUrlPath },
        // OS-level dedup: retries for the same logical event (mention-<id> /
        // event-<id> from the push job) replace the previous card instead of
        // stacking.
        tag,
        icon: "/static/icons/icon-192.png",
        // Android uses only the alpha channel of `badge` and paints it white in
        // the status bar — so this must be a transparent silhouette, not the
        // colorful app icon (which would render as a solid white square).
        badge: "/static/icons/notification-badge.png",
      })
    })()
  )
})

// Browser-initiated rotation can fire when the page isn't open, so the SW
// must be self-sufficient — the React subscribe path stashes the VAPID key
// here at subscribe time. The SW can't import bundled code; keep these
// constants in sync with `app/javascript/react/shared/pushSubscription.ts`.
const VAPID_DB_NAME = "push-subscription-state"
const VAPID_STORE = "state"
const VAPID_KEY = "vapid_public_key"

function openVapidDB() {
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

async function readStashedVapidKey() {
  let db = null
  try {
    db = await openVapidDB()
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(VAPID_STORE, "readonly")
      const req = tx.objectStore(VAPID_STORE).get(VAPID_KEY)
      req.onsuccess = () => resolve(typeof req.result === "string" ? req.result : null)
      req.onerror = () => reject(req.error)
    })
  } catch (_) {
    return null
  } finally {
    if (db) db.close()
  }
}

// Chrome rejects a raw base64url string passed to `applicationServerKey`,
// so VAPID keys must be converted to BufferSource before subscribe().
// Mirrors the implementation in pushSubscription.ts (no shared module since
// the SW can't import bundled code).
function urlBase64ToUint8Array(base64url) {
  const padding = "=".repeat((4 - (base64url.length % 4)) % 4)
  const base64 = (base64url + padding).replace(/-/g, "+").replace(/_/g, "/")
  const raw = atob(base64)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

// PushSubscription.getKey() returns an ArrayBuffer; the API expects the same
// base64url form the browser's toJSON() emits at initial subscribe time, so
// the server's dedupe path doesn't have to handle two encodings.
function arrayBufferToBase64Url(buffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ""
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

// Chrome and Firefox occasionally rotate push subscriptions out from under
// us. Without this handler, the SW silently loses the new endpoint and the
// user effectively loses push until they manually re-enable. `rotated_from`
// lets the server soft-delete the prior row immediately rather than waiting
// for the next 410 on it.
self.addEventListener("pushsubscriptionchange", (event) => {
  event.waitUntil(
    (async () => {
      try {
        // Per the W3C spec, browsers MAY pre-populate `event.newSubscription`
        // with the rotated subscription. When they do, calling subscribe()
        // ourselves is wasted work and can surface a redundant permission
        // prompt; when they don't (Firefox typically), fall back to subscribe.
        let newSubscription = event.newSubscription
        if (!newSubscription) {
          const vapidPublicKey = await readStashedVapidKey()
          if (!vapidPublicKey) return
          newSubscription = await self.registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
          })
        }

        const p256dh = newSubscription.getKey("p256dh")
        const auth = newSubscription.getKey("auth")
        if (!p256dh || !auth) return

        // CSRF-exempt per the middleware: the SW has no DOM, so it can't
        // read the CSRF cookie. The endpoint relies on session-cookie auth
        // + per-user dedupe + the 20/user active cap to bound abuse.
        await fetch("/api/push/subscriptions", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            protocol: "web_push",
            endpoint: newSubscription.endpoint,
            keys: {
              p256dh: arrayBufferToBase64Url(p256dh),
              auth: arrayBufferToBase64Url(auth),
            },
            user_agent: navigator.userAgent,
            rotated_from: event.oldSubscription ? event.oldSubscription.endpoint : null,
          }),
        })
      } catch (_) {
        // Best-effort: storage cleared, push service unreachable, permission
        // revoked, server 4xx/5xx. Anything thrown here leaves the device
        // without push until the user manually re-enables — no in-app surface
        // to expose yet (v2: server-side flag → "re-enable push" banner).
      }
    })()
  )
})

self.addEventListener("notificationclick", (event) => {
  event.notification.close()
  const data = event.notification.data || {}
  const urlAbsolute = data.url
  const urlPath = data.url_path
  if (!urlAbsolute || !urlPath) return

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((matchedClients) => {
      for (const client of matchedClients) {
        if (!("focus" in client)) continue
        if (clientPathname(client) === urlPath) return client.focus()
      }
      // Safari iOS can reject openWindow when the click handler doesn't have
      // a fresh user-activation token (e.g., the click happened well after
      // the notification was shown). Swallow the rejection so the SW doesn't
      // surface an uncaught error — the tap already dismissed the card.
      if (self.clients.openWindow) return self.clients.openWindow(urlAbsolute).catch(() => {})
    })
  )
})
