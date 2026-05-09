"""
email_sender.py
Builds a polished HTML newsletter and sends via Resend or SendGrid.
"""

import requests


SCORE_COLOR = {
    "Strong Match":   ("#d1fae5", "#065f46", "✅"),
    "Moderate Match": ("#fef9c3", "#713f12", "🟡"),
    "Weak Match":     ("#fee2e2", "#7f1d1d", "⚠️"),
    "Skip":           ("#f3f4f6", "#374151", "❌"),
}

def score_bar_html(score: int) -> str:
    if score >= 80:
        color = "#10b981"
    elif score >= 65:
        color = "#f59e0b"
    else:
        color = "#ef4444"
    pct = min(score, 100)
    return f"""
      <div style="background:#e5e7eb;border-radius:4px;height:8px;width:120px;display:inline-block;vertical-align:middle;">
        <div style="background:{color};width:{pct}%;height:8px;border-radius:4px;"></div>
      </div>
      <span style="font-size:13px;font-weight:700;color:{color};margin-left:8px;">{score}/100</span>
    """

def job_card_html(job: dict, rank: int) -> str:
    title       = job.get("title", "Unknown Role")
    company     = job.get("companyName", "Unknown Company")
    location    = job.get("location", "")
    score       = job.get("score", 0)
    verdict     = job.get("verdict", "")
    reasons     = job.get("match_reasons", [])
    gap         = job.get("gap", "")
    exp_req     = job.get("exp_required", "not specified")
    apply_url   = job.get("applyUrl") or job.get("link", "#")
    remote      = job.get("workRemoteAllowed", False)
    posted_at   = job.get("postedAt", "")[:10] if job.get("postedAt") else ""
    emp_type    = job.get("employmentType", "")

    bg, text_color, icon = SCORE_COLOR.get(verdict, ("#f9fafb", "#111827", "•"))
    remote_badge = '<span style="background:#dbeafe;color:#1e40af;border-radius:12px;padding:2px 8px;font-size:11px;margin-left:6px;">Remote</span>' if remote else ""

    reasons_html = "".join(
        f'<li style="color:#374151;font-size:13px;margin:3px 0;">{r}</li>' for r in reasons[:3]
    )

    gap_html = ""
    if gap and gap.lower() != "none":
        gap_html = f'<p style="margin:8px 0 0;font-size:12px;color:#6b7280;"><strong>Gap:</strong> {gap}</p>'

    return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:16px;overflow:hidden;">
      <!-- Header bar -->
      <div style="background:{bg};padding:10px 16px;display:flex;align-items:center;justify-content:space-between;">
        <span style="font-size:12px;font-weight:700;color:{text_color};">{icon} #{rank} — {verdict}</span>
        <span style="font-size:12px;color:{text_color};opacity:0.8;">Exp: {exp_req}</span>
      </div>
      <!-- Job body -->
      <div style="padding:16px;">
        <div style="margin-bottom:8px;">
          <span style="font-size:17px;font-weight:700;color:#111827;">{title}</span>
        </div>
        <div style="font-size:14px;color:#6b7280;margin-bottom:4px;">
          🏢 <strong style="color:#374151;">{company}</strong>
          &nbsp;·&nbsp; 📍 {location}{remote_badge}
        </div>
        <div style="font-size:12px;color:#9ca3af;margin-bottom:12px;">
          {emp_type}{' · ' if emp_type and posted_at else ''}{posted_at}
        </div>
        <!-- Score bar -->
        <div style="margin-bottom:12px;">
          <span style="font-size:12px;color:#6b7280;margin-right:8px;">Compatibility:</span>
          {score_bar_html(score)}
        </div>
        <!-- Match reasons -->
        {'<ul style="margin:0 0 8px;padding-left:18px;">' + reasons_html + '</ul>' if reasons_html else ''}
        {gap_html}
        <!-- Apply button -->
        <div style="margin-top:14px;">
          <a href="{apply_url}"
             style="background:#1d4ed8;color:#ffffff;text-decoration:none;padding:9px 20px;border-radius:8px;font-size:13px;font-weight:600;display:inline-block;">
            Apply Now →
          </a>
          <a href="{job.get('link','#')}"
             style="margin-left:10px;color:#1d4ed8;font-size:13px;text-decoration:none;border:1px solid #bfdbfe;padding:8px 16px;border-radius:8px;display:inline-block;">
            View on LinkedIn
          </a>
        </div>
      </div>
    </div>
    """


def build_html_email(jobs: list[dict], date_str: str, min_score: int) -> str:
    strong   = [j for j in jobs if j.get("score", 0) >= 80]
    moderate = [j for j in jobs if 65 <= j.get("score", 0) < 80]

    cards_html = ""
    rank = 1
    for job in jobs:
        cards_html += job_card_html(job, rank)
        rank += 1

    section_label = ""
    if strong:
        section_label = f'<p style="font-size:13px;color:#059669;margin:0 0 4px;"><strong>✅ {len(strong)} strong match(es)</strong> · <span style="color:#d97706;">{len(moderate)} moderate</span></p>'

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

      <!-- Header -->
      <tr><td style="background:#1e3a5f;border-radius:12px 12px 0 0;padding:28px 32px;">
        <h1 style="color:#ffffff;margin:0;font-size:22px;font-weight:700;">🎯 Your Daily Job Digest</h1>
        <p style="color:#93c5fd;margin:4px 0 0;font-size:14px;">{date_str} · Jobs scored ≥{min_score}/100 for your profile</p>
      </td></tr>

      <!-- Stats row -->
      <tr><td style="background:#1d4ed8;padding:12px 32px;">
        <table width="100%"><tr>
          <td style="color:#bfdbfe;font-size:13px;">
            <strong style="color:#ffffff;font-size:18px;">{len(jobs)}</strong> matches found
          </td>
          <td align="right" style="color:#bfdbfe;font-size:13px;">
            {section_label}
          </td>
        </tr></table>
      </td></tr>

      <!-- Body -->
      <tr><td style="background:#f9fafb;padding:24px 32px;">
        <p style="font-size:14px;color:#374151;margin:0 0 20px;">
          Hi Abhishek! Here are today's best-matched jobs from LinkedIn — sorted by compatibility score.
          Each one has been analyzed against your resume by Claude AI.
        </p>
        {cards_html}
      </td></tr>

      <!-- Footer -->
      <tr><td style="background:#1e3a5f;border-radius:0 0 12px 12px;padding:20px 32px;text-align:center;">
        <p style="color:#93c5fd;font-size:12px;margin:0;">
          Powered by Claude AI · Apify LinkedIn Scraper · GitHub Actions
        </p>
        <p style="color:#60a5fa;font-size:12px;margin:6px 0 0;">
          Jobs scraped from LinkedIn in the last 48 hours · Scores reflect match to your resume
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>
"""


def send_via_resend(html: str, recipient: str, sender: str, api_key: str, date_str: str):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": f"Job Agent <{sender}>",
            "to": [recipient],
            "subject": f"🎯 {date_str} — Your Daily Job Matches",
            "html": html,
        },
        timeout=20,
    )
    resp.raise_for_status()
    print(f"  ✅ Sent via Resend: {resp.json().get('id')}")


def send_via_sendgrid(html: str, recipient: str, sender: str, api_key: str, date_str: str):
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "personalizations": [{"to": [{"email": recipient}]}],
            "from": {"email": sender, "name": "Job Agent"},
            "subject": f"🎯 {date_str} — Your Daily Job Matches",
            "content": [{"type": "text/html", "value": html}],
        },
        timeout=20,
    )
    resp.raise_for_status()
    print(f"  ✅ Sent via SendGrid (status {resp.status_code})")


def send_newsletter(
    jobs: list[dict],
    recipient: str,
    sender: str,
    api_key: str,
    provider: str,
    date_str: str,
    min_score: int,
):
    print(f"📧 Building HTML email ({len(jobs)} jobs)...")
    html = build_html_email(jobs, date_str, min_score)

    print(f"  Sending via {provider} → {recipient}")
    if provider == "resend":
        send_via_resend(html, recipient, sender, api_key, date_str)
    elif provider == "sendgrid":
        send_via_sendgrid(html, recipient, sender, api_key, date_str)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'resend' or 'sendgrid'.")
