// Renders an on-screen keycap for each real keydown event Playwright dispatches, so
// keyboard-driven demos (e.g. ⌘K) visibly show the keys being pressed. Injected via
// context.add_init_script; re-runs per document.
;(() => {
  const ID = "__demo_keys__"
  if (document.getElementById(ID)) return

  const wrap = document.createElement("div")
  wrap.id = ID
  wrap.style.cssText = [
    "position:fixed",
    "bottom:28px",
    "left:50%",
    "transform:translateX(-50%)",
    "z-index:2147483647",
    "pointer-events:none",
    "display:flex",
    "gap:6px",
  ].join(";")

  const attach = () => document.body && document.body.appendChild(wrap)

  const SPECIAL = {
    Enter: "⏎",
    Backspace: "⌫",
    Escape: "esc",
    Tab: "⇥",
    " ": "space",
    ArrowUp: "↑",
    ArrowDown: "↓",
    ArrowLeft: "←",
    ArrowRight: "→",
  }

  function label(e) {
    const mods = []
    if (e.metaKey) mods.push("⌘")
    if (e.ctrlKey) mods.push("⌃")
    if (e.altKey) mods.push("⌥")
    if (e.shiftKey && e.key.length > 1) mods.push("⇧")
    let key = e.key
    if (SPECIAL[key]) key = SPECIAL[key]
    else if (key.length === 1 && mods.length) key = key.toUpperCase()
    return mods.join("") + key
  }

  let timer = null
  const show = (e) => {
    if (["Meta", "Control", "Alt", "Shift"].includes(e.key)) return
    // Only surface chorded shortcuts (⌘K etc.); plain keystrokes are already echoed
    // by whatever input has focus, so showing them would just be noise.
    if (!(e.metaKey || e.ctrlKey || e.altKey)) return

    const cap = document.createElement("div")
    cap.textContent = label(e)
    cap.style.cssText = [
      "font:600 22px -apple-system,system-ui,sans-serif",
      "color:#fff",
      "background:rgba(20,20,20,0.85)",
      "border-radius:10px",
      "padding:8px 14px",
      "min-width:44px",
      "box-sizing:border-box",
      "display:inline-flex",
      "align-items:center",
      "justify-content:center",
      "box-shadow:0 2px 12px rgba(0,0,0,0.4)",
      "opacity:0",
      "transition:opacity .1s ease",
    ].join(";")

    // Single badge that updates per keystroke, then fades once typing pauses.
    wrap.replaceChildren(cap)
    requestAnimationFrame(() => {
      cap.style.opacity = "1"
    })
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      cap.style.opacity = "0"
    }, 1300)
  }
  // Capture phase + registered from an init script (before app handlers) so shortcut
  // keys like ⌘K are seen even though the app's global hotkey handler consumes them.
  document.addEventListener("keydown", show, true)

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attach)
  } else {
    attach()
  }
})()
