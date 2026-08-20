import { install, uninstall } from "@github/hotkey"

/**
 * Initialize hotkeys for all elements with data-hotkey attributes
 */
export function initializeHotkeys(root: Document | HTMLElement = document): void {
  const elements = root.querySelectorAll<HTMLElement>("[data-hotkey]")
  elements.forEach(el => {
    install(el)
  })
}

/**
 * Uninstall hotkeys from an element or all elements in a root
 */
export function uninstallHotkeys(root: Document | HTMLElement): void {
  const elements = root.querySelectorAll<HTMLElement>("[data-hotkey]")
  elements.forEach(el => {
    uninstall(el)
  })
}
