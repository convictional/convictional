import { useEditorEffect } from "@handlewithcare/react-prosemirror"
import { act, cleanup } from "@testing-library/react"
import type { EditorView } from "prosemirror-view"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { Editor, EditorContent } from "../../../../../app/javascript/react/composites/editor/Editor"
import { useCommentMarks } from "../../../../../app/javascript/react/composites/editor/features/comments/useCommentMarks"
import { documentCommentUIStore } from "../../../../../app/javascript/react/features/documentEditor/store"
import { schema } from "../../../../../app/javascript/richText/schema"
import { buildThreadsApi, renderWithCommentProviders } from "./commentTestUtils"

function MarksHarness() {
  useCommentMarks()
  return null
}

function docWithCommentMark(commentId: string) {
  const commentMark = schema.marks.comment.create({ commentId })
  return schema.node("doc", null, [schema.node("paragraph", null, [schema.text("hello world", [commentMark])])])
}

function markCount(container: HTMLElement, commentId: string) {
  return container.querySelectorAll(`span.inline-comment-highlight[data-comment-id="${commentId}"]`).length
}

beforeEach(() => {
  documentCommentUIStore.setState({ pendingCommentId: "new-mark", activeCommentId: null })
})

afterEach(() => {
  cleanup()
  documentCommentUIStore.setState({ pendingCommentId: "" })
})

describe("useCommentMarks orphan-cleanup race", () => {
  // Regression: posting a comment used to make it disappear. createComment patches
  // the Query cache (so getThreads() is fresh), then closeCommentCard clears
  // pendingCommentId and re-runs cleanup — but the rendered `threads` prop lags the
  // cache by a render. Cleanup must read the live cache via getThreads(), not the
  // stale prop, or it treats the just-created mark as an orphan and strips it
  // (broadcasting the removal to all Yjs peers). The threadsApi below models the
  // lag: `threads` stays empty while `getThreads()` already returns the thread.
  test("keeps the freshly-created mark when pendingCommentId clears before the threads prop updates", () => {
    const threadsApi = buildThreadsApi({ threads: [], getThreads: () => [{ markId: "new-mark", comments: [] }] })

    const { container } = renderWithCommentProviders(
      <Editor features={[]} doc={docWithCommentMark("new-mark")}>
        <EditorContent />
        <MarksHarness />
      </Editor>,
      { threadsApi }
    )

    // While pending, the mark is protected by pendingCommentId.
    expect(markCount(container, "new-mark")).toBe(1)

    // closeCommentCard clears pendingCommentId; the live cache (getThreads) already
    // holds the thread even though the `threads` prop is still empty.
    act(() => documentCommentUIStore.setState({ pendingCommentId: "" }))

    expect(markCount(container, "new-mark")).toBe(1)
  })

  // Cross-doc paste: commented text pasted from doc A into doc B carries the
  // highlight mark but not the comment (the comment lives in doc A). Effect 1
  // schedules a confirming refetch for the unknown mark; when it resolves and the
  // mark is still absent from threads, the orphan-cleanup effect must strip it.
  // In the empty-destination-doc case react-query's structural sharing keeps the
  // `threads` reference stable, so Effect 2 only re-runs via the cleanupTick bumped
  // after the fetch resolves.
  test("strips a cross-doc orphan mark once the confirming refetch resolves", async () => {
    vi.useFakeTimers()
    try {
      // Not pending: the orphan is not protected as a freshly-created comment.
      documentCommentUIStore.setState({ pendingCommentId: "" })
      const refetchComments = vi.fn().mockResolvedValue(undefined)
      const threadsApi = buildThreadsApi({
        threads: [],
        isLoaded: true,
        getThreads: () => [],
        refetchComments,
      })

      const { container } = renderWithCommentProviders(
        <Editor features={[]} doc={docWithCommentMark("orphan-mark")}>
          <EditorContent />
          <MarksHarness />
        </Editor>,
        { threadsApi }
      )

      // Protected during the in-flight fetch window (pendingFetchMarkIds guards it).
      expect(markCount(container, "orphan-mark")).toBe(1)

      // Advance past the 500 ms debounce and flush the refetch promise; the tick
      // bump re-runs cleanup and the still-orphaned mark is removed.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500)
      })

      expect(markCount(container, "orphan-mark")).toBe(0)
      expect(refetchComments).toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  // Safety property: if a comment is opened on the mark during the debounce window,
  // the tick-triggered re-run must read the CURRENT-render pendingCommentId (not a
  // stale closure) and leave the mark alone. This is why cleanup runs through
  // Effect 2 rather than being called inside the fetch's .then().
  test("does not strip a mark that becomes pending during the debounce window", async () => {
    vi.useFakeTimers()
    try {
      documentCommentUIStore.setState({ pendingCommentId: "" })
      const refetchComments = vi.fn().mockResolvedValue(undefined)
      const threadsApi = buildThreadsApi({
        threads: [],
        isLoaded: true,
        getThreads: () => [],
        refetchComments,
      })

      const { container } = renderWithCommentProviders(
        <Editor features={[]} doc={docWithCommentMark("late-pending-mark")}>
          <EditorContent />
          <MarksHarness />
        </Editor>,
        { threadsApi }
      )

      // The mark becomes pending (comment opened) before the fetch resolves.
      act(() => documentCommentUIStore.setState({ pendingCommentId: "late-pending-mark" }))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(500)
      })

      // The tick re-run reads the live pendingCommentId and must keep the mark.
      expect(markCount(container, "late-pending-mark")).toBe(1)
    } finally {
      vi.useRealTimers()
    }
  })

  // Live cross-doc paste into an already-open, already-loaded doc: the mark is
  // inserted AFTER mount (unlike the tests above, which mount a doc that already
  // contains it). The mark-detection effect must re-run on the doc change to notice
  // the pasted mark and schedule the confirming refetch — if it only re-ran on
  // threads/pendingCommentId changes, a live paste would never be detected and the
  // orphan would sit until a page reload.
  test("strips an orphan mark pasted into an already-loaded doc without a reload", async () => {
    vi.useFakeTimers()
    let capturedView: EditorView | null = null
    function CaptureView() {
      useEditorEffect(view => {
        capturedView = view
      }, [])
      return null
    }
    try {
      documentCommentUIStore.setState({ pendingCommentId: "" })
      const refetchComments = vi.fn().mockResolvedValue(undefined)
      const threadsApi = buildThreadsApi({ threads: [], isLoaded: true, getThreads: () => [], refetchComments })

      const { container } = renderWithCommentProviders(
        <Editor features={[]} doc={schema.node("doc", null, [schema.node("paragraph")])}>
          <EditorContent />
          <MarksHarness />
          <CaptureView />
        </Editor>,
        { threadsApi }
      )

      // Empty doc: no marks yet, and no fetch scheduled.
      expect(markCount(container, "pasted-orphan")).toBe(0)
      expect(refetchComments).not.toHaveBeenCalled()

      // Simulate the paste: insert comment-marked text after mount.
      act(() => {
        const view = capturedView!
        const marked = schema.text("pasted", [schema.marks.comment.create({ commentId: "pasted-orphan" })])
        view.dispatch(view.state.tr.insert(1, marked))
      })

      // The detection effect re-ran on the doc change and scheduled the refetch;
      // advancing past the debounce + flushing it bumps the tick and cleanup strips it.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500)
      })

      expect(refetchComments).toHaveBeenCalled()
      expect(markCount(container, "pasted-orphan")).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })

  // Regression guard: a mark present in loaded threads is a valid mark. Effect 1
  // never schedules a fetch for it (it's already a known thread id), so the tick
  // path is not exercised — cleanup must simply never strip a valid mark.
  test("never strips a valid mark that is present in loaded threads", () => {
    const threadsApi = buildThreadsApi({
      threads: [{ markId: "kept-mark", comments: [] }],
      getThreads: () => [{ markId: "kept-mark", comments: [] }],
    })

    const { container } = renderWithCommentProviders(
      <Editor features={[]} doc={docWithCommentMark("kept-mark")}>
        <EditorContent />
        <MarksHarness />
      </Editor>,
      { threadsApi }
    )

    expect(markCount(container, "kept-mark")).toBe(1)
  })
})
