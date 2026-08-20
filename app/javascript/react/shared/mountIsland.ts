import { QueryClientProvider } from "@tanstack/react-query"
import { type ReactNode, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import { queryClient } from "~/react/shared/queryClient"
import { IslandErrorBoundary } from "~/react/ui/IslandErrorBoundary"

declare global {
  interface Window {
    __convictionalIslandRoots?: Map<string, { root: Root; element: HTMLElement }>
    __convictionalIslandSwapListenerBound?: boolean
    __convictionalIslandRemovalObserverBound?: boolean
  }
}

// The island root registry lives on window so a second evaluation of this
// module in the same realm reuses the one registry instead of creating a
// parallel Map (and, below, a duplicate htmx:beforeSwap listener). A duplicate
// of either is retained forever by the persistent top document and would leak
// every island's fiber tree.
const activeRoots = (window.__convictionalIslandRoots ??= new Map<string, { root: Root; element: HTMLElement }>())

export function mountIsland<P = Record<string, unknown>>(elementId: string, render: (props: P) => ReactNode): void {
  const el = document.getElementById(elementId)
  if (!el) return

  // Already mounted — skip unless the original element was detached from the
  // DOM (e.g. during a page swap that didn't clean up this root).
  const existing = activeRoots.get(elementId)
  if (existing) {
    if (existing.element.isConnected) return
    existing.root.unmount()
    activeRoots.delete(elementId)
  }

  const props: P = el.dataset.props ? JSON.parse(el.dataset.props) : {}
  const root = createRoot(el)
  // Every island shares the one queryClient singleton (shared/queryClient.ts), so
  // a resource fetched in one island and a channel patch in another reach the
  // same cache. The SPA root (spa.tsx) provides the same client.
  root.render(
    createElement(
      IslandErrorBoundary,
      null,
      createElement(QueryClientProvider, { client: queryClient }, render(props))
    )
  )
  activeRoots.set(elementId, { root, element: el })
}

function unmountIsland(elementId: string): void {
  const existing = activeRoots.get(elementId)
  if (existing) {
    existing.root.unmount()
    activeRoots.delete(elementId)
  }
}

function unmountAll(): void {
  for (const id of [...activeRoots.keys()]) {
    unmountIsland(id)
  }
}

// Unmount any island whose host element has left the document. handleBeforeSwap
// only covers htmx boost swaps; this is the catch-all for every other removal
// path — React re-renders that replace a parent, chat/comment list-row swaps,
// SPA route changes, manual DOM edits. Without it a removed island's root is
// never unmounted, so its fiber tree (and the detached DOM it references) is
// pinned by the registry forever. isConnected is false for hosts detached from
// the live tree; hx-preserve hosts stay connected (htmx moves them), so they're
// correctly skipped.
function pruneDetachedRoots(): void {
  for (const [id, { root, element }] of activeRoots) {
    if (element.isConnected) continue
    root.unmount()
    activeRoots.delete(id)
  }
}

function handleBeforeSwap(event: Event): void {
  const target = (event as CustomEvent).detail?.target as HTMLElement | undefined
  if (!target) return

  for (const id of [...activeRoots.keys()]) {
    const el = document.getElementById(id)
    if (!el) continue
    if (!(target.contains(el) || target === el)) continue
    // hx-preserve elements survive the swap — htmx moves the existing node
    // into the new fragment in handlePreservedElements (htmx.esm.js:1532).
    // Tearing down the React root here would defeat that and force a remount
    // on every boost navigation.
    if (el.hasAttribute("hx-preserve") || el.hasAttribute("data-hx-preserve")) continue
    unmountIsland(id)
  }
}

// HTMX replaces DOM regions on navigation (hx-boost) and swaps. React roots
// inside those regions must be unmounted first, otherwise React loses track of
// the DOM and leaks memory. This fires before HTMX touches the DOM. Bound once
// per window so a re-evaluated module instance doesn't add a second listener.
if (!window.__convictionalIslandSwapListenerBound) {
  window.__convictionalIslandSwapListenerBound = true
  document.addEventListener("htmx:beforeSwap", handleBeforeSwap)
}

// Navigation-agnostic backstop for handleBeforeSwap. A document-wide childList
// observer catches DOM removals from any source (React, SPA routing, htmx swaps
// beforeSwap's containment check misses), then prunes detached roots. Bound once
// per window so a re-evaluated module doesn't stack observers. The per-mutation
// work is trivial (schedule a frame) and the prune only runs when islands exist;
// it is coalesced to one pass per frame so a render storm can't thrash it.
if (!window.__convictionalIslandRemovalObserverBound) {
  window.__convictionalIslandRemovalObserverBound = true
  let scheduled = false
  const observer = new MutationObserver(mutations => {
    if (scheduled || activeRoots.size === 0) return
    // Only removals can detach an island host, so ignore insertion-only
    // mutations (e.g. typing into a chat input) instead of scheduling a prune.
    if (!mutations.some(m => m.removedNodes.length > 0)) return
    scheduled = true
    requestAnimationFrame(() => {
      scheduled = false
      pruneDetachedRoots()
    })
  })
  observer.observe(document.documentElement, { childList: true, subtree: true })
}

export { unmountIsland, unmountAll, pruneDetachedRoots, activeRoots }
