import type { MailboxSort } from "~/react/shared/types"

// The inbox focus-preference contract, kept apart from the route module so it can be
// tested without pulling in the shell (and its whole component tree). The server half
// lives in app/helpers/mailbox_focus.py and app/routers/api/mailbox_focus.py.

// The focus selector: a saved view, or a built-in template (optionally targeting a
// goal). Mutually exclusive, all absent meaning the plain inbox. Preserves the deep
// links url_for("mailbox_index").include_query_params(...) still produces server-side.
export interface FocusSearch {
  mailbox_view_id?: string
  mailbox_view_template?: string
  goal_id?: string
}

export interface InboxSearch extends FocusSearch {
  sort?: MailboxSort
}

export function focusSearch(search: Record<string, unknown>): FocusSearch {
  return {
    mailbox_view_id:
      typeof search.mailbox_view_id === "string" && search.mailbox_view_id ? search.mailbox_view_id : undefined,
    mailbox_view_template:
      typeof search.mailbox_view_template === "string" && search.mailbox_view_template
        ? search.mailbox_view_template
        : undefined,
    // The parser coerces numeric-looking values, but a goal id is a UUID, so a
    // non-string here is garbage rather than something to stringify.
    goal_id: typeof search.goal_id === "string" && search.goal_id ? search.goal_id : undefined,
  }
}

// `sort` is declared on "/" only: mailbox_index was the sole handler that took the
// query param, so the other six always render newest. Note this controls the TYPE,
// not the runtime value — a match's search is its parent's plus its own, and nothing
// above validates, so an undeclared param still reaches every match. The page keys
// its sort off the route it's on for that reason.
//
// `newest` deliberately does NOT normalize out of the URL: "/?sort=newest" is the
// clear-focus action, and the persisted preference "sort=newest" is what defeats a
// stored focus (resolve_mailbox_focus collapses it to the default on read).
export function inboxSearch(search: Record<string, unknown>): InboxSearch {
  return {
    ...focusSearch(search),
    sort: search.sort === "oldest" || search.sort === "newest" ? search.sort : undefined,
  }
}

export interface MailboxFocusResponse {
  sort: MailboxSort | null
  mailbox_view_template: string | null
  goal_id: string | null
  mailbox_view_id: string | null
}

// A focus IS its inbox query params, so one function serves both directions: the
// params to redirect a bare "/" to, and the body to PATCH back. Only the params
// actually present are encoded, `sort` wins over a view/template, and null means no
// focus at all (the default focus / bare URL). Mirrors _preference_from_query in the
// deleted mailbox.py. Including a sort that validateSearch had defaulted would encode
// "sort=newest" and silently drop the view the user just picked, so callers pass the
// raw search.
export function focusParams(focus: InboxSearch | MailboxFocusResponse): InboxSearch | null {
  if (focus.sort) return { sort: focus.sort }
  if (focus.mailbox_view_template) {
    return focus.goal_id
      ? { mailbox_view_template: focus.mailbox_view_template, goal_id: focus.goal_id }
      : { mailbox_view_template: focus.mailbox_view_template }
  }
  if (focus.mailbox_view_id) return { mailbox_view_id: focus.mailbox_view_id }
  return null
}
