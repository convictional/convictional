import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import type { LinkPreview } from "~/react/shared/types"

afterEach(cleanup)

const BASE: LinkPreview = {
  url: "https://example.com/article",
  type: "link",
  title: "An article",
  description: null,
  image_url: null,
  site_name: null,
  domain: "example.com",
}

describe("LinkPreviewCard", () => {
  test("renders a native icon + label and an in-app link for internal previews", () => {
    const preview: LinkPreview = {
      ...BASE,
      url: "https://app.convictional.test/goals#goal-abc",
      title: "Quarterly OKRs",
      domain: "app.convictional.test",
      resource_kind: "goal",
    }
    render(<LinkPreviewCard linkPreview={preview} />)

    // Material Symbol for a goal + its human label, in place of the domain footer.
    expect(screen.getByText("target")).toBeInTheDocument()
    expect(screen.getByText("Goal")).toBeInTheDocument()
    expect(screen.queryByText("app.convictional.test")).not.toBeInTheDocument()

    // Without a router context the card navigates in-tab (no new tab) to a relative path.
    const link = screen.getByRole("link")
    expect(link.getAttribute("href")).toBe("/goals#goal-abc")
    expect(link.getAttribute("target")).toBeNull()
  })

  test("renders the domain footer and opens external previews in a new tab", () => {
    render(<LinkPreviewCard linkPreview={BASE} />)

    expect(screen.getByText("example.com")).toBeInTheDocument()

    const link = screen.getByRole("link")
    expect(link.getAttribute("href")).toBe("https://example.com/article")
    expect(link.getAttribute("target")).toBe("_blank")
  })

  test("renders a branded favicon fallback when there is no image", () => {
    const preview: LinkPreview = { ...BASE, title: null, description: null, image_url: null }
    const { container } = render(<LinkPreviewCard linkPreview={preview} />)

    // A blocked/metadata-less link still renders a card: the site favicon + domain.
    expect(screen.getByText("example.com")).toBeInTheDocument()
    const favicon = container.querySelector("img")
    expect(favicon?.getAttribute("src")).toContain("s2/favicons")
    expect(favicon?.getAttribute("src")).toContain("example.com")
  })

  test("renders a file card for a pasted attachment link", () => {
    const preview: LinkPreview = {
      ...BASE,
      url: "https://app.convictional.test/workspaces/attachments/abc/download",
      title: "report.pdf",
      domain: "app.convictional.test",
      resource_kind: "file",
      file: { file_name: "report.pdf", content_type: "application/pdf", byte_size: 2048 },
    }
    render(<LinkPreviewCard linkPreview={preview} />)

    expect(screen.getByText("report.pdf")).toBeInTheDocument()
    expect(screen.getByText("2 KB")).toBeInTheDocument()
    // PDF icon, and a real download link in a new tab (not in-app navigation).
    expect(screen.getByText("picture_as_pdf")).toBeInTheDocument()
    const link = screen.getByRole("link")
    expect(link.getAttribute("href")).toBe("https://app.convictional.test/workspaces/attachments/abc/download")
    expect(link.getAttribute("target")).toBe("_blank")
  })

  test("falls back to the stored filename when file metadata is absent", () => {
    const preview: LinkPreview = {
      ...BASE,
      url: "https://app.convictional.test/workspaces/attachments/gone/download",
      title: "deleted.csv",
      resource_kind: "file",
      file: null,
    }
    render(<LinkPreviewCard linkPreview={preview} />)

    expect(screen.getByText("deleted.csv")).toBeInTheDocument()
    expect(screen.getByText("attach_file")).toBeInTheDocument()
  })

  test("renders an inline player for a video attachment", () => {
    const preview: LinkPreview = {
      ...BASE,
      url: "https://app.convictional.test/workspaces/attachments/vid/download",
      title: "demo.mp4",
      resource_kind: "file",
      file: { file_name: "demo.mp4", content_type: "video/mp4", byte_size: 4096 },
    }
    const { container } = render(<LinkPreviewCard linkPreview={preview} />)

    const video = container.querySelector("video") as HTMLVideoElement
    expect(video).toBeInTheDocument()
    expect(video.getAttribute("src")).toBe("https://app.convictional.test/workspaces/attachments/vid/download")
    expect(video.getAttribute("aria-label")).toBe("demo.mp4")
    // No file card is rendered alongside the player.
    expect(container.querySelector("video ~ a, a video")).toBeNull()
  })

  test("falls back to the file card for a video whose metadata failed to resolve", () => {
    const preview: LinkPreview = {
      ...BASE,
      url: "https://app.convictional.test/workspaces/attachments/vid/download",
      title: "demo.mp4",
      resource_kind: "file",
      file: null,
    }
    const { container } = render(<LinkPreviewCard linkPreview={preview} />)

    expect(container.querySelector("video")).toBeNull()
    expect(screen.getByText("demo.mp4")).toBeInTheDocument()
  })

  test("does not build a live player src from an unsafe url", () => {
    const preview: LinkPreview = {
      ...BASE,
      url: "javascript:alert(1)",
      title: "evil.mp4",
      resource_kind: "file",
      file: { file_name: "evil.mp4", content_type: "video/mp4", byte_size: 4096 },
    }
    const { container } = render(<LinkPreviewCard linkPreview={preview} />)

    // Unsafe url degrades to the file card, whose download href is neutralised to "#".
    expect(container.querySelector("video")).toBeNull()
    const link = screen.getByRole("link")
    expect(link.getAttribute("href")).toBe("#")
  })
})
