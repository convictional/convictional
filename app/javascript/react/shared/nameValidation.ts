// Latin-script letters, spaces, and common name punctuation only — no emoji,
// non-Latin scripts, or decorative unicode. Mirrors normalize_name server-side;
// the lookahead requires at least one letter so punctuation-only names fail.
// Shared by the profile settings section and the onboarding welcome show.
export const NAME_MAX_LENGTH = 50
export const NAME_PATTERN = "(?=.*\\p{Script=Latin})[\\p{Script=Latin} .'’-]+"
export const NAME_TITLE = "Use letters, spaces, hyphens, apostrophes, or periods."
