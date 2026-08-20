import { useEffect, useRef } from "react"

interface LoadMoreSentinelProps {
  onIntersect: () => void
  loading: boolean
}

export function LoadMoreSentinel({ onIntersect, loading }: LoadMoreSentinelProps) {
  const ref = useRef<HTMLDivElement>(null)
  const intersecting = useRef(false)
  const topWhenLoadStarted = useRef<number | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      entries => {
        intersecting.current = entries[0].isIntersecting
        if (entries[0].isIntersecting) onIntersect()
      },
      { rootMargin: "200px" }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [onIntersect])

  // IntersectionObserver only fires on a crossing, so when a loaded page is too
  // short to push the sentinel back out of view (small page size, tall viewport,
  // few results) no further crossing happens and pagination stalls mid-list.
  // Bridge that: once a load settles while we're still in view, fetch again — but
  // only when new rows actually landed (the sentinel moved down the page). An
  // unchanged position means the load added nothing (an error or an empty page),
  // so we stop rather than hammer the endpoint.
  useEffect(() => {
    const el = ref.current
    if (!el) return

    if (loading) {
      topWhenLoadStarted.current = el.getBoundingClientRect().top
      return
    }

    const startedAt = topWhenLoadStarted.current
    topWhenLoadStarted.current = null
    if (intersecting.current && startedAt !== null && el.getBoundingClientRect().top > startedAt) {
      onIntersect()
    }
  }, [loading, onIntersect])

  return (
    <div ref={ref} className="flex items-center justify-center p-4">
      {loading && <span className="loading loading-spinner" />}
    </div>
  )
}
