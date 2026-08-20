---
key: theo-research-response
model: EmailMessage
thread: !ref thread-research-theo
user: !ref theo
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref theo
subject: "[Research] Why did we prioritize the reviewer UI over the playbook editor for Q3?"
received_at: !relative_day {offset: 0, hour: 9, tz: America/New_York}
---
<h1>[Research] Why did we prioritize the reviewer UI over the playbook editor for Q3?</h1>
<blockquote><p>Why did we prioritize the reviewer UI over the playbook editor for Q3?</p></blockquote>
<h2>Summary</h2>
<p>Based on discussions across posts, meetings, goals, and email threads, the decision to prioritize the reviewer UI over the playbook editor for Q3 was driven by two converging factors: the redline co-pilot prototype requires a high-quality reviewer surface to be useful in research sessions, and Emma's customer research data consistently showed that lawyers spend most of their time in the review flow, not in playbook authoring.</p>
<h2>Key Findings</h2>
<h3>The product principles established the reviewer UI as the primary surface</h3>
<p>Leo's Product Principles post articulated the core design philosophy: "the reviewer panel is the lawyer's cockpit." This framing established a priority hierarchy in which improvements to the review flow take precedence over improvements to the playbook authoring experience, since the review flow is where end users spend the most time and where mistakes have the most consequence.<sup><a href="seed:posts/post-product-principles">1</a></sup></p>
<h3>The Redline Co-pilot Design Review locked the dependency</h3>
<p>The Redline Co-pilot Design Review meeting (Leo, Emma, Jordan, Theo, Priya) established that the prototype would live inside the reviewer panel — not as a standalone tool. This created a hard dependency: shipping the co-pilot prototype required the reviewer UI to be at a quality level suitable for customer research sessions. The playbook editor was explicitly deferred to post-research, contingent on the roadmap decision.<sup><a href="seed:meetings/mtg-redline-copilot-design-review">2</a></sup></p>
<h3>The Ship goal encodes the priority</h3>
<p>The Ship goal's subgoals include Co-pilot (reviewer surface) but not a playbook editor milestone for Q3. The Coverage subgoal (DPA + MSA playbook coverage) is owned by Rhea and Maren on the content side, not by Theo on the UI side — meaning the playbook editor work is not blocking the coverage goal.<sup><a href="seed:goals/ship">3</a></sup></p>
<h3>Emma's research plan confirmed reviewer surface as the research focus</h3>
<p>Emma's Customer Research Plan post described all six research sessions as focused on the reviewer panel experience, not the playbook editor. The session design (lawyers reviewing real contracts with the prototype active) only requires the reviewer UI to function well. This further locked in the Q3 priority order.<sup><a href="seed:posts/post-research-plan">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:posts/post-product-principles">Product Principles — v0</a> — Post by Leo Park</li>
<li><a href="seed:meetings/mtg-redline-copilot-design-review">Redline Co-pilot Design Review</a> — Meeting</li>
<li><a href="seed:goals/ship">Ship goal</a> — Goal</li>
<li><a href="seed:posts/post-research-plan">Customer Research Plan</a> — Post by Emma Lindqvist</li>
</ol>
