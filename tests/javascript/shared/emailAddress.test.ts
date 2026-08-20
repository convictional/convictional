import { expect, test, describe } from "vitest"
import { EmailAddress } from "../../../app/javascript/shared/emailAddress"

describe("EmailAddress", () => {
  describe("parse", () => {
    test("parses simple email address", () => {
      const addr = EmailAddress.parse("test@example.com")
      expect(addr.email).toBe("test@example.com")
      expect(addr.name).toBe("test")
    })

    test("parses display name format", () => {
      const addr = EmailAddress.parse("John Doe <john@example.com>")
      expect(addr.email).toBe("john@example.com")
      expect(addr.name).toBe("John Doe")
    })

    test("parses display name with quotes", () => {
      const addr = EmailAddress.parse('"John Doe" <john@example.com>')
      expect(addr.email).toBe("john@example.com")
      expect(addr.name).toBe("John Doe")
    })

    test("handles extra whitespace", () => {
      const addr = EmailAddress.parse("  John Doe  <  john@example.com  >  ")
      expect(addr.email).toBe("john@example.com")
      expect(addr.name).toBe("John Doe")
    })

    test("returns same instance when passed EmailAddress", () => {
      const original = new EmailAddress("John", "john@example.com")
      const result = EmailAddress.parse(original)
      expect(result).toBe(original)
    })

    test("throws error for invalid email format", () => {
      expect(() => EmailAddress.parse("invalid-email")).toThrow("Invalid email address")
      expect(() => EmailAddress.parse("test@")).toThrow("Invalid email address")
      expect(() => EmailAddress.parse("@example.com")).toThrow("Invalid email address")
    })

    test("throws error for empty or null input", () => {
      expect(() => EmailAddress.parse("")).toThrow("Invalid email address")
      expect(() => EmailAddress.parse("   ")).toThrow("Invalid email address")
      expect(() => EmailAddress.parse(null as any)).toThrow("Invalid email address")
      expect(() => EmailAddress.parse(undefined as any)).toThrow("Invalid email address")
    })
  })

  describe("build", () => {
    test("builds with name parameter", () => {
      const addr = EmailAddress.build("john@example.com", "John Doe")
      expect(addr.email).toBe("john@example.com")
      expect(addr.name).toBe("John Doe")
      expect(addr.displayName).toBe("John Doe <john@example.com>")
    })

    test("builds without name parameter", () => {
      const addr = EmailAddress.build("john@example.com")
      expect(addr.email).toBe("john@example.com")
      expect(addr.name).toBe("john")
    })

    test("ignores empty name parameter", () => {
      const addr = EmailAddress.build("john@example.com", "")
      expect(addr.email).toBe("john@example.com")
      expect(addr.name).toBe("john")
    })

    test("falls back to parsed email if name format is invalid", () => {
      const addr = EmailAddress.build("john@example.com", "John Doe")
      expect(addr.email).toBe("john@example.com")
      expect(addr.name).toBe("John Doe")
    })
  })

  describe("isValidEmail", () => {
    test("validates correct email addresses", () => {
      expect(EmailAddress.isValidEmail("test@example.com")).toBe(true)
      expect(EmailAddress.isValidEmail("John Doe <john@example.com>")).toBe(true)
      expect(EmailAddress.isValidEmail("user.name+tag@domain.co.uk")).toBe(true)
    })

    test("rejects invalid email addresses", () => {
      expect(EmailAddress.isValidEmail("invalid-email")).toBe(false)
      expect(EmailAddress.isValidEmail("test@")).toBe(false)
      expect(EmailAddress.isValidEmail("@example.com")).toBe(false)
      expect(EmailAddress.isValidEmail("")).toBe(false)
      expect(EmailAddress.isValidEmail(null as any)).toBe(false)
      expect(EmailAddress.isValidEmail(undefined as any)).toBe(false)
    })

    test("accepts long email addresses", () => {
      expect(EmailAddress.isValidEmail("a".repeat(244) + "@example.com")).toBe(true)
    })
  })

  describe("parseList", () => {
    test("parses comma-separated email addresses", () => {
      const addresses = EmailAddress.parseList("john@example.com, jane@example.com, bob@test.com")
      expect(addresses).toHaveLength(3)
      expect(addresses[0].email).toBe("john@example.com")
      expect(addresses[1].email).toBe("jane@example.com")
      expect(addresses[2].email).toBe("bob@test.com")
    })

    test("parses mixed format addresses", () => {
      const addresses = EmailAddress.parseList("john@example.com, Jane Smith <jane@example.com>, bob@test.com")
      expect(addresses).toHaveLength(3)
      expect(addresses[0].name).toBe("john")
      expect(addresses[1].name).toBe("Jane Smith")
      expect(addresses[2].name).toBe("bob")
    })

    test("handles extra whitespace and empty entries", () => {
      const addresses = EmailAddress.parseList("john@example.com,  , jane@example.com,   ")
      expect(addresses).toHaveLength(2)
      expect(addresses[0].email).toBe("john@example.com")
      expect(addresses[1].email).toBe("jane@example.com")
    })

    test("returns empty array for empty input", () => {
      expect(EmailAddress.parseList("")).toEqual([])
      expect(EmailAddress.parseList("   ")).toEqual([])
      expect(EmailAddress.parseList(null)).toEqual([])
      expect(EmailAddress.parseList(undefined)).toEqual([])
    })

    test("skips invalid email addresses", () => {
      const addresses = EmailAddress.parseList("john@example.com, invalid-email, jane@example.com")
      expect(addresses).toHaveLength(2)
      expect(addresses[0].email).toBe("john@example.com")
      expect(addresses[1].email).toBe("jane@example.com")
    })

    test("handles display names with commas", () => {
      const addresses = EmailAddress.parseList('"Doe, John" <john@example.com>, "Smith, Jane" <jane@example.com>')
      expect(addresses[0].email).toBe("john@example.com")
      expect(addresses[1].email).toBe("jane@example.com")
    })
  })

  describe("parseListAddresses", () => {
    test("returns array of email addresses only", () => {
      const emails = EmailAddress.parseListAddresses("John Doe <john@example.com>, Jane Smith <jane@example.com>")
      expect(emails).toEqual(["john@example.com", "jane@example.com"])
    })

    test("handles mixed formats", () => {
      const emails = EmailAddress.parseListAddresses("john@example.com, Jane Smith <jane@example.com>, bob@test.com")
      expect(emails).toEqual(["john@example.com", "jane@example.com", "bob@test.com"])
    })

    test("handles display names with commas", () => {
      const emails = EmailAddress.parseListAddresses('"Doe, John" <john@example.com>, "Smith, Jane" <jane@example.com>')
      expect(emails).toEqual(["john@example.com", "jane@example.com"])
    })

    test("handles unquoted display names with commas", () => {
      const emails = EmailAddress.parseListAddresses("Doe, John <john@example.com>, Smith, Jane <jane@example.com>")
      expect(emails).toEqual(["john@example.com", "jane@example.com"])
    })
  })

  describe("isValidEmailList", () => {
    test("validates comma-separated email addresses", () => {
      expect(EmailAddress.isValidEmailList("john@example.com, jane@example.com, bob@test.com")).toBe(true)
      expect(EmailAddress.isValidEmailList("user@domain.com")).toBe(true)
      expect(EmailAddress.isValidEmailList("John Doe <john@example.com>, Jane Smith <jane@example.com>")).toBe(true)
    })

    test("rejects invalid email addresses in list", () => {
      expect(EmailAddress.isValidEmailList("john@example.com, invalid-email, jane@example.com")).toBe(false)
      expect(EmailAddress.isValidEmailList("valid@example.com, @invalid.com")).toBe(false)
      expect(EmailAddress.isValidEmailList("valid@example.com, test@")).toBe(false)
    })

    test("rejects empty parts in list", () => {
      expect(EmailAddress.isValidEmailList("john@example.com, , jane@example.com")).toBe(false)
      expect(EmailAddress.isValidEmailList("john@example.com,   , jane@example.com")).toBe(false)
      expect(EmailAddress.isValidEmailList(",john@example.com")).toBe(false)
      expect(EmailAddress.isValidEmailList("john@example.com,")).toBe(false)
    })

    test("rejects empty or null input", () => {
      expect(EmailAddress.isValidEmailList("")).toBe(false)
      expect(EmailAddress.isValidEmailList("   ")).toBe(false)
      expect(EmailAddress.isValidEmailList(null)).toBe(false)
      expect(EmailAddress.isValidEmailList(undefined)).toBe(false)
    })

    test("handles whitespace around emails", () => {
      expect(EmailAddress.isValidEmailList("  john@example.com  ,  jane@example.com  ")).toBe(true)
      expect(EmailAddress.isValidEmailList(" John Doe <john@example.com> , Jane Smith <jane@example.com> ")).toBe(true)
    })

    test("handles display names with commas", () => {
      expect(EmailAddress.isValidEmailList('"Doe, John" <john@example.com>')).toBe(true)
      expect(EmailAddress.isValidEmailList('"Doe, John" <john@example.com>, Jane Smith <jane@example.com>')).toBe(true)
      expect(EmailAddress.isValidEmailList('"Doe, John" <john@example.com>, "Smith, Jane" <jane@example.com>')).toBe(true)
    })
  })

  describe("properties", () => {
    test("displayName returns formatted display name", () => {
      const addr1 = new EmailAddress("John Doe", "john@example.com")
      expect(addr1.displayName).toBe("John Doe <john@example.com>")

      const addr2 = new EmailAddress("john", "john@example.com")
      expect(addr2.displayName).toBe("john <john@example.com>")
    })

    test("hasDisplayName checks if name differs from username", () => {
      const addr1 = new EmailAddress("John Doe", "john@example.com")
      expect(addr1.hasDisplayName).toBe(true)

      const addr2 = new EmailAddress("john", "john@example.com")
      expect(addr2.hasDisplayName).toBe(false)
    })

    test("toString returns displayName", () => {
      const addr = new EmailAddress("John Doe", "john@example.com")
      expect(addr.toString()).toBe("John Doe <john@example.com>")
    })

    test("toJSON returns name and email", () => {
      const addr = new EmailAddress("John Doe", "john@example.com")
      expect(addr.toJSON()).toEqual({
        name: "John Doe",
        email: "john@example.com"
      })
    })
  })

  describe("splitEmailList", () => {
    test("splits simple comma-separated emails", () => {
      const result = EmailAddress.splitEmailList("john@example.com, jane@example.com, bob@test.com")
      expect(result).toEqual(["john@example.com", "jane@example.com", "bob@test.com"])
    })

    test("handles display names with angle brackets", () => {
      const result = EmailAddress.splitEmailList("John Doe <john@example.com>, Jane Smith <jane@example.com>")
      expect(result).toEqual(["John Doe <john@example.com>", "Jane Smith <jane@example.com>"])
    })

    test("handles quoted display names with commas", () => {
      const result = EmailAddress.splitEmailList('"Doe, John" <john@example.com>, "Smith, Jane" <jane@example.com>')
      expect(result).toEqual(['"Doe, John" <john@example.com>', '"Smith, Jane" <jane@example.com>'])
    })

    test("ignores commas inside quoted strings", () => {
      const result = EmailAddress.splitEmailList('"Last, First" <test@example.com>')
      expect(result).toEqual(['"Last, First" <test@example.com>'])
    })

    test("handles escaped quotes in display names", () => {
      const result = EmailAddress.splitEmailList('"John \\"The Man\\" Doe" <john@example.com>, jane@example.com')
      expect(result).toEqual(['"John \\"The Man\\" Doe" <john@example.com>', 'jane@example.com'])
    })

    test("handles mixed formats", () => {
      const result = EmailAddress.splitEmailList('simple@example.com, "Complex, Name" <complex@example.com>, Another <another@example.com>')
      expect(result).toEqual(['simple@example.com', '"Complex, Name" <complex@example.com>', 'Another <another@example.com>'])
    })

    test("handles empty input", () => {
      const result = EmailAddress.splitEmailList("")
      expect(result).toEqual([""])
    })

    test("handles single email without comma", () => {
      const result = EmailAddress.splitEmailList("single@example.com")
      expect(result).toEqual(["single@example.com"])
    })

    test("removes whitespace around parts", () => {
      const result = EmailAddress.splitEmailList("  email1@example.com  ,  email2@example.com  ")
      expect(result).toEqual(["email1@example.com", "email2@example.com"])
    })
  })
})
