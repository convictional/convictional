---
key: theo-dev-newsletter-01-bytes-issue
model: EmailMessage
thread: !ref thread-theo-dev-newsletter
user: !ref theo
message_type: received
sender: "Bytes <weekly@bytes.dev>"
to:
  - !ref theo
subject: "Bytes — issue #297"
received_at: !relative_day {offset: -2, hour: 8, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,sans-serif;">
<tr><td style="background-color:#1a1a1a;padding:18px 24px;">
<span style="color:#e879f9;font-size:20px;font-weight:bold;">Bytes</span>
<span style="color:#888888;font-size:13px;display:block;margin-top:2px;">Your favorite JavaScript newsletter. Issue #297.</span>
</td></tr>
<tr><td style="padding:24px;color:#1d1d1d;font-size:14px;">

<p>Good morning. This week we have: React 19 concurrent rendering gotchas, the virtualization library you should be using for large lists (hint: it's not the one you're using), and why localStorage is still broken in 2026.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<h2 style="font-family:Georgia,serif;font-size:17px;color:#1a1a1a;">The Real Cost of Not Virtualizing</h2>
<p>If you're rendering more than 200 DOM nodes at once in React without virtualization, you're already losing. The math is simple: a list of 500 items at 60fps means your React reconciler is touching 500 nodes 60 times per second. TanStack Virtual is the library that actually handles this well at production scale — and unlike some alternatives, it works correctly with variable-height rows.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<h2 style="font-family:Georgia,serif;font-size:17px;color:#1a1a1a;">localStorage: It Was Never Meant for This</h2>
<p>This week's cautionary tale: a team ships a feature that caches large JSON payloads in localStorage. It works great — until a user opens a large document and everything breaks. The localStorage quota is typically 5-10MB depending on the browser. If you're storing diffs, history, or any large structured data, use IndexedDB. It's asynchronous, has a larger quota, and has much better error handling when you hit limits.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<h2 style="font-family:Georgia,serif;font-size:17px;color:#1a1a1a;">React 19: Concurrent Rendering Edge Cases</h2>
<p>Concurrent mode is great until it isn't. The edge cases that bite teams: (1) effects that fire twice in strict mode are not a bug — stop fighting them, (2) if you're using external stores, you need <span style="font-family:Courier New,monospace;font-size:12px;">useSyncExternalStore</span> or you'll get tearing, (3) transitions don't work the way you think they do inside forms.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<p style="font-size:12px;color:#888888;">Bytes &bull; <a href="#" style="color:#888888;">Unsubscribe</a> &bull; <a href="#" style="color:#888888;">View in browser</a></p>
</td></tr>
</table>
