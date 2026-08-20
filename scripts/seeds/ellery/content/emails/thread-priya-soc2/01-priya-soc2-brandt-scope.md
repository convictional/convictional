---
key: msg-priya-soc2-brandt-scope
model: EmailMessage
thread: !ref thread-priya-soc2
user: !ref priya
message_type: received
sender: "Brandt Soh <brandt.soh@haldenrossi.com>"
to:
  - !ref priya
subject: "Audit scope and timeline — Ellery SOC 2 Type I"
received_at: !relative_day {offset: -5, hour: 10, tz: America/New_York}
labels: [inbox]
---
<p>Priya,</p>

<p>Good to meet on Tuesday. Following up as promised with the formal scope and timeline for the Type I readiness review.</p>

<p><strong>Proposed audit scope (SOC 2 Type I, Security + Availability trust service criteria):</strong></p>

<ul>
<li>Logical access controls: user authentication, MFA enforcement, privilege management, offboarding</li>
<li>Data encryption: at-rest (AES-256 or equivalent), in-transit (TLS 1.2+), key management</li>
<li>Incident response: documented procedure, on-call runbook, post-mortem evidence</li>
<li>Change management: code review process, deployment controls, environment separation</li>
<li>Vendor management: sub-processor inventory, third-party risk documentation</li>
<li>Monitoring: logging configuration, alerting thresholds, alert-to-action evidence</li>
</ul>

<p><strong>Timeline to Type I opinion:</strong></p>
<p>If we receive complete evidence by May 5, I can issue the draft opinion by May 19 and the final signed opinion by May 26. That gives you a Type I opinion in hand before any Keating contract signatures, which I understand is the goal.</p>

<p><strong>Evidence gaps I noticed in what you sent:</strong></p>
<ol>
<li>No formal offboarding runbook — you mentioned it's a checklist in your wiki; we'll need that formalized and signed as a procedure.</li>
<li>MFA enforcement looks good on the IDP side, but I need evidence of forced enrollment for shared service accounts, not just individual users.</li>
<li>The vendor management spreadsheet is missing contract dates and renewal terms for three vendors. Not blocking, but needs to be complete.</li>
</ol>

<p>Let me know if you have questions on any of the above. Arjun was helpful in the meeting — feel free to loop him in on evidence collection.</p>

<p>Brandt Soh<br>
<em>Senior Auditor, Halden &amp; Rossi</em></p>
