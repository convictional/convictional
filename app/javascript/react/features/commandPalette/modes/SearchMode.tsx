import { LookupResultRow } from "../results/LookupResultRow"
import { SeeAllFooter } from "../SeeAllFooter"
import type { LookupResult, LookupResults } from "../types"

interface SearchModeProps {
  results: LookupResults | null
  query: string
  selectedIndex: number
  onSelect: (index: number) => void
  onUserActivate: (result: LookupResult) => void
  onResultActivate: (result: LookupResult, index: number) => void
  onSeeAllActivate: () => void
}

export function SearchMode({
  results,
  query,
  selectedIndex,
  onSelect,
  onUserActivate,
  onResultActivate,
  onSeeAllActivate,
}: SearchModeProps) {
  const userResults = results?.user_results ?? []
  const otherResults = results?.other_results ?? []
  const totalResults = userResults.length + otherResults.length
  const hasResults = totalResults > 0
  const showSeparator = userResults.length > 0 && otherResults.length > 0
  const seeAllIndex = totalResults

  return (
    <>
      <div className="p-2 grid gap-3 overflow-y-auto max-h-[calc(100dvh-240px)]">
        {hasResults ? (
          <>
            <p className="text-xs text-base-500 px-4">
              {totalResults} {totalResults === 1 ? "Result" : "Results"}
            </p>
            <ul className="divide-y divide-base-300 border border-base-300 rounded-2xl overflow-hidden shadow-xs mx-2">
              {userResults.map((result, index) => (
                <LookupResultRow
                  key={result.id}
                  result={result}
                  query={query}
                  isSelected={selectedIndex === index}
                  onHover={() => onSelect(index)}
                  onActivate={() => onUserActivate(result)}
                />
              ))}
              {showSeparator && (
                <li className="px-2 py-2">
                  <hr className="border-base-300" />
                </li>
              )}
              {otherResults.map((result, i) => {
                const index = userResults.length + i
                return (
                  <LookupResultRow
                    key={result.id}
                    result={result}
                    query={query}
                    isSelected={selectedIndex === index}
                    onHover={() => onSelect(index)}
                    onActivate={() => onResultActivate(result, index)}
                  />
                )
              })}
            </ul>
          </>
        ) : query.length >= 2 ? (
          <p className="text-center text-sm text-base-500 py-8">No results found for &ldquo;{query}&rdquo;</p>
        ) : (
          <p className="text-center text-sm text-base-500 py-8">Start typing to search</p>
        )}
      </div>
      {query.length >= 2 && (
        <SeeAllFooter
          query={query}
          isSelected={selectedIndex === seeAllIndex}
          onHover={() => onSelect(seeAllIndex)}
          onActivate={onSeeAllActivate}
        />
      )}
    </>
  )
}
