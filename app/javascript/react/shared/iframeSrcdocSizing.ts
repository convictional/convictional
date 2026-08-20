// True only for the real navigated srcdoc document with parsed content — not the
// initial about:blank placeholder that a freshly-created iframe exposes before
// the srcdoc navigation completes. That placeholder already has an empty <body>
// and readyState "complete", so a naive "body exists" check fires against it,
// measures ~0px, and observes a body that is discarded (not mutated) on
// navigation — collapsing the iframe permanently. about:srcdoc is the
// spec-defined URL of a navigated srcdoc document; require parsed content too.
//
// Shared by the email body island (EmailMessageBody) and the composer's
// quoted-HTML view (QuotedHtmlNodeView), which both size a sandboxed srcdoc
// iframe from the parent via a bounded requestAnimationFrame poll.
export function isRealSrcdocReady(doc: Document | null | undefined): doc is Document {
  return doc?.URL === "about:srcdoc" && doc.body != null && doc.body.childNodes.length > 0
}
