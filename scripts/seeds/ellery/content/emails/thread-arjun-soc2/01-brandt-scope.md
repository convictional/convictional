---
key: arjun-soc2-01-brandt-scope
model: EmailMessage
thread: !ref thread-arjun-soc2
user: !ref arjun
message_type: received
sender: "Brandt Soh <brandt.soh@haldenrossi.com>"
to:
  - !ref arjun
  - !ref priya
subject: "Re: Evidence collection for CC6"
received_at: !relative_day {offset: -3, hour: 9, tz: America/New_York}
---
<p>Arjun, Priya,</p>

<p>Following up on our SOC 2 readiness call. For CC6 (Logical and Physical Access Controls) I need the following evidence by end of next week:</p>

<ol>
  <li>Access control policy document (current version)</li>
  <li>User provisioning and deprovisioning procedures — a screenshot or export from your IdP (Okta, Google Workspace, etc.) showing the workflow</li>
  <li>List of privileged accounts with justification for each</li>
  <li>Evidence of MFA enforcement for production systems — screenshot of your SSO settings is fine</li>
  <li>Any terminated user access reviews from the last 90 days</li>
</ol>

<p>On the EU residency piece: if you're scoping that into the audit period, I'll need a separate section in the description of criteria. Let me know if you want to include it in this audit cycle or defer to Type II.</p>

<p>Best,<br>
Brandt Soh<br>
<em>Senior Auditor, Halden &amp; Rossi</em></p>
