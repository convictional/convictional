import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { shellRoute } from "../shellRoute"
import { backAndMailboxSearch } from "./mailboxEntryHelpers"

// The collaborative draft editor. The draft title, the re-sourced props (upload
// URL, current user, klipy key, mailbox entry), and the published→show redirect
// are all handled in the component, since none is known until the draft query
// resolves (see PostDraftEditor). Channels derive from the post_id route param
// alone, so the route passes no props.
const PostDraftEditorView = lazyRouteComponent(
  () => import("~/react/features/postDraftEditor/PostDraftEditor"),
  "PostDraftEditor"
)

// `return_to` carries the "back" target (the index, the inbox, a gid redirect
// source); `mailbox_entry_id` scopes the header's mailbox variant when the draft
// was opened from the inbox. Mirrors postShow.
export const postDraftEditorRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/posts/$postId/edit",
  // The editor's comment gutter is positioned beyond the content column; clip the
  // shell #container's horizontal overflow so it doesn't induce page-level scroll
  // (was `<style>#container{overflow-x:clip}</style>` in the old edit template).
  staticData: { clipContainerOverflowX: true },
  validateSearch: backAndMailboxSearch,
  component: PostDraftEditorView,
})
