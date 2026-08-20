// Asset-staleness flag. Must live outside React (plain module state, not a ref
// or store) because shellRoute's beforeLoad guard reads it from outside the
// React render cycle.
let stale = false

export function markAssetsStale(): void {
  stale = true
}

export function isAssetVersionStale(): boolean {
  return stale
}

// Reset the singleton between test cases; has no production callers.
export function resetAssetVersionStale(): void {
  stale = false
}
