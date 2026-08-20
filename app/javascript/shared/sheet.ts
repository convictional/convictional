import { AlpineComponent } from "alpinejs"

interface SheetData {
  isOpen: boolean
  keyboardHeight: number
  isKeyboardVisible: boolean
  maxSheetHeight: string
  setupKeyboardHandlers(): void
  updateSheetPosition(): void
  handleFocus(event: FocusEvent): void
  cleanup(): void
}

function sheet(): AlpineComponent<SheetData> {
  let visualViewport: VisualViewport | null = null
  let resizeHandler: (() => void) | null = null
  let focusHandler: ((event: FocusEvent) => void) | null = null

  const getKeyboardHeight = (): number => {
    if (!visualViewport) return 0

    const windowHeight = window.innerHeight
    const viewportHeight = visualViewport.height
    const keyboardHeight = Math.max(0, windowHeight - viewportHeight)

    return keyboardHeight
  }

  const calculateMaxSheetHeight = (keyboardHeight: number): string => {
    if (keyboardHeight > 0) {
      const availableHeight = window.visualViewport?.height || window.innerHeight
      const maxHeight = Math.floor(availableHeight * 0.85)
      return `${maxHeight}px`
    }

    return "85vh"
  }

  return {
    isOpen: false,
    keyboardHeight: 0,
    isKeyboardVisible: false,
    maxSheetHeight: "85vh",

    init() {
      this.$watch("isOpen", value => {
        if (value) {
          const backdrop = this.$refs.backdrop as HTMLElement
          const sheet = this.$refs.sheet as HTMLElement
          if (backdrop && sheet) {
            document.body.appendChild(backdrop)
            document.body.appendChild(sheet)
          }

          this.setupKeyboardHandlers()
        } else {
          this.cleanup()
        }
      })
    },

    setupKeyboardHandlers() {
      if (typeof window === "undefined" || !window.visualViewport) {
        return
      }

      visualViewport = window.visualViewport

      resizeHandler = () => {
        if (this.isOpen) {
          this.updateSheetPosition()
        }
      }

      focusHandler = (event: FocusEvent) => {
        if (this.isOpen) {
          this.handleFocus(event)
        }
      }

      visualViewport.addEventListener("resize", resizeHandler)
      visualViewport.addEventListener("scroll", resizeHandler)

      document.addEventListener("focusin", focusHandler as EventListener)
    },

    updateSheetPosition() {
      const newKeyboardHeight = getKeyboardHeight()
      this.keyboardHeight = newKeyboardHeight
      this.isKeyboardVisible = newKeyboardHeight > 0
      this.maxSheetHeight = calculateMaxSheetHeight(newKeyboardHeight)
    },

    handleFocus(event: FocusEvent) {
      const target = event.target as HTMLElement

      if (
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT") &&
        this.$el.contains(target)
      ) {
        setTimeout(() => {
          this.updateSheetPosition()

          const sheetElement = this.$el as HTMLElement
          const targetRect = target.getBoundingClientRect()
          const sheetRect = sheetElement.getBoundingClientRect()

          const inputBottomRelativeToSheet = targetRect.bottom - sheetRect.top
          const sheetScrollTop = sheetElement.scrollTop || 0
          const sheetHeight = sheetRect.height

          const keyboardTopPosition = window.visualViewport?.height || window.innerHeight

          if (targetRect.bottom > keyboardTopPosition) {
            const scrollOffset = inputBottomRelativeToSheet - sheetHeight / 2
            const sheetContent = sheetElement.querySelector(".sheet-card") as HTMLElement

            if (sheetContent) {
              sheetContent.scrollTop = sheetScrollTop + scrollOffset
            }
          }
        }, 300)
      }
    },

    cleanup() {
      if (visualViewport && resizeHandler) {
        visualViewport.removeEventListener("resize", resizeHandler)
        visualViewport.removeEventListener("scroll", resizeHandler)
      }

      if (focusHandler) {
        document.removeEventListener("focusin", focusHandler as EventListener)
      }

      this.keyboardHeight = 0
      this.isKeyboardVisible = false
      this.maxSheetHeight = "85vh"
    },
  }
}

export { sheet }
export type { SheetData }
