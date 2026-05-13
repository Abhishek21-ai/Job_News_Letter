"""
email_sender.py
Builds a polished HTML newsletter and sends via Resend or SendGrid.

Phase 2.1 additions:
  - Diagnoser section (ATS score + weak areas + missing keywords)
  - Recruiter section (role fit + quick wins + differentiators)
  - Tailored resume section (XYZ-rewritten bullets, inline in email)
  All three sections render only when present on the job dict.
"""

import requests


SCORE_COLOR = {
    "Strong Match":   ("#d1fae5", "#065f46", "✅"),
    "Moderate Match": ("#fef9c3", "#713f12", "🟡"),
    "Weak Match":     ("#fee2e2", "#7f1d1d", "⚠️"),
    "Skip":           ("#f3f4f6", "#374151", "❌"),
}


def score_bar_html(score: int) -> str:
    color = "#10b981" if score >= 80 else "#f59e0b" if score >= 65 else "#ef4444"
    pct   = min(score, 100)
    return f"""
      <div style="background:#e5e7eb;border-radius:4px;height:8px;width:120px;
                  display:inline-block;vertical-align:middle;">
        <div style="background:{color};width:{pct}%;height:8px;border-radius:4px;"></div>
      </div>
      <span style="font-size:13px;font-weight:700;color:{color};margin-left:8px;">{score}/100</span>
    """


# ──────────────────────────────────────────────────────────────────────────────
# INTELLIGENCE SECTION BUILDERS
# ──────────────────────────────────────────────────────────────────────────────

def diagnoser_html(data: dict) -> str:
    if not data:
        return ""

    ats_score   = data.get("ats_score", "?")
    weak        = data.get("weak_areas", [])
    missing     = data.get("missing_keywords", [])
    strong      = data.get("strong_areas", [])
    verdict     = data.get("ats_verdict", "")

    weak_items    = "".join(f'<li style="color:#92400e;font-size:12px;margin:2px 0;">{w}</li>' for w in weak[:3])
    missing_items = "".join(
        f'<span style="background:#fef3c7;color:#92400e;border-radius:4px;'
        f'padding:2px 6px;font-size:11px;margin:2px 2px 2px 0;display:inline-block;">'
        f'{k}</span>'
        for k in missing[:6]
    )
    strong_items  = "".join(f'<li style="color:#065f46;font-size:12px;margin:2px 0;">{s}</li>' for s in strong[:3])

    ats_color = "#10b981" if ats_score >= 70 else "#f59e0b" if ats_score >= 50 else "#ef4444"

    return f"""
    <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;
                padding:14px;margin-top:14px;">
      <div style="display:flex;align-items:center;margin-bottom:8px;">
        <span style="font-size:13px;font-weight:700;color:#92400e;">🔬 ATS Diagnosis</span>
        <span style="margin-left:auto;background:{ats_color};color:#fff;border-radius:10px;
                     padding:2px 8px;font-size:11px;font-weight:700;">ATS {ats_score}/100</span>
      </div>
      {f'<p style="font-size:12px;color:#78350f;margin:0 0 8px;font-style:italic;">{verdict}</p>' if verdict else ''}
      {f'<p style="font-size:12px;font-weight:600;color:#92400e;margin:6px 0 2px;">⚠ Weak areas:</p><ul style="margin:0 0 6px;padding-left:16px;">{weak_items}</ul>' if weak_items else ''}
      {f'<p style="font-size:12px;font-weight:600;color:#92400e;margin:6px 0 4px;">🔑 Missing keywords:</p><div style="margin-bottom:6px;">{missing_items}</div>' if missing_items else ''}
      {f'<p style="font-size:12px;font-weight:600;color:#065f46;margin:6px 0 2px;">✅ Strong areas:</p><ul style="margin:0;padding-left:16px;">{strong_items}</ul>' if strong_items else ''}
    </div>
    """


def recruiter_html(data: dict) -> str:
    if not data:
        return ""

    fit_score    = data.get("role_fit_score", "?")
    missing      = data.get("commonly_required_missing", [])
    differents   = data.get("candidate_differentiators", [])
    quick_wins   = data.get("quick_wins", [])
    verdict      = data.get("recruiter_verdict", "")

    missing_items = "".join(f'<li style="color:#7f1d1d;font-size:12px;margin:2px 0;">{m}</li>' for m in missing[:3])
    diff_items    = "".join(f'<li style="color:#065f46;font-size:12px;margin:2px 0;">{d}</li>' for d in differents[:3])
    wins_items    = "".join(
        f'<span style="background:#dcfce7;color:#166534;border-radius:4px;'
        f'padding:2px 6px;font-size:11px;margin:2px 2px 2px 0;display:inline-block;">'
        f'+ {w}</span>'
        for w in quick_wins[:4]
    )

    fit_color = "#10b981" if fit_score >= 70 else "#f59e0b" if fit_score >= 50 else "#ef4444"

    return f"""
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;
                padding:14px;margin-top:10px;">
      <div style="display:flex;align-items:center;margin-bottom:8px;">
        <span style="font-size:13px;font-weight:700;color:#166534;">👔 Recruiter Analysis</span>
        <span style="margin-left:auto;background:{fit_color};color:#fff;border-radius:10px;
                     padding:2px 8px;font-size:11px;font-weight:700;">Fit {fit_score}/100</span>
      </div>
      {f'<p style="font-size:12px;color:#166534;margin:0 0 8px;font-style:italic;">{verdict}</p>' if verdict else ''}
      {f'<p style="font-size:12px;font-weight:600;color:#7f1d1d;margin:6px 0 2px;">📋 Commonly required (missing):</p><ul style="margin:0 0 6px;padding-left:16px;">{missing_items}</ul>' if missing_items else ''}
      {f'<p style="font-size:12px;font-weight:600;color:#065f46;margin:6px 0 2px;">⭐ Your differentiators:</p><ul style="margin:0 0 6px;padding-left:16px;">{diff_items}</ul>' if diff_items else ''}
      {f'<p style="font-size:12px;font-weight:600;color:#166534;margin:6px 0 4px;">⚡ Quick wins:</p><div>{wins_items}</div>' if wins_items else ''}
    </div>
    """


def tailored_resume_html(content: str, title: str, company: str) -> str:
    if not content or content == "Resume rewrite unavailable for this job.":
        return ""

    # Render each line as a styled paragraph; blank lines become spacers
    lines_html = ""
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            lines_html += '<div style="height:6px;"></div>'
        elif stripped.startswith("-"):
            lines_html += (
                f'<div style="font-size:12px;color:#374151;padding:2px 0 2px 12px;">'
                f'• {stripped[1:].strip()}</div>'
            )
        elif stripped.isupper() or stripped.endswith(":"):
            lines_html += (
                f'<div style="font-size:12px;font-weight:700;color:#1e3a5f;'
                f'margin-top:8px;">{stripped}</div>'
            )
        else:
            lines_html += f'<div style="font-size:12px;color:#374151;">{stripped}</div>'

    return f"""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                padding:14px;margin-top:10px;">
      <div style="display:flex;align-items:center;margin-bottom:10px;">
        <span style="font-size:13px;font-weight:700;color:#1e3a5f;">✍️ Tailored Resume</span>
        <span style="margin-left:8px;background:#dbeafe;color:#1e40af;border-radius:10px;
                     padding:2px 8px;font-size:11px;">XYZ Formula · {company}</span>
      </div>
      <div style="border-left:3px solid #3b82f6;padding-left:12px;font-family:monospace;">
        {lines_html}
      </div>
    </div>
    """


# ──────────────────────────────────────────────────────────────────────────────
# JOB CARD
# ──────────────────────────────────────────────────────────────────────────────

def job_card_html(job: dict, rank: int) -> str:
    title     = job.get("title", "Unknown Role")
    company   = job.get("companyName", "Unknown Company")
    location  = job.get("location", "")
    score     = job.get("score", 0)
    verdict   = job.get("verdict", "")
    reasons   = job.get("match_reasons", [])
    gap       = job.get("gap", "")
    exp_req   = job.get("exp_required", "not specified")
    apply_url = job.get("applyUrl") or job.get("link", "#")
    remote    = job.get("workRemoteAllowed", False)
    posted_at = job.get("postedAt", "")[:10] if job.get("postedAt") else ""
    emp_type  = job.get("employmentType", "")

    # Intelligence layer outputs (only present for qualifying jobs)
    diagnoser_data  = job.get("diagnoser")
    recruiter_data  = job.get("recruiter")
    resume_content  = job.get("tailored_resume_content", "")

    bg, text_color, icon = SCORE_COLOR.get(verdict, ("#f9fafb", "#111827", "•"))
    remote_badge = (
        '<span style="background:#dbeafe;color:#1e40af;border-radius:12px;'
        'padding:2px 8px;font-size:11px;margin-left:6px;">Remote</span>'
        if remote else ""
    )

    reasons_html = "".join(
        f'<li style="color:#374151;font-size:13px;margin:3px 0;">{r}</li>'
        for r in reasons[:3]
    )
    gap_html = (
        f'<p style="margin:8px 0 0;font-size:12px;color:#6b7280;">'
        f'<strong>Gap:</strong> {gap}</p>'
        if gap and gap.lower() != "none" else ""
    )

    return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;
                margin-bottom:20px;overflow:hidden;">

      <!-- Header bar -->
      <div style="background:{bg};padding:10px 16px;display:flex;
                  align-items:center;justify-content:space-between;">
        <span style="font-size:12px;font-weight:700;color:{text_color};">
          {icon} #{rank} — {verdict}
        </span>
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

        <!-- Apply buttons -->
        <div style="margin-top:14px;">
          <a href="{apply_url}"
             style="background:#1d4ed8;color:#ffffff;text-decoration:none;
                    padding:9px 20px;border-radius:8px;font-size:13px;
                    font-weight:600;display:inline-block;">
            Apply Now →
          </a>
          <a href="{job.get('link','#')}"
             style="margin-left:10px;color:#1d4ed8;font-size:13px;
                    text-decoration:none;border:1px solid #bfdbfe;
                    padding:8px 16px;border-radius:8px;display:inline-block;">
            View on LinkedIn
          </a>
        </div>

        <!-- Intelligence layer — only rendered when present -->
        {diagnoser_html(diagnoser_data)}
        {recruiter_html(recruiter_data)}
        {tailored_resume_html(resume_content, title, company)}

      </div>
    </div>
    """



# ──────────────────────────────────────────────────────────────────────────────
# REJECTED JOBS FEEDBACK SECTION
# ──────────────────────────────────────────────────────────────────────────────

def rejected_feedback_html(rejected_jobs: list[dict], min_score: int) -> str:
    """
    Renders a compact feedback table of all jobs that were scored but
    didn't meet MIN_SCORE. Shows score, gap, and a direct LinkedIn link
    so you can manually inspect any JD that looks promising.
    """
    if not rejected_jobs:
        return ""

    rows = ""
    for job in rejected_jobs:
        score   = job.get("score", 0)
        title   = job.get("title", "Unknown Role")
        company = job.get("companyName", "Unknown")
        verdict = job.get("verdict", "")
        gap     = job.get("gap", "—")
        exp_req = job.get("exp_required", "?")
        link    = job.get("applyUrl") or job.get("link", "#")
        sim     = job.get("similarity_score", "?")

        # Score colour — shows how close to threshold each job was
        if score >= min_score - 10:
            score_color = "#d97706"   # amber — close miss
            score_bg    = "#fef3c7"
        else:
            score_color = "#6b7280"   # grey — clear reject
            score_bg    = "#f3f4f6"

        verdict_icons = {
            "Moderate Match": "🟡",
            "Weak Match":     "⚠️",
            "Skip":           "❌",
        }
        icon = verdict_icons.get(verdict, "•")

        rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;vertical-align:top;">
            <div style="font-size:13px;font-weight:600;color:#111827;">{title}</div>
            <div style="font-size:11px;color:#6b7280;margin-top:2px;">🏢 {company}</div>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #f3f4f6;
                     text-align:center;vertical-align:top;white-space:nowrap;">
            <span style="background:{score_bg};color:{score_color};font-weight:700;
                         font-size:13px;border-radius:6px;padding:3px 8px;">
              {score}/100
            </span>
            <div style="font-size:10px;color:#9ca3af;margin-top:3px;">{icon} {verdict}</div>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #f3f4f6;vertical-align:top;">
            <div style="font-size:11px;color:#374151;">
              <strong>Gap:</strong> {gap}
            </div>
            <div style="font-size:11px;color:#9ca3af;margin-top:2px;">
              Exp: {exp_req} · sim: {sim}
            </div>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #f3f4f6;
                     text-align:right;vertical-align:top;white-space:nowrap;">
            <a href="{link}"
               style="color:#1d4ed8;font-size:11px;text-decoration:none;
                      border:1px solid #bfdbfe;padding:4px 10px;border-radius:6px;
                      display:inline-block;">
              View JD →
            </a>
          </td>
        </tr>
        """

    close_misses = [j for j in rejected_jobs if j.get("score", 0) >= min_score - 10]
    close_miss_note = (
        f'<p style="font-size:12px;color:#d97706;margin:0 0 10px;">'
        f'⚠️ <strong>{len(close_misses)} close miss(es)</strong> — '
        f'within 10 points of threshold. Worth a manual check.</p>'
        if close_misses else ""
    )

    return f"""
    <!-- Feedback Section -->
    <div style="margin-top:32px;">
      <div style="border-left:4px solid #6b7280;padding-left:12px;margin-bottom:16px;">
        <h2 style="font-size:16px;font-weight:700;color:#374151;margin:0;">
          📋 Rejected Jobs — Why They Didn't Qualify
        </h2>
        <p style="font-size:12px;color:#9ca3af;margin:4px 0 0;">
          Scored but below {min_score}/100 threshold ·
          {len(rejected_jobs)} jobs reviewed
        </p>
      </div>
      {close_miss_note}
      <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;">
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
          <thead>
            <tr style="background:#f9fafb;">
              <th style="padding:8px 12px;text-align:left;font-size:11px;
                         color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">
                JOB
              </th>
              <th style="padding:8px 8px;text-align:center;font-size:11px;
                         color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">
                SCORE
              </th>
              <th style="padding:8px 8px;text-align:left;font-size:11px;
                         color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">
                REASON
              </th>
              <th style="padding:8px 8px;text-align:right;font-size:11px;
                         color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">
                LINK
              </th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
    </div>
    """

# ──────────────────────────────────────────────────────────────────────────────
# EMAIL BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def build_html_email(jobs: list[dict], date_str: str, min_score: int, rejected_jobs: list[dict] | None = None) -> str:
    strong   = [j for j in jobs if j.get("score", 0) >= 80]
    moderate = [j for j in jobs if 65 <= j.get("score", 0) < 80]

    cards_html = ""
    for rank, job in enumerate(jobs, start=1):
        cards_html += job_card_html(job, rank)

    section_label = ""
    if strong:
        section_label = (
            f'<p style="font-size:13px;color:#059669;margin:0 0 4px;">'
            f'<strong>✅ {len(strong)} strong match(es)</strong> · '
            f'<span style="color:#d97706;">{len(moderate)} moderate</span></p>'
        )

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f3f4f6;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"
       style="background:#f3f4f6;padding:32px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="max-width:600px;width:100%;">

      <!-- Header -->
      <tr><td style="background:#1e3a5f;border-radius:12px 12px 0 0;padding:28px 32px;">
        <h1 style="color:#ffffff;margin:0;font-size:22px;font-weight:700;">
          🎯 Your Daily Job Digest
        </h1>
        <p style="color:#93c5fd;margin:4px 0 0;font-size:14px;">
          {date_str} · Jobs scored ≥{min_score}/100 · AI intelligence included
        </p>
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
        <p style="font-size:14px;color:#374151;margin:0 0 6px;">
          Hi Abhishek! Here are today's best-matched jobs — each analysed by
          ATS Diagnoser, Recruiter, and Resume Rewriter.
        </p>
        <p style="font-size:12px;color:#9ca3af;margin:0 0 20px;">
          🔬 ATS Diagnosis &nbsp;·&nbsp; 👔 Recruiter Analysis &nbsp;·&nbsp;
          ✍️ Tailored Resume (XYZ formula) included per job.
        </p>
        {cards_html}
        {rejected_feedback_html(rejected_jobs or [], min_score)}
      </td></tr>

      <!-- Footer -->
      <tr><td style="background:#1e3a5f;border-radius:0 0 12px 12px;
                     padding:20px 32px;text-align:center;">
        <p style="color:#93c5fd;font-size:12px;margin:0;">
          Powered by Groq LLM · Apify LinkedIn Scraper · GitHub Actions
        </p>
        <p style="color:#60a5fa;font-size:12px;margin:6px 0 0;">
          Scraped from LinkedIn in the last 12 hours ·
          Intelligence layer: Diagnoser + Recruiter + Rewriter
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# SEND
# ──────────────────────────────────────────────────────────────────────────────

def send_via_resend(html: str, recipient: str, sender: str, api_key: str, date_str: str):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from":    f"Job Agent <{sender}>",
            "to":      [recipient],
            "subject": f"🎯 {date_str} — Your Daily Job Matches + AI Resume",
            "html":    html,
        },
        timeout=20,
    )
    resp.raise_for_status()
    print(f"  ✅ Sent via Resend: {resp.json().get('id')}")


def send_via_sendgrid(html: str, recipient: str, sender: str, api_key: str, date_str: str):
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "personalizations": [{"to": [{"email": recipient}]}],
            "from":             {"email": sender, "name": "Job Agent"},
            "subject":          f"🎯 {date_str} — Your Daily Job Matches + AI Resume",
            "content":          [{"type": "text/html", "value": html}],
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
    rejected_jobs: list[dict] | None = None,
):
    print(f"📧 Building HTML email ({len(jobs)} jobs)...")
    html = build_html_email(jobs, date_str, min_score, rejected_jobs)

    print(f"  Sending via {provider} → {recipient}")
    if provider == "resend":
        send_via_resend(html, recipient, sender, api_key, date_str)
    elif provider == "sendgrid":
        send_via_sendgrid(html, recipient, sender, api_key, date_str)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'resend' or 'sendgrid'.")
