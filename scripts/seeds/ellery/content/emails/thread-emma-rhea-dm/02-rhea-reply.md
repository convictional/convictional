---
key: msg-emma-rhea-dm-rhea-reply
model: EmailMessage
thread: !ref thread-emma-rhea-dm
user: !ref emma
message_type: received
sender: !ref rhea
to:
  - !ref emma
subject: "Re: Lawyer-specific usability heuristics"
received_at: !relative_day {offset: -3, hour: 14, tz: America/New_York}
---
<p>Emma,</p>

<p>Happy to look. Send the task list.</p>

<p>Quick answer to your question: when a lawyer sees a suggested redline, their first three instincts (in order) are: (1) is this consistent with what we've agreed before on this type of clause, (2) who's the counterparty and does their risk appetite matter here, and (3) what's the business cost if this clause goes to negotiation. None of those are obvious from a UI.</p>

<p>The thing that would break them is if the suggestion doesn't account for #1 — prior consistency. If they've done a hundred NDAs and this redline contradicts their muscle memory, they'll reject it and blame the tool, not the playbook.</p>

<p>Send me the task list and I'll mark up which prompts are likely to surface that.</p>

<p>Rhea</p>
