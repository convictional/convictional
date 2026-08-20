import { createStore } from "zustand/vanilla"

interface FeedbackDialogState {
  isOpen: boolean
  open: () => void
  close: () => void
}

// Module-level singleton so triggers in any island can call
// `feedbackDialogStore.getState().open()` without sharing a React tree
// with the dialog. See docs/react-migration.md for the cross-island
// Zustand pattern.
export const feedbackDialogStore = createStore<FeedbackDialogState>(set => ({
  isOpen: false,
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
}))

export type { FeedbackDialogState }
