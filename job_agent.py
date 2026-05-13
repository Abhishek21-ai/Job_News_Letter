"""
Job Newsletter Agent — Phase 2.1
Pipeline:
  Scrape → Dedup → Prefilter → Embed → Similarity Rank
  → Groq Score → [Diagnoser → Recruiter → Rewriter] → Newsletter

Three-actor intelligence layer triggers only when score >= MIN_SCORE:
  Diagnoser : ATS weak-area analysis
  Recruiter : gap analysis vs popular JDs in target role
  Rewriter  : tailored resume rewrite (XYZ formula, preserves structure)
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

from email_sender import send_newsletter
from embedder import build_resume_embedding, rank_jobs_by_similarity, build_resume_embedding_text

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG — all values from GitHub Secrets
# ──────────────────────────────────────────────────────────────────────────────

APIFY_TOKEN     = os.environ["APIFY_TOKEN"]
GROQ_API_KEY    = os.environ["GROQ_API_KEY"]
RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]
SENDER_EMAIL    = os.environ["SENDER_EMAIL"]
EMAIL_API_KEY   = os.environ["EMAIL_API_KEY"]
EMAIL_PROVIDER  = os.environ.get("EMAIL_PROVIDER", "resend")
MIN_SCORE       = int(os.environ.get("MIN_SCORE", "75"))
TOP_N           = int(os.environ.get("TOP_N", "5"))
EMBEDDING_TOP_N = int(os.environ.get("EMBEDDING_TOP_N", "10"))

# Stored in secrets to override LLM inference — prevents freelance/consulting
# history from inflating experience level incorrectly.
CANDIDATE_EXPERIENCE = os.environ.get("CANDIDATE_EXPERIENCE", "1.5 years").strip()
# entry | junior | mid — overrides LinkedIn seniorityLevel which is unreliable
CANDIDATE_SENIORITY  = os.environ.get("CANDIDATE_SENIORITY", "junior").strip()

TAILORED_RESUME_DIR = Path("resumes/tailored")
PROFILE_PATH        = Path("resume_profile.json")

# ──────────────────────────────────────────────────────────────────────────────
# LOAD RESUME PROFILE
# ──────────────────────────────────────────────────────────────────────────────

def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            "resume_profile.json not found. "
            "Set REGENERATE_RESUME=true and run once to generate it."
        )
    with open(PROFILE_PATH) as f:
        return json.load(f)


def build_candidate_context(profile: dict) -> str:
    """
    Builds a rich candidate context string for all Groq prompts.
    Uses CANDIDATE_EXPERIENCE and CANDIDATE_SENIORITY from secrets
    instead of profile-inferred values (which can be wrong for freelancers).
    """
    return f"""
Candidate: {profile.get('name', 'Candidate')}
Experience: {CANDIDATE_EXPERIENCE} industry experience (excluding freelance/consulting)
Seniority: {CANDIDATE_SENIORITY}-level
Primary Roles: {', '.join(profile.get('primary_roles', []))}
Skills: {', '.join(profile.get('skills', []))}
Core Strengths: {', '.join(profile.get('core_strengths', []))}
Domains: {', '.join(profile.get('preferred_domains', []))}
Certifications: {', '.join(profile.get('certifications', []))}
Education: {profile.get('education', '')}
Target Locations: {', '.join(profile.get('target_locations', []))}
""".strip()

# ──────────────────────────────────────────────────────────────────────────────
# LINKEDIN SEARCH URLS
# f_TPR=r43200 = last 12 hours | f_E=2 = Entry level | f_WT=2 = Remote
# ──────────────────────────────────────────────────────────────────────────────

LINKEDIN_SEARCH_URLS = [
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r43200&f_E=2",
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Pune%2C%20Maharashtra%2C%20India&f_TPR=r43200&f_E=2",
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r43200&f_E=2",
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Bengaluru%2C%20Karnataka%2C%20India&f_TPR=r43200&f_E=2",
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer&location=Hyderabad%2C%20Telangana%2C%20India&f_TPR=r43200&f_E=2",
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=Hyderabad%2C%20Telangana%2C%20India&f_TPR=r43200&f_E=2",
    "https://www.linkedin.com/jobs/search/?keywords=Backend%20Engineer%20Python%20FastAPI&location=India&f_TPR=r43200&f_E=2&f_WT=2",
    "https://www.linkedin.com/jobs/search/?keywords=Associate%20Data%20Engineer%20Python&location=India&f_TPR=r43200&f_E=2&f_WT=2",
]

# ──────────────────────────────────────────────────────────────────────────────
# FILTER RULES
# ──────────────────────────────────────────────────────────────────────────────

RELEVANT_KEYWORDS = [
    "python", "fastapi", "backend", "data engineer",
    "databricks", "pyspark", "kafka", "postgresql", "etl", "azure",
]

# Title-level seniority words — these override LinkedIn's unreliable field.
# We check the TITLE specifically, not just the full description.
SENIOR_TITLE_KEYWORDS = [
    "senior", "sr.", "lead", "principal", "staff", "architect",
    "manager", "director", "head of", "vp ", "vice president",
    "10+ years", "12+ years", "8+ years",
]

NEGATIVE_STACK_KEYWORDS = [
    "java", "spring", "springboot", ".net", "dotnet",
    "php", "android", "ios", "react native", "golang", "ruby on rails",
]

# ──────────────────────────────────────────────────────────────────────────────
# SCRAPE
# ──────────────────────────────────────────────────────────────────────────────

def scrape_linkedin_jobs() -> list[dict]:
    print("🔍 Scraping LinkedIn jobs via Apify...")

    run_url = (
        "https://api.apify.com/v2/acts/"
        f"curious_coder~linkedin-jobs-scraper/runs?token={APIFY_TOKEN}"
    )
    resp = requests.post(
        run_url,
        json={"urls": LINKEDIN_SEARCH_URLS, "count": 25, "scrapeCompany": False},
        timeout=30,
    )
    resp.raise_for_status()
    run_id = resp.json()["data"]["id"]
    print(f"  Actor run started: {run_id}")

    status_resp = {}
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
    jobs = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        f"?token={APIFY_TOKEN}&limit=100"
    ).json()

    print(f"  Retrieved {len(jobs)} raw jobs")
    return jobs

# ──────────────────────────────────────────────────────────────────────────────
# DEDUP
# ──────────────────────────────────────────────────────────────────────────────

def deduplicate(jobs: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for job in jobs:
        key = f"{job.get('title','').strip().lower()}|{job.get('companyName','').strip().lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    print(f"  After dedup: {len(unique)} jobs")
    return unique

# ──────────────────────────────────────────────────────────────────────────────
# PREFILTER
# Title-based seniority check is separate and stricter than description check.
# This avoids incorrectly filtering jobs that *mention* "senior" in requirements
# text but are actually entry-level postings.
# ──────────────────────────────────────────────────────────────────────────────

def prefilter_jobs(jobs: list[dict]) -> list[dict]:
    filtered = []
    for job in jobs:
        title = job.get("title", "").lower()
        desc  = (job.get("descriptionText") or "").lower()
        full  = f"{title} {desc}"

        # Title-level seniority check — stricter, uses title only
        if any(k in title for k in SENIOR_TITLE_KEYWORDS):
            continue

        # Stack exclusion — uses full text
        if any(k in full for k in NEGATIVE_STACK_KEYWORDS):
            continue

        # Must have at least one relevant signal
        if not any(k in full for k in RELEVANT_KEYWORDS):
            continue

        filtered.append(job)

    print(f"🔍 Prefiltered to {len(filtered)} relevant jobs")
    return filtered

# ──────────────────────────────────────────────────────────────────────────────
# GROQ HELPER
# ──────────────────────────────────────────────────────────────────────────────

def groq_request(body: dict, retries: int = 5) -> dict:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
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
        return r.json()
    raise Exception("Groq rate limit exceeded after retries")


def groq_json(system: str, user: str, max_tokens: int = 400) -> dict:
    """Single helper for all JSON-returning Groq calls."""
    resp = groq_request({
        "model": "llama-3.1-8b-instant",
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    })
    raw   = resp["choices"][0]["message"]["content"].strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in Groq response: {raw[:200]}")
    return json.loads(match.group())


def groq_text(system: str, user: str, max_tokens: int = 800) -> str:
    """Single helper for all plain-text Groq calls (resume rewriter)."""
    resp = groq_request({
        "model": "llama-3.1-8b-instant",
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    })
    return resp["choices"][0]["message"]["content"].strip()

# ──────────────────────────────────────────────────────────────────────────────
# ACTOR 0 — SCORER
# ──────────────────────────────────────────────────────────────────────────────

def score_job(job: dict, candidate_context: str) -> dict:
    title       = job.get("title", "")
    company     = job.get("companyName", "")
    description = (job.get("descriptionText") or "")[:800]
    sim_score   = job.get("similarity_score", "N/A")

    prompt = f"""
You are a strict recruiter scoring candidate-job compatibility.

CANDIDATE:
{candidate_context}

JOB:
Title: {title}
Company: {company}
Semantic Similarity (pre-computed, 0-1): {sim_score}
Description:
{description}

SCORING RULES:
- Score 80-100: Strong stack match (Python/FastAPI/Databricks/Kafka/Azure) + correct seniority
- Score 65-79:  Partial match — relevant domain but some stack mismatch
- Score 50-64:  Weak match — adjacent role or too senior
- Score <50:    Skip — wrong stack or clearly too senior

IMPORTANT: The candidate has {CANDIDATE_EXPERIENCE} of industry experience.
Do NOT penalise for missing 3+ years if the job only requires 0-2 years.
Do NOT score high if the job clearly requires 5+ years.

Return ONLY valid JSON:
{{
  "score": 0-100,
  "verdict": "Strong Match | Moderate Match | Weak Match | Skip",
  "match_reasons": ["reason1", "reason2", "reason3"],
  "gap": "single biggest missing skill or requirement",
  "exp_required": "experience range from JD"
}}
"""
    try:
        scoring = groq_json(
            system="You are a strict JSON generator. Return ONLY valid JSON. No markdown.",
            user=prompt,
            max_tokens=350,
        )
    except Exception as e:
        print(f"    ⚠ Scorer failed for '{title}': {e}")
        scoring = {
            "score": 0, "verdict": "Skip",
            "match_reasons": [], "gap": "Scoring error",
            "exp_required": "?",
        }

    return {**job, **scoring}


def score_all_jobs(jobs: list[dict], candidate_context: str) -> list[dict]:
    print(f"🤖 Scoring {len(jobs)} jobs with Groq...")
    scored = []
    for i, job in enumerate(jobs):
        print(
            f"  [{i+1}/{len(jobs)}] {job.get('title','?')} @ "
            f"{job.get('companyName','?')} (sim: {job.get('similarity_score','?')})"
        )
        scored.append(score_job(job, candidate_context))
        time.sleep(1)
    return scored

# ──────────────────────────────────────────────────────────────────────────────
# ACTOR 1 — DIAGNOSER
# Acts as an ATS system. Identifies weak areas in the candidate profile
# relative to this specific job. Triggers only for score >= MIN_SCORE.
# ──────────────────────────────────────────────────────────────────────────────

def run_diagnoser(job: dict, candidate_context: str) -> dict:
    title       = job.get("title", "")
    description = (job.get("descriptionText") or "")[:800]

    prompt = f"""
You are a senior ATS (Applicant Tracking System) evaluating a candidate.

CANDIDATE:
{candidate_context}

JOB: {title}
{description}

Diagnose the candidate's profile against this specific job.
Be specific — reference actual skills/keywords from the JD.

Return ONLY valid JSON:
{{
  "ats_score": 0-100,
  "weak_areas": ["specific weakness 1", "specific weakness 2"],
  "missing_keywords": ["keyword from JD not in resume"],
  "strong_areas": ["what the candidate does well for this role"],
  "ats_verdict": "one sentence summary"
}}
"""
    try:
        result = groq_json(
            system="You are a strict ATS evaluator. Return ONLY valid JSON.",
            user=prompt,
            max_tokens=400,
        )
    except Exception as e:
        print(f"    ⚠ Diagnoser failed: {e}")
        result = {
            "ats_score": 0, "weak_areas": [], "missing_keywords": [],
            "strong_areas": [], "ats_verdict": "Analysis unavailable",
        }

    time.sleep(1)
    return result

# ──────────────────────────────────────────────────────────────────────────────
# ACTOR 2 — RECRUITER
# Analyses the resume against what's typically required for this role
# based on the JD. Surfaces what's missing vs what popular JDs expect.
# ──────────────────────────────────────────────────────────────────────────────

def run_recruiter(job: dict, candidate_context: str) -> dict:
    title       = job.get("title", "")
    description = (job.get("descriptionText") or "")[:800]

    prompt = f"""
You are a senior technical recruiter who has reviewed hundreds of {title} JDs.

CANDIDATE:
{candidate_context}

THIS JOB: {title}
{description}

Compare the candidate against what top companies typically require for {title} roles.
Focus on gaps that appear across most JDs, not just this one.

Return ONLY valid JSON:
{{
  "role_fit_score": 0-100,
  "commonly_required_missing": ["skill/tool seen in most {title} JDs but absent from candidate"],
  "candidate_differentiators": ["what makes this candidate stand out for this role"],
  "quick_wins": ["skill to add in 1-2 weeks that would improve fit significantly"],
  "recruiter_verdict": "one sentence honest assessment"
}}
"""
    try:
        result = groq_json(
            system="You are a strict JSON generator. Return ONLY valid JSON.",
            user=prompt,
            max_tokens=400,
        )
    except Exception as e:
        print(f"    ⚠ Recruiter failed: {e}")
        result = {
            "role_fit_score": 0, "commonly_required_missing": [],
            "candidate_differentiators": [], "quick_wins": [],
            "recruiter_verdict": "Analysis unavailable",
        }

    time.sleep(1)
    return result

# ──────────────────────────────────────────────────────────────────────────────
# ACTOR 3 — REWRITER
# Rewrites resume bullet points using the Google XYZ formula:
# "Accomplished [X] as measured by [Y] by doing [Z]"
# Preserves exact structure — only rewrites content, not format.
# Saves tailored resume to resumes/tailored/ with standard naming.
# ──────────────────────────────────────────────────────────────────────────────

def run_rewriter(
    job: dict,
    candidate_context: str,
    diagnoser_output: dict,
    recruiter_output: dict,
    date_str: str,
) -> str:
    """
    Returns the filename of the saved tailored resume (relative path).
    """
    title       = job.get("title", "")
    company     = job.get("companyName", "Unknown")
    description = (job.get("descriptionText") or "")[:600]

    missing_keywords = diagnoser_output.get("missing_keywords", [])
    quick_wins       = recruiter_output.get("quick_wins", [])

    prompt = f"""
You are an expert resume writer specialising in tech roles.

CANDIDATE PROFILE:
{candidate_context}

TARGET JOB: {title} at {company}
JOB DESCRIPTION:
{description}

ATS MISSING KEYWORDS TO INCORPORATE (where truthful):
{', '.join(missing_keywords)}

QUICK WIN SKILLS TO HIGHLIGHT IF PRESENT:
{', '.join(quick_wins)}

TASK:
Rewrite the candidate's work experience bullet points using the Google XYZ formula:
"Accomplished [X] as measured by [Y], by doing [Z]"

STRICT RULES:
1. DO NOT invent skills or experiences not in the candidate profile
2. DO NOT change the section structure (Education, Experience, Skills, etc.)
3. DO NATURALLY incorporate ATS keywords where they honestly apply
4. DO quantify impact wherever possible (use estimates if reasonable)
5. Write in plain text — no markdown headers, no bullet symbols (use dashes)
6. Keep it concise — max 4 bullet points per role
7. End with a "Key Skills for this Role" section listing relevant skills only

Output the full rewritten experience section only (not the entire resume).
"""
    try:
        rewritten = groq_text(
            system=(
                "You are an expert resume writer. "
                "Follow all instructions precisely. "
                "Output plain text only."
            ),
            user=prompt,
            max_tokens=800,
        )
    except Exception as e:
        print(f"    ⚠ Rewriter failed: {e}")
        rewritten = "Resume rewrite unavailable for this job."

    # Save tailored resume
    TAILORED_RESUME_DIR.mkdir(parents=True, exist_ok=True)

    safe_company = re.sub(r"[^a-zA-Z0-9]", "_", company)[:20]
    safe_title   = re.sub(r"[^a-zA-Z0-9]", "_", title)[:25]
    safe_date    = date_str.replace(" ", "_").replace(",", "")

    filename = f"{safe_company}_{safe_title}_{safe_date}.txt"
    filepath = TAILORED_RESUME_DIR / filename

    with open(filepath, "w") as f:
        f.write(f"TAILORED RESUME — {title} at {company}\n")
        f.write(f"Generated: {date_str}\n")
        f.write("=" * 60 + "\n\n")
        f.write(rewritten)

    print(f"    💾 Tailored resume saved: {filepath}")
    time.sleep(1)
    return str(filepath)

# ──────────────────────────────────────────────────────────────────────────────
# INTELLIGENCE LAYER — orchestrates all three actors
# ──────────────────────────────────────────────────────────────────────────────

def run_intelligence_layer(
    job: dict,
    candidate_context: str,
    date_str: str,
) -> dict:
    """
    Runs Diagnoser → Recruiter → Rewriter for a single qualifying job.
    Returns a dict with all intelligence outputs attached.
    """
    title   = job.get("title", "?")
    company = job.get("companyName", "?")

    print(f"\n  🧠 Intelligence layer: {title} @ {company}")

    print(f"    🔬 Diagnoser running...")
    diagnoser = run_diagnoser(job, candidate_context)

    print(f"    👔 Recruiter running...")
    recruiter = run_recruiter(job, candidate_context)

    print(f"    ✍️  Rewriter running...")
    resume_path = run_rewriter(job, candidate_context, diagnoser, recruiter, date_str)

    return {
        **job,
        "diagnoser":    diagnoser,
        "recruiter":    recruiter,
        "resume_path":  resume_path,
    }

# ──────────────────────────────────────────────────────────────────────────────
# FILTER + RANK
# ──────────────────────────────────────────────────────────────────────────────

def filter_and_rank(scored_jobs: list[dict]) -> list[dict]:
    filtered = [j for j in scored_jobs if j.get("score", 0) >= MIN_SCORE]
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = filtered[:TOP_N]
    print(f"✅ {len(top)} jobs meet score threshold (≥{MIN_SCORE})")
    return top

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    print(f"\n{'='*60}")
    print(f"  Job Newsletter Agent — Phase 2.1 — {today}")
    print(f"  Experience: {CANDIDATE_EXPERIENCE} | Seniority: {CANDIDATE_SENIORITY}")
    print(f"{'='*60}\n")

    # ── Load profile ──────────────────────────────────────────
    profile          = load_profile()
    candidate_ctx    = build_candidate_context(profile)

    # ── Step 1: Scrape ────────────────────────────────────────
    raw_jobs = scrape_linkedin_jobs()

    # ── Step 2: Dedup ─────────────────────────────────────────
    unique_jobs = deduplicate(raw_jobs)

    # ── Step 3: Prefilter ─────────────────────────────────────
    filtered_jobs = prefilter_jobs(unique_jobs)
    if not filtered_jobs:
        print("📭 No jobs passed prefilter today.")
        return

    # ── Step 4: Resume embedding (local) ─────────────────────
    resume_text      = build_resume_embedding_text()
    resume_embedding = build_resume_embedding(resume_text)

    # ── Step 5: Semantic similarity ranking ───────────────────
    top_similar_jobs = rank_jobs_by_similarity(
        resume_embedding, filtered_jobs, top_n=EMBEDDING_TOP_N
    )

    # ── Step 6: Groq scoring ──────────────────────────────────
    scored_jobs = score_all_jobs(top_similar_jobs, candidate_ctx)

    # ── Step 7: Filter by score ───────────────────────────────
    top_jobs = filter_and_rank(scored_jobs)
    if not top_jobs:
        print("📭 No jobs met the score threshold today.")
        return

    # ── Step 8: Intelligence layer (Diagnoser+Recruiter+Rewriter)
    # Runs only on qualifying jobs to minimise Groq usage.
    print(f"\n🧠 Running intelligence layer on {len(top_jobs)} qualifying jobs...")
    enriched_jobs = []
    for job in top_jobs:
        enriched = run_intelligence_layer(job, candidate_ctx, today)
        enriched_jobs.append(enriched)

    # ── Step 9: Send newsletter ───────────────────────────────
    send_newsletter(
        jobs=enriched_jobs,
        recipient=RECIPIENT_EMAIL,
        sender=SENDER_EMAIL,
        api_key=EMAIL_API_KEY,
        provider=EMAIL_PROVIDER,
        date_str=today,
        min_score=MIN_SCORE,
    )

    print(f"\n🎉 Newsletter sent → {RECIPIENT_EMAIL}")


if __name__ == "__main__":
    main()
