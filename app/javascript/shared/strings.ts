// Mirrors `app/helpers/strings.py:pluralize` / `make_plural`. Keep the two in
// sync — same irregulars, same suffix rules — so server-rendered and
// client-rendered strings match.

const IRREGULARS: Record<string, string> = {
  child: "children",
  person: "people",
  man: "men",
  woman: "women",
  foot: "feet",
  tooth: "teeth",
  goose: "geese",
  mouse: "mice",
}

const UNCHANGING = new Set(["sheep", "fish", "deer", "species", "aircraft"])
const O_KEEPS_S = new Set(["photo", "piano", "halo"])
const VOWELS = new Set(["a", "e", "i", "o", "u"])

export function makePlural(word: string): string {
  const lower = word.toLowerCase()

  if (lower in IRREGULARS) return IRREGULARS[lower]
  if (UNCHANGING.has(lower)) return word

  if (/(?:s|sh|ch|x|z)$/.test(word)) return `${word}es`
  if (word.endsWith("y")) {
    const prev = word[word.length - 2]?.toLowerCase() ?? ""
    if (VOWELS.has(prev)) return `${word}s`
    return `${word.slice(0, -1)}ies`
  }
  if (word.endsWith("fe")) return `${word.slice(0, -2)}ves`
  if (word.endsWith("f")) return `${word.slice(0, -1)}ves`
  if (word.endsWith("o")) {
    if (O_KEEPS_S.has(lower)) return `${word}s`
    return `${word}es`
  }
  return `${word}s`
}

export function pluralize(count: number, singular: string, plural?: string): string {
  if (count === 1) return singular
  return plural || makePlural(singular)
}
