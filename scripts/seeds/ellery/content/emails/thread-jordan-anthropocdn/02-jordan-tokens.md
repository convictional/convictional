---
key: jordan-anthropocdn-02-jordan-tokens
model: EmailMessage
thread: !ref thread-jordan-anthropocdn
user: !ref jordan
message_type: sent
sender: !ref jordan
to:
  - "Riley Maddox <riley@anthropocdn.co>"
subject: "Re: Inference pricing at scale"
received_at: !relative_day {offset: -5, hour: 11, tz: America/New_York}
---
<p>Riley,</p>

<p>Good to know on EU routing — that's a near-term requirement, not a nice-to-have.</p>

<p>Rough estimates for the cost model:</p>
<ul>
  <li><strong>Interactive mode (redline suggestions during live review):</strong> ~2,000 input tokens per clause + context window, ~500 output tokens. We estimate 50-200 clauses per contract, maybe 10-30 contracts/day initially.</li>
  <li><strong>Batch eval jobs:</strong> We run evals nightly on our benchmark set — currently ~300 examples, will grow to ~1,000. Each eval run is roughly the same input/output as interactive mode but all at once.</li>
  <li><strong>Playbook retrieval + re-ranking (separate from generation):</strong> Smaller context, but we're running it on every clause touch — estimate 800 input tokens, negligible output.</li>
</ul>

<p>The EU residency piece matters but I don't need a contractual commitment right now — I just need to know the architecture is there and that I won't have to migrate if we sign Keating. Decision timeline is 3-4 weeks on our side.</p>

<p>Jordan</p>
