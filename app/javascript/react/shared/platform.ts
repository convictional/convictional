export function isIOS(): boolean {
  if (typeof navigator === "undefined") return false
  // iPadOS 13+ reports `MacIntel` like a desktop Mac; the touch-points check
  // is the standard disambiguator (no touchscreen Macs exist as of writing).
  // `navigator.platform` is technically deprecated in favor of `userAgentData`,
  // but Safari hasn't shipped the latter, so this is still the only reliable
  // iPadOS detection. Revisit when Safari ships `userAgentData`.
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  )
}
