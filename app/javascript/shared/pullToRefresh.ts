// Custom pull-to-refresh for mobile. WKWebView exposes no Safari
// pull-to-refresh, and react-native-webview's native UIRefreshControl gives no
// drag feedback. A progress ring starts hidden above the top edge and slides
// down with the drag (following the header as the page rubber-bands down),
// filling as it goes. Crossing the threshold pops the ring; releasing past it
// reserves a clear band at the top, spins there, and reloads. Eagerly imported
// from main.ts and spa.tsx like themeApplicator so it covers legacy and SPA.
//
// Native app only: mobile web keeps the browser's own pull-to-refresh, so this
// installs solely inside the WebView shell (detected via isNativeShell).

import { isNativeShell } from "~/nativeShell"
import { isScrollLocked } from "~/shared/scrollLock"

// Compared against the resisted pull, so the finger travels ~2.2x this.
const THRESHOLD_PX = 90
// Ring trails the finger rather than tracking it 1:1.
const RESISTANCE = 0.45
// How far above the top edge the ring hides at rest. Larger = more clearance
// before it appears, so it doesn't graze the header early in the pull.
const RING_HIDE_OFFSET = 48
// Reserved clear band (added to the body's safe-area padding) the spinner sits
// in while refreshing, so it never overlaps content.
const REFRESH_BAND_PX = 56
// Ring's resting offset (within the reserved band) while refreshing.
const REST_Y = 12
const RING_RADIUS = 16
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS
const SVGNS = "http://www.w3.org/2000/svg"

function circle(className: string): SVGCircleElement {
  const c = document.createElementNS(SVGNS, "circle")
  c.setAttribute("cx", "18")
  c.setAttribute("cy", "18")
  c.setAttribute("r", String(RING_RADIUS))
  c.setAttribute("fill", "none")
  c.setAttribute("stroke", "currentColor")
  c.setAttribute("stroke-width", "3")
  c.setAttribute("class", className)
  return c
}

function install() {
  // root owns position + follow (transform is fully JS-controlled, so nothing
  // fights it). The inner pill owns the pop/spin transforms, kept off root so
  // they can't perturb the horizontal centering.
  const root = document.createElement("div")
  root.className = "fixed left-1/2 z-[60] pointer-events-none"
  root.style.top = "var(--safe-area-inset-top)"

  const pill = document.createElement("div")
  // Transparent wrapper: no background/shadow, only the ring shows. The padding
  // is kept because it sets the ring's spacing/position.
  pill.className = "flex items-center justify-center p-1.5"

  const svg = document.createElementNS(SVGNS, "svg")
  svg.setAttribute("width", "24")
  svg.setAttribute("height", "24")
  svg.setAttribute("viewBox", "0 0 36 36")
  svg.style.transform = "rotate(-90deg)" // fill from 12 o'clock, not 3

  const progress = circle("text-primary")
  progress.setAttribute("stroke-linecap", "round")
  progress.setAttribute("stroke-dasharray", String(RING_CIRCUMFERENCE))
  progress.setAttribute("stroke-dashoffset", String(RING_CIRCUMFERENCE))

  svg.append(circle("text-base-content/15"), progress)
  pill.appendChild(svg)
  root.appendChild(pill)
  document.body.appendChild(root)

  let startY: number | null = null
  let pull = 0
  let armed = false
  let refreshing = false

  const render = () => {
    // hx-boost swaps <body> on legacy-page navigation, detaching the ring;
    // re-attach so it survives without coupling this module to htmx events.
    if (!root.isConnected) document.body.appendChild(root)
    const p = Math.min(pull / THRESHOLD_PX, 1)
    root.style.transform = `translateX(-50%) translateY(${pull - RING_HIDE_OFFSET}px)`
    root.style.opacity = String(p)
    progress.setAttribute("stroke-dashoffset", String(RING_CIRCUMFERENCE * (1 - p)))
    if (p >= 1 && !armed) {
      armed = true
      // Micro pop when the threshold is reached — the "release to refresh" cue.
      pill.animate([{ transform: "scale(1)" }, { transform: "scale(1.25)" }, { transform: "scale(1)" }], {
        duration: 200,
        easing: "ease-out",
      })
    } else if (p < 1) {
      armed = false
    }
  }
  render()

  const trigger = () => {
    refreshing = true
    // Retract into the reserved band and hold there, spinning.
    root.style.transition = "transform 200ms ease, opacity 200ms ease"
    root.style.transform = `translateX(-50%) translateY(${REST_Y}px)`
    root.style.opacity = "1"
    // Indeterminate spinner: a quarter arc that rotates until the reload lands.
    progress.setAttribute("stroke-dashoffset", String(RING_CIRCUMFERENCE * 0.75))
    pill.animate([{ transform: "rotate(0deg)" }, { transform: "rotate(360deg)" }], {
      duration: 700,
      iterations: Infinity,
    })
    // Push content down so the spinner has clearance instead of covering it.
    document.body.style.transition = "padding-top 200ms ease"
    document.body.style.paddingTop = `calc(var(--safe-area-inset-top) + ${REFRESH_BAND_PX}px)`
    // Let the retract + a beat of spin show before navigating away.
    window.setTimeout(() => window.location.reload(), 400)
  }

  document.addEventListener(
    "touchstart",
    e => {
      if (refreshing) return
      // Only arm at the very top with no overlay open; anywhere else (or while a
      // sheet/dialog owns scrolling via the shared scroll lock) this is a normal
      // scroll.
      startY = window.scrollY <= 0 && !isScrollLocked() ? e.touches[0].clientY : null
      pull = 0
      root.style.transition = "none" // track the finger 1:1 while dragging
    },
    { passive: true }
  )
  document.addEventListener(
    "touchmove",
    e => {
      if (refreshing || startY === null) return
      const delta = e.touches[0].clientY - startY
      pull = delta > 0 ? delta * RESISTANCE : 0
      render()
    },
    { passive: true }
  )
  const retract = () => {
    root.style.transition = "transform 200ms ease, opacity 200ms ease"
    pull = 0
    armed = false
    render()
  }

  document.addEventListener("touchend", () => {
    if (refreshing || startY === null) return
    startY = null
    if (pull >= THRESHOLD_PX) {
      trigger()
      return
    }
    retract()
  })
  // iOS fires touchcancel (not touchend) when the system steals the touch —
  // incoming call, Control Center swipe. Without this the ring stays stuck
  // mid-pull until the next gesture.
  document.addEventListener("touchcancel", () => {
    if (refreshing || startY === null) return
    startY = null
    retract()
  })
}

if (isNativeShell()) {
  if (document.body) install()
  else document.addEventListener("DOMContentLoaded", install, { once: true })
}
