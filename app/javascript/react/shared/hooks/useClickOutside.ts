import { useEffect, type RefObject } from "react"

export function useClickOutside(ref: RefObject<HTMLElement | null>, onClickOutside: () => void): void {
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClickOutside()
      }
    }
    document.addEventListener("click", handleClick)
    return () => document.removeEventListener("click", handleClick)
  }, [ref, onClickOutside])
}
