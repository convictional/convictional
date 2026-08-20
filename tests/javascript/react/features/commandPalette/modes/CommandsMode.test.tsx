import { describe, expect, test } from "vitest"

import { filterCommands } from "../../../../../../app/javascript/react/features/commandPalette/modes/CommandsMode"
import type { Command } from "../../../../../../app/javascript/react/features/commandPalette/types"

const commands: Command[] = [
  {
    key: "research",
    type: "research",
    label: "Research",
    description: null,
    url: null,
    options: null,
    quick_link_id: null,
  },
  {
    key: "create_quick_link",
    type: "create_quick_link",
    label: "Create quick link",
    description: null,
    url: null,
    options: null,
    quick_link_id: null,
  },
]

describe("filterCommands", () => {
  test("empty input returns all", () => {
    expect(filterCommands(commands, "")).toHaveLength(2)
  })

  test("matches startsWith case-insensitively", () => {
    expect(filterCommands(commands, "re")).toEqual([commands[0]])
    expect(filterCommands(commands, "CR")).toEqual([commands[1]])
  })

  test("trims input", () => {
    expect(filterCommands(commands, "  re  ")).toEqual([commands[0]])
  })

  test("no match returns empty", () => {
    expect(filterCommands(commands, "zz")).toEqual([])
  })
})
