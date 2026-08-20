import type { AlpineComponent } from "alpinejs"

import { isNativeShell } from "~/nativeShell"

interface PwaInstallPromptParams {
  isIOS?: boolean
  isMobile?: boolean
}

interface PwaInstallPromptData {
  canInstall: boolean
  isInstalled: boolean
  showPrompt: boolean
  isIOS: boolean
  isMobile: boolean
  deferredPrompt: BeforeInstallPromptEvent | null
  beforeInstallPromptHandler?: (e: Event) => void
  appInstalledHandler?: () => void
  init: () => void
  destroy: () => void
  install: () => Promise<void>
  dismiss: () => void
  isDismissedRecently: () => boolean
}

const DISMISSAL_DAYS = 30
const STORAGE_KEY = "pwa-install-dismissed-at"

export function pwaInstallPrompt(params: PwaInstallPromptParams = {}): AlpineComponent<PwaInstallPromptData> {
  return {
    canInstall: false,
    isInstalled: false,
    showPrompt: false,
    isIOS: params.isIOS ?? false,
    isMobile: params.isMobile ?? false,
    deferredPrompt: null,

    isDismissedRecently() {
      try {
        const dismissedAt = localStorage.getItem(STORAGE_KEY)
        if (!dismissedAt) {
          return false
        }

        const dismissedDate = new Date(dismissedAt)
        const daysSinceDismissal = (Date.now() - dismissedDate.getTime()) / (1000 * 60 * 60 * 24)
        return daysSinceDismissal < DISMISSAL_DAYS
      } catch {
        return false
      }
    },

    init() {
      // Inside the native shell the user already has the app installed —
      // showing an Install-as-PWA banner would be at best redundant and at
      // worst broken (Safari's Add-to-Home-Screen instructions don't apply
      // when the page is running inside the React Native WebView).
      if (isNativeShell()) {
        return
      }

      this.isInstalled =
        window.matchMedia("(display-mode: standalone)").matches ||
        (window.navigator as Navigator & { standalone?: boolean }).standalone === true

      if (this.isInstalled) {
        return
      }

      this.beforeInstallPromptHandler = (e: Event) => {
        e.preventDefault()
        this.deferredPrompt = e as BeforeInstallPromptEvent
        this.canInstall = true

        // Only show prompt on mobile devices
        if (this.isMobile && !this.isDismissedRecently()) {
          this.showPrompt = true
        }
      }

      this.appInstalledHandler = () => {
        this.isInstalled = true
        this.canInstall = false
        this.showPrompt = false
        this.deferredPrompt = null
      }

      window.addEventListener("beforeinstallprompt", this.beforeInstallPromptHandler)
      window.addEventListener("appinstalled", this.appInstalledHandler)

      // For iOS devices, show prompt if not dismissed recently
      if (this.isIOS && !this.isDismissedRecently()) {
        setTimeout(() => {
          this.showPrompt = true
        }, 2000)
      }
    },

    destroy() {
      if (this.beforeInstallPromptHandler) {
        window.removeEventListener("beforeinstallprompt", this.beforeInstallPromptHandler)
      }
      if (this.appInstalledHandler) {
        window.removeEventListener("appinstalled", this.appInstalledHandler)
      }
    },

    async install() {
      if (!this.deferredPrompt) {
        return
      }

      this.showPrompt = false

      try {
        await this.deferredPrompt.prompt()
        const { outcome } = await this.deferredPrompt.userChoice

        if (outcome === "accepted") {
          this.canInstall = false
        }

        this.deferredPrompt = null
        this.dismiss()
      } catch (error) {
        console.error("Error during PWA installation:", error)
      }
    },

    dismiss() {
      this.showPrompt = false

      try {
        localStorage.setItem(STORAGE_KEY, new Date().toISOString())
      } catch (error) {
        console.error("Error saving PWA dismissal:", error)
      }
    },
  }
}
