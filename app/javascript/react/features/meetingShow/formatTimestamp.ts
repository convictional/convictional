// Formats a playback position (in seconds) as H:MM:SS, or MM:SS when under an
// hour. Shared by the transcript line "play from" labels and the copy-timestamp
// link so both render the same shape.
export function formatTimestamp(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const pad = (n: number) => n.toString().padStart(2, "0")
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}
