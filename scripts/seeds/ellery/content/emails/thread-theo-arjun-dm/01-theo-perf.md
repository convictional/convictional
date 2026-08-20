---
key: theo-arjun-dm-01-theo-perf
model: EmailMessage
thread: !ref thread-theo-arjun-dm
user: !ref theo
message_type: sent
sender: !ref theo
to:
  - !ref arjun
subject: "Re: Review panel performance on large contracts"
received_at: !relative_day {offset: -4, hour: 14, tz: America/New_York}
---
<p>Arjun,</p>

<p>I've been profiling the review panel on the 200+ page contracts we're seeing from the Keating pilot set and it's bad. Specifically:</p>

<ul>
  <li>Initial render on a 220-page MSA takes 4.2s on a fast connection. On the lawyer's typical office laptop, I'm seeing 7-9s.</li>
  <li>The clause-list virtualization I added last sprint helps a lot for the body, but the redline diff view is still rendering all diff hunks at once. That's the bottleneck.</li>
  <li>Memory usage climbs to ~400MB after browsing 5-6 contracts in a session — there's definitely a leak somewhere in the diff store.</li>
</ul>

<p>I think the diff view needs lazy rendering: only render the visible window of diff hunks, load more on scroll. I can spec this out but I want to understand if there's anything on the API side that would help — e.g., if the diff is computed server-side, can we paginate it so we don't ship the full diff payload in one response?</p>

<p>Theo</p>
