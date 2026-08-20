---
key: response
model: EmailMessage
thread: !ref thread-research-tessa
user: !ref tessa
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref tessa
subject: "[Research] What drove the decision to accept Keating's EU residency requirement?"
received_at: !relative_day {offset: 0, hour: 8, tz: America/New_York}
labels: [inbox, unread]
---
<h1>[Research] What drove the decision to accept Keating's EU residency requirement?</h1>
<blockquote><p>What drove the decision to accept Keating's EU residency requirement?</p></blockquote>
<h2>Summary</h2>
<p>Based on discussions across goals, meetings, posts, and emails, the decision to accept Keating &amp; Marsh's EU data residency requirement was driven by two converging factors: the strategic importance of the deal (Keating would be Ellery's largest customer by 3x) and Arjun's technical spike confirming the residency work was feasible within the proposal timeline. The decision was contentious internally — Priya and Arjun initially urged caution about scope — but Tessa and Darren concluded the revenue opportunity justified the engineering investment.</p>
<h2>Key Findings</h2>
<h3>Deal Health Post confirms EU residency as the key technical blocker</h3>
<p>Tessa's <em>Keating — Deal Health &amp; Asks</em> post identified EU data residency alongside SOC 2 as the two gating items for Keating's paper review, with Arjun named as the owner of the residency track. The post noted Keating's London and Frankfurt offices as the driver of the requirement, and set in 3 weeks as the target for staging-ready delivery.<sup><a href="seed:posts/post-keating-health">1</a></sup></p>
<h3>Residency ADR Review meeting surfaced the internal trade-off debate</h3>
<p>The Residency ADR Review meeting (6 days ago) was the moment the team explicitly weighed the scope risk. Priya and Arjun presented two architectural options; the region-scoped storage approach was selected over per-tenant sharding because it was achievable within the timeline and lower in operational complexity. Theo was also present — the UI implications of region-aware routing were discussed. The team did not formally vote, but the record shows consensus around the region-scoped approach.<sup><a href="seed:meetings/mtg-residency-adr-review">2</a></sup></p>
<h3>Keating goal tracking confirms scope commitment</h3>
<p>The <em>Keating / Residency</em> subgoal recorded a status transition from on_track to at_risk at 7 days ago as the EU storage scope expanded, then returned to on_track at 2 days ago after Arjun's spike confirmed feasibility. This arc reflects the internal deliberation: the commitment was made, tested against engineering reality, and confirmed.<sup><a href="seed:goals/keating-residency">3</a></sup></p>
<h3>Proposal email thread shows Amira's confirmation of the technical scope</h3>
<p>The pilot proposal email exchange shows Amira Saleh confirming that the technical appendix on region-scoped storage (section 4) addressed Doug Rennert's security questions, and Peter Nakagawa signaling satisfaction with the response quality. This external confirmation aligns with the internal decision timeline.<sup><a href="seed:email_threads/thread-tessa-keating">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:posts/post-keating-health">Keating — Deal Health &amp; Asks</a> — Post by Tessa Nguyen</li>
<li><a href="seed:meetings/mtg-residency-adr-review">Residency ADR Review</a> — Meeting</li>
<li><a href="seed:goals/keating-residency">Keating / Residency</a> — Goal</li>
<li><a href="seed:email_threads/thread-tessa-keating">Pilot proposal — revisions</a> — Email thread with Peter Nakagawa and Amira Saleh</li>
</ol>
