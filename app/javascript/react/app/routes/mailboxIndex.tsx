import { createRoute, getRouteApi, lazyRouteComponent, redirect } from "@tanstack/react-router"
import { useEffect } from "react"

import { EntryListSkeleton } from "~/react/features/mailboxIndex/components/EntryListSkeleton"
import { apiFetch } from "~/react/shared/apiFetch"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"
import { queryClient } from "~/react/shared/queryClient"

import { shellRoute } from "../shellRoute"
import { focusParams, focusSearch, inboxSearch, type InboxSearch, type MailboxFocusResponse } from "./mailboxFocus"

// See documentsIndex.tsx for the route-definition conventions. lazyRouteComponent
// code-splits the page chunk while the route's contracts (validateSearch) stay eager.
const MailboxIndexView = lazyRouteComponent(() => import("~/react/features/mailboxIndex/MailboxIndex"), "MailboxIndex")

// The inbox is seven paths rendering one page, distinguished only by which server
// view it reads — mirroring the route_to_view map in the deleted
// mailbox_entries/index.html.jinja. They're seven static routes rather than one
// `/$view` param route so a bogus single-segment path behaves the same on a soft
// navigation as it does on a hard load (SPA_PATHS is explicit server-side), and so
// each keeps a 1:1 mapping with its legacy route name.

const mailboxFocusQueryOptions = {
  queryKey: ["mailboxFocus"],
  queryFn: () => apiFetch<MailboxFocusResponse>("/api/users/me/mailbox_focus"),
}

// The client-side half of the focus-preference contract the deleted mailbox_index
// handler owned: this is its 302, and usePersistFocus below is its Set-Cookie.
//
// Guarded on the RAW query string, not the validated search, to keep
// `if not request.query_params` behavior — a link carrying an unrelated param
// suppresses the redirect exactly as it does server-side. A default focus falls
// through untouched rather than churning the URL.
async function redirectToStoredFocus(searchStr: string) {
  if (searchStr) return
  // fetchQuery, not ensureQueryData: the focus lives in a cookie that changes under
  // us (the persist effect writes it, and the GET self-heals a preference pointing
  // at something deleted), so a cached value would redirect to a focus that no
  // longer exists — deleting the on-screen view navigates here to escape it.
  // Concurrent calls (preload-on-intent racing the click) still dedup in flight.
  let focus: MailboxFocusResponse
  try {
    focus = await queryClient.fetchQuery(mailboxFocusQueryOptions)
  } catch {
    // The route tree has no errorComponent, so a thrown fetch would drop the user on
    // the router's bare error boundary over a non-critical preference read. Fall
    // through to the default inbox instead, mirroring usePersistFocus's silent write.
    return
  }
  const search = focusParams(focus)
  if (!search) return
  throw redirect({ to: "/", search, replace: true })
}

// The write half, URL-derived rather than click-derived: arriving at "/" carrying
// focus params persists them however you got there — dropdown, deep link, browser
// back — which is what the server did by rendering the params it was handed.
//
// Only the params actually present are sent. The PATCH encodes on presence with
// `sort` winning, so including a sort that validateSearch defaulted would silently
// drop a view the user just picked. Scoped to "/" because only mailbox_index wrote
// the cookie; the other six never did.
function usePersistFocus(search: InboxSearch) {
  const { sort } = search
  const template = search.mailbox_view_template
  const goalId = search.goal_id
  const viewId = search.mailbox_view_id
  useEffect(() => {
    const focus = focusParams({
      sort,
      mailbox_view_template: template,
      goal_id: goalId,
      mailbox_view_id: viewId,
    })
    if (!focus) return
    // A failed preference write is invisible to the user and costs them nothing
    // this navigation, so it stays silent (apiFetch already reports it).
    void apiFetch("/api/users/me/mailbox_focus", { method: "PATCH", body: JSON.stringify(focus) }).catch(() => {})
  }, [sort, template, goalId, viewId])
}

export const mailboxIndexRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/",
  staticData: { showGmailReauthBadge: true },
  validateSearch: inboxSearch,
  beforeLoad: ({ location }) => redirectToStoredFocus(location.searchStr),
  component: function InboxPage() {
    useDocumentTitle("Inbox")
    const search = getRouteApi("/shell/").useSearch()
    usePersistFocus(search)
    return <MailboxIndexView view="inbox" {...search} />
  },
  // Paints while the lazy page chunk downloads, so the skeleton shows the instant
  // a <Link> lands here — before the page code or its data exist.
  pendingComponent: EntryListSkeleton,
})

export const mailboxUnreadRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/unread",
  validateSearch: focusSearch,
  component: function UnreadPage() {
    useDocumentTitle("Inbox")
    const search = getRouteApi("/shell/unread").useSearch()
    return <MailboxIndexView view="unread" {...search} />
  },
  pendingComponent: EntryListSkeleton,
})

export const mailboxArchivedRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/archived",
  staticData: { showGmailReauthBadge: true },
  validateSearch: focusSearch,
  component: function ArchivedPage() {
    useDocumentTitle("Inbox")
    const search = getRouteApi("/shell/archived").useSearch()
    return <MailboxIndexView view="archived" {...search} />
  },
  pendingComponent: EntryListSkeleton,
})

export const mailboxSentRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/sent",
  staticData: { showGmailReauthBadge: true },
  validateSearch: focusSearch,
  component: function SentPage() {
    useDocumentTitle("Inbox")
    const search = getRouteApi("/shell/sent").useSearch()
    return <MailboxIndexView view="sent" {...search} />
  },
  pendingComponent: EntryListSkeleton,
})

export const mailboxDraftsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/drafts",
  staticData: { showGmailReauthBadge: true },
  validateSearch: focusSearch,
  component: function DraftsPage() {
    useDocumentTitle("Inbox")
    const search = getRouteApi("/shell/drafts").useSearch()
    return <MailboxIndexView view="drafts" {...search} />
  },
  pendingComponent: EntryListSkeleton,
})

export const mailboxAssignedToMeRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/assigned_to_me",
  staticData: { showGmailReauthBadge: true },
  validateSearch: focusSearch,
  component: function AssignedToMePage() {
    useDocumentTitle("Inbox")
    const search = getRouteApi("/shell/assigned_to_me").useSearch()
    return <MailboxIndexView view="assigned_to_me" {...search} />
  },
  pendingComponent: EntryListSkeleton,
})

export const mailboxSnoozedRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/snoozed",
  staticData: { showGmailReauthBadge: true },
  validateSearch: focusSearch,
  component: function SnoozedPage() {
    useDocumentTitle("Inbox")
    const search = getRouteApi("/shell/snoozed").useSearch()
    return <MailboxIndexView view="snoozed" {...search} />
  },
  pendingComponent: EntryListSkeleton,
})
