import { cleanup, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { DocumentRow } from "../../../../../app/javascript/react/features/documentsIndex/components/DocumentRow"
import type { DocumentListItem } from "../../../../../app/javascript/react/features/documentsIndex/types"
import { renderInDocumentsRouter } from "./harness"

function makeDocument(overrides: Partial<DocumentListItem> = {}): DocumentListItem {
  return {
    id: "doc-1",
    title: "Roadmap",
    author_display_name: "Alice",
    last_viewed_at: null,
    updated_at: "2026-04-20T09:00:00Z",
    comment_count: 0,
    sharing: "private",
    collaborator_count: 1,
    source_url: "/documents/doc-1",
    ...overrides,
  }
}

// Render the row as the index route's component so the typed <Link> has the
// router (and the /documents/$documentId route) in context.
function rowHarness(document: DocumentListItem) {
  return () => <DocumentRow document={document} returnTo="/documents" />
}

afterEach(() => cleanup())

describe("DocumentRow", () => {
  test("links to the show route with the return_to param", async () => {
    await renderInDocumentsRouter(rowHarness(makeDocument({ id: "abc" })))
    const link = screen.getByRole("link", { name: /Roadmap/ })
    const href = link.getAttribute("href") ?? ""
    expect(href).toContain("/documents/abc")
    expect(href).toContain("return_to=%2Fdocuments")
  })

  test("renders comment count badge when there are open comments", async () => {
    await renderInDocumentsRouter(rowHarness(makeDocument({ comment_count: 3 })))
    expect(screen.getAllByText("3")).toHaveLength(2)
  })

  test("hides comment count badge when there are no open comments", async () => {
    await renderInDocumentsRouter(rowHarness(makeDocument({ comment_count: 0 })))
    expect(screen.queryByText("0")).toBeNull()
  })

  test("renders the public icon for organization-shared documents", async () => {
    const { container } = await renderInDocumentsRouter(rowHarness(makeDocument({ sharing: "organization" })))
    expect(container.textContent).toContain("public")
  })

  test("hides the public icon for private documents", async () => {
    const { container } = await renderInDocumentsRouter(rowHarness(makeDocument({ sharing: "private" })))
    expect(container.textContent).not.toContain("public")
  })

  test("renders the group icon when there is more than one collaborator", async () => {
    const { container } = await renderInDocumentsRouter(rowHarness(makeDocument({ collaborator_count: 3 })))
    expect(container.textContent).toContain("group")
  })

  test("shows em-dash when last_viewed_at is null", async () => {
    await renderInDocumentsRouter(rowHarness(makeDocument({ last_viewed_at: null })))
    expect(screen.getByText("—")).toBeTruthy()
  })

  test("renders a relative-time element when last_viewed_at is present", async () => {
    const { container } = await renderInDocumentsRouter(rowHarness(makeDocument({ last_viewed_at: "2026-04-20T09:00:00Z" })))
    expect(container.querySelector("time")).toBeTruthy()
  })
})
