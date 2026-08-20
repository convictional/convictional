---
key: jordan-anthropocdn-03-riley-model
model: EmailMessage
thread: !ref thread-jordan-anthropocdn
user: !ref jordan
message_type: received
sender: "Riley Maddox <riley@anthropocdn.co>"
to:
  - !ref jordan
subject: "Re: Inference pricing at scale"
received_at: !relative_day {offset: -5, hour: 15, tz: America/New_York}
---
<p>Jordan,</p>

<p>Based on your numbers, rough estimate:</p>

<table cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px;margin:12px 0;">
<tr style="background-color:#f6f8fa;"><th align="left" style="border:1px solid #e1e4e8;padding:6px 10px;">Mode</th><th align="right" style="border:1px solid #e1e4e8;padding:6px 10px;">Monthly tokens</th><th align="right" style="border:1px solid #e1e4e8;padding:6px 10px;">Est. cost</th></tr>
<tr><td style="border:1px solid #e1e4e8;padding:6px 10px;">Interactive (mid-range)</td><td align="right" style="border:1px solid #e1e4e8;padding:6px 10px;">~8M</td><td align="right" style="border:1px solid #e1e4e8;padding:6px 10px;">~$96/mo</td></tr>
<tr style="background-color:#f6f8fa;"><td style="border:1px solid #e1e4e8;padding:6px 10px;">Nightly evals</td><td align="right" style="border:1px solid #e1e4e8;padding:6px 10px;">~2.4M</td><td align="right" style="border:1px solid #e1e4e8;padding:6px 10px;">~$29/mo</td></tr>
<tr><td style="border:1px solid #e1e4e8;padding:6px 10px;">Retrieval/re-ranking</td><td align="right" style="border:1px solid #e1e4e8;padding:6px 10px;">~4M</td><td align="right" style="border:1px solid #e1e4e8;padding:6px 10px;">~$20/mo</td></tr>
</table>

<p>At current scale that's well under the volume tier threshold, so you'd be on standard per-token pricing. The EU routing is included — no surcharge. If you hit 50M tokens/month the tier kicks in and effective rate drops ~15%.</p>

<p>3-4 weeks works fine on my side. Happy to hold a sandbox API key for you in the meantime so your evals aren't blocked on the procurement conversation.</p>

<p>Riley<br>
<em>Anthropocdn</em></p>
