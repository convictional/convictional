import { useCallback, useState } from "react"

// "browse" = opened the Focus control to look around (Continue reveals the menu);
// "leave" = clicked the Clear-focus X (Continue clears the focus and navigates).
export type FocusExplainerIntent = { type: "browse" } | { type: "leave" }

// The "This is a Focus" explainer shown on the first touch of the Focus control while onboarding
// is active, so FocusDropdown stays a generic control instead of hard-coding this flow. In-memory
// only, so it re-arms on reload.
export function useOnboardingFocusExplainer(onboardingActive: boolean) {
  const [seen, setSeen] = useState(false)
  // While set, the explainer panel replaces the menu.
  const [pendingIntent, setPendingIntent] = useState<FocusExplainerIntent | null>(null)

  const needsExplainer = onboardingActive && !seen

  // Showing the explainer consumes the gate up front, so dismissing it any way (Continue, Stay,
  // or clicking away) never re-arms it within the session.
  const openExplainer = useCallback((intent: FocusExplainerIntent) => {
    setSeen(true)
    setPendingIntent(intent)
  }, [])

  const dismissExplainer = useCallback(() => setPendingIntent(null), [])

  return { needsExplainer, pendingIntent, openExplainer, dismissExplainer }
}
