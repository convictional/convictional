import { beforeEach, describe, expect, test, vi } from "vitest"
import { pwaInstallPrompt } from "../../../app/javascript/pwaInstall/component"

/**
 * Minimal BeforeInstallPromptEvent type for testing purposes.
 */
type BeforeInstallPromptEvent = {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>
}

describe("pwaInstallPrompt", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  describe("isDismissedRecently", () => {
    test("returns false when no dismissal recorded", () => {
      const component = pwaInstallPrompt()

      expect(component.isDismissedRecently()).toBe(false)
    })

    test("returns true when dismissed less than 30 days ago", () => {
      const component = pwaInstallPrompt()
      const twoDaysAgo = new Date()
      twoDaysAgo.setDate(twoDaysAgo.getDate() - 2)

      localStorage.setItem("pwa-install-dismissed-at", twoDaysAgo.toISOString())

      expect(component.isDismissedRecently()).toBe(true)
    })

    test("returns true when dismissed exactly 29 days ago", () => {
      const component = pwaInstallPrompt()
      const twentyNineDaysAgo = new Date()
      twentyNineDaysAgo.setDate(twentyNineDaysAgo.getDate() - 29)

      localStorage.setItem("pwa-install-dismissed-at", twentyNineDaysAgo.toISOString())

      expect(component.isDismissedRecently()).toBe(true)
    })

    test("returns false when dismissed exactly 30 days ago", () => {
      vi.useFakeTimers()
      try {
        const now = new Date("2026-03-31T12:00:00Z")
        vi.setSystemTime(now)

        const component = pwaInstallPrompt()
        const thirtyDaysAgo = new Date("2026-03-01T12:00:00Z")

        localStorage.setItem("pwa-install-dismissed-at", thirtyDaysAgo.toISOString())

        expect(component.isDismissedRecently()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    test("returns false when dismissed more than 30 days ago", () => {
      const component = pwaInstallPrompt()
      const fortyDaysAgo = new Date()
      fortyDaysAgo.setDate(fortyDaysAgo.getDate() - 40)

      localStorage.setItem("pwa-install-dismissed-at", fortyDaysAgo.toISOString())

      expect(component.isDismissedRecently()).toBe(false)
    })

    test("returns false when localStorage throws error", () => {
      const component = pwaInstallPrompt()
      const getItemSpy = vi.spyOn(Storage.prototype, "getItem")
      getItemSpy.mockImplementation(() => {
        throw new Error("localStorage error")
      })

      expect(component.isDismissedRecently()).toBe(false)

      getItemSpy.mockRestore()
    })

    test("returns false when localStorage contains invalid date", () => {
      const component = pwaInstallPrompt()

      localStorage.setItem("pwa-install-dismissed-at", "invalid-date")

      expect(component.isDismissedRecently()).toBe(false)
    })
  })

  describe("dismiss", () => {
    test("sets showPrompt to false", () => {
      const component = pwaInstallPrompt()
      component.showPrompt = true

      component.dismiss()

      expect(component.showPrompt).toBe(false)
    })

    test("saves dismissal timestamp to localStorage", () => {
      const component = pwaInstallPrompt()
      const beforeDismiss = new Date()

      component.dismiss()

      const savedTimestamp = localStorage.getItem("pwa-install-dismissed-at")
      expect(savedTimestamp).toBeTruthy()

      const savedDate = new Date(savedTimestamp!)
      expect(savedDate.getTime()).toBeGreaterThanOrEqual(beforeDismiss.getTime())
      expect(savedDate.getTime()).toBeLessThanOrEqual(new Date().getTime())
    })

    test("handles localStorage error gracefully", () => {
      const component = pwaInstallPrompt()
      const setItemSpy = vi.spyOn(Storage.prototype, "setItem")
      setItemSpy.mockImplementation(() => {
        throw new Error("localStorage error")
      })
      // dismiss() logs the swallowed error via console.error; expected here.
      const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})

      expect(() => component.dismiss()).not.toThrow()
      expect(component.showPrompt).toBe(false)

      setItemSpy.mockRestore()
      consoleError.mockRestore()
    })
  })

  describe("initial state", () => {
    test("has correct default values", () => {
      const component = pwaInstallPrompt()

      expect(component.canInstall).toBe(false)
      expect(component.isInstalled).toBe(false)
      expect(component.showPrompt).toBe(false)
      expect(component.deferredPrompt).toBe(null)
    })
  })

  describe("install", () => {
    test("does nothing when deferredPrompt is null", async () => {
      const component = pwaInstallPrompt()
      component.deferredPrompt = null

      await component.install()

      expect(component.showPrompt).toBe(false)
    })

    test("hides prompt when install is called", async () => {
      const component = pwaInstallPrompt()
      component.showPrompt = true

      const mockPrompt = vi.fn().mockResolvedValue(undefined)
      const mockUserChoice = Promise.resolve({ outcome: "accepted" as const, platform: "web" })

      component.deferredPrompt = {
        prompt: mockPrompt,
        userChoice: mockUserChoice,
      } as unknown as BeforeInstallPromptEvent

      await component.install()

      expect(component.showPrompt).toBe(false)
    })

    test("clears canInstall when user accepts", async () => {
      const component = pwaInstallPrompt()
      component.canInstall = true

      const mockPrompt = vi.fn().mockResolvedValue(undefined)
      const mockUserChoice = Promise.resolve({ outcome: "accepted" as const, platform: "web" })

      component.deferredPrompt = {
        prompt: mockPrompt,
        userChoice: mockUserChoice,
      } as unknown as BeforeInstallPromptEvent

      await component.install()

      expect(component.canInstall).toBe(false)
      expect(component.deferredPrompt).toBe(null)
    })

    test("keeps canInstall when user dismisses", async () => {
      const component = pwaInstallPrompt()
      component.canInstall = true

      const mockPrompt = vi.fn().mockResolvedValue(undefined)
      const mockUserChoice = Promise.resolve({ outcome: "dismissed" as const, platform: "web" })

      component.deferredPrompt = {
        prompt: mockPrompt,
        userChoice: mockUserChoice,
      } as unknown as BeforeInstallPromptEvent

      await component.install()

      expect(component.canInstall).toBe(true)
      expect(component.deferredPrompt).toBe(null)
    })
  })
})
