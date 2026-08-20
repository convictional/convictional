import { QueryClientProvider } from "@tanstack/react-query"
import { render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { PostCommentComposer } from "~/react/features/postShow/components/PostCommentComposer"
import { queryClient } from "~/react/shared/queryClient"
import { currentUserQueryKey } from "~/react/shared/stores/currentUser"
import { organizationMembersQueryOptions } from "~/react/shared/stores/organizationMembers"

// PostCommentComposer routes its ⌘↵-to-submit through the shared useEnterToSend
// hook (requireModifier: true, so plain Enter inserts a newline). The reported
// bug: on a published post the keystroke bubbled past the composer and
// published/acted on the surrounding resource. The hook must claim the keystroke
// (preventDefault) and stop it from reaching any ancestor keydown handler.

function seedStores() {
  queryClient.setQueryData(currentUserQueryKey, {
    user: {
      id: "u1",
      display_name: "Test User",
      email: "t@example.com",
      is_superuser: false,
      picture: null,
      is_admin: false,
      onboarding_incomplete: false,
      organization_id: "o1",
      organization_name: "Org",
      time_zone: null,
      feedback_upload_url: "",
    },
    clientConfig: { klipy_api_key: null },
  })
  queryClient.setQueryData(organizationMembersQueryOptions.queryKey, { users: [], groups: [] })
}

afterEach(() => {
  queryClient.clear()
})

describe("PostCommentComposer hotkey submit", () => {
  it("claims ⌘↵ and stops it from reaching an ancestor handler", () => {
    seedStores()
    const onSubmit = vi.fn().mockResolvedValue({})
    const ancestorSpy = vi.fn()
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <div onKeyDown={ancestorSpy}>
          <PostCommentComposer uploadUrl="/upload" onSubmit={onSubmit} autoFocus />
        </div>
      </QueryClientProvider>
    )
    const editable = container.querySelector<HTMLElement>(".ProseMirror")
    if (!editable) throw new Error("editor did not mount")

    const event = new KeyboardEvent("keydown", { key: "Enter", metaKey: true, bubbles: true, cancelable: true })
    editable.dispatchEvent(event)

    // The composer's own handler ran (preventDefault) and stopped the keystroke
    // (stopPropagation) — so the surrounding resource's ⌘↵ handler never fires.
    expect(event.defaultPrevented).toBe(true)
    expect(ancestorSpy).not.toHaveBeenCalled()
  })

  // A plain key with no modifier is not a submit and must fall through as normal
  // editing, so the stopPropagation is scoped to the actual hotkey submit.
  it("does not claim or stop a plain keystroke", () => {
    seedStores()
    const onSubmit = vi.fn().mockResolvedValue({})
    const ancestorSpy = vi.fn()
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <div onKeyDown={ancestorSpy}>
          <PostCommentComposer uploadUrl="/upload" onSubmit={onSubmit} autoFocus />
        </div>
      </QueryClientProvider>
    )
    const editable = container.querySelector<HTMLElement>(".ProseMirror")
    if (!editable) throw new Error("editor did not mount")

    const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })
    editable.dispatchEvent(event)

    expect(ancestorSpy).toHaveBeenCalledOnce()
  })
})
