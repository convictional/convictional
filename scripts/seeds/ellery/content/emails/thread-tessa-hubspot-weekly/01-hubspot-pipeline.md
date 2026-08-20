---
key: msg-hubspot-pipeline
model: EmailMessage
thread: !ref thread-tessa-hubspot-weekly
user: !ref tessa
message_type: received
sender: "HubSpot <notifications@hubspot.com>"
to:
  - !ref tessa
subject: "Your pipeline this week"
received_at: !relative_day {offset: 0, hour: 7, tz: America/New_York}
labels: [inbox, unread]
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,sans-serif;">
<tr>
  <td style="background-color:#ff7a59;padding:20px 24px;">
    <span style="color:#ffffff;font-size:18px;font-weight:bold;">HubSpot</span>
    <span style="color:#ffe8e2;font-size:12px;margin-left:8px;">Weekly Pipeline Digest</span>
  </td>
</tr>
<tr>
  <td style="padding:24px;background-color:#ffffff;">
    <p style="font-size:14px;color:#33475b;margin:0 0 16px 0;"><strong>Your pipeline — week of April 21, 2026</strong></p>
    <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse;font-size:13px;color:#33475b;">
      <tr style="background-color:#f5f8fa;">
        <th style="text-align:left;border-bottom:1px solid #dfe3eb;">Deal</th>
        <th style="text-align:left;border-bottom:1px solid #dfe3eb;">Stage</th>
        <th style="text-align:right;border-bottom:1px solid #dfe3eb;">ACV</th>
        <th style="text-align:left;border-bottom:1px solid #dfe3eb;">Next Step</th>
      </tr>
      <tr>
        <td style="border-bottom:1px solid #eaf0f6;">Keating &amp; Marsh</td>
        <td style="border-bottom:1px solid #eaf0f6;"><span style="color:#00a4bd;font-weight:bold;">Paper Review</span></td>
        <td style="text-align:right;border-bottom:1px solid #eaf0f6;">$220,000</td>
        <td style="border-bottom:1px solid #eaf0f6;">Proposal walk-through Thursday</td>
      </tr>
      <tr>
        <td style="border-bottom:1px solid #eaf0f6;">Lake Forest Trust</td>
        <td style="border-bottom:1px solid #eaf0f6;"><span style="color:#f5a623;font-weight:bold;">Demo Scheduled</span></td>
        <td style="text-align:right;border-bottom:1px solid #eaf0f6;">$48,000</td>
        <td style="border-bottom:1px solid #eaf0f6;">Demo next Monday</td>
      </tr>
      <tr>
        <td style="border-bottom:1px solid #eaf0f6;">Ipso Wakely LLP</td>
        <td style="border-bottom:1px solid #eaf0f6;"><span style="color:#f5a623;font-weight:bold;">Evaluation</span></td>
        <td style="text-align:right;border-bottom:1px solid #eaf0f6;">$64,000</td>
        <td style="border-bottom:1px solid #eaf0f6;">Research session in progress</td>
      </tr>
      <tr>
        <td>Meridian Capital</td>
        <td><span style="color:#999;">Discovery</span></td>
        <td style="text-align:right;">$32,000</td>
        <td>Initial outreach pending</td>
      </tr>
    </table>
    <p style="font-size:13px;color:#33475b;margin:16px 0 8px 0;"><strong>Week-over-week:</strong> 1 deal moved to Paper Review (+1 from last week). Total weighted pipeline: <strong>$176,400</strong>.</p>
    <p style="font-size:13px;color:#33475b;margin:0;">Tasks overdue: <span style="color:#f2545b;font-weight:bold;">2</span> &nbsp;|&nbsp; Meetings logged this week: <strong>4</strong></p>
  </td>
</tr>
<tr>
  <td style="background-color:#f5f8fa;padding:12px 24px;text-align:center;font-size:11px;color:#7c98b6;">
    HubSpot CRM &bull; <a href="#" style="color:#7c98b6;">View pipeline</a> &bull; <a href="#" style="color:#7c98b6;">Manage notifications</a>
  </td>
</tr>
</table>
