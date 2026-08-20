export class EmailAddress {
  public readonly name: string
  public readonly email: string

  constructor(name: string, email: string) {
    this.name = name
    this.email = email
  }

  static parse(value: string | EmailAddress): EmailAddress {
    if (value instanceof EmailAddress) {
      return value
    }

    if (!value || typeof value !== "string") {
      throw new Error("Invalid email address")
    }

    const trimmed = value.trim()
    if (!trimmed) {
      throw new Error("Invalid email address")
    }

    // Handle display name format: "Name <email@domain.com>"
    const displayNameMatch = trimmed.match(/^(.+?)\s*<([^>]+)>$/)
    if (displayNameMatch) {
      const name = displayNameMatch[1].trim().replace(/^["']|["']$/g, "") // Remove quotes
      const email = displayNameMatch[2].trim()

      if (!this.isValidEmailFormat(email)) {
        throw new Error(`Invalid email address: ${email}`)
      }

      return new EmailAddress(name, email)
    }

    // If no angle brackets, treat as just an email address
    if (!this.isValidEmailFormat(trimmed)) {
      throw new Error(`Invalid email address: ${trimmed}`)
    }

    // Extract username from email for name
    const username = trimmed.split("@")[0]
    return new EmailAddress(username, trimmed)
  }

  static build(email: string, name?: string): EmailAddress {
    const parsed = this.parse(email)

    if (name && name.trim()) {
      try {
        return this.parse(`${name.trim()} <${parsed.email}>`)
      } catch {
        // Fall back to parsed email if name format is invalid
        return parsed
      }
    }

    return parsed
  }

  static isValidEmail(email: string): boolean {
    if (!email || typeof email !== "string") {
      return false
    }

    try {
      this.parse(email)
      return true
    } catch {
      return false
    }
  }

  static isValidEmailList(commaSeparatedEmailString?: string | null): boolean {
    if (!commaSeparatedEmailString || typeof commaSeparatedEmailString !== "string") {
      return false
    }

    const trimmed = commaSeparatedEmailString.trim()
    if (!trimmed) {
      return false
    }

    const parts = this.splitEmailList(trimmed)
    if (parts.length === 0) {
      return false
    }

    for (const part of parts) {
      if (!part) {
        return false // Empty parts are invalid
      }

      if (!this.isValidEmail(part)) {
        return false
      }
    }

    return true
  }

  static parseList(commaSeparatedEmailString?: string | null): EmailAddress[] {
    if (!commaSeparatedEmailString || !commaSeparatedEmailString.trim()) {
      return []
    }

    const addresses: EmailAddress[] = []
    const parts = this.splitEmailList(commaSeparatedEmailString.trim())

    for (const part of parts) {
      if (!part) continue

      try {
        addresses.push(this.parse(part))
      } catch {
        // Skip invalid addresses
        continue
      }
    }

    return addresses
  }

  static parseListAddresses(commaSeparatedEmailString?: string | null): string[] {
    return this.parseList(commaSeparatedEmailString).map(addr => addr.email)
  }

  static splitEmailList(emailString: string): string[] {
    const parts: string[] = []
    let current = ""
    let insideQuotes = false
    let insideAngleBrackets = false

    for (let i = 0; i < emailString.length; i++) {
      const char = emailString[i]
      const prevChar = i > 0 ? emailString[i - 1] : ""

      if (char === '"' && prevChar !== "\\") {
        insideQuotes = !insideQuotes
        current += char
      } else if (char === "<" && !insideQuotes) {
        insideAngleBrackets = true
        current += char
      } else if (char === ">" && !insideQuotes) {
        insideAngleBrackets = false
        current += char
      } else if (char === "," && !insideQuotes && !insideAngleBrackets) {
        // Look ahead to see if there's a < before any other comma (indicating unquoted display name)
        const remainingString = emailString.slice(i + 1)
        const nextAngleBracket = remainingString.indexOf("<")
        const nextComma = remainingString.indexOf(",")

        // Check if current accumulated text has content (not just whitespace)
        const hasContent = current.trim().length > 0

        // If there's a < coming up AND (no comma before it OR comma is after it),
        // AND we have content already, this comma is part of display name
        if (hasContent && nextAngleBracket !== -1 && (nextComma === -1 || nextAngleBracket < nextComma)) {
          // Check if current doesn't already have an email (no @ or no >)
          const hasEmail = current.includes("@") || current.includes(">")
          if (!hasEmail) {
            current += char
          } else {
            // We already have a complete email, so this is a separator
            parts.push(current.trim())
            current = ""
          }
        } else {
          parts.push(current.trim())
          current = ""
        }
      } else {
        current += char
      }
    }

    parts.push(current.trim())
    return parts
  }

  private static isValidEmailFormat(email: string): boolean {
    // Basic email validation regex
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return emailRegex.test(email)
  }

  get displayName(): string {
    return `${this.name} <${this.email}>`
  }

  get hasDisplayName(): boolean {
    const username = this.email.split("@")[0]
    return this.name !== username
  }

  toString(): string {
    return this.displayName
  }

  toJSON(): { name: string; email: string } {
    return {
      name: this.name,
      email: this.email,
    }
  }
}
