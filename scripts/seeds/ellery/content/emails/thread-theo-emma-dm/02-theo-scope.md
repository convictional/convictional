---
key: theo-emma-dm-02-theo-scope
model: EmailMessage
thread: !ref thread-theo-emma-dm
user: !ref theo
message_type: sent
sender: !ref theo
to:
  - !ref emma
subject: "Re: Reviewer UI v3 tweaks"
received_at: !relative_day {offset: -1, hour: 9, tz: America/New_York}
---
<p>Emma,</p>

<p>Good feedback. Here's what I can commit to:</p>

<p><strong>Item 1 (inline accept/reject):</strong> Yes, and I actually agree with your participants — the sidebar placement was a placeholder. Moving the controls inline is the right call. I can have a working build today, but I'll need Jordan to check that the accept/reject events still fire correctly to the backend since I'll be changing the component hierarchy. Should be resolved by tomorrow morning.</p>

<p><strong>Item 2 (playbook rule hover text):</strong> Easy — 2 hours. The rule text is already in the API response, I'm just not rendering it. I'll add a hover tooltip. If you want it shown permanently (not just on hover) for the research sessions, I can do that too — it might actually be better for visibility in session 5.</p>

<p><strong>Item 3 (loading state):</strong> The skeleton state is a slightly bigger change — the current architecture fires all suggestions at once. I can add "Loading suggestions..." with a spinner as a quick fix today, but the real fix (progressive loading) is tied to the API pagination work Arjun is doing. Expect the quick fix by tonight and the real fix next week.</p>

<p>Brief Leo with items 1 and 2 confirmed for session 5. Item 3 quick fix will be in by then too.</p>

<p>Theo</p>
