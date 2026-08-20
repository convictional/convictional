import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { LinkifiedText } from "~/react/ui/LinkifiedText"

const DASHBOARD_URL =
  "https://dashboard.ngrok.com/invitation?email=user%40example.com&token=EXAMPLETOKEN123456789"

// An ngrok invitation body (modeled on the #9163 report, anonymized). Note it
// contains BOTH the dashboard URL and a bare `ngrok.com` mention in the first
// line (linkifyjs treats bare domains as URLs), plus two email addresses — one
// with a dotted local part — that must NOT be linkified.
const NGROK_BODY = `alice@example.com has invited you to join the account 'bob.smith@example.com' on ngrok.com.

Click the following link to join the account:
${DASHBOARD_URL}

Reply to this email if you have any questions.`

function anchors(container: HTMLElement): HTMLAnchorElement[] {
  return Array.from(container.querySelectorAll("a"))
}

describe("LinkifiedText", () => {
  it("linkifies the ngrok dashboard URL, leaves emails alone, and preserves the body verbatim", () => {
    const { container } = render(
      <div className="whitespace-pre-wrap">
        <LinkifiedText text={NGROK_BODY} />
      </div>,
    )

    // The dashboard anchor is present with the exact attributes and visible text.
    const dashboardAnchor = anchors(container).find(
      a => a.getAttribute("href") === DASHBOARD_URL,
    )
    expect(dashboardAnchor).toBeTruthy()
    expect(dashboardAnchor!).toHaveTextContent(DASHBOARD_URL)
    expect(dashboardAnchor!).toHaveAttribute("target", "_blank")
    expect(dashboardAnchor!).toHaveAttribute("rel", "noopener noreferrer")

    // The two email addresses must never become anchors.
    for (const email of ["alice@example.com", "bob.smith@example.com"]) {
      expect(
        anchors(container).some(
          a => a.getAttribute("href") === email || a.textContent === email,
        ),
      ).toBe(false)
    }

    // Nothing is dropped or reflowed: the container's text equals the input,
    // including every newline and space as preserved text nodes.
    expect(container.textContent).toBe(NGROK_BODY)
  })

  it("emits exactly one anchor for a clean single-URL body without a bare domain", () => {
    // Dedicated input: only the dashboard URL plus prose, no bare `ngrok.com`.
    const body = `Click the following link to join the account:\n${DASHBOARD_URL}\nReply if you have questions.`
    const { container } = render(<LinkifiedText text={body} />)

    const found = anchors(container)
    expect(found).toHaveLength(1)
    expect(found[0].getAttribute("href")).toBe(DASHBOARD_URL)
    expect(container.textContent).toBe(body)
  })

  it("linkifies bare domains showing the source text, skips non-http(s) URIs, and leaves plain text untouched", () => {
    // Bare domain: href gets the https default protocol, but the VISIBLE text is
    // the original source substring (`ngrok.com`, not `https://ngrok.com`).
    const bare = render(<LinkifiedText text="visit ngrok.com now" />)
    const bareAnchors = anchors(bare.container)
    expect(bareAnchors).toHaveLength(1)
    expect(bareAnchors[0].getAttribute("href")).toBe("https://ngrok.com")
    expect(bareAnchors[0].textContent).toBe("ngrok.com")
    expect(bare.container.textContent).toBe("visit ngrok.com now")

    // Non-http(s) URIs yield no anchor — either undetected by linkifyjs or dropped by the allowed-protocol filter.
    for (const uri of ["ftp://example.com/f", "file:///etc/hosts", "javascript:alert(1)"]) {
      const { container } = render(<LinkifiedText text={uri} />)
      expect(anchors(container)).toHaveLength(0)
    }

    // Plain prose with no URLs yields no anchors and identical text.
    const plain = render(<LinkifiedText text="No links here, just words." />)
    expect(anchors(plain.container)).toHaveLength(0)
    expect(plain.container.textContent).toBe("No links here, just words.")
  })

  it("keeps trailing punctuation and adjacent whitespace as text, with the anchor covering only the URL", () => {
    const body = "see https://x.com.\nthen https://y.com next"
    const { container } = render(
      <div className="whitespace-pre-wrap">
        <LinkifiedText text={body} />
      </div>,
    )

    const found = anchors(container)
    // One anchor per URL; the trailing sentence `.` is excluded from the first.
    expect(found.map(a => a.getAttribute("href"))).toEqual([
      "https://x.com",
      "https://y.com",
    ])
    expect(found.map(a => a.textContent)).toEqual(["https://x.com", "https://y.com"])

    // The trailing period, the newline, and surrounding spaces survive as text.
    expect(container.textContent).toBe(body)

    // A URL at offset 0 still yields exactly one anchor and preserves the text verbatim.
    const leading = render(<LinkifiedText text="https://a.com is first" />)
    const leadingAnchors = anchors(leading.container)
    expect(leadingAnchors.map(a => a.getAttribute("href"))).toEqual(["https://a.com"])
    expect(leadingAnchors[0].textContent).toBe("https://a.com")
    expect(leading.container.textContent).toBe("https://a.com is first")

    // Two adjacent URLs keep the single separating space as a text node.
    const adjacent = render(<LinkifiedText text="https://a.com https://b.com" />)
    expect(anchors(adjacent.container).map(a => a.getAttribute("href"))).toEqual([
      "https://a.com",
      "https://b.com",
    ])
    expect(adjacent.container.textContent).toBe("https://a.com https://b.com")
  })
})
