---
key: msg-priya-datadog-monthly
model: EmailMessage
thread: !ref thread-priya-datadog
user: !ref priya
message_type: received
sender: "Datadog <no-reply@datadoghq.com>"
to:
  - !ref priya
subject: "Monthly performance report — Ellery platform (March 2026)"
received_at: !relative_day {offset: -6, hour: 7, tz: America/New_York}
labels: [inbox]
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;">
<tr><td style="background-color:#632ca6;padding:18px 24px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:20px;font-weight:bold;">Datadog</span>
<span style="color:#d4b8f0;font-family:Arial,sans-serif;font-size:13px;"> &bull; Monthly Digest</span>
</td></tr>
<tr><td style="padding:20px 24px;font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;">
<p style="font-size:15px;font-weight:bold;color:#632ca6;margin-top:0;">Ellery Platform — March 2026 Performance Summary</p>

<table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse;margin:12px 0;">
<tr style="background-color:#f8f4fe;">
<th align="left" style="font-size:12px;color:#555;border-bottom:2px solid #632ca6;padding:8px;">Metric</th>
<th align="right" style="font-size:12px;color:#555;border-bottom:2px solid #632ca6;padding:8px;">March</th>
<th align="right" style="font-size:12px;color:#555;border-bottom:2px solid #632ca6;padding:8px;">vs. February</th>
</tr>
<tr>
<td style="padding:8px;border-bottom:1px solid #f0f0f0;">API uptime</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;color:#16a34a;font-weight:bold;">99.93%</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;color:#16a34a;">&#9650; +0.04%</td>
</tr>
<tr>
<td style="padding:8px;border-bottom:1px solid #f0f0f0;">P95 API latency (contract review)</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;">312ms</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;color:#dc2626;">&#9660; +48ms</td>
</tr>
<tr>
<td style="padding:8px;border-bottom:1px solid #f0f0f0;">Contract ingestion throughput</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;">2,840 docs/day</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;color:#16a34a;">&#9650; +18%</td>
</tr>
<tr>
<td style="padding:8px;border-bottom:1px solid #f0f0f0;">LLM inference latency (P50)</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;">1.8s</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;color:#d97706;">&#9660; +0.3s</td>
</tr>
<tr>
<td style="padding:8px;border-bottom:1px solid #f0f0f0;">Error rate (5xx)</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;color:#16a34a;">0.04%</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;color:#16a34a;">&#9660; -0.01%</td>
</tr>
<tr>
<td style="padding:8px;">RDS CPU (average, peak)</td>
<td align="right" style="padding:8px;">38% / 81%</td>
<td align="right" style="padding:8px;color:#dc2626;">&#9650; Peak +14%</td>
</tr>
</table>

<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">

<p style="font-weight:bold;color:#632ca6;">Alerts fired in March</p>
<ul style="font-size:13px;color:#333;">
<li>2 P3 incidents (both latency spikes, both resolved auto or &lt;20m)</li>
<li>0 P2 or higher incidents</li>
<li>14 informational alerts (disk usage warnings, connection pool warnings)</li>
</ul>

<p style="font-size:13px;color:#666;"><em>Note: RDS peak CPU increase correlates with the 18% throughput increase. No anomaly detected beyond normal load growth. Recommended action: review connection pool settings before next throughput milestone.</em></p>
</td></tr>
<tr><td style="background-color:#f6f4fe;padding:12px 24px;text-align:center;font-family:Arial,sans-serif;font-size:11px;color:#666666;">
Datadog &bull; <a href="#" style="color:#632ca6;">View full dashboard</a> &bull; <a href="#" style="color:#666666;">Manage digest preferences</a> &bull; <a href="#" style="color:#666666;">Unsubscribe</a>
</td></tr>
</table>
