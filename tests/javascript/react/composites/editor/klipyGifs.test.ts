import { expect, test, describe } from "vitest"

import { parseKlipyGifs } from "../../../../../app/javascript/react/composites/editor/components/GifPicker"

const makeGif = (overrides: Record<string, unknown> = {}) => ({
  id: 123,
  slug: "funny-cat",
  title: "Funny Cat",
  type: "gif",
  file: {
    hd: { gif: { url: "https://static.klipy.com/hd.gif", width: 600, height: 400 } },
    md: { gif: { url: "https://static.klipy.com/md.gif", width: 400, height: 300 } },
    sm: {
      gif: { url: "https://static.klipy.com/sm.gif", width: 220, height: 150 },
      jpg: { url: "https://static.klipy.com/sm.jpg", width: 220, height: 150 },
    },
    xs: {
      gif: { url: "https://static.klipy.com/xs.gif", width: 100, height: 75 },
      jpg: { url: "https://static.klipy.com/xs.jpg", width: 100, height: 75 },
    },
  },
  ...overrides,
})

describe("parseKlipyGifs", () => {
  test("parses a standard Klipy API response item", () => {
    const result = parseKlipyGifs([makeGif()])
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      slug: "funny-cat",
      title: "Funny Cat",
      content_url: "https://static.klipy.com/md.gif",
      preview_url: "https://static.klipy.com/sm.gif",
      preview_still_url: "https://static.klipy.com/sm.jpg",
      width: 220,
      height: 150,
    })
  })

  test("filters out ad items", () => {
    const items = [makeGif({ slug: "real-gif" }), makeGif({ slug: "ad-item", type: "ad" })]
    const result = parseKlipyGifs(items)
    expect(result).toHaveLength(1)
    expect(result[0].slug).toBe("real-gif")
  })

  test("falls back to hd when md is missing", () => {
    const item = makeGif()
    delete (item.file as Record<string, unknown>).md
    const result = parseKlipyGifs([item])
    expect(result[0].content_url).toBe("https://static.klipy.com/hd.gif")
  })

  test("falls back to xs when sm is missing", () => {
    const item = makeGif()
    delete (item.file as Record<string, unknown>).sm
    const result = parseKlipyGifs([item])
    expect(result[0].preview_url).toBe("https://static.klipy.com/xs.gif")
    expect(result[0].preview_still_url).toBe("https://static.klipy.com/xs.jpg")
  })

  test("uses defaults for missing dimensions", () => {
    const item = makeGif()
    delete (item.file as Record<string, unknown>).sm
    delete (item.file as Record<string, unknown>).xs
    const result = parseKlipyGifs([item])
    expect(result[0].width).toBe(200)
    expect(result[0].height).toBe(150)
  })

  test("handles empty title", () => {
    const result = parseKlipyGifs([makeGif({ title: "" })])
    expect(result[0].title).toBe("")
  })

  test("handles null/undefined input", () => {
    expect(parseKlipyGifs(null as unknown as [])).toEqual([])
    expect(parseKlipyGifs(undefined as unknown as [])).toEqual([])
    expect(parseKlipyGifs([])).toEqual([])
  })
})
