---
key: theo-arjun-dm-02-arjun-response
model: EmailMessage
thread: !ref thread-theo-arjun-dm
user: !ref arjun
message_type: received
sender: !ref arjun
to:
  - !ref theo
subject: "Re: Review panel performance on large contracts"
received_at: !relative_day {offset: -3, hour: 9, tz: America/New_York}
---
<p>Theo,</p>

<p>Those numbers are what I expected but they're still rough to see in writing. A few things:</p>

<p><strong>Server-side pagination for the diff:</strong> Yes, the diff is computed server-side and right now we return the whole thing. I can add a cursor-based endpoint — something like <span style="font-family:Courier New,monospace;font-size:12px;">GET /contracts/{id}/diff?from=0&amp;limit=50</span> that returns the first N diff hunks. The tricky part is that diffs don't chunk cleanly by line count — a single logical change might span 40 lines. I'd suggest chunking by hunk count, not line count. Let me know if that works for your lazy renderer.</p>

<p><strong>Memory leak:</strong> This is probably the diff store not clearing on contract unload. Check if you're holding a reference to the full diff payload in the store even after navigating away. If so, call <span style="font-family:Courier New,monospace;font-size:12px;">store.clear()</span> in the unmount hook.</p>

<p>I'll prioritize the pagination endpoint — want it before Keating sees the panel. Give me 2-3 days.</p>

<p>Arjun</p>
