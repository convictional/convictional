import { useEffect } from "react"

// iOS address-bar shrink is ~60px; soft keyboard is typically 250px+. 150px sits
// comfortably between the two so we can distinguish keyboard-open from bar-resize.
const SOFT_KEYBOARD_THRESHOLD_PX = 150

// Toggled on <html> only for the quick snap-open reveal; main.css keys the nav
// and sticky-header transitions off it. Absent while hiding, where motion tracks
// the scroll gesture 1:1 and a transition would lag. (Name shared with main.css.)
const ANIMATING_CLASS = "nav-reveal-animating"

// Slides the nav wrapper (`[data-nav-sticky-wrapper]`, rendered by both
// layouts/application.html.jinja and app/AppShell.tsx) up on scroll-down and back
// on scroll-up. Rather than move each page's header by ref, it publishes the nav's
// visible height (`navHeight - hiddenPx`) as `--nav-reveal-offset` on <html>; every
// `.sticky-header` offsets its `top` off that (main.css) and slides in lockstep.
//
// Motion is asymmetric so it feels natural: scrolling DOWN hides the nav tracked
// 1:1 with the gesture, no transition (as if it were content scrolling off, no
// checkpoint); scrolling UP snaps it fully open with a 200ms transition.
//
// The Jinja wrapper is not hx-preserve'd (only the #react-main-nav island inside
// it is), so hx-boost swaps it for a fresh node. This controller lives in the
// preserved island and its effect never re-runs on navigation, so it re-acquires
// the wrapper on `htmx:afterSettle` — else it keeps mutating a detached node and
// silently stops after the first boost nav.
//
// Desktop-only: mobile hides the wrapper and uses a bottom tab bar, so callers
// gate `enabled` on !isMobile.
export function useRevealNavOnScroll(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return
    const root = document.documentElement

    // In PWA mode the status bar overlays the viewport; read the safe area
    // so sticky elements sit below the notch / time+battery.
    const safeAreaTop = parseFloat(getComputedStyle(root).getPropertyValue("--safe-area-inset-top")) || 0

    let nav: HTMLElement | null = null
    let navHeight = 0
    // How much of the nav is currently scrolled out of view, in [0, navHeight].
    let hiddenPx = 0
    // Start at Infinity so the first scroll after (re)acquire is a no-op rather
    // than a spurious reveal/hide of something the user didn't scroll.
    let lastY = Infinity

    const apply = (animate: boolean) => {
      if (!nav) return
      root.classList.toggle(ANIMATING_CLASS, animate)
      nav.style.transition = animate ? "top 200ms ease" : "none"
      nav.style.top = `${safeAreaTop - hiddenPx}px`
      // Header offset tracks the visible nav height: flush below the nav when
      // shown, flush to the viewport top (0) when hidden. No extra gap — a gap
      // leaves a band where content shows between the nav and the header.
      root.style.setProperty("--nav-reveal-offset", `${navHeight - hiddenPx}px`)
    }

    const styleNav = (el: HTMLElement) => {
      Object.assign(el.style, {
        position: "sticky",
        top: `${safeAreaTop}px`,
        zIndex: "40",
      })
      navHeight = el.offsetHeight
    }

    const acquire = () => {
      const current = document.querySelector<HTMLElement>("[data-nav-sticky-wrapper]")
      if (!current || current === nav) return
      nav = current
      styleNav(nav)
      // Fresh page (boost scrolls to top): nav fully shown, headers below it.
      hiddenPx = 0
      lastY = Infinity
      apply(false)
    }
    acquire()

    const onAfterSettle = () => acquire()
    document.body.addEventListener("htmx:afterSettle", onAfterSettle)

    // Suppress nav motion briefly after our own pin-to-bottom calls. The
    // sticky-`top` change interleaves with React's commit of those pins and
    // gives WebKit's scroll-anchor algorithm extra layout shifts to react to —
    // visible as scrollY snapping back when the user scrolls to bottom.
    let suppressUntil = 0
    const onProgrammaticScroll = () => {
      suppressUntil = performance.now() + 250
    }
    window.addEventListener("island:programmatic-scroll", onProgrammaticScroll)

    let resizeRafId = 0
    const onResize = () => {
      // rAF-coalesce so iOS address-bar storms (up to ~60Hz) don't force layout
      // on every event.
      if (resizeRafId) return
      resizeRafId = requestAnimationFrame(() => {
        resizeRafId = 0
        if (!nav) return
        navHeight = nav.offsetHeight
        // Re-clamp in case the nav shrank below the currently-hidden amount,
        // then re-publish: apply() is the only writer of --nav-reveal-offset, so
        // without this the offset (and headers) stay at the old height until the
        // next scroll.
        hiddenPx = Math.min(hiddenPx, navHeight)
        apply(false)
      })
    }
    window.addEventListener("resize", onResize)

    let rafId = 0
    let pendingY = 0
    const onScroll = () => {
      // Snapshot at schedule time, not inside the rAF — otherwise a rapid
      // reversal within a throttle window would compare the latest sample to
      // itself and miss the direction change.
      pendingY = window.scrollY
      if (rafId) return
      rafId = requestAnimationFrame(() => {
        rafId = 0
        if (!nav || !nav.isConnected) return
        if (performance.now() < suppressUntil) {
          // Programmatic scroll just fired (pin-to-bottom, scroll-to-divider);
          // skip so our top change doesn't compound the layout activity React is
          // committing in the same frame.
          lastY = pendingY
          return
        }
        // Don't move the nav while the soft keyboard is open. iOS scrolls the
        // page to keep the input visible, firing scroll events here; the motion
        // would fight the keyboard animation — visible as a "bounce".
        const vv = window.visualViewport
        if (vv && window.innerHeight - vv.height > SOFT_KEYBOARD_THRESHOLD_PX) {
          // Keep lastY current while suppressed (like the programmatic-scroll
          // guard above), so the first event after the keyboard closes isn't a
          // large spurious delta that hides the nav.
          lastY = pendingY
          return
        }
        const y = pendingY
        const dy = y - lastY
        lastY = y
        if (dy > 0) {
          // Scrolling down: hide tracked 1:1 with the gesture, no transition.
          const next = Math.min(navHeight, hiddenPx + dy)
          if (next === hiddenPx) return
          hiddenPx = next
          apply(false)
        } else if (dy < 0 && hiddenPx > 0) {
          // Scrolling up: quick reveal — snap fully open with a transition.
          hiddenPx = 0
          apply(true)
        }
      })
    }
    window.addEventListener("scroll", onScroll, { passive: true })

    return () => {
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onResize)
      window.removeEventListener("island:programmatic-scroll", onProgrammaticScroll)
      document.body.removeEventListener("htmx:afterSettle", onAfterSettle)
      if (rafId) cancelAnimationFrame(rafId)
      if (resizeRafId) cancelAnimationFrame(resizeRafId)
      root.classList.remove(ANIMATING_CLASS)
      if (nav) {
        nav.style.position = ""
        nav.style.top = ""
        nav.style.zIndex = ""
        nav.style.transition = ""
      }
      root.style.removeProperty("--nav-reveal-offset")
    }
  }, [enabled])
}
