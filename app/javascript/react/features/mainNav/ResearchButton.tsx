import { useEffect, useRef, useState } from "react"

import { useHotkeyInstall } from "~/react/shared/hooks/useHotkeyInstall"
import { Tooltip } from "~/react/ui/Tooltip"

import { type PendingResearchQuestion, useResearchProgress } from "./hooks/useResearchProgress"

// Mirrors `_research_button.html.jinja` — dispatches `research-dialog:open` on
// click, listens for `research-dialog:closed` from the existing
// `#react-research-dialog` island to clear active style.
export function ResearchButton() {
  const ref = useRef<HTMLButtonElement>(null)
  const [isOpen, setIsOpen] = useState(false)
  const { pending_research_questions: questions } = useResearchProgress()
  const inProgress = questions.length > 0

  useHotkeyInstall(ref)

  useEffect(() => {
    const onOpen = () => setIsOpen(true)
    const onClose = () => setIsOpen(false)
    window.addEventListener("research-dialog:open", onOpen)
    window.addEventListener("research-dialog:closed", onClose)
    return () => {
      window.removeEventListener("research-dialog:open", onOpen)
      window.removeEventListener("research-dialog:closed", onClose)
    }
  }, [])

  const handleClick = () => {
    window.dispatchEvent(new CustomEvent("research-dialog:open"))
  }

  const tooltipContent = inProgress ? <ResearchInProgressTooltip questions={questions} /> : "Research ⌘⇧K"

  return (
    <Tooltip content={tooltipContent} placement="bottom">
      <button
        ref={ref}
        type="button"
        data-hotkey="Meta+Shift+K"
        onClick={handleClick}
        aria-label="Deep Research"
        className={`flex items-center gap-1.5 pl-2 pr-2 sm:pr-3 py-1 rounded-full transition-all cursor-pointer ${
          isOpen
            ? "text-base-content bg-base-300 border border-base-400"
            : inProgress
              ? "text-primary border border-transparent"
              : "text-base-content hover:text-primary border border-transparent"
        }`}
      >
        <span className={`material-symbols-outlined text-sm ${inProgress ? "animate-pulse" : ""}`}>auto_awesome</span>
        <span className="text-sm hidden sm:inline">Research</span>
      </button>
    </Tooltip>
  )
}

function ResearchInProgressTooltip({ questions }: { questions: PendingResearchQuestion[] }) {
  return (
    <div className="flex flex-col gap-1 text-left">
      <div className="font-medium">Research in progress</div>
      <ul className="space-y-0.5">
        {questions.map(question => (
          <ResearchQuestionRow key={question.id} question={question} />
        ))}
      </ul>
      <div className="pt-1 mt-1 border-t border-base-content/20 text-base-content/60">Research ⌘⇧K</div>
    </div>
  )
}

function ResearchQuestionRow({ question }: { question: PendingResearchQuestion }) {
  return (
    <li className="flex items-center justify-between gap-2">
      <span className="flex-1 truncate">{question.title}</span>
      {question.research_created_at ? (
        <CountUpTimer startedAt={question.research_created_at} className="text-base-content/60 whitespace-nowrap" />
      ) : (
        <span className="italic text-base-content/60 whitespace-nowrap">Pending</span>
      )}
    </li>
  )
}

function CountUpTimer({ startedAt, className }: { startedAt: string; className?: string }) {
  const [text, setText] = useState(() => formatElapsed(startedAt))
  useEffect(() => {
    const id = window.setInterval(() => setText(formatElapsed(startedAt)), 1000)
    return () => window.clearInterval(id)
  }, [startedAt])
  return (
    <time dateTime={startedAt} className={className}>
      {text}
    </time>
  )
}

function formatElapsed(startedAt: string): string {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000))
  if (elapsedSeconds < 60) return `${elapsedSeconds}s`
  const minutes = Math.floor(elapsedSeconds / 60)
  const remaining = elapsedSeconds % 60
  return `${minutes}m ${remaining}s`
}
