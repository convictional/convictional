import { describe, expect, test } from "vitest"

import { makePlural, pluralize } from "../../../app/javascript/shared/strings"

describe("makePlural", () => {
  test("irregulars", () => {
    expect(makePlural("child")).toBe("children")
    expect(makePlural("person")).toBe("people")
    expect(makePlural("man")).toBe("men")
    expect(makePlural("woman")).toBe("women")
    expect(makePlural("foot")).toBe("feet")
    expect(makePlural("tooth")).toBe("teeth")
    expect(makePlural("goose")).toBe("geese")
    expect(makePlural("mouse")).toBe("mice")
  })

  test("unchanging words", () => {
    expect(makePlural("sheep")).toBe("sheep")
    expect(makePlural("fish")).toBe("fish")
    expect(makePlural("deer")).toBe("deer")
  })

  test("suffix rules — matches Python make_plural", () => {
    expect(makePlural("bus")).toBe("buses")
    expect(makePlural("category")).toBe("categories")
    expect(makePlural("wolf")).toBe("wolves")
    expect(makePlural("knife")).toBe("knives")
    expect(makePlural("photo")).toBe("photos")
    expect(makePlural("hero")).toBe("heroes")
  })

  test("regular words", () => {
    expect(makePlural("comment")).toBe("comments")
    expect(makePlural("goal")).toBe("goals")
    expect(makePlural("document")).toBe("documents")
  })
})

describe("pluralize", () => {
  test("returns singular for count of 1", () => {
    expect(pluralize(1, "comment")).toBe("comment")
    expect(pluralize(1, "child")).toBe("child")
  })

  test("auto-derives plural from makePlural when plural arg omitted", () => {
    expect(pluralize(0, "comment")).toBe("comments")
    expect(pluralize(2, "child")).toBe("children")
    expect(pluralize(5, "category")).toBe("categories")
  })

  test("explicit plural arg wins over auto-derivation", () => {
    expect(pluralize(2, "goal", "goals")).toBe("goals")
    expect(pluralize(2, "person", "people")).toBe("people")
  })
})
