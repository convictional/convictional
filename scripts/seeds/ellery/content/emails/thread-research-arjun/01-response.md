---
key: arjun-research-response
model: EmailMessage
thread: !ref thread-research-arjun
user: !ref arjun
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref arjun
subject: "[Research] Why did we design residency as region-scoped storage instead of per-tenant sharding?"
received_at: !relative_day {offset: 0, hour: 9, tz: America/New_York}
---
<h1>[Research] Why did we design residency as region-scoped storage instead of per-tenant sharding?</h1>
<blockquote><p>Why did we design residency as region-scoped storage instead of per-tenant sharding?</p></blockquote>
<h2>Summary</h2>
<p>Based on discussions across meetings, posts, goals, and email threads, the decision to implement EU data residency as <strong>region-scoped storage with tenant-aware routing</strong> rather than per-tenant database sharding came down to three factors: operational complexity, time-to-compliance pressure from the Keating deal, and the insight that encryption key isolation — not storage isolation — is the primary audit requirement for SOC 2 Type I.</p>
<h2>Key Findings</h2>
<h3>The Keating timeline drove scope constraints</h3>
<p>The Keating &amp; Marsh security questionnaire established that the compliance requirement was specifically about where EU customer data <em>at rest</em> is encrypted and where keys reside — not about separate database instances. The SOC 2 readiness review with Brandt Soh confirmed that a description-of-criteria approach using envelope encryption with region-isolated KMS keys would satisfy Type I audit requirements without requiring per-tenant sharding.<sup><a href="seed:email_threads/thread-arjun-soc2">1</a></sup></p>
<h3>The Residency ADR Review meeting aligned the engineering team</h3>
<p>The Residency ADR Review meeting (Priya, Arjun, Theo) walked two options: gateway-layer geo-routing versus application-layer tenant-scoped routing. The application-layer approach was chosen because it keeps the gateway dumb, scales to more than two regions without architectural surgery, and aligns with the long-term multi-tenancy model. Per-tenant sharding was considered and ruled out because the migration path from the current single-cluster design would have added 4-6 weeks and introduced new operational risk during the Keating close window.<sup><a href="seed:meetings/mtg-residency-adr-review">2</a></sup></p>
<h3>The Keating/Residency subgoal documents the decision outcome</h3>
<p>The Residency subgoal updates track the arc from initial scoping (at_risk when EU storage scope expanded) to the greenlit spike, confirming that the region-scoped approach was the path that allowed Priya to commit to a staging deployment within the Keating pilot timeline.<sup><a href="seed:goals/keating">3</a></sup></p>
<h3>The security questionnaire post clarified ownership</h3>
<p>The Security Questionnaire post assigned ownership of the EU-residency-related questions (Q44–Q51) to Arjun, with a note that the design document would serve as the primary evidence artifact for the audit.<sup><a href="seed:posts/post-keating-sq">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:email_threads/thread-arjun-soc2">Re: Evidence collection for CC6</a> — Email thread with Brandt Soh (Halden &amp; Rossi)</li>
<li><a href="seed:meetings/mtg-residency-adr-review">Residency ADR Review</a> — Meeting</li>
<li><a href="seed:goals/keating">Keating goal — Residency subgoal updates</a> — Goal</li>
<li><a href="seed:posts/post-keating-sq">Security Questionnaire — Here's How We're Splitting It</a> — Post by Priya Chandrasekaran</li>
</ol>
