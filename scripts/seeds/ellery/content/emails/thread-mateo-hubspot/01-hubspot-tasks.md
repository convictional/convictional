---
key: msg-mateo-hubspot-tasks
model: EmailMessage
thread: !ref thread-mateo-hubspot
user: !ref mateo
message_type: received
sender: "HubSpot <notifications@hubspot.com>"
to:
  - !ref mateo
subject: "Daily task reminder — 5 tasks due today"
received_at: !relative_day {offset: 0, hour: 7, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,Helvetica,sans-serif;">
<tr>
  <td style="background-color:#ff7a59;padding:16px 20px;">
    <span style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">HubSpot</span>
  </td>
</tr>
<tr>
  <td style="padding:20px;background-color:#ffffff;color:#33475b;font-size:14px;">
    <p style="margin-top:0;">Good morning, Mateo. You have <strong>5 tasks due today</strong>.</p>

    <table width="100%" cellpadding="10" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:4px;margin:12px 0;">
      <tr style="background-color:#fef8f5;border-bottom:1px solid #e5e7eb;">
        <td style="font-size:13px;color:#33475b;">
          <strong>Send revised term sheet to Amira Saleh</strong><br>
          <span style="color:#7a7a7a;">Company: Keating &amp; Marsh · Deal: Keating Enterprise Pilot · Due: Today</span>
        </td>
        <td style="text-align:right;white-space:nowrap;">
          <span style="background-color:#ff7a59;color:#fff;padding:3px 8px;font-size:11px;border-radius:3px;">HIGH</span>
        </td>
      </tr>
      <tr style="border-bottom:1px solid #e5e7eb;">
        <td style="font-size:13px;color:#33475b;">
          <strong>Follow up with Soma Iyer re: Clio integration call</strong><br>
          <span style="color:#7a7a7a;">Company: Lake Forest Trust · Deal: Lake Forest Pilot · Due: Today</span>
        </td>
        <td style="text-align:right;white-space:nowrap;">
          <span style="background-color:#e5e7eb;color:#555;padding:3px 8px;font-size:11px;border-radius:3px;">MEDIUM</span>
        </td>
      </tr>
      <tr style="border-bottom:1px solid #e5e7eb;">
        <td style="font-size:13px;color:#33475b;">
          <strong>Log notes from Thursday proposal walk-through</strong><br>
          <span style="color:#7a7a7a;">Company: Keating &amp; Marsh · Due: Today (overdue)</span>
        </td>
        <td style="text-align:right;white-space:nowrap;">
          <span style="background-color:#f2545b;color:#fff;padding:3px 8px;font-size:11px;border-radius:3px;">OVERDUE</span>
        </td>
      </tr>
      <tr style="border-bottom:1px solid #e5e7eb;">
        <td style="font-size:13px;color:#33475b;">
          <strong>Research: Harrington Digital — GC contact for prospecting</strong><br>
          <span style="color:#7a7a7a;">Prospecting · Due: Today</span>
        </td>
        <td style="text-align:right;white-space:nowrap;">
          <span style="background-color:#e5e7eb;color:#555;padding:3px 8px;font-size:11px;border-radius:3px;">LOW</span>
        </td>
      </tr>
      <tr>
        <td style="font-size:13px;color:#33475b;">
          <strong>Update pipeline stages for Q2 forecast</strong><br>
          <span style="color:#7a7a7a;">Internal · Due: Today</span>
        </td>
        <td style="text-align:right;white-space:nowrap;">
          <span style="background-color:#e5e7eb;color:#555;padding:3px 8px;font-size:11px;border-radius:3px;">MEDIUM</span>
        </td>
      </tr>
    </table>

    <p style="text-align:center;padding:8px 0;">
      <a href="#" style="background-color:#ff7a59;color:#ffffff;padding:8px 20px;font-family:Arial,sans-serif;font-size:13px;text-decoration:none;border-radius:3px;">Open HubSpot</a>
    </p>

    <p style="font-size:12px;color:#7a7a7a;">You're receiving this daily task digest because task reminders are enabled for your HubSpot account. <a href="#" style="color:#7a7a7a;">Manage notifications</a></p>
  </td>
</tr>
</table>
