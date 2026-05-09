"""
Job Newsletter Agent
Scrapes LinkedIn jobs via Apify, scores them with Claude API,
and sends a ranked HTML digest to your email.
"""

import os, json, time, requests
from datetime import datetime, timezone
from email_sender import send_newsletter

# ── Config (set these as GitHub Secrets / env vars) ──────────────────────────
APIFY_TOKEN      = os.environ["APIFY_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
RECIPIENT_EMAIL  = os.environ["RECIPIENT_EMAIL"]    # your email
SENDER_EMAIL     = os.environ["SENDER_EMAIL"]       # verified sender
EMAIL_API_KEY    = os.environ["EMAIL_API_KEY"]      # SendGrid or Resend key
EMAIL_PROVIDER   = os.environ.get("EMAIL_PROVIDER", "resend")  # "resend" or "sendgrid"
MIN_SCORE        = int(os.environ.get("MIN_SCORE", "70"))

# ── Your resume summary (paste your key skills here) ─────────────────────────
RESUME_SUMMARY = """
Name: Abhishek Pandey
Experience: 1.5 years industry experience
Current Role: Software Development Engineer at Modak Analytics (Client: Humana)

Core Skills:
- Python (production), FastAPI, REST APIs, Microservices, Async Programming
- Azure Databricks, PySpark, Delta Lake, ETL/ELT pipelines
- Azure Data Factory (ADF), ADLS Gen2, Azure SQL
- PostgreSQL (schema design, query optimization, indexing)
- Apache Kafka, Event-Driven Architecture
- Redis (caching), Celery (background tasks)
- GitHub Actions, CI/CD, Databricks Asset Bundles
- PyTest, unit & integration testing (85%+ coverage)
- Splunk, centralized logging

Certification: Databricks Certified Data Engineer Professional
Education: M.Sc. Computer Science, Savitribai Phule Pune University (2024)
Total YOE: ~1.5 years industry + 1.5 years freelance ML/CV
"""

# ── LinkedIn search URLs (customize locations/roles) ─────────────────────────
LINKEDIN_SEARCH_URLS = [
    # Data Engineer — Pune, last 48hrs
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r172800&f_E=2&position=1&pageNum=0",
    # Backend Engineer Python — Pune, last 48hrs
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r172800&f_E=2&position=1&pageNum=0",
    # Data Engineer — Bangalore, last 48hrs
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r172800&f_E=2&position=1&pageNum=0",
    # Remote — Python Backend, India, last 48hrs
    "https://www.linkedin.com/jobs/search/?keywords=Associate%20Backend%20Engineer%20Python&location=India&f_TPR=r172800&f_E=2&f_WT=2&position=1&pageNum=0",
    # Associate Data Engineer India, last 48hrs
    "https://www.linkedin.com/jobs/search/?keywords=Associate%20Data%20Engineer%20Python&location=India&f_TPR=r172800&f_E=2&position=1&pageNum=0",
]


def scrape_linkedin_jobs() -> list[dict]:
    """Run Apify LinkedIn scraper and return raw job list."""
    print("🔍 Scraping LinkedIn jobs via Apify...")
    run_url = f"https://api.apify.com/v2/acts/curious_coder~linkedin-jobs-scraper/runs?token={APIFY_TOKEN}"
    payload = {
        "urls": LINKEDIN_SEARCH_URLS,
        "count": 50,
        "scrapeCompany": False,
    }
    resp = requests.post(run_url, json=payload, timeout=30)
    resp.raise_for_status()
    run_id = resp.json()["data"]["id"]
    print(f"  Actor run started: {run_id}")

    # Poll until finished (max 3 minutes)
    for _ in range(36):
        time.sleep(5)
        status_resp = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"
        ).json()
        status = status_resp["data"]["status"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify run failed: {status}")

    dataset_id = status_resp["data"]["defaultDatasetId"]
    items_resp = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_TOKEN}&limit=100"
    )
    jobs = items_resp.json()
    print(f"  Retrieved {len(jobs)} raw jobs")
    return jobs


def deduplicate(jobs: list[dict]) -> list[dict]:
    """Remove duplicate job IDs."""
    seen = set()
    unique = []
    for job in jobs:
        jid = job.get("id") or job.get("link", "")
        if jid and jid not in seen:
            seen.add(jid)
            unique.append(job)
    print(f"  After dedup: {len(unique)} jobs")
    return unique


def score_job_with_claude(job: dict) -> dict:
    """Ask Claude to score a job against the resume. Returns job + score + reasoning."""
    title = job.get("title", "")
    company = job.get("companyName", "")
    description = (job.get("descriptionText") or "")[:2000]  # cap tokens
    seniority = job.get("seniorityLevel", "")

    prompt = f"""You are a career coach scoring job-resume compatibility for a candidate.

CANDIDATE RESUME SUMMARY:
{RESUME_SUMMARY}

JOB POSTING:
Title: {title}
Company: {company}
Seniority: {seniority}
Description (excerpt):
{description}

Score this job on a scale of 0–100 based on:
1. Tech stack overlap (40 pts) — Python, FastAPI, Databricks, PySpark, PostgreSQL, Kafka, Azure
2. Experience level fit (30 pts) — candidate has 1.5 yrs industry; ideal range is 0–3 yrs
3. Role relevance (20 pts) — Data Engineer, Backend Engineer, or Data Platform Engineer
4. Location/remote fit (10 pts) — Pune preferred, Bangalore or Remote acceptable

Respond ONLY with a JSON object (no markdown, no extra text):
{{
  "score": <integer 0-100>,
  "verdict": "<one of: Strong Match | Moderate Match | Weak Match | Skip>",
  "match_reasons": ["<reason 1>", "<reason 2>", "<reason 3>"],
  "gap": "<1 sentence on the biggest gap, or 'None' if strong match>",
  "exp_required": "<e.g. '0-2 yrs', '3-5 yrs', 'not specified'>"
}}"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=body, timeout=30
        )
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        # Strip accidental markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()
        scoring = json.loads(raw)
    except Exception as e:
        print(f"    ⚠ Claude scoring failed for '{title}': {e}")
        scoring = {"score": 0, "verdict": "Skip", "match_reasons": [], "gap": "Error", "exp_required": "?"}

    return {**job, **scoring}


def score_all_jobs(jobs: list[dict]) -> list[dict]:
    """Score all jobs with Claude, with a small delay to respect rate limits."""
    print(f"🤖 Scoring {len(jobs)} jobs with Claude API...")
    scored = []
    for i, job in enumerate(jobs):
        print(f"  [{i+1}/{len(jobs)}] {job.get('title','?')} @ {job.get('companyName','?')}")
        scored.append(score_job_with_claude(job))
        time.sleep(0.5)  # gentle rate limiting
    return scored


def filter_and_rank(scored_jobs: list[dict]) -> list[dict]:
    """Keep only jobs above MIN_SCORE, sorted descending."""
    filtered = [j for j in scored_jobs if j.get("score", 0) >= MIN_SCORE]
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(f"✅ {len(filtered)} jobs passed score threshold (≥{MIN_SCORE})")
    return filtered


def main():
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    print(f"\n{'='*55}")
    print(f"  Job Newsletter Agent — {today}")
    print(f"{'='*55}\n")

    raw_jobs    = scrape_linkedin_jobs()
    unique_jobs = deduplicate(raw_jobs)
    scored_jobs = score_all_jobs(unique_jobs)
    top_jobs    = filter_and_rank(scored_jobs)

    if not top_jobs:
        print("📭 No jobs met the score threshold today. No email sent.")
        return

    send_newsletter(
        jobs=top_jobs,
        recipient=RECIPIENT_EMAIL,
        sender=SENDER_EMAIL,
        api_key=EMAIL_API_KEY,
        provider=EMAIL_PROVIDER,
        date_str=today,
        min_score=MIN_SCORE,
    )
    print(f"\n🎉 Done! Newsletter sent to {RECIPIENT_EMAIL}")


if __name__ == "__main__":
    main()
