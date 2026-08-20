import { useCallback, useEffect, useRef, useState } from "react"
import type { ReactNode } from "react"

import { BackButton } from "~/react/composites/BackButton"
import type { BackNavigation } from "~/react/shared/types"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { Tooltip } from "~/react/ui/Tooltip"

import { AttendeesPanel } from "./components/AttendeesPanel"
import { CopyTimestampButton } from "./components/CopyTimestampButton"
import { Header } from "./components/Header"
import { MeetingTitle } from "./components/MeetingTitle"
import { RecallStatusBadge } from "./components/RecallStatusBadge"
import { Tabs } from "./components/Tabs"
import { TranscriptsToggle } from "./components/TranscriptsToggle"
import { VideoPlayer } from "./components/VideoPlayer"
import { VideoUploadForm } from "./components/VideoUploadForm"
import type { MeetingBotState, MeetingDetail } from "./types"

// How often to re-poll a still-processing meeting so it advances to the
// finished view without a manual reload.
const PROCESSING_POLL_MS = 3000

interface CompletedViewProps {
  meeting: MeetingDetail
  bot: MeetingBotState | null
  back: BackNavigation
  onLocalUpdate: <K extends keyof MeetingDetail>(field: K, value: MeetingDetail[K]) => void
  onServerUpdate: (meeting: MeetingDetail) => void
  refetch: () => void | Promise<void>
}

export function CompletedView({ meeting, bot, back, onLocalUpdate, onServerUpdate, refetch }: CompletedViewProps) {
  // Lifted to the parent so VideoPlayer (writer) and TranscriptsToggle (reader)
  // share one source of truth for playback position. Throttled by VideoPlayer
  // to 250ms, so the transcript re-renders at most ~4x/second.
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [currentTime, setCurrentTime] = useState(0)

  // Audio + Chat live behind the subtitles toggle. Mounted lazily on first
  // reveal and kept mounted afterward so re-opening doesn't re-fetch the
  // transcript.
  const [showTranscripts, setShowTranscripts] = useState(false)
  const [transcriptsEverShown, setTranscriptsEverShown] = useState(false)

  const seek = useCallback((seconds: number) => {
    const videoEl = videoRef.current
    if (!videoEl) return
    videoEl.currentTime = seconds
  }, [])

  function toggleTranscripts() {
    setShowTranscripts(prev => {
      const next = !prev
      if (next) setTranscriptsEverShown(true)
      return next
    })
  }

  // A meeting with no raw transcript yet, or with an initial-processing job
  // still running, is not ready. Within that gate the terminal-or-transient
  // outcomes are: a hard recording failure, a meeting that will never be
  // processed, or genuine in-flight processing.
  const inProcessingGate = !meeting.has_transcript || meeting.is_initial_processing
  const recordingFailed = inProcessingGate && meeting.did_recording_fail
  // Something is actively advancing the meeting toward a transcript: an in-app
  // processing job, or a bot still recording or transcribing.
  const isProcessingActive =
    meeting.is_initial_processing || (!!bot && (bot.is_recording_in_progress || bot.is_processing_transcript))
  // A finished meeting that produced no transcript with nothing in flight to
  // produce one will never be processed — a terminal state, not an endless
  // spinner. (This view only ever renders non-upcoming meetings; see MeetingShow.)
  const isUnrecorded = inProcessingGate && !recordingFailed && !isProcessingActive && meeting.is_completed
  const isProcessing = inProcessingGate && !recordingFailed && !isUnrecorded

  // Poll while processing so a meeting opened mid-processing advances without a
  // manual reload — this also covers non-bot meetings (uploads, pasted
  // transcripts) that have no channel push to lean on.
  useEffect(() => {
    if (!isProcessing) return
    const interval = setInterval(() => void refetch(), PROCESSING_POLL_MS)
    return () => clearInterval(interval)
  }, [isProcessing, refetch])

  // The recording-failed, unrecorded, and processing states intentionally omit
  // the editable header and video card, rendering only the status message plus
  // the agenda/summary content while a meeting is not ready.
  if (recordingFailed) {
    return (
      <NonReadyState back={back} meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate}>
        <div className="flex flex-col items-center justify-center py-12">
          <div className="text-center space-y-4 max-w-md">
            <span className="material-symbols-outlined text-5xl text-base-400">videocam_off</span>
            <p className="font-semibold">Convictional&apos;s meeting bot couldn&apos;t record this meeting.</p>
            {bot && <RecallStatusBadge bot={bot} />}
          </div>
        </div>
      </NonReadyState>
    )
  }

  if (isUnrecorded) {
    return (
      <NonReadyState back={back} meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate}>
        <div className="flex flex-col items-center justify-center py-12">
          <div className="text-center space-y-4 max-w-md">
            <span className="material-symbols-outlined text-5xl text-base-400">videocam_off</span>
            <p className="font-semibold">This meeting wasn&apos;t recorded.</p>
            {bot && <RecallStatusBadge bot={bot} />}
          </div>
        </div>
      </NonReadyState>
    )
  }

  if (isProcessing) {
    return (
      <NonReadyState back={back} meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate}>
        <div className="flex flex-col items-center justify-center gap-4 py-12">
          <div className="text-center space-y-2">
            <span className="loading loading-lg" />
            <p>When the meeting is done being processed you&apos;ll see it here</p>
          </div>
          {bot && <RecallStatusBadge bot={bot} />}
        </div>
      </NonReadyState>
    )
  }

  const hasRecording = meeting.recording_id !== null

  return (
    <div>
      <StickyHeader>
        <Header meeting={meeting} back={back} onServerUpdate={onServerUpdate} />
      </StickyHeader>
      <div className="px-2 grid gap-6">
        <MeetingTitle meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate} />
        <div className="bg-base-50 rounded-lg border border-neutral relative">
          <div className="grayscale hover:grayscale-0 transition-all absolute -top-4 left-4 z-10 pointer-events-auto">
            <AttendeesPanel resolved={meeting.user_attendees} unresolved={meeting.unresolved_attendees} />
          </div>
          <div className="rounded-t-lg overflow-hidden aspect-video">
            {hasRecording ? (
              <VideoPlayer
                meetingId={meeting.id}
                hasRecording={hasRecording}
                videoRef={videoRef}
                onTimeUpdate={setCurrentTime}
              />
            ) : (
              <VideoUploadForm meetingId={meeting.id} onUploaded={onServerUpdate} />
            )}
          </div>
          {hasRecording && (
            <div className="flex justify-between gap-2 items-center p-4 border-t border-neutral">
              <CopyTimestampButton meetingId={meeting.id} currentTime={currentTime} />
              <Tooltip content="View transcripts">
                <button
                  type="button"
                  className="btn btn-ghost btn-square"
                  onClick={toggleTranscripts}
                  aria-label="View transcripts"
                  aria-expanded={showTranscripts}
                >
                  <span className="material-symbols-outlined text-lg">{showTranscripts ? "close" : "subtitles"}</span>
                </button>
              </Tooltip>
            </div>
          )}
          {hasRecording && transcriptsEverShown && (
            <div className={showTranscripts ? "" : "hidden"}>
              <TranscriptsToggle
                meeting={meeting}
                currentTime={currentTime}
                // A meeting is "processing" if its Recall bot is still working
                // OR an upload/transcription job is in flight. No-bot meetings
                // (uploads, pasted transcripts) only have the latter signal —
                // without it, a 404 transcript would spin forever.
                isProcessing={(bot?.is_processing_transcript ?? false) || meeting.is_initial_processing}
                onSeek={seek}
              />
            </div>
          )}
        </div>
        <Tabs meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate} />
      </div>
    </div>
  )
}

interface MeetingContentProps {
  meeting: MeetingDetail
  onLocalUpdate: <K extends keyof MeetingDetail>(field: K, value: MeetingDetail[K]) => void
  onServerUpdate: (meeting: MeetingDetail) => void
}

// The agenda/summary content section, shared between the processing, failed, and
// completed states.
function MeetingContent({ meeting, onLocalUpdate, onServerUpdate }: MeetingContentProps) {
  return (
    <div className="px-2 grid gap-6">
      <Tabs meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate} />
    </div>
  )
}

interface NonReadyStateProps extends MeetingContentProps {
  back: BackNavigation
  children: ReactNode
}

// The recording-failed / unrecorded / processing states omit the editable header
// and video card, but must still offer a way back — on mobile the sticky-header
// back button is the only nav. The status message sits between the back button
// and the agenda/summary content.
function NonReadyState({ back, children, meeting, onLocalUpdate, onServerUpdate }: NonReadyStateProps) {
  return (
    <div>
      <div className="p-2">
        <BackButton back={back} />
      </div>
      {children}
      <MeetingContent meeting={meeting} onLocalUpdate={onLocalUpdate} onServerUpdate={onServerUpdate} />
    </div>
  )
}
