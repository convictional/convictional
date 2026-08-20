---
key: jordan-research-response
model: EmailMessage
thread: !ref thread-research-jordan
user: !ref jordan
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref jordan
subject: "[Research] Why did we decide to ship the redline co-pilot behind a flag before publishing evals?"
received_at: !relative_day {offset: 0, hour: 9, tz: America/New_York}
---
<h1>[Research] Why did we decide to ship the redline co-pilot behind a flag before publishing evals?</h1>
<blockquote><p>Why did we decide to ship the redline co-pilot behind a flag before publishing evals?</p></blockquote>
<h2>Summary</h2>
<p>Based on discussions across posts, meetings, goals, and email threads, the decision to ship the redline co-pilot prototype behind a feature flag prior to finalizing the eval harness was driven by the research sprint timeline: Emma needed real prototype access for customer research sessions, and the research findings are the tiebreaker for the broader roadmap decision. The flag approach was explicitly framed as a <em>research instrument</em>, not a production launch.</p>
<h2>Key Findings</h2>
<h3>The research sprint created the pull</h3>
<p>Emma's research plan post established a 6-session sprint with a synthesis deadline of in 1 week — the same week as the formal roadmap decision post. The research sessions required participants to interact with a real prototype rather than mockups. This created a hard dependency on the prototype being accessible to at least two design partner customers before evals were complete.<sup><a href="seed:posts/post-research-plan">1</a></sup></p>
<h3>The Design Review aligned on the flag approach</h3>
<p>The Redline Co-pilot Design Review meeting (Leo, Emma, Jordan, Theo, Priya) surfaced the flag approach as a deliberate constraint — specifically, that any prototype access would require an explicit disclaimer in the UI and that no customer data would be used for training without explicit opt-in. Jordan raised concerns about the eval readiness; Leo's response was that the research sessions were about understanding workflow fit, not quality benchmarking.<sup><a href="seed:meetings/mtg-redline-copilot-design-review">2</a></sup></p>
<h3>The Co-pilot subgoal tracks the flag rollout</h3>
<p>The Ship/Co-pilot subgoal specifies shipping to ≥3 design-partner customers behind a flag in 6 weeks. The flag-first approach is explicitly encoded in the goal as the planned path — not a workaround for incomplete evals, but the agreed delivery shape for the research phase.<sup><a href="seed:goals/ship">3</a></sup></p>
<h3>The Redline Co-pilot PRD framed the decision</h3>
<p>Leo's PRD post describes the prototype-behind-flag as an intentional "learning loop" — the prototype generates the research data, the research data informs whether to invest in evals, and the evals then gate any public rollout. The flag is a risk management tool, not a shortcut.<sup><a href="seed:posts/post-redline-prd">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:posts/post-research-plan">Customer Research Plan</a> — Post by Emma Lindqvist</li>
<li><a href="seed:meetings/mtg-redline-copilot-design-review">Redline Co-pilot Design Review</a> — Meeting</li>
<li><a href="seed:goals/ship">Ship goal — Co-pilot subgoal</a> — Goal</li>
<li><a href="seed:posts/post-redline-prd">Redline Co-pilot PRD</a> — Post by Leo Park</li>
</ol>
