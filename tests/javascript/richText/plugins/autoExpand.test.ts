import { expect, test, describe, beforeEach, vi, afterEach } from "vitest"
import autoExpand from "../../../../app/javascript/richText/plugins/autoExpand"

describe("autoExpand plugin", () => {
  let editorDom: HTMLDivElement
  let mockView: any
  let pluginViewReturn: { update: (view: any, prevState: any) => void; destroy?: () => void }
  let mockVisualViewport: EventTarget & { height: number }

  beforeEach(() => {
    editorDom = document.createElement("div")
    Object.defineProperty(editorDom, "scrollHeight", { value: 48, writable: true, configurable: true })

    mockView = {
      dom: editorDom,
      state: { doc: { content: "initial" } },
    }

    // jsdom doesn't have visualViewport — provide a mock with height
    mockVisualViewport = Object.assign(new EventTarget(), { height: 800 })
    Object.defineProperty(window, "visualViewport", { value: mockVisualViewport, writable: true, configurable: true })
  })

  afterEach(() => {
    pluginViewReturn?.destroy?.()
    vi.restoreAllMocks()
  })

  test("sets height to scrollHeight on mount", () => {
    const plugin = autoExpand()
    const viewSpec = plugin.spec.view!
    pluginViewReturn = (viewSpec as (view: any) => any)(mockView)

    expect(editorDom.style.height).toBe("48px")
    expect(editorDom.style.maxHeight).toBe("320px") // min(384, 800 * 0.4)
  })

  test("expands height when content grows", () => {
    const plugin = autoExpand()
    const viewSpec = plugin.spec.view!
    pluginViewReturn = (viewSpec as (view: any) => any)(mockView)

    expect(editorDom.style.height).toBe("48px")

    // Simulate content growth
    const prevState = { doc: mockView.state.doc }
    mockView.state = { doc: { content: "updated with more text" } }
    Object.defineProperty(editorDom, "scrollHeight", { value: 120, writable: true, configurable: true })

    pluginViewReturn.update(mockView, prevState)

    expect(editorDom.style.height).toBe("120px")
  })

  test("shrinks height when content is deleted", () => {
    Object.defineProperty(editorDom, "scrollHeight", { value: 120, writable: true, configurable: true })

    const plugin = autoExpand()
    const viewSpec = plugin.spec.view!
    pluginViewReturn = (viewSpec as (view: any) => any)(mockView)

    expect(editorDom.style.height).toBe("120px")

    // Simulate content deletion
    const prevState = { doc: mockView.state.doc }
    mockView.state = { doc: { content: "short" } }
    Object.defineProperty(editorDom, "scrollHeight", { value: 48, writable: true, configurable: true })

    pluginViewReturn.update(mockView, prevState)

    expect(editorDom.style.height).toBe("48px")
  })

  test("caps height at maxHeight and sets overflow", () => {
    mockVisualViewport.height = 1200 // large viewport so px cap (384) wins
    Object.defineProperty(editorDom, "scrollHeight", { value: 500, writable: true, configurable: true })

    const plugin = autoExpand()
    const viewSpec = plugin.spec.view!
    pluginViewReturn = (viewSpec as (view: any) => any)(mockView)

    expect(editorDom.style.height).toBe("384px")
    expect(editorDom.style.overflowY).toBe("auto")
  })

  test("caps height at viewport ratio on small screens", () => {
    mockVisualViewport.height = 667 // iPhone-size viewport
    Object.defineProperty(editorDom, "scrollHeight", { value: 500, writable: true, configurable: true })

    const plugin = autoExpand()
    const viewSpec = plugin.spec.view!
    pluginViewReturn = (viewSpec as (view: any) => any)(mockView)

    // min(384, 667 * 0.4) = min(384, 266.8) = 266.8
    expect(parseFloat(editorDom.style.height)).toBeCloseTo(266.8, 0)
    expect(editorDom.style.overflowY).toBe("auto")
  })

  test("does not update when doc has not changed", () => {
    const plugin = autoExpand()
    const viewSpec = plugin.spec.view!
    pluginViewReturn = (viewSpec as (view: any) => any)(mockView)

    expect(editorDom.style.height).toBe("48px")

    // Simulate update where doc has not changed (same reference)
    const prevState = { doc: mockView.state.doc }
    Object.defineProperty(editorDom, "scrollHeight", { value: 200, writable: true, configurable: true })

    pluginViewReturn.update(mockView, prevState)

    // Height should remain unchanged since doc did not change
    expect(editorDom.style.height).toBe("48px")
  })

  test("re-clamps height when viewport resizes", () => {
    mockVisualViewport.height = 1200
    Object.defineProperty(editorDom, "scrollHeight", { value: 500, writable: true, configurable: true })

    const plugin = autoExpand()
    const viewSpec = plugin.spec.view!
    pluginViewReturn = (viewSpec as (view: any) => any)(mockView)

    expect(editorDom.style.height).toBe("384px")

    // Simulate keyboard opening — viewport shrinks
    mockVisualViewport.height = 400
    mockVisualViewport.dispatchEvent(new Event("resize"))

    // min(384, 400 * 0.4) = 160
    expect(editorDom.style.height).toBe("160px")
    expect(editorDom.style.overflowY).toBe("auto")
  })

  test("cleans up viewport listener on destroy", () => {
    const removeSpy = vi.spyOn(mockVisualViewport, "removeEventListener")

    const plugin = autoExpand()
    const viewSpec = plugin.spec.view!
    pluginViewReturn = (viewSpec as (view: any) => any)(mockView)
    pluginViewReturn.destroy!()

    expect(removeSpy).toHaveBeenCalledWith("resize", expect.any(Function))
  })
})
