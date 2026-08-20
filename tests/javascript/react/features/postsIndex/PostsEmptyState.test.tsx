import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { PostsEmptyState } from "~/react/features/postsIndex/components/PostsEmptyState"

afterEach(() => cleanup())

describe("PostsEmptyState", () => {
  test("drafts view shows the no-drafts variant", () => {
    render(<PostsEmptyState view="drafts" decided={false} />)
    expect(screen.getByText("No drafts")).toBeInTheDocument()
    expect(screen.getByText(/Save as draft/)).toBeInTheDocument()
  })

  test("decided filter shows the no-decisions variant", () => {
    render(<PostsEmptyState view="posts" decided={true} />)
    expect(screen.getByText("No decisions")).toBeInTheDocument()
  })

  test("default posts view shows the no-posts variant", () => {
    render(<PostsEmptyState view="posts" decided={false} />)
    expect(screen.getByText("No posts")).toBeInTheDocument()
  })
})
