import { useState } from "react"

interface InlineVideoProps {
  src: string
  title?: string
}

// onError covers codec/container decode failures that the nested <a> fallback doesn't:
// that anchor only renders in browsers with no <video> element at all, so without
// onError a browser that has <video> but can't decode would leave an empty player.
export function InlineVideo({ src, title }: InlineVideoProps) {
  const [failed, setFailed] = useState(false)

  if (failed) {
    return (
      <a
        href={src}
        target="_blank"
        rel="noopener noreferrer"
        className="my-2 inline-block text-sm underline not-prose"
      >
        {title ?? "Download video"}
      </a>
    )
  }

  return (
    <video
      src={src}
      controls
      muted
      preload="metadata"
      playsInline
      aria-label={title}
      onError={() => setFailed(true)}
      className="block max-h-[min(50vh,320px)] w-auto max-w-full rounded my-2 not-prose"
    >
      <a href={src} target="_blank" rel="noopener noreferrer">
        {title ?? "Download video"}
      </a>
    </video>
  )
}
