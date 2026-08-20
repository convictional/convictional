import { expect, test, describe, vi, beforeEach, afterEach } from "vitest"
import { sheet } from "../../../app/javascript/shared/sheet"

describe("sheet", () => {
  let component: ReturnType<typeof sheet>
  let mockVisualViewport: Partial<VisualViewport>
  let originalVisualViewport: VisualViewport | undefined

  beforeEach(() => {
    originalVisualViewport = window.visualViewport

    mockVisualViewport = {
      height: 800,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }

    Object.defineProperty(window, "visualViewport", {
      writable: true,
      configurable: true,
      value: mockVisualViewport,
    })

    Object.defineProperty(window, "innerHeight", {
      writable: true,
      configurable: true,
      value: 800,
    })

    component = sheet()
  })

  afterEach(() => {
    Object.defineProperty(window, "visualViewport", {
      writable: true,
      configurable: true,
      value: originalVisualViewport,
    })
    vi.clearAllMocks()
  })

  describe("setupKeyboardHandlers", () => {
    test("sets up event listeners when visualViewport is available", () => {
      component.setupKeyboardHandlers()

      expect(mockVisualViewport.addEventListener).toHaveBeenCalledWith("resize", expect.any(Function))
      expect(mockVisualViewport.addEventListener).toHaveBeenCalledWith("scroll", expect.any(Function))
    })

    test("does not throw when visualViewport is unavailable", () => {
      Object.defineProperty(window, "visualViewport", {
        writable: true,
        configurable: true,
        value: undefined,
      })

      expect(() => component.setupKeyboardHandlers()).not.toThrow()
    })
  })

  describe("updateSheetPosition", () => {
    test("updates keyboard height when keyboard is not visible", () => {
      component.setupKeyboardHandlers()
      mockVisualViewport.height = 800
      Object.defineProperty(window, "innerHeight", { value: 800 })

      component.updateSheetPosition()

      expect(component.keyboardHeight).toBe(0)
      expect(component.isKeyboardVisible).toBe(false)
      expect(component.maxSheetHeight).toBe("85vh")
    })

    test("updates keyboard height when keyboard is visible", () => {
      component.setupKeyboardHandlers()
      mockVisualViewport.height = 400
      Object.defineProperty(window, "innerHeight", { value: 800 })

      component.updateSheetPosition()

      expect(component.keyboardHeight).toBe(400)
      expect(component.isKeyboardVisible).toBe(true)
      expect(component.maxSheetHeight).toBe("340px")
    })

    test("calculates maxSheetHeight as 85% of viewport when keyboard is visible", () => {
      component.setupKeyboardHandlers()
      mockVisualViewport.height = 500
      Object.defineProperty(window, "innerHeight", { value: 800 })

      component.updateSheetPosition()

      const expectedMaxHeight = Math.floor(500 * 0.85)
      expect(component.maxSheetHeight).toBe(`${expectedMaxHeight}px`)
    })
  })

  describe("handleFocus", () => {
    test("updates sheet position when input is focused", () => {
      vi.useFakeTimers()
      component.setupKeyboardHandlers()
      component.isOpen = true

      const input = document.createElement("input")
      const mockEl = document.createElement("div")
      mockEl.appendChild(input)

      component.$el = mockEl

      input.getBoundingClientRect = vi.fn(() => ({
        top: 100,
        bottom: 150,
        left: 0,
        right: 100,
        width: 100,
        height: 50,
        x: 0,
        y: 100,
        toJSON: () => ({}),
      }))

      mockEl.getBoundingClientRect = vi.fn(() => ({
        top: 0,
        bottom: 600,
        left: 0,
        right: 100,
        width: 100,
        height: 600,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }))

      mockVisualViewport.height = 400
      Object.defineProperty(window, "innerHeight", { value: 800 })

      const focusEvent = new FocusEvent("focusin", { relatedTarget: input })
      Object.defineProperty(focusEvent, "target", { value: input, writable: false })

      component.handleFocus(focusEvent)

      vi.advanceTimersByTime(300)

      expect(component.keyboardHeight).toBe(400)

      vi.useRealTimers()
    })

    test("ignores focus events on non-form elements", () => {
      vi.useFakeTimers()
      component.isOpen = true

      const div = document.createElement("div")
      const mockEl = document.createElement("div")
      mockEl.appendChild(div)

      component.$el = mockEl

      const originalKeyboardHeight = component.keyboardHeight

      const focusEvent = new FocusEvent("focusin", { relatedTarget: div })
      Object.defineProperty(focusEvent, "target", { value: div, writable: false })

      component.handleFocus(focusEvent)

      vi.advanceTimersByTime(300)

      expect(component.keyboardHeight).toBe(originalKeyboardHeight)

      vi.useRealTimers()
    })
  })

  describe("cleanup", () => {
    test("removes event listeners on cleanup", () => {
      component.setupKeyboardHandlers()
      component.cleanup()

      expect(mockVisualViewport.removeEventListener).toHaveBeenCalledWith("resize", expect.any(Function))
      expect(mockVisualViewport.removeEventListener).toHaveBeenCalledWith("scroll", expect.any(Function))
    })
  })
})
