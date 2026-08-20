---
key: response
model: EmailMessage
thread: !ref thread-research-priya
user: !ref priya
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref priya
subject: "[Research] Why did we sequence SRE ahead of the 2nd backend engineer?"
received_at: !relative_day {offset: 0, hour: 8, tz: America/New_York}
labels: [inbox, unread]
---
<h1>[Research] Why did we sequence SRE ahead of the 2nd backend engineer?</h1>
<blockquote><p>Why did we sequence SRE ahead of the 2nd backend engineer?</p></blockquote>
<h2>Summary</h2>
<p>Based on discussions across posts, meetings, and emails, SRE was sequenced ahead of a second backend engineer for two compounding reasons: the Keating &amp; Marsh deal is exposing reliability infrastructure gaps that need an owner before the platform scales to enterprise load, and the Engineering Hiring Deep-Dive meeting surfaced a consensus that the team's biggest risk is reliability and observability architecture, not raw backend headcount.</p>
<h2>Key Findings</h2>
<h3>Priya's hiring plan explicitly prioritizes SRE for infrastructure ownership</h3>
<p>The Hiring Plan v1 post lays out the sequencing rationale in engineering terms: the SRE hire is needed to own the on-call rotation design, the observability stack, and the reliability roadmap before Ellery scales to enterprise customers. The current setup works at startup scale but isn't designed for the audit trail, uptime commitment, and incident response discipline that enterprise customers like Keating will require. A second backend engineer adds throughput; an SRE adds reliability architecture that no backend engineer specializes in.<sup><a href="seed:posts/post-hiring-plan">1</a></sup></p>
<h3>The Engineering Hiring Deep-Dive produced a soft yes on SRE-first</h3>
<p>In the Engineering Hiring Deep-Dive meeting, Priya and Arjun walked through the SRE-first argument with Darren. Arjun's input was direct: the contract ingestion pipeline is showing early signs of connection pool stress under load, and without an SRE owning the reliability architecture, the team will spend backend-engineering cycles on operational fires rather than product features. Darren's only open question was the scope of the integrations engineer role, not the SRE sequencing.<sup><a href="seed:meetings/mtg-eng-hiring">2</a></sup></p>
<h3>Keating's enterprise requirements create a reliability forcing function</h3>
<p>Priya's email to Darren on hiring order v2 makes the Keating connection explicit: the SOC 2 evidence collection, incident response documentation, and uptime commitments required for the Keating deal all benefit from having an SRE who owns these artifacts. A second backend engineer doesn't change Ellery's reliability posture — an SRE does.<sup><a href="seed:email_threads/thread-priya-darren-hiring">3</a></sup></p>
<h3>The Hire goal's Engineering subgoal reflects SRE as the first close</h3>
<p>The Engineering subgoal under the Hire goal targets SRE, 2nd ML engineer, and integrations engineer as the three roles to close in 6 weeks. The sequencing implied is SRE first, consistent with Priya's hiring plan and the Engineering Hiring Deep-Dive outcome.<sup><a href="seed:goals/hire-engineering">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:posts/post-hiring-plan">Hiring Plan v1</a> — Post by Priya Chandrasekaran</li>
<li><a href="seed:meetings/mtg-eng-hiring">Engineering Hiring Deep-Dive</a> — Meeting</li>
<li><a href="seed:email_threads/thread-priya-darren-hiring">Hiring order v2 — my updated read</a> — Email thread with Darren</li>
<li><a href="seed:goals/hire-engineering">Engineering subgoal</a> — Hire goal</li>
</ol>
