import { install, uninstall } from "@github/hotkey"
import { useEffect } from "react"
import type { RefObject } from "react"

// React-side hotkey installation for dynamically rendered nodes:
// React components mount/unmount independently of the global initialization, so
// `data-hotkey` nodes must install themselves on mount and uninstall on unmount.
// When `enabled` is false (e.g., a popover is open and should swallow hotkey events),
// nothing is installed — `e` while the snooze popover is open should not archive.
//
// A MutationObserver keeps the installed set in sync as `data-hotkey` nodes come
// and go: the mailbox nav arrows only gain their `data-hotkey` once an async query
// resolves their neighbor, and the archive button toggles its `data-hotkey` as it
// flips between archive/unarchive. Installing only at mount would miss both, so the
// hotkey would silently never fire even though the button works.
export function useHotkeyInstall<T extends HTMLElement>(ref: RefObject<T | null>, enabled: boolean = true): void {
  useEffect(() => {
    const root = ref.current
    if (!root || !enabled) return

    let installed: HTMLElement[] = []

    const sync = () => {
      // Include the ref element itself if it has data-hotkey — querySelectorAll
      // only matches descendants, so a single-element use case (passing the
      // button's own ref, e.g. SearchButton/ResearchButton) would otherwise
      // install zero elements and the hotkey silently never fires.
      const descendants = Array.from(root.querySelectorAll<HTMLElement>("[data-hotkey]"))
      const next = root.hasAttribute("data-hotkey") ? [root, ...descendants] : descendants
      installed.forEach(el => {
        if (!next.includes(el)) uninstall(el)
      })
      next.forEach(el => {
        if (!installed.includes(el)) install(el)
      })
      installed = next
    }

    sync()
    const observer = new MutationObserver(sync)
    observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-hotkey"] })

    return () => {
      observer.disconnect()
      installed.forEach(el => uninstall(el))
    }
  }, [ref, enabled])
}
