import { useState } from "react"

import { Tooltip } from "~/react/ui/Tooltip"

import { useTranscript } from "../hooks/useTranscript"
import type { MeetingDetail } from "../types"

import { ChatTab } from "./ChatTab"
import { CopyTranscriptButton } from "./CopyTranscriptButton"
import { TranscriptPanel } from "./TranscriptPanel"

interface TranscriptsToggleProps {
  meeting: MeetingDetail
  currentTime: number
  isProcessing: boolean
  onSeek: (seconds: number) => void
}

type SubTab = "audio" | "chat"

// Sub-tab strip + scroll container for the transcripts panel. Audio + Chat sit
// side-by-side here, rather than alongside Summary/Agenda in the main tab strip
// — they stay hidden behind a subtitles toggle as progressive disclosure.
export function TranscriptsToggle({ meeting, currentTime, isProcessing, onSeek }: TranscriptsToggleProps) {
  const [active, setActive] = useState<SubTab>("audio")
  // Lazy-mount Chat on first activation, then keep it mounted so re-opening is
  // instant and doesn't re-fetch.
  const [chatEverActive, setChatEverActive] = useState(false)
  const status = useTranscript(meeting.id, isProcessing)

  function activate(tab: SubTab) {
    setActive(tab)
    if (tab === "chat") setChatEverActive(true)
  }

  const lines = status.kind === "loaded" ? status.lines : null
  const hasChat = meeting.has_chat_messages

  return (
    <div className="border-t border-neutral">
      <div role="tablist" className="tabs tabs-border">
        {/* The copy control is a sibling of the tab button, not a child: a
            <button> can't legally contain another <button>. */}
        <div className={`tab grow flex items-center justify-center gap-2${active === "audio" ? " tab-active" : ""}`}>
          <button
            type="button"
            role="tab"
            aria-selected={active === "audio"}
            onClick={() => activate("audio")}
            className="cursor-pointer"
          >
            Audio
          </button>
          {lines && lines.length > 0 && <CopyTranscriptButton meeting={meeting} lines={lines} />}
        </div>
        {hasChat ? (
          <button
            type="button"
            role="tab"
            aria-selected={active === "chat"}
            onClick={() => activate("chat")}
            className={`tab grow cursor-pointer${active === "chat" ? " tab-active" : ""}`}
          >
            Chat
          </button>
        ) : (
          // No in-meeting chat: a non-interactive tab with an explanatory
          // tooltip.
          <span role="tab" aria-disabled className="tab grow cursor-default text-base-500">
            <Tooltip content="No in-meeting chat available">
              <span>Chat</span>
            </Tooltip>
          </span>
        )}
      </div>
      <div className="h-96 bg-base-200 p-2">
        <div className={active === "audio" ? "h-full" : "hidden"}>
          <TranscriptPanel status={status} currentTime={currentTime} hasRecording={true} onSeek={onSeek} />
        </div>
        {hasChat && chatEverActive && (
          <div className={`h-full overflow-y-auto ${active === "chat" ? "" : "hidden"}`}>
            <ChatTab meetingId={meeting.id} />
          </div>
        )}
      </div>
    </div>
  )
}
