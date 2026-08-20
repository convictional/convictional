---
key: response
model: EmailMessage
thread: !ref thread-research-maren
user: !ref maren
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref maren
subject: "[Research] Why are we prioritizing coverage over the redline co-pilot?"
received_at: !relative_day {offset: 0, hour: 8, tz: America/New_York}
labels: [inbox, unread]
---
<h1>[Research] Why are we prioritizing coverage over the redline co-pilot?</h1>
<blockquote><p>Why are we prioritizing coverage over the redline co-pilot?</p></blockquote>
<h2>Summary</h2>
<p>Based on discussions across posts, meetings, and emails, the case for prioritizing DPA and MSA playbook coverage over the redline co-pilot is grounded in measurable customer-facing gaps, direct feedback from existing enterprise customers, and a judgment that a speculative feature built on thin coverage data is likely to underperform. The debate is formally open, but the coverage-first position has significant empirical support.</p>
<h2>Key Findings</h2>
<h3>Coverage gaps are measurable and already visible in customer behavior</h3>
<p>Rhea's data shows that 76% of DPA clauses return uncertain or no-opinion, and DPA sub-processor language generates more customer overrides than any other category. This data was compiled specifically for the coverage memo and represents the strongest quantitative case for the coverage-first argument. The coverage gaps are not hypothetical — they're active friction in existing customer workflows.<sup><a href="seed:email_threads/thread-maren-rhea-coverage">1</a></sup></p>
<h3>Alderman Holdings has named the gap directly</h3>
<p>Drew Halberstam, Head of Legal Ops at Alderman Holdings, raised DPA coverage as a workflow bottleneck in an unprompted email. His team has been running DPA volume through the platform and experiencing thin suggestions on the clause categories that matter most — sub-processor change notifications, DSR timelines, and lawful basis documentation. Maren's response committed Alderman to a reference playbook partnership, which provides both urgency and a structured feedback loop for coverage work.<sup><a href="seed:email_threads/thread-maren-drew-coverage">2</a></sup></p>
<h3>The Coverage-First Memo makes the roadmap case directly</h3>
<p>Maren's Coverage-First Memo argues that shipping the redline co-pilot on top of a coverage library with 29% DPA completeness would produce a feature whose quality is bounded by its weakest data source. The memo frames coverage work not as a delay to the co-pilot, but as prerequisite infrastructure that determines whether the co-pilot's suggestions are defensible.<sup><a href="seed:posts/post-coverage-memo">3</a></sup></p>
<h3>The Coverage-First Walk-Through surfaced engineering agreement</h3>
<p>In the Coverage-First Memo walk-through meeting, Priya restated the engineering cost of each path in terms the team could compare. Her read: coverage work creates reusable evaluation infrastructure that benefits both the coverage gaps and any future AI features, whereas the redline co-pilot built before evals are ready would require re-engineering later. This was a significant input to Darren's decision to defer the call to Emma's research.<sup><a href="seed:meetings/mtg-coverage-walkthrough">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:email_threads/thread-maren-rhea-coverage">Coverage memo — your numbers</a> — Email thread with Rhea</li>
<li><a href="seed:email_threads/thread-maren-drew-coverage">DPA playbook gaps</a> — Email thread with Drew Halberstam</li>
<li><a href="seed:posts/post-coverage-memo">Coverage-First Memo</a> — Post by Maren Kovacs</li>
<li><a href="seed:meetings/mtg-coverage-walkthrough">Coverage-First Memo Walk-Through</a> — Meeting</li>
</ol>
