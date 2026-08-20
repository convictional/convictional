import { useCallback } from "react"

export interface UseArrowKeySelectionOptions {
  itemCount: number
  selectedIndex: number
  setSelectedIndex: (index: number) => void
  onActivate: (index: number) => void
  mouseEnabled: boolean
  setMouseEnabled: (enabled: boolean) => void
  initialMouse: { x: number; y: number } | null
  setInitialMouse: (pos: { x: number; y: number } | null) => void
}

const MOUSE_GATE_PIXELS = 10

// Arrow nav + Enter + mouse-gate, copied from palette.ts:305-323 + 497-518.
// The mouse-gate (only enable hover after >10px of cursor movement) prevents
// arrow-key navigation from being clobbered by mouseover events fired when the
// list re-renders under a stationary cursor.
export function useArrowKeySelection(opts: UseArrowKeySelectionOptions) {
  const {
    itemCount,
    selectedIndex,
    setSelectedIndex,
    onActivate,
    mouseEnabled,
    setMouseEnabled,
    initialMouse,
    setInitialMouse,
  } = opts

  const handleArrowDown = useCallback(() => {
    setMouseEnabled(false)
    if (itemCount > 0) setSelectedIndex((selectedIndex + 1) % itemCount)
  }, [itemCount, selectedIndex, setSelectedIndex, setMouseEnabled])

  const handleArrowUp = useCallback(() => {
    setMouseEnabled(false)
    if (itemCount > 0) setSelectedIndex((selectedIndex - 1 + itemCount) % itemCount)
  }, [itemCount, selectedIndex, setSelectedIndex, setMouseEnabled])

  const handleEnter = useCallback(() => {
    if (selectedIndex >= 0 && selectedIndex < itemCount) onActivate(selectedIndex)
  }, [selectedIndex, itemCount, onActivate])

  const handleMouseMove = useCallback(
    (event: { clientX: number; clientY: number }) => {
      if (mouseEnabled) return
      if (initialMouse === null) {
        setInitialMouse({ x: event.clientX, y: event.clientY })
        return
      }
      const dx = event.clientX - initialMouse.x
      const dy = event.clientY - initialMouse.y
      if (Math.sqrt(dx * dx + dy * dy) > MOUSE_GATE_PIXELS) setMouseEnabled(true)
    },
    [mouseEnabled, initialMouse, setInitialMouse, setMouseEnabled]
  )

  const handleItemHover = useCallback(
    (index: number) => {
      if (mouseEnabled) setSelectedIndex(index)
    },
    [mouseEnabled, setSelectedIndex]
  )

  return { handleArrowDown, handleArrowUp, handleEnter, handleMouseMove, handleItemHover }
}
