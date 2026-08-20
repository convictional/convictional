// Mirrors `app.routers.api.schemas.ProfileResponse`. The curated timezone list
// is *not* on this resource — it's a display-only frontend constant (timezones.ts).
export interface Profile {
  name: string | null
  bio: string | null
  time_zone: string | null
  picture: string | null
  has_custom_avatar: boolean
}

// Mirrors `integrations.google.api.GmailConnectionResponse`. Single explicit-state
// enum: "unavailable" = the user isn't Google-authed, so a Gmail
// connect is impossible and the island shows the explanatory message instead.
// `requires_reauth` is consumed only by the mailbox reauth badge (GmailReauthBadge);
// this section keys off `status` alone (reconnect and connect are one flow here).
export interface GmailConnection {
  status: "connected" | "disconnected" | "unavailable"
  requires_reauth: boolean
}

// Mirrors `integrations.slack.api.SlackConnectionResponse`. "unavailable" = no one
// in the org has installed the Slack app, so the island shows the "ask an admin"
// copy instead of a connect button.
export interface SlackConnection {
  status: "connected" | "disconnected" | "unavailable"
}

// Mirrors the subset of `integrations.notion.api.NotionStatusResponse` this section
// reads. The full status type lives in the (sealed) notion island; this section is
// status-only (a line + a link to the notion management island), so it redeclares
// just what it needs rather than reaching across islands.
export interface NotionConnection {
  is_connected: boolean
}

// Bootstrap config only — server values the client can't discover. `hasGoogleOauth`
// gates the Gmail section; `slackAppInstallUrl` is the workspace-admin install link
// shown when Slack isn't installed for the org.
export interface UserSettingsProps {
  hasGoogleOauth: boolean
  slackAppInstallUrl: string
}
