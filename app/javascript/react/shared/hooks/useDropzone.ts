import { useCallback, useEffect, useRef, useState } from "react"

interface UseDropzoneOptions {
  onFiles: (files: File[]) => void
  enabled?: boolean
}

// dragover fires continuously (~every 50ms) while a file drag is over the
// window. dragleave/dragend are unreliable for drags that originate outside
// the document — exiting the window, pressing Esc, or releasing without a
// drop can all leave a depth-counter approach stuck above zero. A short
// timeout on the last dragover is the only signal that survives every
// drag-cancellation path.
//
// Uses a callback ref instead of consuming a RefObject so the effect can
// re-run when the element mounts later (e.g. after a loading state flips). A
// useEffect that reads RefObject.current would attach to a null ref the first
// time and never re-attach.
//
// onFiles is read through a ref so the effect depends only on `el`/`enabled`.
// A caller passing an unmemoized onFiles would otherwise re-run the effect on
// every render, and the cleanup's setIsDragOver(false) racing each dragover's
// setIsDragOver(true) produces a rapid flicker mid-drag.
export function useDropzone({ onFiles, enabled = true }: UseDropzoneOptions) {
  const [el, setEl] = useState<HTMLElement | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const onFilesRef = useRef(onFiles)
  onFilesRef.current = onFiles

  const ref = useCallback((next: HTMLElement | null) => {
    setEl(next)
  }, [])

  useEffect(() => {
    if (!enabled || !el) return

    const hasFiles = (e: DragEvent) => !!e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files")

    let clearTimer = 0
    const scheduleClear = () => {
      window.clearTimeout(clearTimer)
      // 150ms gives a comfortable buffer over the ~50ms dragover cadence so
      // the overlay doesn't flicker on a slow drag, while still feeling
      // immediate when the drag actually ends.
      clearTimer = window.setTimeout(() => setIsDragOver(false), 150)
    }

    const onDragOver = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy"
      setIsDragOver(true)
      scheduleClear()
    }
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      window.clearTimeout(clearTimer)
      setIsDragOver(false)
      const files = e.dataTransfer ? Array.from(e.dataTransfer.files) : []
      if (files.length > 0) onFilesRef.current(files)
    }

    el.addEventListener("dragover", onDragOver)
    el.addEventListener("drop", onDrop)
    return () => {
      el.removeEventListener("dragover", onDragOver)
      el.removeEventListener("drop", onDrop)
      window.clearTimeout(clearTimer)
      setIsDragOver(false)
    }
  }, [el, enabled])

  return { isDragOver, ref }
}
