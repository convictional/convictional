import { useEffect, useState } from "react"

import { useResearchProgress } from "./hooks/useResearchProgress"

// Focus a temporary off-screen input synchronously within the user-gesture
// call stack so mobile Safari "claims" the keyboard, then dispatch the
// event. The overlay transfers focus to the real input once it mounts.
function claimKeyboardAndDispatch(eventName: string) {
  const tmp = document.createElement("input")
  tmp.style.position = "fixed"
  tmp.style.opacity = "0"
  tmp.style.top = "0"
  tmp.style.left = "0"
  tmp.style.width = "1px"
  tmp.style.height = "1px"
  document.body.appendChild(tmp)
  tmp.focus()
  window.dispatchEvent(new CustomEvent(eventName))
  setTimeout(() => tmp.remove(), 500)
}

export function MobileTopBar() {
  const [researchOpen, setResearchOpen] = useState(false)
  const { pending_research_questions: questions } = useResearchProgress()
  const inProgress = questions.length > 0

  useEffect(() => {
    const onResearchOpen = () => setResearchOpen(true)
    const onResearchClose = () => setResearchOpen(false)
    window.addEventListener("research-dialog:open", onResearchOpen)
    window.addEventListener("research-dialog:closed", onResearchClose)
    return () => {
      window.removeEventListener("research-dialog:open", onResearchOpen)
      window.removeEventListener("research-dialog:closed", onResearchClose)
    }
  }, [])

  return (
    <div
      className={`w-full flex items-center rounded-full border transition-all h-[48px] ${
        researchOpen ? "bg-base-300 border-base-400 shadow-xs" : "bg-base-200/80 border-base-300"
      }`}
    >
      <button
        type="button"
        onClick={() => claimKeyboardAndDispatch("research-dialog:open")}
        aria-label="Research"
        className={`flex-1 flex items-center gap-3 px-4 py-2.5 rounded-full cursor-pointer transition-colors ${
          researchOpen || inProgress ? "text-primary" : "text-base-content/50 active:text-base-content/70"
        }`}
      >
        <span className={`material-symbols-outlined text-lg ${inProgress ? "animate-pulse" : ""}`}>auto_awesome</span>
        <span className="text-base">Research...</span>
      </button>
      <button
        type="button"
        onClick={() => claimKeyboardAndDispatch("mobile-search:open")}
        aria-label="Search"
        className="flex items-center justify-center p-1.5 mr-0.5 cursor-pointer"
      >
        <span className="material-symbols-outlined text-lg w-8 h-8 flex items-center justify-center rounded-full bg-base-content/8 text-base-content/50 active:bg-base-content/15">
          search
        </span>
      </button>
    </div>
  )
}
