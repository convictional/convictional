---
key: arjun-soc2-02-arjun-reply
model: EmailMessage
thread: !ref thread-arjun-soc2
user: !ref arjun
message_type: sent
sender: !ref arjun
to:
  - "Brandt Soh <brandt.soh@haldenrossi.com>"
  - !ref priya
subject: "Re: Evidence collection for CC6"
received_at: !relative_day {offset: -3, hour: 14, tz: America/New_York}
---
<p>Brandt,</p>

<p>Good list. A few notes:</p>

<p><strong>1-4:</strong> I can have all of these by Thursday. We run Google Workspace with MFA enforced via organizational policy — I'll export the admin console screenshot. Privileged accounts are documented; I'll clean up the justifications for the two service accounts we still have kicking around from the pre-seed infra.</p>

<p><strong>5 (terminated user reviews):</strong> We've had two departures in the 90-day window. Both were revoked within 24 hours. I have the provisioning log entries but we don't have a formal sign-off artifact — is a timestamped export from the admin console sufficient, or do you need a separate sign-off doc?</p>

<p><strong>EU residency:</strong> We're targeting staging in 3 weeks. Priya wants to include it in this audit cycle. I'll have a draft of the data-flow diagram next week. If that timeline doesn't fit your scope window, tell me now.</p>

<p>Arjun</p>
