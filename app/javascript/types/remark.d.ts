declare module "micromark-util-types" {
  interface TokenTypeMap {
    mention: "mention"
    mentionMarker: "mentionMarker"
    mentionOpen: "mentionOpen"
    mentionName: "mentionName"
    mentionClose: "mentionClose"
  }
}

declare module "mdast" {
  interface RootContentMap {
    mention: Mention
  }
}

declare module "unified" {
  interface Data {
    micromarkExtensions?: Array<unknown> | undefined
    fromMarkdownExtensions?: Array<unknown> | undefined
    toMarkdownExtensions?: Array<unknown> | undefined
  }
}
export {}
