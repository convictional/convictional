---
key: theo-emma-dm-01-emma-tweaks
model: EmailMessage
thread: !ref thread-theo-emma-dm
user: !ref theo
message_type: received
sender: !ref emma
to:
  - !ref theo
subject: "Re: Reviewer UI v3 tweaks"
received_at: !relative_day {offset: -2, hour: 16, tz: America/New_York}
---
<p>Theo,</p>

<p>Notes from session 4 — things I want to get in before session 5:</p>

<ol>
  <li><strong>Accept/reject button placement:</strong> Two out of three lawyers tried to click in the wrong place on the first pass. They expected the accept/reject to be <em>inline</em> in the diff, next to the suggested redline, not in the sidebar. This is a priority change — can we move those controls?</li>
  <li><strong>Playbook rule reference:</strong> When the co-pilot surfaces a suggestion, it shows the rule ID (<span style="font-family:Courier New,monospace;font-size:12px;">PB-NDA-037</span>) but not the rule text. The lawyers kept stopping to look it up. Can you show a one-line summary of the rule on hover, or inline below the suggestion?</li>
  <li><strong>Loading state:</strong> On the large contract (220-page MSA), the panel loads and then the redline suggestions trickle in over 4-5 seconds. One participant thought the feature wasn't working. We need a better skeleton state — even just "Loading suggestions..." with a spinner would help.</li>
</ol>

<p>None of these are hard, right? I want to brief Leo tomorrow and I'd like to say "items 1 and 2 will be in the build by session 5."</p>

<p>Emma</p>
