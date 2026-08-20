import { useState } from "react"

import { FileCard } from "~/react/composites/FileCard"
import { ResourceBadge } from "~/react/composites/ResourceBadge"
import { CONTENT_TYPE_ICON_STYLES, CONTENT_TYPE_LABELS } from "~/react/shared/contentTypes"
import { NavLink } from "~/react/shared/NavLink"
import type { LinkPreview } from "~/react/shared/types"
import { faviconUrl, isSafeUrl } from "~/react/shared/urls"
import { InlineVideo } from "~/react/ui/InlineVideo"

// Internal previews are same-origin; hand NavLink a path so it can SPA-route
// where a client route exists and otherwise do an in-tab full load.
function relativeHref(url: string): string {
  try {
    const u = new URL(url)
    return u.pathname + u.search + u.hash
  } catch {
    return url
  }
}

function DismissButton({ onDismiss }: { onDismiss: () => void }) {
  return (
    <button
      type="button"
      onClick={onDismiss}
      aria-label="Dismiss link preview"
      className="absolute top-1.5 right-1.5 z-10 cursor-pointer text-base-500 hover:text-base-700"
    >
      <span className="material-symbols-outlined text-base">close</span>
    </button>
  )
}

export function LinkPreviewCard({ linkPreview, onDismiss }: { linkPreview: LinkPreview; onDismiss?: () => void }) {
  const [imgFailed, setImgFailed] = useState(false)
  const [faviconFailed, setFaviconFailed] = useState(false)
  const resourceKind = linkPreview.resource_kind

  // A pasted attachment link renders as a file card. file metadata is re-resolved at render
  // and may be absent (attachment deleted / access lost); fall back to the stored filename.
  if (resourceKind === "file") {
    // A video attachment plays inline; every other file (and a video whose metadata
    // failed to re-resolve) renders the file card. content_type is the real MIME from
    // the attachment, so this branch is exact rather than an extension guess.
    const isVideo = linkPreview.file?.content_type?.startsWith("video/") && isSafeUrl(linkPreview.url)
    return (
      <div className="relative">
        {onDismiss && <DismissButton onDismiss={onDismiss} />}
        {isVideo ? (
          <InlineVideo src={linkPreview.url} title={linkPreview.file?.file_name ?? linkPreview.title ?? undefined} />
        ) : (
          <FileCard
            fileName={linkPreview.file?.file_name ?? linkPreview.title ?? "File"}
            contentType={linkPreview.file?.content_type ?? null}
            byteSize={linkPreview.file?.byte_size ?? null}
            downloadUrl={isSafeUrl(linkPreview.url) ? linkPreview.url : "#"}
          />
        )}
      </div>
    )
  }

  // NavLink renders an in-app client route for internal previews and degrades to
  // a plain anchor for external ones (an absolute URL is never a client route),
  // so a single element covers both — external links just opt into a new tab.
  const internal = Boolean(resourceKind)
  const href = internal ? relativeHref(linkPreview.url) : isSafeUrl(linkPreview.url) ? linkPreview.url : "#"
  const newTab = internal ? {} : { target: "_blank", rel: "noopener noreferrer" }
  const accentColor = resourceKind ? CONTENT_TYPE_ICON_STYLES[resourceKind]?.color : undefined

  // The dismiss affordance exists only in the composer, so its absence means the
  // card is posted — sitting inside a bg-base-200 message bubble. Lift posted
  // internal previews onto the lighter base surface so they read as a distinct
  // card rather than blending into the bubble.
  const posted = !onDismiss
  const surface = internal && posted ? "bg-base-100" : "bg-base-200"
  const hoverSurface = internal && posted ? "hover:bg-base-200" : "hover:bg-base-300"

  return (
    <div className={`relative border border-neutral rounded-lg overflow-hidden ${surface}`}>
      {onDismiss && <DismissButton onDismiss={onDismiss} />}
      <NavLink
        href={href}
        {...newTab}
        aria-label={linkPreview.title || linkPreview.domain}
        className={`flex items-start gap-2.5 p-2.5 ${hoverSurface} transition`}
      >
        {resourceKind ? (
          <ResourceBadge contentType={resourceKind} />
        ) : linkPreview.image_url && isSafeUrl(linkPreview.image_url) && !imgFailed ? (
          <img
            src={linkPreview.image_url}
            alt=""
            loading="lazy"
            className="w-16 h-16 object-cover rounded-md flex-shrink-0"
            onError={() => setImgFailed(true)}
          />
        ) : faviconFailed ? null : (
          // Branded fallback: no OpenGraph image (or it failed / the fetch was
          // blocked), so show the site's favicon so the card still reads as a link.
          // If the favicon service is unreachable too, drop the image entirely —
          // the domain text below still identifies the link.
          <img
            src={faviconUrl(linkPreview.domain)}
            alt=""
            loading="lazy"
            className="w-8 h-8 object-contain rounded flex-shrink-0 self-center"
            onError={() => setFaviconFailed(true)}
          />
        )}
        <div className="min-w-0 flex-1">
          {linkPreview.title && (
            <p className="text-xs font-semibold line-clamp-2 wrap-anywhere">{linkPreview.title}</p>
          )}
          {linkPreview.description && (
            <p className="text-xs text-base-content/50 line-clamp-2 mt-0.5 wrap-anywhere">{linkPreview.description}</p>
          )}
          {resourceKind ? (
            <p className="text-xs font-medium mt-1 wrap-anywhere" style={{ color: accentColor }}>
              {CONTENT_TYPE_LABELS[resourceKind] ?? resourceKind}
            </p>
          ) : (
            <p className="text-xs text-base-content/50 mt-0.5 wrap-anywhere">
              {linkPreview.site_name || linkPreview.domain}
            </p>
          )}
        </div>
      </NavLink>
    </div>
  )
}
