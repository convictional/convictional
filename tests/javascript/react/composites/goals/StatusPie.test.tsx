import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { StatusPie } from "~/react/composites/goals/StatusPie"

afterEach(cleanup)

describe("StatusPie", () => {
  test("labels a tracked value as a percentage", () => {
    render(<StatusPie progress={0.42} />)
    expect(screen.getByLabelText("42% complete")).toBeInTheDocument()
  })

  test("labels a null value as untracked rather than 0%", () => {
    render(<StatusPie progress={null} />)
    expect(screen.getByLabelText("Progress not tracked")).toBeInTheDocument()
  })
})
