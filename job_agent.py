"""
Job Newsletter Agent — Phase 2
Scrapes LinkedIn jobs via Apify, semantically ranks them with local embeddings,
scores top matches with Groq, and sends a ranked HTML digest to your email.

Phase 2 changes vs Phase 1:
  - Embedding-based semantic ranking replaces hard [:10] cap
  - Resume summary used to generate embedding (not just pasted into prompt)
  - Groq LLM now only scores top N semantically similar jobs
  - embedder.py handles all vector logic (zero API cost)
"""

import os
import re
import json
import time
import requests

from datetime import datetime, timezone
from email_sender import send_newsletter
from embedder import build_resume_embedding, rank_jobs_by_similarity

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]
SENDER_EMAIL    = os.environ["SENDER_EMAIL"]

EMAIL_API_KEY  = os.environ["EMAIL_API_KEY"]
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "resend")

MIN_SCORE = int(os.environ.get("MIN_SCORE", "80"))
TOP_N     = int(os.environ.get("TOP_N", "5"))

# How many jobs pass through embeddings → Groq.
# Embedding is cheap (local), Groq is the rate-limit bottleneck.
# 10 is a safe ceiling — keeps Groq usage minimal.
EMBEDDING_TOP_N = int(os.environ.get("EMBEDDING_TOP_N", "10"))

# ──────────────────────────────────────────────────────────────────────────────
# RESUME SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

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

Target Roles:
- Backend Engineer (Python/FastAPI)
- Data Engineer
- Platform Engineer
- Associate Data Engineer

Preferred: Entry-level to 2 years experience required.
Locations: Pune, Bangalore, Hyderabad, Remote India.
"""

# ──────────────────────────────────────────────────────────────────────────────
# LINKEDIN SEARCH URLS
# f_TPR=r43200 = last 12 hours
# f_E=2        = Entry level
# f_WT=2       = Remote
# ──────────────────────────────────────────────────────────────────────────────

LINKEDIN_SEARCH_URLS = [

    # ── PUNE ─────────────────────────────────────────────

    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r43200&f_E=2",

    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r43200&f_E=2",

    # ── BANGALORE ───────────────────────────────────────

    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r43200&f_E=2",

    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r43200&f_E=2",

    # ── HYDERABAD ───────────────────────────────────────

    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Hyderabad%2C%20Telangana%2C%20India&f_TPR=r43200&f_E=2",

    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Hyderabad%2C%20Telangana%2C%20India&f_TPR=r43200&f_E=2",

    # ── REMOTE INDIA ────────────────────────────────────

    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=India&f_TPR=r43200&f_E=2&f_WT=2",

    "https://www.linkedin.com/jobs/search/?keywords=Associate%20Data%20Engineer%20Python&location=India&f_TPR=r43200&f_E=2&f_WT=2",
]

# ──────────────────────────────────────────────────────────────────────────────
# FILTERING RULES
# ──────────────────────────────────────────────────────────────────────────────

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

NEGATIVE_KEYWORDS = [
    "java",
    "spring",
    "springboot",
    ".net",
    "dotnet",
    "php",
    "android",
    "ios",
    "react native",
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

    seen   = set()
    unique = []

    for job in jobs:

        title    = job.get("title", "").strip().lower()
        company  = job.get("companyName", "").strip().lower()
        location = job.get("location", "").strip().lower()

        key = f"{title}|{company}|{location}"

        if key not in seen:
            seen.add(key)
            unique.append(job)

    print(f"  After dedup: {len(unique)} jobs")

    return unique

# ──────────────────────────────────────────────────────────────────────────────
# PREFILTER  (unchanged — still runs before embeddings to reduce noise)
# ──────────────────────────────────────────────────────────────────────────────

def prefilter_jobs(jobs: list[dict]) -> list[dict]:

    filtered = []

    for job in jobs:

        text = (
            f"{job.get('title', '')} "
            f"{job.get('descriptionText', '')}"
        ).lower()

        # Must contain at least one relevant keyword
        if not any(k in text for k in RELEVANT_KEYWORDS):
            continue

        # Exclude unwanted tech stacks
        if any(k in text for k in NEGATIVE_KEYWORDS):
            continue

        # Exclude senior / leadership roles
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

        if r.status_code == 429:
            wait = 2 ** attempt
            print(f"    ⏳ Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            continue

        r.raise_for_status()
        return r

    raise Exception("Groq rate limit exceeded after retries")

# ──────────────────────────────────────────────────────────────────────────────
# SCORE JOB WITH GROQ
# ──────────────────────────────────────────────────────────────────────────────

def score_job_with_groq(job: dict) -> dict:

    title       = job.get("title", "")
    company     = job.get("companyName", "")
    description = (job.get("descriptionText") or "")[:800]
    seniority   = job.get("seniorityLevel", "")
    sim_score   = job.get("similarity_score", "N/A")

    prompt = f"""
You are a career coach scoring job compatibility.

CANDIDATE:
{RESUME_SUMMARY}

JOB:
Title: {title}
Company: {company}
Seniority: {seniority}
Semantic Similarity (pre-computed): {sim_score}

Description:
{description}

Scoring Rules:
1. Python/FastAPI/Backend/Data Engineering relevance
2. Entry-level or 0-3 years preferred
3. Databricks/PySpark/Kafka/Azure are strong positives
4. Remote/Pune/Bangalore/Hyderabad preferred

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
                "content": "You are a strict JSON generator. Return ONLY valid JSON.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }

    try:

        r      = groq_request(headers, body)
        raw    = r.json()["choices"][0]["message"]["content"].strip()
        match  = re.search(r"\{.*\}", raw, re.DOTALL)

        if not match:
            raise ValueError("No JSON found in Groq response")

        scoring = json.loads(match.group())

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

        sim = job.get("similarity_score", "?")

        print(
            f"  [{i+1}/{len(jobs)}] "
            f"{job.get('title', '?')} @ {job.get('companyName', '?')} "
            f"(similarity: {sim})"
        )

        scored.append(score_job_with_groq(job))
        time.sleep(1)

    return scored

# ──────────────────────────────────────────────────────────────────────────────
# FILTER + RANK
# ──────────────────────────────────────────────────────────────────────────────

def filter_and_rank(scored_jobs: list[dict]) -> list[dict]:

    filtered = [j for j in scored_jobs if j.get("score", 0) >= MIN_SCORE]

    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)

    top_jobs = filtered[:TOP_N]

    print(f"✅ Returning top {len(top_jobs)} jobs (score ≥ {MIN_SCORE})")

    return top_jobs

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    print(f"\n{'='*60}")
    print(f"  Job Newsletter Agent — Phase 2 — {today}")
    print(f"{'='*60}\n")

    # ── Step 1: Scrape ────────────────────────────────────────
    raw_jobs = scrape_linkedin_jobs()

    # ── Step 2: Deduplicate ───────────────────────────────────
    unique_jobs = deduplicate(raw_jobs)

    # ── Step 3: Keyword prefilter ─────────────────────────────
    filtered_jobs = prefilter_jobs(unique_jobs)

    if not filtered_jobs:
        print("📭 No jobs passed prefilter today.")
        return

    # ── Step 4: Resume embedding (local, free) ────────────────
    resume_embedding = build_resume_embedding(RESUME_SUMMARY)

    # ── Step 5: Semantic similarity ranking ───────────────────
    # All filtered jobs get embedded; top EMBEDDING_TOP_N are selected.
    # This replaces the old hard [:10] cap with intelligent selection.
    top_similar_jobs = rank_jobs_by_similarity(
        resume_embedding,
        filtered_jobs,
        top_n=EMBEDDING_TOP_N,
    )

    # ── Step 6: Groq LLM scoring (only on top similar jobs) ───
    print(f"🚀 Sending {len(top_similar_jobs)} semantically ranked jobs to Groq")
    scored_jobs = score_all_jobs(top_similar_jobs)

    # ── Step 7: Final ranking by Groq score ───────────────────
    top_jobs = filter_and_rank(scored_jobs)

    if not top_jobs:
        print("📭 No jobs met the score threshold today.")
        return

    # ── Step 8: Send newsletter ───────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
