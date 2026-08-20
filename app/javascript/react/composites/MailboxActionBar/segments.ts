// Shared styling for the mailbox action bar's joined segment clusters. Lives in
// its own module (not MailboxActionBar.tsx) so sibling pieces like MailboxEntryNav
// can reuse it without importing MailboxActionBar and forming an import cycle.
// MAILBOX_ACTION_SEGMENT_CLASS is re-exported from MailboxActionBar for existing
// consumers (e.g. the email-thread AI toggle).

// A flat icon button that sits inside a joined cluster. The disabled: utilities
// dim the button and neutralize hover/cursor so a boundary nav arrow (front/back
// of the mailbox) reads as unavailable — :hover still applies to disabled buttons.
export const MAILBOX_ACTION_SEGMENT_CLASS =
  "flex items-center justify-center h-8 w-8 rounded-full text-base-600 transition-colors cursor-pointer hover:bg-base-300 hover:text-base-content active:bg-base-400/50 disabled:opacity-40 disabled:cursor-default disabled:hover:bg-transparent disabled:hover:text-base-600"

// The pill that joins segment buttons together, mirroring the segmented clusters
// in the top nav.
export const MAILBOX_ACTION_CLUSTER_CLASS =
  "flex items-center rounded-full border border-neutral bg-base-200 p-0.5 shadow-xs"

// Vertical hairline between segments inside a cluster.
export const MAILBOX_ACTION_DIVIDER_CLASS = "w-px h-5 bg-base-300 shrink-0"
