"""
Job Newsletter Agent
Scrapes LinkedIn jobs via Apify, filters + scores them with Groq,
and sends a ranked HTML digest to your email.
"""

import os
import json
import time
import requests
from datetime import datetime, timezone
from email_sender import send_newsletter

# ── Config ────────────────────────────────────────────────────────────────────

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]
SENDER_EMAIL = os.environ["SENDER_EMAIL"]

EMAIL_API_KEY = os.environ["EMAIL_API_KEY"]
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "resend")

MIN_SCORE = int(os.environ.get("MIN_SCORE", "90"))
TOP_N = int(os.environ.get("TOP_N", "5"))

# ── Resume Summary ───────────────────────────────────────────────────────────

RESUME_SUMMARY = """
Name: Abhishek Pandey
Experience: 1.5 years industry experience
Current Role: Software Development Engineer at Modak Analytics (Client: Humana)

Core Skills:
- Python (production), FastAPI, REST APIs, Microservices
- Azure Databricks, PySpark, Delta Lake
- Azure Data Factory (ADF), ADLS Gen2
- PostgreSQL, Kafka
- Redis, Celery
- GitHub Actions, CI/CD
- PyTest, Splunk

Certification: Databricks Certified Data Engineer Professional
Education: M.Sc. Computer Science
"""

# ── LinkedIn Search URLs ─────────────────────────────────────────────────────

LINKEDIN_SEARCH_URLS = [

    # ── PUNE ─────────────────────────────────────────────

    # Data Engineer — Pune — Last 24 Hours
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r86400&f_E=2",

    # Backend Engineer Python FastAPI — Pune — Last 24 Hours
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r86400&f_E=2",


    # ── BANGALORE ───────────────────────────────────────

    # Data Engineer — Bangalore — Last 24 Hours
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r86400&f_E=2",

    # Backend Engineer Python — Bangalore — Last 24 Hours
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r86400&f_E=2",


    # ── HYDERABAD ───────────────────────────────────────

    # Data Engineer — Hyderabad — Last 24 Hours
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Hyderabad%2C%20Telangana%2C%20India&f_TPR=r86400&f_E=2",

    # Backend Engineer Python — Hyderabad — Last 24 Hours
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Hyderabad%2C%20Telangana%2C%20India&f_TPR=r86400&f_E=2",


    # ── REMOTE INDIA ────────────────────────────────────

    # Remote Backend Engineer Python
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=India&f_TPR=r86400&f_E=2&f_WT=2",

    # Remote Associate Data Engineer
    "https://www.linkedin.com/jobs/search/?keywords=Associate%20Data%20Engineer%20Python&location=India&f_TPR=r86400&f_E=2&f_WT=2",

]

# ── Smart Local Filtering ────────────────────────────────────────────────────

RELEVANT_KEYWORDS = [
    "python",
    "fastapi",
    "backend",
    "data engineer",
    "databricks",
    "pyspark",
    "kafka",
    "postgresql",
    "etl",
    "azure",
]

EXCLUDED_KEYWORDS = [
    "manager",
    "director",
    "lead",
    "principal",
    "architect",
    "10+ years",
    "12+ years",
]


# ──────────────────────────────────────────────────────────────────────────────
# SCRAPE JOBS
# ──────────────────────────────────────────────────────────────────────────────

def scrape_linkedin_jobs() -> list[dict]:

    print("🔍 Scraping LinkedIn jobs via Apify...")

    run_url = (
        "https://api.apify.com/v2/acts/"
        f"curious_coder~linkedin-jobs-scraper/runs?token={APIFY_TOKEN}"
    )

    payload = {
        "urls": LINKEDIN_SEARCH_URLS,
        "count": 25,
        "scrapeCompany": False,
    }

    resp = requests.post(run_url, json=payload, timeout=30)
    resp.raise_for_status()

    run_id = resp.json()["data"]["id"]

    print(f"  Actor run started: {run_id}")

    # Poll until completed
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
        f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        f"?token={APIFY_TOKEN}&limit=100"
    )

    jobs = items_resp.json()

    print(f"  Retrieved {len(jobs)} raw jobs")

    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# DEDUPLICATE
# ──────────────────────────────────────────────────────────────────────────────

def deduplicate(jobs: list[dict]) -> list[dict]:

    seen = set()
    unique = []

    for job in jobs:

        jid = job.get("id") or job.get("link", "")

        if jid and jid not in seen:
            seen.add(jid)
            unique.append(job)

    print(f"  After dedup: {len(unique)} jobs")

    return unique


# ──────────────────────────────────────────────────────────────────────────────
# PREFILTER
# ──────────────────────────────────────────────────────────────────────────────

def prefilter_jobs(jobs: list[dict]) -> list[dict]:

    filtered = []

    for job in jobs:

        text = (
            f"{job.get('title', '')} "
            f"{job.get('descriptionText', '')}"
        ).lower()

        # Must contain relevant keywords
        if not any(k in text for k in RELEVANT_KEYWORDS):
            continue

        # Exclude senior roles
        if any(k in text for k in EXCLUDED_KEYWORDS):
            continue

        filtered.append(job)

    print(f"🔍 Prefiltered to {len(filtered)} relevant jobs")

    return filtered


# ──────────────────────────────────────────────────────────────────────────────
# GROQ REQUEST WITH RETRY
# ──────────────────────────────────────────────────────────────────────────────

def groq_request(headers, body, retries=5):

    for attempt in range(retries):

        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=30,
        )

        # Handle rate limits
        if r.status_code == 429:

            wait = 2 ** attempt

            print(f"    ⏳ Rate limited. Waiting {wait}s...")

            time.sleep(wait)

            continue

        r.raise_for_status()

        return r

    raise Exception("Groq rate limit exceeded after retries")


# ──────────────────────────────────────────────────────────────────────────────
# SCORE JOB
# ──────────────────────────────────────────────────────────────────────────────

def score_job_with_groq(job: dict) -> dict:

    title = job.get("title", "")
    company = job.get("companyName", "")

    # Reduced token size
    description = (job.get("descriptionText") or "")[:800]

    seniority = job.get("seniorityLevel", "")

    prompt = f"""
You are a career coach scoring job compatibility.

CANDIDATE:
{RESUME_SUMMARY}

JOB:
Title: {title}
Company: {company}
Seniority: {seniority}

Description:
{description}

Return ONLY valid JSON.

{{
  "score": 0-100,
  "verdict": "Strong Match | Moderate Match | Weak Match | Skip",
  "match_reasons": ["reason1", "reason2"],
  "gap": "biggest missing skill",
  "exp_required": "experience range"
}}
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "llama-3.1-8b-instant",
        "temperature": 0.2,
        "max_tokens": 250,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict JSON generator. "
                    "Return ONLY valid JSON."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }

    try:

        r = groq_request(headers, body)

        raw = r.json()["choices"][0]["message"]["content"].strip()

        raw = raw.replace("```json", "").replace("```", "").strip()

        scoring = json.loads(raw)

    except Exception as e:

        print(f"    ⚠ Groq scoring failed for '{title}': {e}")

        scoring = {
            "score": 0,
            "verdict": "Skip",
            "match_reasons": [],
            "gap": "Error",
            "exp_required": "?",
        }

    return {**job, **scoring}


# ──────────────────────────────────────────────────────────────────────────────
# SCORE ALL JOBS
# ──────────────────────────────────────────────────────────────────────────────

def score_all_jobs(jobs: list[dict]) -> list[dict]:

    print(f"🤖 Scoring {len(jobs)} jobs with Groq API...")

    scored = []

    for i, job in enumerate(jobs):

        print(
            f"  [{i+1}/{len(jobs)}] "
            f"{job.get('title', '?')} "
            f"@ {job.get('companyName', '?')}"
        )

        scored.append(score_job_with_groq(job))

        # Small delay
        time.sleep(1)

    return scored


# ──────────────────────────────────────────────────────────────────────────────
# FILTER + RANK
# ──────────────────────────────────────────────────────────────────────────────

def filter_and_rank(scored_jobs: list[dict]) -> list[dict]:

    filtered = [
        j for j in scored_jobs
        if j.get("score", 0) >= MIN_SCORE
    ]

    filtered.sort(
        key=lambda x: x.get("score", 0),
        reverse=True,
    )

    top_jobs = filtered[:TOP_N]

    print(
        f"✅ Returning top {len(top_jobs)} jobs "
        f"(score ≥ {MIN_SCORE})"
    )

    return top_jobs


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    print(f"\n{'='*60}")
    print(f"  Job Newsletter Agent — {today}")
    print(f"{'='*60}\n")

    raw_jobs = scrape_linkedin_jobs()

    unique_jobs = deduplicate(raw_jobs)

    filtered_jobs = prefilter_jobs(unique_jobs)

    # Hard limit before LLM scoring
    filtered_jobs = filtered_jobs[:10]

    print(f"🚀 Sending only {len(filtered_jobs)} jobs to Groq")

    scored_jobs = score_all_jobs(filtered_jobs)

    top_jobs = filter_and_rank(scored_jobs)

    if not top_jobs:

        print("📭 No jobs met the threshold today.")

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

    print(f"\n🎉 Newsletter sent to {RECIPIENT_EMAIL}")


if __name__ == "__main__":
    main()
