import { useEffect, useState } from "react"

import { GmailLogo } from "~/react/ui/GmailLogo"

import type { InboxProgressResponse } from "../types"

interface InboxSetupBannerProps {
  state: InboxProgressResponse
  gmailAuthUrl?: string
}

type BannerVariant = "syncing" | "gmail_not_connected" | null

const GMAIL_DISMISSAL_KEY = "inbox-gmail-banner-dismissed-at"
const GMAIL_DISMISSAL_TTL_MS = 60 * 60 * 1000

function gmailBannerDismissedRecently(): boolean {
  try {
    const dismissedAt = Number(window.localStorage.getItem(GMAIL_DISMISSAL_KEY))
    return dismissedAt > 0 && Date.now() - dismissedAt < GMAIL_DISMISSAL_TTL_MS
  } catch {
    return false
  }
}

function recordGmailBannerDismissal(): void {
  try {
    window.localStorage.setItem(GMAIL_DISMISSAL_KEY, String(Date.now()))
  } catch {
    // private mode / storage disabled — the dismissal still holds for this session
  }
}

function resolveVariant(state: InboxProgressResponse): BannerVariant {
  if (state.onboarding_mailbox_sync_started_at && !state.is_onboarding_mailbox_sync_complete) {
    return "syncing"
  }
  // Microsoft users have no Gmail to connect — never surface the Gmail prompt,
  // including on a live WebSocket-driven re-render.
  if (!state.has_gmail_integration && state.is_google_authenticated) {
    return "gmail_not_connected"
  }
  return null
}

export function InboxSetupBanner({ state, gmailAuthUrl }: InboxSetupBannerProps) {
  const variant = resolveVariant(state)
  // Dismissals are per-variant: each variant gets its own component instance (keyed by
  // variant), so closing a banner and returning with a different variant will show the new
  // banner. The key={variant} prop ensures a fresh mount on variant change.
  //
  // The Gmail prompt outlives the session: connecting Gmail is a deliberate task a user may
  // not want to do right now, so a dismissal is honoured for an hour rather than re-nagging
  // on the next load. The syncing banner is transient, so its dismissal stays in-memory.
  const [dismissedVariant, setDismissedVariant] = useState<BannerVariant>(() =>
    gmailBannerDismissedRecently() ? "gmail_not_connected" : null
  )

  if (!variant || dismissedVariant === variant) return null

  const dismiss = () => {
    if (variant === "gmail_not_connected") recordGmailBannerDismissal()
    setDismissedVariant(variant)
  }

  // Keyed on `variant` so each variant mounts a fresh `AnimatedBanner` with its own
  // `shown` lifecycle — guarantees the enter animation plays on every variant change.
  return <AnimatedBanner key={variant} variant={variant} gmailAuthUrl={gmailAuthUrl} onDismiss={dismiss} />
}

function AnimatedBanner({
  variant,
  gmailAuthUrl,
  onDismiss,
}: {
  variant: Exclude<BannerVariant, null>
  gmailAuthUrl?: string
  onDismiss: () => void
}) {
  const [shown, setShown] = useState(false)

  useEffect(() => {
    const handle = window.setTimeout(() => setShown(true), 200)
    return () => window.clearTimeout(handle)
  }, [])

  return (
    <div
      className={`m-1.5 mb-4 bg-base-50 rounded-xl p-6 border border-base-300 shadow-xs transition duration-500 ease-out ${
        shown ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-2"
      }`}
    >
      {variant === "syncing" ? <SyncingBanner onDismiss={onDismiss} /> : null}
      {variant === "gmail_not_connected" ? (
        <GmailNotConnectedBanner onDismiss={onDismiss} gmailAuthUrl={gmailAuthUrl ?? "#"} />
      ) : null}
    </div>
  )
}

function DismissButton({ onDismiss }: { onDismiss: () => void }) {
  return (
    <button
      type="button"
      onClick={onDismiss}
      aria-label="Dismiss"
      className="flex items-center justify-center w-5 h-5 rounded-full bg-base-200 text-base-500 shrink-0 cursor-pointer"
    >
      <span className="material-symbols-outlined leading-none text-[12px]">close</span>
    </button>
  )
}

function SyncingBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="flex-1 flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-baseline justify-between min-w-0 w-full">
          <span className="text-sm font-medium">Syncing your Gmail</span>
          <span className="text-xs text-base-500 hidden sm:inline shrink-0">Can take up to an hour</span>
        </div>
        <DismissButton onDismiss={onDismiss} />
      </div>
      <div className="h-1 bg-base-200 rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full w-0 min-w-2 animate-[fillToNinetyFive_800s_linear_forwards]" />
      </div>
      <p className="text-xs text-base-500">
        Your emails are encrypted at rest, and attested to by SOC2 Type II and Google&apos;s CASA level 3. They can
        only be read by you.
      </p>
    </div>
  )
}

function GmailNotConnectedBanner({ onDismiss, gmailAuthUrl }: { onDismiss: () => void; gmailAuthUrl: string }) {
  return (
    <div className="flex-1 flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-baseline justify-between min-w-0 w-full">
          <span className="text-sm font-medium">Gmail not connected</span>
        </div>
        <DismissButton onDismiss={onDismiss} />
      </div>
      <p className="text-sm text-base-500">
        Connect Gmail to organize your inbox with AI, get smarter notifications, and collaborate with your team in real
        time.
      </p>
      {/* Gmail OAuth redirects cross-origin to Google, so opt this anchor out of
          HTMX boost — a boosted AJAX request can't follow the redirect. */}
      <a className="btn btn-lg btn-primary w-fit" href={gmailAuthUrl} data-hx-boost="false">
        <span className="w-5">
          <GmailLogo />
        </span>
        Connect Gmail
      </a>
    </div>
  )
}
