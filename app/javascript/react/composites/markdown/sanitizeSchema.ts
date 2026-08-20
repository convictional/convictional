import { defaultSchema } from "rehype-sanitize"

// Narrowed from rehype-sanitize's defaultSchema (~50 tags) to the set our
// remark/rehype chain actually emits, so a future plugin can't introduce a tag
// the design system never validated. Mirrors the server's posture in
// app/helpers/markdown.py (BaseMarkdownRenderer.allowed_inline_html allows
// only `<br>` for raw HTML).
const ALLOWED_TAGS = [
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "em",
  "strong",
  "del",
  "code",
  "pre",
  "blockquote",
  "ul",
  "ol",
  "li",
  "table",
  "thead",
  "tbody",
  "tr",
  "td",
  "th",
  "a",
  "br",
  "hr",
  "input",
  "span",
  "img",
]

// `data-name` (remarkMentions) and `data-align` (rehypeRestoreAlign) would be
// stripped by the default schema and never reach the JSX overrides.
export const sanitizeSchema = {
  ...defaultSchema,
  tagNames: ALLOWED_TAGS,
  attributes: {
    ...defaultSchema.attributes,
    // Explicitly constrain <input type> to "checkbox" via the tuple form so a
    // future change can't widen the allowlist past task-list checkboxes. The
    // tuple `[name, value]` syntax is hast-util-sanitize's way of pinning an
    // attribute to specific values.
    input: [["type", "checkbox"], "checked", "disabled"],
    span: [...(defaultSchema.attributes?.span ?? []), "className", "data-name"],
    td: [...(defaultSchema.attributes?.td ?? []), "data-align"],
    th: [...(defaultSchema.attributes?.th ?? []), "data-align"],
  },
}
