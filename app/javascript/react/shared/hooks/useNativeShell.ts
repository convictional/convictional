import { isNativeShell } from "~/nativeShell"

// Hook over isNativeShell() for React consumers. The underlying detection
// reads `window.__convictionalNative`, which is installed before any page JS
// runs (via injectedJavaScriptBeforeContentLoaded). So this is synchronous —
// no useState / useEffect, no async resolve, just a window read every render.
//
// The value never changes within a single page load: a WebView either has
// the bridge or it doesn't. We don't subscribe to changes for that reason.
export function useNativeShell(): boolean {
  return isNativeShell()
}
