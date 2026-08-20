---
key: response
model: EmailMessage
thread: !ref thread-research-leo
user: !ref leo
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref leo
subject: "[Research] What does the research so far say about the redline co-pilot?"
received_at: !relative_day {offset: 0, hour: 9, tz: America/New_York}
labels: [inbox, unread]
---
<h1>[Research] What does the research so far say about the redline co-pilot?</h1>
<blockquote><p>What does the research so far say about the redline co-pilot?</p></blockquote>
<h2>Summary</h2>
<p>Based on discussions across posts, meetings, emails, and goals, the research sprint (4 of 6 sessions complete) has produced mixed but directionally useful signals. Lawyers are receptive to AI suggestions when they understand the source — playbook-grounded suggestions are trusted more than black-box outputs. The most significant unexpected finding is that reviewers are using the tool in ways not anticipated by the design, suggesting the current interaction model may need revisiting before the design-partner launch.</p>
<h2>Key Findings</h2>
<h3>Redline Co-pilot PRD established the design hypotheses under test</h3>
<p>Leo's PRD articulated three core hypotheses for the research sprint to validate: that reviewers would trust playbook-grounded suggestions, that prior-edit context would improve acceptance rates, and that the reviewer UI could surface suggestions without increasing cognitive load. The PRD also acknowledged the eval-readiness dependency — research findings and eval results were meant to converge before the design-partner launch decision.<sup><a href="seed:posts/post-redline-prd">1</a></sup></p>
<h3>Research Synthesis Working Session is the planned decision gate</h3>
<p>The Research Synthesis Working Session (scheduled in 2 days) is structured to walk the findings with Maren, Darren, and the product team and identify the single finding that changes the roadmap. This meeting has not yet occurred at the snapshot moment; its outcome is the formal input into the Ship decision post.<sup><a href="seed:meetings/mtg-research-synthesis">2</a></sup></p>
<h3>Design partner email thread reveals unexpected usage behavior</h3>
<p>Emma's exchange with Leo on research prompts notes that session 3 (Alderman associate) surfaced usage behavior "not designed for" that may be "more interesting than what we built." This is consistent with the pattern Kai Andersen flagged — a limitation-of-liability clause suggestion that pulled from the wrong contract type. These findings suggest the interaction model may need iteration before the design-partner rollout.<sup><a href="seed:email_threads/thread-leo-emma-dm">3</a></sup></p>
<h3>Ship / Research subgoal is on track per latest update</h3>
<p>The Ship / Research subgoal is tracking at 0.67 progress with 4 of 6 sessions complete. The goal update notes that Emma's synthesis is the dependency for the roadmap decision — no decision is expected before the synthesis lands on day 1 week.<sup><a href="seed:goals/ship-research">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:posts/post-redline-prd">Redline Co-pilot PRD</a> — Post by Leo Park</li>
<li><a href="seed:meetings/mtg-research-synthesis">Research Synthesis Working Session</a> — Meeting</li>
<li><a href="seed:email_threads/thread-leo-emma-dm">Research prompts — v2</a> — Email thread with Emma Lindqvist</li>
<li><a href="seed:goals/ship-research">Ship / Research</a> — Goal</li>
</ol>
