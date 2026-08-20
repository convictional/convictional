// Push notifications on iOS only work when the site has been added to the Home
// Screen and opened as a standalone PWA — a Safari tab can't request notification
// permission at all. We branch the Push section UI on that to show install
// instructions instead of an Enable button that would either error or stay disabled.

import { isNativeShell } from "~/nativeShell"
import { isIOS } from "~/react/shared/platform"
import { isPushSupported } from "./pushSubscription"

export function isStandalonePWA(): boolean {
  if (typeof window === "undefined") return false
  if (window.matchMedia("(display-mode: standalone)").matches) return true
  // iOS Safari pre-dates the standardized display-mode media query and exposes
  // standalone state through a non-standard navigator flag instead.
  return (window.navigator as Navigator & { standalone?: boolean }).standalone === true
}

export function isPushAvailableHere(): boolean {
  // Native shell uses APNs via expo-notifications rather than the W3C Push
  // API. Hiding the web-push UI prevents the iOS WKWebView from prompting
  // for notification permission via Notification.requestPermission; the
  // native side owns the OS-level permission dialog.
  if (isNativeShell()) return false
  if (!isPushSupported()) return false
  if (isIOS() && !isStandalonePWA()) return false
  return true
}
