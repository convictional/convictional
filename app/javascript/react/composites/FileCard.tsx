// MIME content type → Material Symbol icon. Mirrors the coarse buckets of
// Attachment.is_image/is_pdf/is_document in app/models/collaboration/workspace.py.
function fileIconForContentType(contentType: string | null): string {
  if (!contentType) return "attach_file"
  if (contentType.startsWith("image/")) return "image"
  if (contentType === "application/pdf") return "picture_as_pdf"
  if (contentType.startsWith("video/")) return "movie"
  if (contentType.startsWith("audio/")) return "audio_file"
  if (
    contentType === "application/msword" ||
    contentType.startsWith("application/vnd.openxmlformats-officedocument") ||
    contentType === "application/vnd.ms-excel" ||
    contentType.startsWith("text/")
  ) {
    return "description"
  }
  return "attach_file"
}

// Human-readable byte size, e.g. 1536 → "1.5 KB". Empty string when size is unknown.
function formatBytes(bytes: number | null): string {
  if (bytes == null) return ""
  if (bytes < 1024) return `${bytes} B`
  const units = ["KB", "MB", "GB", "TB"]
  let value = bytes / 1024
  let unitIndex = 0
  // Compare the rounded value so a size just under a unit ceiling (e.g. 1048575 B → 1023.99 KB,
  // which rounds to 1024.0) carries into the next unit instead of rendering "1024 KB".
  while (Math.round(value * 10) / 10 >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex++
  }
  return `${Math.round(value * 10) / 10} ${units[unitIndex]}`
}

// A file card for a pasted attachment link that unfurls to a preview (via LinkPreviewCard).
// The href is a real download endpoint, so this is a plain anchor — not a NavLink — and
// opens in a new tab.
export function FileCard({
  fileName,
  contentType,
  byteSize,
  downloadUrl,
}: {
  fileName: string
  contentType: string | null
  byteSize: number | null
  downloadUrl: string
}) {
  const size = formatBytes(byteSize)

  return (
    <a
      href={downloadUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 p-2 border border-neutral rounded-lg bg-base-200 hover:bg-base-300 transition max-w-full"
    >
      <span className="material-symbols-outlined text-2xl text-base-content/70 flex-shrink-0">
        {fileIconForContentType(contentType)}
      </span>
      <div className="min-w-0">
        <p className="text-sm truncate">{fileName}</p>
        {size && <p className="text-xs text-base-content/50">{size}</p>}
      </div>
    </a>
  )
}
