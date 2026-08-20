import "@testing-library/jest-dom/vitest"

import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { MailboxEntryNav } from "~/react/composites/MailboxActionBar/MailboxEntryNav"

vi.mock("~/react/shared/boostedNavigate", () => ({ boostedNavigate: vi.fn() }))

describe("MailboxEntryNav", () => {
  it("enables both arrows with hotkeys when neighbors exist", () => {
    render(
      <MailboxEntryNav
        prevHref="/posts/1?return_to=%2F"
        nextHref="/posts/3?return_to=%2F"
        loadingNext={false}
        generating={false}
        positionLabel={null}
      />
    )

    const prev = screen.getByRole("button", { name: "Previous" })
    const next = screen.getByRole("button", { name: "Next" })
    expect(prev).toBeEnabled()
    expect(next).toBeEnabled()
    expect(prev).toHaveAttribute("data-hotkey", "ArrowLeft")
    expect(next).toHaveAttribute("data-hotkey", "ArrowRight")
  })

  it("disables the end arrow and drops its hotkey", () => {
    render(
      <MailboxEntryNav
        prevHref={null}
        nextHref="/posts/2?return_to=%2F"
        loadingNext={false}
        generating={false}
        positionLabel={null}
      />
    )

    const prev = screen.getByRole("button", { name: "Previous" })
    expect(prev).toBeDisabled()
    expect(prev).not.toHaveAttribute("data-hotkey")
  })

  it("shows a spinner on the next arrow while a boundary page loads", () => {
    const { container } = render(
      <MailboxEntryNav
        prevHref="/posts/1?return_to=%2F"
        nextHref={null}
        loadingNext
        generating={false}
        positionLabel={null}
      />
    )
    expect(container.querySelector(".loading")).not.toBeNull()
  })

  it("shows the section title with the position disclosed via hover for a grouped view", () => {
    render(
      <MailboxEntryNav
        prevHref="/posts/1?return_to=%2F%3Fmailbox_view_id%3Dv1"
        nextHref="/posts/3?return_to=%2F%3Fmailbox_view_id%3Dv1"
        loadingNext={false}
        generating={false}
        positionLabel={{ name: "Blockers", position: 2, total: 3 }}
      />
    )
    // The section title shows inline; the exact position rides on the accessible label.
    expect(screen.getByText("Blockers")).toBeInTheDocument()
    expect(screen.getByLabelText("Blockers · 2 of 3")).toBeInTheDocument()
  })

  it("shows the sort's name for a ranked custom sort", () => {
    render(
      <MailboxEntryNav
        prevHref="/posts/1?return_to=%2F%3Fmailbox_view_template%3Dpriority"
        nextHref={null}
        loadingNext={false}
        generating={false}
        positionLabel={{ name: "By priority", position: 5, total: 40 }}
      />
    )
    expect(screen.getByText("By priority")).toBeInTheDocument()
    expect(screen.getByLabelText("By priority · 5 of 40")).toBeInTheDocument()
  })

  it("fills the whole pill background to the position within the section", () => {
    const { container } = render(
      <MailboxEntryNav
        prevHref="/posts/1?return_to=%2F%3Fmailbox_view_id%3Dv1"
        nextHref="/posts/3?return_to=%2F%3Fmailbox_view_id%3Dv1"
        loadingNext={false}
        generating={false}
        positionLabel={{ name: "Blockers", position: 3, total: 4 }}
      />
    )
    // The fill is a sibling of the arrows spanning the cluster, not nested in the label.
    const fill = container.querySelector("[aria-hidden]") as HTMLElement
    expect(fill).toHaveStyle({ width: "75%" })
    expect(screen.getByLabelText("Blockers · 3 of 4").contains(fill)).toBe(false)
  })

  it("shows no progress fill while generating", () => {
    const { container } = render(
      <MailboxEntryNav
        prevHref="/posts/1?return_to=%2F%3Fmailbox_view_id%3Dv1"
        nextHref="/posts/3?return_to=%2F%3Fmailbox_view_id%3Dv1"
        loadingNext={false}
        generating
        positionLabel={{ name: "Blockers", position: 3, total: 4 }}
      />
    )
    expect(container.querySelector("[aria-hidden]")).toBeNull()
  })

  it("disables both arrows and shows Organizing… while generating", () => {
    render(
      <MailboxEntryNav
        prevHref="/posts/1?return_to=%2F%3Fmailbox_view_id%3Dv1"
        nextHref="/posts/3?return_to=%2F%3Fmailbox_view_id%3Dv1"
        loadingNext={false}
        generating
        positionLabel={null}
      />
    )
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled()
    expect(screen.getByText("Organizing…")).toBeInTheDocument()
  })
})
