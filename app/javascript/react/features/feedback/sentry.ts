// Best-effort: returns `{ success: false }` on any failure so callers can
// proceed with a server-only submission when Sentry is unavailable.
import * as Sentry from "@sentry/browser"

export interface FeedbackData {
  message: string
  name?: string
  email?: string
  url?: string
  attachments?: File[]
}

export interface FeedbackResult {
  success: boolean
  eventId?: string
  error?: string
}

async function fileToAttachment(file: File): Promise<{ data: Uint8Array; filename: string; contentType?: string }> {
  return {
    data: new Uint8Array(await file.arrayBuffer()),
    filename: file.name,
    ...(file.type && { contentType: file.type }),
  }
}

export async function captureFeedback(data: FeedbackData): Promise<FeedbackResult> {
  try {
    if (!Sentry.isInitialized()) {
      return { success: false, error: "Sentry not initialized" }
    }

    const attachments = data.attachments?.length
      ? await Promise.all(data.attachments.map(fileToAttachment))
      : undefined

    const eventId = Sentry.captureFeedback(
      {
        message: data.message,
        ...(data.name && { name: data.name }),
        ...(data.email && { email: data.email }),
        ...(data.url && { url: data.url }),
      },
      attachments ? { attachments } : undefined
    )

    return { success: true, eventId: eventId || undefined }
  } catch (error) {
    console.error("Failed to capture feedback to Sentry:", error)
    return {
      success: false,
      error: error instanceof Error ? error.message : "Unknown error",
    }
  }
}
