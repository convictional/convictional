import { describe, expect, test } from "vitest"

import { toggleReactionInMap } from "../../../../app/javascript/react/shared/reactions"
import type { ReactionUser } from "../../../../app/javascript/react/shared/types"

const me: ReactionUser = { id: "u-me", display_name: "Me" }
const other: ReactionUser = { id: "u-other", display_name: "Other" }

describe("toggleReactionInMap", () => {
  test("adds the user when the reaction type is absent", () => {
    expect(toggleReactionInMap({}, "thumbs_up", me)).toEqual({ thumbs_up: [me] })
  })

  test("adds the user to an existing bucket without dropping others", () => {
    const result = toggleReactionInMap({ thumbs_up: [other] }, "thumbs_up", me)
    expect(result.thumbs_up).toEqual([other, me])
  })

  test("removes the user when already present, leaving an empty bucket", () => {
    const result = toggleReactionInMap({ thumbs_up: [me] }, "thumbs_up", me)
    expect(result.thumbs_up).toEqual([])
  })

  test("removes only the user, keeping other reactors in the bucket", () => {
    const result = toggleReactionInMap({ heart: [other, me] }, "heart", me)
    expect(result.heart).toEqual([other])
  })

  test("leaves other reaction types untouched", () => {
    const result = toggleReactionInMap({ heart: [other], rocket: [me] }, "heart", me)
    expect(result.rocket).toEqual([me])
    expect(result.heart).toEqual([other, me])
  })

  test("does not mutate the input map or its buckets", () => {
    const input = { thumbs_up: [other] }
    const inputBucket = input.thumbs_up
    const result = toggleReactionInMap(input, "thumbs_up", me)
    expect(input).toEqual({ thumbs_up: [other] })
    expect(input.thumbs_up).toBe(inputBucket)
    expect(result).not.toBe(input)
  })
})
