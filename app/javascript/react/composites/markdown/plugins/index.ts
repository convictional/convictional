import remarkGfm from "remark-gfm"
import type { PluggableList } from "unified"

import { remarkContentCitation } from "./remarkContentCitation"
import { remarkHtmlBreaks } from "./remarkHtmlBreaks"
import { remarkMentions } from "./remarkMentions"

// remark-gfm must run before remarkContentCitation so well-formed `[^content:UUID]`
// is parsed into a footnoteReference node that the citation plugin can drop.
export const REMARK_PLUGINS: PluggableList = [remarkGfm, remarkMentions, remarkContentCitation, remarkHtmlBreaks]

export { remarkContentCitation, remarkHtmlBreaks, remarkMentions }
