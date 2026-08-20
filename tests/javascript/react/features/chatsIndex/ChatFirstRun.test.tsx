import { afterEach, describe, expect, test, vi } from "vitest"

vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { ChatFirstRun } from "~/react/features/chatsIndex/components/ChatFirstRun"

import { cleanup, fireEvent, render, screen, waitFor } from "../../shared/testUtils"

afterEach(() => {
  cleanup()
})

describe("ChatFirstRun", () => {
  // Split renders: a create leaves the chips in their busy state (the real flow
  // navigates away on success), so the two paths can't share one mount.
  test("creates a group from a suggested chip", async () => {
    const onCreateGroup = vi.fn().mockResolvedValue(undefined)
    render(<ChatFirstRun onCreateGroup={onCreateGroup} onInvite={vi.fn()} />)

    fireEvent.click(screen.getByRole("button", { name: /General/ }))
    await waitFor(() => expect(onCreateGroup).toHaveBeenCalledWith("General"))
  })

  test("creates a group from a custom name", async () => {
    const onCreateGroup = vi.fn().mockResolvedValue(undefined)
    render(<ChatFirstRun onCreateGroup={onCreateGroup} onInvite={vi.fn()} />)

    // "Name your own" reveals a field that creates the typed group.
    fireEvent.click(screen.getByRole("button", { name: /Name your own/ }))
    fireEvent.change(screen.getByLabelText("Group name"), { target: { value: "Design" } })
    fireEvent.click(screen.getByRole("button", { name: "Create" }))
    await waitFor(() => expect(onCreateGroup).toHaveBeenCalledWith("Design"))
  })

  test("switches to the invite tab and submits a teammate email", async () => {
    const onInvite = vi.fn().mockResolvedValue(undefined)
    render(<ChatFirstRun onCreateGroup={vi.fn()} onInvite={onInvite} />)

    fireEvent.click(screen.getByRole("button", { name: "Invite people" }))
    const email = screen.getByLabelText("Teammate email") as HTMLInputElement
    fireEvent.change(email, { target: { value: "teammate@example.com" } })
    fireEvent.click(screen.getByRole("button", { name: "Invite" }))

    await waitFor(() => expect(onInvite).toHaveBeenCalledWith("teammate@example.com"))
    // The field clears after a successful invite.
    await waitFor(() => expect(email.value).toBe(""))
  })
})
