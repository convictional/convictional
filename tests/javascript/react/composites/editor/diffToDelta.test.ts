import { expect, test } from "vitest"
import diff from "fast-diff"
import * as Y from "yjs"

import { diffToDelta } from "../../../../../app/javascript/react/composites/editor/features/useCollaboration"

const applyMarkdownDiff = (yText: Y.Text, oldText: string, newText: string) => {
  const diffs = diff(oldText, newText)
  const delta = diffToDelta(diffs)
  yText.applyDelta(delta)
}

test("Y.js markdown diffing handles basic text insertion", () => {
  const doc = new Y.Doc()
  const text = doc.getText("markdown")

  text.insert(0, "Hello world")
  applyMarkdownDiff(text, "Hello world", "Hello beautiful world")

  expect(text.toString()).toBe("Hello beautiful world")
})

test("Y.js markdown diffing handles word insertion in middle", () => {
  const doc = new Y.Doc()
  const text = doc.getText("markdown")

  text.insert(0, "The quick fox")
  applyMarkdownDiff(text, "The quick fox", "The quick brown fox")

  expect(text.toString()).toBe("The quick brown fox")
})

test("Y.js markdown diffing handles text deletion", () => {
  const doc = new Y.Doc()
  const text = doc.getText("markdown")

  text.insert(0, "The quick brown fox jumps")
  applyMarkdownDiff(text, "The quick brown fox jumps", "The quick fox jumps")

  expect(text.toString()).toBe("The quick fox jumps")
})

test("Y.js markdown diffing handles word replacement", () => {
  const doc = new Y.Doc()
  const text = doc.getText("markdown")

  text.insert(0, "I like cats")
  applyMarkdownDiff(text, "I like cats", "I like dogs")

  expect(text.toString()).toBe("I like dogs")
})

test("Y.js markdown diffing handles markdown formatting changes", () => {
  const doc = new Y.Doc()
  const text = doc.getText("markdown")

  text.insert(0, "# Title\n\nThis is a paragraph.")
  applyMarkdownDiff(text, "# Title\n\nThis is a paragraph.", "# Updated Title\n\nThis is a longer paragraph with more content.")

  expect(text.toString()).toBe("# Updated Title\n\nThis is a longer paragraph with more content.")
})

test("Y.js markdown diffing generates proper updates for collaboration", () => {
  const doc1 = new Y.Doc()
  const doc2 = new Y.Doc()
  const text1 = doc1.getText("markdown")
  const text2 = doc2.getText("markdown")

  // Set up initial state in both documents
  text1.insert(0, "Original text")
  const update1 = Y.encodeStateAsUpdate(doc1)
  Y.applyUpdate(doc2, update1)

  expect(text2.toString()).toBe("Original text")

  // Apply diff to first document
  applyMarkdownDiff(text1, "Original text", "Modified original text")

  // Get the update and apply to second document
  const update2 = Y.encodeStateAsUpdate(doc1, Y.encodeStateVector(doc2))
  Y.applyUpdate(doc2, update2)

  expect(text2.toString()).toBe("Modified original text")
})

test("Y.js markdown diffing produces smaller updates than full replacement", () => {
  const docDiff = new Y.Doc()
  const docReplace = new Y.Doc()
  const textDiff = docDiff.getText("markdown")
  const textReplace = docReplace.getText("markdown")

  const original = "This is a very long paragraph with lots of content that we want to test with to see how efficient our diffing algorithm is compared to full replacement."
  const modified = "This is a very long paragraph with some different content that we want to test with to see how efficient our diffing algorithm is compared to full replacement."

  // Set up initial state
  textDiff.insert(0, original)
  textReplace.insert(0, original)

  // Capture state before changes
  const stateBeforeDiff = Y.encodeStateVector(docDiff)
  const stateBeforeReplace = Y.encodeStateVector(docReplace)

  // Apply changes using diff
  applyMarkdownDiff(textDiff, original, modified)
  const diffUpdate = Y.encodeStateAsUpdate(docDiff, stateBeforeDiff)

  // Apply changes using full replacement
  textReplace.delete(0, textReplace.length)
  textReplace.insert(0, modified)
  const replaceUpdate = Y.encodeStateAsUpdate(docReplace, stateBeforeReplace)

  // Diff update should be smaller than replace update
  expect(diffUpdate.length).toBeLessThan(replaceUpdate.length)

  // Both should produce the same result
  expect(textDiff.toString()).toBe(modified)
  expect(textReplace.toString()).toBe(modified)
})
