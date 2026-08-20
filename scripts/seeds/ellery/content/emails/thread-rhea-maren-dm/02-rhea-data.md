---
key: msg-rhea-maren-dm-rhea-data
model: EmailMessage
thread: !ref thread-rhea-maren-dm
user: !ref rhea
message_type: sent
sender: !ref rhea
to:
  - !ref maren
subject: "Re: Coverage memo — my numbers"
received_at: !relative_day {offset: -4, hour: 17, tz: America/New_York}
---
<p>Maren,</p>

<p>Here's the current state as of today:</p>

<p><strong>MSAs:</strong> 82% of clause types have at least one position defined. 61% have a customer-preferred alternative. Zero-coverage clauses: liquidated damages, IP ownership on custom development, source code escrow.</p>

<p><strong>DPAs:</strong> 54% of clause types have at least one position defined. 31% have a customer-preferred alternative. Zero-coverage clauses: LGPD (Brazil), PIPL (China), cross-border transfer mechanisms other than SCCs, breach notification to third-party regulators (not just data subjects).</p>

<p><strong>NDAs:</strong> 91% of clause types defined. 78% with alternatives. Near-complete except for NDAs in employment contexts (different legal frame) and NDAs with embedded IP assignment language.</p>

<p>The DPA number is the one that surprised me most. We're at barely half coverage on a contract type that every enterprise customer requires. That's the number to put in the memo.</p>

<p>Rhea</p>
