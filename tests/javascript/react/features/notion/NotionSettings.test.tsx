import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})
vi.mock("~/react/composites/confirmationDialog/confirm", () => ({ confirm: vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { showFlash } from "~/shared/flash"
import { NotionSettings } from "~/react/features/notion/NotionSettings"
import type {
  NotionNode,
  NotionNodeListResponse,
  NotionSelectionStateResponse,
  NotionStatus,
} from "~/react/features/notion/types"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"

const mockedFetch = vi.mocked(apiFetch)
const mockedConfirm = vi.mocked(confirm)
const mockedShowFlash = vi.mocked(showFlash)

function status(overrides: Partial<NotionStatus> = {}): NotionStatus {
  return { is_connected: true, workspace_name: "Acme HQ", last_synced_at: null, ...overrides }
}

// Factory for a server tree node. Defaults to a childless leaf page; pass kind:
// "database" + has_children for a folder, and the count fields to drive the
// folder's checked state.
function treeNode(overrides: Partial<NotionNode> = {}): NotionNode {
  return {
    notion_node_id: "node-1",
    kind: "page",
    title: "Planning Doc",
    parent_id: null,
    parent_kind: null,
    has_children: false,
    url: null,
    last_edited_time: null,
    is_selected_for_sync: false,
    is_imported: false,
    document_id: null,
    selected_descendant_count: 0,
    total_descendant_count: 0,
    counts_authoritative: false,
    ...overrides,
  }
}

function nodeList(nodes: NotionNode[], extra: Partial<NotionNodeListResponse> = {}): NotionNodeListResponse {
  return { nodes, next_cursor: null, has_more: false, ...extra }
}

function selectionState(overrides: Partial<NotionSelectionStateResponse> = {}): NotionSelectionStateResponse {
  return { state: "done", node: null, ...overrides }
}

beforeEach(() => {
  mockedFetch.mockReset()
  mockedConfirm.mockReset()
  mockedShowFlash.mockReset()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("NotionSettings", () => {
  test("disconnected → renders connect form and submits the token", async () => {
    mockedFetch.mockResolvedValueOnce(status({ is_connected: false, workspace_name: null })) // initial GET
    mockedFetch.mockResolvedValueOnce({ is_connected: true, workspace_name: "Acme HQ" }) // POST connection
    mockedFetch.mockResolvedValueOnce(nodeList([])) // tree load after connect

    render(<NotionSettings />)

    const input = await screen.findByLabelText("Notion integration token")
    fireEvent.change(input, { target: { value: "secret_token" } })
    fireEvent.click(screen.getByRole("button", { name: "Connect Notion" }))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/integrations/notion/connection",
        expect.objectContaining({ method: "POST", body: JSON.stringify({ access_token: "secret_token" }) }),
        expect.anything()
      )
    })
    expect(await screen.findByRole("button", { name: "Sync now" })).toBeInTheDocument()
  })

  test("connected → renders workspace, sync controls, and the tree", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(nodeList([treeNode({ title: "Planning Doc" })]))

    render(<NotionSettings />)

    expect(await screen.findByText("Planning Doc")).toBeInTheDocument()
    // The connection status is read from GET /connection (not the bare /notion path).
    expect(mockedFetch).toHaveBeenCalledWith("/api/integrations/notion/connection")
    expect(screen.getByText("Acme HQ")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument()
    expect(screen.getByRole("tree")).toBeInTheDocument()
  })

  test("expand fetches a folder's children once, and re-expand reuses the cache", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "folder", kind: "database", title: "My DB", has_children: true })])
    )
    // Children of the folder, fetched on first expand.
    mockedFetch.mockResolvedValueOnce(nodeList([treeNode({ notion_node_id: "child", title: "Inner Page" })]))

    render(<NotionSettings />)
    await screen.findByText("My DB")

    fireEvent.click(screen.getByRole("button", { name: "Expand" }))
    expect(await screen.findByText("Inner Page")).toBeInTheDocument()

    const childFetches = () =>
      mockedFetch.mock.calls.filter(c => String(c[0]).includes("/nodes/folder/children")).length
    expect(childFetches()).toBe(1)
    // The folder's kind rides along so the server walks an unpersisted top-tier database correctly.
    expect(
      mockedFetch.mock.calls.some(
        c => String(c[0]).includes("/nodes/folder/children") && String(c[0]).includes("kind=database")
      )
    ).toBe(true)

    // Collapse, then re-expand: no new fetch (children cached).
    fireEvent.click(screen.getByRole("button", { name: "Collapse" }))
    expect(screen.queryByText("Inner Page")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Expand" }))
    expect(await screen.findByText("Inner Page")).toBeInTheDocument()
    expect(childFetches()).toBe(1)
  })

  test("folder with partial selection renders an unchecked checkbox", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([
        treeNode({
          notion_node_id: "folder",
          kind: "database",
          title: "Mixed DB",
          has_children: true,
          counts_authoritative: true,
          selected_descendant_count: 2,
          total_descendant_count: 5,
        }),
      ])
    )

    render(<NotionSettings />)
    await screen.findByText("Mixed DB")

    const checkbox = screen.getByRole("checkbox", { name: "Select Mixed DB" }) as HTMLInputElement
    expect(checkbox.checked).toBe(false)
    expect(checkbox.indeterminate).toBe(false)
    expect(checkbox.getAttribute("aria-checked")).not.toBe("mixed")
  })

  test("folder with non-authoritative counts renders an unchecked checkbox", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([
        treeNode({
          notion_node_id: "folder",
          kind: "database",
          title: "Unknown DB",
          has_children: true,
          counts_authoritative: false,
          selected_descendant_count: 0,
          total_descendant_count: 0,
        }),
      ])
    )

    render(<NotionSettings />)
    await screen.findByText("Unknown DB")

    const checkbox = screen.getByRole("checkbox", { name: "Select Unknown DB" }) as HTMLInputElement
    expect(checkbox.checked).toBe(false)
    expect(checkbox.indeterminate).toBe(false)
    expect(checkbox.getAttribute("aria-checked")).not.toBe("mixed")
  })

  test("a leaf toggle is optimistic and PATCHes the page selection", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(nodeList([treeNode({ notion_node_id: "page-1" })]))
    mockedFetch.mockResolvedValueOnce(treeNode({ notion_node_id: "page-1", is_selected_for_sync: true })) // PATCH

    render(<NotionSettings />)
    const checkbox = (await screen.findByRole("checkbox")) as HTMLInputElement
    expect(checkbox.checked).toBe(false)

    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(true) // optimistic

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/integrations/notion/pages/page-1",
        expect.objectContaining({ method: "PATCH" })
      )
    })
    expect(checkbox.checked).toBe(true)
  })

  test("a leaf toggle rolls back when the PATCH fails", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(nodeList([treeNode({ notion_node_id: "page-1" })]))
    mockedFetch.mockRejectedValueOnce(new ApiError(502, null)) // PATCH fails

    render(<NotionSettings />)
    const checkbox = (await screen.findByRole("checkbox")) as HTMLInputElement

    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(true) // optimistic
    await waitFor(() => expect(checkbox.checked).toBe(false)) // rolled back
  })

  test("selecting a folder flips its loaded leaves, then reconciles counts from the poll", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([
        treeNode({
          notion_node_id: "folder",
          kind: "database",
          title: "Cascade DB",
          has_children: true,
          counts_authoritative: false,
        }),
      ])
    )
    // Expand → one leaf child, unselected.
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "leaf", title: "Leaf Page", is_selected_for_sync: false })])
    )
    // PATCH /selection → 202 echo.
    mockedFetch.mockResolvedValueOnce({
      notion_node_id: "folder",
      kind: "database",
      selected_for_sync: true,
      selected_descendant_count: 0,
      total_descendant_count: 1,
      counts_authoritative: false,
    })
    // Poll → done, authoritative counts.
    mockedFetch.mockResolvedValueOnce(
      selectionState({
        state: "done",
        node: {
          notion_node_id: "folder",
          selected_descendant_count: 1,
          total_descendant_count: 1,
          counts_authoritative: true,
        },
      })
    )
    // Re-fetch of children after the cascade finishes (leaf now selected).
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "leaf", title: "Leaf Page", is_selected_for_sync: true })])
    )

    render(<NotionSettings />)
    await screen.findByText("Cascade DB")
    fireEvent.click(screen.getByRole("button", { name: "Expand" }))
    const leafCheckbox = (await screen.findByRole("checkbox", { name: "Select Leaf Page" })) as HTMLInputElement
    expect(leafCheckbox.checked).toBe(false)

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Cascade DB" }))
    // Optimistic: the loaded leaf flips immediately.
    await waitFor(() => expect(leafCheckbox.checked).toBe(true))

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/integrations/notion/nodes/folder/selection",
        expect.objectContaining({ method: "PATCH" }),
        expect.anything()
      )
    })

    // The cascade is reconciled by polling GET /nodes/{id}/selection.
    await waitFor(
      () => {
        expect(mockedFetch).toHaveBeenCalledWith(
          "/api/integrations/notion/nodes/folder/selection",
          expect.objectContaining({ signal: expect.anything() })
        )
      },
      { timeout: 4000 }
    )

    // Poll resolves → folder reads checked (all descendants selected).
    await waitFor(
      () => {
        const folderCheckbox = screen.getByRole("checkbox", { name: "Select Cascade DB" }) as HTMLInputElement
        expect(folderCheckbox.checked).toBe(true)
      },
      { timeout: 4000 }
    )
  })

  test("de-selecting a parent keeps a nested folder unchecked", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockedFetch.mockResolvedValueOnce(status())
    // Top: a fully-selected, authoritative parent → starts checked.
    mockedFetch.mockResolvedValueOnce(
      nodeList([
        treeNode({
          notion_node_id: "parent",
          kind: "database",
          title: "Parent DB",
          has_children: true,
          counts_authoritative: true,
          selected_descendant_count: 1,
          total_descendant_count: 1,
        }),
      ])
    )
    // Expand → a nested folder whose own counts are NOT authoritative, so it reads unchecked.
    mockedFetch.mockResolvedValueOnce(
      nodeList([
        treeNode({
          notion_node_id: "subfolder",
          kind: "database",
          title: "Subfolder",
          parent_id: "parent",
          has_children: true,
          counts_authoritative: false,
          selected_descendant_count: 1,
          total_descendant_count: 1,
        }),
      ])
    )
    mockedFetch.mockResolvedValueOnce({
      notion_node_id: "parent",
      kind: "database",
      selected_for_sync: false,
      selected_descendant_count: 0,
      total_descendant_count: 1,
      counts_authoritative: true,
    })
    mockedFetch.mockResolvedValueOnce(
      selectionState({
        state: "done",
        node: {
          notion_node_id: "parent",
          selected_descendant_count: 0,
          total_descendant_count: 1,
          counts_authoritative: true,
        },
      })
    )
    mockedFetch.mockResolvedValueOnce(
      nodeList([
        treeNode({
          notion_node_id: "subfolder",
          kind: "database",
          title: "Subfolder",
          parent_id: "parent",
          has_children: true,
          counts_authoritative: true,
          selected_descendant_count: 0,
          total_descendant_count: 1,
        }),
      ])
    )

    render(<NotionSettings />)
    await screen.findByText("Parent DB")
    fireEvent.click(screen.getByRole("button", { name: "Expand" }))
    const subCheckbox = (await screen.findByRole("checkbox", { name: "Select Subfolder" })) as HTMLInputElement
    // A non-authoritative nested folder reads unchecked (we can't claim all descendants selected).
    await waitFor(() => expect(subCheckbox.checked).toBe(false))

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Parent DB" }))
    // Optimistic flip claims authority across the subtree, so the nested folder resolves to a
    // definite unchecked state immediately.
    await waitFor(() => expect(subCheckbox.checked).toBe(false))
  })

  test("a folder cascade rolls back the optimistic flip when the job fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "folder", kind: "database", title: "Doomed DB", has_children: true })])
    )
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "leaf", title: "Leaf Page", is_selected_for_sync: false })])
    )
    mockedFetch.mockResolvedValueOnce({
      notion_node_id: "folder",
      kind: "database",
      selected_for_sync: true,
      selected_descendant_count: 0,
      total_descendant_count: 1,
      counts_authoritative: false,
    })
    mockedFetch.mockResolvedValueOnce(selectionState({ state: "failed", node: null }))

    render(<NotionSettings />)
    await screen.findByText("Doomed DB")
    fireEvent.click(screen.getByRole("button", { name: "Expand" }))
    const leafCheckbox = (await screen.findByRole("checkbox", { name: "Select Leaf Page" })) as HTMLInputElement

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Doomed DB" }))
    await waitFor(() => expect(leafCheckbox.checked).toBe(true)) // optimistic

    // Poll says failed → leaf rolls back to unselected.
    await waitFor(() => expect(leafCheckbox.checked).toBe(false), { timeout: 4000 })
  })

  test("the Sync button is disabled while a folder cascade is pending", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "folder", kind: "database", title: "Pending DB", has_children: true })])
    )
    mockedFetch.mockResolvedValueOnce({
      notion_node_id: "folder",
      kind: "database",
      selected_for_sync: true,
      selected_descendant_count: 0,
      total_descendant_count: 0,
      counts_authoritative: false,
    })
    // Poll stays pending for a while.
    mockedFetch.mockResolvedValue(selectionState({ state: "pending", node: null }))

    render(<NotionSettings />)
    await screen.findByText("Pending DB")
    const syncButton = screen.getByRole("button", { name: "Sync now" }) as HTMLButtonElement
    expect(syncButton.disabled).toBe(false)

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Pending DB" }))
    await waitFor(() => expect(syncButton.disabled).toBe(true))
  })

  test("a cascade that never resolves stops polling at the cap, re-enables Sync, and flashes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "folder", kind: "database", title: "Stuck DB", has_children: true })])
    )
    mockedFetch.mockResolvedValueOnce({
      notion_node_id: "folder",
      kind: "database",
      selected_for_sync: true,
      selected_descendant_count: 0,
      total_descendant_count: 0,
      counts_authoritative: false,
    })
    // The job is wedged: every poll comes back non-terminal forever.
    mockedFetch.mockResolvedValue(selectionState({ state: "running", node: null }))

    render(<NotionSettings />)
    await screen.findByText("Stuck DB")
    const syncButton = screen.getByRole("button", { name: "Sync now" }) as HTMLButtonElement

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Stuck DB" }))
    await waitFor(() => expect(syncButton.disabled).toBe(true))

    // 60 polls × 1500ms = the 90s cap. Drive the loop to (just past) it.
    await vi.advanceTimersByTimeAsync(60 * 1500)

    // The button is freed and the user is told it's still finishing in the background.
    await waitFor(() => expect(syncButton.disabled).toBe(false))
    expect(mockedShowFlash).toHaveBeenCalledWith(
      "Notion is still finishing that update in the background. Refresh to confirm.",
      "success"
    )

    // And polling has actually stopped — further time advances trigger no new polls.
    const pollCount = () =>
      mockedFetch.mock.calls.filter(
        ([url, opts]) =>
          url === "/api/integrations/notion/nodes/folder/selection" && opts != null && !("method" in opts)
      ).length
    expect(pollCount()).toBe(60)
    await vi.advanceTimersByTimeAsync(30 * 1500)
    expect(pollCount()).toBe(60)
  })

  test("a per-node child-fetch error shows a retry that re-fetches", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "folder", kind: "database", title: "Flaky DB", has_children: true })])
    )
    mockedFetch.mockRejectedValueOnce(new ApiError(502, null)) // children fetch fails
    mockedFetch.mockResolvedValueOnce(nodeList([treeNode({ notion_node_id: "child", title: "Recovered Page" })])) // retry

    render(<NotionSettings />)
    await screen.findByText("Flaky DB")
    fireEvent.click(screen.getByRole("button", { name: "Expand" }))

    const retry = await screen.findByRole("button", { name: "Retry" })
    fireEvent.click(retry)
    expect(await screen.findByText("Recovered Page")).toBeInTheDocument()
  })

  test("an imported leaf links to its Convictional document", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ is_imported: true, is_selected_for_sync: true, document_id: "doc-123" })])
    )

    render(<NotionSettings />)
    const link = (await screen.findByRole("link", { name: /Open document/ })) as HTMLAnchorElement
    expect(link.getAttribute("href")).toContain("/documents/doc-123/edit")
  })

  test("Load more fetches the next top-tier page with the cursor and appends rows", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(
      nodeList([treeNode({ notion_node_id: "a", title: "Alpha" })], { next_cursor: "cur-2", has_more: true })
    )
    mockedFetch.mockResolvedValueOnce(nodeList([treeNode({ notion_node_id: "b", title: "Beta" })]))

    render(<NotionSettings />)
    expect(await screen.findByText("Alpha")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Load more" }))
    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/integrations/notion/nodes?cursor=cur-2",
        expect.anything(),
        expect.anything()
      )
    })
    expect(await screen.findByText("Beta")).toBeInTheDocument()
    expect(screen.getByText("Alpha")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull()
  })

  test("empty top tier renders the empty state", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(nodeList([]))

    render(<NotionSettings />)
    expect(await screen.findByText("No pages visible")).toBeInTheDocument()
  })

  test("disconnect confirms, removes the connection, clears the tree, and returns to the connect form", async () => {
    mockedFetch.mockResolvedValueOnce(status())
    mockedFetch.mockResolvedValueOnce(nodeList([treeNode({ title: "Secret Page" })]))
    mockedConfirm.mockResolvedValueOnce(true)
    mockedFetch.mockResolvedValueOnce(undefined) // DELETE (204)
    mockedFetch.mockResolvedValueOnce(status({ is_connected: false, workspace_name: null })) // follow-up GET

    render(<NotionSettings />)
    expect(await screen.findByText("Secret Page")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }))
    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/integrations/notion/connection",
        expect.objectContaining({ method: "DELETE" })
      )
    })

    expect(await screen.findByLabelText("Notion integration token")).toBeInTheDocument()
    expect(screen.queryByText("Secret Page")).toBeNull()
    expect(screen.queryByRole("tree")).toBeNull()
  })
})
