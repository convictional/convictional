// Playwright/CDP screencasts capture page content, not the OS compositor, so the
// real mouse cursor never appears in recordings. This injects a synthetic cursor
// that follows the (real) mousemove events Playwright dispatches. It stays hidden
// until the first movement so it never shows parked in the top-left corner (and
// re-hides on navigation, since add_init_script re-runs per document).
;(() => {
  const CURSOR_ID = "__demo_cursor__"
  if (document.getElementById(CURSOR_ID)) return

  const dot = document.createElement("div")
  dot.id = CURSOR_ID
  dot.style.cssText = [
    "position:fixed",
    "top:0",
    "left:0",
    "width:22px",
    "height:22px",
    "margin-left:-11px",
    "margin-top:-11px",
    "border-radius:50%",
    "background:rgba(20,20,20,0.35)",
    "border:2px solid rgba(255,255,255,0.95)",
    "box-shadow:0 1px 5px rgba(0,0,0,0.45)",
    "pointer-events:none",
    "z-index:2147483647",
    "opacity:0",
    "transition:opacity .16s ease,width .09s ease,height .09s ease,background .09s ease",
  ].join(";")

  const attach = () => document.body && document.body.appendChild(dot)

  document.addEventListener("mousemove", (e) => {
    dot.style.left = e.clientX + "px"
    dot.style.top = e.clientY + "px"
    dot.style.opacity = "1"
  })
  document.addEventListener("mousedown", () => {
    dot.style.width = "14px"
    dot.style.height = "14px"
    dot.style.background = "rgba(20,20,20,0.55)"
  })
  document.addEventListener("mouseup", () => {
    dot.style.width = "22px"
    dot.style.height = "22px"
    dot.style.background = "rgba(20,20,20,0.35)"
  })

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attach)
  } else {
    attach()
  }
})()
