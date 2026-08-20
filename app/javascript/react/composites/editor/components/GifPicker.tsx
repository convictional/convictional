import { flip, offset, shift } from "@floating-ui/react"
import { useCallback, useEffect, useRef, useState } from "react"

import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { Dropdown } from "~/react/ui/Dropdown"

export interface KlipyGif {
  slug: string
  title: string
  content_url: string
  preview_url: string
  preview_still_url: string
  width: number
  height: number
}

export function parseKlipyGifs(items: Record<string, unknown>[]): KlipyGif[] {
  return (items || [])
    .filter(item => item.type !== "ad")
    .map(item => {
      const file = item.file as Record<string, Record<string, { url: string; width: number; height: number }>>
      return {
        slug: item.slug as string,
        title: (item.title as string) || "",
        content_url: file.md?.gif?.url || file.hd?.gif?.url || "",
        preview_url: file.sm?.gif?.url || file.xs?.gif?.url || "",
        preview_still_url: file.sm?.jpg?.url || file.xs?.jpg?.url || "",
        width: file.sm?.gif?.width || 200,
        height: file.sm?.gif?.height || 150,
      }
    })
}

const PER_PAGE = 20

interface GifPickerProps {
  klipyApiKey: string
  onSelectGif: (gif: KlipyGif) => void
  buttonClassName?: string
  // Render the trigger as a bare icon (no btn chrome) for inline composer use.
  naked?: boolean
}

export function GifPicker({ klipyApiKey, onSelectGif, buttonClassName, naked }: GifPickerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const isMobile = useIsMobile()
  const baseClassName = naked
    ? "flex items-center justify-center shrink-0 rounded-full cursor-pointer"
    : "btn btn-square"

  return (
    <Dropdown
      open={isOpen}
      onOpenChange={setIsOpen}
      placement="bottom-end"
      // Disable floating-ui's auto-focus so we can focus the search input
      // with { preventScroll: true } below. Otherwise the browser scrolls
      // the document to bring the focused input into view, which jerks the
      // chat page upward when the picker opens.
      initialFocus={-1}
      // Use the shared dropdown-card styling (bevel + drop shadow); just size it.
      className="dropdown-card w-80 z-50"
      // Extra offset so the picker sits clear of the composer container.
      middleware={[offset(10), flip(), shift({ padding: 8 })]}
      trigger={
        <button
          type="button"
          className={`${baseClassName} ${buttonClassName || ""} ${isOpen && !naked ? "text-info-content" : ""}`}
          title="GIF"
          tabIndex={-1}
          onMouseDown={e => {
            // On mobile, dismiss the soft keyboard when opening the picker so
            // it isn't crammed above the keyboard — consistent with the attach
            // flow, which iOS force-closes the keyboard for anyway.
            if (isMobile) {
              ;(document.activeElement as HTMLElement | null)?.blur()
              return
            }
            // Desktop: keep the editor's contenteditable focused so the
            // selection is preserved when the picker opens.
            e.preventDefault()
          }}
        >
          <span className="material-symbols-outlined !text-lg">gif_2</span>
        </button>
      }
    >
      {({ close }) => <GifPickerPanel klipyApiKey={klipyApiKey} onSelectGif={onSelectGif} close={close} />}
    </Dropdown>
  )
}

function GifPickerPanel({
  klipyApiKey,
  onSelectGif,
  close,
}: {
  klipyApiKey: string
  onSelectGif: (gif: KlipyGif) => void
  close: () => void
}) {
  const [gifs, setGifs] = useState<KlipyGif[]>([])
  const [searchQuery, setSearchQuery] = useState("")
  const [hasMore, setHasMore] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const isMobile = useIsMobile()

  const baseUrl = `https://api.klipy.com/api/v1/${klipyApiKey}`

  const fetchGifs = useCallback(
    async (query: string, p: number): Promise<{ gifs: KlipyGif[]; hasMore: boolean }> => {
      const endpoint = query
        ? `${baseUrl}/gifs/search?q=${encodeURIComponent(query)}&per_page=${PER_PAGE}&page=${p}`
        : `${baseUrl}/gifs/trending?per_page=${PER_PAGE}&page=${p}`

      const response = await fetch(endpoint)
      if (!response.ok) throw new Error(`Klipy API error: ${response.status}`)

      const json = await response.json()
      return {
        gifs: parseKlipyGifs(json.data?.data || []),
        hasMore: json.data?.has_next ?? false,
      }
    },
    [baseUrl]
  )

  const pageRef = useRef(1)
  const searchQueryRef = useRef("")

  const doSearch = useCallback(
    async (query: string) => {
      setIsLoading(true)
      pageRef.current = 1
      searchQueryRef.current = query
      try {
        const result = await fetchGifs(query, 1)
        setGifs(result.gifs)
        setHasMore(result.hasMore)
      } catch {
        setGifs([])
        setHasMore(false)
      } finally {
        setIsLoading(false)
      }
    },
    [fetchGifs]
  )

  // Ref-based guard prevents double-clicks from firing duplicate fetches
  // before React re-renders with the updated isLoading state.
  const isLoadingRef = useRef(false)

  const loadMore = useCallback(async () => {
    if (isLoadingRef.current || !hasMore) return
    isLoadingRef.current = true
    setIsLoading(true)
    const nextPage = pageRef.current + 1
    pageRef.current = nextPage
    try {
      const result = await fetchGifs(searchQueryRef.current, nextPage)
      setGifs(prev => [...prev, ...result.gifs])
      setHasMore(result.hasMore)
    } catch {
      setHasMore(false)
    } finally {
      isLoadingRef.current = false
      setIsLoading(false)
    }
  }, [hasMore, fetchGifs])

  // Trigger initial trending fetch on mount (panel mounts when dropdown opens).
  useEffect(() => {
    doSearch("")
  }, [doSearch])

  // Focus the search input without scrolling. The picker lives in a floating
  // portal that renders during the chat page's document-level scroll, so a
  // plain .focus() (or autoFocus) would scroll the page up to "reveal" it.
  // Skip on mobile: focusing the field pops the soft keyboard, which crams the
  // picker and is inconsistent with the attach flow (no keyboard). The user can
  // tap the field to search if they want.
  useEffect(() => {
    if (isMobile) return
    searchInputRef.current?.focus({ preventScroll: true })
  }, [isMobile])

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    },
    []
  )

  const handleSearchInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const query = e.target.value
      setSearchQuery(query)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => doSearch(query), 300)
    },
    [doSearch]
  )

  const selectGif = useCallback(
    (gif: KlipyGif) => {
      onSelectGif(gif)
      close()
    },
    [onSelectGif, close]
  )

  return (
    <div onMouseDown={e => e.preventDefault()}>
      <div className="sticky top-0 z-10 bg-base-300 p-2.5 pb-1">
        <div className="relative">
          <span className="material-symbols-outlined text-base absolute left-2.5 top-1/2 -translate-y-1/2 text-base-content/30">
            search
          </span>
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search GIFs..."
            autoComplete="off"
            className="w-full pl-8 pr-3 py-1.5 text-sm rounded-lg border border-base-content/10 bg-base-100/50 !outline-none transition-all placeholder:text-base-content/40 focus:bg-base-100 focus:border-base-content/20"
            onChange={handleSearchInput}
          />
        </div>
      </div>

      <div className="px-2.5 pb-2 max-h-72 overflow-y-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
        {isLoading && gifs.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <span className="loading loading-spinner loading-sm text-base-content/30" />
          </div>
        )}

        {!isLoading && gifs.length === 0 && searchQuery && (
          <div className="text-center py-8 text-sm text-base-content/40">No GIFs found</div>
        )}

        <div className="grid grid-cols-2 gap-1">
          {gifs.map(gif => (
            <GifButton key={gif.slug} gif={gif} onSelect={selectGif} />
          ))}
        </div>

        {hasMore && (
          <div className="pt-2 pb-1 text-center">
            <button
              type="button"
              className="text-xs text-base-content/50 hover:text-base-content/70"
              onClick={loadMore}
            >
              {isLoading ? <span className="loading loading-spinner loading-xs" /> : <span>Load more</span>}
            </button>
          </div>
        )}
      </div>

      <div className="px-2.5 py-1.5 border-t border-base-content/5 text-center">
        <span className="text-[10px] text-base-content/25">Powered by Klipy</span>
      </div>
    </div>
  )
}

function GifButton({ gif, onSelect }: { gif: KlipyGif; onSelect: (gif: KlipyGif) => void }) {
  const [hovered, setHovered] = useState(false)
  const src = hovered ? gif.preview_url : gif.preview_still_url || gif.preview_url

  return (
    <button
      type="button"
      className="rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-primary transition-all"
      onClick={() => onSelect(gif)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <img
        src={src}
        alt={gif.title}
        width={gif.width}
        height={gif.height}
        loading="lazy"
        className="w-full h-auto object-cover"
      />
    </button>
  )
}
