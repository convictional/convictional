import { expect, test, describe } from "vitest"
import Fuse from "fuse.js"
import { nameToEmoji } from "gemoji"

interface Emoji {
  name: string
  emoji: string
}

const allEmojis: Emoji[] = Object.entries(nameToEmoji).map(([name, emoji]) => ({
  name,
  emoji,
}))

const fuse = new Fuse(allEmojis, { keys: ["name"], threshold: 0.3 })

describe("Emoji data and search", () => {
  test("gemoji data contains expected common emojis", () => {
    expect(nameToEmoji["smile"]).toBe("😄")
    expect(nameToEmoji["heart"]).toBe("❤️")
    expect(nameToEmoji["+1"]).toBe("👍")
    expect(nameToEmoji["fire"]).toBe("🔥")
    expect(nameToEmoji["rocket"]).toBe("🚀")
  })

  test("fuzzy search returns relevant results for 'smile'", () => {
    const results = fuse.search("smile").map(r => r.item.name)
    expect(results).toContain("smile")
    expect(results.length).toBeGreaterThan(1)
  })

  test("fuzzy search returns relevant results for 'heart'", () => {
    const results = fuse.search("heart").map(r => r.item.name)
    expect(results).toContain("heart")
    expect(results).toContain("heart_eyes")
  })

  test("search for nonexistent shortcode returns empty", () => {
    const results = fuse.search("zzzznotanemoji")
    expect(results).toHaveLength(0)
  })

  test("allEmojis array is populated", () => {
    expect(allEmojis.length).toBeGreaterThan(1000)
    expect(allEmojis[0]).toHaveProperty("name")
    expect(allEmojis[0]).toHaveProperty("emoji")
  })
})
