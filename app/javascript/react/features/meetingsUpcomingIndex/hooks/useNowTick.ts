import { useEffect, useState } from "react"

const TICK_MS = 60_000

// Returns a Date snapshot that re-renders the consumer every minute. The day
// rollover near midnight requires the date headers to re-bucket without a
// reload (see WO #449); ticking once per minute is cheap and self-correcting.
export function useNowTick(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), TICK_MS)
    return () => clearInterval(id)
  }, [])
  return now
}
