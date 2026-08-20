import type { Element, ElementContent } from "hast"
import type { ComponentPropsWithoutRef, ComponentType } from "react"
import React, { useMemo } from "react"
import type { Components } from "react-markdown"
import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import type { PluggableList } from "unified"

import { REMARK_PLUGINS } from "./plugins"
import { rehypeRestoreAlign } from "./plugins/rehypeRestoreAlign"
import { rehypeStripBreakNewlines } from "./plugins/rehypeStripBreakNewlines"
import { rehypeUpgradeImageProtocol } from "./plugins/rehypeUpgradeImageProtocol"
import { rehypeWrapEmptyParagraphs } from "./plugins/rehypeWrapEmptyParagraphs"
import { sanitizeSchema } from "./sanitizeSchema"

interface MarkdownProps {
  source: string
  variant?: "default" | "compact"
  className?: string
  // Override the default <img> renderer. Used by chat to wrap images in a
  // height-capped, click-to-lightbox component. Callers without this prop get
  // the browser default rendering.
  imageComponent?: ComponentType<{ src: string; alt: string }>
  // Optional renderer for paragraphs that contain only images. When provided,
  // a paragraph with ≥2 images and no other meaningful content is replaced
  // with this component (chat uses it to lay images out in a grid). Note: the
  // group renders its own <img> elements and does not go through
  // `imageComponent` — pass both together if you want a consistent renderer
  // for single and grouped images.
  imageGroupComponent?: ComponentType<{ images: { src: string; alt: string }[] }>
}

function isImageElement(child: ElementContent): child is Element {
  return child.type === "element" && child.tagName === "img"
}

function isMeaningfulSibling(child: ElementContent): boolean {
  if (child.type === "text") return !/^\s*$/.test(child.value)
  if (child.type === "element") return child.tagName !== "img"
  return true
}

function extractImageGroup(node: Element | undefined): { src: string; alt: string }[] | null {
  if (!node) return null
  const children = node.children ?? []
  const imageNodes = children.filter(isImageElement)
  if (imageNodes.length < 2) return null
  if (children.some(isMeaningfulSibling)) return null
  return imageNodes.map(img => ({
    src: typeof img.properties?.src === "string" ? img.properties.src : "",
    alt: typeof img.properties?.alt === "string" ? img.properties.alt : "",
  }))
}

// Order matters: sanitize first (it clones/normalizes the tree), then the
// structural tweaks that add attributes or synthesize elements the schema would
// otherwise strip. The break/whitespace passes run last — strip the cosmetic
// serializer newlines, then wrap the now-bare root-level `<br>` as an empty
// paragraph — so the wrap sees a clean `<br>` with no adjacent `\n` to carry in.
const REHYPE_PLUGINS: PluggableList = [
  [rehypeSanitize, sanitizeSchema],
  rehypeUpgradeImageProtocol,
  rehypeRestoreAlign,
  rehypeStripBreakNewlines,
  rehypeWrapEmptyParagraphs,
]

// Every override destructures `node` into `_node` because react-markdown v9
// passes the hast node as a prop; spreading `...rest` onto the DOM element
// would serialize it as `node="[object Object]"`.
const COMPONENTS: Components = {
  // Only force new-tab on absolute http(s) links. Relative/internal hrefs (e.g.
  // /documents/abc) stay in-tab for in-app navigation.
  a({ node: _node, children, href, ...rest }) {
    const isExternal = typeof href === "string" && /^https?:\/\//i.test(href)
    if (isExternal) {
      return (
        <a {...rest} href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      )
    }
    return (
      <a {...rest} href={href}>
        {children}
      </a>
    )
  },
  input({ node: _node, type, ...rest }) {
    if (type === "checkbox") {
      return <input {...rest} type="checkbox" disabled className="task-checkbox absolute -left-5 top-1" />
    }
    return <input type={type} {...rest} />
  },
  // Suppress the bullet only on task-list items; regular <li>s keep their marker
  // because remark-gfm leaves the parent <ul>'s list-style intact.
  li({ node: _node, children, className, ...rest }) {
    if (typeof className === "string" && className.includes("task-list-item")) {
      return (
        <li {...rest} className="!my-1 list-none relative">
          {children}
        </li>
      )
    }
    return (
      <li {...rest} className={className}>
        {children}
      </li>
    )
  },
  // Mentions arrive from remarkMentions as <span class="mention" data-name>;
  // re-emit them with the server's class (see app/helpers/markdown.py:61). For
  // any other span we pass through the full props so unrecognized data-* attrs
  // future plugins might emit aren't silently dropped.
  span({
    node: _node,
    children,
    className,
    ...rest
  }: ComponentPropsWithoutRef<"span"> & { "data-name"?: string; node?: unknown }) {
    const dataName = rest["data-name"]
    if (typeof className === "string" && className.includes("mention") && typeof dataName === "string") {
      return (
        <span className="text-info-content" data-name={dataName}>
          @{dataName}
        </span>
      )
    }
    return (
      <span {...rest} className={className}>
        {children}
      </span>
    )
  },
}

function wrapperClassName(variant: "default" | "compact", extra?: string): string {
  const base = variant === "compact" ? "markdown-content compact-markdown" : "markdown-content"
  return extra ? `${base} ${extra}` : base
}

export const Markdown = React.memo(function Markdown({
  source,
  variant = "default",
  className,
  imageComponent: ImageComponent,
  imageGroupComponent: ImageGroupComponent,
}: MarkdownProps) {
  const components = useMemo<Components>(() => {
    if (!ImageComponent && !ImageGroupComponent) return COMPONENTS
    const overrides: Components = { ...COMPONENTS }
    if (ImageComponent) {
      overrides.img = ({ node: _node, src, alt }) => (
        <ImageComponent src={typeof src === "string" ? src : ""} alt={typeof alt === "string" ? alt : ""} />
      )
    }
    if (ImageGroupComponent) {
      overrides.p = ({ node, children }) => {
        const group = extractImageGroup(node)
        if (group) return <ImageGroupComponent images={group} />
        return <p>{children}</p>
      }
    }
    return overrides
  }, [ImageComponent, ImageGroupComponent])

  return (
    <div className={wrapperClassName(variant, className)}>
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  )
})
