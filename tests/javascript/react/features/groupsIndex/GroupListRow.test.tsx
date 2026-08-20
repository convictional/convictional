import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"

import { GroupListRow } from "~/react/features/groupsIndex/components/GroupListRow"
import { makeGroup } from "./factories"

function defaultProps() {
  return {
    canManage: true,
    canJoin: true,
    onJoin: vi.fn(),
    onLeave: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
  }
}

describe("GroupListRow", () => {
  test("renders the name and a Join action for non-members", () => {
    const props = defaultProps()
    render(<GroupListRow group={makeGroup({ is_member: false })} {...props} />)

    expect(screen.getByText("Engineering")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Join" }))
    expect(props.onJoin).toHaveBeenCalledWith("group-1")
  })

  test("members get a Leave action", () => {
    const props = defaultProps()
    render(<GroupListRow group={makeGroup({ is_member: true })} {...props} />)
    fireEvent.click(screen.getByRole("button", { name: "Leave" }))
    expect(props.onLeave).toHaveBeenCalledWith("group-1")
  })

  test("inline rename is admin-only", () => {
    const props = defaultProps()
    render(<GroupListRow group={makeGroup()} {...props} canManage={false} />)
    expect(screen.queryByRole("button", { name: "Group actions" })).not.toBeInTheDocument()
  })
})
