import { useQuery } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { GmailLogo } from "~/react/ui/GmailLogo"

// Only the reauth bit is read here; the full connection resource also carries a
// `status` enum (see integrations.google.api.GmailConnectionResponse), but this
// composite can't reach the userSettings island's type, so it redeclares the
// subset it needs — the same posture as NotionConnection in userSettings/types.
interface GmailConnection {
  requires_reauth: boolean
}

// The "your Gmail needs reconnecting" nag, shown across the mailbox/email routes
// (route gating lives in AppShell via staticData.showGmailReauthBadge, mirroring
// the legacy GMAIL_REAUTH_BADGE_ROUTES list). This owns only the domain half —
// whether the connection actually needs re-authorizing — so the shell decides the
// where and this decides the whether.
export function GmailReauthBadge() {
  const { data } = useQuery({
    queryKey: ["gmailConnection"],
    queryFn: () => apiFetch<GmailConnection>("/api/integrations/gmail/connection"),
  })

  if (!data?.requires_reauth) return null

  // `return_to` sends the user back where they were after the OAuth round-trip,
  // matching the legacy badge's `return_to=request.path`.
  const authUrl = `/integrations/gmail/auth?return_to=${encodeURIComponent(window.location.pathname)}`

  return (
    <div className="px-2">
      <div className="w-full max-w-4xl mx-auto">
        <div className="grid grid-cols-[auto_1fr_auto] items-center gap-3 pl-3 pr-1.5 py-1.5 text-error-content bg-error/40 rounded-lg">
          <span className="material-symbols-outlined text-lg">error</span>
          <div className="text-sm">Your Gmail account needs to be reconnected</div>
          {/* The OAuth redirect needs a full-document navigation; a plain anchor in
              the htmx-free SPA shell does exactly that, with no client routing to
              intercept it. */}
          <a href={authUrl} className="flex justify-center">
            <button className="btn btn-primary">
              <span className="w-8 h-8">
                <GmailLogo />
              </span>
              Connect Gmail
            </button>
          </a>
        </div>
      </div>
    </div>
  )
}
