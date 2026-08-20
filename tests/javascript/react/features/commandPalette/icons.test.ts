import { describe, expect, test } from "vitest"

import {
  iconForCommandType,
  iconForContentType,
  iconForResourceType,
} from "../../../../../app/javascript/react/features/commandPalette/icons"

describe("icons", () => {
  test("command types map to expected icons", () => {
    expect(iconForCommandType("research")).toBe("lab_research")
    expect(iconForCommandType("create_quick_link")).toBe("add_link")
    expect(iconForCommandType("quick_link")).toBe("link")
    expect(iconForCommandType("unknown")).toBe("command")
  })

  test("content types cover lookup result kinds", () => {
    expect(iconForContentType("user")).toBe("person")
    expect(iconForContentType("email_contact")).toBe("contact_mail")
    expect(iconForContentType("email_thread")).toBe("mail")
    expect(iconForContentType("chat")).toBe("chat_bubble")
    expect(iconForContentType("unknown")).toBe("description")
  })

  test("resource_type normalizes case/separators", () => {
    expect(iconForResourceType("EmailThread")).toBe("mail")
    expect(iconForResourceType("email_thread")).toBe("mail")
    expect(iconForResourceType("CHAT")).toBe("chat_bubble")
    expect(iconForResourceType("anything-else")).toBe("description")
  })
})
