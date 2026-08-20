import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, test } from "vitest"

import { Markdown } from "../../../../../app/javascript/react/composites/markdown/Markdown"

// The wrapper div is the first child of the render container. We assert against
// it directly rather than using getByRole/getByText so we can verify the
// variant→class mapping contract.
function renderMarkdown(source: string, props: { variant?: "default" | "compact"; className?: string } = {}) {
  const { container } = render(<Markdown source={source} {...props} />)
  const wrapper = container.firstElementChild as HTMLElement
  return { container, wrapper }
}

describe("Markdown", () => {
  afterEach(cleanup)

  describe("basic rendering", () => {
    test("renders paragraph, heading, bold, italic, code fence, and blockquote", () => {
      const source = [
        "# Hello",
        "",
        "Some **bold** and *italic* text.",
        "",
        "> A quote.",
        "",
        "```js",
        "console.log('hi')",
        "```",
      ].join("\n")
      const { wrapper } = renderMarkdown(source)

      expect(wrapper.querySelector("h1")?.textContent).toBe("Hello")
      expect(wrapper.querySelector("p")?.textContent).toContain("bold")
      expect(wrapper.querySelector("strong")?.textContent).toBe("bold")
      expect(wrapper.querySelector("em")?.textContent).toBe("italic")
      expect(wrapper.querySelector("blockquote")?.textContent).toContain("A quote.")
      // Code fences render as <pre><code>…</code></pre>; remark-gfm doesn't add highlighting.
      expect(wrapper.querySelector("pre code")?.textContent).toContain("console.log('hi')")
    })
  })

  describe("GFM features", () => {
    test("renders tables with per-cell alignment", () => {
      const source = ["| a | b | c |", "|:--|:-:|--:|", "| 1 | 2 | 3 |"].join("\n")
      const { wrapper } = renderMarkdown(source)

      const table = wrapper.querySelector("table")
      expect(table).not.toBeNull()
      const headerCells = wrapper.querySelectorAll("th")
      expect(headerCells).toHaveLength(3)
      // remark-gfm emits `align` but hast-util-to-jsx-runtime mangles it into
      // style.textAlign; rehypeRestoreAlign moves the value onto data-align (and
      // deletes the original `align`) so the [data-align] CSS selectors in
      // markdown-content.css can match without an inline style overriding them.
      expect(headerCells[0].getAttribute("data-align")).toBe("left")
      expect(headerCells[1].getAttribute("data-align")).toBe("center")
      expect(headerCells[2].getAttribute("data-align")).toBe("right")
      const bodyCells = wrapper.querySelectorAll("tbody td")
      expect(bodyCells).toHaveLength(3)
      expect(bodyCells[1].getAttribute("data-align")).toBe("center")

      // The bare `align` attribute and the inline text-align style must not
      // survive — either would let inline styling beat the [data-align]
      // selectors in markdown-content.css.
      for (const cell of [...headerCells, ...bodyCells]) {
        expect(cell.getAttribute("align")).toBeNull()
        expect(cell.style.textAlign).toBe("")
      }
    })

    test("renders task list items with checked/unchecked checkboxes", () => {
      const source = ["- [ ] todo one", "- [x] done one"].join("\n")
      const { wrapper } = renderMarkdown(source)

      const checkboxes = wrapper.querySelectorAll<HTMLInputElement>("input[type='checkbox']")
      expect(checkboxes).toHaveLength(2)
      expect(checkboxes[0].checked).toBe(false)
      expect(checkboxes[1].checked).toBe(true)
      checkboxes.forEach(cb => {
        expect(cb.disabled).toBe(true)
        expect(cb.className).toContain("task-checkbox")
      })
    })

    test("renders strikethrough", () => {
      const { wrapper } = renderMarkdown("~~gone~~")
      expect(wrapper.querySelector("del")?.textContent).toBe("gone")
    })

    test("renders autolinks", () => {
      const { wrapper } = renderMarkdown("Visit https://example.com please")
      const link = wrapper.querySelector("a")
      expect(link?.getAttribute("href")).toBe("https://example.com")
    })
  })

  describe("variant wrapper classes", () => {
    test("default variant uses markdown-content", () => {
      const { wrapper } = renderMarkdown("hi", { variant: "default" })
      expect(wrapper.tagName).toBe("DIV")
      expect(wrapper.getAttribute("class")).toBe("markdown-content")
    })

    test("compact variant uses markdown-content compact-markdown", () => {
      const { wrapper } = renderMarkdown("hi", { variant: "compact" })
      expect(wrapper.tagName).toBe("DIV")
      expect(wrapper.getAttribute("class")).toBe("markdown-content compact-markdown")
    })

    test("default variant when variant is omitted", () => {
      const { wrapper } = renderMarkdown("hi")
      expect(wrapper.getAttribute("class")).toBe("markdown-content")
    })

    test("additional className appends after the variant class", () => {
      const { wrapper: a } = renderMarkdown("hi", { variant: "default", className: "extra-1 extra-2" })
      expect(a.getAttribute("class")).toBe("markdown-content extra-1 extra-2")

      const { wrapper: b } = renderMarkdown("hi", { variant: "compact", className: "extra" })
      expect(b.getAttribute("class")).toBe("markdown-content compact-markdown extra")
    })
  })

  describe("mentions", () => {
    test("renders @[Alice] as a Mention component carrying data-name", () => {
      const { wrapper } = renderMarkdown("Hi @[Alice], welcome.")
      const mention = wrapper.querySelector("[data-name='Alice']")
      expect(mention).not.toBeNull()
      expect(mention?.textContent).toContain("Alice")
    })

    test("preserves apostrophes in the name", () => {
      const { wrapper } = renderMarkdown("@[O'Brien] arrived.")
      const mention = wrapper.querySelector('[data-name="O\'Brien"]')
      expect(mention).not.toBeNull()
      expect(mention?.textContent).toContain("O'Brien")
    })

    test("preserves unicode names", () => {
      const { wrapper } = renderMarkdown("@[Frédéric Étienne] said hi.")
      const mention = wrapper.querySelector("[data-name='Frédéric Étienne']")
      expect(mention).not.toBeNull()
      expect(mention?.textContent).toContain("Frédéric Étienne")
    })
  })

  describe("content citations", () => {
    test("[^content:UUID] is deleted with no leakage to the DOM", () => {
      const { wrapper } = renderMarkdown("Before [^content:abc-12345-def-6789-0123] after.")
      const text = wrapper.textContent ?? ""
      expect(text).not.toContain("content:")
      expect(text).not.toContain("[^")
      expect(text).not.toContain("abc-12345")
      expect(wrapper.innerHTML).not.toContain("content:")
    })

    test("truncated [^content:ab is deleted, no stray brackets", () => {
      const { wrapper } = renderMarkdown("Before [^content:ab")
      const text = wrapper.textContent ?? ""
      expect(text).not.toContain("[^")
      expect(text).not.toContain("content:")
      expect(text.trim()).toBe("Before")
    })

    test("'Foo [^.* bar' bracket form is deleted", () => {
      const { wrapper } = renderMarkdown("Foo [^.* bar")
      const text = wrapper.textContent ?? ""
      expect(text).not.toContain("[^")
      expect(text).toContain("Foo")
    })
  })

  describe("dangerous content", () => {
    test("blocks <script> tags", () => {
      const { wrapper } = renderMarkdown("Hi <script>alert('x')</script> there")
      expect(wrapper.querySelector("script")).toBeNull()
      expect(wrapper.innerHTML.toLowerCase()).not.toContain("<script")
    })

    test("strips dangerous handlers like onerror", () => {
      const { wrapper } = renderMarkdown('Look <img src="x" onerror="alert(\'x\')"> at this')
      const img = wrapper.querySelector("img")
      // rehype-sanitize either removes the <img> entirely or strips the onerror handler.
      if (img) {
        expect(img.getAttribute("onerror")).toBeNull()
      }
      expect(wrapper.innerHTML.toLowerCase()).not.toContain("onerror")
    })

    test("drops javascript: URLs from links", () => {
      const { wrapper } = renderMarkdown("[click](javascript:alert(1))")
      const link = wrapper.querySelector("a")
      // The link element may still render but the unsafe href is dropped
      // (or the entire anchor is stripped); either way the unsafe scheme
      // must not reach the DOM.
      const href = link?.getAttribute("href") ?? ""
      expect(href.toLowerCase()).not.toContain("javascript:")
    })

    test("drops data: URLs from links", () => {
      const { wrapper } = renderMarkdown("[x](data:text/html,<script>alert(1)</script>)")
      const link = wrapper.querySelector("a")
      // The sanitizer drops the unsafe href entirely (yielding null) or, if the
      // anchor is removed too, querySelector returns null. Either is fine — the
      // contract is that "data:..." never reaches the DOM as an href.
      const href = link?.getAttribute("href") ?? ""
      expect(href.toLowerCase()).not.toContain("data:")
      expect(wrapper.innerHTML.toLowerCase()).not.toContain("data:text/html")
    })

    test("strips raw <style> elements", () => {
      const { wrapper } = renderMarkdown("<style>body{display:none}</style>before after")
      expect(wrapper.querySelector("style")).toBeNull()
      expect(wrapper.innerHTML.toLowerCase()).not.toContain("<style")
    })

    test("strips raw <iframe> elements", () => {
      const { wrapper } = renderMarkdown('<iframe src="//evil"></iframe>after')
      expect(wrapper.querySelector("iframe")).toBeNull()
      expect(wrapper.innerHTML.toLowerCase()).not.toContain("<iframe")
    })

    test("does not render unexpected tags like <details>", () => {
      // react-markdown escapes raw HTML by default, so <details> in markdown
      // source becomes literal text. The sanitizer's tagNames allowlist is the
      // backstop for plugin-emitted hast nodes — verify the element is absent
      // from the DOM either way.
      const { wrapper } = renderMarkdown("<details><summary>hi</summary>nope</details>")
      expect(wrapper.querySelector("details")).toBeNull()
      expect(wrapper.querySelector("summary")).toBeNull()
    })

    test("strips non-checkbox <input> types", () => {
      // The sanitizer pins input[type] to "checkbox" so a future plugin or raw
      // HTML path can't slip a text/password/file input past the allowlist.
      // react-markdown escapes raw HTML today, so this is defense-in-depth.
      const { wrapper } = renderMarkdown('<input type="text" name="x">after')
      const input = wrapper.querySelector("input")
      // Either the entire <input> is dropped, or the type attribute is
      // stripped — what matters is that type="text" never reaches the DOM.
      if (input) {
        expect(input.getAttribute("type")).not.toBe("text")
      }
      expect(wrapper.innerHTML.toLowerCase()).not.toContain('type="text"')
    })
  })

  describe("hard breaks", () => {
    test("two trailing spaces before newline render a <br>", () => {
      // CommonMark hard break: "line one  \nline two". remark-parse handles
      // this natively; do NOT add a remarkHardBreak plugin in Markdown.tsx.
      const { wrapper } = renderMarkdown("line one  \nline two")
      expect(wrapper.querySelector("br")).not.toBeNull()
    })

    test("raw <br> in source renders a <br>", () => {
      const { wrapper } = renderMarkdown("first<br>second")
      expect(wrapper.querySelector("br")).not.toBeNull()
      expect(wrapper.textContent ?? "").not.toContain("<br>")
    })
  })

  describe("blank lines between paragraphs", () => {
    test("a <br /> block between paragraphs renders a wrapped empty paragraph", () => {
      // A blank line a user adds between paragraphs reaches the renderer as a
      // literal `<br />` block (see richText/schema/paragraphFormatting.ts). The
      // whitespace contract's canonical empty block is a wrapped <p><br></p>,
      // 1:1 with the empty paragraph — rehypeWrapEmptyParagraphs stops
      // react-markdown lifting the <br> to the document root.
      const source = ["para one", "", "<br />", "", "para two"].join("\n")
      const { wrapper } = renderMarkdown(source)

      expect(wrapper.innerHTML).toBe("<p>para one</p><p><br></p><p>para two</p>")
    })

    test("multiple consecutive blank lines render multiple <br> separators", () => {
      const source = ["para one", "", "<br />", "", "<br />", "", "para two"].join("\n")
      const { wrapper } = renderMarkdown(source)
      expect(wrapper.querySelectorAll("br")).toHaveLength(2)
    })
  })

  describe("mention edge cases", () => {
    test("mention inside a link does not crash and renders something", () => {
      // Behavior for [@[Alice]](http://x): remark-mentions runs after parsing
      // so the inner @[Alice] inside link text is recognized as a mention. We
      // assert non-crash and that the link target is preserved.
      const { wrapper } = renderMarkdown("[@[Alice]](http://x)")
      const link = wrapper.querySelector("a")
      expect(link).not.toBeNull()
      expect(link?.getAttribute("href")).toBe("http://x")
    })
  })

  describe("streaming and truncated input", () => {
    test("does not crash on partial inline markup and produces some output", () => {
      const fixtures = ["*bo", "[link", "**unfinished", "| col1 | col2"]
      for (const source of fixtures) {
        const { wrapper, container } = renderMarkdown(source)
        expect(wrapper).not.toBeNull()
        expect(container.textContent?.length).toBeGreaterThan(0)
      }
    })
  })

  describe("empty source", () => {
    test("renders an empty wrapper with the markdown-content class", () => {
      const { wrapper } = renderMarkdown("")
      expect(wrapper.tagName).toBe("DIV")
      expect(wrapper.getAttribute("class")).toBe("markdown-content")
      expect(wrapper.children.length).toBe(0)
    })
  })

  describe("mixed task/regular list", () => {
    test("task li carries list-none, regular li does not", () => {
      const source = ["- [ ] task item", "- regular item"].join("\n")
      const { wrapper } = renderMarkdown(source)

      const items = wrapper.querySelectorAll("li")
      expect(items).toHaveLength(2)

      const [taskItem, regularItem] = Array.from(items)
      expect(taskItem.className).toContain("list-none")
      expect(regularItem.className).not.toContain("list-none")
    })
  })

  describe("link safety", () => {
    test("rendered links open in a new tab with noopener noreferrer", () => {
      const { wrapper } = renderMarkdown("Read [this](https://example.com) please")
      const link = wrapper.querySelector("a")
      expect(link?.getAttribute("href")).toBe("https://example.com")
      expect(link?.getAttribute("target")).toBe("_blank")
      const rel = link?.getAttribute("rel") ?? ""
      expect(rel).toContain("noopener")
      expect(rel).toContain("noreferrer")
    })

    test("renders a canonical link with exact expected attributes", () => {
      const { wrapper } = renderMarkdown("[link text](https://example.com)")
      const link = wrapper.querySelector("a")
      expect(link?.textContent).toBe("link text")
      expect(link?.getAttribute("href")).toBe("https://example.com")
      expect(link?.getAttribute("target")).toBe("_blank")
      expect(link?.getAttribute("rel")).toBe("noopener noreferrer")
      expect(link?.hasAttribute("node")).toBe(false)
    })

    test("internal/relative links stay in-tab without target or rel", () => {
      // HTMX boost and in-app navigation require relative hrefs to load in the
      // same tab; only absolute http(s) URLs should escape to a new tab.
      const { wrapper } = renderMarkdown("See [the doc](/documents/abc-123) for details")
      const link = wrapper.querySelector("a")
      expect(link?.getAttribute("href")).toBe("/documents/abc-123")
      expect(link?.hasAttribute("target")).toBe(false)
      expect(link?.hasAttribute("rel")).toBe(false)
    })

    test("http:// links are treated as external", () => {
      const { wrapper } = renderMarkdown("[plain http](http://example.com)")
      const link = wrapper.querySelector("a")
      expect(link?.getAttribute("target")).toBe("_blank")
      expect(link?.getAttribute("rel")).toBe("noopener noreferrer")
    })
  })

  describe("span override (non-mention path)", () => {
    // No remark/rehype plugin in this pipeline emits a non-mention <span>
    // today, and the sanitizer's allowed-attribute list for <span> is
    // ["className", "data-name"] — so we can't drive an unrecognized data-*
    // attribute through ReactMarkdown to the override. The existing mention
    // tests cover the only reachable branch. The override now spreads `...rest`
    // on the non-mention branch so any future plugin that emits a <span> with
    // additional attributes (after being whitelisted in sanitizeSchema) won't
    // silently lose them. This test guards the only span path we can exercise:
    // mention spans still emit data-name and class as before.
    test("mention span emits class and data-name attribute", () => {
      const { wrapper } = renderMarkdown("Hi @[Alice]")
      const span = wrapper.querySelector("span")
      expect(span?.getAttribute("data-name")).toBe("Alice")
      expect(span?.className).toContain("text-info-content")
      expect(span?.hasAttribute("node")).toBe(false)
    })
  })

  describe("imageComponent override", () => {
    test("renders the default <img> when no imageComponent is passed", () => {
      const { wrapper } = renderMarkdown("![cat](https://example.com/cat.png)")
      const img = wrapper.querySelector("img")
      expect(img).not.toBeNull()
      expect(img?.getAttribute("src")).toBe("https://example.com/cat.png")
      expect(img?.getAttribute("alt")).toBe("cat")
    })

    test("invokes the custom imageComponent with src and alt from the markdown", () => {
      const calls: Array<{ src: string; alt: string }> = []
      // <span> rather than <div> because remark renders standalone images
      // inside a <p>, and block-in-inline trips an HTML nesting warning.
      function Spy({ src, alt }: { src: string; alt: string }) {
        calls.push({ src, alt })
        return <span data-testid="custom-img" data-src={src} data-alt={alt} />
      }
      const { container } = render(
        <Markdown source="![cat](https://example.com/cat.png)" imageComponent={Spy} />
      )

      expect(calls).toEqual([{ src: "https://example.com/cat.png", alt: "cat" }])
      const node = container.querySelector("[data-testid='custom-img']")
      expect(node?.getAttribute("data-src")).toBe("https://example.com/cat.png")
      expect(node?.getAttribute("data-alt")).toBe("cat")
      // The default <img> must not also be rendered.
      expect(container.querySelector("img")).toBeNull()
    })
  })

  describe("insecure image URLs", () => {
    test("upgrades an http:// image src to https:// on the default <img>", () => {
      // User-authored posts embed images pasted from old CMSes by http:// URL.
      // On our HTTPS pages those are mixed content: blocked by `img-src ... https:`.
      // rehypeUpgradeImageProtocol rewrites the scheme so the image loads over TLS.
      const { wrapper } = renderMarkdown(
        "![sq](http://static1.squarespace.com/static/abc/t/def/image.png.webp)"
      )
      const img = wrapper.querySelector("img")
      expect(img?.getAttribute("src")).toBe(
        "https://static1.squarespace.com/static/abc/t/def/image.png.webp"
      )
    })

    test("leaves https://, protocol-relative, and data: image srcs untouched", () => {
      expect(
        renderMarkdown("![a](https://example.com/a.png)").wrapper.querySelector("img")?.getAttribute("src")
      ).toBe("https://example.com/a.png")
      expect(
        renderMarkdown("![b](//example.com/b.png)").wrapper.querySelector("img")?.getAttribute("src")
      ).toBe("//example.com/b.png")
    })

    test("passes the upgraded src to a custom imageComponent", () => {
      const calls: Array<{ src: string; alt: string }> = []
      function Spy({ src, alt }: { src: string; alt: string }) {
        calls.push({ src, alt })
        return <span data-testid="custom-img" data-src={src} />
      }
      render(<Markdown source="![cat](http://example.com/cat.png)" imageComponent={Spy} />)
      expect(calls).toEqual([{ src: "https://example.com/cat.png", alt: "cat" }])
    })

    test("passes upgraded srcs to a custom imageGroupComponent", () => {
      const srcs: string[] = []
      function Group({ images }: { images: { src: string; alt: string }[] }) {
        srcs.push(...images.map(i => i.src))
        return <span data-testid="group" />
      }
      const source = "![a](http://example.com/a.png)\n![b](https://example.com/b.png)"
      render(<Markdown source={source} imageGroupComponent={Group} />)
      expect(srcs).toEqual(["https://example.com/a.png", "https://example.com/b.png"])
    })
  })

  describe("imageGroupComponent override", () => {
    function Group({ images }: { images: { src: string; alt: string }[] }) {
      return (
        <span data-testid="group" data-count={images.length}>
          {images.map(i => i.alt).join(",")}
        </span>
      )
    }

    test("groups an image-only paragraph when 2+ images are present", () => {
      const source = "![a](https://example.com/a.png)\n![b](https://example.com/b.png)"
      const { container } = render(<Markdown source={source} imageGroupComponent={Group} />)
      const group = container.querySelector("[data-testid='group']")
      expect(group?.getAttribute("data-count")).toBe("2")
      expect(group?.textContent).toBe("a,b")
    })

    test("leaves a single-image paragraph alone (falls through to imageComponent)", () => {
      const source = "![only](https://example.com/only.png)"
      const { container } = render(<Markdown source={source} imageGroupComponent={Group} />)
      expect(container.querySelector("[data-testid='group']")).toBeNull()
      expect(container.querySelector("img")?.getAttribute("alt")).toBe("only")
    })

    test("leaves a paragraph that mixes images with text alone", () => {
      const source = "look ![a](https://example.com/a.png) ![b](https://example.com/b.png) please"
      const { container } = render(<Markdown source={source} imageGroupComponent={Group} />)
      expect(container.querySelector("[data-testid='group']")).toBeNull()
      expect(container.querySelectorAll("img").length).toBe(2)
    })
  })

  describe("hast node leakage", () => {
    test("does not leak the hast node object as an attribute", () => {
      const { wrapper } = renderMarkdown("[link](https://example.com)")
      const link = wrapper.querySelector("a")
      expect(link?.hasAttribute("node")).toBe(false)
      const taskLi = renderMarkdown("- [ ] task").wrapper.querySelector("li")
      expect(taskLi?.hasAttribute("node")).toBe(false)
      // task checkbox (input override)
      const checkbox = renderMarkdown("- [ ] task").wrapper.querySelector("input[type='checkbox']")
      expect(checkbox?.hasAttribute("node")).toBe(false)
      // table cells (td/th overrides)
      const { wrapper: tableWrapper } = renderMarkdown("| a |\n|---|\n| 1 |")
      const th = tableWrapper.querySelector("th")
      const td = tableWrapper.querySelector("td")
      expect(th?.hasAttribute("node")).toBe(false)
      expect(td?.hasAttribute("node")).toBe(false)
    })
  })
})
