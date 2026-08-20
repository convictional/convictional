import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: Record<string, unknown> | null
    constructor(status: number, body: Record<string, unknown> | null = null) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = body
    }
  },
}))

vi.mock("../../../../../app/javascript/react/composites/confirmationDialog/confirm", () => ({
  confirm: vi.fn(),
}))

import { ApiError, apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { confirm } from "../../../../../app/javascript/react/composites/confirmationDialog/confirm"
import { BackgroundJobs } from "../../../../../app/javascript/react/features/backgroundJobs/BackgroundJobs"
import { toastStore } from "../../../../../app/javascript/react/shared/stores/toast"

const mockApiFetch = vi.mocked(apiFetch)
const mockConfirm = vi.mocked(confirm)

const JOB_TYPES_RESPONSE = {
  job_types: [
    {
      job_type: "reindex_search",
      name: "ReindexSearchJob",
      queue: "indexing",
      args_schema: {
        properties: { workspace_id: { type: "string" }, queue: { type: "string" } },
        required: ["workspace_id"],
      },
    },
    {
      job_type: "cleanup_orphans",
      name: "CleanupOrphansJob",
      queue: "maintenance",
      args_schema: { properties: {}, required: [] },
    },
  ],
  next_cursor: null,
  has_more: false,
}

async function renderAndLoad() {
  mockApiFetch.mockResolvedValueOnce(JOB_TYPES_RESPONSE)
  render(<BackgroundJobs userId="42" organizationId="7" />)
  await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/background_job_types"))
  await screen.findByRole("button", { name: /select a job type/i })
}

// Open the searchable picker and click the option carrying this snake_case key
// (unique to the option row — the trigger only shows the human name).
async function selectJob(jobTypeKey: string) {
  fireEvent.click(screen.getByRole("button", { name: /select a job type/i }))
  fireEvent.click(await screen.findByText(jobTypeKey))
}

function textarea() {
  return screen.getByRole("textbox") as HTMLTextAreaElement
}

function enqueue() {
  fireEvent.click(screen.getByRole("button", { name: /enqueue job/i }))
}

describe("BackgroundJobs", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    mockConfirm.mockReset()
    toastStore.setState({ toasts: [] })
  })
  afterEach(cleanup)

  test("shows a loading state, then fetches job types and renders the debug IDs", async () => {
    await renderAndLoad()
    fireEvent.click(screen.getByRole("button", { name: /select a job type/i }))
    expect(await screen.findByText("ReindexSearchJob")).toBeInTheDocument()
    expect(screen.getByText("CleanupOrphansJob")).toBeInTheDocument()
    expect(screen.getByText("42")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
  })

  test("a failed load renders the error state and never shows the form", async () => {
    mockApiFetch.mockRejectedValueOnce(new ApiError(500, null))
    render(<BackgroundJobs userId="42" organizationId="7" />)
    expect(await screen.findByText(/couldn't load the job types/i)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /enqueue job/i })).not.toBeInTheDocument()
  })

  test("selecting a job fills the textarea with its required-field template and shows the fields reference", async () => {
    await renderAndLoad()
    await selectJob("reindex_search")
    expect(JSON.parse(textarea().value)).toEqual({ workspace_id: "" })
    // The reference panel lists the required field (and not the base `queue` field).
    expect(await screen.findByText("Fields")).toBeInTheDocument()
    expect(screen.getByText("required")).toBeInTheDocument()
    // The job's default queue is surfaced.
    expect(screen.getByText("indexing")).toBeInTheDocument()
  })

  test("invalid JSON shows an inline error and never calls the API or confirm", async () => {
    await renderAndLoad()
    await selectJob("reindex_search")
    fireEvent.change(textarea(), { target: { value: "{ not json" } })
    enqueue()

    expect(await screen.findByText(/invalid JSON/i)).toBeInTheDocument()
    expect(mockConfirm).not.toHaveBeenCalled()
    expect(mockApiFetch).toHaveBeenCalledTimes(1) // only the initial GET
  })

  test("non-object JSON (array/scalar) is rejected before confirm or POST", async () => {
    await renderAndLoad()
    await selectJob("reindex_search")
    fireEvent.change(textarea(), { target: { value: "[1, 2, 3]" } })
    enqueue()

    expect(await screen.findByText(/must be a JSON object/i)).toBeInTheDocument()
    expect(mockConfirm).not.toHaveBeenCalled()
    expect(mockApiFetch).toHaveBeenCalledTimes(1) // only the initial GET
  })

  test("cancelling the confirm dialog aborts the POST", async () => {
    await renderAndLoad()
    mockConfirm.mockResolvedValueOnce(false)
    await selectJob("cleanup_orphans")
    enqueue()

    await waitFor(() => expect(mockConfirm).toHaveBeenCalledTimes(1))
    expect(mockConfirm.mock.calls[0][0]).toMatchObject({ title: "Enqueue CleanupOrphansJob?" })
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })

  test("a successful enqueue posts, shows a success toast, and resets the arguments", async () => {
    await renderAndLoad()
    mockConfirm.mockResolvedValueOnce(true)
    mockApiFetch.mockResolvedValueOnce({ job_id: "job-1", job_type: "cleanup_orphans" })
    await selectJob("cleanup_orphans")
    enqueue()

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))
    const [url, options] = mockApiFetch.mock.calls[1]
    expect(url).toBe("/api/background_jobs")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(options?.body as string)).toEqual({ job_type: "cleanup_orphans", arguments: {} })

    await waitFor(() => expect(toastStore.getState().toasts).toHaveLength(1))
    expect(toastStore.getState().toasts[0]).toMatchObject({ message: "Job enqueued successfully", level: "success" })
    expect(textarea().value).toBe("{}")
  })

  test("a rapid second click during the confirm dialog does not enqueue twice", async () => {
    await renderAndLoad()
    // Hold the confirm dialog open so a second click lands while the first is
    // still awaiting confirmation.
    let resolveConfirm!: (value: boolean) => void
    mockConfirm.mockReturnValueOnce(new Promise<boolean>(resolve => (resolveConfirm = resolve)))
    mockApiFetch.mockResolvedValueOnce({ job_id: "job-1", job_type: "cleanup_orphans" })
    await selectJob("cleanup_orphans")

    enqueue()
    enqueue() // ignored — the first submit already claimed the in-flight guard
    await waitFor(() => expect(mockConfirm).toHaveBeenCalledTimes(1))

    resolveConfirm(true)
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2)) // initial GET + exactly one POST
    expect(mockConfirm).toHaveBeenCalledTimes(1)
  })

  test("a 422 renders one field error per detail entry, stripping the body.arguments prefix", async () => {
    await renderAndLoad()
    mockConfirm.mockResolvedValueOnce(true)
    mockApiFetch.mockRejectedValueOnce(
      new ApiError(422, {
        detail: [
          { loc: ["body", "arguments", "workspace_id"], msg: "Field required" },
          { loc: ["body", "arguments", "limit"], msg: "value is not a valid integer" },
        ],
      })
    )
    await selectJob("reindex_search")
    enqueue()

    expect(await screen.findByText("workspace_id: Field required")).toBeInTheDocument()
    expect(screen.getByText("limit: value is not a valid integer")).toBeInTheDocument()
    expect(toastStore.getState().toasts).toHaveLength(0)
  })

  test("a non-422 failure shows a generic error", async () => {
    await renderAndLoad()
    mockConfirm.mockResolvedValueOnce(true)
    mockApiFetch.mockRejectedValueOnce(new ApiError(403, null))
    await selectJob("cleanup_orphans")
    enqueue()

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
