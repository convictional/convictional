// Detection and side-effect helpers for "the web product is loaded inside the
// Convictional native shell" — i.e. running inside the React Native WebView
// host with `window.__convictionalNative` injected by
// `injectedJavaScriptBeforeContentLoaded`. See app/mobile/components/bridge.ts
// for the contract.
//
// In native shell we suppress browser-specific affordances that either don't
// apply (Install-as-PWA banner) or are actively replaced by native equivalents
// (web push permission prompt). The body class lets server-rendered HTML opt
// chrome out of the native shell via a single CSS selector.

// Mirror of the bridge contract in app/mobile/components/bridge.ts. Drift
// here breaks the cross-stack handshake silently — keep both sides in sync.
export interface ConvictionalNativeBridge {
  registerPush(): void
  logout(): void
  shareCurrentUrl(title?: string): void
  appReady(): void
  setUser(user: { id: string; email: string } | null): void
}

declare global {
  interface Window {
    __convictionalNative?: ConvictionalNativeBridge
  }
}

const BODY_CLASS = "native-shell"

export function isNativeShell(): boolean {
  return typeof window !== "undefined" && typeof window.__convictionalNative !== "undefined"
}

// Called once at module load (from main.ts). The class lets CSS hide PWA-only
// chrome with `body.native-shell .pwa-only { display: none }`. Idempotent so
// hot-reload or accidental double-import doesn't add duplicate classes.
//
// `document.body` is null until `<body>` is parsed. `<script type="module">`
// is deferred, so in practice body is always available by the time this
// runs — but the optional-chain costs nothing and defends against bundle
// loading via inline `<script>` or test environments that stub document.
export function applyNativeShellBodyClass(): void {
  if (typeof document === "undefined") return
  if (!isNativeShell()) return
  document.body?.classList.add(BODY_CLASS)
}

// Notifies the native side that this is an authenticated page load so it can
// request notification permission and POST the Expo push token to the backend.
// Fires once per full page load (including HTMX-driven full nav / OAuth
// redirects), not once per HTMX partial swap. The native side maintains its
// own ref of "already registered for this WebHost mount" — gating here would
// no-op because the JS realm restarts on every full nav, defeating the
// module-scoped flag.
export function notifyNativeAuthenticated(): void {
  if (!isNativeShell()) return
  try {
    window.__convictionalNative?.registerPush()
  } catch (error) {
    console.warn("[nativeShell] registerPush call failed", error)
  }
}

// Called by web on first DOMContentLoaded so the native splash screen can
// dismiss without flashing a blank WebView. Native also has its own
// `onLoadEnd` fallback for safety, so missing this call only degrades to a
// slightly later splash dismissal — never blocks the user.
export function notifyNativeAppReady(): void {
  if (!isNativeShell()) return
  try {
    window.__convictionalNative?.appReady()
  } catch (error) {
    console.warn("[nativeShell] appReady call failed", error)
  }
}

// Forwards the current user (or null on logout/session reset) to the native
// shell so its Sentry SDK can attribute native-shell errors to the right user
// across all channels — the web product is the source of truth for identity.
// No-op outside the shell.
export function notifyNativeSetUser(user: { id: string; email: string } | null): void {
  if (!isNativeShell()) return
  try {
    window.__convictionalNative?.setUser(user)
  } catch (error) {
    console.warn("[nativeShell] setUser call failed", error)
  }
}

// Wire as `onSubmitCapture` on any form that POSTs to /logout. In the native
// shell, intercepts the submit before HTMX's bubble-phase listener on
// `<body hx-boost>` can fire its XHR — the bridge takes over and the native
// side clears cookies + remounts <LoginScreen> directly.
//
// Capture phase is load-bearing: HTMX's submit handler runs in the bubble
// phase, so a plain `onSubmit` would fire AFTER HTMX has already dispatched
// the XHR. Capture fires during the event's downward trip; stopPropagation
// here halts it before the target phase, so HTMX never sees the event.
//
// In a normal browser (no native shell) this is a no-op — the form submits
// to /logout as usual and the server-side 302 to /login lands the user on
// the web login page.
export function delegateLogoutToNativeShell(event: { preventDefault(): void; stopPropagation(): void }): void {
  if (!isNativeShell()) return
  event.preventDefault()
  event.stopPropagation()
  try {
    window.__convictionalNative?.logout()
  } catch (error) {
    console.warn("[nativeShell] logout call failed", error)
  }
}
