import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { CollectionPicker } from "~/react/composites/meetings/CollectionPicker"

import { makeCollection, makeCollectionListResponse } from "../../shared/meetingsFixtures"

const mockApiFetch = vi.mocked(apiFetch)

function calledUrl(callIndex: number): URL {
  return new URL(mockApiFetch.mock.calls[callIndex][0] as string, "http://test.local")
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(cleanup)

describe("CollectionPicker", () => {
  test("drains every page of collections via the shared helper when opened", async () => {
    // Two pages — the second is only reachable if the picker exhausts pagination
    // (it reuses shared/collections.fetchAllCollections rather than its own loop).
    mockApiFetch
      .mockResolvedValueOnce(
        makeCollectionListResponse([makeCollection({ id: "a", title: "Alpha" })], {
          next_cursor: "cursor-1",
          has_more: true,
        })
      )
      .mockResolvedValueOnce(makeCollectionListResponse([makeCollection({ id: "b", title: "Beta" })]))

    render(<CollectionPicker meetingId="m1" collection={null} onMeetingUpdated={vi.fn()} />)

    fireEvent.click(screen.getByRole("button", { name: /No collection/ }))

    // The page-2 collection appears, proving the drain.
    expect(await screen.findByText("Beta")).toBeInTheDocument()
    expect(screen.getByText("Alpha")).toBeInTheDocument()

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))
    expect(calledUrl(0).pathname).toBe("/api/meetings_collections")
    expect(calledUrl(0).search).toBe("")
    expect(calledUrl(1).searchParams.get("cursor")).toBe("cursor-1")
  })
})
