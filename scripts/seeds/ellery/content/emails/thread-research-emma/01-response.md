---
key: response
model: EmailMessage
thread: !ref thread-research-emma
user: !ref emma
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref emma
subject: "[Research] What are we learning from the redline co-pilot research sessions?"
received_at: !relative_day {offset: 0, hour: 9, tz: America/New_York}
---
<h1>[Research] What are we learning from the redline co-pilot research sessions?</h1>
<blockquote><p>What are we learning from the redline co-pilot research sessions?</p></blockquote>
<h2>Summary</h2>
<p>Across four completed sessions with in-house lawyers, the dominant finding is that lawyers will not act on AI-suggested redlines without visible provenance — specifically, they want to know both where the suggestion came from (the playbook clause) and who authorized that playbook. Accuracy alone does not create trust.</p>
<h2>Key Findings</h2>
<h3>Research plan set the provenance-first agenda</h3>
<p>Emma's Customer Research Plan post laid out a 6-session sprint designed to observe lawyers using the prototype on real contract review tasks. The plan explicitly targeted the gap between "prototype accuracy" and "prototype adoption" — framing the research question as a trust problem, not a feature completeness problem. Rhea Patel commented with supporting data from playbook coverage gaps, and Leo Park confirmed observer access for sessions 3–6.<sup><a href="seed:posts/post-research-plan">1</a></sup></p>
<h3>Session 4 surfaced the core insight</h3>
<p>The Research Synthesis Working Session is scheduled to formalize findings, but notes from session 4 document the pivotal quote: a participant stopped mid-task and said "I don't trust this suggestion because I don't know where it came from." When shown the playbook citation panel, the participant partially accepted the suggestion but then asked "what if the playbook is wrong?" — indicating that trust requires both provenance and authority, not just a source link.<sup><a href="seed:meetings/mtg-redline-copilot-design-review">2</a></sup></p>
<h3>Research is the tiebreaker in the roadmap debate</h3>
<p>The Ship goal frames Emma's research synthesis as the data that will close the redline co-pilot decision. The current goal status reflects an open decision: Leo's co-pilot PRD argues for shipping a full feature; Maren's Coverage-First Memo argues for closing coverage gaps first. The research findings — particularly the playbook authority problem — add a third dimension that neither memo fully addressed.<sup><a href="seed:goals/ship">3</a></sup></p>
<h3>Lawyer-specific UX heuristics inform session design</h3>
<p>Internal consultation with Rhea Patel on lawyer usability heuristics revealed that lawyers evaluate AI suggestions against three sequential criteria: prior consistency, counterparty risk appetite, and negotiation cost. These criteria are not surfaced by the current prototype UI, which the research sessions have confirmed causes hesitation even when suggestions are correct.<sup><a href="seed:posts/post-redline-prd">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:posts/post-research-plan">Customer Research Plan</a> — Post by Emma Lindqvist</li>
<li><a href="seed:meetings/mtg-redline-copilot-design-review">Redline Co-pilot Design Review</a> — Meeting</li>
<li><a href="seed:goals/ship">Ship</a> — Goal</li>
<li><a href="seed:posts/post-redline-prd">Redline Co-pilot PRD</a> — Post by Leo Park</li>
</ol>
