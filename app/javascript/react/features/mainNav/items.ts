export interface NavItem {
  label: string
  href: string
  icon: string
  hotkey: string
  match: (pathname: string) => boolean
  // The destination is served by the SPA shell (app/routers/spa.py). In island
  // mode this makes the link a native navigation instead of an hx-boost fragment
  // fetch (see NavLink). Absent for pages still rendered server-side.
  clientRouted?: boolean
}

// Predicates mirror the server-side `is_route_tagged()` calls in
// _navigation.html.jinja. Each predicate is anchored (^…(/|$)) so /posts does
// not falsely match /post_drafts and /goals does not match /goal_alignments by
// accident — these belong to their own tag groups.
export const NAV_ITEMS: readonly NavItem[] = [
  {
    label: "Inbox",
    href: "/",
    icon: "inbox",
    hotkey: "g i",
    match: pathname =>
      pathname === "/" ||
      /^\/(mailbox_views|unread|archived|sent|drafts|assigned_to_me|snoozed|email_threads|email_drafts|email_contacts|email_attachments)(\/|$)/.test(
        pathname
      ),
    clientRouted: true,
  },
  {
    label: "Chat",
    href: "/chats",
    icon: "chat_bubble",
    hotkey: "g c",
    match: pathname => /^\/chats(\/|$)/.test(pathname),
    clientRouted: true,
  },
  {
    label: "Posts",
    href: "/posts",
    icon: "feed",
    hotkey: "g p",
    match: pathname => /^\/(posts|post_drafts|post_comments)(\/|$)/.test(pathname),
    clientRouted: true,
  },
  {
    label: "Docs",
    href: "/documents",
    icon: "description",
    hotkey: "g o",
    match: pathname => /^\/documents(\/|$)/.test(pathname),
    clientRouted: true,
  },
  {
    label: "Goals",
    href: "/goals",
    icon: "flag",
    hotkey: "g g",
    match: pathname => /^\/(goals|goal_alignments|goal_comments|goal_updates)(\/|$)/.test(pathname),
    clientRouted: true,
  },
]

// The mobile bottom tab bar surfaces only the first three destinations; the
// rest are demoted into the "More" menu (MobileMoreMenu). Desktop (MainNav)
// still shows all of NAV_ITEMS. One split so the bar and the menu can't drift.
export const MOBILE_BOTTOM_TAB_ITEMS = NAV_ITEMS.slice(0, 3)
export const MOBILE_MORE_NAV_ITEMS = NAV_ITEMS.slice(3)

export function activeNavItem(pathname: string): NavItem | null {
  return NAV_ITEMS.find(item => item.match(pathname)) ?? null
}
