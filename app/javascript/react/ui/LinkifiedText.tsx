import { useMemo, type ReactNode } from "react"

import { findUrlMatches } from "~/shared/links"

export function LinkifiedText({ text }: { text: string }) {
  const children: ReactNode[] = []
  let cursor = 0

  const matches = useMemo(() => findUrlMatches(text), [text])
  matches.forEach((match, index) => {
    if (match.start > cursor) {
      children.push(text.slice(cursor, match.start))
    }
    children.push(
      <a key={index} href={match.href} target="_blank" rel="noopener noreferrer" className="underline">
        {text.slice(match.start, match.end)}
      </a>
    )
    cursor = match.end
  })

  if (cursor < text.length) {
    children.push(text.slice(cursor))
  }

  return <>{children}</>
}
