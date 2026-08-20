// iOS Safari (in a tab, not standalone PWA) can't subscribe to push at all —
// Apple gates push to Home-Screen-installed PWAs. Rendered in place of the
// Enable button on iOS Safari so the user sees actionable guidance instead of
// a permission prompt that would fail or a button that silently no-ops.

export function AddToHomeScreenInstructions() {
  return (
    <div className="text-sm text-base-content/80 space-y-3">
      <p className="font-semibold text-base-content">
        Push notifications on iPhone and iPad need the app installed on your Home Screen.
      </p>
      <ol className="list-decimal list-inside space-y-1">
        <li>Tap the Share button in Safari.</li>
        <li>Choose &ldquo;Add to Home Screen.&rdquo;</li>
        <li>Open the app from your Home Screen icon.</li>
        <li>Return here and tap &ldquo;Enable push.&rdquo;</li>
      </ol>
      <details className="text-xs text-base-content/60">
        <summary className="cursor-pointer hover:text-base-content/80">Why iOS needs this</summary>
        <p className="mt-2">
          Apple only allows web apps to send push notifications when they&apos;re installed on the Home Screen and
          opened as a standalone app. Safari tabs can&apos;t request notification permission.
        </p>
      </details>
    </div>
  )
}
